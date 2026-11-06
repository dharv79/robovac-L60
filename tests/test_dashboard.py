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

"""Phase 18: the dashboard YAML only uses core cards and real entities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import robovac
from custom_components.robovac.const import CONF_VACS, DOMAIN

from .conftest import make_item

DASHBOARD = Path(__file__).parent.parent / "docs" / "dashboards" / "robovac-l60.yaml"
ALLOWED_CARDS = {"grid", "heading", "tile", "gauge", "history-graph", "markdown", "entities"}
ALLOWED_FEATURES = {"vacuum-commands", "select-options", "toggle"}


def walk(node):
    """Yield every dict in the document."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def entity_ids(doc) -> set[str]:
    found = set()
    for node in walk(doc):
        entity = node.get("entity")
        if isinstance(entity, str):
            found.add(entity)
    return found


def test_dashboard_parses_and_uses_only_core_cards():
    doc = yaml.safe_load(DASHBOARD.read_text())
    view = doc["views"][0]
    assert view["type"] == "sections"
    types = {n["type"] for n in walk(view["sections"]) if "type" in n}
    assert types <= ALLOWED_CARDS | ALLOWED_FEATURES | {"attribute"}, types
    assert "custom:" not in DASHBOARD.read_text()


async def test_every_referenced_entity_is_created_by_the_integration(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, data={CONF_VACS: {"dobby-id": make_item()}}
    )
    entry.add_to_hass(hass)
    with patch.object(robovac.TuyaLocalDiscovery, "start", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    created = {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    referenced = entity_ids(yaml.safe_load(DASHBOARD.read_text()))
    assert referenced and referenced <= created, referenced - created
    assert await hass.config_entries.async_unload(entry.entry_id)
