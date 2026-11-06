# Phase 06 — State after an HA restart

## Goal
After an HA restart the vacuum shows unknown until Dobby pushes, because the L60's GET reply has no DPS 152/153. Ask the device for those DPS on connect, and show the last known state in the meantime, without letting a stale state affect commands. Source: 06/11/2026 brainstorm (features: query status on connect, restore last state).

## Scope
- **Query on connect (model-gated):**
  - `Message.UPDATE_DPS_COMMAND = 0x12` (Tuya UPDATEDPS).
  - After each `async_connect`, `_async_query_dps` sends `{"dpId": [...]}` for any `query_dps_on_connect` codes missing from `_dps`. No response is awaited.
  - At most `MAX_DPS_QUERIES` (3) per device, in case the device drops the socket on it.
  - `_async_update_dps_reply` logs any `0x12` reply at debug, for the on-device experiment.
  - `T2267.query_dps_on_connect = (152, 153)`. The flag is in the model file, not a hard-coded check (do-not-break #2). Other L-series files (T2275-T2278, T2320, T2351) aren't opted in until verified.
  - **Deviation:** only UPDATEDPS is implemented. The DP_QUERY-with-`dpId`-list fallback is left for a follow-up if UPDATEDPS doesn't work on Dobby.
- **Restore last state:**
  - `RoboVacEntity` also inherits `RestoreEntity`. `async_added_to_hass` now calls `super().async_added_to_hass()`, which it didn't before.
  - `_async_restore_activity` seeds `_restored_activity` from the last state when `tuya_state` is unknown.
  - `activity` shows it only while `tuya_state` is `None`, with a `state_restored: true` attribute. The first decoded status clears it.
  - **Deviation:** the restored value is the HA activity, not `tuya_state`, since the restored state carries no raw status. Command logic uses the new `_live_activity()`, so a restored state never blocks the start escalation.

## Files touched
- `custom_components/robovac/tuyalocalapi.py`: `MAX_DPS_QUERIES`, `Message.UPDATE_DPS_COMMAND`, `TuyaDevice.__init__` (`_query_dps`, `_dps_queries`, `0x12` handler), `async_connect`, `_async_query_dps`, `_async_update_dps_reply`.
- `custom_components/robovac/vacuums/T2267.py`: `query_dps_on_connect`.
- `custom_components/robovac/vacuum.py`: `RestoreEntity` base, `ATTR_STATE_RESTORED`, `_restored_activity`, `activity`/`_live_activity`, `extra_state_attributes`, `async_added_to_hass`, `_async_restore_activity`, `update_entity_values`, `_update_cleaning_event`, `_async_wait_until_cleaning`.
- `docs/architecture/transport.md`: "DPS query on connect" section.
- `docs/architecture/ha-entity.md`: "Restored state after an HA restart" section.
- `docs/architecture/models.md`: "Optional model attributes" section.

## Tests
Scratch simulation, not committed (`sim_phase06.py` in the session scratchpad; Phase 07 turns it into pytest). It stubs HA and `cryptography`. 16/16 pass:
- **Restore:**
  - `RestoreEntity.async_added_to_hass` is called.
  - A restored `docked` is shown with `state_restored`, while the live activity stays unknown.
  - A restored `cleaning` doesn't set the cleaning event, and the wait for cleaning ignores it.
  - `unavailable`/`unknown` or no last state restore nothing, and an already-known state isn't overwritten.
  - The first live status clears the restored state and its attribute.
- **Query:**
  - UPDATEDPS is sent on connect with `dpId [152, 153]` and no response awaited.
  - It's capped at 3 per device and sends only the missing codes, or nothing once both are known.
  - The `0x12` handler is registered, and a model without the flag sends nothing.
- **Regression:** the Phase 04 and 05 simulations still pass, 13/13 and 20/20.
- **Static checks:** `python -m py_compile` passes on all files, including the model files; `ruff check` shows no new findings; new lines fit black's 88 columns.

On-device checks, still open. These decide whether UPDATEDPS stays:
- [ ] Restart HA with Dobby docked. With debug logging on, check whether an `UPDATEDPS reply` line and a push with 152/153 appear, and whether the card shows Docked within 10 s, or at once from the restored state.
- [ ] Restart HA while paused via the Eufy app: Start resumes on the first step, with no escalation in the log, if the query works.
- [ ] No reconnect loop after the query: at most 3 `Querying DPS` lines.
- [ ] Record the result in `docs/architecture/transport.md`. If UPDATEDPS does nothing, try the DP_QUERY variant or remove the T2267 flag.

## Status
Done; PR pending.

## Built (06/11/2026)
- Code and docs are as listed above.
- **Size:** S, ~30k actual (rough figure).
