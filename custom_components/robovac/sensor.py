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
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_ID,
    CONF_NAME,
    PERCENTAGE,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RoboVacConfigEntry
from .const import DOMAIN, EVENT_CLEANING_FINISHED
from .coordinator import PROMPT_TEXT, STATUS_MAPPING, RoboVacCoordinator
from .entity import RoboVacBaseEntity
from .vacuums.base import RobovacCommand

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: RoboVacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up battery sensors for each vacuum."""
    entities: list[SensorEntity] = []
    for coordinator in config_entry.runtime_data.values():
        entities.append(RobovacBatterySensor(coordinator))
        if coordinator.vacuum is not None:
            entities.append(LastSeenSensor(coordinator))
            entities += [
                CleaningCountSensor(coordinator),
                LastCleanedSensor(coordinator),
                LastCleanDurationSensor(coordinator),
            ]
            if RobovacCommand.STATUS in coordinator.command_codes:
                entities.append(StatusSensor(coordinator))
            if RobovacCommand.LAST_PROMPT in coordinator.command_codes:
                entities.append(LastPromptSensor(coordinator))
    async_add_entities(entities)


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


class StatusSensor(RoboVacBaseEntity, SensorEntity):
    """The vacuum's status text ("Recharge", "Cleaning paused", ...)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "status")
        keys = set(coordinator.status_values.values())
        self._attr_options = [text for key, text in STATUS_MAPPING.items() if key in keys]

    @property
    def native_value(self) -> str | None:
        status = self.coordinator.data.status if self.coordinator.data else None
        return status if status in self._attr_options else None


class LastSeenSensor(RoboVacBaseEntity, SensorEntity):
    """When the vacuum last pushed or answered a GET."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "last_seen")

    @property
    def available(self) -> bool:
        return True  # a stale timestamp is the point while the vacuum is offline

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_seen


class LastPromptSensor(RoboVacBaseEntity, SensorEntity):
    """The vacuum's last spoken prompt (DPS 178), e.g. "Can't start while recharging"."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "last_prompt")

    def _code(self) -> int | None:
        return self.coordinator.data.last_prompt if self.coordinator.data else None

    @property
    def native_value(self) -> str | None:
        code = self._code()
        if code is None:
            return None
        return PROMPT_TEXT.get(code, f"code {code}")

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        code = self._code()
        return None if code is None else {"code": code}


class CleanHistorySensor(RoboVacBaseEntity, RestoreSensor):
    """Updated by each finished-clean event; keeps its value across restarts."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True  # history is still true while the vacuum is offline

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._restore(last.native_value)

        @callback
        def mine(data) -> bool:
            return data.get("vacuum_id") == self.robovac_id

        self.async_on_remove(
            self.hass.bus.async_listen(
                EVENT_CLEANING_FINISHED, self._handle_finished, event_filter=mine
            )
        )

    @callback
    def _handle_finished(self, event: Event) -> None:
        self._apply(event)
        self.async_write_ha_state()

    def _restore(self, value) -> None:
        self._attr_native_value = value

    def _apply(self, event: Event) -> None:
        raise NotImplementedError


class CleaningCountSensor(CleanHistorySensor):
    """Finished cleans since the sensor was created."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "cleaning_count")
        self._attr_native_value = 0

    def _restore(self, value) -> None:
        try:
            self._attr_native_value = int(value)
        except (TypeError, ValueError):
            pass

    def _apply(self, event: Event) -> None:
        self._attr_native_value = int(self._attr_native_value or 0) + 1


class LastCleanedSensor(CleanHistorySensor):
    """When the last clean finished."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "last_cleaned")

    def _apply(self, event: Event) -> None:
        self._attr_native_value = event.time_fired


class LastCleanDurationSensor(CleanHistorySensor):
    """How long the last clean ran."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        super().__init__(coordinator, "last_clean_duration")

    def _apply(self, event: Event) -> None:
        self._attr_native_value = event.data.get("duration")
