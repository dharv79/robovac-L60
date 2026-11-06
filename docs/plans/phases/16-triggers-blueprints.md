# Phase 16 — Device triggers and blueprints

## Scope
From the 06/11/2026 brainstorm (features: device triggers, bundled blueprints). Uses Phase 15's events.

## Design
- **`device_trigger.py`**: `cleaning_started`, `cleaning_finished`, `docked`, `error`, so they're selectable in the UI automation editor.
  - Event-based triggers come from Phase 15's events.
  - `docked` comes from Phase 11's binary sensor.
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
Planned, not built.

## Size
M, ~40-65k.
