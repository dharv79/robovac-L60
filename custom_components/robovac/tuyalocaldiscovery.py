import asyncio
import ipaddress
import json
import logging
from hashlib import md5

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

# Public, protocol-wide key for Tuya 3.3 discovery broadcasts (not a user
# secret): anyone can forge a broadcast, so its contents are only a hint.
UDP_KEY = md5(b"yGAdlopoPVldABfn").digest()  # noqa: S324 - protocol-defined discovery key
UDP_CIPHER = Cipher(algorithms.AES(UDP_KEY), modes.ECB())  # noqa: S305 - protocol-defined discovery cipher


class DiscoveryPortsNotAvailableException(Exception):
    """This model is not supported"""


class TuyaLocalDiscovery(asyncio.DatagramProtocol):
    def __init__(self, callback):
        self.devices = {}
        self._listeners = []
        self._tasks: set[asyncio.Task] = set()
        self.discovered_callback = callback

    async def start(self):
        loop = asyncio.get_running_loop()
        listener = loop.create_datagram_endpoint(
            lambda: self, local_addr=("0.0.0.0", 6666), reuse_port=True  # noqa: S104 - broadcasts arrive on every interface
        )
        encrypted_listener = loop.create_datagram_endpoint(
            lambda: self, local_addr=("0.0.0.0", 6667), reuse_port=True  # noqa: S104 - broadcasts arrive on every interface
        )

        try:
            self._listeners = await asyncio.gather(listener, encrypted_listener)
            _LOGGER.debug("Listening to broadcasts on UDP port 6666 and 6667")
        except Exception as e:
            raise DiscoveryPortsNotAvailableException(
                "Ports 6666 and 6667 are needed for autodiscovery but are unavailable. This may be due to having the localtuya integration installed and it not allowing other integrations to use the same ports. A pull request has been raised to address this: https://github.com/rospogrigio/localtuya/pull/1481"
            ) from e

    def close(self, *args, **kwargs):
        for transport, _ in self._listeners:
            transport.close()
        for task in self._tasks:
            task.cancel()

    def datagram_received(self, data, addr):
        data = data[20:-8]
        try:
            decryptor = UDP_CIPHER.decryptor()
            padded_data = decryptor.update(data) + decryptor.finalize()
            data = padded_data[: -padded_data[-1]]
        except (ValueError, IndexError):
            pass  # noqa: S110 - port 6666 broadcasts are plaintext

        try:
            decoded = json.loads(data)
        except ValueError:
            _LOGGER.debug("Ignoring undecodable broadcast from %s", addr)
            return
        if not is_valid_broadcast(decoded):
            _LOGGER.debug("Ignoring malformed broadcast from %s", addr)
            return
        task = asyncio.ensure_future(self.discovered_callback(decoded))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def is_valid_broadcast(decoded) -> bool:
    """A usable broadcast has a string gwId and a unicast IPv4 address."""
    if not isinstance(decoded, dict) or not isinstance(decoded.get("gwId"), str):
        return False
    if not isinstance(decoded.get("ip"), str):
        return False
    try:
        ip = ipaddress.IPv4Address(decoded["ip"])
    except ValueError:
        return False
    return not (
        ip.is_multicast or ip.is_unspecified or ip.is_loopback or ip.is_reserved
    )
