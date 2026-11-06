# Phase 22 — README command reference and manifest housekeeping

## Scope
From the 06/11/2026 brainstorm (improvements: README L60 command reference, manifest version and owner).

## Design
- **README L60 section**:
  - each `vacuum.*` service and what it sends;
  - a raw mode-code table (from the Phase 09 model keys);
  - `vacuum.send_command` examples for `boostIQ`, `doNotDisturb` and room clean;
  - which items are verified on Dobby.
  - Link the Phase 17 blueprints.
- **Manifest** (**needs the user's explicit OK**; locked: do not modify manifests):
  - `version` is still `1.0.4` while releases are at v1.0.11, so HA shows the wrong version. Option: have `release.yml` stamp the tag version into `manifest.json` on the release branch.
  - `codeowners` is `@harv79`, while the repo owner is `dharv79`.
  - If declined, record the decision here and skip.

## Acceptance criteria
- [ ] README section reviewed by the user.
- [ ] Manifest change done only with recorded approval; otherwise marked declined.

## Status
Planned, not built (manifest part needs user approval).

## Size
XS, ~10-20k.
