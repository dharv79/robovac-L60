# Phase 08 — Vulnerability + security sweep

## Goal
Find and fix security weaknesses in the integration, and in the repo's supply chain, before the large refactors. Add automated scanners to Phase 07's CI so every later phase is gated by them. Added at the user's request (06/11/2026) and inserted after 07; the old 08-20 became 09-21.

## Context
- **Threat model:**
  - A home LAN with other, possibly compromised, devices.
  - HA debug logs that users paste into GitHub issues.
  - A public GitHub repo installed through HACS.
- **Assets:**
  - The Eufy account password.
  - Each vacuum's `localKey`, which gives full local control.
  - The device IDs.
  - The HA instance itself, since the integration runs inside its event loop.
- **Out of scope:** Tuya protocol 3.3's own cryptography. AES-ECB with an MD5-derived discovery key is mandated by the device, so it's recorded as an accepted risk rather than changed.
- **Prerequisite:** Phase 07, for pytest, ruff and the PR CI workflow. Phase 05 should already have replaced `ast.literal_eval`; verify it here.

## Scope

### A. Automated scanning, added to the Phase 07 CI workflow
- **Static analysis:** ruff `S` (flake8-bandit) rules, or `bandit -r custom_components`.
  - Fix or justify each hit. Use per-line `# noqa: S…` with a reason, never a blanket ignore.
- **Secret scanning:**
  - Use GitHub's secret scanning (`run_secret_scanning` MCP tool) across the tree and history, and add a gitleaks job in CI.
  - Report only file, commit and rule. Never print a matched value.
  - If anything real turns up, stop and tell the user. Rotating it, and any history rewrite, is their call.
- **Dependency audit:** `manifest.json` has `"requirements": []`, so `cryptography` and `requests` come from HA core. There's no pip-audit target; note this in `security.md` rather than inventing one.
- **GitHub Actions hardening (`.github/workflows/release.yml`):**
  - Pin `actions/checkout@v4` and any other actions to full commit SHAs, with the version in a comment.
  - Give each job the minimum `permissions`. Only the release job needs `contents: write`.
  - Keep `${{ }}` expressions out of `run:` scripts. Pass them through `env:`, as `GITHUB_REF_NAME` already is on line 39; `github.repository` on lines 30 and 39 is safe but should move too, for consistency.
  - Add Dependabot for the `github-actions` ecosystem (`.github/dependabot.yml`).

### B. Secrets in logs
- **`TuyaDevice.__repr__`** (`tuyalocalapi.py:378-385`) includes `self.cipher.key`, the localKey. Any `%r` of a device, now or later, leaks it into logs. Drop the key from the repr.
- **Skipped-device payload log** (`config_flow.py:164`): it logs the whole Eufy cloud device item at debug when parsing fails, and that item can carry another device's `localKey`. Log only the id and the error, or redact the known secret fields.
- **Sweep every `_LOGGER` call** for credentials, `localKey`, tokens, session IDs or raw cloud responses. That covers `eufywebapi.py`, `tuyawebapi.py`, `config_flow.py` and `__init__.py`. Redact, or move the call behind Phase 05's `VERBOSE` flag.

### C. Untrusted input from the LAN
- **UDP discovery** (`tuyalocaldiscovery.py:45-59`, `__init__.update_device`):
  - Any host can send a broadcast encrypted with the public UDP key. A spoofed packet with a known `gwId` changes a vacuum's IP and reloads the config entry, which allows redirection or a reload storm.
  - Validate the packet: `ip` must be a valid IPv4 address and `gwId` must be a known vacuum.
  - Rate-limit IP changes per vacuum.
  - Before switching, require the vacuum to answer an authenticated GET on the new IP with its `localKey`; that proves the sender's identity.
  - Keep a reference to the `ensure_future` task (line 59).
- **TCP frame parsing** (`Message.from_bytes`, `_async_handle_message`): check that length fields are bounds-checked, CRC/HMAC failures are rejected, and decode errors can't spin or grow buffers. Do-not-break #1 still applies.
- **DPS decoding:**
  - Confirm `ast.literal_eval` (`vacuum.py:423`) is gone after Phase 05.
  - Make sure base64/JSON decode errors on device data are caught, without breaking the entity.

### D. Cloud APIs (setup time only)
- **Missing timeout:** `tuyawebapi.py:160` (`session.post`) has none, so a stalled Tuya endpoint hangs the config flow. Add `timeout=10`, matching `eufywebapi.py`.
- **TLS:** confirm no `verify=False` anywhere, and that every URL is `https://`.
- **Constants:**
  - `EUFY_HMAC_KEY` (`tuyawebapi.py:18`) and `UDP_KEY` (`tuyalocaldiscovery.py:10`) are public constants taken from the app/protocol, not user secrets.
  - Add a comment saying so, so scanners and readers don't flag them repeatedly.
- **Stored password:**
  - Check whether `CONF_PASSWORD` is persisted in `entry.data`; `config_flow.py:203` stores `valid_data`.
  - If it is, the password is only needed at setup. Phase 18's reconfigure asks for it again anyway.
  - **Decision for the user:** stop storing the password, with an `async_migrate_entry` to strip it from existing entries, or keep it. Don't change it without their OK.

### E. HA service surface
- **Raw `send_command`:** `vacuum.send_command` with a numeric code writes any value to any DPS (`vacuum.py`, the `else` branch).
  - HA restricts services to authenticated users, so this is documented rather than blocked.
  - **Decision for the user:** optionally restrict raw writes to the model's known DPS codes.

### F. Deliverables
- **New `docs/architecture/security.md`** containing:
  - the threat model;
  - a findings table (ID, severity High/Medium/Low, location, status: fixed / accepted / deferred to phase N);
  - accepted risks (protocol crypto, no pip-audit target);
  - how to run the scanners locally.
  - Add it to the CLAUDE.md topic table.
- **Fix rule:** High and Medium findings are fixed in this phase; Low ones are fixed if they're small, otherwise recorded with a target phase.
- **Optional `SECURITY.md`** (a vulnerability-reporting policy): it's outward-facing and names a contact route, so it needs the user's OK before it's added.

## Files touched
- **Code:**
  - `custom_components/robovac/tuyalocalapi.py`: `__repr__`, plus frame-parsing hardening if needed.
  - `custom_components/robovac/tuyalocaldiscovery.py`: packet validation; task reference.
  - `custom_components/robovac/__init__.py`: verify on the new IP and rate-limit before `update_device` reloads.
  - `custom_components/robovac/config_flow.py`: log redaction; and if the user approves dropping the stored password, stop storing it and add the migration.
  - `custom_components/robovac/tuyawebapi.py`: timeout; comment on the public constant.
- **CI and repo:**
  - `.github/workflows/release.yml`: SHA pins, permissions, `env:` for expressions.
  - Phase 07's CI workflow: ruff `S` or bandit, and gitleaks.
  - `.github/dependabot.yml` (new).
- **Docs and tests:**
  - `docs/architecture/security.md` (new); CLAUDE.md topic table; `docs/architecture/testing.md` test map.
  - `tests/test_security.py` (new, with the Apache 2.0 header).

## Tests
- **Unit tests (pytest, Phase 07 harness):**
  - `repr()` and `str()` of a `TuyaDevice` don't contain the local key.
  - The config-flow skip path logs no `localKey` (checked with `caplog`, using a fake key).
  - Discovery ignores bad IPs and unknown `gwId`s, and rate-limits repeated IP changes.
  - An IP change is applied only after the authenticated GET on the new IP succeeds (mocked).
  - A truncated or oversized frame is rejected without a busy loop.
- **CI:** the new scanner jobs are green on the PR, and secret scanning is clean, or its findings have been reported to the user.
- **Static checks:** `python -m py_compile` passes; ruff, format and type checks pass as configured by Phase 07.
- **On-device:**
  - [ ] Dobby still autodiscovers and controls normally.
  - [ ] An HA restart with debug logging on shows no localKey in `home-assistant.log`.

## Status
In progress (PR open). On-device checks open.

## Built (06/11/2026)
- **Decisions (user, 06/11/2026):** stop storing the password, with a migration; document raw `send_command` only; add `SECURITY.md` using GitHub private vulnerability reporting.
- **Findings:** S1-S14 in `docs/architecture/security.md`. S1-S11 fixed, S12-S14 accepted.
- **Code changes:**
  - `TuyaDevice.__repr__` no longer includes the key.
  - The config-flow skip log no longer includes the payload.
  - Tuya cloud errors are redacted (`TuyaAPIError`), with `timeout=10`.
  - Cloud API hosts must be HTTPS.
  - Eufy headers are built per call.
  - Discovery: `is_valid_broadcast` checks packets, and the callback task is tracked.
  - IP changes: `async_update_device_ip` applies one only after `async_probe_device` (an encrypted GET with the stored key) succeeds, rate-limited to one attempt per vacuum per 60 s.
  - The frame length is range-checked, and `from_bytes(require_encrypted=True)`.
  - Config entry `VERSION` 2, with `async_migrate_entry`.
- **CI changes:**
  - ruff `S` is enabled, with per-line justified `noqa`.
  - New `secrets` job: gitleaks 8.30.1, checksum-pinned, full history.
  - Actions are SHA-pinned (checkout v4.4.0, setup-python v5.6.0).
  - Release job: `contents: write` only, with `env:` for expressions.
  - Dependabot for `github-actions`.
- **Secret scan:** gitleaks found 3 false positives, now in `.gitleaksignore`. GitHub secret scanning is unavailable because the repo has no Advanced Security. No real secrets were found.
- **Tests:** `tests/test_security.py` adds 32 tests. The config-flow test now asserts the password isn't stored. Full suite: 201 passed.
- **Follow-ups found while building:**
  - `TuyaAPISession.acquire_session` calls a missing `self.getCountryCode` when `phoneCode` is empty. This is a correctness bug, not a security one, and is deferred.
  - Enable GitHub private vulnerability reporting in the repo settings; that's a user action.

## Size
M, ~50-85k. The estimate assumes Phase 07's CI exists. It's at the high end if the discovery verify-on-new-IP change needs more `__init__` restructuring, or if the user approves dropping the stored password, which brings in the migration.
