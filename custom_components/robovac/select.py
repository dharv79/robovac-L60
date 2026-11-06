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


"""Select: suction level, using the model's fan speeds."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoboVacConfigEntry
from .coordinator import RoboVacCoordinator
from .entity import RoboVacBaseEntity
from .vacuums.base import RobovacCommand


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        SuctionSelect(coordinator)
        for coordinator in config_entry.runtime_data.values()
        if coordinator.fan_speed_map and RobovacCommand.FAN_SPEED in coordinator.command_codes
    )


class SuctionSelect(RoboVacBaseEntity, SelectEntity):
    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "suction_level")
        self._attr_options = list(coordinator.fan_speed_map)

    @property
    def current_option(self) -> str | None:
        speed = self.coordinator.data.fan_speed if self.coordinator.data else None
        return speed if speed in self.coordinator.fan_speed_map else None

    async def async_select_option(self, option: str) -> None:
        raw = self.coordinator.fan_speed_map.get(option)
        if raw is None:
            return
        code = self.coordinator.command_codes[RobovacCommand.FAN_SPEED]
        await self.coordinator.async_send_dps({code: raw})
