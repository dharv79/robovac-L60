# Model definitions (`vacuums/`)

Moved verbatim from CLAUDE.md (26/09/2026).

Each `T<model>.py` file defines a plain class (no base class) with two attributes:
- `robovac_features` — bitmask of `RoboVacEntityFeature` flags (controls which extra attributes are exposed in `extra_state_attributes`)
- `commands` — dict mapping `RobovacCommand` enum values to either an integer DPS code or a `{"code": int, "values": [...]}` dict

Model files must not import from `homeassistant`. HA feature flags are derived at runtime from `commands` in `RoboVacEntity._build_supported_features`.

`vacuums/__init__.py` defines `ROBOVAC_MODELS`, the registry mapping model code strings to their classes, keyed by class name.

Older models (T21xx) use low DPS codes (2–106); newer L-series models like the L60 (T2267) use codes in the 150–179 range. Check an existing similar model before assigning codes to a new one.

## Adding a New Model

1. Create `custom_components/robovac/vacuums/T<model>.py` following the pattern of an existing model (e.g. `T2267.py` for newer L-series models with higher DPS codes).
2. Set `robovac_features` by OR-ing relevant `RoboVacEntityFeature` values.
3. Map each supported `RobovacCommand` to its DPS code. For commands with multiple values, use `{"code": int, "values": [...]}`. For simple boolean/int commands, use just the integer code.
4. Add the class to `vacuums/__init__.py` — both the import and the tuple inside `ROBOVAC_MODELS`. The class name is the registry key, so it must be the first 5 characters of the model code as it appears in the Eufy app (e.g. `T2267`).

## HA 2026.9 `VacuumEntityFeature.BATTERY` crash (v1.0.6, PR #3)

A dead `homeassistant_features` attribute referencing `VacuumEntityFeature.BATTERY` took the whole integration down when HA 2026.9 removed that enum member. The attribute was removed from all model files; feature flags are now derived from `commands` only.

## Optional model attributes

- `query_dps_on_connect`: a tuple of DPS codes the device should be asked to push after each connect, for codes its GET reply omits (`tuyalocalapi._async_query_dps`, UPDATEDPS `0x12`). Set on T2267 as `(152, 153)`. Leave it unset for other models until verified on that model.
- `mode_values`: DPS 152 values by semantic key, using `ModeKey` from `vacuums/base.py`: `start_auto`, `pause`, `resume`, `stop_return`, `return_home` (plus `standby`, label only). Set on all eight L60 models (T2266, T2267, T2275-T2278, T2320, T2351). A model without it, or without a given key, falls back to `DEFAULT_MODE_VALUES` in `base.py` (the L60 strings, i.e. today's behaviour). `vacuum.py` looks values up by key and builds the mode label map from them (`resolve_mode_values`, `resolve_mode_labels`), so there are no raw mode strings in `vacuum.py`. Partial dicts are fine: they merge over the defaults.
- `status_values`: optional dict of raw DPS 153 value → status key (e.g. `"AA=="` → `"STANDBY"`), merged over the shared `TUYA_STATUS_MAPPING` in `vacuum.py`. `activity` still matches the human-readable `STATUS_MAPPING` strings (do-not-break #5). No model sets it yet.

## DPS 178 last prompt and the protobuf codec (Phase 14, 06/11/2026)
- `proto.py` decodes the L60's base64 values (a length byte, then a protobuf message) to `{field: value}` dicts and encodes them back (`decode_prefixed`, `encode_prefixed`). Length-delimited fields become nested dicts when they parse cleanly, otherwise bytes; repeated fields become lists. The DND default `DgoAEgoKABICCBYaAggI` decodes to `{1: b"", 2: {1: b"", 2: {1: 22}, 3: {1: 8}}}`.
- DPS 178 layout (`RobovacCommand.LAST_PROMPT`, all eight L60 models): field 1 is an opaque varint (about 1.2e17, probably a timestamp; unmapped), field 2 is one byte, the prompt code. A message with no field 2 carries no prompt, and the sensor keeps the previous one.
- Known codes (`PROMPT_TEXT` in `coordinator.py`): 31 = "Can't start while recharging". Seen but not yet named: 85, 40. Unknown codes show as `code N`. Name more by turning capture mode on, triggering the prompt in the Eufy app and reading the log.
