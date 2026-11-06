# Phase 19 — Type hints and type checking

## Scope
From the 06/11/2026 brainstorm (improvement: type hints + type checking). Done late so it covers the code as reshaped by Phases 08-18.

## Design
- Annotate `tuyalocalapi.py` (`Message`, `TuyaCipher`, `TuyaDevice`), `robovac.py`, `vacuum.py` and the coordinator.
- Replace bare `Exception` catches with specific ones where the type checker shows what's raised.
- Add `mypy` (or `pyright`) to `ci.yml`:
  - strict on `tuyalocalapi.py` and `proto.py`;
  - basic elsewhere;
  - `vacuums/*` excluded, apart from the base class.
- Tighten the ruff rule set from Phase 07's `E9,F` baseline (add `B`, `UP`, `I`), in separate commits.

## Acceptance criteria
- [ ] CI runs the type checker and is green.
- [ ] No behaviour change on Dobby (smoke test: start, pause, resume, dock).
- [ ] `docs/architecture/testing.md` updated.

## Status
Planned, not built.

## Size
M, ~50-85k.
