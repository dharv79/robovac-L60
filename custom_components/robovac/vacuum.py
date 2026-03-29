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
import ast
import base64
import json
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.components.vacuum import StateVacuumEntity, VacuumActivity
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

from .const import CONF_VACS, DOMAIN, PING_RATE, REFRESH_RATE, TIMEOUT
from .errors import getErrorMessage
from .robovac import ModelNotSupportedException, RoboVac
from .tuyalocalapi import TuyaException
from .vacuums.base import RoboVacEntityFeature, RobovacCommand

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=REFRESH_RATE)
UPDATE_RETRIES = 3

ATTR_ERROR = "error"
ATTR_CLEANING_AREA = "cleaning_area"
ATTR_CLEANING_TIME = "cleaning_time"
ATTR_AUTO_RETURN = "auto_return"
ATTR_DO_NOT_DISTURB = "do_not_disturb"
ATTR_BOOST_IQ = "boost_iq"
ATTR_CONSUMABLES = "consumables"
ATTR_MODE = "mode"

MODE_MAPPING = {
    "AggO": "Auto cleaning",
    "BBoCCAE=": "Start auto",
    "AggN": "Pause",
    "AggG": "Stop / Go to charge",
    "AA==": "Standby",
}

EMPTY_MAPPING = {
    "BBICGAE=": "Empty dust",
    "BBICIAE=": "Wash mop",
    "BBICEAE=": "Dry mop",
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
    vacuums = config_entry.data[CONF_VACS]
    entities: list[RoboVacEntity] = []

    for item in vacuums.values():
        entity = RoboVacEntity(item)
        hass.data[DOMAIN][CONF_VACS][item[CONF_ID]] = entity
        entities.append(entity)

    async_add_entities(entities)


class RoboVacEntity(StateVacuumEntity):
    """Eufy Robovac L60 Vacuum entity."""

    _attr_should_poll = True
    _attr_access_token: str | None = None
    _attr_ip_address: str | None = None
    _attr_model_code: str | None = None
    _attr_cleaning_area: str | None = None
    _attr_cleaning_time: str | None = None
    _attr_auto_return: str | None = None
    _attr_do_not_disturb: str | None = None
    _attr_boost_iq: str | None = None
    _attr_consumables: str | None = None
    _attr_mode: str | None = None
    _attr_robovac_supported: Any = None

    def __init__(self, item: dict) -> None:
        """Initialize Eufy Robovac L60."""
        super().__init__()

        self._battery_level_cache: int | None = None
        self._attr_name = item[CONF_NAME]
        self._attr_unique_id = item[CONF_ID]
        self._attr_model_code = item[CONF_MODEL]
        self._attr_ip_address = item[CONF_IP_ADDRESS]
        self._attr_access_token = item[CONF_ACCESS_TOKEN]

        self.update_failures = 0
        self._attr_available = True
        self.error_code: str | None = None

        self.tuya_state: str | None = None
        self.tuyastatus: dict[str, Any] | None = None

        try:
            self.vacuum = RoboVac(
                device_id=self.unique_id,
                host=self.ip_address,
                local_key=self.access_token,
                timeout=TIMEOUT,
                ping_interval=PING_RATE,
                model_code=self.model_code[0:5] if self.model_code else "",
                update_entity_state=self.pushed_update_handler,
            )
        except ModelNotSupportedException:
            self.error_code = "UNSUPPORTED_MODEL"
            self.vacuum = None

        if self.error_code != "UNSUPPORTED_MODEL" and self.vacuum is not None:
            self._attr_supported_features = self.vacuum.getHomeAssistantFeatures()
            self._attr_robovac_supported = self.vacuum.getRoboVacFeatures()

            fan_speeds = self.vacuum.getFanSpeeds()
            self.fan_speed_map: dict[str, str] = {}
            for speed in fan_speeds:
                self.fan_speed_map[friendly_text(speed)] = speed
            self._attr_fan_speed_list = list(self.fan_speed_map.keys())

            self._tuya_command_codes = self.vacuum.getCommandCodes()
        else:
            self._attr_supported_features = 0
            self._attr_robovac_supported = 0
            self.fan_speed_map = {}
            self._attr_fan_speed_list = []
            self._tuya_command_codes = {}

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])},
            name=item[CONF_NAME],
            manufacturer="Eufy",
            model=item[CONF_DESCRIPTION],
            connections=[(CONNECTION_NETWORK_MAC, item[CONF_MAC])],
        )

    @property
    def robovac_supported(self) -> Any:
        return self._attr_robovac_supported

    @property
    def mode(self) -> str | None:
        return self._attr_mode

    @property
    def consumables(self) -> str | None:
        return self._attr_consumables

    @property
    def cleaning_area(self) -> str | None:
        return self._attr_cleaning_area

    @property
    def cleaning_time(self) -> str | None:
        return self._attr_cleaning_time

    @property
    def auto_return(self) -> str | None:
        return self._attr_auto_return

    @property
    def do_not_disturb(self) -> str | None:
        return self._attr_do_not_disturb

    @property
    def boost_iq(self) -> str | None:
        return self._attr_boost_iq

    @property
    def model_code(self) -> str | None:
        return self._attr_model_code

    @property
    def access_token(self) -> str | None:
        return self._attr_access_token

    @property
    def ip_address(self) -> str | None:
        return self._attr_ip_address

    @property
    def activity(self) -> VacuumActivity:
        """Return the vacuum activity."""
        if self.tuya_state is None:
            return VacuumActivity.IDLE

        if self.error_code and self.error_code not in [0, "no_error", None]:
            return VacuumActivity.ERROR

        if self.tuya_state in ("Charging", "Completed"):
            return VacuumActivity.DOCKED
        if self.tuya_state == "Recharge":
            return VacuumActivity.RETURNING
        if self.tuya_state in ("Sleeping", "Standby"):
            return VacuumActivity.IDLE
        if self.tuya_state == "Cleaning paused":
            return VacuumActivity.PAUSED

        return VacuumActivity.CLEANING

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device-specific attributes."""
        data: dict[str, Any] = {}

        if self.error_code is not None and self.error_code not in [0, "no_error"]:
            data[ATTR_ERROR] = getErrorMessage(self.error_code)

        if (
            self.robovac_supported & RoboVacEntityFeature.CLEANING_AREA
            and self.cleaning_area
        ):
            data[ATTR_CLEANING_AREA] = self.cleaning_area

        if (
            self.robovac_supported & RoboVacEntityFeature.CLEANING_TIME
            and self.cleaning_time
        ):
            data[ATTR_CLEANING_TIME] = self.cleaning_time

        if (
            self.robovac_supported & RoboVacEntityFeature.AUTO_RETURN
            and self.auto_return
        ):
            data[ATTR_AUTO_RETURN] = self.auto_return

        if (
            self.robovac_supported & RoboVacEntityFeature.DO_NOT_DISTURB
            and self.do_not_disturb
        ):
            data[ATTR_DO_NOT_DISTURB] = self.do_not_disturb

        if self.robovac_supported & RoboVacEntityFeature.BOOST_IQ and self.boost_iq:
            data[ATTR_BOOST_IQ] = self.boost_iq

        if (
            self.robovac_supported & RoboVacEntityFeature.CONSUMABLES
            and self.consumables
        ):
            data[ATTR_CONSUMABLES] = self.consumables

        if self.mode:
            data[ATTR_MODE] = self.mode

        return data

    async def async_added_to_hass(self):
        """Warm up a few polls so the entity comes up cleanly on restart."""
        if self.error_code == "UNSUPPORTED_MODEL":
            self._attr_available = False
            return

        if not self.ip_address:
            self.error_code = "IP_ADDRESS"
            self._attr_available = False
            return

        for attempt in range(5):
            try:
                await self.async_forced_update()
                self.update_failures = 0
                self._attr_available = True
                return
            except Exception as err:
                _LOGGER.debug(
                    "Startup refresh attempt %s failed for %s: %s",
                    attempt + 1,
                    self.unique_id,
                    err,
                )
                await asyncio.sleep(1.5)

        self._attr_available = False

    async def async_update(self):
        """Synchronise state from the vacuum."""
        try:
            await self.async_update_vacuum()

            if self.tuyastatus is None:
                _LOGGER.debug(
                    "Vacuum %s returned no DPS yet; keeping previous state",
                    self.unique_id,
                )
                return

            self.update_failures = 0
            self._attr_available = True

        except TuyaException as err:
            self.update_failures += 1
            _LOGGER.warning(
                "Update errored for %s. Failure count: %s. Reason: %s",
                self.unique_id,
                self.update_failures,
                err,
            )
            if self.update_failures >= UPDATE_RETRIES:
                self.error_code = "CONNECTION_FAILED"
                self._attr_available = False

    async def async_update_vacuum(self):
        """Fetch latest state from the vacuum."""
        if self.error_code == "UNSUPPORTED_MODEL":
            return
        if not self.ip_address:
            self.error_code = "IP_ADDRESS"
            return
        if self.vacuum is None:
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

    def update_entity_values(self) -> None:
        """Update cached entity values from latest DPS payload."""
        if self.vacuum is None:
            return

        dps = getattr(self.vacuum, "_dps", None)

        if not isinstance(dps, dict) or not dps:
            _LOGGER.debug(
                "No DPS datapoints available yet for %s; skipping state refresh",
                self.unique_id,
            )
            return

        self.tuyastatus = dps
        _LOGGER.debug("tuyastatus %s", self.tuyastatus)

        raw_batt = self.tuyastatus.get(
            self._tuya_command_codes.get(RobovacCommand.BATTERY)
        )
        try:
            self._battery_level_cache = int(raw_batt) if raw_batt is not None else None
        except (TypeError, ValueError):
            self._battery_level_cache = None
        _LOGGER.debug("_battery_level_cache %s", self._battery_level_cache)

        raw_status = self.tuyastatus.get(
            self._tuya_command_codes.get(RobovacCommand.STATUS)
        )
        self.tuya_state = STATUS_MAPPING.get(
            TUYA_STATUS_MAPPING.get(raw_status),
            None,
        )
        _LOGGER.debug("tuya_state %s", self.tuya_state)

        raw_error = self.tuyastatus.get(
            self._tuya_command_codes.get(RobovacCommand.ERROR)
        )
        self.error_code = ERROR_MAPPING.get(raw_error, "no_error")
        _LOGGER.debug("error_code %s", self.error_code)

        raw_mode = self.tuyastatus.get(
            self._tuya_command_codes.get(RobovacCommand.MODE)
        )
        self._attr_mode = MODE_MAPPING.get(raw_mode, raw_mode)
        _LOGGER.debug("_attr_mode %s", self._attr_mode)

        raw_fan = self.tuyastatus.get(
            self._tuya_command_codes.get(RobovacCommand.FAN_SPEED),
            "",
        )
        self._attr_fan_speed = friendly_text(raw_fan) if raw_fan else None
        _LOGGER.debug("_attr_fan_speed %s", self._attr_fan_speed)

        if self.robovac_supported & RoboVacEntityFeature.CLEANING_AREA:
            self._attr_cleaning_area = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.CLEANING_AREA)
            )

        if self.robovac_supported & RoboVacEntityFeature.CLEANING_TIME:
            self._attr_cleaning_time = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.CLEANING_TIME)
            )

        if self.robovac_supported & RoboVacEntityFeature.AUTO_RETURN:
            self._attr_auto_return = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.AUTO_RETURN)
            )

        if self.robovac_supported & RoboVacEntityFeature.DO_NOT_DISTURB:
            self._attr_do_not_disturb = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.DO_NOT_DISTURB)
            )

        if self.robovac_supported & RoboVacEntityFeature.BOOST_IQ:
            self._attr_boost_iq = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.BOOST_IQ)
            )

        if self.robovac_supported & RoboVacEntityFeature.CONSUMABLES:
            raw = self.tuyastatus.get(
                self._tuya_command_codes.get(RobovacCommand.CONSUMABLES)
            )
            if raw:
                try:
                    consumables = ast.literal_eval(
                        base64.b64decode(raw).decode("ascii")
                    )
                    _LOGGER.debug("Consumables decoded value is: %s", consumables)
                    if (
                        isinstance(consumables, dict)
                        and "consumable" in consumables
                        and "duration" in consumables["consumable"]
                    ):
                        self._attr_consumables = consumables["consumable"]["duration"]
                except (ValueError, SyntaxError, TypeError) as err:
                    _LOGGER.debug(
                        "Failed to decode consumables for %s: %s",
                        self.unique_id,
                        err,
                    )

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        _LOGGER.info("Locate pressed")
        if self.vacuum is None:
            return

        code = self._tuya_command_codes[RobovacCommand.LOCATE]
        if self.tuyastatus and self.tuyastatus.get(code):
            await self.vacuum.async_set({code: False})
        else:
            await self.vacuum.async_set({code: True})
        asyncio.create_task(self.async_forced_update())

    async def async_return_to_base(self, **kwargs):
        """Return to dock."""
        _LOGGER.info("Return home pressed")
        if self.vacuum is None:
            return

        await self.vacuum.async_set(
            {self._tuya_command_codes[RobovacCommand.MODE]: "AggG"}
        )
        asyncio.create_task(self.async_forced_update())

    async def async_start(self, **kwargs):
        """Start cleaning."""
        if self.vacuum is None:
            return

        await self.vacuum.async_set(
            {self._tuya_command_codes[RobovacCommand.MODE]: "BBoCCAE="}
        )
        asyncio.create_task(self.async_forced_update())

    async def async_pause(self, **kwargs):
        """Pause cleaning."""
        if self.vacuum is None:
            return

        await self.vacuum.async_set(
            {self._tuya_command_codes[RobovacCommand.MODE]: "AggN"}
        )
        asyncio.create_task(self.async_forced_update())

    async def async_stop(self, **kwargs):
        """Stop cleaning."""
        await self.async_return_to_base()
        asyncio.create_task(self.async_forced_update())

    async def async_clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        _LOGGER.info("Spot clean pressed")
        if self.vacuum is None:
            return

        await self.vacuum.async_set(
            {self._tuya_command_codes[RobovacCommand.MODE]: "Spot"}
        )
        asyncio.create_task(self.async_forced_update())

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set fan speed."""
        _LOGGER.info("Fan speed selected")
        if self.vacuum is None:
            return
        if fan_speed not in self.fan_speed_map:
            _LOGGER.debug("Unknown fan speed requested: %s", fan_speed)
            return

        await self.vacuum.async_set(
            {
                self._tuya_command_codes[RobovacCommand.FAN_SPEED]: self.fan_speed_map[
                    fan_speed
                ]
            }
        )
        asyncio.create_task(self.async_forced_update())

    async def async_send_command(
        self,
        command: str,
        params: dict | list | None = None,
        **kwargs,
    ) -> None:
        """Send a command to a vacuum cleaner."""
        _LOGGER.info("Send command %s pressed", command)
        if self.vacuum is None:
            return

        params = params or {}

        if command == "edgeClean":
            await self.vacuum.async_set({"5": "Edge"})
        elif command == "smallRoomClean":
            await self.vacuum.async_set({"5": "SmallRoom"})
        elif command == "autoClean":
            await self.vacuum.async_set({"152": "BBoCCAE="})
        elif command == "autoReturn":
            if self.auto_return:
                await self.vacuum.async_set({"135": False})
            else:
                await self.vacuum.async_set({"135": True})
        elif command == "doNotDisturb":
            if self.do_not_disturb:
                await self.vacuum.async_set({"139": "MEQ4MDAwMDAw"})
                await self.vacuum.async_set({"107": False})
            else:
                await self.vacuum.async_set({"139": "MTAwMDAwMDAw"})
                await self.vacuum.async_set({"107": True})
        elif command == "boostIQ":
            if self.boost_iq:
                await self.vacuum.async_set({"118": False})
            else:
                await self.vacuum.async_set({"118": True})
        elif command == "roomClean":
            room_ids = params.get("roomIds", [1])
            count = params.get("count", 1)
            clean_request = {"roomIds": room_ids, "cleanTimes": count}
            method_call = {
                "method": "selectRoomsClean",
                "data": clean_request,
                "timestamp": round(time.time() * 1000),
            }
            json_str = json.dumps(method_call, separators=(",", ":"))
            base64_str = base64.b64encode(json_str.encode("utf8")).decode("utf8")
            _LOGGER.info("roomClean call %s", json_str)
            await self.vacuum.async_set({"124": base64_str})
        else:
            value = params.get("value", "") if isinstance(params, dict) else ""
            await self.vacuum.async_set({command: value})

        asyncio.create_task(self.async_forced_update())

    async def async_will_remove_from_hass(self):
        """Clean up when entity is removed."""
        if self.error_code != "UNSUPPORTED_MODEL" and self.vacuum is not None:
            await self.vacuum.async_disable()


def friendly_text(input_value: str) -> str:
    """Convert string to friendly text."""
    if not input_value:
        return ""
    return " ".join(
        word[0].upper() + word[1:] for word in input_value.replace("_", " ").split()
    )