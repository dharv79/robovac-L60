# Phase 18 — Modern L60 dashboard

## Goal
Ship a ready-to-use, modern Lovelace dashboard for the L60, built from the entities added in Phases 11-17. Added at the user's request (06/11/2026); inserted after 17, so the old 18-21 became 19-22.

## Decisions (user, 06/11/2026)
- **Delivery:** Lovelace YAML views kept in the repo (`docs/dashboards/`), imported by the user. No bundled JS card, no auto-created dashboard.
- **Cards:** core Home Assistant cards only (tile, entities, history-graph, gauge, markdown, picture-elements if useful). No HACS frontend dependencies.
- **Content:** controls + status; consumables + history; Do Not Disturb + diagnostics.
- **Map:** not included. The L60 map data is not available locally.

## Scope
- One dashboard YAML (a single view, sections layout) with these blocks:
  - **Controls + status:** vacuum tile with start / pause / dock / locate, fan speed, Boost IQ, battery gauge, error and connectivity (Phases 11-12).
  - **Consumables + history:** brush / filter life, last cleaned, cleaning count, and a history graph of battery and activity (Phases 12, 16).
  - **DND + diagnostics:** Do Not Disturb switch and schedule (Phase 15), last decoded prompt, diagnostics sensors and capture controls (Phases 13-14).
- Entity IDs are written with a clear placeholder (e.g. `vacuum.dobby`) and a documented find-and-replace step. Blocks for entities that don't exist on a given install are marked optional.
- README section "Dashboard" with a screenshot and import steps (raw YAML in the dashboard editor).
- If Phase 15 stays on hold, the DND block ships commented out.

## Files touched
- `docs/dashboards/robovac-l60.yaml` (new), `docs/dashboards/README.md` (new).
- Root `README.md`: Dashboard section.
- `docs/architecture/ha-entity.md`: list of entities the dashboard uses, so renames update it.

## Tests
- A test loads the YAML and checks it parses, uses only allowed core card types, and that every entity it references (after placeholder substitution) is in a list of entities the integration creates.
- Manual: import on a test HA with Dobby and check each block renders (light and dark theme, phone width).

## Acceptance criteria
- [ ] Dashboard YAML imports without errors on current HA.
- [ ] Every referenced entity exists after Phases 11-17 (or is marked optional).
- [ ] README documents the import with a screenshot.
- [ ] CI green, including the YAML test.

## Status
Planned, not built. Depends on Phases 11, 12, 13, 14, 16 (15 optional).

## Size
M, ~40-65k.
