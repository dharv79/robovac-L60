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

"""CLAUDE.md do-not-break rules as tests (numbers match the list there)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.robovac import tuyalocalapi
from custom_components.robovac.robovac import RoboVac
from custom_components.robovac.vacuums import ROBOVAC_MODELS

from .conftest import TEST_KEY

VACUUMS_DIR = Path(__file__).parent.parent / "custom_components" / "robovac" / "vacuums"


def _model_codes(model) -> dict:
    return RoboVac.getCommandCodes(SimpleNamespace(model_details=model))


async def _noop():
    return None


def _device(model=None) -> tuyalocalapi.TuyaDevice:
    return tuyalocalapi.TuyaDevice(
        model or SimpleNamespace(),
        "dobby-id",
        "192.0.2.10",
        1,
        9999,
        _noop,
        local_key=TEST_KEY,
    )


async def test_1_disconnect_on_eof_without_retrying_read():
    device = _device()
    reads = []

    class Reader:
        async def readuntil(self, *_):
            reads.append(1)
            raise asyncio.IncompleteReadError(b"", None)

        def at_eof(self):
            return True

    class Writer:
        def close(self):
            pass

        async def wait_closed(self):
            pass

    device.reader, device.writer, device._connected = Reader(), Writer(), True
    await asyncio.wait_for(device._async_handle_message(), 1)
    assert reads == [1]
    assert device._connected is False
    await device.async_disable()


@pytest.mark.parametrize("path", sorted(VACUUMS_DIR.glob("*.py")), ids=lambda p: p.name)
def test_2_model_files_never_import_homeassistant(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(n.split(".")[0] == "homeassistant" for n in names), path.name


@pytest.mark.parametrize("key", sorted(ROBOVAC_MODELS))
def test_3_command_codes_are_str(key):
    codes = _model_codes(ROBOVAC_MODELS[key])
    assert codes
    assert all(isinstance(code, str) for code in codes.values()), codes


@pytest.mark.parametrize("key", sorted(ROBOVAC_MODELS))
def test_7_registry_key_is_class_name_and_5_chars(key):
    assert ROBOVAC_MODELS[key].__name__ == key
    assert len(key) == 5


async def test_6_disable_cancels_all_loop_tasks():
    device = _device()
    device._ping_task = asyncio.create_task(asyncio.sleep(60))
    device._reader_task = asyncio.create_task(asyncio.sleep(60))
    tasks = (device._queue_task, device._ping_task, device._reader_task)
    await device.async_disable()
    await asyncio.sleep(0)
    assert all(task.cancelled() for task in tasks)
