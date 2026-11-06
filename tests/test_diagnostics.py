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

"""Phase 13: diagnostics, get_dps service and capture mode."""

from __future__ import annotations

import json
import logging

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.robovac import LIVE_KEYS, tuyalocalapi, vacuum
from custom_components.robovac.const import CONF_CAPTURE, CONF_VACS, DOMAIN
from custom_components.robovac.coordinator import RoboVacCoordinator
from custom_components.robovac.diagnostics import async_get_config_entry_diagnostics

from .conftest import CHARGING, CLEANING, TEST_KEY, make_item

SECRETS = ["user@example.com", "client-123", "00:00:5e:00:53:01", "hunter2", TEST_KEY]


def make_entry(hass, coordinators):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        data={
            "username": "user@example.com",
            "password": "hunter2",
            "client_id": "client-123",
            CONF_VACS: {"dobby-id": make_item()},
        },
    )
    entry.add_to_hass(hass)
    entry.runtime_data = coordinators
    return entry


async def test_diagnostics_redacts_and_includes_dps(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    coordinator.vacuum._dps.update({"153": CLEANING, "157": "dnd-raw", "159": True})
    entry = make_entry(hass, {"dobby-id": coordinator})
    dump = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(dump)
    for secret in SECRETS:
        assert secret not in text, secret
    info = dump["vacuums"]["dobby-id"]
    assert info["raw_dps"]["157"] == "dnd-raw" and info["raw_dps"]["159"] is True
    assert info["model_class"] == "T2267" and "BOOST_IQ" in info["features"]
    assert info["command_codes"]["mode"] == "152"
    assert info["protocol_version"] == "3.3"
    await coordinator.async_shutdown()


async def test_diagnostics_for_unsupported_model(hass):
    coordinator = RoboVacCoordinator(hass, make_item(model="T9999"))
    entry = make_entry(hass, {"dobby-id": coordinator})
    info = (await async_get_config_entry_diagnostics(hass, entry))["vacuums"]["dobby-id"]
    assert info["fault"] == "UNSUPPORTED_MODEL" and info["model_code"] == "T9999"
    assert "raw_dps" not in info
    await coordinator.async_shutdown()


async def test_get_dps_returns_and_filters(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entity = vacuum.RoboVacEntity(coordinator)
    coordinator.vacuum._dps.update({"157": "x", "159": False, "163": 80})

    async def fake_refresh():
        return None

    coordinator.async_forced_refresh = fake_refresh
    assert (await entity.async_get_dps())["dps"] == {"157": "x", "159": False, "163": 80}
    assert (await entity.async_get_dps(["159", "999"]))["dps"] == {"159": False}
    await coordinator.async_shutdown()


async def test_get_dps_errors_are_ha_errors(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entity = vacuum.RoboVacEntity(coordinator)

    async def boom():
        raise tuyalocalapi.TuyaException("timeout")

    coordinator.async_forced_refresh = boom
    with pytest.raises(HomeAssistantError):
        await entity.async_get_dps()
    coordinator.vacuum = None
    with pytest.raises(HomeAssistantError):
        await entity.async_get_dps()
    await coordinator.async_shutdown()


async def test_capture_logs_changes_and_stops(hass, caplog):
    coordinator = RoboVacCoordinator(hass, make_item())
    coordinator.vacuum._dps["153"] = CLEANING
    coordinator.async_set_capture(True)
    assert tuyalocalapi.VERBOSE is True
    with caplog.at_level(logging.INFO, logger="custom_components.robovac"):
        coordinator.vacuum._dps["153"] = CHARGING
        coordinator.vacuum._dps["157"] = "dnd"
        coordinator.update_from_device()
        coordinator.update_from_device()  # unchanged: no further lines
    lines = [r.message for r in caplog.records if r.message.startswith("capture ")]
    assert len(lines) == 2
    assert lines[0].startswith(f"capture dobby-id DPS 153: {CLEANING} → {CHARGING}")
    assert lines[1] == "capture dobby-id DPS 157: None → dnd"  # not decodable
    coordinator.async_set_capture(False)
    assert tuyalocalapi.VERBOSE is False
    caplog.clear()
    coordinator.vacuum._dps["153"] = CLEANING
    coordinator.update_from_device()
    assert not [r for r in caplog.records if r.message.startswith("capture ")]
    await coordinator.async_shutdown()


async def test_verbose_stays_on_while_any_vacuum_captures(hass):
    one = RoboVacCoordinator(hass, make_item())
    other_item = {**make_item(), "id": "other-id"}
    two = RoboVacCoordinator(hass, other_item)
    one.async_set_capture(True)
    two.async_set_capture(True)
    one.async_set_capture(False)
    assert tuyalocalapi.VERBOSE is True
    await two.async_shutdown()  # shutdown clears capture
    assert tuyalocalapi.VERBOSE is False
    await one.async_shutdown()


async def test_capture_toggle_applies_without_reload(hass):
    from custom_components.robovac import update_listener

    coordinator = RoboVacCoordinator(hass, make_item())
    entry = make_entry(hass, {"dobby-id": coordinator})
    assert CONF_CAPTURE in LIVE_KEYS
    vacs = {"dobby-id": {**entry.data[CONF_VACS]["dobby-id"], CONF_CAPTURE: True}}
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_VACS: vacs})
    reloads = []

    async def fake_reload(entry_id):
        reloads.append(entry_id)

    hass.config_entries.async_reload = fake_reload
    await update_listener(hass, entry)
    assert coordinator.capture is True and not reloads
    await coordinator.async_shutdown()
