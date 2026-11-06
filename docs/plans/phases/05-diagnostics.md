# Phase 05 — Diagnostics download (Phase 03 idea #9)

## Scope
Add HA's "Download diagnostics" (Settings → Devices & services → Robovac → ⋮). It produces a redacted JSON dump to attach to issues or to use for reverse-engineering DPS values (e.g. the DND capture in Phase 02).

## Design
- New `diagnostics.py` with `async_get_config_entry_diagnostics(hass, entry)`.
- Redact with `homeassistant.components.diagnostics.async_redact_data`: `CONF_ACCESS_TOKEN` (localKey), `CONF_PASSWORD`, `CONF_USERNAME`, `CONF_CLIENT_ID`, `CONF_MAC`. The entry title is the username, so redact it too.
- Per vacuum (from `hass.data[DOMAIN][CONF_VACS]`):
  - Device: full model code, matched model class, `robovac_features` (as flag names), `_tuya_command_codes`.
  - State: last raw DPS dict (`vacuum._dps`), `error_code`, connected flag, Tuya protocol version.
- If a vacuum entity failed to initialise (`UNSUPPORTED_MODEL` / `INVALID_KEY`), still include the model code and error, since that's the case where diagnostics help most.

## Acceptance criteria
- [ ] Diagnostics download works from the HA UI for the user's L60.
- [ ] The dump contains no localKey, password, username, client id or MAC (checked by searching the file for the known values).
- [ ] The dump includes raw DPS `"157"` and `"159"`.
- [ ] `python -m py_compile` passes; `docs/architecture/ha-entity.md` mentions diagnostics.

## Status
Planned, not built.

## Size
S, ~20-35k.
