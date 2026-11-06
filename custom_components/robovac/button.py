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


"""Buttons: stop return to dock, locate."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoboVacConfigEntry
from .coordinator import RoboVacCoordinator
from .entity import RoboVacBaseEntity
from .vacuums.base import ModeKey, RobovacCommand


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[ButtonEntity] = []
    for coordinator in config_entry.runtime_data.values():
        if ModeKey.STOP_RETURN in coordinator.declared_modes and (
            RobovacCommand.MODE in coordinator.command_codes
        ):
            entities.append(StopReturnButton(coordinator))
        if RobovacCommand.LOCATE in coordinator.command_codes:
            entities.append(LocateButton(coordinator))
    async_add_entities(entities)


class StopReturnButton(RoboVacBaseEntity, ButtonEntity):
    """Cancel a return to dock, leaving the vacuum where it is."""

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "stop_return")

    async def async_press(self) -> None:
        coordinator = self.coordinator
        await coordinator.async_send_dps(
            {
                coordinator.command_codes[RobovacCommand.MODE]: coordinator.mode_values[
                    ModeKey.STOP_RETURN
                ]
            },
            supersede_start=True,
        )


class LocateButton(RoboVacBaseEntity, ButtonEntity):
    """Make the vacuum beep (the device toggles locate on each write)."""

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "locate")

    async def async_press(self) -> None:
        coordinator = self.coordinator
        code = coordinator.command_codes[RobovacCommand.LOCATE]
        current = coordinator.data.dps.get(code) if coordinator.data else None
        await coordinator.async_send_dps({code: not current})
