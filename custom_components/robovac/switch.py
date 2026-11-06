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


"""Switches: Boost IQ, written as an explicit on/off (never a toggle)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoboVacConfigEntry
from .coordinator import ATTR_BOOST_IQ, RoboVacCoordinator
from .entity import RoboVacBaseEntity
from .vacuums.base import RoboVacEntityFeature, RobovacCommand


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        BoostIQSwitch(coordinator)
        for coordinator in config_entry.runtime_data.values()
        if coordinator.supports(RoboVacEntityFeature.BOOST_IQ)
        and RobovacCommand.BOOST_IQ in coordinator.command_codes
    )


class BoostIQSwitch(RoboVacBaseEntity, SwitchEntity):
    """Boost IQ on/off. State is unknown until the device reports it."""

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "boost_iq")

    @property
    def is_on(self) -> bool | None:
        value = (self.coordinator.data.passthrough if self.coordinator.data else {}).get(
            ATTR_BOOST_IQ
        )
        return None if value is None else bool(value)

    async def _async_write(self, value: bool) -> None:
        code = self.coordinator.command_codes[RobovacCommand.BOOST_IQ]
        await self.coordinator.async_send_dps({code: value})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(False)
