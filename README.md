# Eufy RobovVac L60 control for Home Assistant

Supports L60 and sorts the depreciated sensors and the unavaliable issue

Forked from https://github.com/maximoei/robovac which was forked from https://github.com/CodeFoodPixels/robovac  

## Installation

### Prerequisites
Before installing, please ensure the following:

1. Your **Home Assistant Core** is fully up to date.
2. Any previous **Eufy** or **RoboVac** integrations have been completely removed, including any related entries in `configuration.yaml`.

You can clone this repository manually if you prefer, but **using HACS is recommended**.

---

### Installation via HACS (Recommended)

1. In **HACS**, add this repository as an **Additional Integration Repository**.
2. Install the integration.
3. Restart **Home Assistant**.
4. Navigate to **Settings → Devices & Services → Integrations**.
5. Click **+ Add Integration**.
6. Search for **Eufy RoboVac L60** and select it.
7. Enter your **Eufy account username and password** (the same credentials used in the Eufy mobile app), then submit.
8. If successful, you will see a confirmation dialog and be prompted to assign an **Area** to each RoboVac.
9. Click **Finish**.
10. On the **Integrations** page, locate the **Eufy RoboVac L60** integration and click **Configure**.
11. Select the radio button next to the vacuum name, enter its **IP address**, and click **Submit**.

> Repeat steps **10–11** for each RoboVac you own.

---

### Issues sorted in this Fork and reasons for it

See the [changelog](CHANGELOG.md) for a full list of changes.

### Notes

- From time to time, **Eufy may change the access key** used by your vacuum.
- If this happens, you may need to **remove and re-add the integration** to obtain a new key.

Enjoy! 🧹✨

