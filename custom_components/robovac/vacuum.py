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

"""Eufy Robovac L60 vacuum platform."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DESCRIPTION,
    CONF_ID,
    CONF_IP_ADDRESS,
    CONF_MAC,
    CONF_MODEL,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_VACS, DOMAIN, PING_RATE, REFRESH_RATE, TIMEOUT
from .errors import getErrorMessage
from . import tuyalocalapi
from .robovac import ModelNotSupportedException, RoboVac
from .tuyalocalapi import InvalidKey, TuyaException
from .vacuums.base import RoboVacEntityFeature, RobovacCommand

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=REFRESH_RATE)
UPDATE_RETRIES = 4
WARMUP_ATTEMPTS = 5
WARMUP_DELAY = 1.5

ATTR_ERROR = "error"
ATTR_CLEANING_AREA = "cleaning_area"
ATTR_CLEANING_TIME = "cleaning_time"
ATTR_AUTO_RETURN = "auto_return"
ATTR_DO_NOT_DISTURB = "do_not_disturb"
ATTR_BOOST_IQ = "boost_iq"
ATTR_CONSUMABLES = "consumables"
ATTR_MODE = "mode"
ATTR_STATE_RESTORED = "state_restored"

MODE_MAPPING = {
    "AggO": "Resume",
    "AggP": "Stop return to dock",
    "BBoCCAE=": "Start auto",
    "AggN": "Pause",
    "AggG": "Stop / Go to charge",
    "AA==": "Standby",
}

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
START_CONFIRM_TIMEOUT = 4.0

ERROR_MAPPING = {
    "DAiI6suO9dXszgFSAA==": "no_error",
    "FAjwudWorOPszgEaAqURUgQSAqUR": "Sidebrush stuck",
    "FAj+nMu7zuPszgEaAtg2UgQSAtg2": "Robot stuck",
    "DAjtzbfps+XszgFSAA==": "no_error",
    "DAiom9rd6eTszgFSAA==": "no_error",
    "DAia8JTV5OPszgFSAA==": "no_error",
    "DAj489bWsePszgFSAA==": "no_error",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Robovac entities from a config entry."""
    entities: list[RoboVacEntity] = []

    for item in config_entry.data[CONF_VACS].values():
        entity = RoboVacEntity(item)
        hass.data[DOMAIN][CONF_VACS][item[CONF_ID]] = entity
        entities.append(entity)

    async_add_entities(entities)


# Raw DPS values exposed as extra attributes when the model advertises the feature.
PASSTHROUGH_ATTRIBUTES = (
    (RoboVacEntityFeature.CLEANING_AREA, RobovacCommand.CLEANING_AREA, ATTR_CLEANING_AREA),
    (RoboVacEntityFeature.CLEANING_TIME, RobovacCommand.CLEANING_TIME, ATTR_CLEANING_TIME),
    (RoboVacEntityFeature.AUTO_RETURN, RobovacCommand.AUTO_RETURN, ATTR_AUTO_RETURN),
    (RoboVacEntityFeature.DO_NOT_DISTURB, RobovacCommand.DO_NOT_DISTURB, ATTR_DO_NOT_DISTURB),
    (RoboVacEntityFeature.BOOST_IQ, RobovacCommand.BOOST_IQ, ATTR_BOOST_IQ),
)

NO_ERROR_CODES = (0, "no_error", None)


class RoboVacEntity(StateVacuumEntity, RestoreEntity):
    """Eufy Robovac L60 Vacuum entity."""

    _attr_should_poll = True

    def __init__(self, item: dict) -> None:
        """Initialize Eufy Robovac L60."""
        super().__init__()

        self._attr_name = item[CONF_NAME]
        self._attr_unique_id = item[CONF_ID]
        # Unavailable until the first good update (warm-up or poll).
        self._attr_available = False
        self._unavailable_logged = False
        self._warmup_task: asyncio.Task | None = None
        # Last activity from before an HA restart; display only, see activity.
        self._restored_activity: VacuumActivity | None = None
        self.ip_address: str | None = item[CONF_IP_ADDRESS]

        self._battery_level_cache: int | None = None
        self.update_failures = 0
        self.error_code: str | None = None
        self.tuya_state: str | None = None
        self.tuyastatus: dict[str, Any] | None = None
        self._mode: str | None = None
        self._consumables: Any = None
        self._passthrough: dict[str, Any] = {}
        self._refresh_task: asyncio.Task | None = None
        self._start_task: asyncio.Task | None = None
        self._cleaning = asyncio.Event()

        model_code = item[CONF_MODEL] or ""
        try:
            self.vacuum: RoboVac | None = RoboVac(
                device_id=self.unique_id,
                host=self.ip_address,
                local_key=item[CONF_ACCESS_TOKEN],
                timeout=TIMEOUT,
                ping_interval=PING_RATE,
                model_code=model_code[:5],
                update_entity_state=self.pushed_update_handler,
            )
        except ModelNotSupportedException:
            self.error_code = "UNSUPPORTED_MODEL"
            self.vacuum = None
        except InvalidKey:
            self.error_code = "INVALID_KEY"
            self.vacuum = None

        if self.vacuum is not None:
            self._robovac_features = self.vacuum.getRoboVacFeatures()
            self.fan_speed_map = {
                friendly_text(speed): speed for speed in self.vacuum.getFanSpeeds()
            }
            self._tuya_command_codes = self.vacuum.getCommandCodes()
            self._attr_supported_features = self._build_supported_features()
        else:
            self._robovac_features = 0
            self.fan_speed_map = {}
            self._tuya_command_codes = {}
            self._attr_supported_features = VacuumEntityFeature.STATE
        self._attr_fan_speed_list = list(self.fan_speed_map)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])},
            name=item[CONF_NAME],
            manufacturer="Eufy",
            model=item[CONF_DESCRIPTION],
            connections=[(CONNECTION_NETWORK_MAC, item[CONF_MAC])],
        )

    def _build_supported_features(self) -> VacuumEntityFeature:
        """Build HA vacuum features from the model's supported commands."""
        supported_commands = set(self.vacuum.getSupportedCommands())
        features = (
            VacuumEntityFeature.STATE
            | VacuumEntityFeature.START
            | VacuumEntityFeature.RETURN_HOME
            | VacuumEntityFeature.SEND_COMMAND
        )
        if RobovacCommand.FAN_SPEED in supported_commands:
            features |= VacuumEntityFeature.FAN_SPEED
        if RobovacCommand.LOCATE in supported_commands:
            features |= VacuumEntityFeature.LOCATE
        if RobovacCommand.MODE in supported_commands:
            features |= VacuumEntityFeature.PAUSE | VacuumEntityFeature.CLEAN_SPOT
        return features

    def _supports(self, feature: RoboVacEntityFeature) -> bool:
        return bool(self._robovac_features & feature)

    @property
    def activity(self) -> VacuumActivity:
        """Return the vacuum activity, or the restored one until the device reports."""
        if self.tuya_state is None and self._restored_activity is not None:
            return self._restored_activity
        return self._live_activity()

    def _live_activity(self) -> VacuumActivity:
        # Device-reported only. Command logic uses this, never the restored
        # value, so an unknown state still escalates in _async_start_sequence.
        if self.tuya_state is None:
            return VacuumActivity.IDLE
        if self.error_code not in NO_ERROR_CODES:
            return VacuumActivity.ERROR
        if self.tuya_state in ("Charging", "Completed"):
            return VacuumActivity.DOCKED
        if self.tuya_state == "Recharge":
            return VacuumActivity.RETURNING
        if self.tuya_state in ("Sleeping", "Standby"):
            return VacuumActivity.IDLE
        if self.tuya_state in PAUSED_STATES:
            return VacuumActivity.PAUSED
        return VacuumActivity.CLEANING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device-specific attributes."""
        data: dict[str, Any] = {}

        if self.error_code not in NO_ERROR_CODES:
            data[ATTR_ERROR] = getErrorMessage(self.error_code)

        for feature, _, attr in PASSTHROUGH_ATTRIBUTES:
            value = self._passthrough.get(attr)
            if value and self._supports(feature):
                data[attr] = value

        if self._consumables and self._supports(RoboVacEntityFeature.CONSUMABLES):
            data[ATTR_CONSUMABLES] = self._consumables

        if self._mode:
            data[ATTR_MODE] = self._mode

        if self.tuya_state is None and self._restored_activity is not None:
            data[ATTR_STATE_RESTORED] = True

        return data

    async def async_added_to_hass(self):
        """Restore the last state, then warm up in the background."""
        await super().async_added_to_hass()
        await self._async_restore_activity()

        if self.vacuum is None:
            return

        if not self.ip_address:
            self.error_code = "IP_ADDRESS"
            return

        self._warmup_task = self.hass.async_create_background_task(
            self._async_warm_up(), name=f"robovac warm-up {self.unique_id}"
        )

    async def _async_restore_activity(self) -> None:
        last = await self.async_get_last_state()
        if last is None or self.tuya_state is not None:
            return
        try:
            self._restored_activity = VacuumActivity(last.state)
        except ValueError:
            return  # unavailable / unknown: nothing to show
        _LOGGER.debug(
            "Restored %s activity %s until the device reports",
            self.unique_id,
            self._restored_activity,
        )

    async def _async_warm_up(self) -> None:
        """Poll a few times so the entity comes up promptly on restart."""
        for attempt in range(WARMUP_ATTEMPTS):
            if self.available:
                return  # a regular poll got there first
            try:
                await self.async_update_vacuum()
            except Exception as err:
                _LOGGER.debug(
                    "Startup refresh attempt %s failed for %s: %s",
                    attempt + 1,
                    self.unique_id,
                    err,
                )
            else:
                if self.tuyastatus is not None:
                    self._mark_available()
                    self.async_write_ha_state()
                    return
            await asyncio.sleep(WARMUP_DELAY)

        self._mark_unavailable("no response during startup")
        self.async_write_ha_state()

    def _mark_available(self) -> None:
        self.update_failures = 0
        self._attr_available = True
        if self._unavailable_logged:
            _LOGGER.info("Vacuum %s is available again", self.unique_id)
            self._unavailable_logged = False

    def _mark_unavailable(self, reason: Any) -> None:
        self._attr_available = False
        if not self._unavailable_logged:
            _LOGGER.warning("Vacuum %s is unavailable: %s", self.unique_id, reason)
            self._unavailable_logged = True

    async def async_update(self):
        """Synchronise state from the vacuum."""
        try:
            await self.async_update_vacuum()
        except TuyaException as err:
            self.update_failures += 1
            _LOGGER.debug(
                "Update timeout/error for %s. Failure count: %s. Reason: %s",
                self.unique_id,
                self.update_failures,
                err,
            )
            if self.update_failures >= UPDATE_RETRIES:
                self.error_code = "CONNECTION_FAILED"
                self._mark_unavailable(err)
            return

        if self.tuyastatus is None:
            _LOGGER.debug(
                "Vacuum %s returned no DPS yet; keeping previous state",
                self.unique_id,
            )
            return

        self._mark_available()

    async def async_update_vacuum(self):
        """Fetch latest state from the vacuum."""
        if self.vacuum is None:
            return
        if not self.ip_address:
            self.error_code = "IP_ADDRESS"
            return

        await self.vacuum.async_get()
        self.update_entity_values()

    async def async_forced_update(self):
        """Force immediate update and write state."""
        await self.async_update_vacuum()
        self.async_write_ha_state()

    async def pushed_update_handler(self):
        """Handle push update from the library."""
        self.update_entity_values()
        self.async_write_ha_state()

    def _dps_value(self, command: RobovacCommand, default: Any = None) -> Any:
        return self.tuyastatus.get(self._tuya_command_codes.get(command), default)

    def update_entity_values(self) -> None:
        """Update cached entity values from latest DPS payload."""
        if self.vacuum is None:
            return

        dps = self.vacuum._dps
        if not dps:
            _LOGGER.debug(
                "No DPS datapoints available yet for %s; skipping state refresh",
                self.unique_id,
            )
            return

        self.tuyastatus = dps
        if tuyalocalapi.VERBOSE:
            _LOGGER.debug("tuyastatus %s", dps)

        try:
            raw_batt = self._dps_value(RobovacCommand.BATTERY)
            self._battery_level_cache = int(raw_batt) if raw_batt is not None else None
        except (TypeError, ValueError):
            self._battery_level_cache = None

        self.tuya_state = STATUS_MAPPING.get(
            TUYA_STATUS_MAPPING.get(self._dps_value(RobovacCommand.STATUS))
        )
        self.error_code = ERROR_MAPPING.get(
            self._dps_value(RobovacCommand.ERROR), "no_error"
        )

        raw_mode = self._dps_value(RobovacCommand.MODE)
        self._mode = MODE_MAPPING.get(raw_mode, raw_mode)

        raw_fan = self._dps_value(RobovacCommand.FAN_SPEED, "")
        self._attr_fan_speed = friendly_text(raw_fan) if raw_fan else None

        for feature, command, attr in PASSTHROUGH_ATTRIBUTES:
            if self._supports(feature):
                self._passthrough[attr] = self._dps_value(command)

        if self._supports(RoboVacEntityFeature.CONSUMABLES):
            self._update_consumables(self._dps_value(RobovacCommand.CONSUMABLES))

        if self.tuya_state is not None:
            self._restored_activity = None

        self._update_cleaning_event()

        _LOGGER.debug(
            "Decoded %s: state=%s error=%s mode=%s fan=%s battery=%s",
            self.unique_id,
            self.tuya_state,
            self.error_code,
            self._mode,
            self._attr_fan_speed,
            self._battery_level_cache,
        )

    def _update_consumables(self, raw: Any) -> None:
        if not raw:
            return
        try:
            consumables = json.loads(base64.b64decode(raw).decode("ascii"))
            _LOGGER.debug("Consumables decoded value is: %s", consumables)
            if isinstance(consumables, dict) and "duration" in consumables.get(
                "consumable", {}
            ):
                self._consumables = consumables["consumable"]["duration"]
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Failed to decode consumables for %s: %s", self.unique_id, err)

    def _update_cleaning_event(self) -> None:
        if self._live_activity() == VacuumActivity.CLEANING:
            self._cleaning.set()
        else:
            self._cleaning.clear()

    def _schedule_refresh(self) -> None:
        # One refresh per command burst: a pending refresh covers later writes,
        # and the L60 pushes its status changes anyway.
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.create_task(self._async_refresh_after_command())

    def _cancel_start(self) -> None:
        task, self._start_task = self._start_task, None
        if task is not None and not task.done() and task is not asyncio.current_task():
            _LOGGER.debug("Cancelling start sequence for %s", self.unique_id)
            task.cancel()

    async def _async_refresh_after_command(self) -> None:
        try:
            await self.async_forced_update()
        except TuyaException as err:
            _LOGGER.debug("Refresh after command failed for %s: %s", self.unique_id, err)

    async def _async_send_dps(self, *dps_updates: dict[str, Any]) -> None:
        """Queue one or more DPS writes, then refresh state once."""
        if self.vacuum is None:
            return
        for dps in dps_updates:
            await self.vacuum.async_set(dps)
        self._schedule_refresh()

    async def _async_set_mode(self, value: str) -> None:
        if self.vacuum is None:
            return
        # Any mode command from outside the start sequence supersedes it.
        if asyncio.current_task() is not self._start_task:
            self._cancel_start()
        await self._async_send_dps({self._tuya_command_codes[RobovacCommand.MODE]: value})

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        _LOGGER.debug("Locate pressed")
        if self.vacuum is None:
            return
        code = self._tuya_command_codes[RobovacCommand.LOCATE]
        await self._async_send_dps({code: not (self.tuyastatus and self.tuyastatus.get(code))})

    async def async_return_to_base(self, **kwargs):
        """Return to dock."""
        _LOGGER.debug("Return home pressed")
        await self._async_set_mode("AggG")

    async def async_start(self, **kwargs):
        """Start cleaning, resuming a paused task or cancelling a return to dock first."""
        # The L60 acks but ignores START_AUTO_CLEAN ("BBoCCAE=") while paused
        # (needs RESUME_TASK "AggO") or returning to dock (needs STOP_GOHOME
        # "AggP" first). Its GET reply has no status DPS, so after an HA restart
        # the state can be unknown: then escalate until it reports cleaning.
        # Runs in the background so the service call returns at once; any other
        # mode command cancels it (_async_set_mode).
        if self._start_task is not None and not self._start_task.done():
            _LOGGER.debug("Start already in progress for %s", self.unique_id)
            return
        self._start_task = asyncio.create_task(self._async_start_sequence())

    async def _async_wait_until_cleaning(self, timeout: float = START_CONFIRM_TIMEOUT) -> bool:
        try:
            await asyncio.wait_for(self._cleaning.wait(), timeout)
        except TimeoutError:
            return False
        return self._live_activity() == VacuumActivity.CLEANING

    async def _async_start_sequence(self) -> None:
        # Each fallback runs only if the current state (None = unknown) allows it.
        if self.tuya_state not in (*PAUSED_STATES, "Recharge"):
            await self._async_set_mode("BBoCCAE=")
            if await self._async_wait_until_cleaning():
                return
        if self.tuya_state is None or self.tuya_state in PAUSED_STATES:
            await self._async_set_mode("AggO")
            if await self._async_wait_until_cleaning():
                return
        if self.tuya_state in (None, "Recharge"):
            await self._async_set_mode("AggP")
            await asyncio.sleep(1)
            await self._async_set_mode("BBoCCAE=")
            if await self._async_wait_until_cleaning():
                return
        _LOGGER.warning(
            "%s did not start cleaning (state %s)", self.unique_id, self.tuya_state
        )

    async def async_pause(self, **kwargs):
        """Pause cleaning."""
        await self._async_set_mode("AggN")

    async def async_stop(self, **kwargs):
        """Stop cleaning."""
        await self.async_return_to_base()

    async def async_clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        _LOGGER.debug("Spot clean pressed")
        await self._async_set_mode("Spot")

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set fan speed."""
        if fan_speed not in self.fan_speed_map:
            _LOGGER.debug("Unknown fan speed requested: %s", fan_speed)
            return
        await self._async_send_dps(
            {self._tuya_command_codes[RobovacCommand.FAN_SPEED]: self.fan_speed_map[fan_speed]}
        )

    async def async_send_command(
        self,
        command: str,
        params: dict | list | None = None,
        **kwargs,
    ) -> None:
        """Send a command to a vacuum cleaner."""
        _LOGGER.debug("Send command %s pressed", command)
        params = params if isinstance(params, dict) else {}

        if command in ("edgeClean", "smallRoomClean"):
            feature = (
                RoboVacEntityFeature.EDGE
                if command == "edgeClean"
                else RoboVacEntityFeature.SMALL_ROOM
            )
            if not self._supports(feature):
                _LOGGER.debug(
                    "%s does not support %s; ignoring send_command %s",
                    self.unique_id,
                    feature.name,
                    command,
                )
                return
            await self._async_set_mode("Edge" if command == "edgeClean" else "SmallRoom")
            return
        elif command == "autoClean":
            await self._async_set_mode("BBoCCAE=")
            return
        elif command in ("autoReturn", "doNotDisturb", "boostIQ"):
            feature, robovac_command, attr = {
                "autoReturn": (
                    RoboVacEntityFeature.AUTO_RETURN,
                    RobovacCommand.AUTO_RETURN,
                    ATTR_AUTO_RETURN,
                ),
                "doNotDisturb": (
                    RoboVacEntityFeature.DO_NOT_DISTURB,
                    RobovacCommand.DO_NOT_DISTURB,
                    ATTR_DO_NOT_DISTURB,
                ),
                "boostIQ": (
                    RoboVacEntityFeature.BOOST_IQ,
                    RobovacCommand.BOOST_IQ,
                    ATTR_BOOST_IQ,
                ),
            }[command]
            code = self._tuya_command_codes.get(robovac_command)
            if not self._supports(feature) or code is None:
                _LOGGER.debug(
                    "%s does not support %s; ignoring send_command %s",
                    self.unique_id,
                    feature.name,
                    command,
                )
                return
            updates = [{code: not self._passthrough.get(attr)}]
        elif command == "roomClean":
            if not self._supports(RoboVacEntityFeature.ROOM):
                _LOGGER.debug(
                    "%s does not support room-select cleaning; ignoring send_command roomClean",
                    self.unique_id,
                )
                return
            _LOGGER.warning(
                "roomClean has no known DPS code for any supported model yet; ignoring send_command roomClean"
            )
            return
        else:
            if not str(command).isdigit():
                _LOGGER.debug(
                    "send_command %s is not a known numeric DPS code for %s; "
                    "writing %r to it anyway",
                    command,
                    self.unique_id,
                    params.get("value", ""),
                )
            if str(command) == self._tuya_command_codes.get(RobovacCommand.MODE):
                self._cancel_start()
            updates = [{command: params.get("value", "")}]

        await self._async_send_dps(*updates)

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed."""
        if self._warmup_task is not None:
            self._warmup_task.cancel()
        self._cancel_start()
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        if self.vacuum is not None:
            await self.vacuum.async_disable()


def friendly_text(input_value: str) -> str:
    """Convert string to friendly text."""
    if not input_value:
        return ""
    return " ".join(
        word[0].upper() + word[1:] for word in input_value.replace("_", " ").split()
    )
