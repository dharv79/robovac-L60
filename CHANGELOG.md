## Issues corrected from the original robovac code

### 1. Home Assistant 2026.x compatibility fixes
- Removed deprecated `STATE_*` constants (`STATE_CLEANING`, `STATE_DOCKED`, etc.)
- Migrated to `StateVacuumEntity` and `VacuumActivity`
- Removed custom `state()` overrides in favor of the modern `activity` property
- Prevented future breakage caused by upcoming Home Assistant vacuum platform changes

---

### 2. Battery attribute deprecation fix
- Removed direct use of `_attr_battery_level` on the vacuum entity
- Introduced an internal battery cache (`_battery_level_cache`)
- Added a dedicated battery sensor entity with the correct device class
- Fully resolves the Home Assistant warning: *“setting battery_level is deprecated”*

---

### 3. “Unavailable until wake” behaviour improved (L60-specific)
- Prevented the vacuum entity from reporting `unavailable` before the first successful status read
- Added startup warm-up polling with multiple retries
- Only marks the entity unavailable after multiple consecutive update failures
- Avoids false offline states caused by L60 sleep behaviour

---

### 4. Robust availability handling
- Availability is no longer tied to a single failed poll
- Introduced failure counters to prevent availability flapping
- Ensures the vacuum remains controllable during transient network or device delays

---

### 5. Sensor–vacuum entity linking fixed
- Ensured vacuum entity instances are stored and shared via `hass.data`
- Battery sensor now reliably references the live vacuum entity
- Prevents battery sensors from remaining permanently unavailable

---

### 6. Tuya DPS handling hardened
- Added defensive parsing for Tuya DPS values (battery, consumables, status)
- Prevented crashes caused by missing or malformed DPS payloads
- Improved debug logging for DPS decoding and state mapping

---

### 7. L60 model support improvements
- Verified and corrected Tuya command mappings specific to the L60
- Ensured start, pause, return-to-base, and fan speed commands work reliably
- Avoided assumptions that only apply to older RoboVac models

---

### 8. Integration lifecycle correctness
- Fixed incorrect `async_setup` function signature
- Cleaned up `async_unload_entry` implementation
- Improved reload behaviour during IP autodiscovery updates

---

### 9. Code quality and maintainability
- Removed unused imports and dead code paths
- Normalized logging levels and messages
- Improved separation of internal state, attributes, and sensors
- Made the integration HACS-friendly and forward-maintainable

---

### 10. Naming and clarity
- Rebranded the integration as **Eufy Robovac L60**
- Improved device model identification in Home Assistant
- Reduced confusion with unsupported RoboVac models

---

### Summary
> This fork modernizes the original robovac integration, resolves multiple Home Assistant deprecations, improves Eufy L60 reliability, and introduces a compliant battery sensor while preserving original functionality.
