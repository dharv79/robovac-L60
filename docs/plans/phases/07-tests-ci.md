# Phase 07 — Tests + lint in CI (Phase 03 idea #18)

## Goal
Add a test suite and a CI workflow, so the binding process's "green CI" step actually checks something. Before this phase `.github/workflows/` only had `release.yml`, and PRs #9-#11 were merged on local checks alone.

## Scope
- **CI:** `.github/workflows/ci.yml` runs on pull requests and on pushes to `main`. It uses Python 3.13 with `permissions: contents: read` and a 15-minute timeout, and runs `ruff check custom_components tests`, `python -m compileall`, and `pytest`.
- **Tooling:**
  - `requirements_test.txt` pins `pytest-homeassistant-custom-component==0.13.316` (HA 2026.2.3) and `ruff==0.16.9`.
  - `pytest.ini` sets asyncio auto mode.
  - `ruff.toml` sets the baseline to `E9` + `F`, which the existing code passes. `setup.py` is left out of the lint scope (3 unused imports).
  - `.gitignore` adds the tool caches.
- **Tests:** 169 in total, and no device needed.
  - **Do-not-break:** #1, #2 (per model file), #3 and #7 (per model), #6, and #4 in the vacuum tests.
  - **Transport:** AES round-trip; frame decode and rejection; queue (Phase 04); backoff and push reset (Phase 05); UPDATEDPS (Phase 06).
  - **Entity:** activity mapping; Boost IQ writes `{"159": <toggled>}`; unsupported model is inert; refresh coalescing.
  - **Start escalation:** the 6 start-sequence cases with exact command order, plus the Dock cancel, raw-mode cancel, double start and fan-speed cases. These replace the Phase 04-06 scratch simulations.
  - **Availability and restore:** log once, background warm-up, restored state.
  - **Config flow:** success, `invalid_auth`, `cannot_connect`, `unknown`.
- **Deviations from the original plan:**
  - No formatter check, because the repo isn't formatted; adding one needs a reformat-only commit first.
  - Actions are still on version tags; Phase 08 pins them to SHAs.

## Files touched
- `.github/workflows/ci.yml`, `requirements_test.txt`, `pytest.ini`, `ruff.toml`, `.gitignore`.
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_do_not_break.py`, `tests/test_tuyalocalapi.py`, `tests/test_vacuum.py`, `tests/test_config_flow.py`. All have the Apache 2.0 header.
- `docs/architecture/testing.md` (rewritten: CI, local runs, test map); `CLAUDE.md` ("Run / test" section and the topic table).

## Tests
- **Locally (Python 3.13 venv, the CI's requirements):** `ruff check custom_components tests` is clean; `compileall` passes; `pytest` passes 169 tests in ~8 s.
- **Mutation checks, both reverted:**
  - Dropping `str()` from `getCommandCodes` (breaking #3) fails 59 tests.
  - Adding `import homeassistant` to `T2267.py` (breaking #2) fails 1 test.
- **CI:** green on the PR (see Status).

## Status
Done; PR pending.

## Built (06/11/2026)
- Everything is as listed above.
- **Size:** M, ~60k actual (rough figure); estimated L, ~95-145k. It came in under because the Phase 04-06 simulations had already worked out the fakes.
