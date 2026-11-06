# Phase 10 — Shared coordinator and modern HA patterns

## Scope
From the 06/11/2026 brainstorm (improvements: shared coordinator, `entry.runtime_data`, modern entity naming, poll only as fallback, per-vacuum IP update). Supersedes Phase 03 idea #5. Done before the new entity phases (11-17) so they're all built on it.

## Design
- **`RoboVacCoordinator(DataUpdateCoordinator)`** per vacuum:
  - Owns the `RoboVac` device, and pushes `async_set_updated_data` from `pushed_update_handler`.
  - Exposes a parsed state object: status, mode, battery, error and passthrough, parsed once instead of per property.
  - Vacuum and sensor become `CoordinatorEntity`s.
  - The battery still lives outside the vacuum entity (do-not-break #4): the sensor reads `coordinator.data.battery`. Update do-not-break #4's wording in CLAUDE.md and `do-not-break.md`.
- **`entry.runtime_data`** holds `{vac_id: coordinator}`, replacing `hass.data[DOMAIN][CONF_VACS]` (`vacuum.py:136`, `sensor.py:76`, `__init__.py:90`).
- **Poll only as a fallback**:
  - Coordinator `update_interval` is long (e.g. 5 min).
  - A watchdog forces a GET if no push has arrived for `REFRESH_RATE`.
  - Changing `iot_class` to `local_push` in `manifest.json` **needs the user's OK** (locked: do not modify manifests). Ask at build time; ship without it if declined.
- **`_attr_has_entity_name = True`** plus a translated name on the vacuum. Keep `unique_id`s unchanged so entity IDs don't change.
- **Per-vacuum IP update**: on a discovered IP change, `__init__.update_device` (`__init__.py:58-59`) reloads the whole entry. Instead, update that coordinator's device host and reconnect. Still persist the new IP with `async_update_entry`, but skip the reload (the update listener must ignore IP-only changes).

## Acceptance criteria
- [ ] Entity IDs and unique_ids unchanged after upgrade.
- [ ] Battery sensor updates on push without its own poll.
- [ ] Debug log shows no 60 s GETs while pushes are arriving.
- [ ] Changing the IP via discovery reconnects only that vacuum.
- [ ] CI green; `docs/architecture/ha-entity.md` and the CLAUDE.md code map updated.

## Status
Planned, not built.

## Size
L, ~90-140k.
