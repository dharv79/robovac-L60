# -*- coding: utf-8 -*-

# Copyright 2019 Richard Mitchell
# Copyright (c) 2026 Dave Harvey
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Based on portions of https://github.com/codetheweb/tuyapi/
#
# MIT License
#
# Copyright (c) 2017 Max Isom
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import asyncio
import base64
import json
import logging
import random
import struct
import time
import zlib
from collections import deque
from typing import Callable, Coroutine

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hashes import MD5, Hash
from cryptography.hazmat.primitives.padding import PKCS7

INITIAL_BACKOFF = 5
INITIAL_QUEUE_TIME = 0.1
BACKOFF_MULTIPLIER = 1.70224
MAX_BACKOFF = 600
BACKOFF_JITTER = 0.2

# Full payloads and frame hex in debug logs. Off by default; Phase 13's
# capture option turns it on. Otherwise debug lines carry a one-line summary.
VERBOSE = False

# UPDATEDPS queries sent per TuyaDevice while a queried DPS is still missing.
# Bounds the damage if a device drops the socket on the command.
MAX_DPS_QUERIES = 3
MAX_QUEUE_LENGTH = 20
_LOGGER = logging.getLogger(__name__)
MESSAGE_PREFIX_FORMAT = ">IIII"
MESSAGE_SUFFIX_FORMAT = ">II"
HEADER_SIZE = struct.calcsize(MESSAGE_PREFIX_FORMAT)
SUFFIX_SIZE = struct.calcsize(MESSAGE_SUFFIX_FORMAT)
RETURN_CODE_SIZE = struct.calcsize(">I")
MAGIC_PREFIX = 0x000055AA
MAGIC_SUFFIX = 0x0000AA55
MAGIC_SUFFIX_BYTES = struct.pack(">I", MAGIC_SUFFIX)


class TuyaException(Exception):
    """Base for Tuya exceptions."""


class InvalidKey(TuyaException):
    """The local key is invalid."""


class InvalidMessage(TuyaException):
    """The message received is invalid."""


class MessageDecodeFailed(TuyaException):
    """The message received cannot be decoded as JSON."""


class ConnectionException(TuyaException):
    """The socket connection failed."""


class ConnectionTimeoutException(ConnectionException):
    """The socket connection timed out."""


class RequestResponseCommandMismatch(TuyaException):
    """The command in the response didn't match the one from the request."""


class ResponseTimeoutException(TuyaException):
    """Did not recieve a response to the request within the timeout."""


class BackoffException(TuyaException):
    """Backoff time not reached."""


class TuyaCipher:
    """Tuya cryptographic helpers."""

    def __init__(self, key, version):
        self.version = version
        self.key = key
        self.cipher = Cipher(algorithms.AES(key.encode("ascii")), modes.ECB())

    def get_prefix_size_and_validate(self, command, encrypted_data):
        try:
            version = tuple(map(int, encrypted_data[:3].decode("utf8").split(".")))
        except ValueError:
            version = (0, 0)
        if version != self.version:
            return 0
        if version < (3, 3):
            hash_value = encrypted_data[3:19].decode("ascii")
            expected_hash = self.hash(encrypted_data[19:])
            if hash_value != expected_hash:
                return 0
            return 19
        if command in (Message.SET_COMMAND, Message.GRATUITOUS_UPDATE):
            return 15
        return 0

    def decrypt(self, command, data):
        prefix_size = self.get_prefix_size_and_validate(command, data)
        data = data[prefix_size:]
        decryptor = self.cipher.decryptor()
        if self.version < (3, 3):
            data = base64.b64decode(data)
        decrypted_data = decryptor.update(data)
        decrypted_data += decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted_data)
        unpadded_data += unpadder.finalize()
        return unpadded_data

    def encrypt(self, command, data):
        encrypted_data = b""
        if data:
            padder = PKCS7(128).padder()
            padded_data = padder.update(data)
            padded_data += padder.finalize()
            encryptor = self.cipher.encryptor()
            encrypted_data = encryptor.update(padded_data)
            encrypted_data += encryptor.finalize()

        prefix = ".".join(map(str, self.version)).encode("utf8")
        if self.version < (3, 3):
            payload = base64.b64encode(encrypted_data)
            hash_value = self.hash(payload)
            prefix += hash_value.encode("utf8")
        else:
            payload = encrypted_data
            if command in (Message.SET_COMMAND, Message.GRATUITOUS_UPDATE):
                prefix += b"\x00" * 12
            else:
                prefix = b""

        return prefix + payload

    def hash(self, data):
        digest = Hash(MD5())
        to_hash = "data={}||lpv={}||{}".format(
            data.decode("ascii"), ".".join(map(str, self.version)), self.key
        )
        digest.update(to_hash.encode("utf8"))
        intermediate = digest.finalize().hex()
        return intermediate[8:24]


def crc(data):
    """Calculate the Tuya CRC of some data (standard CRC-32)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def backoff_interval(failures):
    """Queue delay after `failures` (>3) consecutive send failures, with jitter."""
    base = min(INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** (failures - 4)), MAX_BACKOFF)
    return base * random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)


def _log_undecodable(device, payload_data, err):
    if VERBOSE:
        device._LOGGER.debug("Undecodable payload %s: %s", payload_data.hex(), err)
    else:
        device._LOGGER.debug(
            "Undecodable payload (%s bytes): %s", len(payload_data), err
        )


class Message:
    PING_COMMAND = 0x09
    UPDATE_DPS_COMMAND = 0x12  # UPDATEDPS: ask the device to push these DPS
    GET_COMMAND = 0x0A
    SET_COMMAND = 0x07
    GRATUITOUS_UPDATE = 0x08

    def __init__(
        self,
        command,
        payload=None,
        sequence=None,
        encrypt=False,
        device=None,
        expect_response=True,
        ttl=5,
    ):
        if payload is None:
            payload = b""
        self.payload = payload
        self.command = command
        self.original_sequence = sequence
        if sequence is None:
            self.set_sequence()
        else:
            self.sequence = sequence
        self.encrypt = encrypt
        self.device = device
        self.expiry = int(time.time()) + ttl
        self.expect_response = expect_response
        self.listener = None
        if expect_response:
            self.listener = asyncio.Semaphore(0)
            if device is not None:
                device._listeners[self.sequence] = self.listener

    def __repr__(self):
        return "{}({}, {!r}, {!r}, {})".format(
            self.__class__.__name__,
            hex(self.command),
            self.payload,
            self.sequence,
            "<Device {}>".format(self.device) if self.device else None,
        )

    def summary(self):
        """One-line description for logs: command, sequence and DPS keys."""
        dps = self.payload.get("dps") if isinstance(self.payload, dict) else None
        keys = ",".join(sorted(map(str, dps))) if isinstance(dps, dict) else "-"
        return f"cmd={hex(self.command)} seq={self.sequence} dps=[{keys}]"

    def describe(self):
        """Full repr when VERBOSE is on, otherwise the summary."""
        return repr(self) if VERBOSE else self.summary()

    _last_sequence = 0

    def set_sequence(self):
        # Strictly increasing: a ms clock alone gives two messages built in the
        # same ms one sequence, and the second overwrites the first's listener.
        sequence = max(int(time.perf_counter() * 1000), Message._last_sequence + 1)
        Message._last_sequence = sequence
        self.sequence = sequence & 0xFFFFFFFF

    def hex(self):
        return self.bytes().hex()

    def bytes(self):
        payload_data = self.payload
        if isinstance(payload_data, dict):
            payload_data = json.dumps(payload_data, separators=(",", ":"))
        if not isinstance(payload_data, bytes):
            payload_data = payload_data.encode("utf8")

        if self.encrypt:
            payload_data = self.device.cipher.encrypt(self.command, payload_data)

        payload_size = len(payload_data) + SUFFIX_SIZE

        header = struct.pack(
            MESSAGE_PREFIX_FORMAT,
            MAGIC_PREFIX,
            self.sequence,
            self.command,
            payload_size,
        )
        if self.device and self.device.version >= (3, 3):
            checksum = crc(header + payload_data)
        else:
            checksum = crc(payload_data)
        footer = struct.pack(MESSAGE_SUFFIX_FORMAT, checksum, MAGIC_SUFFIX)
        return header + payload_data + footer

    __bytes__ = bytes

    @classmethod
    def from_bytes(cls, device, data, cipher=None):
        try:
            prefix, sequence, command, payload_size = struct.unpack_from(
                MESSAGE_PREFIX_FORMAT, data
            )
        except struct.error as e:
            raise InvalidMessage("Invalid message header format.") from e
        if prefix != MAGIC_PREFIX:
            raise InvalidMessage("Magic prefix missing from message.")

        try:
            (return_code,) = struct.unpack_from(">I", data, HEADER_SIZE)
        except struct.error as e:
            raise InvalidMessage("Unable to unpack return code.") from e

        body_end = HEADER_SIZE + payload_size - SUFFIX_SIZE
        # Device responses carry a 4-byte return code before the payload.
        body_start = HEADER_SIZE if return_code >> 8 else HEADER_SIZE + RETURN_CODE_SIZE
        payload_data = data[body_start:body_end]

        try:
            expected_crc, suffix = struct.unpack_from(
                MESSAGE_SUFFIX_FORMAT, data, body_end
            )
        except struct.error as e:
            raise InvalidMessage("Invalid message suffix format.") from e
        if suffix != MAGIC_SUFFIX:
            raise InvalidMessage("Magic suffix missing from message")

        if expected_crc != crc(data[:body_end]):
            raise InvalidMessage("CRC check failed")

        payload = None
        if payload_data:
            try:
                payload_data = cipher.decrypt(command, payload_data)
            except ValueError:
                pass
            try:
                payload_text = payload_data.decode("utf8")
            except UnicodeDecodeError as e:
                _log_undecodable(device, payload_data, e)
                raise MessageDecodeFailed() from e
            try:
                payload = json.loads(payload_text)
            except json.decoder.JSONDecodeError as e:
                _log_undecodable(device, payload_data, e)
                raise MessageDecodeFailed() from e

        return cls(command, payload, sequence)


class TuyaDevice:
    """Represents a generic Tuya device."""

    def __init__(
        self,
        model_details,
        device_id,
        host,
        timeout,
        ping_interval,
        update_entity_state,
        local_key=None,
        port=6668,
        gateway_id=None,
        version=(3, 3),
    ):
        self._LOGGER = _LOGGER.getChild(device_id)
        self.model_details = model_details
        self.device_id = device_id
        self.host = host
        self.port = port
        self.gateway_id = gateway_id or device_id
        self.version = version
        self.timeout = timeout
        self.last_ping = 0
        self.last_pong = 0
        self.ping_interval = ping_interval
        self.update_entity_state_cb = update_entity_state

        if not local_key or len(local_key) != 16:
            raise InvalidKey("Local key should be a 16-character string")

        self.cipher = TuyaCipher(local_key, self.version)
        self.writer = None
        self.reader = None
        self._response_task = None
        self._reader_task = None
        self._ping_task = None
        self._handlers: dict[int, Callable[[Message], Coroutine]] = {
            Message.GRATUITOUS_UPDATE: self.async_gratuitous_update_state,
            Message.PING_COMMAND: self._async_pong_received,
            Message.UPDATE_DPS_COMMAND: self._async_update_dps_reply,
        }
        self._dps = {}
        self._connected = False
        self._enabled = True
        self._queue: deque[Message] = deque()
        self._listeners = {}
        self._backoff = False
        self._queue_interval = INITIAL_QUEUE_TIME
        self._failures = 0
        self._backoff_ended = asyncio.Event()
        self._background_tasks: set[asyncio.Task] = set()
        # DPS the model wants pushed on connect (GET doesn't return them).
        self._query_dps = tuple(getattr(model_details, "query_dps_on_connect", ()))
        self._dps_queries = 0

        self._queue_task = asyncio.create_task(self.process_queue())

    def __repr__(self):
        return "{}({!r}, {!r}, {!r}, {!r})".format(
            self.__class__.__name__,
            self.device_id,
            self.host,
            self.port,
            self.cipher.key,
        )

    def __str__(self):
        return "{} ({}:{})".format(self.device_id, self.host, self.port)

    @property
    def _encrypt(self) -> bool:
        return self.version >= (3, 3)

    async def process_queue(self):
        while self._enabled:
            self.clean_queue()

            if self._queue:
                self._LOGGER.debug(
                    "Processing queue. Current length: %s", len(self._queue)
                )
                try:
                    await self._async_send(self._queue.popleft())
                    self._reset_backoff()
                except Exception as e:
                    self._failures += 1
                    self._LOGGER.debug("%s failures. Most recent: %s", self._failures, e)
                    if self._failures > 3:
                        # Debug only: the entity logs the one unavailable warning.
                        self._backoff = True
                        self._queue_interval = backoff_interval(self._failures)
                        self._LOGGER.debug(
                            "%s failures, backing off for %.1f seconds",
                            self._failures,
                            self._queue_interval,
                        )

            # A successful push ends a backoff early (see _reset_backoff).
            try:
                await asyncio.wait_for(self._backoff_ended.wait(), self._queue_interval)
            except TimeoutError:
                pass
            self._backoff_ended.clear()

    def _reset_backoff(self):
        """Clear failure state after a successful send or a device push."""
        was_backing_off = self._backoff
        self._failures = 0
        self._queue_interval = INITIAL_QUEUE_TIME
        self._backoff = False
        if was_backing_off:
            self._LOGGER.debug("%s responding again; backoff cleared", self)
            self._backoff_ended.set()

    def clean_queue(self):
        now = int(time.time())
        if any(item.expiry <= now for item in self._queue):
            self._queue = deque(item for item in self._queue if item.expiry > now)

    def _enqueue(self, message):
        """Queue a message, replacing stale SETs and keeping the queue bounded."""
        self.clean_queue()
        if message.command == Message.SET_COMMAND:
            # An unsent SET whose DPS are all overwritten by this one is stale.
            new_codes = set(message.payload["dps"])
            kept = deque(
                item
                for item in self._queue
                if item.command != Message.SET_COMMAND
                or not set(item.payload["dps"]) <= new_codes
            )
            if len(kept) != len(self._queue):
                self._LOGGER.debug(
                    "Replaced %s queued SET(s) for DPS %s",
                    len(self._queue) - len(kept),
                    sorted(new_codes),
                )
                self._queue = kept
        while len(self._queue) >= MAX_QUEUE_LENGTH:
            # Prefer dropping a message nobody is waiting on (ping/SET).
            dropped = next(
                (item for item in self._queue if not item.expect_response),
                self._queue[0],
            )
            self._queue.remove(dropped)
            self._LOGGER.warning(
                "Send queue for %s full; dropped %s", self, dropped.describe()
            )
        self._queue.append(message)

    async def async_connect(self):
        if self._connected or not self._enabled:
            return

        self._LOGGER.debug("Connecting to %s", self)
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except TimeoutError as e:
            raise ConnectionTimeoutException("Connection timed out") from e
        except OSError as e:
            raise ConnectionException(
                "Connection to {} failed: {}".format(self, e)
            ) from e
        self._connected = True

        if self._ping_task is None or self._ping_task.done():
            self._ping_task = asyncio.create_task(self.async_ping(self.ping_interval))

        self._reader_task = asyncio.create_task(self._async_handle_message())
        await self._async_query_dps()

    async def _async_query_dps(self):
        """Ask the device to push DPS its GET reply leaves out (model-gated)."""
        missing = [code for code in self._query_dps if str(code) not in self._dps]
        if not missing or self._dps_queries >= MAX_DPS_QUERIES:
            return
        self._dps_queries += 1
        message = Message(
            Message.UPDATE_DPS_COMMAND,
            {"dpId": [int(code) for code in missing]},
            encrypt=self._encrypt,
            device=self,
            expect_response=False,
        )
        self._LOGGER.debug(
            "Querying DPS %s on connect (attempt %s)", missing, self._dps_queries
        )
        try:
            # Called from inside _async_send, so write directly: the queue
            # task already serialises writes and this goes ahead of its message.
            self.writer.write(message.bytes())
            await self.writer.drain()
        except OSError as e:
            self._LOGGER.debug("DPS query to %s failed: %r", self, e)

    async def _async_update_dps_reply(self, message):
        self._LOGGER.debug("UPDATEDPS reply from %s: %s", self, message.describe())

    async def async_disable(self):
        self._enabled = False
        await self.async_disconnect()
        for task in (self._queue_task, self._ping_task, self._reader_task):
            if task is not None and task is not asyncio.current_task():
                task.cancel()
        for task in self._background_tasks:
            task.cancel()

    async def async_disconnect(self):
        if not self._connected:
            return

        self._LOGGER.debug("Disconnected from %s", self)
        self._connected = False
        self.last_pong = 0

        if self._response_task is not None and not self._response_task.done():
            self._response_task.cancel()
        self._response_task = None

        writer, self.writer = self.writer, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

        if self.reader is not None and not self.reader.at_eof():
            self.reader.feed_eof()
        self.reader = None

    async def async_get(self):
        payload = {"gwId": self.gateway_id, "devId": self.device_id}
        message = Message(
            Message.GET_COMMAND, payload, encrypt=self._encrypt, device=self
        )
        self._enqueue(message)
        response = await self.async_receive(message)
        await self.async_update_state(response)

    async def async_set(self, dps):
        payload = {"devId": self.device_id, "uid": "", "t": int(time.time()), "dps": dps}
        message = Message(
            Message.SET_COMMAND,
            payload,
            encrypt=True,
            device=self,
            expect_response=False,
        )
        self._enqueue(message)

    async def async_ping(self, ping_interval):
        while self._enabled:
            if self._backoff:
                self._LOGGER.debug("Currently in backoff, not adding ping to queue")
            else:
                self.last_ping = time.time()
                self._enqueue(
                    Message(
                        Message.PING_COMMAND,
                        sequence=0,
                        encrypt=self._encrypt,
                        device=self,
                        expect_response=False,
                    )
                )

            await asyncio.sleep(ping_interval)
            if self.last_pong < self.last_ping:
                await self.async_disconnect()

    async def _async_pong_received(self, message):
        self.last_pong = time.time()

    async def async_gratuitous_update_state(self, state_message):
        # An unsolicited push proves the device is reachable.
        self._reset_backoff()
        await self.async_update_state(state_message)
        await self.update_entity_state_cb()

    async def async_update_state(self, state_message, _=None):
        if (
            state_message is not None
            and state_message.payload
            and state_message.payload.get("dps")
        ):
            self._dps.update(state_message.payload["dps"])
            if VERBOSE:
                self._LOGGER.debug("Received updated state %s: %s", self, self._dps)
            else:
                self._LOGGER.debug(
                    "Received updated state %s: dps=[%s]",
                    self,
                    ",".join(sorted(map(str, state_message.payload["dps"]))),
                )

    @property
    def state(self):
        return dict(self._dps)

    def _dispatch(self, message):
        listener = self._listeners.get(message.sequence)
        if listener is not None:
            if isinstance(listener, asyncio.Semaphore):
                self._listeners[message.sequence] = message
                listener.release()
            return

        handler = self._handlers.get(message.command)
        if handler is not None:
            task = asyncio.create_task(handler(message))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _async_handle_message(self):
        reader = self.reader
        while self._enabled and self._connected and self.reader is reader:
            read_task = asyncio.create_task(reader.readuntil(MAGIC_SUFFIX_BYTES))
            self._response_task = read_task
            try:
                message = Message.from_bytes(self, await read_task, self.cipher)
            except asyncio.CancelledError:
                self._LOGGER.debug("Response task cancelled for %s", self)
                return
            except InvalidMessage as e:
                self._LOGGER.debug("Invalid message from %s: %s", self, e)
                continue
            except MessageDecodeFailed:
                self._LOGGER.debug("Failed to decrypt message from %s", self)
                continue
            except Exception as e:
                # EOF, reset, or an unrecoverable buffer state: retrying the read
                # would fail immediately, so drop the connection and let the next
                # send reconnect.
                self._LOGGER.debug("Connection to %s lost: %r", self, e)
                if self.reader is reader:
                    await self.async_disconnect()
                return
            finally:
                if self._response_task is read_task:
                    self._response_task = None

            self._LOGGER.debug(
                "Received message from %s: %s", self, message.describe()
            )
            self._dispatch(message)

    async def _async_send(self, message, retries=2):
        self._LOGGER.debug("Sending to %s: %s", self, message.describe())
        for attempt in range(retries, -1, -1):
            try:
                await self.async_connect()
                self.writer.write(message.bytes())
                await self.writer.drain()
                return
            except Exception as e:
                if attempt == 0:
                    if isinstance(e, OSError):
                        await self.async_disconnect()
                        raise ConnectionException(
                            "Connection to {} failed: {}".format(self, e)
                        ) from e
                    if isinstance(e, asyncio.IncompleteReadError):
                        raise InvalidMessage(
                            "Incomplete read from: {} : {}".format(self, e)
                        ) from e
                    raise TuyaException(
                        "Failed to send data to {}".format(self)
                    ) from e

                self._LOGGER.debug(
                    "Retrying send to %s due to error: %r", self, e
                )
                await asyncio.sleep(0.25)

    async def async_receive(self, message):
        if not message.expect_response:
            return None

        listener = message.listener
        if listener is None:
            raise TuyaException(
                "Message {} expected a response but has no listener".format(
                    message.sequence
                )
            )

        try:
            await asyncio.wait_for(listener.acquire(), timeout=self.timeout)
        except TimeoutError as e:
            self._listeners.pop(message.sequence, None)
            await self.async_disconnect()
            raise ResponseTimeoutException(
                "Timed out waiting for response to sequence number {}".format(
                    message.sequence
                )
            ) from e
        except BaseException:
            self._listeners.pop(message.sequence, None)
            await self.async_disconnect()
            raise

        response = self._listeners.pop(message.sequence, None)
        if response is None:
            raise ResponseTimeoutException(
                "Listener for sequence {} disappeared before response retrieval".format(
                    message.sequence
                )
            )
        if isinstance(response, Exception):
            raise response
        return response
