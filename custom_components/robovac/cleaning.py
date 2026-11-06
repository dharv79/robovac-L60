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

"""Clean-session tracking: pure logic, no Home Assistant imports needed to test it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.vacuum import VacuumActivity

# Docked or idle must hold this long before a clean counts as finished, so a
# brief flap while the vacuum auto-docks (or a pause/resume) doesn't end it.
FINISH_DEBOUNCE = 10.0

STARTED = "started"
FINISHED = "finished"
ERROR = "error"


@dataclass(frozen=True)
class CleanEvent:
    kind: str  # STARTED, FINISHED or ERROR
    time: datetime
    duration: float | None = None  # seconds, FINISHED only


class CleanTracker:
    """Turns a stream of activities into started / finished / error events.

    A clean starts when the vacuum is CLEANING with no clean open. It stays open
    through pauses and the trip home, and finishes once docked or idle for
    FINISH_DEBOUNCE seconds. A clean already running when HA starts is not
    started, and its finish is not reported either.
    """

    def __init__(self) -> None:
        self.in_clean = False
        self._started_at: datetime | None = None
        self._docked_mono: float | None = None
        self._docked_at: datetime | None = None
        self._in_error = False

    @property
    def deadline(self) -> float | None:
        """Monotonic time at which a pending finish confirms, if any."""
        if self.in_clean and self._docked_mono is not None:
            return self._docked_mono + FINISH_DEBOUNCE
        return None

    def update(
        self, activity: VacuumActivity, mono: float, now: datetime
    ) -> list[CleanEvent]:
        events: list[CleanEvent] = []
        if activity == VacuumActivity.ERROR:
            if not self._in_error:
                events.append(CleanEvent(ERROR, now))
            self._in_error = True
        else:
            self._in_error = False

        if activity == VacuumActivity.CLEANING and not self.in_clean:
            self.in_clean = True
            self._started_at = now
            self._docked_mono = self._docked_at = None
            events.append(CleanEvent(STARTED, now))

        if self.in_clean:
            if activity in (VacuumActivity.DOCKED, VacuumActivity.IDLE):
                if self._docked_mono is None:
                    self._docked_mono, self._docked_at = mono, now
                if mono - self._docked_mono >= FINISH_DEBOUNCE:
                    ended = self._docked_at
                    duration = (ended - self._started_at).total_seconds()
                    self.in_clean = False
                    self._docked_mono = self._docked_at = None
                    events.append(CleanEvent(FINISHED, ended, max(duration, 0.0)))
            else:
                self._docked_mono = self._docked_at = None
        return events
