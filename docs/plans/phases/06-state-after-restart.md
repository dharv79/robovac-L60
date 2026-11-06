# Phase 06 — State after an HA restart

## Scope
From the 06/11/2026 brainstorm (features: query status on connect, restore last state). After an HA restart the vacuum shows unknown until Dobby pushes, because the L60's GET reply has no DPS 152/153.

## Design
- **Query on connect**:
  - After `async_connect`, try Tuya's DP-refresh/query commands for `["152", "153"]` (UPDATEDPS `0x12`; the 3.3 `DP_QUERY` with a `dpId` list as a fallback). Add the command constant(s) in `tuyalocalapi.py`.
  - Gate it per model: a flag in the L60 model files, not hard-coded L60 checks (do-not-break #2).
  - **Needs on-device experiments first.** Log what each variant returns; keep whichever makes Dobby report 152/153.
- **Restore last state** (fallback whatever the query outcome): `RoboVacEntity` also inherits `RestoreEntity`.
  - In `async_added_to_hass`, seed `tuya_state` from the last state's attributes.
  - Mark it stale: the next real push or GET replaces it, and it never blocks the start escalation (unknown still escalates).

## Acceptance criteria
- [ ] Restart HA with Dobby docked: the card shows Docked within 10 s (query works), or immediately from the restored state.
- [ ] Restart HA while paused via the Eufy app: Start resumes on the first step (no escalation in the log) if the query works.
- [ ] Findings recorded in `docs/architecture/transport.md` as a dated section.
- [ ] `python -m py_compile` passes.

## Status
Planned, not built.

## Size
S, ~25-45k (more if several query variants need testing).
