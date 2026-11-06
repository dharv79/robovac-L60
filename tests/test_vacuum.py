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

"""RoboVacEntity: state decoding, commands, start sequence, availability."""

from __future__ import annotations

import asyncio
import base64
import json
import logging

import pytest
from homeassistant.components.vacuum import VacuumActivity
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import mock_restore_cache

from custom_components.robovac.coordinator import _decode_consumables
from custom_components.robovac.tuyalocalapi import TuyaException

from .conftest import (
    CHARGING,
    CLEANING,
    PAUSED,
    RECHARGE,
    STANDBY,
    attach,
    make_entity,
    make_item,
)

COORDINATOR_LOGGER = "custom_components.robovac.coordinator"


# --- State decoding -------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "activity"),
    [
        (CLEANING, VacuumActivity.CLEANING),
        (PAUSED, VacuumActivity.PAUSED),
        ("CgoCCAEQBTICCAE=", VacuumActivity.PAUSED),  # room pause
        (RECHARGE, VacuumActivity.RETURNING),
        (CHARGING, VacuumActivity.DOCKED),
        ("BhADGgIIAQ==", VacuumActivity.DOCKED),  # completed
        (STANDBY, VacuumActivity.IDLE),
        ("AhAB", VacuumActivity.IDLE),  # sleeping
    ],
)
async def test_activity_from_status_dps(entity, status, activity):
    entity.vacuum._dps.update({"153": status})
    entity.coordinator.update_from_device()
    assert entity.activity == activity


async def test_unknown_status_is_idle(entity):
    assert entity.tuya_state is None
    assert entity.activity == VacuumActivity.IDLE


async def test_battery_in_coordinator_not_on_entity(entity):
    # Do-not-break #4: battery lives in the coordinator data, never on the entity.
    entity.vacuum._dps.update({"163": 87})
    entity.coordinator.update_from_device()
    assert entity.coordinator.data.battery == 87
    assert getattr(entity, "_attr_battery_level", None) is None


async def test_consumables_json_and_bad_payloads(entity):
    payload = json.dumps({"consumable": {"duration": {"SP": 3}}}).encode()
    assert _decode_consumables(base64.b64encode(payload), None, "id") == {"SP": 3}
    assert _decode_consumables(base64.b64encode(b"{'consumable': {}}"), None, "id") is None
    assert _decode_consumables("!!not base64", None, "id") is None
    assert _decode_consumables(None, {"SP": 3}, "id") == {"SP": 3}  # keeps the last value


# --- Commands -------------------------------------------------------------


async def test_boost_iq_toggles_dps_159(entity):
    fake = attach(entity, STANDBY)
    await entity.async_send_command("boostIQ")
    assert fake.sent[-1] == {"159": True}
    entity.vacuum._dps["159"] = True
    entity.coordinator.update_from_device()
    await entity.async_send_command("boostIQ")
    assert fake.sent[-1] == {"159": False}


async def test_dnd_toggle_ignored_for_protobuf_value(entity):
    fake = attach(entity, STANDBY)
    entity.vacuum._dps["157"] = "DgoAEgoKABICCBYaAggI"
    entity.coordinator.update_from_device()
    await entity.async_send_command("doNotDisturb")
    assert not any("157" in sent for sent in fake.sent)


async def test_unsupported_model_is_inert(hass):
    ent = make_entity(hass, make_item(model="T9999"))
    assert ent.vacuum is None
    assert ent.error_code == "UNSUPPORTED_MODEL"
    assert ent.available is False
    await ent.async_send_command("boostIQ")
    await ent.async_locate()
    await ent.async_return_to_base()


async def test_one_refresh_per_burst(entity):
    attach(entity, STANDBY)
    for _ in range(4):
        await entity.async_set_fan_speed(entity.fan_speed_list[0])
    await asyncio.sleep(0.05)
    assert len(entity.refreshes) == 1


# --- Start sequence (v1.0.11 escalation, Phase 04 cancellation) ------------


@pytest.mark.parametrize(
    ("status", "known", "expected"),
    [
        (PAUSED, True, ["AggO"]),
        (PAUSED, False, ["BBoCCAE=", "AggO"]),
        (RECHARGE, True, ["AggP", "BBoCCAE="]),
        (RECHARGE, False, ["BBoCCAE=", "AggO", "AggP", "BBoCCAE="]),
        (STANDBY, True, ["BBoCCAE="]),
        (STANDBY, False, ["BBoCCAE="]),
    ],
)
async def test_start_sequence(entity, status, known, expected):
    fake = attach(entity, status, known=known)
    await entity.async_start()
    await entity._start_task
    assert fake.modes == expected
    assert entity.activity == VacuumActivity.CLEANING


async def test_dock_during_start_cancels_it(entity):
    fake = attach(entity, PAUSED, known=False)
    await entity.async_start()
    task = entity._start_task
    await asyncio.sleep(0.1)
    await entity.async_return_to_base()
    await asyncio.sleep(1.5)
    assert task.cancelled()
    assert entity._start_task is None
    assert fake.modes[-1] == "AggG"
    assert fake.modes == ["BBoCCAE=", "AggG"]


async def test_second_start_is_noop(entity):
    fake = attach(entity, STANDBY)
    await entity.async_start()
    task = entity._start_task
    await entity.async_start()
    assert entity._start_task is task
    await task
    assert fake.modes == ["BBoCCAE="]


async def test_raw_mode_write_cancels_start(entity):
    attach(entity, PAUSED, known=False)
    await entity.async_start()
    task = entity._start_task
    await asyncio.sleep(0.05)
    await entity.async_send_command("152", {"value": "AggN"})
    await asyncio.sleep(0)
    assert task.cancelled()


async def test_fan_speed_does_not_cancel_start(entity):
    fake = attach(entity, PAUSED, known=False)
    await entity.async_start()
    task = entity._start_task
    await entity.async_set_fan_speed(entity.fan_speed_list[0])
    await task
    assert not task.cancelled()
    assert fake.modes == ["BBoCCAE=", "AggO"]


# --- Availability (Phase 05) ---------------------------------------------


def _vacuum_records(caplog, level):
    return [
        r for r in caplog.records if r.name == COORDINATOR_LOGGER and r.levelno == level
    ]


async def test_unavailable_and_recovery_logged_once(entity, caplog):
    caplog.set_level(logging.DEBUG)
    coordinator = entity.coordinator

    async def fail():
        raise TuyaException("timeout")

    coordinator.vacuum.async_get = fail
    for _ in range(8):
        await coordinator.async_refresh()
    assert entity.available is False
    assert len(_vacuum_records(caplog, logging.WARNING)) == 1

    async def ok():
        coordinator.vacuum._dps["153"] = STANDBY

    coordinator.vacuum.async_get = ok
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert entity.available is True
    assert len(_vacuum_records(caplog, logging.INFO)) == 1


async def test_warm_up_runs_in_background(entity):
    coordinator = entity.coordinator
    calls = []

    async def fail():
        calls.append(1)
        raise TuyaException("asleep")

    coordinator.async_forced_refresh = fail
    coordinator.async_start()
    assert coordinator._warmup_task is not None and not coordinator._warmup_task.done()
    assert entity.available is False
    coordinator._warmup_task.cancel()


# --- Restored state (Phase 06) -------------------------------------------


async def test_restored_state_is_display_only(hass, entity):
    mock_restore_cache(hass, [State("vacuum.dobby", "cleaning")])
    entity.hass = hass
    entity.entity_id = "vacuum.dobby"
    attach(entity, PAUSED, known=False)
    await entity.async_added_to_hass()
    assert entity.activity == VacuumActivity.CLEANING
    assert entity.extra_state_attributes["state_restored"] is True
    # Command logic ignores it: a start still escalates from unknown.
    assert entity._live_activity() == VacuumActivity.IDLE
    assert not entity.coordinator.cleaning.is_set()
    entity.vacuum._dps["153"] = STANDBY
    entity.coordinator.update_from_device()
    assert entity.activity == VacuumActivity.IDLE
    assert "state_restored" not in entity.extra_state_attributes


async def test_unavailable_last_state_not_restored(hass, entity):
    mock_restore_cache(hass, [State("vacuum.dobby", "unavailable")])
    entity.hass = hass
    entity.entity_id = "vacuum.dobby"
    await entity.async_added_to_hass()
