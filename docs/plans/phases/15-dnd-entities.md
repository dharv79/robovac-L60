# Phase 15 — Do Not Disturb entities

## Scope
From the 06/11/2026 brainstorm (feature: DND start/end and on/off). Resolves the Phase 02 DND finding. Blocked on Phase 14's decoder and on DPS 157 captures.

## Design
- Capture DPS 157 with Phase 13's capture mode while changing DND in the Eufy app:
  - toggle on and off
  - change the start time
  - change the end time
- Decode the captures with Phase 14's decoder.
- Entities:
  - a `switch` for DND on/off;
  - two `time` entities (start, end), on a new `time.py` platform.
  - Each write re-encodes the full 157 message from the current decoded value, so unchanged fields are preserved.
- Make `async_send_command("doNotDisturb")` use the same encoder, replacing today's untested raw write.
- If captures show the encoding differs between firmware versions, ship read-only entities and log a warning on write.

## Acceptance criteria
- [ ] Changing DND in HA changes the Eufy app, and the other way round.
- [ ] Unchanged fields of 157 survive a write (compare before/after captures).
- [ ] CI green with encode tests from the real captures; `docs/architecture/models.md` documents 157.

## Status
On hold (needs DPS 157 captures and Phase 14).

## Size
M, ~40-70k.
