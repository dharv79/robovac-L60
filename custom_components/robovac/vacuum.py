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
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DESCRIPTION, CONF_ID, CONF_MAC, CONF_NAME
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    ATTR_AUTO_RETURN,
    ATTR_BOOST_IQ,
    ATTR_DO_NOT_DISTURB,
    EMPTY_DATA,
    NO_ERROR_CODES,
    PASSTHROUGH_ATTRIBUTES,
    PAUSED_STATES,
    RoboVacCoordinator,
    RoboVacData,
    live_activity,
)
from .errors import getErrorMessage
from .robovac import RoboVac
from .tuyalocalapi import TuyaException
from .vacuums.base import (
    ModeKey,
    RoboVacEntityFeature,
    RobovacCommand,
)

_LOGGER = logging.getLogger(__name__)

ATTR_ERROR = "error"
ATTR_CONSUMABLES = "consumables"
ATTR_MODE = "mode"
ATTR_STATE_RESTORED = "state_restored"

START_CONFIRM_TIMEOUT = 4.0
NEW_CLEAN_SETTLE_TIMEOUT = 4.0
SERVICE_START_NEW_CLEAN = "start_new_clean"
SERVICE_AUTO_CLEAN = "auto_clean"
SERVICE_GET_DPS = "get_dps"



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Robovac entities from a config entry."""
    async_add_entities(
        RoboVacEntity(coordinator) for coordinator in config_entry.runtime_data.values()
    )
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_START_NEW_CLEAN, None, "async_start_new_clean"
    )
    platform.async_register_entity_service(
        SERVICE_AUTO_CLEAN, None, "async_auto_clean"
    )
    platform.async_register_entity_service(
        SERVICE_GET_DPS,
        {vol.Optional("codes"): vol.All(cv.ensure_list, [vol.Coerce(str)])},
        "async_get_dps",
        supports_response=SupportsResponse.ONLY,
    )


class RoboVacEntity(CoordinatorEntity[RoboVacCoordinator], StateVacuumEntity, RestoreEntity):
    """Eufy Robovac L60 Vacuum entity."""

    # The vacuum is the device's main entity: its name is the device name.
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: RoboVacCoordinator) -> None:
        """Initialize Eufy Robovac L60."""
        super().__init__(coordinator)
        item = coordinator.item

        self._attr_unique_id = item[CONF_ID]
        # Last activity from before an HA restart; display only, see activity.
        self._restored_activity: VacuumActivity | None = None
        self._refresh_task: asyncio.Task | None = None
        self._start_task: asyncio.Task | None = None
        coordinator.cancel_start = self._cancel_start

        if coordinator.vacuum is not None:
            self._attr_supported_features = self._build_supported_features()
        else:
            self._attr_supported_features = VacuumEntityFeature.STATE
        self._attr_fan_speed_list = list(coordinator.fan_speed_map)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, item[CONF_ID])},
            name=item[CONF_NAME],
            manufacturer="Eufy",
            model=item[CONF_DESCRIPTION],
            connections=[(CONNECTION_NETWORK_MAC, item[CONF_MAC])],
        )

    @property
    def vacuum(self) -> RoboVac | None:
        return self.coordinator.vacuum

    @property
    def _state(self) -> RoboVacData:
        return self.coordinator.data or EMPTY_DATA

    @property
    def tuya_state(self) -> str | None:
        return self._state.status

    @property
    def error_code(self) -> str | None:
        return self.coordinator.error_code

    @property
    def available(self) -> bool:
        return self.coordinator.available

    @property
    def fan_speed(self) -> str | None:
        return self._state.fan_speed

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
        return self.coordinator.supports(feature)

    @property
    def activity(self) -> VacuumActivity:
        """Return the vacuum activity, or the restored one until the device reports."""
        if self.tuya_state is None and self._restored_activity is not None:
            return self._restored_activity
        return self._live_activity()

    def _live_activity(self) -> VacuumActivity:
        # Device-reported only. Command logic uses this, never the restored
        # value, so an unknown state still escalates in _async_start_sequence.
        return live_activity(self.tuya_state, self.error_code)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device-specific attributes."""
        data: dict[str, Any] = {}
        state = self._state

        if self.error_code not in NO_ERROR_CODES:
            data[ATTR_ERROR] = getErrorMessage(self.error_code)

        for feature, _, attr in PASSTHROUGH_ATTRIBUTES:
            value = state.passthrough.get(attr)
            if value and self._supports(feature):
                data[attr] = value

        if state.consumables and self._supports(RoboVacEntityFeature.CONSUMABLES):
            data[ATTR_CONSUMABLES] = state.consumables

        if state.mode:
            data[ATTR_MODE] = state.mode

        if self.tuya_state is None and self._restored_activity is not None:
            data[ATTR_STATE_RESTORED] = True

        return data

    async def async_added_to_hass(self):
        """Restore the last state; the coordinator warms up on its own."""
        await super().async_added_to_hass()
        await self._async_restore_activity()

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

    async def async_forced_update(self):
        """Force an immediate GET; the coordinator publishes the new state."""
        await self.coordinator.async_forced_refresh()

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
        await self._async_send_dps({self.coordinator.command_codes[RobovacCommand.MODE]: value})

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        _LOGGER.debug("Locate pressed")
        if self.vacuum is None:
            return
        code = self.coordinator.command_codes[RobovacCommand.LOCATE]
        await self._async_send_dps({code: not (self._state.dps.get(code))})

    async def async_return_to_base(self, **kwargs):
        """Return to dock."""
        _LOGGER.debug("Return home pressed")
        await self._async_set_mode(self.coordinator.mode_values[ModeKey.RETURN_HOME])

    async def async_start(self, **kwargs):
        """Start cleaning, resuming a paused task or cancelling a return to dock first."""
        # The L60 acks but ignores START_AUTO_CLEAN (start_auto) while paused
        # (needs RESUME_TASK, resume) or returning to dock (needs STOP_GOHOME,
        # stop_return, first). Its GET reply has no status DPS, so after an HA restart
        # the state can be unknown: then escalate until it reports cleaning.
        # Runs in the background so the service call returns at once; any other
        # mode command cancels it (_async_set_mode).
        if self._start_task is not None and not self._start_task.done():
            _LOGGER.debug("Start already in progress for %s", self.unique_id)
            return
        self._start_task = asyncio.create_task(self._async_start_sequence())

    async def _async_wait_until_cleaning(self, timeout: float = START_CONFIRM_TIMEOUT) -> bool:
        try:
            await asyncio.wait_for(self.coordinator.cleaning.wait(), timeout)
        except TimeoutError:
            return False
        return self._live_activity() == VacuumActivity.CLEANING

    async def _async_start_sequence(self) -> None:
        # Each fallback runs only if the current state (None = unknown) allows it.
        if self.tuya_state not in (*PAUSED_STATES, "Recharge"):
            await self._async_set_mode(self.coordinator.mode_values[ModeKey.START_AUTO])
            if await self._async_wait_until_cleaning():
                return
        if self.tuya_state is None or self.tuya_state in PAUSED_STATES:
            await self._async_set_mode(self.coordinator.mode_values[ModeKey.RESUME])
            if await self._async_wait_until_cleaning():
                return
        if self.tuya_state in (None, "Recharge"):
            await self._async_set_mode(self.coordinator.mode_values[ModeKey.STOP_RETURN])
            await asyncio.sleep(1)
            await self._async_set_mode(self.coordinator.mode_values[ModeKey.START_AUTO])
            if await self._async_wait_until_cleaning():
                return
        _LOGGER.warning(
            "%s did not start cleaning (state %s)", self.unique_id, self.tuya_state
        )

    async def async_get_dps(self, codes: list[str] | None = None) -> dict[str, Any]:
        """robovac.get_dps: force a GET and return the raw DPS, optionally filtered."""
        if self.vacuum is None:
            raise HomeAssistantError("This vacuum is not supported or not configured")
        try:
            await self.coordinator.async_forced_refresh()
        except TuyaException as err:
            raise HomeAssistantError(f"Could not read the vacuum: {err}") from err
        dps = {str(code): value for code, value in self.vacuum._dps.items()}
        if codes:
            dps = {code: dps[code] for code in codes if code in dps}
        return {"dps": dps}

    async def async_auto_clean(self) -> None:
        """robovac.auto_clean: send the model's start-auto mode directly."""
        await self._async_set_mode(self.coordinator.mode_values[ModeKey.START_AUTO])

    async def async_start_new_clean(self) -> None:
        """robovac.start_new_clean: drop a paused task and start a fresh clean."""
        if self.vacuum is None:
            return
        self._cancel_start()
        self._start_task = asyncio.create_task(self._async_new_clean_sequence())

    async def _async_new_clean_sequence(self) -> None:
        await self._async_set_mode(self.coordinator.mode_values[ModeKey.STOP_RETURN])
        # Wait for the old task to leave the paused state, then start afresh.
        try:
            async with asyncio.timeout(NEW_CLEAN_SETTLE_TIMEOUT):
                while self.tuya_state in PAUSED_STATES:
                    await asyncio.sleep(0.2)
        except TimeoutError:
            _LOGGER.debug("%s still paused after stop; starting anyway", self.unique_id)
        await self._async_set_mode(self.coordinator.mode_values[ModeKey.START_AUTO])
        if not await self._async_wait_until_cleaning():
            _LOGGER.warning(
                "%s did not start a new clean (state %s)", self.unique_id, self.tuya_state
            )

    async def async_pause(self, **kwargs):
        """Pause cleaning."""
        await self._async_set_mode(self.coordinator.mode_values[ModeKey.PAUSE])

    async def async_stop(self, **kwargs):
        """Stop cleaning."""
        await self.async_return_to_base()

    async def async_clean_spot(self, **kwargs):
        """Perform a spot clean-up."""
        _LOGGER.debug("Spot clean pressed")
        await self._async_set_mode("Spot")

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set fan speed."""
        if fan_speed not in self.coordinator.fan_speed_map:
            _LOGGER.debug("Unknown fan speed requested: %s", fan_speed)
            return
        await self._async_send_dps(
            {self.coordinator.command_codes[RobovacCommand.FAN_SPEED]: self.coordinator.fan_speed_map[fan_speed]}
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
            await self._async_set_mode(self.coordinator.mode_values[ModeKey.START_AUTO])
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
            code = self.coordinator.command_codes.get(robovac_command)
            if not self._supports(feature) or code is None:
                _LOGGER.debug(
                    "%s does not support %s; ignoring send_command %s",
                    self.unique_id,
                    feature.name,
                    command,
                )
                return
            current = self._state.passthrough.get(attr)
            if command == "doNotDisturb" and not isinstance(current, bool):
                # L60 DPS 157 holds a protobuf string, not a bool; a toggle
                # would write False to it. Ignored until Phase 15.
                _LOGGER.debug(
                    "%s: DND value %r is not boolean; ignoring send_command doNotDisturb",
                    self.unique_id,
                    current,
                )
                return
            updates = [{code: not current}]
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
            if str(command) == self.coordinator.command_codes.get(RobovacCommand.MODE):
                self._cancel_start()
            updates = [{command: params.get("value", "")}]

        await self._async_send_dps(*updates)


    async def async_will_remove_from_hass(self):
        """Cancel this entity's tasks; the coordinator owns the device."""
        self._cancel_start()
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()
