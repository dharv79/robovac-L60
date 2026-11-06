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


"""Base class for the per-vacuum helper entities (switch, button, select...)."""

from __future__ import annotations

from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RoboVacCoordinator


class RoboVacBaseEntity(CoordinatorEntity[RoboVacCoordinator]):
    """A named entity on the vacuum's device, fed by its coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RoboVacCoordinator, key: str) -> None:
        super().__init__(coordinator)
        item = coordinator.item
        self.robovac_id = item[CONF_ID]
        self._attr_translation_key = key
        self._attr_unique_id = f"{item[CONF_ID]}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])}, name=item[CONF_NAME]
        )

    @property
    def available(self) -> bool:
        return self.coordinator.available
