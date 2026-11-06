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
