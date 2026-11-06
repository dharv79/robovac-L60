# Plans index

## Context
Home Assistant integration for Eufy RoboVac (L60 focus). Active plan: review the codebase, fix what the review finds, and brainstorm new features.

## Phase status

| Phase | Status | Size / tokens |
|---|---|---|
| 01 Code review & audit | Done, merged (1d54606, PR #5) | S, ~25k actual |
| 02 Apply review fixes | Done, merged (1d54606, PR #5); Boost IQ verified on-device, DND open (needs DPS 157 protobuf encoding). Follow-up sequence-number fix merged (0a706c7, PR #6), released v1.0.9. Start-while-paused resume fix merged (a585f72, PR #7), released v1.0.10. Start escalation for returning/unknown states merged (268423e, PR #8), released v1.0.11 | M, ~45k actual |
| 03 Feature ideas (20) | Done, merged (1d54606, PR #5) | S, ~20k actual |
| 04 Boost IQ switch + services | Planned, not built | S, ~25-45k |
| 05 Diagnostics download | Planned, not built | S, ~20-35k |
| 06 Reauth / reconfigure flow | Planned, not built | M, ~45-70k |
| 07 Tests + lint in CI | Planned, not built | L, ~90-140k |

## Decisions locked in with the user (do not re-litigate)
- Releases go through the `release/vX.Y.Z` branch workflow; version and target commit are confirmed with the user first.
- Do not modify `manifest.json` or changelogs.
- Never echo the GitHub token (kept in gitignored `.claude/settings.local.json`).

## Process (binding)
branch → implement/test → draft PR → green CI → merge → sync main → CI-replica test run → update plan docs → stop and report.

Each phase lives in `phases/NN-short-name.md` (scope, design, acceptance criteria, status). Update both this table and the phase file when work lands.

## Status table format
- Columns: Phase (number + short title) | Status | Size / tokens. The size column is required on every row.
- Status: "Planned, not built" · "In progress" · "On hold" · "Done, merged (<short SHA>, PR #N)" · "Superseded by ...".
- Size bands: XS <~30k · S ~15-50k · M ~40-90k · L ~90-175k · XL 250k+. Estimate a range if not built (e.g. "M, ~50-70k"); give the actual figure once done (e.g. "L, ~95k actual"). Re-estimate if scope changes and note why in the phase file.
- Stop reports list only undone phases (heading **Remaining phases**), in index order, then the build order in one sentence. Below the table: open items outside the plan, remaining context tokens, ask which phase next, remind to `/compact`.
