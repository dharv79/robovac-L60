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
- [x] Each fix above lands with the specific finding it closes referenced in the commit message.
- [ ] Finding #1's fix is verified against a real L60 (do-not-disturb, boost IQ confirmed to actually change device behaviour, not just "no error thrown"). **Still open — needs on-device access.**
- [x] `python -m py_compile` passes on every changed file (no test suite exists yet — see Phase 03 feature #18).
- [x] `docs/architecture/do-not-break.md` and the `vacuum.py` comment both updated to stop claiming the old codes are "L60-specific".

## What landed
- **#1**: `async_send_command` rewritten. `doNotDisturb`/`boostIQ`/`autoReturn` now look up their DPS code from `self._tuya_command_codes` and gate on `self._supports(...)` instead of writing hard-coded numbers. `edgeClean`/`smallRoomClean`/`autoClean` route through `_async_set_mode` (same mechanism as `clean_spot`/`start`) instead of a hard-coded MODE dps index. `roomClean` is now a guarded no-op: no supported model defines a DPS code for room-select cleaning today (confirmed by grep across every `vacuums/T*.py`), so rather than invent one it logs a warning and does nothing until a model adds that mapping (Phase 03 feature #11). `autoReturn` is similarly a no-op on every current model since no model defines `RobovacCommand.AUTO_RETURN` yet — this is correct: the old code wrote to DPS `"135"` on every model regardless, which was never right.
- **#7**: the fallback passthrough branch now logs a debug line when `command` isn't a numeric DPS code, instead of writing silently.
- **#3**: `TuyaDevice.__init__` guards `not local_key` before the length check; `RoboVacEntity.__init__` now catches `InvalidKey` the same way it catches `ModelNotSupportedException` (new `error_code = "INVALID_KEY"`, added to `errors.py`).
- **#2**: `get_user_info` and `get_device_info` in `eufywebapi.py` now pass `timeout=10`, matching `get_user_settings`.
- **#4**: `MessageDecodeFailed`'s two log sites dropped from `.error()` to `.debug()`.
- **#5**: dead `EMPTY_MAPPING` removed from `vacuum.py` (not claimed by any Phase 03 feature yet; trivial to re-add if feature #8 wants it).
- **#6**: orphaned `host` string removed from `strings.json`'s `config.step.user.data` (schema never asked for it).
- Follow-on cleanup: `json`/`time` imports in `vacuum.py` dropped (only used by the old `roomClean` JSON-RPC payload); `do-not-break.md` rule 6 (hard-coded L60 DPS codes) replaced with a rule describing the new lookup-based pattern; the matching "Conventions and gotchas" bullet removed from `CLAUDE.md`.

## Status
In progress. All six findings' code changes landed and compile clean. Finding #1's on-device verification (do-not-disturb / boost IQ actually toggling on a real L60) is still outstanding — needs the user to confirm live L60 access before this is called fully closed per the binding process (branch → implement/test → draft PR → green CI → merge → sync main → CI-replica test run → update plan docs → stop and report).

## Size
M, ~45k actual (6 code changes across 5 files + 2 doc files; on-device verification not yet done).
