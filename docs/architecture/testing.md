# Testing and verification

Moved verbatim from CLAUDE.md (26/09/2026).

There is no test suite, linter configuration, or build tooling. Development is done by:
1. Copying `custom_components/robovac/` into a Home Assistant instance's `custom_components/` directory
2. Restarting Home Assistant and observing integration behaviour

For syntax checking: `python -m py_compile custom_components/robovac/<file>.py`

| Test file | Covers |
|---|---|
| _(none yet)_ | |
