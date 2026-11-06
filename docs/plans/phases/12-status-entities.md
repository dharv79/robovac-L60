# Phase 12 — Status and connectivity entities

## Goal
Show what the vacuum is doing and whether it is reachable: a status sensor, docked/charging binary sensors, a connected sensor and a last-seen timestamp. Built on Phase 10's coordinator.

## Scope
- `sensor` Status (enum, from `STATUS_MAPPING` and the model's `status_values`) and Last seen (timestamp, diagnostic).
- New `binary_sensor.py`: docked, charging (`battery_charging`), connected (`connectivity`, diagnostic).
- `TuyaDevice.connection_cb` so `connected` updates on connect/disconnect.
- DeviceInfo: MAC already present; firmware not stored, so `sw_version` omitted (no migration).
- Out of scope: reading firmware from DPS 169 (Phase 14).

## Files touched
- New: `binary_sensor.py`, `tests/test_status_entities.py`.
- Edited: `sensor.py`, `coordinator.py` (`last_seen`, `connected`, `DOCKED_STATES`, connection callback), `tuyalocalapi.py` (`connected`, `connection_cb`), `__init__.py`, `strings.json`, `translations/en.json`.
- Docs: `ha-entity.md`, `testing.md`, CLAUDE.md code map.

## Tests
See the `test_status_entities.py` row in `docs/architecture/testing.md`.

## Acceptance criteria
- [ ] Each entity reflects the Eufy app on Dobby through a full clean → dock cycle (on-device).
- [ ] `connected` turns off within one ping interval of pulling Dobby's power (on-device).
- [x] Device page shows the MAC (via the vacuum entity); firmware omitted by design.
- [x] CI green; `ha-entity.md` updated; the CLAUDE.md code map lists `binary_sensor.py`.

## Status
In progress (PR pending). On-device checks pending.

## Built (06/11/2026)
- 279 tests pass locally; ruff clean.
- Deviation: `docked` is Charging / Completed (the captured dock statuses, matching `live_activity`), not "Recharge", which is the vacuum heading home.

## Size
M, ~40-65k.
