# K1-J1 bounded-family replay bundle

This directory preserves the compact, canonical inputs and outputs behind
`../2026-08-31-k1-j1-domain-refloorplan.md`. The 60 generated candidate boards
are intentionally omitted; `manifest.json` retains every placement, candidate
board hash, target-pair result, and REQ-SAFE signature needed to audit the
negative certificate.

## Frozen artifacts

| File | Purpose | SHA-256 |
|---|---|---|
| `build_authority.py` | Replaces J1 on the clean production board with the approved KiCad/JST land pattern at the original origin. | `add550df27ce87608ceac15b369c61bd308e3c549e1eb3b47ae111712b259e0d` |
| `search.py` | Frozen shared board, geometry, and REQ-SAFE helpers; its `main()` is the invalidated calibration and is not part of the verdict. | `1cbf2fe7eeabb959134000c654c39ef858fdfb2a11db35a3c55d83d8b99267b2` |
| `search_v2.py` | Corrected, fixed-obstacle-clear family declaration, materializer, and evaluator. | `6674b24e2b634f698daadf218d3c70c3c06116556c0058d44c3d0ae11fd01d17` |
| `declaration.json` | Candidate family frozen before materialization. | `3edeb18206004e98d07903860c5ff1bf377e96c9b97b845d1ae2c98cce1a833f` |
| `manifest.json` | Complete 60-candidate corrected result manifest. | `f7a56e454007eebf342357b5fad6892a681f8a41d0be5d0702540cce81e9e95b` |
| `negative-certificate.md` | Scratch-time stop certificate. | `3a72b4bb740687a52221e8efa449ba689b5e475e520846c5f646ef6c370e063e` |

## Replay recipe

1. Check out clean commit
   `faac70f39db924dcbeb162be9fc27284f747a909`. Run `make netlist`, regenerate
   `pcb/temper.kicad_dru`, rebuild the pyo3 extensions with
   `env -u CONDA_PREFIX make extensions`, and confirm `make extensions-check`.
2. Create
   `/tmp/compound-engineering-1000/k1-j1-candidates/authority/`. Copy the
   clean board's basename-matched `.kicad_pro`, `.kicad_prl`, generated
   `.kicad_dru`, `fp-lib-table`, and `pcb/libs/` into that directory.
3. Run `build_authority.py pcb/temper.kicad_pcb
   /tmp/compound-engineering-1000/k1-j1-candidates/authority/temper.kicad_pcb
   --j1-y 237.0 --footprint-only`. Verify the board SHA-256 is
   `5ef29bfda80ac96cd490bed0b8881835f807eba3fa60b2b126eefc16eaf26e8a`.
4. Copy `search.py` and `search_v2.py` to
   `/tmp/compound-engineering-1000/k1-j1-refloorplan-20260831/`. If the
   checkout is elsewhere, change only `ROOT` in `search.py`; the board outputs
   and measured results are path-independent. From that directory, run
   `uv run --no-sync python search_v2.py`.
5. Compare all candidate board SHA-256 values and measurement records with
   `manifest.json`. A byte-identical manifest requires the original absolute
   paths recorded inside it; a checkout at another path must compare the
   semantic fields and candidate board hashes after excluding `source`,
   `board`, and `supersedes_calibration_manifest` path strings.

The runner writes only beneath `/tmp`; it does not edit the production board.
Its ranking differs from the plan's aspirational KTD1 ordering, but the
corrected polygon filter retained only 60 candidates against a 96-candidate
screen budget. All 60 were evaluated, so ordering cannot change this negative
result.
