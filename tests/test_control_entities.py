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


"""Phase 11: switch, buttons, suction select and the robovac services."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import robovac
from custom_components.robovac import button, select, switch, vacuum
from custom_components.robovac.const import CONF_VACS, DOMAIN
from custom_components.robovac.coordinator import RoboVacCoordinator
from custom_components.robovac.vacuums.base import ModeKey

from . import conftest
from .conftest import CHARGING, PAUSED, STANDBY, attach, make_item


def make_coordinator(hass, model: str = "T2267") -> RoboVacCoordinator:
    coordinator = RoboVacCoordinator(hass, make_item(model))
    sent: list[dict] = []

    async def fake_set(dps: dict) -> None:
        sent.append(dps)

    if coordinator.vacuum is not None:
        coordinator.vacuum.async_set = fake_set
    coordinator.refreshes = []

    async def fake_refresh() -> None:
        coordinator.refreshes.append(1)
        await asyncio.sleep(0.02)

    coordinator.async_forced_refresh = fake_refresh
    coordinator.sent = sent
    return coordinator


def entry_for(*coordinators):
    return SimpleNamespace(runtime_data={c.vacuum_id: c for c in coordinators})


async def collect(module, *coordinators) -> list:
    added: list = []
    await module.async_setup_entry(None, entry_for(*coordinators), added.extend)
    return added


async def test_boost_switch_state_and_explicit_writes(hass):
    coordinator = make_coordinator(hass)
    (sw,) = await collect(switch, coordinator)
    assert sw.unique_id == "dobby-id_boost_iq"
    assert sw.is_on is None  # nothing reported yet: unknown, not off

    coordinator.vacuum._dps["159"] = False
    coordinator.update_from_device()
    assert sw.is_on is False
    coordinator.vacuum._dps["159"] = True
    coordinator.update_from_device()
    assert sw.is_on is True

    await sw.async_turn_off()
    await sw.async_turn_off()
    await sw.async_turn_on()
    assert coordinator.sent == [{"159": False}, {"159": False}, {"159": True}]
    await coordinator.async_shutdown()


async def test_no_entities_for_unsupported_model(hass):
    coordinator = make_coordinator(hass, "T9999")
    for module in (switch, button, select):
        assert await collect(module, coordinator) == []
    await coordinator.async_shutdown()


async def test_l60_gets_one_of_each(hass):
    coordinator = make_coordinator(hass)
    assert len(await collect(switch, coordinator)) == 1
    assert {b.unique_id for b in await collect(button, coordinator)} == {
        "dobby-id_stop_return",
        "dobby-id_locate",
    }
    assert len(await collect(select, coordinator)) == 1
    await coordinator.async_shutdown()


async def test_stop_return_button_needs_a_declared_mode(hass):
    coordinator = make_coordinator(hass)
    coordinator.declared_modes = frozenset()
    assert {b.unique_id for b in await collect(button, coordinator)} == {
        "dobby-id_locate"
    }
    await coordinator.async_shutdown()


async def test_stop_return_button_sends_model_value_and_cancels_start(hass):
    coordinator = make_coordinator(hass)
    ent = next(
        b for b in await collect(button, coordinator) if b.unique_id.endswith("stop_return")
    )
    pending = asyncio.create_task(asyncio.sleep(10))
    coordinator.cancel_start = pending.cancel
    await ent.async_press()
    await asyncio.sleep(0)
    assert coordinator.sent == [{"152": coordinator.mode_values[ModeKey.STOP_RETURN]}]
    assert pending.cancelled()
    await coordinator.async_shutdown()


async def test_locate_button_toggles(hass):
    coordinator = make_coordinator(hass)
    ent = next(
        b for b in await collect(button, coordinator) if b.unique_id.endswith("locate")
    )
    coordinator.vacuum._dps["160"] = False
    coordinator.update_from_device()
    await ent.async_press()
    coordinator.vacuum._dps["160"] = True
    coordinator.update_from_device()
    await ent.async_press()
    assert coordinator.sent == [{"160": True}, {"160": False}]
    await coordinator.async_shutdown()


async def test_suction_select_matches_fan_speeds(hass):
    coordinator = make_coordinator(hass)
    (sel,) = await collect(select, coordinator)
    assert sel.options == list(coordinator.fan_speed_map)
    assert sel.current_option is None

    coordinator.vacuum._dps["158"] = "Turbo"
    coordinator.update_from_device()
    assert sel.current_option == "Turbo"

    await sel.async_select_option("Max")
    await sel.async_select_option("Bogus")  # ignored
    assert coordinator.sent == [{"158": coordinator.fan_speed_map["Max"]}]
    await coordinator.async_shutdown()


async def test_one_refresh_per_burst(hass):
    coordinator = make_coordinator(hass)
    (sw,) = await collect(switch, coordinator)
    await sw.async_turn_on()
    await sw.async_turn_off()
    await asyncio.sleep(0.05)
    assert len(coordinator.refreshes) == 1
    await coordinator.async_shutdown()


async def test_start_new_clean_from_paused(entity, monkeypatch):
    monkeypatch.setitem(conftest.TRANSITIONS, (PAUSED, "AggP"), STANDBY)
    fake = attach(entity, PAUSED)
    await entity.async_start_new_clean()
    await entity._start_task
    assert fake.modes == ["AggP", "BBoCCAE="]
    assert entity.tuya_state == "Auto cleaning"


async def test_start_new_clean_starts_even_if_still_paused(entity, monkeypatch):
    monkeypatch.setattr(vacuum, "NEW_CLEAN_SETTLE_TIMEOUT", 0.2)
    fake = attach(entity, PAUSED)  # no transition: stays paused
    await entity.async_start_new_clean()
    await entity._start_task
    assert fake.modes == ["AggP", "BBoCCAE="]


async def test_start_new_clean_is_cancelled_by_another_command(entity, monkeypatch):
    monkeypatch.setitem(conftest.TRANSITIONS, (PAUSED, "AggP"), STANDBY)
    fake = attach(entity, PAUSED, known=True)
    await entity.async_start_new_clean()
    task = entity._start_task
    await asyncio.sleep(0)
    await entity.async_return_to_base()
    await asyncio.sleep(0.1)
    assert task.cancelled() or task.done()
    assert fake.modes[-1] == "AggG"


async def test_auto_clean_service_sends_only_start_auto(entity):
    fake = attach(entity, CHARGING)
    await entity.async_auto_clean()
    assert fake.modes == ["BBoCCAE="]


async def test_full_setup_registers_entities_and_services(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": make_item()}}
    )
    entry.add_to_hass(hass)
    with patch.object(robovac.TuyaLocalDiscovery, "start", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    for domain, key, entity_id in (
        ("switch", "dobby-id_boost_iq", "switch.dobby_boost_iq"),
        ("button", "dobby-id_stop_return", "button.dobby_stop_return_to_dock"),
        ("button", "dobby-id_locate", "button.dobby_locate"),
        ("select", "dobby-id_suction_level", "select.dobby_suction_level"),
    ):
        assert registry.async_get_entity_id(domain, DOMAIN, key) == entity_id
    assert hass.services.has_service(DOMAIN, "start_new_clean")
    assert hass.services.has_service(DOMAIN, "auto_clean")
    assert registry.async_get_entity_id("vacuum", DOMAIN, "dobby-id") == "vacuum.dobby"
    assert await hass.config_entries.async_unload(entry.entry_id)
