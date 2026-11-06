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

"""Phase 17: device triggers and bundled blueprints."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint import models
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import async_initialize_triggers
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml as yaml_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.robovac import device_trigger
from custom_components.robovac.const import (
    CONF_VACS,
    DOMAIN,
    EVENT_CLEANING_ERROR,
    EVENT_CLEANING_FINISHED,
    EVENT_CLEANING_STARTED,
)

from .conftest import make_item

BLUEPRINTS = Path(__file__).parent.parent / "blueprints" / "automation" / "robovac"


@pytest.fixture
def device(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_VACS: {"dobby-id": make_item()}})
    entry.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "dobby-id")}, name="Dobby"
    )
    er.async_get(hass).async_get_or_create(
        "binary_sensor", DOMAIN, "dobby-id_docked", config_entry=entry, device_id=dev.id
    )
    return dev


async def test_lists_all_triggers_for_a_robovac_device(hass, device):
    triggers = await device_trigger.async_get_triggers(hass, device.id)
    assert {t[CONF_TYPE] for t in triggers} == {
        "cleaning_started", "cleaning_finished", "docked", "error"
    }
    assert all(t[CONF_DOMAIN] == DOMAIN and t[CONF_PLATFORM] == "device" for t in triggers)


async def test_other_devices_get_none(hass, device):
    entry = MockConfigEntry(domain="other")
    entry.add_to_hass(hass)
    other = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("other", "x")}
    )
    assert await device_trigger.async_get_triggers(hass, other.id) == []


async def attach(hass, device_id, trigger_type):
    fired = []

    async def action(run_variables, context=None):
        fired.append(run_variables["trigger"]["platform"])

    unsub = await async_initialize_triggers(
        hass,
        [{CONF_PLATFORM: "device", CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: trigger_type}],
        action,
        DOMAIN,
        "test",
        lambda *args, **kwargs: None,
    )
    return fired, unsub


@pytest.mark.parametrize(
    ("trigger_type", "event"),
    [
        ("cleaning_started", EVENT_CLEANING_STARTED),
        ("cleaning_finished", EVENT_CLEANING_FINISHED),
        ("error", EVENT_CLEANING_ERROR),
    ],
)
async def test_event_triggers_fire_for_their_device_only(hass, device, trigger_type, event):
    fired, unsub = await attach(hass, device.id, trigger_type)
    hass.bus.async_fire(event, {CONF_DEVICE_ID: "someone-else"})
    hass.bus.async_fire("robovac_other", {CONF_DEVICE_ID: device.id})
    await hass.async_block_till_done()
    assert fired == []
    hass.bus.async_fire(event, {CONF_DEVICE_ID: device.id})
    await hass.async_block_till_done()
    assert fired == ["device"]
    unsub()


async def test_docked_trigger_fires_when_the_sensor_turns_on(hass, device):
    fired, unsub = await attach(hass, device.id, "docked")
    entity_id = device_trigger._docked_entity_id(hass, device.id)
    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()
    assert fired == []
    hass.states.async_set(entity_id, "on")
    await hass.async_block_till_done()
    assert fired == ["device"]
    unsub()


@pytest.mark.parametrize("name", ["notify_on_error", "clean_when_away", "dock_at_time"])
def test_blueprints_are_valid_and_use_only_standard_services(name):
    path = BLUEPRINTS / f"{name}.yaml"
    blueprint = models.Blueprint(
        yaml_util.load_yaml(path),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    assert blueprint.inputs
    text = path.read_text()
    for line in text.splitlines():
        if line.strip().startswith("- action:"):
            assert line.split(":", 1)[1].strip().startswith("vacuum."), line


async def test_blueprint_automation_runs(hass, device):
    """The dock-at-time blueprint, applied for real, sends the vacuum home."""
    calls = []
    hass.services.async_register("vacuum", "return_to_base", lambda call: calls.append(call))
    hass.states.async_set("vacuum.dobby", "cleaning")
    blueprint = models.Blueprint(
        yaml_util.load_yaml(BLUEPRINTS / "dock_at_time.yaml"),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    inputs = models.BlueprintInputs(
        blueprint,
        {"use_blueprint": {"path": "robovac/dock_at_time.yaml",
                           "input": {"vacuum": "vacuum.dobby", "dock_time": "21:00:00"}}},
    )
    inputs.validate()
    config = inputs.async_substitute()
    assert config["triggers"][0]["at"] == "21:00:00"
    assert config["actions"][0]["target"]["entity_id"] == "vacuum.dobby"
    assert await async_setup_component(hass, "automation", {})
