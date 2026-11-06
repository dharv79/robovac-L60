# Testing and verification

Rewritten 06/11/2026 (Phase 07) when the test suite and CI were added. Earlier text was moved verbatim from CLAUDE.md (26/09/2026).

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`. It uses Python 3.13 with `requirements_test.txt`, and runs:
1. `ruff check custom_components tests`. The `ruff.toml` baseline is `E9` + `F` only, chosen so the existing code passes; tighten it one rule family per commit. `setup.py` is out of scope.
2. `python -m compileall -q custom_components tests`.
3. `pytest`. `pytest.ini` sets `asyncio_mode = auto` and `testpaths = tests`.

There's no formatter check yet, because the repo isn't black/ruff-formatted. Adding one means a reformat-only commit first.

## Running locally

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check custom_components tests
pytest            # or: pytest tests/test_vacuum.py -k start
```

- `pytest-homeassistant-custom-component` pins a matching `homeassistant`, which needs Python 3.13 for the pinned 0.13.316 / HA 2026.2.3.
- Tests need no device and no network. The cloud APIs are mocked, and the transport is faked or disabled.
- Flaky tests get the framework's retry (e.g. `pytest-rerunfailures`). Never skip or remove them.

## Test map

| Test file | Covers |
|---|---|
| `tests/conftest.py` | Fixtures: `entity` (a T2267 `RoboVacEntity` with fake writes and refreshes), `FakeDevice`, which replays Dobby's mode→status transitions as pushes, `attach()`, `make_item()`, `TEST_KEY` (fake). |
| `tests/test_do_not_break.py` | CLAUDE.md rules: #1 EOF disconnects without retrying the read; #2 no `homeassistant` import in `vacuums/*.py`; #3 `getCommandCodes()` values are `str` for every model; #6 `async_disable` cancels the three loop tasks; #7 registry key = class name, 5 chars. #4 is in `test_vacuum.py`; #5 is covered by the activity mapping tests. |
| `tests/test_tuyalocalapi.py` | AES round-trip (SET with the 3.3 header, GET without); device-frame decode; CRC and truncation rejection; SET bytes round-trip; `Message.summary`; queue stale-SET replacement, partial overlap and cap (Phase 04); backoff jitter and cap, and a push clearing the backoff and waking the queue (Phase 05); UPDATEDPS on connect, capped and missing-only (Phase 06). |
| `tests/test_vacuum.py` | Status DPS → activity mapping; battery cache (#4); consumables JSON; Boost IQ toggles DPS 159; unsupported model is inert; one refresh per burst; start sequence from 6 states with exact command order; Dock, a raw mode write or a second start during a start; fan speed doesn't cancel; unavailable/recovered logged once; warm-up in the background (Phase 05); restored state is display-only (Phase 06). |
| `tests/test_config_flow.py` | User step: entry created, plus `invalid_auth`, `cannot_connect` and `unknown` errors, with `get_eufy_vacuums` mocked and integration setup patched out. |

## Manual testing on HA

1. Copy `custom_components/robovac/` into the HA instance's `custom_components/`.
2. Restart HA and watch the integration's behaviour, with debug logging for `custom_components.robovac` when needed.

Syntax check without the suite: `python -m py_compile custom_components/robovac/<file>.py`.
