# Phase 17 — Reauth / reconfigure flow + IP connection test (Phase 03 idea #2; was Phase 06)

## Scope
Refresh Eufy credentials and each vacuum's localKey without deleting and re-adding the integration, keeping per-vacuum options and entity IDs. Extended 06/11/2026 with the brainstorm's "test the connection when changing the IP" feature.

## Design
- **`async_step_reconfigure`** (user-started from the integration's ⋮ menu): asks for the password only. The username is fixed, since it's the entry's unique_id (`config_flow.py:191`). Re-runs `validate_input` / `get_eufy_vacuums`.
- **`async_step_reauth` + `async_step_reauth_confirm`**: the same form, started automatically when a vacuum hits `InvalidKey` (`RoboVacEntity.__init__`, `error_code = "INVALID_KEY"`) via `entry.async_start_reauth(hass)`.
  - A rotated localKey usually shows up as decode failures, not `InvalidKey`, so reconfigure is the main path. Reauth is a bonus.
- **Merge, don't replace**, `entry.data[CONF_VACS]`:
  - Vacuums still on the account get a fresh `CONF_ACCESS_TOKEN`/model/name, but keep their existing `CONF_IP_ADDRESS` and `CONF_AUTODISCOVERY`.
  - New vacuums are added.
  - Vacuums no longer on the account are dropped, with a log line.
- Finish with `async_update_reload_and_abort`. If the account differs from the entry's unique_id, abort with `wrong_account`.
- **IP connection test** in the per-vacuum options step:
  - Before saving a new IP, open a throwaway `RoboVac` connection with the stored localKey and do one GET, with a ~5 s timeout.
  - On failure, show `cannot_connect` on the form and save nothing.
  - Skip the test when autodiscovery is on and the IP is unchanged.
- `strings.json` / `translations/en.json`: new step text, plus `reauth_successful`, `reconfigure_successful` and `wrong_account` abort strings.

## Acceptance criteria
- [ ] Reconfigure with the correct password: the entry reloads, the vacuum works, its IP/autodiscovery options are unchanged, and `vacuum.living_room_dobby` keeps its entity ID.
- [ ] A wrong password shows `invalid_auth` on the form; nothing is written.
- [ ] Entering a wrong IP in options shows `cannot_connect`, and the old IP is kept; the correct IP saves.
- [ ] `python -m py_compile` passes; `docs/architecture/ha-entity.md` config-flow section updated.

## Status
Planned, not built.

## Size
M, ~55-85k. Re-estimated 06/11/2026 (was M, ~45-70k): IP connection test added.
