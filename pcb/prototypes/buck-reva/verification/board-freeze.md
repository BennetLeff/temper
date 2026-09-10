# Buck Rev A — board freeze record

Frozen: 2026-09-10. Revision **A**. Project: `pcb/prototypes/buck-reva/`.

This document freezes one concrete board revision. Later changes to any file
listed in `source-manifest.json` invalidate this freeze and require a new one.

## Freeze identity

- Source manifest: `pcb/prototypes/buck-reva/source-manifest.json`
- Schema: `buck-reva.source-manifest.v1`
- **Source-manifest SHA-256: `7cf32ae8c6be81a46b73bc72a8edf469f70031affaefecdf3b0050be5369a0ea`**
- Frozen CAD hashes (full digests; also in the manifest):

| File | SHA-256 |
|---|---|
| `buck-reva.kicad_sch` | `1c6529104b5ce671406785a3c6b1508a9ae0a05ebf81f61423be6062659a56c5` |
| `buck-reva.kicad_pcb` | `cb8cca0bd5eaaf695e6c8a3e23a8e270f62b39f2ab4d08ffad7d9a9a850b3303` |
| `buck-reva.kicad_pro` | `260eaf039a2aa24c08389d5870da409e6ac1135a3be15633b4c96747fdf733e8` |
| `buck-reva.kicad_dru` | `e53161ef573ffc1623e5f4751f32a11e23d65479c83230e49e41cf93273cacf5` |
| `buck-reva.kicad_sym` | `d2eed7d974fe60449b1c14d568b9892415b6fabfa890490acbdc9cc7b7eb078d` |

The five hashes above are repeated here for convenience; `source-manifest.json`
is the authority and additionally pins `fp-lib-table`, `sym-lib-table` and
every local `.kicad_mod` (15 files total).

## Toolchain

- KiCad CLI **10.0.6**, `/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
  (verified with `kicad-cli version`). One runtime used for ERC, DRC and all
  renders; no legacy 10.0.4 checks are mixed into this receipt.
- The board, schematic and project file were confirmed byte-stable across
  `sch erc`, `sch export netlist` and `pcb drc` runs.

## Final interface (authoritative)

| Connector | Pin | Net | Silk |
|---|---|---|---|
| J1 (input) | J1.1 | `+15V` | `VIN` |
| J1 (input) | J1.2 | `gnd` | `GND` |
| J2 (output) | J2.1 | `+3V3` | `3V3` |
| J2 (output) | J2.2 | `gnd` | `GND` |

- J1, J2 part: **Würth Elektronik 691253500002**, DigiKey `732-691253500002-ND`
  — WR-TBL Series 2535, 2-position, 5.08 mm, **vertical (top) wire entry**,
  rising-cage screw, 16 A / 300 V (UL), 30–12 AWG, −30…+120 °C.
- Test points (bare copper pads, no purchased part):

| TP | Net | Silk/value |
|---|---|---|
| TP1 | `+15V` | `VIN` |
| TP2 | `gnd` | `GND` |
| TP3 | `+3V3` | `VOUT` |
| TP4 | `gnd` | `GND` |

- Optional SW access: **not populated**. No dedicated probe pad was added,
  because every candidate location lies inside L2's courtyard or would extend
  the switching-node copper. SW remains reachable at the U3.2 / L2.1 pads.
- Mounting: H1–H4, 3.2 mm non-plated holes for M3, isolated.
- Net-name aliases are recorded in `verification/connectivity.md`.

## Fabrication specification

- 2 copper layers, FR-4, 1.6 mm, 1 oz finished copper.
- Solder mask both sides; silkscreen both sides.
- Surface finish: lead-free HASL.
- Top-side assembly.
- Outline 50 × 40 mm.
- Design rules: 0.2 mm min track, 0.2 mm min clearance, 0.2 mm min
  copper-to-edge (`.kicad_dru` adds a 0.2 mm "buck copper clearance" rule;
  `buck-reva.kicad_pro` sets `min_clearance` 0.2 and
  `min_copper_edge_clearance` 0.2, Default netclass clearance 0.2).

## Native verification results (KiCad 10.0.6)

| Check | Result | Report |
|---|---|---|
| Schematic ERC (`--severity-all`) | **0 violations** | `verification/buck-reva-erc.json` |
| PCB DRC (`--all-track-errors --format json`) | **0 violations, 0 unconnected, 0 schematic-parity** | `verification/buck-reva-drc.json` |
| Schematic↔board connectivity | exact match, all 6 nets | `verification/connectivity.md` |
| Locality metrics (core) | all within limits (below) | this file |

Warning disposition: the final reports contain **no warnings**. Earlier
iterations' silk warnings (edge clearance, over-copper, overlap, text height)
and one dangling track were fixed in geometry, not suppressed; DRC exclusions
are empty.

## Locality metrics (supporting checks)

Measured on the frozen board; limits from `buck-v2-contract.json`.

| Check | Measured | Limit | Result |
|---|---|---|---|
| `input_locality` C9.1–U3.3 | 1.94 mm | ≤8.0 | PASS |
| `input_locality` C9.2–U3.1 | 6.52 mm | ≤8.0 | PASS |
| `boot_locality` C10.1–U3.6 | 3.07 mm | ≤6.0 | PASS |
| `boot_locality` C10.2–U3.2 | 4.02 mm | ≤6.0 | PASS |
| `output_locality` L2.2–C11.1 / C12.1 | 5.64 mm | ≤14.0 | PASS |
| `output_locality` L2.2–C13.1 | 4.68 mm | ≤14.0 | PASS |
| `fb_locality` R16.2–U3.4 | 4.53 mm | ≤10.0 | PASS |
| `fb_locality` R17.1–U3.4 | 4.48 mm | ≤10.0 | PASS |
| `fb_pair` R16.2–R17.1 | 4.00 mm | ≤6.0 | PASS |
| `fb_sw_separation` (pads + same-layer segments) | 2.47 mm | ≥1.0 | PASS |
| `ground_return` C9.2/C11.2/C12.2/C13.2 | 0.00 mm | ≤4.0 | PASS |

These are geometry checks, not performance measurements. The routed loops were
inspected directly (see the renders) in addition to the numeric checks.

## Reviewed artifacts

- `verification/renders/top.svg`, `verification/renders/bottom.svg` — 2D copper/mask/silk/outline, both sides.
- `verification/renders/top-3d.png` — assembled top 3D view.
- `verification/renders/schematic.pdf` — one-page schematic.
- `verification/buck-reva.net` — exported schematic netlist.
- `verification/footprints.md` — land-pattern/mechanical review.
- `verification/connectivity.md` — source/schematic/board connectivity review.

## Source provenance (upstream)

Recorded separately from the manufacturing input mapping (see
`source-manifest.json.source_provenance`):

| Upstream source | SHA-256 |
|---|---|
| `elec/src/modules.ato` | `d3873898d65300b5982eeba66d61b1ec4938c63ec29ce869d34a3ac8d11cc547` |
| `harness-lab/engineering/circuit-contract.json` | `2866d51e6176239275f945b97e560c75abbd2475ca22d81bbebea3cd95b9df44` |
| `harness-lab/fixtures/buck-v2/buck-v2-contract.json` | `eb69d057cdf0801f7257095e5818352408de183ead1d20dacab050df78569959` |
| `harness-lab/fixtures/buck-v2/buck-dev-a/witness.kicad_pcb` | `65143d7a6e7691ffed3c053bc767fa14fe4db14c768cc9eecbeae52db4cfdb5f` |
| `harness-lab/audits/buck-final-20260910/components/current-buck-bom.md` | `0cd86e3d210622f04e900596e7691c42f9928f4735e0695fd15199e0e4b233bb` |
| `harness-lab/audits/buck-final-20260910/source-build/collection.json` | `3702152ebe2570dbefddd328916f9a08efdbc3f29a506065435c05c6ff1b24d0` |
| `harness-lab/audits/buck-20260910-followup/layout.md` | `a28016f3e75e48193da9bd0450f7188ec11448d9668c684adb8cdf973dcea7e5` |
| `pcb/temper.kicad_pcb` (production, unchanged) | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |

The production board and all benchmark fixtures were left unchanged.

## Outstanding items (explicit)

- Combined capacitor derating, hot-inductor characterization, behavioral-model
  correlation and environmental qualification remain deferred; they are not
  required for this prototype build.
- No STEP model for L2 or the terminals (cosmetic only; dimensions verified).
- Physical assembly and bench measurements are **NOT RUN** and are out of scope
  for the board freeze.

## Release / bring-up handoff

- Manufacturing inputs: this project directory; manifest digest above.
- Release owner: export from the frozen files; do not hand-edit CAD.
- Bring-up owner: bind figures and runbook to revision A and the digest above.
- A later CAD change returns here for a new freeze.
