# Plans index

## Context
Home Assistant integration for Eufy RoboVac (L60 focus). No multi-phase plan is active; add phases here when one starts.

## Phase status

| Phase | Status | Size / tokens |
|---|---|---|
| _(none)_ | — | — |

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
