# HA integration layer

Moved verbatim from CLAUDE.md (26/09/2026).

**`vacuum.py`** — `RoboVacEntity` is the main entity. It instantiates `RoboVac`, builds `_tuya_command_codes` (a flat `RobovacCommand → str(DPS_code)` dict), and polls/receives push state via `update_entity_values()`. Status decoding uses a two-step mapping: raw base64 Tuya value → internal status key (`TUYA_STATUS_MAPPING`) → human-readable string (`STATUS_MAPPING`). The `activity` property then pattern-matches against those **human-readable strings** (e.g. `"Charging"`, `"Recharge"`) — not the internal keys.

State updates arrive via two paths: (1) polling — `async_update` → `async_update_vacuum` → `vacuum.async_get()` every `REFRESH_RATE` seconds; (2) push — the device sends unsolicited DPS packets which `TuyaDevice.async_gratuitous_update_state` handles, calling back into `pushed_update_handler`. `_dps` accumulates across both paths via `.update()`, so it holds all DPS values seen since connection, not just the latest message.

**`async_send_command` hard-coded DPS trap:** Several named commands (`edgeClean`, `smallRoomClean`, `autoClean`, `autoReturn`, `doNotDisturb`, `boostIQ`, `roomClean`) bypass `_tuya_command_codes` entirely and use hard-coded DPS integer strings (`"5"`, `"152"`, `"135"`, etc.). These are L60-specific and will be wrong for other models.

**`sensor.py`** — `RobovacBatterySensor` reads `coordinator.data.battery` (see the Phase 10 section below) rather than communicating with the device directly.

**`config_flow.py`** — Two-step setup: initial credential flow calls Eufy/Tuya cloud APIs synchronously (via `async_add_executor_job`) to populate `CONF_VACS`. The password is used only for that and is not stored (entry `VERSION` 2; `async_migrate_entry` strips it from v1 entries). Options flow lets users set IP address and toggle autodiscovery per vacuum.

## Entity behaviour details

- Battery level is **not** set on the vacuum entity — it lives in `coordinator.data.battery` and is read by the separate sensor entity. This is intentional to avoid HA deprecation warnings.
- `robovac_features` gates which extra state attributes appear in `extra_state_attributes`. A feature flag in `robovac_features` does not automatically mean the DPS code is mapped — both must be present. Raw-value attributes are table-driven via `PASSTHROUGH_ATTRIBUTES` in `vacuum.py`; add new ones there rather than as new properties.
- Entity commands go through `_async_send_dps(*dps_dicts)`, which queues the writes and schedules one follow-up state refresh, skipped if one is already pending (exceptions from that refresh are caught and logged).
- The integration uses `iot_class: local_polling` but also receives gratuitous push updates from the device via `async_gratuitous_update_state`.
- After 4 consecutive update failures (`UPDATE_RETRIES`), the entity is marked unavailable. On startup, a background warm-up task makes up to 5 attempts (1.5 s apart) before giving up — this handles the L60's tendency to sleep and not respond immediately. See "Startup and availability" below.

## Start while paused sends resume (06/11/2026)

On the L60, DPS 152 is a protobuf `ModeCtrl` method: `AggN` = PAUSE_TASK (13), `AggO` = RESUME_TASK (14), `BBoCCAE=` = START_AUTO_CLEAN with options. In the user's 10:15 log Dobby was in "Cleaning paused" (153 `CAoAEAUyAggB`); `vacuum.start` sent `BBoCCAE=`, which was acked but ignored. `async_start` now sends `AggO` when the state is any paused state (`PAUSED_STATES`), and `activity` reports PAUSED for room/spot pauses too. `MODE_MAPPING["AggO"]` relabelled from "Auto cleaning" to "Resume". Untested whether start from "Recharge" (mid-task return to dock) also needs resume.

## Start escalation for unknown / returning states (06/11/2026)

Verified on Dobby: `AggP` (STOP_GOHOME, method 15) stops a return to dock and leaves it in Standby; `BBoCCAE=` from Standby starts cleaning; `AggO` resumes a pause. The L60's GET reply carries no 152/153, so after an HA restart `tuya_state` is `None` until Dobby pushes a change, and v1.0.10's paused check could not fire. `async_start` now runs `_async_start_sequence` as a background task: start (unless paused/returning) → resume (if paused or unknown) → stop-gohome + start (if returning or unknown), each step waiting up to `START_CONFIRM_TIMEOUT` (4 s) for activity CLEANING, and logs a warning if nothing worked. Dobby also returns to dock on its own a few minutes after a pause or stop (seen 10:28 and 10:33, no HA command).

## Command sequencing (06/11/2026, Phase 04)

- The start sequence runs in `self._start_task`. Any mode command from outside it cancels it: `_async_set_mode` (pause, dock/stop, spot, edge/small-room/autoClean) and a raw `send_command` to the mode DPS. Fan speed, locate and Boost IQ don't conflict with DPS 152 and don't cancel it. A second `async_start` while one runs is a no-op.
- `_async_wait_until_cleaning` waits on `self._cleaning`, an `asyncio.Event` kept in step with activity CLEANING by `_update_cleaning_event()` at the end of `update_entity_values`; no polling.
- `_schedule_refresh` keeps a single `self._refresh_task`. A write made while a refresh is pending relies on the device's push update rather than a second GET.
- Teardown cancels the start and refresh tasks.

## Startup and availability (06/11/2026, Phase 05)

- The entity starts unavailable and becomes available on the first update that returns DPS, from the warm-up or a regular poll.
- `async_added_to_hass` starts `_async_warm_up` with `hass.async_create_background_task` and returns at once, so a powered-off vacuum doesn't delay HA startup. The warm-up stops early if a poll already made the entity available. `async_will_remove_from_hass` cancels it.
- Log once: `_mark_unavailable` logs one `warning` when the entity goes unavailable (warm-up exhausted, or `UPDATE_RETRIES` failed polls), and `_mark_available` logs one `info` when it recovers. Individual failures log at debug.
- Consumables are decoded with `json.loads`, not `ast.literal_eval`. No model currently has both the `CONSUMABLES` feature and a mapped DPS code, so this path doesn't run yet; a Python-literal payload (single quotes) would be logged at debug and ignored.
- The full `tuyastatus` debug line only appears when `tuyalocalapi.VERBOSE` is on; the one-line "Decoded ..." summary is always logged.

## Restored state after an HA restart (06/11/2026, Phase 06)

- `RoboVacEntity` also inherits `RestoreEntity`. `async_added_to_hass` calls `super().async_added_to_hass()`, then `_async_restore_activity` seeds `_restored_activity` from the last state (any `VacuumActivity` value; `unavailable`/`unknown` are skipped) when `tuya_state` is still `None`.
- `activity` returns the restored value only while `tuya_state` is `None`, and `extra_state_attributes` then adds `state_restored: true`. The first decoded status clears it.
- Command logic uses `_live_activity()` (device-reported only): `_update_cleaning_event`, `_async_wait_until_cleaning`, and `_async_start_sequence`'s `tuya_state` checks. A restored state never short-circuits the start escalation; unknown still escalates.

## Shared coordinator (Phase 10, 06/11/2026)

- `coordinator.py`: `RoboVacCoordinator(DataUpdateCoordinator[RoboVacData])`, one per vacuum, stored in `entry.runtime_data` as `{vac_id: coordinator}` (replaces `hass.data[DOMAIN][CONF_VACS]`). It owns the `RoboVac` device, `command_codes`, mode/status maps, availability (`available`, `update_failures`, `fault`) and the warm-up task. State is parsed once per payload into the frozen `RoboVacData` (`status`, `error`, `mode`, `battery`, `fan_speed`, `consumables`, `passthrough`, raw `dps`).
- **Push first:** `pushed_update_handler` → `update_from_device` → `async_set_updated_data`. A push also marks the vacuum available. `update_interval` is 5 min (`FALLBACK_UPDATE_INTERVAL`) and a watchdog (`async_track_time_interval`, `REFRESH_RATE`) forces a GET only if nothing has arrived for `REFRESH_RATE`. Failed GETs keep the last data; after `UPDATE_RETRIES` the vacuum is unavailable (logged once). `async_forced_refresh` (GET, errors propagate) is used after commands.
- **Entities:** `RoboVacEntity` and `RobovacBatterySensor` are `CoordinatorEntity`s. `available` comes from `coordinator.available`; the sensor is always available and keeps its last reading. `_cleaning` (asyncio.Event for the start sequence) now lives on the coordinator and is set when the parsed activity is CLEANING. Restored activity stays on the entity (display only).
- **Naming:** `_attr_has_entity_name = True`, `_attr_name = None` (the main entity takes the device name, so `vacuum.dobby` is unchanged). unique_ids unchanged. This replaces the plan's "translated name": none is needed for the main entity.
- **IP changes:** after the Phase 08 authenticated probe, `async_update_device_ip` calls `coordinator.async_set_host` (disable the old device, create a new one on the new host, warm up) then `async_update_entry`. `update_listener` compares entry data minus IPs with each coordinator's `item`: any other change reloads the entry, an IP-only change (including a manual IP in the options flow) just reconnects that vacuum.
- `iot_class` in `manifest.json` stays `local_polling` (user declined `local_push`, 06/11/2026).

## Control entities and services (Phase 11, 06/11/2026)

- `entity.py`: `RoboVacBaseEntity(CoordinatorEntity)` for helper entities: `has_entity_name`, `translation_key`, unique_id `<vac_id>_<key>`, device identifiers, `available` from the coordinator. Names live in `strings.json` / `translations/en.json` (`entity.<domain>.<key>.name`).
- `switch.py`: Boost IQ (`<id>_boost_iq`), only where the model has `BOOST_IQ` and a DPS code. State from `coordinator.data.passthrough[boost_iq]` (`None` = unknown). Writes an explicit `True`/`False`; the `boostIQ` `send_command` stays a toggle.
- `button.py`: Stop return to dock (`<id>_stop_return`, only if the model file declares `ModeKey.STOP_RETURN`, i.e. `coordinator.declared_modes`) and Locate (`<id>_locate`, toggles DPS 160 like the vacuum entity).
- `select.py`: Suction level (`<id>_suction_level`), options from `coordinator.fan_speed_map`; unknown current value shows as unknown.
- All writes go through `coordinator.async_send_dps(*dps, supersede_start=False)`: one follow-up refresh per burst, and `supersede_start=True` (mode commands) calls `coordinator.cancel_start`, which the vacuum entity points at its `_cancel_start`.
- Services (entity services on the vacuum platform, `services.yaml`): `robovac.start_new_clean` (stop-return, wait up to `NEW_CLEAN_SETTLE_TIMEOUT` for a non-paused state, then start-auto; runs as the cancellable `_start_task`) and `robovac.auto_clean` (start-auto directly, no escalation). `edge_clean` / `small_room_clean` were dropped: no L60 model declares those modes (user decision, 06/11/2026).

## Status and connectivity entities (Phase 12, 06/11/2026)

- `sensor.py` adds `StatusSensor` (`<id>_status`, `device_class: enum`, options = `STATUS_MAPPING` texts for the model's `status_values`; unknown if the status isn't an option) and `LastSeenSensor` (`<id>_last_seen`, `timestamp`, diagnostic, `coordinator.last_seen`, set on every parsed push or GET reply; always available so a stale value shows while offline).
- `binary_sensor.py`: `docked` (status in `DOCKED_STATES` = Charging / Completed, matching `live_activity` DOCKED), `charging` (`battery_charging`; status Charging) and `connected` (`connectivity`, diagnostic; always available so it reads off rather than unavailable). `docked` and `charging` are unknown until a status arrives. Strings come from the captured statuses; "Recharge" (heading home) is not docked.
- `connected` reads `coordinator.connected` → `TuyaDevice.connected`. `TuyaDevice.connection_cb` (sync, exceptions logged and contained) fires on connect and disconnect; the coordinator points it at `async_update_listeners`, so a ping timeout turns the sensor off within one ping interval.
- DeviceInfo: the MAC is already on the device via the vacuum entity (`connections`). The firmware version isn't stored at setup, so `sw_version` is omitted (no migration added, per plan).

