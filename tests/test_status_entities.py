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


"""Phase 12: status, docked, charging, connected and last-seen entities."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import robovac
from custom_components.robovac import binary_sensor, sensor
from custom_components.robovac.const import CONF_VACS, DOMAIN
from custom_components.robovac.coordinator import RoboVacCoordinator

from .conftest import CHARGING, CLEANING, PAUSED, RECHARGE, STANDBY, make_item


async def collect(module, coordinator) -> dict:
    added: list = []
    entry = SimpleNamespace(runtime_data={coordinator.vacuum_id: coordinator})
    await module.async_setup_entry(None, entry, added.extend)
    return {e.unique_id.removeprefix("dobby-id_"): e for e in added}


def push(coordinator: RoboVacCoordinator, status: str) -> None:
    coordinator.vacuum._dps["153"] = status
    coordinator.update_from_device()


async def test_status_sensor_options_and_value(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    status = (await collect(sensor, coordinator))["status"]
    assert "Recharge" in status.options and "Cleaning paused" in status.options
    assert status.native_value is None
    push(coordinator, PAUSED)
    assert status.native_value == "Cleaning paused"
    push(coordinator, RECHARGE)
    assert status.native_value == "Recharge"
    await coordinator.async_shutdown()


async def test_status_options_follow_model_status_values(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    coordinator.status_values = {"AA==": "STANDBY"}
    status = (await collect(sensor, coordinator))["status"]
    assert status.options == ["Standby"]
    await coordinator.async_shutdown()


async def test_docked_and_charging_through_a_cycle(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entities = await collect(binary_sensor, coordinator)
    docked, charging = entities["docked"], entities["charging"]
    assert docked.is_on is None and charging.is_on is None  # unknown, not off

    expected = [
        (CLEANING, False, False),
        (PAUSED, False, False),
        (RECHARGE, False, False),  # heading home is not docked
        (STANDBY, False, False),
        (CHARGING, True, True),
    ]
    for raw, is_docked, is_charging in expected:
        push(coordinator, raw)
        assert (docked.is_on, charging.is_on) == (is_docked, is_charging), raw
    push(coordinator, "BhADGgIIAQ==")  # Completed: on the dock, no longer charging
    assert (docked.is_on, charging.is_on) == (True, False)
    await coordinator.async_shutdown()


async def test_connected_follows_the_socket_and_notifies(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    connected = (await collect(binary_sensor, coordinator))["connected"]
    assert connected.is_on is False and connected.available is True

    calls = []
    coordinator.async_add_listener(lambda: calls.append(1))
    coordinator.vacuum._connected = True
    assert connected.is_on is True
    await coordinator.vacuum.async_disconnect()  # e.g. the ping went unanswered
    assert connected.is_on is False
    assert calls  # listeners told, so the entity rewrites its state
    await coordinator.async_shutdown()


async def test_connect_callback_fires_on_connect(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    calls = []
    coordinator.vacuum.connection_cb = lambda: calls.append(coordinator.connected)
    reader = MagicMock()
    reader.at_eof.return_value = True
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    with (
        patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))),
        patch.object(coordinator.vacuum, "_async_handle_message", AsyncMock()),
        patch.object(coordinator.vacuum, "_async_query_dps", AsyncMock()),
        patch.object(coordinator.vacuum, "async_ping", AsyncMock()),
    ):
        await coordinator.vacuum.async_connect()
    assert calls == [True]
    await coordinator.async_shutdown()


async def test_failing_connection_callback_is_contained(hass):
    coordinator = RoboVacCoordinator(hass, make_item())

    def boom() -> None:
        raise RuntimeError("listener bug")

    coordinator.vacuum.connection_cb = boom
    coordinator.vacuum._connected = True
    await coordinator.vacuum.async_disconnect()  # must not raise
    assert coordinator.connected is False
    await coordinator.async_shutdown()


async def test_last_seen_updates_on_data_only(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    last_seen = (await collect(sensor, coordinator))["last_seen"]
    assert last_seen.native_value is None and last_seen.available is True
    push(coordinator, CLEANING)
    first = last_seen.native_value
    assert isinstance(first, datetime) and first.tzinfo is not None
    await asyncio.sleep(0.01)
    push(coordinator, PAUSED)
    assert last_seen.native_value > first
    await coordinator.async_shutdown()


async def test_no_status_entities_for_unsupported_model(hass):
    coordinator = RoboVacCoordinator(hass, make_item("T9999"))
    assert await collect(binary_sensor, coordinator) == {}
    assert set(await collect(sensor, coordinator)) == {"battery"}
    await coordinator.async_shutdown()


async def test_full_setup_registers_status_entities(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": make_item()}}
    )
    entry.add_to_hass(hass)
    with patch.object(robovac.TuyaLocalDiscovery, "start", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    for domain, key, entity_id in (
        ("sensor", "dobby-id_status", "sensor.dobby_status"),
        ("sensor", "dobby-id_last_seen", "sensor.dobby_last_seen"),
        ("sensor", "dobby-id_battery", "sensor.dobby_battery"),
        ("binary_sensor", "dobby-id_docked", "binary_sensor.dobby_docked"),
        ("binary_sensor", "dobby-id_charging", "binary_sensor.dobby_charging"),
        ("binary_sensor", "dobby-id_connected", "binary_sensor.dobby_connected"),
    ):
        assert registry.async_get_entity_id(domain, DOMAIN, key) == entity_id
    assert await hass.config_entries.async_unload(entry.entry_id)
