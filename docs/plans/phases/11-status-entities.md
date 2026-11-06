# Phase 11 — Status and connectivity entities

## Scope
From the 06/11/2026 brainstorm (features: status sensor, docked/charging binary sensors, connected and last-seen entities, device page detail). Built on Phase 09's coordinator.

## Design
- **Status `sensor`** (`device_class: enum`): the full STATUS_MAPPING text ("Recharge", "Cleaning paused", "Position"). The options list comes from the model's status values (Phase 08).
- **New `binary_sensor.py` platform**:
  - `docked`: status in Recharge / Standby-at-dock / Charging-complete. Exact strings are taken from captures, not guessed.
  - `charging` (`device_class: battery_charging`).
  - `connected` (`device_class: connectivity`, `entity_category: diagnostic`) from the coordinator's socket state.
- **Last-seen `sensor`** (`timestamp`, diagnostic): time of the last push or GET reply.
- **DeviceInfo**: add `sw_version` (from the cloud data stored at setup, if present) and `connections={(CONNECTION_NETWORK_MAC, mac)}`. Check what `config_flow.py` stores. If the firmware version isn't stored, leave it out; don't add a config-entry migration just for it.
- Names in `strings.json` / `translations/en.json`.

## Acceptance criteria
- [ ] Each entity reflects the Eufy app on Dobby through a full clean → dock cycle.
- [ ] `connected` turns off within one ping interval of pulling Dobby's power.
- [ ] Device page shows the MAC (and firmware if available).
- [ ] CI green; `docs/architecture/ha-entity.md` updated; the CLAUDE.md code map lists `binary_sensor.py`.

## Status
Planned, not built.

## Size
M, ~40-65k.
