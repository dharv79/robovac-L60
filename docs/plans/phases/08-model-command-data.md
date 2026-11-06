# Phase 08 — Per-model command data

## Scope
From the 06/11/2026 brainstorm (improvements: L60 codes into model files, per-model status/mode tables). Done after Phase 07 so the tests catch regressions.

## Design
- **Named mode values in model files**:
  - The L60 raw mode strings (`BBoCCAE=` start auto, `AggN` pause, `AggO` resume, `AggP` stop return, `AggG` go home) are hard-coded in `vacuum.py:447-512`.
  - Move them into the L60 model files' `commands[MODE]["values"]` (or a new `mode_values` dict) under semantic keys (`start_auto`, `pause`, `resume`, `stop_return`, `return_home`). `vacuum.py` looks them up by key.
  - Models without a key fall back to today's legacy strings. Model files still import nothing from HA (do-not-break #2).
- **Per-model status and mode mappings**: `STATUS_MAPPING` / `MODE_MAPPING` in `vacuum.py` mix L60 encoded values with older models' plain text.
  - Let a model file provide its own `status_values` / `mode_values`, merged over the shared defaults.
  - `activity` still matches human-readable strings (do-not-break #5).
- Add tests: every L60 model resolves all five mode keys; the legacy models still resolve `AggG`-style fallbacks.

## Acceptance criteria
- [ ] No raw L60 mode strings left in `vacuum.py`.
- [ ] Start / pause / resume / dock behave as in v1.0.11 on Dobby.
- [ ] CI green, including the new tests; `docs/architecture/models.md` documents the new keys.

## Status
Planned, not built.

## Size
M, ~40-70k.
