# Phase 10 — Shared coordinator and modern HA patterns

## Goal
Give each vacuum one coordinator that owns the device and the parsed state, so entities (now and in Phases 11-17) are thin `CoordinatorEntity`s, pushes are the main update path, and an IP change reconnects only that vacuum. From the 06/11/2026 brainstorm; supersedes Phase 03 idea #5.

## Scope
- `RoboVacCoordinator` per vacuum; `RoboVacData` parsed once; vacuum and battery sensor become `CoordinatorEntity`s.
- `entry.runtime_data` = `{vac_id: coordinator}`; `hass.data[DOMAIN][CONF_VACS]` removed.
- Poll only as fallback: 5 min `update_interval` plus a `REFRESH_RATE` watchdog.
- `_attr_has_entity_name = True`, `_attr_name = None`; unique_ids unchanged.
- Per-vacuum IP update with no entry reload; listener ignores IP-only changes.
- Out of scope: `iot_class` (user declined `local_push`, 06/11/2026; manifest untouched).

## Files touched
- `coordinator.py` (new); `vacuum.py`, `sensor.py`, `__init__.py`.
- Tests: `tests/test_coordinator.py` (new), `conftest.py`, `test_vacuum.py`, `test_security.py`, `test_model_modes.py`.
- Docs: `CLAUDE.md` (code map, do-not-break #4), `do-not-break.md`, `ha-entity.md`, `testing.md`.

## Tests
See the `test_coordinator.py` row in `docs/architecture/testing.md`. The existing start-sequence, activity, restore and security tests pass, adapted to the coordinator.

## Acceptance criteria
- [x] Entity IDs and unique_ids unchanged (full setup test).
- [x] Battery sensor updates on push without its own poll.
- [ ] Debug log shows no 60 s GETs while pushes are arriving (on-device).
- [x] Changing the IP via discovery reconnects only that vacuum (unit-tested; on-device check pending).
- [x] CI green; `ha-entity.md` and the CLAUDE.md code map updated.

## Status
Done, merged (2fac439, PR #15); CI green. On-device checks pending.

## Built (06/11/2026)
- 257 tests pass locally; ruff clean.
- Deviations from the plan: no translated name (main entity uses the device name); push also marks the vacuum available; options-flow IP edits now also reconnect without a reload.
- A quiet vacuum is still polled every 60 s by the watchdog, as before; pushes within 60 s suppress it.

## Size
L, ~90-140k.
