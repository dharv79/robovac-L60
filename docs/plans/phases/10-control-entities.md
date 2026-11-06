# Phase 10 — Control entities + robovac services (Phase 03 idea #1; was Phase 04)

## Scope
Replace "`vacuum.send_command` with a magic string" for Boost IQ with a real `switch` entity, and register typed entity services for the remaining named commands. Extended 06/11/2026 with brainstorm features: a stop-return-to-dock button, a suction select and a `start_new_clean` service. Built on Phase 09's coordinator; entities read `coordinator.data` instead of `hass.data`.

## Design
- **New `switch.py` platform**, added to `PLATFORMS` in `__init__.py`. One switch per vacuum per supported toggle. For now that's Boost IQ only:
  - DND is excluded until DPS 157's protobuf encoding is known (Phase 02, "DND finding").
  - `AUTO_RETURN` has no DPS code on any model.
  - Created only when `_supports(BOOST_IQ)` and `_tuya_command_codes` has the code.
- Mirror `sensor.py`: find the vacuum entity through `hass.data[DOMAIN][CONF_VACS][vac_id]`. State comes from `vac_entity._passthrough[ATTR_BOOST_IQ]`.
  - `None` means unknown, so the switch state is unknown. Don't go through `extra_state_attributes`, which hides `False` (`vacuum.py:261`).
- `turn_on`/`turn_off` write an **explicit** bool via `vac_entity._async_send_dps({code: True|False})`. The existing `boostIQ` send_command stays a toggle for backwards compatibility.
- Entity services (`platform.async_register_entity_service` in `vacuum.py`) plus `services.yaml`: `robovac.edge_clean`, `robovac.small_room_clean`, `robovac.auto_clean`, routed to the existing `_async_set_mode` branches.
  - **Open decision:** the L60 model files don't declare `EDGE`/`SMALL_ROOM`, so these no-op on Dobby and can't be tested on the user's hardware. Confirm with the user whether to ship them or drop them before building.
- **`button.py`**:
  - "Stop return to dock" sends the model's `stop_return` mode value (Phase 08). Created only where the model defines it.
  - "Locate", for models with `LOCATE`.
- **`select.py`**: suction level, with options from the model's fan speeds; it writes through `async_set_fan_speed`.
- **`robovac.start_new_clean`** entity service: throws away a paused task and starts fresh.
  - Sequence: `stop_return`/stop, wait for a non-paused state, then `start_auto`.
  - Uses Phase 04's cancellable task.
- Entity names go in `strings.json` / `translations/en.json` (`entity.switch.boost_iq.name`, etc.).

## Acceptance criteria
- [ ] `switch.living_room_dobby_boost_iq` (or similar) appears; no switch on models without `BOOST_IQ`.
- [ ] HA switch state matches the Eufy app at startup.
- [ ] Turning it on/off from HA changes the Eufy app. Changing it in the app updates HA within `REFRESH_RATE`.
- [ ] Stop-return button stops Dobby returning to dock; the suction select matches the Eufy app both ways.
- [ ] `start_new_clean` while paused starts a fresh clean (the Eufy app shows a new session).
- [ ] CI green.
- [ ] `docs/architecture/ha-entity.md` documents the new platforms; the CLAUDE.md code map lists `switch.py`, `button.py`, `select.py`.

## Status
Planned, not built.

## Size
M, ~50-80k. Re-estimated 06/11/2026 (was S, ~25-45k): button, select and `start_new_clean` added.
