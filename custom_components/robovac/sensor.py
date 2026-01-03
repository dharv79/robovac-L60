# Copyright 2022 Brendan McCluskey
# Copyright (c) 2025 Dave Harvey
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
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, CONF_NAME, CONF_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_VACS, DOMAIN, REFRESH_RATE

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=REFRESH_RATE)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up battery sensors for each vacuum."""
    vacuums = config_entry.data[CONF_VACS]

    entities: list[RobovacBatterySensor] = []
    for key in vacuums:
        item = vacuums[key]
        entities.append(RobovacBatterySensor(item))

    async_add_entities(entities)


class RobovacBatterySensor(SensorEntity):
    """Battery % for a Robovac, linked to the same device as the vacuum entity."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, item: dict) -> None:
        self.robovac_id = item[CONF_ID]

        # IMPORTANT: do NOT reuse the vacuum unique_id
        self._attr_unique_id = f"{item[CONF_ID]}_battery"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])},
            name=item[CONF_NAME],
        )

        self._battery_level: int | None = None

    def update(self) -> None:
        """Poll battery from the vacuum entity cache."""
        try:
            vac_entity = self.hass.data[DOMAIN][CONF_VACS][self.robovac_id]
            # Read an internal cache set by vacuum.py
            self._battery_level = getattr(vac_entity, "_battery_level_cache", None)
            self._attr_available = self._battery_level is not None
        except Exception:
            _LOGGER.debug("Failed to get battery level for %s", self.robovac_id)
            self._battery_level = None
            self._attr_available = False

    @property
    def native_value(self) -> int | None:
        return self._battery_level
