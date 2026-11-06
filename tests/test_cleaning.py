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

"""Phase 16: clean-session events, history sensors and logbook."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.components.sensor import SensorExtraStoredData
from homeassistant.components.vacuum import VacuumActivity as A
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    mock_restore_cache_with_extra_data,
)

from custom_components.robovac import sensor
from custom_components.robovac import logbook as robovac_logbook
from custom_components.robovac.cleaning import (
    ERROR,
    FINISH_DEBOUNCE,
    FINISHED,
    STARTED,
    CleanTracker,
)
from custom_components.robovac.const import (
    EVENT_CLEANING_ERROR,
    EVENT_CLEANING_FINISHED,
    EVENT_CLEANING_STARTED,
)
from custom_components.robovac.coordinator import RoboVacCoordinator

from .conftest import CHARGING, CLEANING, PAUSED, RECHARGE, make_item

T0 = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def run(steps):
    """Feed (seconds, activity) steps; return [(kind, duration)]."""
    tracker = CleanTracker()
    out = []
    for seconds, activity in steps:
        for event in tracker.update(activity, seconds, T0 + timedelta(seconds=seconds)):
            out.append((event.kind, event.duration))
    return out, tracker


def test_full_clean_with_pause_gives_one_pair():
    out, tracker = run(
        [(0, A.DOCKED), (5, A.CLEANING), (300, A.PAUSED), (400, A.CLEANING),
         (900, A.RETURNING), (960, A.DOCKED), (975, A.DOCKED)]
    )
    assert out == [(STARTED, None), (FINISHED, 960 - 5)]
    assert not tracker.in_clean


def test_flap_while_docking_does_not_finish_or_restart():
    out, tracker = run(
        [(0, A.CLEANING), (100, A.DOCKED), (103, A.CLEANING), (200, A.DOCKED),
         (203, A.RETURNING), (260, A.DOCKED), (275, A.DOCKED)]
    )
    assert [kind for kind, _ in out] == [STARTED, FINISHED]
    assert out[1][1] == 260


def test_finish_waits_for_the_debounce_and_exposes_deadline():
    tracker = CleanTracker()
    tracker.update(A.CLEANING, 0, T0)
    assert tracker.deadline is None
    assert tracker.update(A.DOCKED, 50, T0) == []
    assert tracker.deadline == 50 + FINISH_DEBOUNCE
    assert tracker.update(A.DOCKED, 50 + FINISH_DEBOUNCE - 1, T0) == []
    assert [e.kind for e in tracker.update(A.DOCKED, 50 + FINISH_DEBOUNCE, T0)] == [FINISHED]
    assert tracker.deadline is None


def test_two_cleans_two_pairs_and_idle_ends_a_clean():
    out, _ = run(
        [(0, A.CLEANING), (60, A.IDLE), (80, A.IDLE),
         (500, A.CLEANING), (560, A.DOCKED), (580, A.DOCKED)]
    )
    assert [kind for kind, _ in out] == [STARTED, FINISHED, STARTED, FINISHED]


def test_error_fires_once_per_entry_and_clean_continues():
    out, tracker = run(
        [(0, A.CLEANING), (10, A.ERROR), (20, A.ERROR), (30, A.CLEANING),
         (40, A.ERROR), (50, A.DOCKED), (70, A.DOCKED)]
    )
    assert [kind for kind, _ in out] == [STARTED, ERROR, ERROR, FINISHED]


def test_clean_in_progress_at_startup_is_not_started():
    out, _ = run([(0, A.PAUSED), (10, A.RETURNING), (80, A.DOCKED), (100, A.DOCKED)])
    assert out == []


async def test_coordinator_fires_events_once_per_clean(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    started = async_capture_events(hass, EVENT_CLEANING_STARTED)
    finished = async_capture_events(hass, EVENT_CLEANING_FINISHED)
    errors = async_capture_events(hass, EVENT_CLEANING_ERROR)
    clock = {"t": 1000.0}

    def push(raw):
        coordinator.vacuum._dps["153"] = raw
        coordinator.update_from_device()

    with patch("custom_components.robovac.coordinator.time.monotonic", lambda: clock["t"]):
        push(CLEANING)
        clock["t"] += 100
        push(PAUSED)
        clock["t"] += 50
        push(CLEANING)
        clock["t"] += 100
        push(RECHARGE)
        clock["t"] += 30
        push(CHARGING)
        clock["t"] += FINISH_DEBOUNCE + 1
        await coordinator._flush_clean(None)  # the debounce timer firing
    await hass.async_block_till_done()
    assert len(started) == 1 and len(finished) == 1 and not errors
    assert started[0].data["vacuum_id"] == "dobby-id"
    assert finished[0].data["duration"] >= 0
    await coordinator.async_shutdown()


async def collect(coordinator):
    added: list = []
    entry = SimpleNamespace(runtime_data={coordinator.vacuum_id: coordinator})
    await sensor.async_setup_entry(None, entry, added.extend)
    return {e.unique_id.removeprefix("dobby-id_"): e for e in added}


async def add(hass, entity):
    entity.hass = hass
    entity.platform = SimpleNamespace(
        platform_name="robovac", domain="sensor", platform=None
    )
    entity.entity_id = f"sensor.dobby_{entity.unique_id.removeprefix('dobby-id_')}"
    await entity.async_added_to_hass()


async def test_history_sensors_follow_finished_events(hass):
    coordinator = RoboVacCoordinator(hass, make_item())
    entities = await collect(coordinator)
    count, last, duration = (
        entities["cleaning_count"], entities["last_cleaned"], entities["last_clean_duration"]
    )
    for entity in (count, last, duration):
        await add(hass, entity)
        entity.async_write_ha_state = lambda: None
    assert count.native_value == 0 and last.native_value is None

    hass.bus.async_fire(EVENT_CLEANING_FINISHED, {"vacuum_id": "other", "duration": 5})
    hass.bus.async_fire(EVENT_CLEANING_FINISHED, {"vacuum_id": "dobby-id", "duration": 1800})
    await hass.async_block_till_done()
    assert count.native_value == 1 and duration.native_value == 1800
    assert last.native_value is not None
    hass.bus.async_fire(EVENT_CLEANING_FINISHED, {"vacuum_id": "dobby-id", "duration": 60})
    await hass.async_block_till_done()
    assert count.native_value == 2 and duration.native_value == 60
    await coordinator.async_shutdown()


async def test_history_sensors_restore(hass):
    when = datetime(2026, 11, 5, 9, 30, tzinfo=timezone.utc)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (State("sensor.dobby_cleaning_count", "7"), SensorExtraStoredData(7, None).as_dict()),
            (State("sensor.dobby_last_cleaned", when.isoformat()), SensorExtraStoredData(when, None).as_dict()),
        ],
    )
    coordinator = RoboVacCoordinator(hass, make_item())
    entities = await collect(coordinator)
    for key in ("cleaning_count", "last_cleaned"):
        await add(hass, entities[key])
    assert entities["cleaning_count"].native_value == 7
    assert entities["last_cleaned"].native_value == when
    await coordinator.async_shutdown()


def test_logbook_describes_the_three_events(hass):
    described = {}

    def register(domain, name, func):
        described[name] = func

    robovac_logbook.async_describe_events(hass, register)
    assert set(described) == {
        EVENT_CLEANING_STARTED, EVENT_CLEANING_FINISHED, EVENT_CLEANING_ERROR
    }
    event = SimpleNamespace(data={"entity_id": "vacuum.dobby", "duration": 1800, "error": "Robot stuck"})
    assert "30 min" in described[EVENT_CLEANING_FINISHED](event)["message"]
    assert described[EVENT_CLEANING_STARTED](event)["entity_id"] == "vacuum.dobby"
    assert "Robot stuck" in described[EVENT_CLEANING_ERROR](event)["message"]
