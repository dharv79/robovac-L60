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


"""Binary sensors: docked, charging, connected."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RoboVacConfigEntry
from .coordinator import DOCKED_STATES, RoboVacCoordinator
from .entity import RoboVacBaseEntity
from .vacuums.base import RobovacCommand


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[BinarySensorEntity] = []
    for coordinator in config_entry.runtime_data.values():
        if coordinator.vacuum is None:
            continue
        entities.append(ConnectedBinarySensor(coordinator))
        if RobovacCommand.STATUS in coordinator.command_codes:
            entities += [DockedBinarySensor(coordinator), ChargingBinarySensor(coordinator)]
    async_add_entities(entities)


class _StatusBinarySensor(RoboVacBaseEntity, BinarySensorEntity):
    """On/off from the parsed status; unknown until the device reports one."""

    def _status(self) -> str | None:
        return self.coordinator.data.status if self.coordinator.data else None


class DockedBinarySensor(_StatusBinarySensor):
    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "docked")

    @property
    def is_on(self) -> bool | None:
        status = self._status()
        return None if status is None else status in DOCKED_STATES


class ChargingBinarySensor(_StatusBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "charging")

    @property
    def is_on(self) -> bool | None:
        status = self._status()
        return None if status is None else status == "Charging"


class ConnectedBinarySensor(RoboVacBaseEntity, BinarySensorEntity):
    """The local socket to the vacuum; always available so it can read off."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected
