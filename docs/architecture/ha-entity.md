# HA integration layer

Moved verbatim from CLAUDE.md (26/09/2026).

**`vacuum.py`** — `RoboVacEntity` is the main entity. It instantiates `RoboVac`, builds `_tuya_command_codes` (a flat `RobovacCommand → str(DPS_code)` dict), and polls/receives push state via `update_entity_values()`. Status decoding uses a two-step mapping: raw base64 Tuya value → internal status key (`TUYA_STATUS_MAPPING`) → human-readable string (`STATUS_MAPPING`). The `activity` property then pattern-matches against those **human-readable strings** (e.g. `"Charging"`, `"Recharge"`) — not the internal keys.

State updates arrive via two paths: (1) polling — `async_update` → `async_update_vacuum` → `vacuum.async_get()` every `REFRESH_RATE` seconds; (2) push — the device sends unsolicited DPS packets which `TuyaDevice.async_gratuitous_update_state` handles, calling back into `pushed_update_handler`. `_dps` accumulates across both paths via `.update()`, so it holds all DPS values seen since connection, not just the latest message.

**`async_send_command` hard-coded DPS trap:** Several named commands (`edgeClean`, `smallRoomClean`, `autoClean`, `autoReturn`, `doNotDisturb`, `boostIQ`, `roomClean`) bypass `_tuya_command_codes` entirely and use hard-coded DPS integer strings (`"5"`, `"152"`, `"135"`, etc.). These are L60-specific and will be wrong for other models.

**`sensor.py`** — `RobovacBatterySensor` polls `hass.data[DOMAIN][CONF_VACS][id]._battery_level_cache` from the vacuum entity rather than communicating with the device directly.

**`config_flow.py`** — Two-step setup: initial credential flow calls Eufy/Tuya cloud APIs synchronously (via `async_add_executor_job`) to populate `CONF_VACS`. Options flow lets users set IP address and toggle autodiscovery per vacuum.

## Entity behaviour details

- Battery level is **not** set on the vacuum entity — it lives in `_battery_level_cache` and is read by the separate sensor entity. This is intentional to avoid HA deprecation warnings.
- `robovac_features` gates which extra state attributes appear in `extra_state_attributes`. A feature flag in `robovac_features` does not automatically mean the DPS code is mapped — both must be present. Raw-value attributes are table-driven via `PASSTHROUGH_ATTRIBUTES` in `vacuum.py`; add new ones there rather than as new properties.
- Entity commands go through `_async_send_dps(*dps_dicts)`, which queues the writes and schedules exactly one follow-up state refresh (exceptions from that refresh are caught and logged).
- The integration uses `iot_class: local_polling` but also receives gratuitous push updates from the device via `async_gratuitous_update_state`.
- After 4 consecutive update failures (`UPDATE_RETRIES`), the entity is marked unavailable. On startup, `async_added_to_hass` makes up to 5 warm-up attempts (1.5 s apart) before giving up — this handles the L60's tendency to sleep and not respond immediately.
