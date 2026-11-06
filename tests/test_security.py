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

"""Phase 08 security sweep: secrets kept out of logs, discovery hardening."""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import robovac
from custom_components.robovac import config_flow, tuyawebapi
from custom_components.robovac import tuyalocalapi as tla
from custom_components.robovac.const import CONF_VACS, DOMAIN
from custom_components.robovac.tuyalocaldiscovery import (
    TuyaLocalDiscovery,
    is_valid_broadcast,
)

from .conftest import TEST_KEY, make_item
from .test_tuyalocalapi import device_frame

OTHER_KEY = "fedcba9876543210"  # fake key for "another device" in cloud data  # gitleaks:allow


async def _noop():
    return None


def _frame(body: bytes, sequence=7, command=tla.Message.GET_COMMAND) -> bytes:
    header = struct.pack(
        tla.MESSAGE_PREFIX_FORMAT, tla.MAGIC_PREFIX, sequence, command,
        len(body) + tla.SUFFIX_SIZE,
    )
    footer = struct.pack(tla.MESSAGE_SUFFIX_FORMAT, tla.crc(header + body), tla.MAGIC_SUFFIX)
    return header + body + footer


# --- B. Secrets in logs -----------------------------------------------------


async def test_device_repr_and_str_omit_local_key():
    dev = tla.TuyaDevice(
        SimpleNamespace(), "dobby-id", "192.0.2.10", 1, 9999, _noop, local_key=TEST_KEY
    )
    try:
        assert TEST_KEY not in repr(dev)
        assert TEST_KEY not in str(dev)
        assert "dobby-id" in repr(dev)
    finally:
        await dev.async_disable()


def test_config_flow_skip_path_logs_no_local_key(caplog):
    """A vacuum that fails to parse is skipped without dumping cloud data."""
    login = MagicMock(status_code=200)
    login.json.return_value = {
        "res_code": 1,
        "access_token": "fake-token",
        "user_info": {"request_host": "https://example.invalid", "id": "u1",
                      "phone_code": "44", "timezone": "Europe/London"},
    }
    devices = MagicMock()
    # No alias_name, so parsing raises after the Tuya lookup.
    devices.json.return_value = {"devices": [{
        "id": "dobby-id", "product": {"appliance": "Cleaning", "product_code": "T2267"},
        "local_key": OTHER_KEY,
    }]}
    settings = MagicMock()
    settings.json.return_value = {}
    eufy = MagicMock()
    eufy.get_user_info.return_value = login
    eufy.get_device_info.return_value = devices
    eufy.get_user_settings.return_value = settings
    tuya = MagicMock()
    tuya.get_device.return_value = {"localKey": TEST_KEY, "schema": "[]"}

    caplog.set_level(logging.DEBUG, logger=config_flow.__name__)
    with (
        patch.object(config_flow, "EufyLogon", return_value=eufy),
        patch.object(config_flow, "TuyaAPISession", return_value=tuya),
    ):
        data = config_flow.get_eufy_vacuums(
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "not-a-real-password"}
        )

    assert data[CONF_VACS] == {}
    assert "dobby-id" in caplog.text
    assert TEST_KEY not in caplog.text
    assert OTHER_KEY not in caplog.text


def _tuya_session():
    session = tuyawebapi.TuyaAPISession("eh-u1", "EU", "Europe/London", "44")
    session.session_id = session.default_query_params["sid"] = "secret-session-id"
    return session


def test_tuya_http_error_omits_url_and_body():
    session = _tuya_session()
    session.session = MagicMock()
    session.session.post.return_value = MagicMock(ok=False, status_code=500)
    with pytest.raises(tuyawebapi.TuyaAPIError) as err:
        session.get_device("dobby-id")
    assert "secret-session-id" not in str(err.value)
    assert "HTTP 500" in str(err.value)
    assert session.session.post.call_args.kwargs["timeout"] == tuyawebapi.REQUEST_TIMEOUT


def test_tuya_missing_result_omits_body():
    session = _tuya_session()
    session.session = MagicMock()
    resp = MagicMock(ok=True)
    resp.json.return_value = {"errorCode": "PERMISSION_DENIED", "localKey": TEST_KEY}
    session.session.post.return_value = resp
    with pytest.raises(tuyawebapi.TuyaAPIError) as err:
        session.get_device("dobby-id")
    assert TEST_KEY not in str(err.value)
    assert "PERMISSION_DENIED" in str(err.value)


def test_eufy_refuses_plain_http_host():
    eufy = robovac.eufywebapi.EufyLogon("user@example.com", "not-a-real-password")
    with patch.object(robovac.eufywebapi.requests, "request") as request:
        with pytest.raises(ValueError):
            eufy.get_device_info("http://example.invalid", "u1", "fake-token")
    request.assert_not_called()


# --- D. Stored password -----------------------------------------------------


async def test_migration_strips_password(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=1,
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "not-a-real-password",
              CONF_VACS: {"dobby-id": make_item()}},
    )
    entry.add_to_hass(hass)
    assert await robovac.async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert CONF_PASSWORD not in entry.data
    assert entry.data[CONF_VACS] == {"dobby-id": make_item()}


async def test_migration_refuses_future_version(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={})
    entry.add_to_hass(hass)
    assert not await robovac.async_migrate_entry(hass, entry)


# --- C. Untrusted LAN input: discovery --------------------------------------


@pytest.mark.parametrize(
    ("packet", "valid"),
    [
        ({"gwId": "dobby-id", "ip": "192.0.2.20"}, True),
        ({"gwId": "dobby-id", "ip": "not-an-ip"}, False),
        ({"gwId": "dobby-id", "ip": 3221225492}, False),
        ({"gwId": "dobby-id", "ip": "127.0.0.1"}, False),
        ({"gwId": "dobby-id", "ip": "255.255.255.255"}, False),
        ({"gwId": "dobby-id", "ip": "224.0.0.1"}, False),
        ({"gwId": "dobby-id", "ip": "0.0.0.0"}, False),  # noqa: S104 - test data
        ({"gwId": "dobby-id"}, False),
        ({"gwId": 5, "ip": "192.0.2.20"}, False),
        (["dobby-id"], False),
    ],
)
def test_is_valid_broadcast(packet, valid):
    assert is_valid_broadcast(packet) is valid


async def test_datagram_drops_malformed_and_tracks_tasks():
    seen = []

    async def callback(device):
        seen.append(device)

    discovery = TuyaLocalDiscovery(callback)
    for packet in ({"gwId": "dobby-id", "ip": "bad"}, {"gwId": "dobby-id", "ip": "192.0.2.20"}):
        # Plaintext (port 6666) layout: 20-byte header, JSON, 8-byte footer.
        discovery.datagram_received(b"\0" * 20 + json.dumps(packet).encode() + b"\0" * 8, None)
    assert len(discovery._tasks) == 1
    await asyncio.sleep(0)
    await asyncio.sleep(0)  # done callbacks run one loop pass later
    assert seen == [{"gwId": "dobby-id", "ip": "192.0.2.20"}]
    assert not discovery._tasks


@pytest.fixture
def vac_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": make_item()}})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def reload(hass):
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock:
        yield mock


def _probe(result):
    return patch.object(robovac, "async_probe_device", AsyncMock(return_value=result))


async def test_ip_change_needs_authenticated_reply(hass, vac_entry, reload):
    with _probe(False) as probe:
        await robovac.async_update_device_ip(hass, {"gwId": "dobby-id", "ip": "192.0.2.66"})
    probe.assert_awaited_once_with("192.0.2.66", "dobby-id", TEST_KEY, timeout=robovac.PROBE_TIMEOUT)
    assert vac_entry.data[CONF_VACS]["dobby-id"][CONF_IP_ADDRESS] == "192.0.2.10"
    reload.assert_not_awaited()


async def test_ip_change_applied_after_probe(hass, vac_entry, reload):
    with _probe(True):
        await robovac.async_update_device_ip(hass, {"gwId": "dobby-id", "ip": "192.0.2.20"})
    assert vac_entry.data[CONF_VACS]["dobby-id"][CONF_IP_ADDRESS] == "192.0.2.20"
    reload.assert_not_awaited()  # Phase 10: only that vacuum reconnects


async def test_ip_changes_rate_limited(hass, vac_entry, reload):
    with _probe(False) as probe:
        for last_octet in range(30, 35):
            await robovac.async_update_device_ip(
                hass, {"gwId": "dobby-id", "ip": f"192.0.2.{last_octet}"}
            )
    assert probe.await_count == 1


async def test_unknown_or_unchanged_device_not_probed(hass, vac_entry, reload):
    with _probe(True) as probe:
        await robovac.async_update_device_ip(hass, {"gwId": "stranger", "ip": "192.0.2.20"})
        await robovac.async_update_device_ip(hass, {"gwId": "dobby-id", "ip": "192.0.2.10"})
    probe.assert_not_awaited()
    reload.assert_not_awaited()


# --- C. Authenticated probe and frame parsing -------------------------------


class FakeWriter:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, data):
        self.data += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def _connection(reply: bytes | None):
    """Patch open_connection: the "device" sends `reply` (None = refused)."""
    writer = FakeWriter()

    async def open_connection(host, port):
        if reply is None:
            raise ConnectionRefusedError
        reader = asyncio.StreamReader()
        reader.feed_data(reply)
        reader.feed_eof()
        return reader, writer

    return patch.object(tla.asyncio, "open_connection", open_connection), writer


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (device_frame(tla.TuyaCipher(TEST_KEY, (3, 3)), 0x0A, {"dps": {"153": "AA=="}}), True),
        (device_frame(tla.TuyaCipher(OTHER_KEY, (3, 3)), 0x0A, {"dps": {"153": "AA=="}}), False),
        # A spoofer without the key can only send plaintext.
        (_frame(struct.pack(">I", 0) + b'{"dps":{"153":"AA=="}}'), False),
        (b"", False),
        (None, False),
    ],
)
async def test_probe_device(reply, expected):
    patcher, writer = _connection(reply)
    with patcher:
        result = await tla.async_probe_device("192.0.2.20", "dobby-id", TEST_KEY, timeout=0.5)
    assert result is expected
    if reply is not None:
        assert writer.closed
        # The probe's GET is encrypted with the stored key.
        sent = tla.Message.from_bytes(None, writer.data, tla.TuyaCipher(TEST_KEY, (3, 3)),
                                      require_encrypted=True)
        assert sent.payload == {"gwId": "dobby-id", "devId": "dobby-id"}


async def test_probe_device_bad_key():
    assert not await tla.async_probe_device("192.0.2.20", "dobby-id", None)


@pytest.mark.parametrize("payload_size", [0, 4, 10_000])
def test_from_bytes_rejects_bad_length(payload_size):
    good = _frame(struct.pack(">I", 0) + b"{}")
    bad = good[:12] + struct.pack(">I", payload_size) + good[16:]
    with pytest.raises(tla.InvalidMessage):
        tla.Message.from_bytes(None, bad, tla.TuyaCipher(TEST_KEY, (3, 3)))


async def test_bad_frames_then_eof_end_reader_loop():
    dev = tla.TuyaDevice(
        SimpleNamespace(), "dobby-id", "192.0.2.10", 1, 9999, _noop, local_key=TEST_KEY
    )
    try:
        reader = asyncio.StreamReader()
        good = _frame(struct.pack(">I", 0) + b"{}")
        reader.feed_data(good[:12] + struct.pack(">I", 10_000) + good[16:])
        reader.feed_data(b"\x00\x00\xaa\x55")  # truncated: suffix only
        reader.feed_eof()
        dev.reader, dev._connected = reader, True
        await asyncio.wait_for(dev._async_handle_message(), 1)
        assert not dev._connected
    finally:
        await dev.async_disable()
