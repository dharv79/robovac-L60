# Phase 20 — "New RoboVac found" setup prompt

## Scope
From the 06/11/2026 brainstorm (feature: discovery-started setup). The brainstorm's "share discovery ports with localtuya" improvement is dropped: `tuyalocaldiscovery.py:27,30` already binds with `reuse_port=True`.

## Design
- In `__init__.update_device` (`__init__.py:36`), when a broadcast's `gwId` isn't in any entry:
  - Start `hass.config_entries.flow.async_init(DOMAIN, context={"source": "integration_discovery"}, data={"gwId", "ip", "productKey"})`.
  - Rate-limit it to once per `gwId` per HA run.
- `config_flow.async_step_integration_discovery`:
  - Set the unique id from the `gwId` and abort if it's already configured.
  - Show a confirm step, then continue into the existing credential step. The cloud login is still needed for the localKey.
- If the account already has an entry, add the vacuum to it instead of creating a second entry. This merges the same way as Phase 19.

## Acceptance criteria
- [ ] With the Dobby entry deleted, a "Discovered: RoboVac" card appears within a minute and completes setup.
- [ ] No card for an already-configured vacuum, and no repeat card after dismissing it.
- [ ] CI covers the discovery step with mocks; `docs/architecture/transport.md` discovery section updated.

## Status
Planned, not built.

## Size
M, ~45-75k.
