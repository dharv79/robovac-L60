# RoboVac L60 dashboard

A ready-made Lovelace view built only from core Home Assistant cards (grid, heading, tile, gauge, history graph, markdown). No HACS frontend cards are needed.

## Import
1. Settings > Dashboards > Add dashboard > "New dashboard from scratch", then open it.
2. Pencil icon > three dots > **Raw configuration editor**.
3. Paste the contents of [`robovac-l60.yaml`](robovac-l60.yaml) and save.
4. Replace the slug `dobby` with your vacuum's entity slug (for example `vacuum.dobby` becomes `vacuum.my_robovac`). A find-and-replace on `dobby` in the editor does it.

## What it shows
| Block | Entities |
|---|---|
| Controls | `vacuum.dobby` (start/pause, stop, dock, locate), `select.dobby_suction_level`, `switch.dobby_boost_iq`, `button.dobby_stop_return_to_dock`, `button.dobby_locate` |
| Status | `sensor.dobby_battery` (gauge), `sensor.dobby_status`, `binary_sensor.dobby_docked`, `_charging`, `_connected`, `sensor.dobby_last_seen` |
| History | `sensor.dobby_last_cleaned`, `_cleaning_count`, `_last_clean_duration`, and a 24 h graph of battery and status |
| Diagnostics | `sensor.dobby_last_prompt`, plus a note on diagnostics download, capture mode and `robovac.get_dps` |

## Not included
- **Consumables:** the L60 reports them encrypted, so there is nothing to show. A commented block shows how to read the `consumables` attribute on models that report it.
- **Do Not Disturb:** commented out until Phase 15 is built.
- **Map:** the L60 map data is not available locally.

A test (`tests/test_dashboard.py`) checks that the file parses, uses only core cards, and references only entities the integration creates. The layout has not yet been checked on a real HA (light and dark theme, phone width).
