# Testing and verification

Rewritten 06/11/2026 (Phase 07) when the test suite and CI were added. Earlier text was moved verbatim from CLAUDE.md (26/09/2026).

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`. It uses Python 3.13 with `requirements_test.txt`, and runs:
1. `ruff check custom_components tests`. `ruff.toml` selects `E9` + `F` (Phase 07 baseline) and `S` (flake8-bandit, Phase 08); tighten one rule family per commit. Source `S` hits carry a per-line `# noqa: S… - reason`; tests may use bare `assert` (S101). `setup.py` is out of scope.
2. `python -m compileall -q custom_components tests`.
3. `pytest`. `pytest.ini` sets `asyncio_mode = auto` and `testpaths = tests`.
4. A separate `secrets` job runs gitleaks (version- and checksum-pinned) over the full history with values redacted. Reviewed false positives are in `.gitleaksignore`. See `security.md`.

Actions are pinned to full commit SHAs; Dependabot (`.github/dependabot.yml`) proposes updates weekly.

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
| `tests/test_security.py` | Phase 08: device `repr`/`str` omit the local key; config-flow skip path and Tuya cloud errors log no keys, URLs or bodies; Eufy refuses a non-HTTPS host; v1→v2 migration strips the password; broadcast validation and task tracking; IP change only after an authenticated probe, rate-limited, unknown gwId ignored; probe accepts only an encrypted reply (wrong key, plaintext spoof, EOF and refused all fail); bad length fields rejected and bad frames + EOF end the reader loop. |
| `tests/test_coordinator.py` | Phase 10: unique_ids/names unchanged; a push reaches listeners with no GET; battery sensor reads the coordinator and keeps its last value; watchdog polls only a quiet vacuum; `async_set_host` reconnects one vacuum; discovered IP applies without reload; the update listener ignores IP-only changes but reloads on others; full setup/unload keeps entity IDs. |
| `tests/test_control_entities.py` | Phase 11: Boost IQ switch state (unknown/on/off) and explicit writes; no entities for an unsupported model; L60 gets one of each; stop-return button needs a declared mode, sends the model value and cancels a running start; locate toggles; suction select options/current/writes; one refresh per burst; `start_new_clean` (from paused, still-paused timeout, cancelled by another command); `auto_clean`; full setup registers the entity IDs and services. |
| `tests/test_status_entities.py` | Phase 12: status sensor options, values and model `status_values`; docked/charging unknown then through a full cycle (Recharge is not docked, Completed is docked not charging); `connected` follows the socket, notifies listeners on disconnect and on connect, and a failing callback is contained; last-seen updates only on data; no status entities for an unsupported model; full setup registers the entity IDs. |
| `tests/test_diagnostics.py` | Phase 13: dump redacts every secret and keeps raw DPS 157/159; unsupported model still reported; `get_dps` returns, filters and raises HA errors; capture logs one line per change and stops when off; VERBOSE tracks any capturing vacuum; capture toggle applies without a reload. |
| `tests/test_proto.py` | Phase 14: known DPS values round-trip through the codec; decoded shapes (including DND); repeated fields and strings; malformed input rejected; prompt code extraction (31, 85, 40, timestamp-only); the last-prompt sensor keeps the previous prompt; capture log shows the decoded value. |
| `tests/test_model_modes.py` | Phase 09: all eight L60 models resolve the five mode keys; models without `mode_values` use the shared defaults; overrides merge key by key; labels follow raw values; `status_values` overrides; no raw L60 mode strings in `vacuum.py`. |
| `tests/test_config_flow.py` | User step: entry created (without the password), plus `invalid_auth`, `cannot_connect` and `unknown` errors, with `get_eufy_vacuums` mocked and integration setup patched out. |

## Manual testing on HA

1. Copy `custom_components/robovac/` into the HA instance's `custom_components/`.
2. Restart HA and watch the integration's behaviour, with debug logging for `custom_components.robovac` when needed.

Syntax check without the suite: `python -m py_compile custom_components/robovac/<file>.py`.
