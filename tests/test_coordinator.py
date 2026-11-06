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

"""Phase 10: per-vacuum coordinator, runtime_data, watchdog and IP handling."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_IP_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import robovac
from custom_components.robovac.const import CONF_VACS, DOMAIN, REFRESH_RATE
from custom_components.robovac.coordinator import RoboVacCoordinator
from custom_components.robovac.sensor import RobovacBatterySensor

from .conftest import STANDBY, make_item


async def test_unique_ids_and_names_unchanged(entity):
    # Upgrade safety: unique_ids stay as they were; the main entity takes the device name.
    assert entity.unique_id == "dobby-id"
    assert entity.has_entity_name is True
    assert entity.name is None
    assert entity.device_info["name"] == "Dobby"
    sensor = RobovacBatterySensor(entity.coordinator)
    assert sensor.unique_id == "dobby-id_battery"


async def test_push_updates_listeners_without_polling(entity):
    coordinator = entity.coordinator
    seen = []
    coordinator.async_add_listener(lambda: seen.append(coordinator.data))
    gets = []

    async def get():
        gets.append(1)

    coordinator.vacuum.async_get = get
    coordinator.vacuum._dps.update({"153": STANDBY, "163": 64})
    await coordinator.pushed_update_handler()
    assert seen[-1].battery == 64
    assert seen[-1].status == "Standby"
    assert entity.available is True
    assert gets == []  # a push never triggers a GET


async def test_battery_sensor_reads_coordinator_and_keeps_last_value(entity):
    sensor = RobovacBatterySensor(entity.coordinator)
    sensor.async_write_ha_state = lambda: None
    assert sensor.native_value is None
    entity.coordinator.vacuum._dps["163"] = 80
    entity.coordinator.update_from_device()
    sensor._handle_coordinator_update()
    assert sensor.native_value == 80
    entity.coordinator.vacuum._dps.pop("163")
    entity.coordinator.update_from_device()
    sensor._handle_coordinator_update()
    assert sensor.native_value == 80
    assert sensor.available is True


async def test_watchdog_only_polls_a_quiet_vacuum(entity):
    coordinator = entity.coordinator
    with patch.object(coordinator, "async_refresh", AsyncMock()) as refresh:
        coordinator._last_data = time.monotonic()
        await coordinator._async_watchdog(None)
        refresh.assert_not_awaited()
        coordinator._last_data = time.monotonic() - REFRESH_RATE - 1
        await coordinator._async_watchdog(None)
        refresh.assert_awaited_once()


async def test_set_host_reconnects_only_that_vacuum(hass):
    first = RoboVacCoordinator(hass, make_item())
    other_item = {**make_item(), "id": "other-id"}
    second = RoboVacCoordinator(hass, other_item)
    old_device, other_device = first.vacuum, second.vacuum
    await first.async_set_host("192.0.2.77")
    assert first.ip_address == "192.0.2.77"
    assert first.item[CONF_IP_ADDRESS] == "192.0.2.77"
    assert first.vacuum is not old_device and first.vacuum.host == "192.0.2.77"
    assert old_device._enabled is False
    assert second.vacuum is other_device and other_device._enabled is True
    for coordinator in (first, second):
        await coordinator.async_shutdown()


def _entry(hass, coordinator, **overrides):
    item = {**coordinator.item, **overrides}
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": item}})
    entry.add_to_hass(hass)
    entry.runtime_data = {"dobby-id": coordinator}
    return entry


async def test_discovered_ip_reconnects_without_reload(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entry = _entry(hass, coordinator)
    with (
        patch.object(robovac, "async_probe_device", AsyncMock(return_value=True)),
        patch.object(coordinator, "async_set_host", AsyncMock()) as set_host,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        await robovac.async_update_device_ip(hass, {"gwId": "dobby-id", "ip": "192.0.2.20"})
    set_host.assert_awaited_once_with("192.0.2.20")
    reload.assert_not_awaited()
    assert entry.data[CONF_VACS]["dobby-id"][CONF_IP_ADDRESS] == "192.0.2.20"
    await coordinator.async_shutdown()


async def test_update_listener_ignores_ip_only_changes(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entry = _entry(hass, coordinator, **{CONF_IP_ADDRESS: "192.0.2.50"})
    with (
        patch.object(coordinator, "async_set_host", AsyncMock()) as set_host,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        await robovac.update_listener(hass, entry)
    reload.assert_not_awaited()
    set_host.assert_awaited_once_with("192.0.2.50")
    await coordinator.async_shutdown()


async def test_update_listener_reloads_on_other_changes(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entry = _entry(hass, coordinator, autodiscovery=False)
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await robovac.update_listener(hass, entry)
    reload.assert_awaited_once_with(entry.entry_id)
    await coordinator.async_shutdown()


async def test_unload_shuts_down_every_coordinator(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    device = coordinator.vacuum
    entry = _entry(hass, coordinator)
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    ):
        assert await robovac.async_unload_entry(hass, entry)
    assert device._enabled is False


async def test_full_setup_keeps_entity_ids_and_unloads(hass):
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": make_item()}}
    )
    entry.add_to_hass(hass)
    with patch.object(robovac.TuyaLocalDiscovery, "start", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("vacuum", DOMAIN, "dobby-id") == "vacuum.dobby"
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, "dobby-id_battery")
        == "sensor.dobby_battery"
    )
    coordinator = entry.runtime_data["dobby-id"]
    assert isinstance(coordinator, RoboVacCoordinator)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator.vacuum._enabled is False
