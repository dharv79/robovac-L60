# Phase 02 — Apply fixes from the code review

## Scope
Implement fixes for the findings in `phases/01-code-review.md`, in priority order. This phase touches live-device command paths (finding #1 in particular rewrites what DPS codes get written to the vacuum), so it needs a real L60 to validate against before merge — per the binding process, branch → implement/test → draft PR → green CI → merge → sync main → CI-replica test run → update plan docs → stop and report.

## Planned work (priority order)
1. **Finding #1** — rewrite `edgeClean`/`smallRoomClean`/`autoReturn`/`doNotDisturb`/`boostIQ`/`roomClean` in `vacuum.py:async_send_command` to look up DPS codes from `self._tuya_command_codes`, gated by `self._supports(...)`, instead of hard-coded numbers. Fix the stale comment above it. **Highest value, needs on-device testing** — these commands are currently broken for the L60.
2. **Finding #3** — guard `TuyaDevice.__init__` against a missing/None `local_key`; catch `InvalidKey` in `RoboVacEntity.__init__` alongside `ModelNotSupportedException`.
3. **Finding #2** — add a timeout to `get_user_info` and `get_device_info` in `eufywebapi.py`.
4. **Finding #4** — drop the `MessageDecodeFailed` log line from `.error()` to `.debug()`.
5. **Finding #7** — validate/guard the fallback DPS passthrough in `async_send_command`, log what key it wrote.
6. **Finding #5 / #6** — remove dead `EMPTY_MAPPING` (unless claimed by a Phase 03 feature first) and the orphaned `host` string.

## Acceptance criteria
- [ ] Each fix above lands with the specific finding it closes referenced in the commit message.
- [ ] Finding #1's fix is verified against a real L60 (do-not-disturb, boost IQ, auto-return, edge/small-room clean, room clean all confirmed to actually change device behaviour, not just "no error thrown").
- [ ] `python -m py_compile` passes on every changed file (no test suite exists yet — see Phase 03 feature #18).
- [ ] `docs/architecture/do-not-break.md` and the `vacuum.py` comment both updated to stop claiming the old codes are "L60-specific".

## Status
Planned, not built. Waiting on the user to confirm which items to take (all six, or a subset) and confirm access to a live L60 for on-device verification of #1 before this phase starts.

## Size
M, ~40-70k (6 small-to-medium code changes across 2 files, plus on-device verification round-trips).
