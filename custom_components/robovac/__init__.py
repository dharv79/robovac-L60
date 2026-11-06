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
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant

from .const import CONF_CAPTURE, CONF_VACS, CONFIG_VERSION, DOMAIN
from .coordinator import RoboVacCoordinator
from .tuyalocalapi import async_probe_device
from .tuyalocaldiscovery import TuyaLocalDiscovery

PLATFORMS = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
]
_LOGGER = logging.getLogger(__name__)

# Discovery broadcasts can be forged, so an IP change is applied only after the
# vacuum answers on the new IP with its local key, and at most once a minute.
IP_CHANGE_INTERVAL = 60
PROBE_TIMEOUT = 5
_IP_ATTEMPTS = "ip_change_attempts"

type RoboVacConfigEntry = ConfigEntry[dict[str, RoboVacCoordinator]]


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the Robovac domain."""
    hass.data.setdefault(DOMAIN, {})

    async def update_device(device):
        await async_update_device_ip(hass, device)

    tuyalocaldiscovery = TuyaLocalDiscovery(update_device)
    try:
        await tuyalocaldiscovery.start()
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, tuyalocaldiscovery.close)
    except Exception:
        _LOGGER.exception("Failed to set up discovery")

    return True


async def async_update_device_ip(hass: HomeAssistant, device: dict) -> None:
    """Apply a discovered IP for a known vacuum once it proves its identity."""
    gw_id = device["gwId"]
    entry = async_get_config_entry_for_device(hass, gw_id)
    if entry is None or not entry.state.recoverable:
        return

    vac = entry.data[CONF_VACS][gw_id]
    new_ip = device.get("ip")
    if (
        new_ip is None
        or not vac.get("autodiscovery", True)
        or vac.get(CONF_IP_ADDRESS) == new_ip
    ):
        return

    attempts = hass.data.setdefault(DOMAIN, {}).setdefault(_IP_ATTEMPTS, {})
    now = time.monotonic()
    if now - attempts.get(gw_id, -IP_CHANGE_INTERVAL) < IP_CHANGE_INTERVAL:
        return
    attempts[gw_id] = now

    if not await async_probe_device(
        new_ip, gw_id, vac.get(CONF_ACCESS_TOKEN), timeout=PROBE_TIMEOUT
    ):
        _LOGGER.debug(
            "Ignoring broadcast for %s: no authenticated reply from %s", gw_id, new_ip
        )
        return

    entry_data = dict(entry.data)
    vacs = dict(entry_data[CONF_VACS])
    vacs[gw_id] = {**vac, CONF_IP_ADDRESS: new_ip}
    entry_data[CONF_VACS] = vacs
    # Reconnect only this vacuum, then persist; the update listener ignores
    # IP-only changes, so nothing else restarts.
    coordinator = (getattr(entry, "runtime_data", None) or {}).get(gw_id)
    if coordinator is not None:
        await coordinator.async_set_host(new_ip)
    hass.config_entries.async_update_entry(entry, data=entry_data)
    _LOGGER.debug("Updated IP address of %s to %s", gw_id, new_ip)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries; v2 stops storing the Eufy account password."""
    if entry.version > CONFIG_VERSION:
        return False
    if entry.version < 2:
        data = {key: value for key, value in entry.data.items() if key != CONF_PASSWORD}
        hass.config_entries.async_update_entry(entry, data=data, version=2)
        _LOGGER.debug("Migrated %s to version 2 (password removed)", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RoboVacConfigEntry) -> bool:
    """Set up Robovac from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    entry.runtime_data = {
        vac_id: RoboVacCoordinator(hass, dict(item), entry)
        for vac_id, item in entry.data[CONF_VACS].items()
    }
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for coordinator in entry.runtime_data.values():
        coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RoboVacConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        for coordinator in entry.runtime_data.values():
            await coordinator.async_shutdown()
    return unloaded


LIVE_KEYS = (CONF_IP_ADDRESS, CONF_CAPTURE)  # applied per vacuum, no reload


def _without_ip(vacs: dict) -> dict:
    return {
        vac_id: {k: v for k, v in vac.items() if k not in LIVE_KEYS}
        for vac_id, vac in vacs.items()
    }


async def update_listener(hass: HomeAssistant, entry: RoboVacConfigEntry) -> None:
    """Reload on real option changes; apply IP-only changes per vacuum."""
    coordinators = entry.runtime_data
    vacs = entry.data[CONF_VACS]
    current = _without_ip(vacs)
    known = _without_ip({vac_id: c.item for vac_id, c in coordinators.items()})
    if current != known:
        await hass.config_entries.async_reload(entry.entry_id)
        return
    for vac_id, coordinator in coordinators.items():
        coordinator.async_set_capture(bool(vacs[vac_id].get(CONF_CAPTURE)))
        await coordinator.async_set_host(vacs[vac_id].get(CONF_IP_ADDRESS))


def async_get_config_entry_for_device(hass: HomeAssistant, device_id: str):
    """Get config entry containing a given Robovac device."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if device_id in entry.data.get(CONF_VACS, {}):
            return entry
    return None