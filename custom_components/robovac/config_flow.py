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

"""Config flow for Eufy Robovac L60 integration."""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Optional

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_COUNTRY_CODE,
    CONF_DESCRIPTION,
    CONF_ID,
    CONF_IP_ADDRESS,
    CONF_MAC,
    CONF_MODEL,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_TIME_ZONE,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_AUTODISCOVERY, CONF_VACS, DOMAIN
from .countries import (
    get_phone_code_by_country_code,
    get_phone_code_by_region,
    get_region_by_country_code,
    get_region_by_phone_code,
)
from .eufywebapi import EufyLogon
from .tuyawebapi import TuyaAPISession

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    }
)


def get_eufy_vacuums(self_data: dict[str, Any]):
    """Login to Eufy and get the vacuum details."""
    eufy_session = EufyLogon(self_data[CONF_USERNAME], self_data[CONF_PASSWORD])

    response = eufy_session.get_user_info()
    if response.status_code != 200:
        raise CannotConnect

    user_response = response.json()
    if user_response.get("res_code") != 1:
        raise InvalidAuth

    response = eufy_session.get_device_info(
        user_response["user_info"]["request_host"],
        user_response["user_info"]["id"],
        user_response["access_token"],
    )
    device_response = response.json()

    response = eufy_session.get_user_settings(
        user_response["user_info"]["request_host"],
        user_response["user_info"]["id"],
        user_response["access_token"],
    )
    settings_response = response.json()

    self_data[CONF_CLIENT_ID] = user_response["user_info"]["id"]

    if (
        "tuya_home" in settings_response.get("setting", {}).get("home_setting", {})
        and "tuya_region_code"
        in settings_response["setting"]["home_setting"]["tuya_home"]
    ):
        self_data[CONF_REGION] = settings_response["setting"]["home_setting"][
            "tuya_home"
        ]["tuya_region_code"]
        if user_response["user_info"].get("phone_code"):
            self_data[CONF_COUNTRY_CODE] = user_response["user_info"]["phone_code"]
        else:
            self_data[CONF_COUNTRY_CODE] = get_phone_code_by_region(
                self_data[CONF_REGION]
            )
    elif user_response["user_info"].get("phone_code"):
        self_data[CONF_REGION] = get_region_by_phone_code(
            user_response["user_info"]["phone_code"]
        )
        self_data[CONF_COUNTRY_CODE] = user_response["user_info"]["phone_code"]
    elif user_response["user_info"].get("country"):
        self_data[CONF_REGION] = get_region_by_country_code(
            user_response["user_info"]["country"]
        )
        self_data[CONF_COUNTRY_CODE] = get_phone_code_by_country_code(
            user_response["user_info"]["country"]
        )
    else:
        self_data[CONF_REGION] = "EU"
        self_data[CONF_COUNTRY_CODE] = "44"

    self_data[CONF_TIME_ZONE] = user_response["user_info"]["timezone"]

    tuya_client = TuyaAPISession(
        username="eh-" + self_data[CONF_CLIENT_ID],
        region=self_data[CONF_REGION],
        timezone=self_data[CONF_TIME_ZONE],
        phone_code=self_data[CONF_COUNTRY_CODE],
    )

    items = device_response.get("devices", [])
    self_data[CONF_VACS] = {}

    for item in items:
        if item.get("product", {}).get("appliance") != "Cleaning":
            continue

        try:
            device = tuya_client.get_device(item["id"])
            _LOGGER.debug("Robovac schema: %s", device.get("schema"))

            vac_details = {
                CONF_ID: item["id"],
                CONF_MODEL: item["product"]["product_code"],
                CONF_NAME: item["alias_name"],
                CONF_DESCRIPTION: item["name"],
                CONF_MAC: item["wifi"]["mac"],
                CONF_IP_ADDRESS: "",
                CONF_AUTODISCOVERY: True,
                CONF_ACCESS_TOKEN: device["localKey"],
            }
            self_data[CONF_VACS][item["id"]] = vac_details

        except Exception as err:
            _LOGGER.debug(
                "Vacuum %s found on Eufy, but not on Tuya or failed to parse. "
                "Skipping. Error: %s",
                item.get("id"),
                err,
            )
            try:
                _LOGGER.debug("Skipped device payload: %s", json.dumps(item, indent=2))
            except Exception:
                pass

    return self_data


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    return await hass.async_add_executor_job(get_eufy_vacuums, data)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eufy Robovac L60."""

    data: Optional[dict[str, Any]]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        errors: dict[str, str] = {}

        try:
            unique_id = user_input[CONF_USERNAME]
            valid_data = await validate_input(self.hass, dict(user_input))
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception as err:
            _LOGGER.exception("Unexpected exception during config flow: %s", err)
            errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=unique_id, data=valid_data)

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self.selected_vacuum: str | None = None

    async def async_step_init(self, user_input=None):
        """Select the vacuum to edit."""
        errors = {}

        if user_input is not None:
            self.selected_vacuum = user_input["selected_vacuum"]
            return await self.async_step_edit()

        vacuums_config = self.config_entry.data.get(CONF_VACS, {})
        vacuum_list = {
            vacuum_id: vacuums_config[vacuum_id][CONF_NAME]
            for vacuum_id in vacuums_config
        }

        devices_schema = vol.Schema(
            {vol.Required("selected_vacuum"): vol.In(vacuum_list)}
        )

        return self.async_show_form(
            step_id="init",
            data_schema=devices_schema,
            errors=errors,
        )

    async def async_step_edit(self, user_input=None):
        """Manage the options for the custom component."""
        errors = {}

        vacuums = self.config_entry.data.get(CONF_VACS, {})

        if self.selected_vacuum is None or self.selected_vacuum not in vacuums:
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {vol.Required("selected_vacuum"): vol.In({})}
                ),
                errors=errors,
            )

        if user_input is not None:
            updated_vacuums = deepcopy(vacuums)
            updated_vacuums[self.selected_vacuum][CONF_AUTODISCOVERY] = user_input[
                CONF_AUTODISCOVERY
            ]
            updated_vacuums[self.selected_vacuum][CONF_IP_ADDRESS] = user_input.get(
                CONF_IP_ADDRESS, ""
            )

            updated_data = dict(self.config_entry.data)
            updated_data[CONF_VACS] = updated_vacuums

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
            )

            return self.async_create_entry(title="", data={})

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_AUTODISCOVERY,
                    default=vacuums[self.selected_vacuum].get(CONF_AUTODISCOVERY, True),
                ): bool,
                vol.Optional(
                    CONF_IP_ADDRESS,
                    default=vacuums[self.selected_vacuum].get(CONF_IP_ADDRESS, ""),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="edit",
            data_schema=options_schema,
            errors=errors,
        )