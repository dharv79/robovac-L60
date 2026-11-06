# Plans index

## Context
Home Assistant integration for Eufy RoboVac (L60 focus). Active plan: review the codebase, fix what the review finds, and brainstorm new features.

## Phase status

| Phase | Status | Size / tokens |
|---|---|---|
| 01 Code review & audit | Done, merged (1d54606, PR #5) | S, ~25k actual |
| 02 Apply review fixes | Done, merged (1d54606, PR #5); Boost IQ verified on-device, DND open (needs DPS 157 protobuf encoding). Follow-up sequence-number fix merged (0a706c7, PR #6), released v1.0.9. Start-while-paused resume fix merged (a585f72, PR #7), released v1.0.10. Start escalation for returning/unknown states merged (268423e, PR #8), released v1.0.11 | M, ~45k actual |
| 03 Feature ideas (20) | Done, merged (1d54606, PR #5) | S, ~20k actual |
| 04 Command sequencing fixes | Done, merged (cfe88d3, PR #9); on-device checks open | S, ~40k actual |
| 05 Startup + connection resilience | Done, merged (0641822, PR #10); on-device checks open | S, ~35k actual |
| 06 State after HA restart | Done, merged (38ab805, PR #11); on-device checks open | S, ~30k actual |
| 07 Tests + lint in CI | Done, merged (973920f, PR #12); CI green | M, ~60k actual (est. L) |
| 08 Vulnerability + security sweep | Done, merged (5b4a03b, PR #13); CI green; on-device checks open | M, ~70k actual |
| 09 Per-model command data | Done, merged (2a838be, PR #14); on-device check open | M, ~40-70k |
| 10 Shared coordinator + modern HA patterns | Done, merged (2fac439, PR #15); CI green; on-device checks open | L, ~90-140k |
| 11 Control entities + services | Done, merged (9e438de, PR #16); CI green; on-device checks open | M, ~50-80k |
| 12 Status + connectivity entities | Done, merged (8ed3785, PR #17); CI green; on-device checks open | M, ~40-65k |
| 13 Diagnostics + capture tools | Planned, not built | M, ~40-65k |
| 14 Protobuf decoder + last-prompt sensor | Planned, not built | M, ~50-85k |
| 15 Do Not Disturb entities | On hold (needs DPS 157 captures + Phase 14) | M, ~40-70k |
| 16 Cleaning events + history sensors | Planned, not built | M, ~40-65k |
| 17 Device triggers + blueprints | Planned, not built | M, ~40-65k |
| 18 Modern L60 dashboard (Lovelace YAML, core cards) | Planned, not built | M, ~40-65k |
| 19 Reauth / reconfigure + IP test | Planned, not built | M, ~55-85k |
| 20 "New RoboVac found" setup prompt | Planned, not built | M, ~45-75k |
| 21 Type hints + type checking | Planned, not built | M, ~50-85k |
| 22 README command reference + manifest housekeeping | Planned, not built (manifest part needs user OK) | XS, ~10-20k |

Phases are numbered in build order (renumbered 06/11/2026: old 04 → 10, 05 → 12, 06 → 17; 07 unchanged. Renumbered again 06/11/2026 when the security sweep was inserted at 08: old 08-20 → 09-21). Dashboard inserted at 18 (06/11/2026): old 18-21 → 19-22). Order rationale:
- Bug fixes and robustness first (04-06).
- Then tests (07), then the security sweep (08), so its scanners run in CI and gate every later phase, before the refactors (09-10).
- New entities (11-17) come after the coordinator, so they're built on it once.
- The capture tools (13) come before the decoder and DND (14-15).
- The dashboard (18) comes after the entities it displays (11-17).
- Type checking (21) comes late, so it covers the final code shape.

## Decisions locked in with the user (do not re-litigate)
- Releases go through the `release/vX.Y.Z` branch workflow; version and target commit are confirmed with the user first.
- Do not modify `manifest.json` or changelogs.
- Never echo the GitHub token (kept in gitignored `.claude/settings.local.json`).

## Process (binding)
branch reset to `main` → implement/test → draft PR (subscribe to activity) → green CI → mark ready → squash-merge with the expected head SHA (unsubscribe) → sync main → CI-replica test run → update plan docs → stop and report.

Each phase lives in `phases/NN-short-name.md` and must be self-contained: Goal, Scope, Files touched, Tests, Status, and a "Built (DD/MM/YYYY)" section on completion. Phases 05-21 (except 08) predate this standard; bring each file up to it when the phase is built. Update both this table and the phase file when work lands.

## Status table format
- Columns: Phase (number + short title) | Status | Size / tokens. The size column is required on every row.
- Status: "Planned, not built" · "In progress" · "On hold" · "Done, merged (<short SHA>, PR #N)" · "Superseded by ...".
- Size bands: XS <~30k · S ~15-50k · M ~40-90k · L ~90-175k · XL 250k+. Estimate a range if not built (e.g. "M, ~50-70k"); give the actual figure once done (e.g. "L, ~95k actual"). Re-estimate if scope changes and note why in the phase file.
- Stop reports list only undone phases (heading **Remaining phases**), in index order, then the build order in one sentence. Below the table: open items outside the plan, remaining context tokens, ask which phase next, remind to `/compact`.
