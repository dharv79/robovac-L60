# Phase 13 — Protobuf decoder and last-prompt sensor

## Scope
From the 06/11/2026 brainstorm (features: decoder for the L60's encoded values, "last prompt" sensor). Unblocks Phase 14 (DND) and possibly L60 consumables.

## Design
- **`proto.py`**, a small pure-Python decoder for the base64 length-prefixed protobuf the L60 uses (e.g. 152/153/157):
  - varint, length-delimited, and fixed32/64.
  - Returns nested `{field_no: value}` dicts; no schema needed.
  - An encoder for the same subset, needed by Phase 14.
  - No HA imports, so it's unit-testable.
- Round-trip tests with known values: `BBoCCAE=` (start auto), `AggN`, `AggO`, `AggP`, `AggG`, and the captured DND default `DgoAEgoKABICCBYaAggI`.
- **Last-prompt `sensor`** for DPS 178 (currently "Unknown: 178" in the L60 model files):
  - Decode the prompt code and map known codes to text, e.g. 31 = "Can't start while recharging".
  - Unknown codes show as `code N`.
  - **Needs captures:** the user triggers a few prompts (start while recharging, stuck, bin missing) with Phase 12's capture mode on.
- Optionally expose decoded fields of other undecoded L60 DPS as attributes, behind the capture option.

## Acceptance criteria
- [ ] Decoder round-trips all the known values above (tests in CI).
- [ ] The last-prompt sensor shows the right text for at least 3 captured prompts.
- [ ] DPS 178 field layout documented in `docs/architecture/models.md` as a dated section.

## Status
Planned, not built.

## Size
M, ~50-85k.
