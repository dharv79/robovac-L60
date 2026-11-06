# Security

Created 06/11/2026 (Phase 08 security sweep). Update the findings table whenever a security-relevant change lands.

## Threat model

- **Attackers:** other (possibly compromised) devices on the home LAN; anyone reading HA debug logs pasted into GitHub issues; anyone able to influence the public repo or its CI, which HACS installs from.
- **Assets:** the Eufy account password; each vacuum's `localKey` (full local control); device IDs; the HA instance itself (the integration runs in its event loop).
- **Trust boundaries:** UDP 6666/6667 broadcasts (unauthenticated, public key); TCP 6668 frames (AES with the `localKey`); the Eufy/Tuya cloud (setup time only); HA service calls (authenticated HA users).

## Findings (06/11/2026)

| ID | Sev | Location | Finding | Status |
|---|---|---|---|---|
| S1 | High | `tuyalocalapi.TuyaDevice.__repr__` | repr included the `localKey`; any `%r` of a device logged it | Fixed: key dropped |
| S2 | Med | `config_flow.get_eufy_vacuums` skip path | dumped the whole Eufy cloud item at debug (can carry `localKey`s) | Fixed: logs id, model and exception type only |
| S3 | Med | `tuyawebapi._request` | errors carried the full response body, and `raise_for_status` the URL with the session id, into logs | Fixed: `TuyaAPIError` with HTTP status / `errorCode` only |
| S4 | Med | `tuyalocaldiscovery`, `__init__` | a forged broadcast with a known `gwId` changed the vacuum's IP and reloaded the entry (redirect / reload storm) | Fixed: packet validation, authenticated probe on the new IP, one attempt per vacuum per 60 s |
| S5 | Med | `config_flow` → `entry.data` | Eufy password stored in the config entry | Fixed: not stored; entry v2 migration strips it (user decision 06/11/2026) |
| S6 | Med | `tuyawebapi._request` | `session.post` had no timeout; a stalled endpoint hung the config flow | Fixed: `timeout=10` |
| S7 | Low | `tuyalocaldiscovery.datagram_received` | `ensure_future` task unreferenced (could be garbage-collected mid-run) | Fixed: tracked set, cancelled on close |
| S8 | Low | `Message.from_bytes` | length field not bounds-checked explicitly (overruns already ended in `struct.error`) | Fixed: explicit range check |
| S9 | Low | `eufywebapi`, `tuyawebapi.acquire_session` | API hosts from cloud replies used unchecked; token could go over plain HTTP | Fixed: HTTPS required |
| S10 | Low | `eufywebapi` | access token written into module-level headers dict | Fixed: per-call headers |
| S11 | Low | `.github/workflows/*.yml` | actions pinned by tag; workflow-wide `contents: write`; `${{ }}` in `run:` | Fixed: SHA pins, per-job least privilege, `env:`; Dependabot added |
| S12 | Low | `vacuum.async_send_command` (numeric codes) | raw writes to any DPS | Accepted (user decision 06/11/2026): HA services need an authenticated user; kept for experimentation |
| S13 | Info | `tuyalocalapi`, `tuyalocaldiscovery` | AES-ECB, MD5, public UDP key | Accepted: mandated by Tuya protocol 3.3 |
| S14 | Info | `manifest.json` | `"requirements": []`; `cryptography`/`requests` come from HA core | Accepted: no pip-audit target; HA core owns those pins |

Checked and clean: no `verify=False`; every URL is `https://`; `ast.literal_eval` is gone (Phase 05); base64/JSON decode errors on device data are caught (`_update_consumables`, `from_bytes`); socket EOF still disconnects without retrying the read (do-not-break #1).

Public constants, not secrets: `UDP_KEY`, `EUFY_HMAC_KEY`, `TUYA_PASSWORD_INNER_CIPHER` and the Eufy app `client_Secret`/`client_id` ship in every install and are commented as such.

## Secret scanning

- **gitleaks** (CI `secrets` job, full history, `--redact`): 3 hits on 06/11/2026, all false positives, recorded in `.gitleaksignore`: the fake `TEST_KEY` in `tests/conftest.py` (2 commits) and the public Eufy app `client_Secret` (`eufywebapi.py`, upstream commit ff6184a).
- **GitHub secret scanning** is unavailable: the repo doesn't have GitHub Advanced Security.
- Report only rule, file and commit; never print a matched value. A real hit is the user's call (rotation, any history rewrite).

## Running the scanners locally

```bash
ruff check custom_components tests          # includes flake8-bandit (S)
gitleaks git . --redact --no-banner         # v8.30.1, from the GitHub release
```

## Reporting

`SECURITY.md` points reporters to GitHub private vulnerability reporting (Security tab → Report a vulnerability). It must be enabled in the repo settings.
