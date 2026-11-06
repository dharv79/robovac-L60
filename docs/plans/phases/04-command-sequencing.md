# Phase 04 — Command sequencing fixes

## Goal
Fix the race in v1.0.11's start escalation, where a Dock pressed during the start sequence could be followed by the sequence's own `AggP` + `BBoCCAE=`, and trim redundant traffic. Source: 06/11/2026 brainstorm (improvements: cancel start sequence, event wait, coalesce refreshes, bounded queue).

## Scope
- **Cancel the start sequence on conflicting commands**:
  - Run the sequence in a dedicated `self._start_task`.
  - Any mode command from outside the sequence cancels it: everything routed through `_async_set_mode` (pause, dock/stop, spot, edge/small-room/autoClean) and a raw `send_command` to the mode DPS.
  - A second `async_start` while one runs is a no-op.
  - **Deviation from the original plan:** fan speed is excluded. It writes a different DPS and shouldn't abort a start.
- **Event wait:**
  - `_async_wait_until_cleaning` waits on an `asyncio.Event` (`self._cleaning`), set and cleared by `_update_cleaning_event()` at the end of `update_entity_values`, instead of a 0.25 s poll.
  - The `tuyalocalapi._async_send` item needed no change: its 0.25 s sleep is a retry pause, and responses already wait on a per-sequence semaphore.
- **One refresh per burst:** `_schedule_refresh` keeps a single `self._refresh_task` and skips scheduling while one is pending.
- **Bounded queue, drop stale SETs:**
  - Every queue append goes through `TuyaDevice._enqueue`.
  - Expired messages are dropped first.
  - Any unsent SET whose DPS codes are all overwritten by the new SET is removed.
  - The queue is capped at `MAX_QUEUE_LENGTH = 20`. When full, the oldest message nobody waits on (a ping or SET) is dropped first, with a warning.

## Files touched
- `custom_components/robovac/vacuum.py`:
  - `__init__`, `update_entity_values`
  - `_update_cleaning_event`, `_schedule_refresh`, `_cancel_start`
  - `_async_set_mode`, `async_start`, `_async_wait_until_cleaning`
  - `async_send_command` (raw mode write), `async_will_remove_from_hass`
- `custom_components/robovac/tuyalocalapi.py`: `MAX_QUEUE_LENGTH`, `_enqueue`; `async_get`, `async_set` and `async_ping` use it.
- `docs/architecture/ha-entity.md`: "Command sequencing" section, and the refresh wording.
- `docs/architecture/transport.md`: "Bounded send queue" section.

## Tests
Scratch simulation, not committed (`sim_phase04.py` in the session scratchpad; Phase 07 turns these cases into pytest). It stubs HA and `cryptography`. 13/13 pass:
- **Start from each state:** paused, returning and standby, each with the state known and unknown (6 cases). Each ends cleaning, with the same command order as v1.0.11.
- **Start then Dock after 0.1 s:** nothing is sent after `AggG`, and the start task is cleared.
- **Second start while one runs:** it's a no-op.
- **Raw `send_command("152", …)` during a start:** it cancels the start.
- **Four writes in a burst:** one refresh.
- **Queue:**
  - A stale SET is replaced and the queued GET is kept.
  - A SET that only partly overlaps is kept.
  - The cap holds at 20 and the GET survives.
- **Static checks:**
  - `python -m py_compile` passes on all files.
  - `ruff check` shows no new findings (16 already there).
  - The repo isn't black-formatted (deferred to Phase 07), but the new lines are black-clean apart from the existing long `_async_wait_until_cleaning` signature.

On-device checks, still open:
- [ ] Start then Dock within 2 s: Dobby docks, and the log shows no `AggP`/`BBoCCAE=` after `AggG`.
- [ ] Start from paused, returning and docked still works (the three v1.0.11 cases).
- [ ] The debug log shows one follow-up GET per command burst.

## Status
Built; on-device checks open.

## Built (06/11/2026)
- Code and docs are as listed above.
- **Size:** S, ~40k actual. This is a rough figure and above the ~20-35k estimate, because the scratch tests were rebuilt to drive the real entity methods.
