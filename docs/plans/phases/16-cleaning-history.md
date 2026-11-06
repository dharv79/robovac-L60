# Phase 16 — Cleaning events and history sensors

## Scope
From the 06/11/2026 brainstorm (features: cleaning events, cleaning count and last-cleaned sensors).

## Design
- In the coordinator, detect activity transitions:
  - idle/docked → cleaning: **started**
  - cleaning → returning/docked after a full clean: **finished**
  - → error: **error**
- Fire `robovac_cleaning_started` / `_finished` / `_error` on `hass.bus` with `device_id`, `entity_id`, plus duration and area when the model reports cleaning time/area.
- Add `logbook.py` (`async_describe_events`) so they show in the logbook.
- Sensors:
  - `cleaning_count` (`total_increasing`)
  - `last_cleaned` (`timestamp`)
  - `last_clean_duration` (`duration`)
- All are `RestoreSensor`s, so they survive restarts.
- Pause/resume within one clean must not count as two cleans. Debounce transitions that last under ~10 s, since Dobby flaps briefly during auto-dock.

## Acceptance criteria
- [ ] One full clean on Dobby gives exactly one started and one finished event and count +1, including a pause/resume in the middle.
- [ ] Logbook shows both events.
- [ ] Sensors keep their values across an HA restart.
- [ ] CI tests cover the transition logic with fake state sequences.

## Status
In progress (draft PR).

## Size
M, ~40-65k.

## Built (06/11/2026)
`cleaning.py` tracker (10 s finish debounce), coordinator events, `logbook.py`, three restoring sensors. Tests in `tests/test_cleaning.py` (315 total). On-device check open: one full clean on Dobby gives one started, one finished, count +1, and the logbook shows both.
