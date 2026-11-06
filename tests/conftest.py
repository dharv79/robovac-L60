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

"""Shared fixtures: an L60 entity wired to a fake device, no network."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DESCRIPTION,
    CONF_ID,
    CONF_IP_ADDRESS,
    CONF_MAC,
    CONF_MODEL,
    CONF_NAME,
)

from custom_components.robovac.vacuum import RoboVacEntity

TEST_KEY = "0123456789abcdef"  # fake 16-char local key, never a real one  # gitleaks:allow

# Raw DPS 153 (status) values for the L60.
CLEANING = "BgoAEAUyAA=="
PAUSED = "CAoAEAUyAggB"
RECHARGE = "BBAHQgA="
STANDBY = "AA=="
CHARGING = "BBADGgA="

# (current status, mode written) -> next status, as Dobby behaves on-device.
TRANSITIONS = {
    (PAUSED, "AggO"): CLEANING,
    (RECHARGE, "AggP"): STANDBY,
    (STANDBY, "BBoCCAE="): CLEANING,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load custom_components/robovac in every test."""
    return


def make_item(model: str = "T2267", ip: str | None = "192.0.2.10") -> dict:
    return {
        CONF_NAME: "Dobby",
        CONF_ID: "dobby-id",
        CONF_IP_ADDRESS: ip,
        CONF_ACCESS_TOKEN: TEST_KEY,
        CONF_MODEL: model,
        CONF_DESCRIPTION: "RoboVac L60",
        CONF_MAC: "00:00:5e:00:53:01",
    }


class FakeDevice:
    """Replaces the entity's async_set: records writes, replays state pushes."""

    def __init__(self, entity: RoboVacEntity, status: str, push_delay: float = 0.02):
        self.entity = entity
        self.status = status
        self.push_delay = push_delay
        self.sent: list[dict] = []

    async def async_set(self, dps: dict) -> None:
        self.sent.append(dps)
        mode = dps.get("152")
        if mode is None:
            return
        nxt = "BBAHQgA=" if mode == "AggG" else TRANSITIONS.get((self.status, mode))
        if nxt is not None:
            self.status = nxt
            asyncio.get_running_loop().call_later(self.push_delay, self.push)

    def push(self) -> None:
        self.entity.vacuum._dps["153"] = self.status
        self.entity.update_entity_values()

    @property
    def modes(self) -> list[str]:
        return [d["152"] for d in self.sent if "152" in d]


@pytest.fixture
async def entity(monkeypatch):
    """An L60 RoboVacEntity with its transport disabled and writes faked."""
    # START_CONFIRM_TIMEOUT is bound as a default argument, so patch that.
    monkeypatch.setattr(
        RoboVacEntity._async_wait_until_cleaning, "__defaults__", (0.3,)
    )
    ent = RoboVacEntity(make_item())
    ent.async_write_ha_state = lambda: None
    refreshes = []

    async def fake_refresh():
        refreshes.append(1)
        await asyncio.sleep(0.02)

    ent.async_forced_update = fake_refresh
    ent.refreshes = refreshes
    yield ent
    await ent.async_will_remove_from_hass()
    await asyncio.sleep(0)


def attach(entity: RoboVacEntity, status: str, known: bool = True) -> FakeDevice:
    """Give the entity a fake device in `status`; known=False hides it (restart)."""
    fake = FakeDevice(entity, status)
    entity.vacuum.async_set = fake.async_set
    if known:
        entity.vacuum._dps["153"] = status
        entity.update_entity_values()
    return fake
