# Phase 05 — Startup and connection resilience

## Scope
From the 06/11/2026 brainstorm (improvements: non-blocking startup, safer consumables parse, reconnect behaviour, log noise).

## Design
- **Don't block HA startup**: `async_added_to_hass` (`vacuum.py:276-302`) does up to 5 forced updates with 1.5 s sleeps inline. Move the warm-up to `hass.async_create_background_task`, and start the entity as unavailable until the first good update. Cancel the task in `async_will_remove_from_hass`.
- **Safer consumables parse**: replace `ast.literal_eval` on device data (`vacuum.py:419`) with `json.loads`. Fall back to the existing debug log on failure. Check the format against a real T2xxx consumables payload first; the format is Python-literal-like on some models.
- **Reconnect**:
  - Exponential backoff already exists (`tuyalocalapi.py:410-421`, capped at 600 s). Add ±20% jitter.
  - Reset the backoff on a successful push as well as on a successful send.
- **Log once**: log `warning` once when the entity goes unavailable and `info` once when it recovers (HA's `log-when-unavailable` quality rule), instead of per failure.
- **Debug log noise**: log full message hex/payloads only when a module-level `VERBOSE` flag is on. Phase 13's capture option will set that flag. Otherwise log a one-line summary (command, sequence, DPS keys).

## Acceptance criteria
- [ ] With Dobby powered off, HA startup isn't delayed by the integration, and the entity shows unavailable.
- [ ] Powering Dobby back on recovers without an HA restart and logs exactly one recovery line.
- [ ] The consumables attribute is unchanged for the L60 (or still absent, if the L60 doesn't report it).
- [ ] `python -m py_compile` passes; `docs/architecture/transport.md` updated.

## Status
Planned, not built.

## Size
S, ~25-45k.
