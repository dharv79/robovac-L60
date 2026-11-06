# Phase 07 — Tests + lint in CI (Phase 03 idea #18)

## Scope
Add a test suite and a CI workflow so the binding process's "green CI" step actually checks something. Today `.github/workflows/` only has `release.yml`.

## Design
- `.github/workflows/ci.yml`: on push and PR, run `ruff check`, `python -m compileall custom_components`, and `pytest`.
- `requirements_test.txt` pinning `pytest-homeassistant-custom-component` (which pins a matching HA).
- **Lint baseline:** start with a minimal ruff rule set (`E9`, `F`) so the existing code passes on day one. Tighten later in separate commits.
- **Tests, no device needed:**
  - `tuyalocalapi.py`: `Message` encode/decode round-trip and AES with a fixed test key.
  - Do-not-break rules as tests:
    - #2: no `homeassistant` import under `vacuums/`.
    - #3: `getCommandCodes()` values are `str`.
    - #7: each `ROBOVAC_MODELS` key equals its class name and is 5 chars.
  - `vacuum.py`: state/activity mapping from a fake DPS dict; `async_send_command("boostIQ")` writes `{"159": <toggled bool>}` for an L60 class; unsupported models no-op.
  - `config_flow.py`: user step with the Eufy/Tuya cloud calls mocked (success, `invalid_auth`, `cannot_connect`).
  - Start escalation: turn the scratch start-sequence simulation (6 cases, plus Phase 04's cancel case) into tests for `_async_start_sequence` with a fake device that reports state pushes.
- Update `docs/architecture/testing.md` and the CLAUDE.md "Run / test" section.

## Acceptance criteria
- [ ] CI runs on a PR and is green.
- [ ] Deliberately breaking a do-not-break rule (e.g. an int DPS code) fails CI.
- [ ] Testing docs explain how to run the suite locally.

## Status
Planned, not built.

## Size
L, ~95-145k. Re-estimated 06/11/2026: start-sequence tests added from the brainstorm. Moved ahead of the refactor phases (08, 09) so they're covered by tests.
