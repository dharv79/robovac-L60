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

**`tuyalocalapi.py`** — Raw Tuya protocol implementation. `TuyaDevice` maintains a persistent TCP socket to the vacuum (port 6668), encrypts/decrypts AES-ECB messages, manages a send queue with exponential backoff, and handles gratuitous push updates from the device. `TuyaCipher` handles the version-specific encryption. All I/O is async.

**`tuyalocaldiscovery.py`** — Listens on UDP ports 6666/6667 for Tuya broadcast packets to auto-discover device IP addresses. Decrypts broadcasts with a fixed UDP key and fires a callback when a known device is found.

**`robovac.py`** — `RoboVac` subclasses `TuyaDevice`, adding model-specific validation. Raises `ModelNotSupportedException` for unknown model codes. Exposes helpers to retrieve the model's supported commands, fan speeds, and HA feature flags.

**`eufywebapi.py` / `tuyawebapi.py`** — Used only during config flow setup to log into Eufy/Tuya cloud and retrieve the device `localKey` (16-char AES key). Once obtained, all runtime communication is local-only.

### Model definitions (`vacuums/`)

Each `T<model>.py` file defines a plain class (no base class) with three attributes:
- `homeassistant_features` — bitmask of `VacuumEntityFeature` flags (legacy, not used by vacuum.py at runtime)
- `robovac_features` — bitmask of `RoboVacEntityFeature` flags (controls which extra attributes are exposed)
- `commands` — dict mapping `RobovacCommand` enum values to either an integer DPS code or a `{"code": int, "values": [...]}` dict

`vacuums/__init__.py` defines `ROBOVAC_MODELS`, the registry mapping model code strings to their class instances.

### HA integration layer

**`vacuum.py`** — `RoboVacEntity` is the main entity. It instantiates `RoboVac`, builds `_tuya_command_codes` (a flat `RobovacCommand → str(DPS_code)` dict), and polls/receives push state via `update_entity_values()`. Status decoding uses a two-step mapping: raw base64 Tuya value → internal status key (`TUYA_STATUS_MAPPING`) → human-readable string (`STATUS_MAPPING`).

**`sensor.py`** — `RobovacBatterySensor` polls `hass.data[DOMAIN][CONF_VACS][id]._battery_level_cache` from the vacuum entity rather than communicating with the device directly.

**`config_flow.py`** — Two-step setup: initial credential flow calls Eufy/Tuya cloud APIs synchronously (via `async_add_executor_job`) to populate `CONF_VACS`. Options flow lets users set IP address and toggle autodiscovery per vacuum.

**`__init__.py`** — `async_setup` starts `TuyaLocalDiscovery` globally; when a broadcast is received for a known device with a changed IP, the config entry is updated and reloaded automatically.

## Adding a New Model

1. Create `custom_components/robovac/vacuums/T<model>.py` following the pattern of an existing model (e.g. `T2267.py` for newer L-series models with higher DPS codes).
2. Set `robovac_features` by OR-ing relevant `RoboVacEntityFeature` values.
3. Map each supported `RobovacCommand` to its DPS code. For commands with multiple values, use `{"code": int, "values": [...]}`. For simple boolean/int commands, use just the integer code.
4. Add the class to `vacuums/__init__.py` — both the import and the `ROBOVAC_MODELS` dict entry. The dict key must be the first 5 characters of the model code as it appears in the Eufy app (e.g. `"T2267"`).

## Key Conventions

- DPS codes are stored and looked up as **strings** at runtime. `getCommandCodes()` converts all codes with `str()`. Always use `str(dps_code)` when constructing payloads.
- `RobovacCommand` is a `StrEnum`; use it as the key in both model `commands` dicts and `_tuya_command_codes`.
- Battery level is **not** set on the vacuum entity — it lives in `_battery_level_cache` and is read by the separate sensor entity. This is intentional to avoid HA deprecation warnings.
- `robovac_features` gates which extra state attributes appear in `extra_state_attributes`. A feature flag in `robovac_features` does not automatically mean the DPS code is mapped — both must be present.
- The integration uses `iot_class: local_polling` but also receives gratuitous push updates from the device via `async_gratuitous_update_state`.

## Branch

Active development branch: `claude/add-claude-documentation-pqqQd`. Push to this branch.
