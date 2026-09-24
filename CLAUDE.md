# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration (HACS-compatible) for Eufy RoboVac vacuum cleaners, with particular focus on L60 support. It communicates with vacuums over the local network using the Tuya local API protocol, and authenticates via the Eufy cloud API to obtain device credentials.

The integration registers two HA platforms per vacuum: `vacuum` (the primary control entity) and `sensor` (a battery % diagnostic sensor).

## No Build or Test Infrastructure

There is no test suite, linter configuration, or build tooling. Development is done by:
1. Copying `custom_components/robovac/` into a Home Assistant instance's `custom_components/` directory
2. Restarting Home Assistant and observing integration behaviour

For syntax checking: `python -m py_compile custom_components/robovac/<file>.py`

## Architecture

### Communication layers (bottom to top)

**`tuyalocalapi.py`** — Raw Tuya protocol implementation. `TuyaDevice` maintains a persistent TCP socket to the vacuum (port 6668), encrypts/decrypts AES-ECB messages, manages a send queue with exponential backoff, and handles gratuitous push updates from the device. `TuyaCipher` handles the version-specific encryption. All I/O is async. Three long-lived loop tasks run per device — `process_queue` (send queue), `async_ping` (keepalive), `_async_handle_message` (socket reader) — and `async_disable` cancels them all. When the reader hits EOF/reset (the L60 drops the socket when it sleeps) it disconnects immediately so the next queued send reconnects; don't reintroduce retry-the-read-on-EOF, which busy-spins the event loop.

**`tuyalocaldiscovery.py`** — Listens on UDP ports 6666/6667 for Tuya broadcast packets to auto-discover device IP addresses. Decrypts broadcasts with a fixed UDP key and fires a callback when a known device is found.

**`robovac.py`** — `RoboVac` subclasses `TuyaDevice`, adding model-specific validation. Raises `ModelNotSupportedException` for unknown model codes. Exposes helpers to retrieve the model's supported commands, fan speeds, and HA feature flags.

**`eufywebapi.py` / `tuyawebapi.py`** — Used only during config flow setup to log into Eufy/Tuya cloud and retrieve the device `localKey` (16-char AES key). Once obtained, all runtime communication is local-only.

### Model definitions (`vacuums/`)

Each `T<model>.py` file defines a plain class (no base class) with two attributes:
- `robovac_features` — bitmask of `RoboVacEntityFeature` flags (controls which extra attributes are exposed in `extra_state_attributes`)
- `commands` — dict mapping `RobovacCommand` enum values to either an integer DPS code or a `{"code": int, "values": [...]}` dict

Model files must not import from `homeassistant`. HA feature flags are derived at runtime from `commands` in `RoboVacEntity._build_supported_features`. (A dead `homeassistant_features` attribute referencing `VacuumEntityFeature.BATTERY` took the whole integration down when HA 2026.9 removed that enum member.)

`vacuums/__init__.py` defines `ROBOVAC_MODELS`, the registry mapping model code strings to their classes, keyed by class name.

Older models (T21xx) use low DPS codes (2–106); newer L-series models like the L60 (T2267) use codes in the 150–179 range. Check an existing similar model before assigning codes to a new one.

### HA integration layer

**`vacuum.py`** — `RoboVacEntity` is the main entity. It instantiates `RoboVac`, builds `_tuya_command_codes` (a flat `RobovacCommand → str(DPS_code)` dict), and polls/receives push state via `update_entity_values()`. Status decoding uses a two-step mapping: raw base64 Tuya value → internal status key (`TUYA_STATUS_MAPPING`) → human-readable string (`STATUS_MAPPING`). The `activity` property then pattern-matches against those **human-readable strings** (e.g. `"Charging"`, `"Recharge"`) — not the internal keys.

State updates arrive via two paths: (1) polling — `async_update` → `async_update_vacuum` → `vacuum.async_get()` every `REFRESH_RATE` seconds; (2) push — the device sends unsolicited DPS packets which `TuyaDevice.async_gratuitous_update_state` handles, calling back into `pushed_update_handler`. `_dps` accumulates across both paths via `.update()`, so it holds all DPS values seen since connection, not just the latest message.

**`async_send_command` hard-coded DPS trap:** Several named commands (`edgeClean`, `smallRoomClean`, `autoClean`, `autoReturn`, `doNotDisturb`, `boostIQ`, `roomClean`) bypass `_tuya_command_codes` entirely and use hard-coded DPS integer strings (`"5"`, `"152"`, `"135"`, etc.). These are L60-specific and will be wrong for other models.

**`sensor.py`** — `RobovacBatterySensor` polls `hass.data[DOMAIN][CONF_VACS][id]._battery_level_cache` from the vacuum entity rather than communicating with the device directly.

**`config_flow.py`** — Two-step setup: initial credential flow calls Eufy/Tuya cloud APIs synchronously (via `async_add_executor_job`) to populate `CONF_VACS`. Options flow lets users set IP address and toggle autodiscovery per vacuum.

**`__init__.py`** — `async_setup` starts `TuyaLocalDiscovery` globally; when a broadcast is received for a known device with a changed IP, the config entry is updated and reloaded automatically. UDP ports 6666/6667 are required; if the `localtuya` integration is also installed it may hold these ports exclusively, breaking autodiscovery.

## Adding a New Model

1. Create `custom_components/robovac/vacuums/T<model>.py` following the pattern of an existing model (e.g. `T2267.py` for newer L-series models with higher DPS codes).
2. Set `robovac_features` by OR-ing relevant `RoboVacEntityFeature` values.
3. Map each supported `RobovacCommand` to its DPS code. For commands with multiple values, use `{"code": int, "values": [...]}`. For simple boolean/int commands, use just the integer code.
4. Add the class to `vacuums/__init__.py` — both the import and the tuple inside `ROBOVAC_MODELS`. The class name is the registry key, so it must be the first 5 characters of the model code as it appears in the Eufy app (e.g. `T2267`).

## Key Conventions

- DPS codes are stored and looked up as **strings** at runtime. `getCommandCodes()` converts all codes with `str()`. Always use `str(dps_code)` when constructing payloads.
- `RobovacCommand` is a `StrEnum`; use it as the key in both model `commands` dicts and `_tuya_command_codes`.
- Battery level is **not** set on the vacuum entity — it lives in `_battery_level_cache` and is read by the separate sensor entity. This is intentional to avoid HA deprecation warnings.
- `robovac_features` gates which extra state attributes appear in `extra_state_attributes`. A feature flag in `robovac_features` does not automatically mean the DPS code is mapped — both must be present. Raw-value attributes are table-driven via `PASSTHROUGH_ATTRIBUTES` in `vacuum.py`; add new ones there rather than as new properties.
- Entity commands go through `_async_send_dps(*dps_dicts)`, which queues the writes and schedules exactly one follow-up state refresh (exceptions from that refresh are caught and logged).
- The integration uses `iot_class: local_polling` but also receives gratuitous push updates from the device via `async_gratuitous_update_state`.
- After 4 consecutive update failures (`UPDATE_RETRIES`), the entity is marked unavailable. On startup, `async_added_to_hass` makes up to 5 warm-up attempts (1.5 s apart) before giving up — this handles the L60's tendency to sleep and not respond immediately.

## Code Output & Efficiency Directives

These directives govern how code changes and responses are delivered in this repository:

- Output only modified functions or specific blocks; never rewrite entire files unless fundamentally restructuring them.
- Do not echo back code, errors, or logs provided in the prompt.
- Omit boilerplate, import statements, and setup code unless they are being modified.
- Provide code edits directly without introductory or concluding explanations.
- **Workflow requirement:** Whenever a complex task is completed, or before starting a completely new substantive task in this session, explicitly remind the user to run the `/compact` command to compress the chat history.
