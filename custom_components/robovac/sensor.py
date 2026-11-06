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

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONF_ID, CONF_NAME, PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RoboVacConfigEntry
from .const import DOMAIN
from .coordinator import RoboVacCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up battery sensors for each vacuum."""
    async_add_entities(
        RobovacBatterySensor(coordinator)
        for coordinator in config_entry.runtime_data.values()
    )


class RobovacBatterySensor(CoordinatorEntity[RoboVacCoordinator], SensorEntity):
    """Battery % for a Robovac, read from the coordinator's parsed state."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator)
        item = coordinator.item
        self.robovac_id = item[CONF_ID]
        self._attr_unique_id = f"{item[CONF_ID]}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])},
            name=item[CONF_NAME],
        )
        self._attr_native_value: int | None = None
        self._cache_battery()

    def _cache_battery(self) -> None:
        battery = self.coordinator.data.battery if self.coordinator.data else None
        if battery is not None:
            self._attr_native_value = battery

    @property
    def available(self) -> bool:
        """Always available, keeping the last reading, so the sensor doesn't
        flap while the vacuum sleeps or reconnects."""
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self._cache_battery()
        super()._handle_coordinator_update()
