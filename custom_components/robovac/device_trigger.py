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

"""Device triggers: cleaning started/finished, docked, error."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
    STATE_ON,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    EVENT_CLEANING_ERROR,
    EVENT_CLEANING_FINISHED,
    EVENT_CLEANING_STARTED,
)

# Event-backed triggers (Phase 16 events) and the docked binary sensor.
EVENT_TRIGGERS = {
    "cleaning_started": EVENT_CLEANING_STARTED,
    "cleaning_finished": EVENT_CLEANING_FINISHED,
    "error": EVENT_CLEANING_ERROR,
}
DOCKED = "docked"
TRIGGER_TYPES = {*EVENT_TRIGGERS, DOCKED}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)}
)


def _docked_entity_id(hass: HomeAssistant, device_id: str) -> str | None:
    for entry in er.async_entries_for_device(er.async_get(hass), device_id):
        if (
            entry.platform == DOMAIN
            and entry.domain == "binary_sensor"
            and entry.unique_id.endswith("_docked")
        ):
            return entry.entity_id
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List the triggers for a RoboVac device."""
    registry = er.async_get(hass)
    if not any(
        entry.platform == DOMAIN
        for entry in er.async_entries_for_device(registry, device_id)
    ):
        return []
    has_docked = _docked_entity_id(hass, device_id) is not None
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger,
        }
        for trigger in sorted(TRIGGER_TYPES)
        if trigger != DOCKED or has_docked
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger."""
    trigger_type = config[CONF_TYPE]
    if trigger_type == DOCKED:
        entity_id = _docked_entity_id(hass, config[CONF_DEVICE_ID])
        state_config = await state_trigger.async_validate_trigger_config(
            hass,
            {
                CONF_PLATFORM: "state",
                CONF_ENTITY_ID: entity_id,
                state_trigger.CONF_TO: STATE_ON,
            },
        )
        return await state_trigger.async_attach_trigger(
            hass, state_config, action, trigger_info, platform_type="device"
        )
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: EVENT_TRIGGERS[trigger_type],
            event_trigger.CONF_EVENT_DATA: {CONF_DEVICE_ID: config[CONF_DEVICE_ID]},
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
