# Copyright 2022 Brendan McCluskey
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

"""Tuya local protocol: cipher, framing, send queue, backoff, DPS query."""

from __future__ import annotations

import asyncio
import json
import struct
from types import SimpleNamespace

import pytest

from custom_components.robovac import tuyalocalapi as tla
from custom_components.robovac.tuyalocalapi import Message, TuyaCipher
from custom_components.robovac.vacuums.T2267 import T2267

from .conftest import TEST_KEY


async def _noop():
    return None


@pytest.fixture
async def device():
    dev = tla.TuyaDevice(
        SimpleNamespace(), "dobby-id", "192.0.2.10", 1, 9999, _noop, local_key=TEST_KEY
    )
    yield dev
    await dev.async_disable()


def device_frame(cipher, command, payload: dict, sequence=7) -> bytes:
    """Build a frame as the device sends it: return code, then encrypted body."""
    body = struct.pack(">I", 0) + cipher.encrypt(command, json.dumps(payload).encode())
    header = struct.pack(
        tla.MESSAGE_PREFIX_FORMAT,
        tla.MAGIC_PREFIX,
        sequence,
        command,
        len(body) + tla.SUFFIX_SIZE,
    )
    footer = struct.pack(tla.MESSAGE_SUFFIX_FORMAT, tla.crc(header + body), tla.MAGIC_SUFFIX)
    return header + body + footer


# --- Cipher and framing ---------------------------------------------------


@pytest.mark.parametrize(
    ("command", "prefixed"),
    [(Message.SET_COMMAND, True), (Message.GET_COMMAND, False)],
)
def test_cipher_round_trip(command, prefixed):
    cipher = TuyaCipher(TEST_KEY, (3, 3))
    data = b'{"dps":{"152":"AggN"}}'
    encrypted = cipher.encrypt(command, data)
    assert encrypted.startswith(b"3.3") is prefixed
    assert data not in encrypted
    assert cipher.decrypt(command, encrypted) == data


def test_device_frame_decodes(device):
    payload = {"dps": {"153": "AA==", "163": 87}}
    frame = device_frame(device.cipher, Message.GRATUITOUS_UPDATE, payload, sequence=42)
    message = Message.from_bytes(device, frame, device.cipher)
    assert message.command == Message.GRATUITOUS_UPDATE
    assert message.sequence == 42
    assert message.payload == payload


def test_crc_mismatch_rejected(device):
    frame = bytearray(device_frame(device.cipher, Message.GRATUITOUS_UPDATE, {"dps": {}}))
    frame[-9] ^= 0xFF  # flip a CRC byte
    with pytest.raises(tla.InvalidMessage):
        Message.from_bytes(device, bytes(frame), device.cipher)


def test_truncated_frame_rejected(device):
    frame = device_frame(device.cipher, Message.GRATUITOUS_UPDATE, {"dps": {}})
    with pytest.raises(tla.InvalidMessage):
        Message.from_bytes(device, frame[:20], device.cipher)


def test_set_message_bytes_round_trip(device):
    message = Message(
        Message.SET_COMMAND,
        {"dps": {"152": "AggG"}},
        encrypt=True,
        device=device,
        expect_response=False,
    )
    decoded = Message.from_bytes(device, message.bytes(), device.cipher)
    assert decoded.payload == {"dps": {"152": "AggG"}}
    assert decoded.sequence == message.sequence


def test_summary_hides_values():
    message = Message(Message.SET_COMMAND, {"dps": {"152": "AggN", "5": "auto"}}, 7)
    message.expect_response = False
    assert message.summary() == "cmd=0x7 seq=7 dps=[152,5]"
    assert "AggN" not in message.describe()
    ping = Message(Message.PING_COMMAND, sequence=0, expect_response=False)
    assert ping.summary() == "cmd=0x9 seq=0 dps=[-]"


# --- Send queue (Phase 04) ------------------------------------------------


async def test_stale_set_replaced_get_kept(device):
    await device.async_set({"152": "AggN"})
    device._enqueue(Message(Message.GET_COMMAND, {}, device=device))
    await device.async_set({"152": "AggG"})
    sets = [m for m in device._queue if m.command == Message.SET_COMMAND]
    assert [m.payload["dps"] for m in sets] == [{"152": "AggG"}]
    assert any(m.command == Message.GET_COMMAND for m in device._queue)


async def test_partial_overlap_set_kept(device):
    await device.async_set({"152": "AggN", "158": "Quiet"})
    await device.async_set({"152": "AggG"})
    assert len([m for m in device._queue if m.command == Message.SET_COMMAND]) == 2


async def test_queue_capped_get_survives(device):
    device._enqueue(Message(Message.GET_COMMAND, {}, device=device))
    for code in range(200, 240):
        await device.async_set({str(code): True})
    assert len(device._queue) == tla.MAX_QUEUE_LENGTH
    assert any(m.command == Message.GET_COMMAND for m in device._queue)


# --- Backoff (Phase 05) ---------------------------------------------------


def test_backoff_jitter_and_cap():
    first = [tla.backoff_interval(4) for _ in range(200)]
    assert all(4 <= x <= 6 for x in first)
    capped = [tla.backoff_interval(40) for _ in range(200)]
    assert all(480 <= x <= 720 for x in capped)
    assert len({round(x, 3) for x in capped}) > 50


async def test_push_clears_backoff_and_wakes_queue(device):
    device._backoff, device._failures, device._queue_interval = True, 9, 300
    sent = []

    async def send(message):
        sent.append(message)

    device._async_send = send
    await asyncio.sleep(0.15)  # let process_queue enter its 300 s sleep
    device._enqueue(Message(Message.PING_COMMAND, sequence=0, expect_response=False))
    push = Message(Message.GRATUITOUS_UPDATE, {"dps": {"153": "AA=="}}, 1)
    await device.async_gratuitous_update_state(push)
    assert device._backoff is False and device._failures == 0
    await asyncio.sleep(0.3)
    assert len(sent) == 1


# --- DPS query on connect (Phase 06) --------------------------------------


async def test_update_dps_query_on_connect(monkeypatch):
    written = []

    class Writer:
        def write(self, data):
            written.append(data)

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    class Reader:
        async def readuntil(self, *_):
            await asyncio.Event().wait()

        def at_eof(self):
            return False

        def feed_eof(self):
            pass

    async def open_connection(*_args, **_kwargs):
        return Reader(), Writer()

    monkeypatch.setattr(tla.asyncio, "open_connection", open_connection)
    dev = tla.TuyaDevice(T2267, "dobby-id", "192.0.2.10", 1, 9999, _noop, local_key=TEST_KEY)

    def queries():
        found = []
        for data in written:
            message = Message.from_bytes(dev, data, dev.cipher)
            if message.command == Message.UPDATE_DPS_COMMAND:
                found.append(message.payload)
        return found

    await dev.async_connect()
    assert queries() == [{"dpId": [152, 153]}]
    for _ in range(4):
        await dev.async_disconnect()
        await dev.async_connect()
    assert len(queries()) == tla.MAX_DPS_QUERIES
    dev._dps_queries = 0
    dev._dps.update({"152": "x"})
    written.clear()
    await dev.async_disconnect()
    await dev.async_connect()
    assert queries() == [{"dpId": [153]}]
    await dev.async_disable()
