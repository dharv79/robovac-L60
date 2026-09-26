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
