# Phase 01 — Code review & audit

## Scope
Read every file under `custom_components/robovac/` and record concrete, file:line-anchored findings: correctness bugs, dead/stale code, misleading docs, and robustness gaps. No code changes in this phase — findings feed Phase 02.

## Status
Done (review complete, written up below). Not merged yet.

## Findings (most impactful first)

### 1. `async_send_command`'s custom DPS codes don't match any supported model — `vacuum.py:502-530`
The `edgeClean`, `smallRoomClean`, `autoReturn`, `doNotDisturb`, `boostIQ`, and `roomClean` branches hard-code Tuya DPS indexes (`"5"`, `"135"`, `"139"`/`"107"`, `"118"`, `"124"`). Grepping every file in `vacuums/` turns up **no model** that defines those codes for those commands — e.g. the L60 (`T2351`) uses DPS `157` for `DO_NOT_DISTURB` and `159` for `BOOST_IQ`, not `139`/`107`/`118`. Only `autoClean` (`"152"`) happens to coincide with the L60's `MODE` code by chance. In practice these six `vacuum.send_command` service calls are no-ops or write to unrelated/unknown DPS indexes on every model, including the L60 this fork targets.
- **Fix direction:** derive the DPS code from `self._tuya_command_codes[RobovacCommand.X]` (same pattern as every other write in this file) and gate behind `self._supports(RoboVacEntityFeature.X)`, instead of hard-coding numbers.
- The comment directly above (`# These DPS codes are L60-specific; see CLAUDE.md.`) is itself wrong given the above — needs correcting once the codes are fixed.

### 2. Two Eufy cloud HTTP calls have no timeout — `eufywebapi.py:39,45`
`get_user_settings` passes `timeout=1.5`, but `get_user_info` (line 33) and `get_device_info` (line 45) don't pass any timeout. `validate_input` runs this in an executor job during config flow, so a hung TCP connection to `home-api.eufylife.com` blocks that executor thread indefinitely — the config flow just spins with no error shown to the user.
- **Fix direction:** add a consistent timeout (e.g. 10s) to all three `requests` calls.

### 3. `TuyaDevice.__init__` raises `TypeError` instead of `InvalidKey` for a missing key — `tuyalocalapi.py:346`
`if len(local_key) != 16` assumes `local_key` is always a string. If a vacuum's `CONF_ACCESS_TOKEN` is ever `None` (e.g. cleared via options, or a future reauth flow lands it empty), this raises an unhandled `TypeError` instead of the intended `InvalidKey`, which `RoboVacEntity.__init__` doesn't catch (only `ModelNotSupportedException` is caught in `vacuum.py:193`) — the whole entity setup would fail unhandled.
- **Fix direction:** `if not local_key or len(local_key) != 16:` and make sure `RoboVacEntity.__init__` catches `InvalidKey` the same way it catches `ModelNotSupportedException`.

### 4. `MessageDecodeFailed` is logged at `.error()` for a condition the caller treats as routine — `tuyalocalapi.py:304-305, 310-311`
`Message.from_bytes` calls `device._LOGGER.error(e)` on a JSON/UTF-8 decode failure, but `_async_handle_message` (line 566-568) catches `MessageDecodeFailed` and just `continue`s — i.e. the caller considers this expected/recoverable (a garbled or partial packet). Logging it at ERROR on every occurrence will put red noise in HA logs for something that isn't actually a failure from the user's point of view.
- **Fix direction:** drop to `.debug()`, matching how `InvalidMessage` is already handled one branch up.

### 5. `EMPTY_MAPPING` is defined but never used — `vacuum.py:77-81`
`EMPTY_MAPPING` (dust bin / wash mop / dry mop DPS value → label) has no reader anywhere in the file. Dead code — either wire it up (see Phase 03 feature #8) or remove it.

### 6. `strings.json` declares a `host` field the schema never asks for — `custom_components/robovac/strings.json` (`config.step.user.data.host`)
`USER_SCHEMA` in `config_flow.py:58-63` only has `username`/`password`. The `host` string is orphaned translation text left over from an earlier flow shape.

### 7. Unbounded DPS passthrough from `async_send_command`'s fallback branch — `vacuum.py:531-532`
For any command not special-cased, `updates = [{command: params.get("value", "")}]` sends the caller-supplied `command` string directly as a DPS key with no validation that it's a known/numeric code. A typo'd service call (or a copy-pasted automation) silently writes to an arbitrary DPS index with no log line explaining what happened. Low severity (local network, requires an explicit `vacuum.send_command` call) but worth a guard + debug log so misfires are diagnosable.

### 8. Thirty near-identical model files invite copy-paste drift — `custom_components/robovac/vacuums/T22*.py`
Most `vacuums/T*.py` files are ~30 lines of near-duplicate dict literals. Already a vector for the kind of mismatch found in #1 (codes copied from the wrong source model). Not urgent, but a shared base/schema (see Phase 03 feature list) would reduce that risk over time.

## Acceptance criteria
- [x] Every `.py` file under `custom_components/robovac/` read at least once this phase.
- [x] Each finding has a file:line anchor and a concrete fix direction (no vague "consider refactoring").
- [x] No code changed in this phase — review only.

## Size
S, ~25k tokens actual (review + write-up, no code changes).
