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
- Entity commands go through `_async_send_dps(*dps_dicts)`, which queues the writes and schedules one follow-up state refresh, skipped if one is already pending (exceptions from that refresh are caught and logged).
- The integration uses `iot_class: local_polling` but also receives gratuitous push updates from the device via `async_gratuitous_update_state`.
- After 4 consecutive update failures (`UPDATE_RETRIES`), the entity is marked unavailable. On startup, `async_added_to_hass` makes up to 5 warm-up attempts (1.5 s apart) before giving up — this handles the L60's tendency to sleep and not respond immediately.

## Start while paused sends resume (06/11/2026)

On the L60, DPS 152 is a protobuf `ModeCtrl` method: `AggN` = PAUSE_TASK (13), `AggO` = RESUME_TASK (14), `BBoCCAE=` = START_AUTO_CLEAN with options. In the user's 10:15 log Dobby was in "Cleaning paused" (153 `CAoAEAUyAggB`); `vacuum.start` sent `BBoCCAE=`, which was acked but ignored. `async_start` now sends `AggO` when the state is any paused state (`PAUSED_STATES`), and `activity` reports PAUSED for room/spot pauses too. `MODE_MAPPING["AggO"]` relabelled from "Auto cleaning" to "Resume". Untested whether start from "Recharge" (mid-task return to dock) also needs resume.

## Start escalation for unknown / returning states (06/11/2026)

Verified on Dobby: `AggP` (STOP_GOHOME, method 15) stops a return to dock and leaves it in Standby; `BBoCCAE=` from Standby starts cleaning; `AggO` resumes a pause. The L60's GET reply carries no 152/153, so after an HA restart `tuya_state` is `None` until Dobby pushes a change, and v1.0.10's paused check could not fire. `async_start` now runs `_async_start_sequence` as a background task: start (unless paused/returning) → resume (if paused or unknown) → stop-gohome + start (if returning or unknown), each step waiting up to `START_CONFIRM_TIMEOUT` (4 s) for activity CLEANING, and logs a warning if nothing worked. Dobby also returns to dock on its own a few minutes after a pause or stop (seen 10:28 and 10:33, no HA command).

## Command sequencing (06/11/2026, Phase 04)

- The start sequence runs in `self._start_task`. Any mode command from outside it cancels it: `_async_set_mode` (pause, dock/stop, spot, edge/small-room/autoClean) and a raw `send_command` to the mode DPS. Fan speed, locate and Boost IQ don't conflict with DPS 152 and don't cancel it. A second `async_start` while one runs is a no-op.
- `_async_wait_until_cleaning` waits on `self._cleaning`, an `asyncio.Event` kept in step with activity CLEANING by `_update_cleaning_event()` at the end of `update_entity_values`; no polling.
- `_schedule_refresh` keeps a single `self._refresh_task`. A write made while a refresh is pending relies on the device's push update rather than a second GET.
- Teardown cancels the start and refresh tasks.
