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

"""Per-vacuum coordinator: owns the device, parses state once, pushes updates."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from collections.abc import Callable

from homeassistant.components.vacuum import VacuumActivity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_ID,
    CONF_IP_ADDRESS,
    CONF_MODEL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import tuyalocalapi
from .const import DOMAIN, PING_RATE, REFRESH_RATE, TIMEOUT
from .robovac import ModelNotSupportedException, RoboVac
from .tuyalocalapi import InvalidKey, TuyaException
from .vacuums.base import (
    DEFAULT_MODE_VALUES,
    RoboVacEntityFeature,
    RobovacCommand,
    resolve_mode_labels,
    resolve_mode_values,
)

_LOGGER = logging.getLogger(__name__)

# Pushes are the main source of state; this poll and the watchdog only cover
# a vacuum that has gone quiet.
FALLBACK_UPDATE_INTERVAL = timedelta(minutes=5)
UPDATE_RETRIES = 4
WARMUP_ATTEMPTS = 5
WARMUP_DELAY = 1.5

ATTR_CLEANING_AREA = "cleaning_area"
ATTR_CLEANING_TIME = "cleaning_time"
ATTR_AUTO_RETURN = "auto_return"
ATTR_DO_NOT_DISTURB = "do_not_disturb"
ATTR_BOOST_IQ = "boost_iq"

TUYA_STATUS_MAPPING = {
    "BgoAEAUyAA==": "AUTO",
    "BgoAEAVSAA==": "POSITION",
    "CAoAEAUyAggB": "PAUSE",
    "CAoCCAEQBTIA": "ROOM",
    "CAoCCAEQBVIA": "ROOM_POSITION",
    "CgoCCAEQBTICCAE=": "ROOM_PAUSE",
    "CAoCCAIQBTIA": "SPOT",
    "CAoCCAIQBVIA": "SPOT_POSITION",
    "CgoCCAIQBTICCAE=": "SPOT_PAUSE",
    "BAoAEAY=": "START_MANUAL",
    "BBAHQgA=": "GOING_TO_CHARGE",
    "BBADGgA=": "CHARGING",
    "BhADGgIIAQ==": "COMPLETED",
    "AA==": "STANDBY",
    "AhAB": "SLEEPING",
}

STATUS_MAPPING = {
    "AUTO": "Auto cleaning",
    "POSITION": "Positioning",
    "PAUSE": "Cleaning paused",
    "ROOM": "Cleaning room",
    "ROOM_POSITION": "Positioning room",
    "ROOM_PAUSE": "Cleaning room paused",
    "SPOT": "Spot cleaning",
    "SPOT_POSITION": "Positioning spot",
    "SPOT_PAUSE": "Cleaning spot paused",
    "START_MANUAL": "Manual mode",
    "GOING_TO_CHARGE": "Recharge",
    "CHARGING": "Charging",
    "COMPLETED": "Completed",
    "STANDBY": "Standby",
    "SLEEPING": "Sleeping",
}

PAUSED_STATES = ("Cleaning paused", "Cleaning room paused", "Cleaning spot paused")

ERROR_MAPPING = {
    "DAiI6suO9dXszgFSAA==": "no_error",
    "FAjwudWorOPszgEaAqURUgQSAqUR": "Sidebrush stuck",
    "FAj+nMu7zuPszgEaAtg2UgQSAtg2": "Robot stuck",
    "DAjtzbfps+XszgFSAA==": "no_error",
    "DAiom9rd6eTszgFSAA==": "no_error",
    "DAia8JTV5OPszgFSAA==": "no_error",
    "DAj489bWsePszgFSAA==": "no_error",
}

# Raw DPS values exposed as extra attributes when the model advertises the feature.
PASSTHROUGH_ATTRIBUTES = (
    (RoboVacEntityFeature.CLEANING_AREA, RobovacCommand.CLEANING_AREA, ATTR_CLEANING_AREA),
    (RoboVacEntityFeature.CLEANING_TIME, RobovacCommand.CLEANING_TIME, ATTR_CLEANING_TIME),
    (RoboVacEntityFeature.AUTO_RETURN, RobovacCommand.AUTO_RETURN, ATTR_AUTO_RETURN),
    (RoboVacEntityFeature.DO_NOT_DISTURB, RobovacCommand.DO_NOT_DISTURB, ATTR_DO_NOT_DISTURB),
    (RoboVacEntityFeature.BOOST_IQ, RobovacCommand.BOOST_IQ, ATTR_BOOST_IQ),
)

NO_ERROR_CODES = (0, "no_error", None)





@dataclass(frozen=True)
class RoboVacData:
    """State parsed from one DPS payload."""

    dps: dict[str, Any] = field(default_factory=dict)
    status: str | None = None  # human-readable, a STATUS_MAPPING value
    error: str | None = None
    mode: str | None = None
    battery: int | None = None
    fan_speed: str | None = None
    consumables: Any = None
    passthrough: dict[str, Any] = field(default_factory=dict)


EMPTY_DATA = RoboVacData()


def live_activity(status: str | None, error: str | None) -> VacuumActivity:
    """Device-reported activity (command logic uses this, never restored state)."""
    if status is None:
        return VacuumActivity.IDLE
    if error not in NO_ERROR_CODES:
        return VacuumActivity.ERROR
    if status in ("Charging", "Completed"):
        return VacuumActivity.DOCKED
    if status == "Recharge":
        return VacuumActivity.RETURNING
    if status in ("Sleeping", "Standby"):
        return VacuumActivity.IDLE
    if status in PAUSED_STATES:
        return VacuumActivity.PAUSED
    return VacuumActivity.CLEANING


class RoboVacCoordinator(DataUpdateCoordinator[RoboVacData]):
    """One per vacuum. Owns the RoboVac device and the parsed state."""

    def __init__(
        self,
        hass: HomeAssistant,
        item: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {item[CONF_ID]}",
            config_entry=config_entry,
            update_interval=FALLBACK_UPDATE_INTERVAL,
        )
        self.item = item
        self.vacuum_id: str = item[CONF_ID]
        self.ip_address: str | None = item[CONF_IP_ADDRESS]
        self.available = False  # until the first good update
        self.update_failures = 0
        self.fault: str | None = None  # UNSUPPORTED_MODEL, INVALID_KEY, IP_ADDRESS...
        self.cleaning = asyncio.Event()
        self._unavailable_logged = False
        self._warmup_task: asyncio.Task | None = None
        self._refresh_task: asyncio.Task | None = None
        # Set by the vacuum entity: cancels its start sequence when another
        # entity (button, service) writes a mode command.
        self.cancel_start: Callable[[], None] | None = None
        self._unsub_watchdog = None
        self._last_data = 0.0
        self.vacuum: RoboVac | None = self._create_device()

        if self.vacuum is not None:
            details = self.vacuum.model_details
            self.robovac_features = self.vacuum.getRoboVacFeatures()
            self.fan_speed_map = {
                friendly_text(speed): speed for speed in self.vacuum.getFanSpeeds()
            }
            self.command_codes = self.vacuum.getCommandCodes()
            self.mode_values = resolve_mode_values(details)
            self.mode_labels = resolve_mode_labels(details)
            # Mode keys the model file declares itself (not shared defaults).
            self.declared_modes = frozenset(getattr(details, "mode_values", {}))
            self.status_values = {
                **TUYA_STATUS_MAPPING,
                **getattr(details, "status_values", {}),
            }
        else:
            self.robovac_features = 0
            self.fan_speed_map = {}
            self.command_codes = {}
            self.mode_values = dict(DEFAULT_MODE_VALUES)
            self.mode_labels = {}
            self.declared_modes = frozenset()
            self.status_values = dict(TUYA_STATUS_MAPPING)

    # --- device ---------------------------------------------------------

    def _create_device(self) -> RoboVac | None:
        try:
            return RoboVac(
                device_id=self.vacuum_id,
                host=self.ip_address,
                local_key=self.item[CONF_ACCESS_TOKEN],
                timeout=TIMEOUT,
                ping_interval=PING_RATE,
                model_code=(self.item[CONF_MODEL] or "")[:5],
                update_entity_state=self.pushed_update_handler,
            )
        except ModelNotSupportedException:
            self.fault = "UNSUPPORTED_MODEL"
        except InvalidKey:
            self.fault = "INVALID_KEY"
        return None

    @property
    def error_code(self) -> str | None:
        return self.fault or (self.data or EMPTY_DATA).error

    def supports(self, feature: RoboVacEntityFeature) -> bool:
        return bool(self.robovac_features & feature)

    # --- lifecycle ------------------------------------------------------

    def async_start(self) -> None:
        """Warm up in the background and start the quiet-vacuum watchdog."""
        if self.vacuum is None:
            return
        if not self.ip_address:
            self.fault = "IP_ADDRESS"
            return
        self._unsub_watchdog = async_track_time_interval(
            self.hass, self._async_watchdog, timedelta(seconds=REFRESH_RATE)
        )
        self._warmup_task = self.hass.async_create_background_task(
            self._async_warm_up(), name=f"robovac warm-up {self.vacuum_id}"
        )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unsub_watchdog is not None:
            self._unsub_watchdog()
            self._unsub_watchdog = None
        if self._warmup_task is not None:
            self._warmup_task.cancel()
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        if self.vacuum is not None:
            await self.vacuum.async_disable()

    async def async_set_host(self, host: str) -> None:
        """Reconnect this vacuum on a new IP, leaving other vacuums alone."""
        if not host or host == self.ip_address:
            return
        _LOGGER.debug("Reconnecting %s on a new address", self.vacuum_id)
        self.ip_address = host
        self.item = {**self.item, CONF_IP_ADDRESS: host}
        self.fault = None if self.fault == "IP_ADDRESS" else self.fault
        if self._warmup_task is not None:
            self._warmup_task.cancel()
        if self.vacuum is not None:
            await self.vacuum.async_disable()
        self.vacuum = self._create_device()
        if self.vacuum is not None:
            self._last_data = 0.0
            self._warmup_task = self.hass.async_create_background_task(
                self._async_warm_up(), name=f"robovac warm-up {self.vacuum_id}"
            )

    async def _async_warm_up(self) -> None:
        """Poll a few times so the entity comes up promptly on restart."""
        for attempt in range(WARMUP_ATTEMPTS):
            if self.available:
                return  # a push or regular poll got there first
            try:
                await self.async_forced_refresh()
            except Exception as err:
                _LOGGER.debug(
                    "Startup refresh attempt %s failed for %s: %s",
                    attempt + 1,
                    self.vacuum_id,
                    err,
                )
            else:
                if self.available:
                    return
            await asyncio.sleep(WARMUP_DELAY)

        self._mark_unavailable("no response during startup")
        self.async_update_listeners()

    async def _async_watchdog(self, _now: datetime) -> None:
        """Force a GET when no push or poll has landed for REFRESH_RATE."""
        if time.monotonic() - self._last_data >= REFRESH_RATE:
            await self.async_refresh()

    # --- availability ---------------------------------------------------

    def _mark_available(self) -> None:
        self.update_failures = 0
        self.available = True
        if self._unavailable_logged:
            _LOGGER.info("Vacuum %s is available again", self.vacuum_id)
            self._unavailable_logged = False

    def _mark_unavailable(self, reason: Any) -> None:
        self.available = False
        if not self._unavailable_logged:
            _LOGGER.warning("Vacuum %s is unavailable: %s", self.vacuum_id, reason)
            self._unavailable_logged = True

    # --- updates --------------------------------------------------------

    async def _async_update_data(self) -> RoboVacData:
        """Fallback GET. Failures keep the last data until UPDATE_RETRIES."""
        if self.vacuum is None:
            return self.data or EMPTY_DATA
        if not self.ip_address:
            self.fault = "IP_ADDRESS"
            return self.data or EMPTY_DATA
        try:
            await self.vacuum.async_get()
        except TuyaException as err:
            self.update_failures += 1
            _LOGGER.debug(
                "Update timeout/error for %s. Failure count: %s. Reason: %s",
                self.vacuum_id,
                self.update_failures,
                err,
            )
            if self.update_failures >= UPDATE_RETRIES:
                self.fault = "CONNECTION_FAILED"
                self._mark_unavailable(err)
            return self.data or EMPTY_DATA

        data = self._parse()
        if data is None:
            _LOGGER.debug(
                "Vacuum %s returned no DPS yet; keeping previous state", self.vacuum_id
            )
            return self.data or EMPTY_DATA
        self._mark_available()
        return data

    async def async_forced_refresh(self) -> None:
        """GET now and publish; errors propagate (used after commands)."""
        if self.vacuum is None or not self.ip_address:
            return
        await self.vacuum.async_get()
        self.update_from_device()

    async def async_send_dps(
        self, *dps_updates: dict[str, Any], supersede_start: bool = False
    ) -> None:
        """Write DPS values, then refresh state once for the whole burst.

        supersede_start: a mode command that cancels a running start sequence.
        """
        if self.vacuum is None:
            return
        if supersede_start and self.cancel_start is not None:
            self.cancel_start()
        for dps in dps_updates:
            await self.vacuum.async_set(dps)
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = self.hass.async_create_background_task(
                self._async_refresh_after_command(),
                name=f"robovac refresh {self.vacuum_id}",
            )

    async def _async_refresh_after_command(self) -> None:
        try:
            await self.async_forced_refresh()
        except TuyaException as err:
            _LOGGER.debug("Refresh after command failed for %s: %s", self.vacuum_id, err)

    async def pushed_update_handler(self) -> None:
        """Handle a push from the device."""
        self.update_from_device()

    def update_from_device(self) -> None:
        """Parse the device's current DPS and publish it to the entities."""
        data = self._parse()
        if data is None:
            return
        self._mark_available()
        self.async_set_updated_data(data)

    def _parse(self) -> RoboVacData | None:
        if self.vacuum is None:
            return None
        dps = self.vacuum._dps
        if not dps:
            _LOGGER.debug(
                "No DPS datapoints available yet for %s; skipping state refresh",
                self.vacuum_id,
            )
            return None
        dps = dict(dps)
        if tuyalocalapi.VERBOSE:
            _LOGGER.debug("tuyastatus %s", dps)

        def value(command: RobovacCommand, default: Any = None) -> Any:
            return dps.get(self.command_codes.get(command), default)

        try:
            raw_batt = value(RobovacCommand.BATTERY)
            battery = int(raw_batt) if raw_batt is not None else None
        except (TypeError, ValueError):
            battery = None

        raw_mode = value(RobovacCommand.MODE)
        raw_fan = value(RobovacCommand.FAN_SPEED, "")
        consumables = self.data.consumables if self.data else None
        if self.supports(RoboVacEntityFeature.CONSUMABLES):
            consumables = _decode_consumables(
                value(RobovacCommand.CONSUMABLES), consumables, self.vacuum_id
            )
        data = RoboVacData(
            dps=dps,
            status=STATUS_MAPPING.get(self.status_values.get(value(RobovacCommand.STATUS))),
            error=ERROR_MAPPING.get(value(RobovacCommand.ERROR), "no_error"),
            mode=self.mode_labels.get(raw_mode, raw_mode),
            battery=battery,
            fan_speed=friendly_text(raw_fan) if raw_fan else None,
            consumables=consumables,
            passthrough={
                attr: value(command)
                for feature, command, attr in PASSTHROUGH_ATTRIBUTES
                if self.supports(feature)
            },
        )
        self.fault = None
        self._last_data = time.monotonic()
        if live_activity(data.status, data.error) == VacuumActivity.CLEANING:
            self.cleaning.set()
        else:
            self.cleaning.clear()
        _LOGGER.debug(
            "Decoded %s: state=%s error=%s mode=%s fan=%s battery=%s",
            self.vacuum_id,
            data.status,
            data.error,
            data.mode,
            data.fan_speed,
            data.battery,
        )
        return data


def _decode_consumables(raw: Any, previous: Any, vacuum_id: str) -> Any:
    if not raw:
        return previous
    try:
        consumables = json.loads(base64.b64decode(raw).decode("ascii"))
        _LOGGER.debug("Consumables decoded value is: %s", consumables)
        if isinstance(consumables, dict) and "duration" in consumables.get(
            "consumable", {}
        ):
            return consumables["consumable"]["duration"]
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Failed to decode consumables for %s: %s", vacuum_id, err)
    return previous


def friendly_text(input_value: str) -> str:
    """Convert string to friendly text."""
    if not input_value:
        return ""
    return " ".join(
        word[0].upper() + word[1:] for word in input_value.replace("_", " ").split()
    )
