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

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_VACS, DOMAIN
from .tuyalocaldiscovery import TuyaLocalDiscovery

PLATFORMS = [Platform.VACUUM, Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the Robovac domain."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(CONF_VACS, {})

    async def update_device(device):
        entry = async_get_config_entry_for_device(hass, device["gwId"])
        if entry is None:
            return

        if not entry.state.recoverable:
            return

        entry_data = dict(entry.data)
        vacs = dict(entry_data.get(CONF_VACS, {}))

        if (
            device["gwId"] in vacs
            and device.get("ip") is not None
            and vacs[device["gwId"]].get("autodiscovery", True)
        ):
            if vacs[device["gwId"]].get(CONF_IP_ADDRESS) != device["ip"]:
                vac = dict(vacs[device["gwId"]])
                vac[CONF_IP_ADDRESS] = device["ip"]
                vacs[device["gwId"]] = vac
                entry_data[CONF_VACS] = vacs

                hass.config_entries.async_update_entry(entry, data=entry_data)
                await hass.config_entries.async_reload(entry.entry_id)
                _LOGGER.debug(
                    "Updated IP address of %s to %s",
                    device["gwId"],
                    device["ip"],
                )

    tuyalocaldiscovery = TuyaLocalDiscovery(update_device)
    try:
        await tuyalocaldiscovery.start()
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, tuyalocaldiscovery.close)
    except Exception:
        _LOGGER.exception("Failed to set up discovery")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Robovac from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(CONF_VACS, {})

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def async_get_config_entry_for_device(hass: HomeAssistant, device_id: str):
    """Get config entry containing a given Robovac device."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if device_id in entry.data.get(CONF_VACS, {}):
            return entry
    return None