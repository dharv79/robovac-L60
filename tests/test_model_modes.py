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

"""Phase 09: per-model mode values and status overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.robovac.coordinator import RoboVacCoordinator
from custom_components.robovac.vacuums import ROBOVAC_MODELS
from custom_components.robovac.vacuums.base import (
    DEFAULT_MODE_VALUES,
    ModeKey,
    RobovacCommand,
    resolve_mode_labels,
    resolve_mode_values,
)

from .conftest import make_item

L60_MODELS = [
    code
    for code, model in ROBOVAC_MODELS.items()
    if hasattr(model, "mode_values")
]
COMMAND_KEYS = (
    ModeKey.START_AUTO,
    ModeKey.PAUSE,
    ModeKey.RESUME,
    ModeKey.STOP_RETURN,
    ModeKey.RETURN_HOME,
)


def test_eight_l60_models_declare_mode_values():
    assert sorted(L60_MODELS) == [
        "T2266", "T2267", "T2275", "T2276", "T2277", "T2278", "T2320", "T2351",
    ]


@pytest.mark.parametrize("code", L60_MODELS)
def test_l60_models_resolve_all_command_keys(code):
    model = ROBOVAC_MODELS[code]
    values = resolve_mode_values(model)
    for key in COMMAND_KEYS:
        assert isinstance(model.mode_values[key], str)
        assert values[key] == model.mode_values[key]
    # The legacy MODE value list still holds the pause / go home / start / resume strings.
    listed = model.commands[RobovacCommand.MODE]["values"]
    for key in (ModeKey.PAUSE, ModeKey.RETURN_HOME, ModeKey.START_AUTO, ModeKey.RESUME):
        assert values[key] in listed


@pytest.mark.parametrize(
    "code", [c for c in ROBOVAC_MODELS if c not in L60_MODELS]
)
def test_models_without_mode_values_use_defaults(code):
    assert resolve_mode_values(ROBOVAC_MODELS[code]) == DEFAULT_MODE_VALUES


def test_override_merges_over_defaults():
    class Fake:
        mode_values = {ModeKey.PAUSE: "XYZ"}

    values = resolve_mode_values(Fake)
    assert values[ModeKey.PAUSE] == "XYZ"
    assert values[ModeKey.RESUME] == DEFAULT_MODE_VALUES[ModeKey.RESUME]
    assert resolve_mode_labels(Fake)["XYZ"] == "Pause"


def test_labels_follow_raw_values():
    labels = resolve_mode_labels(ROBOVAC_MODELS["T2267"])
    assert labels["AggO"] == "Resume"
    assert labels["AggG"] == "Stop / Go to charge"
    assert labels["AA=="] == "Standby"


async def test_coordinator_uses_model_values(hass, monkeypatch):
    model = ROBOVAC_MODELS["T2267"]
    monkeypatch.setattr(
        model, "mode_values", {**model.mode_values, ModeKey.PAUSE: "CUSTOM"}
    )
    ent = RoboVacCoordinator(hass, make_item())
    assert ent.mode_values[ModeKey.PAUSE] == "CUSTOM"
    assert ent.mode_labels["CUSTOM"] == "Pause"


async def test_model_status_values_override(hass, monkeypatch):
    monkeypatch.setattr(
        ROBOVAC_MODELS["T2267"], "status_values", {"ZZZ=": "STANDBY"}, raising=False
    )
    ent = RoboVacCoordinator(hass, make_item())
    assert ent.status_values["ZZZ="] == "STANDBY"
    assert ent.status_values["AA=="] == "STANDBY"  # shared default kept


def test_no_raw_l60_mode_strings_in_vacuum_py():
    source = (
        Path(__file__).parent.parent / "custom_components" / "robovac" / "vacuum.py"
    ).read_text()
    for raw in ("BBoCCAE=", "AggN", "AggO", "AggP", "AggG"):
        assert raw not in source
