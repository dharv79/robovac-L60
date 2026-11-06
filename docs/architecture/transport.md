# Transport and cloud APIs

Communication layers, bottom to top. Moved verbatim from CLAUDE.md (26/09/2026).

**`tuyalocalapi.py`** — Raw Tuya protocol implementation. `TuyaDevice` maintains a persistent TCP socket to the vacuum (port 6668), encrypts/decrypts AES-ECB messages, manages a send queue with exponential backoff, and handles gratuitous push updates from the device. `TuyaCipher` handles the version-specific encryption. All I/O is async. Three long-lived loop tasks run per device — `process_queue` (send queue), `async_ping` (keepalive), `_async_handle_message` (socket reader) — and `async_disable` cancels them all. When the reader hits EOF/reset (the L60 drops the socket when it sleeps) it disconnects immediately so the next queued send reconnects; don't reintroduce retry-the-read-on-EOF, which busy-spins the event loop.

**`tuyalocaldiscovery.py`** — Listens on UDP ports 6666/6667 for Tuya broadcast packets to auto-discover device IP addresses. Decrypts broadcasts with a fixed UDP key and fires a callback when a known device is found.

**`robovac.py`** — `RoboVac` subclasses `TuyaDevice`, adding model-specific validation. Raises `ModelNotSupportedException` for unknown model codes. Exposes helpers to retrieve the model's supported commands, fan speeds, and HA feature flags.

**`eufywebapi.py` / `tuyawebapi.py`** — Used only during config flow setup to log into Eufy/Tuya cloud and retrieve the device `localKey` (16-char AES key). Once obtained, all runtime communication is local-only.

**`__init__.py` discovery wiring** — `async_setup` starts `TuyaLocalDiscovery` globally; when a broadcast is received for a known device with a changed IP, the config entry is updated and reloaded automatically. UDP ports 6666/6667 are required; if the `localtuya` integration is also installed it may hold these ports exclusively, breaking autodiscovery.

## Socket-drop CPU spin fix (v1.0.7, PR #4)

The reader previously retried the read on EOF, which busy-spun the event loop when the L60 slept and dropped the socket. It now disconnects on EOF/reset; the next queued send reconnects. Loop tasks are tracked and cancelled by `async_disable`. Not yet verified on a live HA instance at release time.

## Duplicate sequence numbers after a command (06/11/2026)

Every entity command queued two GETs in the same millisecond: HA's post-service update of a polling entity, plus `_schedule_refresh`. `Message.set_sequence` used `perf_counter` milliseconds, so both got the same sequence. The second overwrote the first's entry in `_listeners`, the first waiter never got a reply, and after `TIMEOUT` (10 s) it disconnected and HA logged "Update of vacuum.… is taking over 10 seconds". Seen in the user's debug log at 09:57:07: start command acked, two GETs with sequence 744183316. Sequences are now strictly increasing.

## Bounded send queue (06/11/2026, Phase 04)

All queue appends go through `TuyaDevice._enqueue`. It drops expired messages, then removes any unsent SET whose DPS codes are all overwritten by the new SET (a SET touching other codes too is kept), and caps the queue at `MAX_QUEUE_LENGTH` (20), dropping the oldest message nobody waits on (ping/SET) first and logging a warning. The 0.25 s sleep in `_async_send` is a retry pause, not a response wait; responses already wait on a per-sequence semaphore.

## Backoff and debug logging (06/11/2026, Phase 05)

- After more than 3 consecutive send failures the queue backs off: `backoff_interval(failures)` = `5 × 1.70224^(failures−4)` s, capped at `MAX_BACKOFF` (600 s), then ±20% jitter (`BACKOFF_JITTER`), so the longest wait is 720 s.
- `_reset_backoff()` clears the failure count, interval and backoff flag. It runs after a successful send and on every gratuitous push (a push proves the device is reachable). If a backoff was active it sets `_backoff_ended`, which wakes `process_queue` from its sleep straight away.
- Backoff start and end log at debug only; the entity logs the single unavailable/recovered pair.
- `VERBOSE` (module-level, default `False`) gates full payloads in debug logs. Off: `Message.describe()` returns `summary()` (`cmd=0x7 seq=N dps=[152,5]`, keys only), state updates log DPS keys, and undecodable payloads log their length. On: full `repr`, full `_dps` and payload hex. Phase 13's capture option will set it.

## DPS query on connect (06/11/2026, Phase 06)

- The L60's GET reply carries no DPS 152/153, so after an HA restart mode and status stay unknown until the device pushes.
- A model can set `query_dps_on_connect` (a tuple of DPS codes; T2267 sets `(152, 153)`). After each `async_connect`, `_async_query_dps` sends Tuya UPDATEDPS (`0x12`, payload `{"dpId": [...]}`, no 3.3 version header, no response awaited) for any of those codes not yet in `_dps`. It writes directly to the socket because it runs inside `_async_send`.
- At most `MAX_DPS_QUERIES` (3) per `TuyaDevice`, in case a device drops the socket on the command.
- Replies to `0x12` are logged at debug by `_async_update_dps_reply`. The pushed DPS arrive as a normal gratuitous update.
- **Unverified on-device.** The DP_QUERY-with-`dpId`-list variant from the plan wasn't added. Try it only if UPDATEDPS doesn't make Dobby report 152/153; record the result here.
