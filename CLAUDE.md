# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Maintaining this file

- This file is injected on every turn: keep it an index of durable, load-bearing facts (summary, file map, do-not-break rules, conventions, how to run). Stay under ~1,000 lines.
- No bug write-ups, diagnosis narratives, old-vs-new code or feature history here. Those go in git history and `docs/architecture/<topic>.md` (as a dated section, e.g. "Feature X (DD/MM/YYYY)").
- Before adding a paragraph ask: "Does every future turn need this?" If not, put it in the topic file.
- Read a topic file only when about to change that area. Multi-phase work lives in `docs/plans/` — read `docs/plans/README.md` first if mid-plan.
- Re-audit every few phases; move anything historical out.

## What This Is

Home Assistant custom integration (HACS) for Eufy RoboVac vacuums, focused on the L60. Local control over the Tuya local protocol (TCP 6668, AES); Eufy/Tuya cloud is used only at setup to fetch the device `localKey`. Python, async, no dependencies beyond HA. Registers `vacuum` and `sensor` (battery %) platforms per vacuum.

## Code map (`custom_components/robovac/`)

- `tuyalocalapi.py` — `TuyaDevice`: persistent socket, cipher, send queue, keepalive, push updates.
- `tuyalocaldiscovery.py` — UDP 6666/6667 broadcast listener for IP autodiscovery.
- `robovac.py` — `RoboVac(TuyaDevice)`: model validation, command/fan-speed/feature helpers.
- `eufywebapi.py` / `tuyawebapi.py` — cloud login at config-flow time only.
- `vacuum.py` — `RoboVacEntity`: state decoding, commands, polling + push.
- `sensor.py` — battery sensor reading the vacuum entity's `_battery_level_cache`.
- `config_flow.py` — credential flow + per-vacuum options (IP, autodiscovery).
- `__init__.py` — starts discovery; reloads entry on IP change.
- `vacuums/T*.py` + `vacuums/__init__.py` — per-model DPS maps and `ROBOVAC_MODELS` registry.

## Topic docs

| Topic | File | Covers |
|---|---|---|
| Transport | `docs/architecture/transport.md` | Tuya socket, loop tasks, discovery, cloud APIs |
| Models | `docs/architecture/models.md` | Model file format, DPS ranges, adding a new model |
| HA entity | `docs/architecture/ha-entity.md` | Status mapping, polling/push, commands, sensor, config flow |
| Do-not-break | `docs/architecture/do-not-break.md` | Reasoning behind each rule below |
| Testing | `docs/architecture/testing.md` | Manual HA testing, syntax check, test file list |
| Releases | `docs/architecture/releases.md` | Release-branch workflow, version history |
| Plans | `docs/plans/README.md` | Phase status, locked decisions, process |

## Do-not-break

1. On socket EOF/reset, disconnect — never retry the read (`tuyalocalapi._async_handle_message`).
2. Model files never import `homeassistant`; HA features derive from `commands` (`RoboVacEntity._build_supported_features`).
3. DPS codes are `str` at runtime (`getCommandCodes`, `_tuya_command_codes`); always `str(dps_code)` in payloads.
4. Battery lives in `_battery_level_cache` / `sensor.py`, never on the vacuum entity.
5. `activity` matches `STATUS_MAPPING` human-readable strings, not internal keys (`vacuum.py`).
6. `async_disable` cancels all three loop tasks (`process_queue`, `async_ping`, `_async_handle_message`).
7. `ROBOVAC_MODELS` key = class name = first 5 chars of the model code.

## Conventions and gotchas

- `RobovacCommand` is a `StrEnum`; key both model `commands` and `_tuya_command_codes` with it.
- Several `async_send_command` names use hard-coded L60 DPS codes — wrong for other models.
- Entity commands go through `_async_send_dps(*dps_dicts)` (one follow-up refresh).
- Add raw-value attributes to `PASSTHROUGH_ATTRIBUTES`, not new properties; they need both a `robovac_features` flag and a mapped DPS code.
- `localtuya` may hold UDP 6666/6667 and break autodiscovery.

## Run / test

No test suite, linter or build. Copy `custom_components/robovac/` into an HA instance and restart. Syntax check: `python -m py_compile custom_components/robovac/<file>.py`.

## Code Output & Efficiency Directives

- Output only modified functions or specific blocks; never rewrite entire files unless fundamentally restructuring them.
- Do not echo back code, errors, or logs provided in the prompt.
- Omit boilerplate, import statements, and setup code unless they are being modified.
- Provide code edits directly without introductory or concluding explanations.
- Do not re-derive established facts or re-open locked decisions (`docs/plans/README.md`).
- **Workflow requirement:** Whenever a complex task is completed, or before starting a completely new substantive task in this session, explicitly remind the user to run the `/compact` command to compress the chat history.
- At every stop, report the phase status table in the format defined in `docs/plans/README.md`, then open items, remaining context tokens, ask which phase next, and remind about `/compact`.
