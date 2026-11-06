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

"""Phase 14: protobuf codec and the last-prompt sensor."""

from __future__ import annotations

import base64
import logging
from types import SimpleNamespace

import pytest

from custom_components.robovac import sensor
from custom_components.robovac.coordinator import RoboVacCoordinator, decode_prompt
from custom_components.robovac.proto import (
    ProtoError,
    decode_prefixed,
    encode_prefixed,
    try_decode,
)

from .conftest import make_item

KNOWN = [
    "BBoCCAE=",  # start auto
    "AggN",
    "AggO",
    "AggP",
    "AggG",
    "AA==",  # empty message
    "DgoAEgoKABICCBYaAggI",  # captured DND default
    "BgoAEAUyAA==",  # status: auto cleaning
    "CAoAEAUyAggB",
    "DQjRidjfv9bszgESAR8=",  # DPS 178 samples
    "DQiMrPbd+eLszgESAVU=",
    "Cgiv6NbWsePszgE=",
]


@pytest.mark.parametrize("raw", KNOWN)
def test_known_values_round_trip(raw):
    assert encode_prefixed(decode_prefixed(raw)) == raw


def test_decoded_shapes():
    assert decode_prefixed("AggN") == {1: 13}
    assert decode_prefixed("BBoCCAE=") == {3: {1: 1}}
    assert decode_prefixed("AA==") == {}
    dnd = decode_prefixed("DgoAEgoKABICCBYaAggI")
    assert dnd == {1: b"", 2: {1: b"", 2: {1: 22}, 3: {1: 8}}}


def test_repeated_fields_and_strings_and_flat_mode():
    raw = encode_prefixed({1: [1, 2], 2: "hi", 3: True})
    assert decode_prefixed(raw, nested=False) == {1: [1, 2], 2: b"hi", 3: 1}


def test_bad_input_is_rejected():
    for bad in ("!!!", "AwgB", "BQgB", "AQ=="):  # not base64, short, long, truncated
        with pytest.raises(ProtoError):
            decode_prefixed(bad)
    with pytest.raises(ProtoError):
        encode_prefixed({1: 1.5})
    assert try_decode("not base64!") is None and try_decode(True) is None


def test_decode_prompt_codes():
    assert decode_prompt("DQjRidjfv9bszgESAR8=") == 31
    assert decode_prompt("DQiMrPbd+eLszgESAVU=") == 85
    assert decode_prompt("DQjayd7nsOXszgESASg=") == 40
    assert decode_prompt("Cgiv6NbWsePszgE=") is None  # timestamp only
    assert decode_prompt(None) is None and decode_prompt("junk") is None
    # A code byte that would look like a nested tag stays a plain byte.
    raw = base64.b64encode(bytes([3, 0x12, 0x01, 0x08])).decode()
    assert decode_prompt(raw) == 8


async def test_last_prompt_sensor(hass, caplog):
    coordinator = RoboVacCoordinator(hass, make_item())
    added: list = []
    entry = SimpleNamespace(runtime_data={coordinator.vacuum_id: coordinator})
    await sensor.async_setup_entry(None, entry, added.extend)
    prompt = next(e for e in added if e.unique_id.endswith("_last_prompt"))
    assert prompt.native_value is None and prompt.extra_state_attributes is None

    def push(raw):
        coordinator.vacuum._dps["178"] = raw
        coordinator.update_from_device()

    push("DQjRidjfv9bszgESAR8=")
    assert prompt.native_value == "Can't start while recharging"
    assert prompt.extra_state_attributes == {"code": 31}
    push("DQiMrPbd+eLszgESAVU=")
    assert prompt.native_value == "code 85"
    push("Cgiv6NbWsePszgE=")  # no code: keep the last one
    assert prompt.native_value == "code 85"
    coordinator.vacuum._dps.pop("178")
    coordinator.update_from_device()
    assert prompt.native_value == "code 85"
    await coordinator.async_shutdown()


async def test_capture_log_includes_decoded_value(hass, caplog):
    coordinator = RoboVacCoordinator(hass, make_item())
    coordinator.async_set_capture(True)
    with caplog.at_level(logging.INFO, logger="custom_components.robovac"):
        coordinator.vacuum._dps["157"] = "DgoAEgoKABICCBYaAggI"
        coordinator.update_from_device()
    line = next(r.message for r in caplog.records if "DPS 157" in r.message)
    assert "(decoded {1: b'', 2: {1: b'', 2: {1: 22}, 3: {1: 8}}})" in line
    await coordinator.async_shutdown()
