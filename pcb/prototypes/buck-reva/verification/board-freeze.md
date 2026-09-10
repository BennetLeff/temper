# Buck Rev A — board freeze record

Frozen: 2026-09-10. Revision **A**. Project: `pcb/prototypes/buck-reva/`.

This document freezes one concrete board revision. Later changes to any file
listed in `source-manifest.json` invalidate this freeze and require a new one.

> Supersedes an earlier same-day freeze whose DRC receipt did not enable
> KiCad's `--schematic-parity` check. That check is now enabled and included in
> this record; the board and schematic were additionally brought into field
> parity (footprint Value/Manufacturer/MPN/Datasheet fields and the four
> mounting-hole symbols). See "Change history" at the end.

## Freeze identity

- Source manifest: `pcb/prototypes/buck-reva/source-manifest.json`
- Schema: `buck-reva.source-manifest.v1`
- **Source-manifest SHA-256: `3f77b285623adf3fcdc1ccea152fedbf86431f3404f8b9c7b36003c398beebcb`**
- Frozen CAD hashes (full digests; also in the manifest):

| File | SHA-256 |
|---|---|
| `buck-reva.kicad_sch` | `f0a48a4c707a90fd7aa51a36d1879652492e78d1f08f8a87a944e9e9ee920a26` |
| `buck-reva.kicad_pcb` | `308131c56e3af2c9f40ee526018c6af945e92f42ad9db4c4d89710911c85390b` |
| `buck-reva.kicad_pro` | `b5a93ddb50cef2d550aaacdff28a67ecfa6ed2e060b945ca82bec222a287196b` |
| `buck-reva.kicad_dru` | `e53161ef573ffc1623e5f4751f32a11e23d65479c83230e49e41cf93273cacf5` |
| `buck-reva.kicad_sym` | `64406f8d76017d988a2e1f5c6a678c20fd38351862ea2d2f8b254c358986b268` |

`source-manifest.json` additionally pins `fp-lib-table`, `sym-lib-table` and
every local `.kicad_mod` (15 files total).

## Toolchain

- KiCad CLI **10.0.6**, `/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
  (verified with `kicad-cli version`). One runtime used for ERC, DRC and all
  renders; no legacy 10.0.4 checks are mixed into this receipt.
- The board, schematic, project and library files were confirmed byte-stable
  across the export commands (`sch erc`, `sch export netlist`,
  `pcb drc`, `pcb drc --refill-zones`, `pcb export pos`). The `.kicad_pro`
  stored here is KiCad's canonical serialization and is idempotent under
  kicad-cli.

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
- Mounting: H1–H4, 3.2 mm non-plated holes for M3, isolated (symbols present in
  the schematic for parity; excluded from the BOM).
- Net-name aliases are recorded in `verification/connectivity.md`.

## Fabrication specification

- 2 copper layers, FR-4, 1.6 mm, 1 oz finished copper.
- Solder mask both sides; **front** silkscreen only (no back silk artwork).
- Surface finish: lead-free HASL.
- Top-side assembly.
- Outline 50 × 40 mm.
- Rules: Default netclass clearance 0.2 mm and `min_track_width` 0.2 mm; the
  project-local `buck-reva.kicad_dru` adds a 0.2 mm "buck copper clearance"
  rule; `min_copper_edge_clearance` is KiCad's 0.5 mm default (stricter than
  the 0.2 mm starting rule).
- **Via treatment (assembly note):** the nine-device core carries nine vias
  placed at SMD pad centres (via-in-pad), 0.8 mm / 0.4 mm, including the U3
  GND pad and the R16/R17 feedback divider. They are mask-tented but not
  filled/capped. For reflow assembly, either accept via-in-pad at these joints
  or specify IPC-4761 Type VII fill+cap; hand-soldering those joints is also
  acceptable for this prototype. Flagged for the release owner's assembly
  notes.

## Native verification results (KiCad 10.0.6)

Command: `kicad-cli pcb drc --all-track-errors --schematic-parity --severity-all --format json`.

| Check | Result | Report |
|---|---|---|
| Schematic ERC (`sch erc --severity-all`) | **0 violations** | `verification/buck-reva-erc.json` |
| PCB DRC (with `--schematic-parity --severity-all`) | **0 violations, 0 unconnected, 0 schematic-parity** | `verification/buck-reva-drc.json` |
| Schematic↔board connectivity | exact match, all 6 nets | `verification/connectivity.md` |
| Locality metrics (core) | all within limits (below) | this file |

Warning disposition: the final reports contain **no warnings**. Earlier
iterations' issues (silk edge/overlap/over-copper, one dangling track, and
60 schematic-parity warnings) were fixed in geometry/data, not suppressed; DRC
exclusions are empty. The 60 parity warnings were 30 root-prefix `net_conflict`
entries (fixed by using global labels), 15+11 footprint/symbol field
mismatches (fixed by syncing the board footprint Value/Manufacturer/MPN/
Datasheet and Description fields from the schematic), and 4 extra mounting-hole
footprints (fixed by adding H1–H4 symbols to the schematic).

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

Caveat (recorded): `ground_return` is structurally 0.00 because a ground via
sits at each of those pad centres; it confirms the pads are connected and says
nothing about return-path length or impedance. Ground return is a routed B.Cu
network (17 segments, 0.6 mm); there is no ground plane/zone. The routed loops
were inspected directly in the renders; this is a geometry check, not a
measurement of transient performance.

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

## Change history

- **rev A (first freeze, superseded):** manifest
  `7cf32ae8c6be81a46b73bc72a8edf469f70031affaefecdf3b0050be5369a0ea`. DRC
  command omitted `--schematic-parity`; the "0 parity" claim was unsupported.
- **rev A (this freeze):** global labels, board↔schematic field sync, and
  H1–H4 schematic symbols added; DRC now runs with `--schematic-parity` and
  reports 0. Manifest digest above.

## Outstanding items (explicit)

- Fabricator capability for the frozen spec (2-layer, 1.6 mm, 1 oz, lead-free
  HASL, 0.2 mm min track/clearance, 1.5 mm terminal holes) is a standard,
  widely supported capability but was **not** verified against a selected
  fabricator; fabricator selection and capability confirmation belong to the
  release owner.
- Via-in-pad treatment (see fabrication note) is an assembly decision.
- Combined capacitor derating, hot-inductor characterization, behavioral-model
  correlation and environmental qualification remain deferred; they are not
  required for this prototype build.
- No STEP model for L2 or the terminals (cosmetic only; dimensions verified).
- Physical assembly and bench measurements are **NOT RUN**.

## Release / bring-up handoff

- Manufacturing inputs: this project directory; manifest digest above.
- Release owner: export from the frozen files; do not hand-edit CAD.
- Bring-up owner: bind figures and runbook to revision A and the digest above.
- A later CAD change returns here for a new freeze.
