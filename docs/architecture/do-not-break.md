# Do-not-break rules: reasoning

CLAUDE.md keeps the one-line rule; the why lives here.

1. **No retry-the-read on socket EOF** (`tuyalocalapi.py`, `_async_handle_message`). The L60 drops the TCP socket when it sleeps. Retrying the read on EOF returns immediately forever and pins the event loop at 100% CPU. Disconnect instead; `process_queue` reconnects on the next send.
2. **Model files never import `homeassistant`** (`vacuums/T*.py`). HA enum members get removed between releases; a single stale reference (`VacuumEntityFeature.BATTERY`, HA 2026.9) crashed the integration at import. Feature flags are derived in `RoboVacEntity._build_supported_features`.
3. **DPS codes are strings at runtime** (`robovac.getCommandCodes`, `vacuum._tuya_command_codes`). The device returns string keys; an int key silently never matches.
4. **Battery stays off the vacuum entity** (`_battery_level_cache` → `sensor.py`). Setting battery on the vacuum entity triggers HA deprecation warnings.
5. **`activity` matches human-readable status strings** (`vacuum.py`, via `STATUS_MAPPING`), not internal keys. Changing the mapping text changes activity detection.
6. **`async_disable` must cancel all three loop tasks** (`process_queue`, `async_ping`, `_async_handle_message`). A leaked task keeps a dead device reconnecting after unload.
7. **Registry key = class name = first 5 chars of model code** (`vacuums/__init__.py`, `ROBOVAC_MODELS`).
8. **`async_send_command`'s named branches (`edgeClean`, `autoReturn`, `doNotDisturb`, `boostIQ`, ...) look up DPS codes from `_tuya_command_codes` and gate on `_supports(...)`** (`vacuum.py`, fixed 06/11/2026 — see Phase 02). Don't reintroduce hard-coded per-model DPS numbers here; a model without the code/feature should no-op, not silently write to the wrong index.
