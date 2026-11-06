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

"""Download diagnostics: a redacted dump for issues and DPS reverse-engineering."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from .coordinator import RoboVacCoordinator
from .vacuums.base import RoboVacEntityFeature

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_CLIENT_ID,
    CONF_MAC,
}


def _coordinator_info(coordinator: RoboVacCoordinator) -> dict[str, Any]:
    """Device and state facts; present even when the model is unsupported."""
    vacuum = coordinator.vacuum
    info: dict[str, Any] = {
        "model_code": coordinator.item.get("model"),
        "model_class": getattr(vacuum.model_details, "__name__", None) if vacuum else None,
        "fault": coordinator.fault,
        "error_code": coordinator.error_code,
        "available": coordinator.available,
        "connected": coordinator.connected,
        "capture_mode": coordinator.capture,
        "features": [
            feature.name
            for feature in RoboVacEntityFeature
            if coordinator.supports(feature)
        ],
        "command_codes": {str(k): v for k, v in coordinator.command_codes.items()},
    }
    if vacuum is not None:
        info["protocol_version"] = ".".join(map(str, vacuum.version))
        info["raw_dps"] = {str(k): v for k, v in vacuum._dps.items()}
    return info


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for the config entry."""
    coordinators: dict[str, RoboVacCoordinator] = getattr(entry, "runtime_data", None) or {}
    return {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "version": entry.version,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT | {"title"},
        ),
        "vacuums": {
            vac_id: async_redact_data(_coordinator_info(coordinator), TO_REDACT)
            for vac_id, coordinator in coordinators.items()
        },
    }
