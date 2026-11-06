# Phase 03 — 20 candidate features / improvements

## Scope
Brainstorm only — no code changes. Each idea is grounded in the current codebase (file/line where relevant), with a rough size estimate so the user can pick which ones become their own numbered phase (04, 05, ...). Ideas are roughly ordered by value for effort.

## Status
Done, merged (1d54606, PR #5). Promoted (06/11/2026): #1 → Phase 11, #9 → Phase 13, #2 → Phase 18, #18 → Phase 07, and #5 is superseded by Phase 10. These were first numbered 04-07, then renumbered into build order when the second brainstorm's 40 items became Phases 04-20 (now 04-21: the security sweep was inserted at 08).
Stale since Phase 02: #4 (timeouts landed), #6 (`EMPTY_MAPPING` removed). On the L60, #7 and #14 have no usable DPS codes (commented out / encrypted in the L60 model files).

## Ideas

1. **Fix the broken custom commands properly, then add `services.yaml`** — once Phase 02 finding #1 is fixed, give `edgeClean`, `doNotDisturb`, `boostIQ`, `roomClean`, etc. real HA services (`robovac.set_do_not_disturb`, `robovac.clean_rooms(room_ids, count)`, ...) with typed/validated schemas, instead of only `vacuum.send_command` with magic strings. Much more discoverable in the HA UI. *Size: S.*
2. **Reauth flow (`async_step_reauth`)** — right now an expired Eufy session or rotated `localKey` means delete-and-re-add the whole integration (losing all per-vacuum options). A reauth step re-runs `get_eufy_vacuums` and patches just the credentials. *Size: M.*
3. **Manual local-key entry flow** — a config-flow branch that skips the Eufy cloud login entirely for users who already know their `device_id`/`local_key`/IP, reducing the integration's dependency on (and exposure to) the Eufy cloud API. *Size: M.*
4. **Timeout/retry hardening on `eufywebapi.py`** — see Phase 02 finding #2; bundle with simple retry-with-backoff so a flaky cloud call during setup doesn't need a full flow restart. *Size: XS.*
5. **Push-driven battery sensor instead of independent polling** — `sensor.py` currently polls every `REFRESH_RATE` (60s) and just reads `vac_entity._battery_level_cache`; it could instead be notified directly when `RoboVacEntity.pushed_update_handler`/`async_update` runs, cutting one more scheduler tick per vacuum. *Size: S.*
6. **Wire up `EMPTY_MAPPING` as `button` entities** — "Empty dust", "Wash mop", "Dry mop" (`vacuum.py:77-81`) are already mapped but never used anywhere; expose them as HA `button` entities for models that support them. *Size: S.*
7. **Consumables as individual sensors** — `_consumables` is currently one opaque attribute blob (`vacuum.py:416-427`, base64+literal_eval decoded); split filter/brush/mop life into their own `sensor` entities with `%`/days remaining, so they're usable in dashboards and automations without templating. *Size: M.*
8. **Error binary sensor** — today "stuck"/"error" is only an extra_state_attribute string (`ATTR_ERROR`); add a `binary_sensor.<vacuum>_problem` so automations can trigger on `is_on` instead of string-matching an attribute. *Size: XS.*
9. **Diagnostics platform (`async_get_config_entry_diagnostics`)** — let a user attach a redacted dump (model code, DPS map, firmware) straight from Settings → Devices, which massively speeds up "please add my model" GitHub issues. *Size: S.*
10. **Repair/issue registry integration for discovery failures** — `__init__.py:70-71` currently just logs and swallows `DiscoveryPortsNotAvailableException` (e.g. when `localtuya` holds UDP 6666/6667). Surface an actionable `Settings → Repairs` card instead of a silent log line. *Size: S.*
11. **Room/zone cleaning UI** — a `select` entity or richer service (building on idea #1) that lists actual room names rather than requiring the raw `roomIds` list via `send_command`'s `params`. Needs room-name DPS reverse-engineering per model. *Size: L.*
12. **Live map camera entity** — for `RoboVacEntityFeature.MAP` models, decode the protobuf-ish map payload (some already-captured but undecoded blobs are sitting in `T2351.py`'s comments, DPS 164/167/176) and expose as a `camera` entity. *Size: XL — real reverse-engineering required.*
13. **Scheduled cleaning** — expose Tuya's native weekly-schedule DPS (if present on a model) as an HA `calendar` entity or service, instead of relying on HA-side automations alone. *Size: L, needs per-model DPS discovery.*
14. **Long-term statistics for cleaning time/area** — `cleaning_time`/`cleaning_area` are currently transient extra_state_attributes; expose as proper `sensor` entities with `state_class: total_increasing` so HA's history/statistics graphs work ("minutes cleaned per day"). *Size: S.*
15. **Config-flow schema sanity check** — `tuyawebapi.get_device()`'s response already includes a `schema` field that's logged at debug (`config_flow.py:142`) and then discarded; compare it against the chosen model file at setup time and warn if they look mismatched, catching bad model-code guesses before the user ever deploys. *Size: M.*
16. **`async_migrate_entry` scaffold** — no config-entry migration path exists yet; add the scaffold now so a future schema change doesn't need to be invented from scratch under time pressure. *Size: XS.*
17. **Shared model-schema base to cut copy/paste risk** — per review finding #8, 30 near-identical `vacuums/T*.py` files invite the kind of code-mismatch found in finding #1. A small shared dataclass/validator (or at least a model-file lint script) would catch an obviously-wrong DPS code (e.g. copied from a different model) at import time. *Size: M.*
18. **Basic CI: lint + a real test suite** — `docs/architecture/testing.md` already documents there's no test infrastructure; add `ruff`/`black` plus `pytest` with `pytest-homeassistant-custom-component`, at least covering `tuyalocalapi.py`'s message framing/crypto and `vacuum.py`'s state-mapping logic (both pure-ish and easy to unit test without a real device). *Size: L.*
19. **HACS quality-scale pass** — flesh out `hacs.json` (currently just `name`+`render_readme`) and add a `quality_scale.yaml`/brand assets to move up HACS's quality tiers, improving trust/discoverability for the L60 community. *Size: S.*
20. **Additional language translations** — `translations/` currently only has `en.json`; once the community grows, accept PRs for other locales using the existing `strings.json` as the source of truth. *Size: XS per language, ongoing.*

## Suggested next step
Pick a handful (start with #1, #5, #8, #9, #16 for low-risk, self-contained wins) and I'll turn each into its own `phases/0N-*.md` with scope/acceptance criteria, sized the same way as Phase 02.
