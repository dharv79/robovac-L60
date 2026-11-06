# Releases

- Push a `release/vX.Y.Z` branch; `.github/workflows/release.yml` runs `gh release create "$TAG" --target main`.
- Notes: `RELEASE_NOTES.md` on the trigger branch if present, otherwise `--generate-notes`.
- A tag matching `b[0-9]+` (e.g. `v1.0.8b1`) is marked prerelease.
- The workflow deletes the trigger branch afterwards.
- Confirm version and target commit with the user before triggering. Do not modify `manifest.json` or changelogs.

| Version | Commit | Contents |
|---|---|---|
| v1.0.6 | PR #3 | HA 2026.9 `VacuumEntityFeature.BATTERY` crash fix |
| v1.0.7 | eeaae48 (PR #4) | Transport/entity refactor, socket-drop CPU spin fix |
| v1.0.8 | 1d54606 (PR #5) | Docs restructure (CLAUDE.md index + docs/plans); Phase 02 code review fixes #1-#7 |
| v1.0.9 | 0a706c7 (PR #6) | Strictly increasing Tuya sequence numbers (fixes "Update taking over 10 seconds" after commands); phase 04-07 plans |
| v1.0.10 | a585f72 (PR #7) | `vacuum.start` resumes a paused task (`AggO`) instead of sending start auto clean, which the L60 ignores while paused |
| v1.0.11 | 268423e (PR #8) | `vacuum.start` escalates start → resume (`AggO`) → stop return to dock (`AggP`) + start, so it works while paused, returning, or with unknown state after an HA restart |
| v1.0.12 | 973920f (PRs #9-#12) | Phases 04-07: start-sequence cancel and one refresh per burst; background warm-up, backoff jitter, quieter logs; restored state and DPS 152/153 query on connect; test suite and CI |
