# Phase 11 — Control entities and services

## Goal
Replace the Boost IQ `send_command` magic string with a real switch, add a stop-return button, locate button and suction select, and register `robovac.start_new_clean` and `robovac.auto_clean`. Built on Phase 10's coordinator.

## Scope
- `switch` Boost IQ (explicit on/off; the `boostIQ` send_command stays a toggle).
- `button` Stop return to dock (model must declare `stop_return`) and Locate.
- `select` Suction level from the model's fan speeds.
- Entity services `robovac.start_new_clean` (cancellable stop-return → wait for non-paused → start-auto) and `robovac.auto_clean`.
- Dropped by user decision (06/11/2026): `edge_clean` / `small_room_clean` (no L60 model declares those modes).
- Out of scope: DND switch (Phase 15), `AUTO_RETURN` (no DPS code).

## Files touched
- New: `entity.py`, `switch.py`, `button.py`, `select.py`, `services.yaml`.
- Edited: `coordinator.py` (`async_send_dps`, `declared_modes`, `cancel_start`), `vacuum.py` (services, sequence), `__init__.py` (platforms), `strings.json`, `translations/en.json`.
- Tests: `tests/test_control_entities.py`. Docs: `ha-entity.md`, `testing.md`, CLAUDE.md code map.

## Tests
See the `test_control_entities.py` row in `docs/architecture/testing.md`.

## Acceptance criteria
- [x] Boost IQ switch appears only on models with `BOOST_IQ`; stop-return only where the model declares it.
- [ ] Switch state matches the Eufy app at startup and both ways (on-device).
- [ ] Stop-return button stops Dobby returning to dock; suction select matches the app both ways (on-device).
- [ ] `start_new_clean` while paused starts a fresh clean (on-device; the stop-return-on-paused behaviour is unconfirmed).
- [x] CI green; `ha-entity.md` and the CLAUDE.md code map updated.

## Status
Done, merged (9e438de, PR #16); CI green. On-device checks pending.

## Built (06/11/2026)
- 270 tests pass locally; ruff clean.
- Deviation: `auto_clean` kept (routed to start-auto) while the other typed services were dropped.

## Size
M, ~50-80k.
