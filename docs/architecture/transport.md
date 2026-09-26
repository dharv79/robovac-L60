# Transport and cloud APIs

Communication layers, bottom to top. Moved verbatim from CLAUDE.md (26/09/2026).

**`tuyalocalapi.py`** — Raw Tuya protocol implementation. `TuyaDevice` maintains a persistent TCP socket to the vacuum (port 6668), encrypts/decrypts AES-ECB messages, manages a send queue with exponential backoff, and handles gratuitous push updates from the device. `TuyaCipher` handles the version-specific encryption. All I/O is async. Three long-lived loop tasks run per device — `process_queue` (send queue), `async_ping` (keepalive), `_async_handle_message` (socket reader) — and `async_disable` cancels them all. When the reader hits EOF/reset (the L60 drops the socket when it sleeps) it disconnects immediately so the next queued send reconnects; don't reintroduce retry-the-read-on-EOF, which busy-spins the event loop.

**`tuyalocaldiscovery.py`** — Listens on UDP ports 6666/6667 for Tuya broadcast packets to auto-discover device IP addresses. Decrypts broadcasts with a fixed UDP key and fires a callback when a known device is found.

**`robovac.py`** — `RoboVac` subclasses `TuyaDevice`, adding model-specific validation. Raises `ModelNotSupportedException` for unknown model codes. Exposes helpers to retrieve the model's supported commands, fan speeds, and HA feature flags.

**`eufywebapi.py` / `tuyawebapi.py`** — Used only during config flow setup to log into Eufy/Tuya cloud and retrieve the device `localKey` (16-char AES key). Once obtained, all runtime communication is local-only.

**`__init__.py` discovery wiring** — `async_setup` starts `TuyaLocalDiscovery` globally; when a broadcast is received for a known device with a changed IP, the config entry is updated and reloaded automatically. UDP ports 6666/6667 are required; if the `localtuya` integration is also installed it may hold these ports exclusively, breaking autodiscovery.

## Socket-drop CPU spin fix (v1.0.7, PR #4)

The reader previously retried the read on EOF, which busy-spun the event loop when the L60 slept and dropped the socket. It now disconnects on EOF/reset; the next queued send reconnects. Loop tasks are tracked and cancelled by `async_disable`. Not yet verified on a live HA instance at release time.
