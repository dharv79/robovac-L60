# Phase 04 — Command sequencing fixes

## Scope
From the 06/11/2026 brainstorm (improvements: cancel start sequence, event wait, coalesce refreshes, bounded queue). Fixes a real race in v1.0.11's start escalation and trims redundant traffic.

## Design
- **Cancel the start sequence on any other command** (bug): `async_start` puts `_async_start_sequence` in `_refresh_tasks` (`vacuum.py:465-474`). Pressing Dock within about 12 s still lets it send `AggP` + `BBoCCAE=` after the user's `AggG`.
  - Keep the sequence in a dedicated `self._start_task`.
  - `async_pause`, `async_stop`, `async_return_to_base`, `async_set_fan_speed`, `async_clean_spot` and `async_send_command` cancel it first.
  - A second `async_start` while one runs is a no-op.
- **Wait on an event, not a 0.25 s poll**: `_async_wait_until_cleaning` (`vacuum.py:476-483`) waits on an `asyncio.Event` set from `update_entity_values` when activity becomes CLEANING. Same for the response wait loop in `tuyalocalapi._async_send` (`tuyalocalapi.py:616`), if it can be done without touching do-not-break #1.
- **One refresh per burst**: `_schedule_refresh` (`vacuum.py:428`) skips scheduling if a refresh is already pending. The start sequence sends up to 4 writes, so this saves up to 3 refreshes.
- **Bounded queue, drop stale duplicates**: in `TuyaDevice` (`tuyalocalapi.py:393`), a new SET for the same DPS replaces a queued, unsent SET for that DPS. Cap the queue (e.g. 20) and log when dropping.

## Acceptance criteria
- [ ] Start then Dock within 2 s: Dobby docks, and the logs show no `AggP`/`BBoCCAE=` after `AggG`.
- [ ] Start from paused, returning and docked still works (the three v1.0.11 cases).
- [ ] Debug log shows one follow-up GET per command burst.
- [ ] The scratch start-sequence simulation (6 cases) passes, plus a cancel case.
- [ ] `python -m py_compile` passes; `docs/architecture/ha-entity.md` commands section updated.

## Status
Planned, not built.

## Size
S, ~20-35k.
