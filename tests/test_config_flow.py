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

"""Config flow user step with the Eufy/Tuya cloud calls mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.robovac.config_flow import CannotConnect, InvalidAuth
from custom_components.robovac.const import CONF_VACS, DOMAIN

from .conftest import make_item

USER_INPUT = {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "not-a-real-password"}
GET_VACUUMS = "custom_components.robovac.config_flow.get_eufy_vacuums"


@pytest.fixture(autouse=True)
def no_setup():
    """Don't start discovery or entities when an entry is created."""
    with (
        patch("custom_components.robovac.async_setup", return_value=True),
        patch("custom_components.robovac.async_setup_entry", return_value=True),
    ):
        yield


async def _start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_user_step_creates_entry(hass):
    result = await _start(hass)
    item = make_item()
    with patch(GET_VACUUMS, side_effect=lambda data: {**data, CONF_VACS: {"dobby-id": item}}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == USER_INPUT[CONF_USERNAME]
    assert result["data"][CONF_VACS] == {"dobby-id": item}
    assert CONF_PASSWORD not in result["data"]  # Phase 08: never stored


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (InvalidAuth, "invalid_auth"),
        (CannotConnect, "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_step_errors(hass, error, code):
    result = await _start(hass)
    with patch(GET_VACUUMS, side_effect=error):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": code}
