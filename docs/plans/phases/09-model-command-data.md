# Phase 09 — Per-model command data

## Goal
Move the L60 DPS 152 mode strings out of `vacuum.py` into the model files, under semantic keys, and let a model override its status mapping. From the 06/11/2026 brainstorm; done after Phase 07 so the tests catch regressions.

## Scope
- `mode_values` on each L60 model, keyed by `ModeKey`: `start_auto`, `pause`, `resume`, `stop_return`, `return_home` (plus `standby` for the label).
- Shared defaults in `vacuums/base.py` (`DEFAULT_MODE_VALUES`, `MODE_LABELS`) so models without a key keep today's behaviour. Model files still import nothing from HA (do-not-break #2).
- `vacuum.py` looks values up by key and builds its mode label map from the model; the old `MODE_MAPPING` is gone.
- Optional per-model `status_values` (raw DPS 153 → status key), merged over `TUYA_STATUS_MAPPING`. `activity` still matches human-readable strings (do-not-break #5).
- Out of scope: moving `TUYA_STATUS_MAPPING` itself out of `vacuum.py`, and the plain-text `Spot` / `Edge` / `SmallRoom` modes of legacy models.

## Files touched
- `vacuums/base.py`: `ModeKey`, defaults, `resolve_mode_values`, `resolve_mode_labels`.
- `vacuums/T2266, T2267, T2275, T2276, T2277, T2278, T2320, T2351.py`: `mode_values`.
- `vacuum.py`: lookups by key; per-entity `_mode_values`, `_mode_labels`, `_status_values`.
- `tests/test_model_modes.py` (new), `docs/architecture/models.md`, `docs/architecture/testing.md`.

## Tests
- All eight L60 models resolve the five keys, and the values appear in the model's MODE value list.
- Models without `mode_values` use the defaults; partial overrides merge; labels follow raw values.
- The entity picks up model overrides for modes and `status_values`.
- No raw L60 mode strings remain in `vacuum.py`.
- The existing start-sequence, dock and pause tests pass unchanged (same wire values as v1.0.11).

## Acceptance criteria
- [x] No raw L60 mode strings left in `vacuum.py`.
- [x] Start / pause / resume / dock send the same values as v1.0.11 (existing exact-order tests unchanged and green). On-device check on Dobby still to do.
- [x] CI green, including the new tests; `docs/architecture/models.md` documents the new keys.

## Status
Done, merged (2a838be, PR #14); CI green. On-device check pending.

## Built (06/11/2026)
- 247 tests pass; ruff clean.
- Defaults live in `vacuums/base.py`, not `vacuum.py`, so the "no raw strings in `vacuum.py`" rule holds while legacy models keep working.
