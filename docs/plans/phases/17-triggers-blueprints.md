# Phase 17 — Device triggers and blueprints

## Scope
From the 06/11/2026 brainstorm (features: device triggers, bundled blueprints). Uses Phase 16's events.

## Design
- **`device_trigger.py`**: `cleaning_started`, `cleaning_finished`, `docked`, `error`, so they're selectable in the UI automation editor.
  - Event-based triggers come from Phase 16's events.
  - `docked` comes from Phase 12's binary sensor.
  - Strings in `strings.json` → `device_automation.trigger_type`.
- **Blueprints** in `blueprints/automation/robovac/` (repo root, linked from the README for one-click import; HACS doesn't install them):
  - notify when stuck/error;
  - clean when everyone leaves (a `person`/zone input) and dock when someone returns;
  - dock at a set time if still cleaning.
- Blueprints use only `vacuum.*` services and the device triggers above, so they work for any model.

## Acceptance criteria
- [ ] Each trigger fires in a test automation on Dobby.
- [ ] Each blueprint imports from its GitHub URL and runs on a test HA.
- [ ] README has a Blueprints section.

## Status
In progress (draft PR).

## Size
M, ~40-65k.

## Built (06/11/2026)
`device_trigger.py` (four triggers), three blueprints, README Blueprints section with import buttons. Tests in `tests/test_device_trigger.py` (325 total). Open on a real HA: each blueprint's import from its GitHub URL (works once this is on `main`) and a run of each; `clean_when_away` and `notify_on_error` are schema-validated only.
