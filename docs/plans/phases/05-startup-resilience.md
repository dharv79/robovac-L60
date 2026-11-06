# Phase 05 — Startup and connection resilience

## Goal
Keep a sleeping or powered-off vacuum from delaying HA startup or flooding the log, recover cleanly when it comes back, and remove `ast.literal_eval` from device data. Source: 06/11/2026 brainstorm (improvements: non-blocking startup, safer consumables parse, reconnect behaviour, log noise).

## Scope
- **Non-blocking startup:**
  - `async_added_to_hass` starts `_async_warm_up` with `hass.async_create_background_task` and returns at once. The warm-up is still up to 5 attempts, 1.5 s apart (`WARMUP_ATTEMPTS`, `WARMUP_DELAY`), and stops early if a poll already made the entity available.
  - The entity starts unavailable until the first update that returns DPS.
  - `async_will_remove_from_hass` cancels the warm-up task.
- **Safer consumables parse:** `json.loads` replaces `ast.literal_eval`.
  - No model has both the `CONSUMABLES` feature and a mapped DPS code (T2190/T2193/T2253 have the flag with the DPS commented out; T2276/T2320 have DPS 168 with the flag commented out), so this path doesn't run today. No real payload was available to check the format; a Python-literal payload would be logged at debug and ignored.
- **Reconnect:**
  - `backoff_interval()` adds ±20% jitter to the existing exponential backoff (cap 600 s before jitter).
  - `_reset_backoff()` runs on a successful send and on every gratuitous push. It wakes the queue loop if a backoff was active.
- **Log once:** `_mark_unavailable` logs one warning when the entity goes unavailable, and `_mark_available` logs one info when it recovers. The transport's backoff messages are now debug, so recovery gives exactly one non-debug line.
- **Debug log noise:** a module-level `tuyalocalapi.VERBOSE` (default off) gates full payloads. Otherwise:
  - sends and receives log `Message.summary()` (command, sequence, DPS keys);
  - state updates log DPS keys;
  - undecodable payloads log their length, not hex;
  - the entity's full `tuyastatus` line is skipped.

## Files touched
- `custom_components/robovac/vacuum.py`: `WARMUP_*`, `__init__`, `async_added_to_hass`, `_async_warm_up`, `_mark_available`, `_mark_unavailable`, `async_update`, `update_entity_values` (VERBOSE gate), `_update_consumables`, `async_will_remove_from_hass`.
- `custom_components/robovac/tuyalocalapi.py`: `MAX_BACKOFF`, `BACKOFF_JITTER`, `VERBOSE`, `backoff_interval`, `_log_undecodable`, `Message.summary`/`describe`, `process_queue`, `_reset_backoff`, `async_gratuitous_update_state`, `async_update_state`, `_enqueue`, `_async_handle_message` and `_async_send` log lines.
- `docs/architecture/ha-entity.md`: "Startup and availability" section.
- `docs/architecture/transport.md`: "Backoff and debug logging" section.

## Tests
Scratch simulation, not committed (`sim_phase05.py` in the session scratchpad; Phase 07 turns it into pytest). It stubs HA and `cryptography`. 20/20 pass:
- **Device off:** `async_added_to_hass` returns at once; the entity starts unavailable; the warm-up makes 5 attempts; one warning, and 6 more failed polls add none.
- **Recovery:** available again with exactly one info line. A later outage needs 4 failed polls before the second warning.
- **Warm-up:** success on attempt 2 gives no warning or info; it stops once a poll makes the entity available; removal cancels it.
- **Consumables:** a JSON payload decodes; a Python-literal or non-base64 payload is ignored.
- **Transport:**
  - The first backoff step is 4-6 s; the cap holds at 600 ±20%, with jitter.
  - A push clears the backoff, and the queue loop sends within 0.25 s instead of sleeping 300 s.
  - `summary()` holds keys but no values; `describe()` gives the full repr only when `VERBOSE` is on; a payload-less ping summarises cleanly.
- **Regression:** the Phase 04 simulation still passes 13/13.
- **Static checks:** `python -m py_compile` passes on all files; `ruff check` shows no new findings; new lines fit black's 88 columns.

On-device checks, still open:
- [ ] With Dobby powered off, HA startup isn't delayed and the entity shows unavailable.
- [ ] Powering Dobby back on recovers without an HA restart and logs exactly one recovery line.
- [ ] The consumables attribute is still absent on the L60.

## Status
Done; PR pending.

## Built (06/11/2026)
- Code and docs are as listed above.
- **Size:** S, ~35k actual (rough figure).
