# Phase 13 — Diagnostics + capture tools (Phase 03 idea #9; was Phase 05)

## Scope
Add HA's "Download diagnostics" (Settings → Devices & services → Robovac → ⋮). It produces a redacted JSON dump to attach to issues or to use for reverse-engineering DPS values (e.g. the DND capture in Phase 02). Extended 06/11/2026 with brainstorm features: a `robovac.get_dps` service and a capture-mode option. Together these are the capture tooling that Phases 14 and 15 depend on.

## Design
- New `diagnostics.py` with `async_get_config_entry_diagnostics(hass, entry)`.
- Redact with `homeassistant.components.diagnostics.async_redact_data`: `CONF_ACCESS_TOKEN` (localKey), `CONF_PASSWORD`, `CONF_USERNAME`, `CONF_CLIENT_ID`, `CONF_MAC`. The entry title is the username, so redact it too.
- Per vacuum (from `entry.runtime_data`, after Phase 10):
  - Device: full model code, matched model class, `robovac_features` (as flag names), `_tuya_command_codes`.
  - State: last raw DPS dict (`vacuum._dps`), `error_code`, connected flag, Tuya protocol version.
- If a vacuum entity failed to initialise (`UNSUPPORTED_MODEL` / `INVALID_KEY`), still include the model code and error, since that's the case where diagnostics help most.
- **`robovac.get_dps`** entity service with `supports_response=SupportsResponse.ONLY`: forces a GET and returns the raw DPS dict, optionally filtered by a `codes` list. Usable from Developer Tools → Actions.
- **Capture mode**, a per-vacuum option in the options flow (default off). When on:
  - logs every DPS change at `info` as `code: old → new`;
  - adds base64/protobuf-decoded text once Phase 14 lands;
  - sets Phase 05's `VERBOSE` transport logging.

## Acceptance criteria
- [ ] Diagnostics download works from the HA UI for the user's L60.
- [ ] The dump contains no localKey, password, username, client id or MAC (checked by searching the file for the known values).
- [ ] The dump includes raw DPS `"157"` and `"159"`.
- [ ] `robovac.get_dps` returns DPS 157/159 for Dobby in Developer Tools.
- [ ] Capture mode logs a DND change from the Eufy app as one readable line; turning it off stops the logging without a restart.
- [ ] `python -m py_compile` passes; `docs/architecture/ha-entity.md` mentions diagnostics.

## Status
In progress (draft PR).

## Size
M, ~40-65k. Re-estimated 06/11/2026 (was S, ~20-35k): `get_dps` service and capture mode added.
