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

"""Logbook descriptions for the cleaning events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    DOMAIN,
    EVENT_CLEANING_ERROR,
    EVENT_CLEANING_FINISHED,
    EVENT_CLEANING_STARTED,
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Register how the cleaning events read in the logbook."""

    @callback
    def describe_started(event: Event) -> dict[str, Any]:
        return _entry(event, "started cleaning")

    @callback
    def describe_finished(event: Event) -> dict[str, Any]:
        minutes = event.data.get("duration")
        suffix = f" after {round(minutes / 60)} min" if minutes else ""
        return _entry(event, f"finished cleaning{suffix}")

    @callback
    def describe_error(event: Event) -> dict[str, Any]:
        return _entry(event, f"reported an error ({event.data.get('error')})")

    async_describe_event(DOMAIN, EVENT_CLEANING_STARTED, describe_started)
    async_describe_event(DOMAIN, EVENT_CLEANING_FINISHED, describe_finished)
    async_describe_event(DOMAIN, EVENT_CLEANING_ERROR, describe_error)


def _entry(event: Event, message: str) -> dict[str, Any]:
    return {
        LOGBOOK_ENTRY_NAME: "RoboVac",
        LOGBOOK_ENTRY_MESSAGE: message,
        ATTR_ENTITY_ID: event.data.get(ATTR_ENTITY_ID),
    }
