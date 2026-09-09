# Buck 3.3 V fixture qualification (U1)

Nine-component buck harness: U3, L2, C9–C13, R16, R17 from Temper's PCB plus
three protected single-purpose terminals (J1 VIN/+15V, J2 GND/gnd,
J3 VOUT/+3V3). Four frozen variants, two development and two reserved, each
with a passing native witness and intended failing controls.

## Provenance

- Source board `pcb/temper.kicad_pcb`: `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` (unmodified; receipt asserts equality).
- Schematic module `elec/src/modules.ato:BuckConverter3V3`. U3 enable (EN) is
  tied to +15V in schematic and board; there is no separate enable net.
- KiCad `10.0.4` for `pcbnew` and `kicad-cli` (both pinned by the adapters).
- Contract `harness-lab/fixtures/buck-contract.json`: `245787268137b99872bebf3c3a33fa2f390625cbf4c5619263d20a7898472d4b`.
- Judge `temper-harness-e00`: `e8cf172f9f5ea052bcee4dd4274ef23d188eb359d3ecf21ccef36e6f0da5cbf6`.
- TI LMR51430 datasheet layout section informed the locality/separation
  proxies; no TI numeric limit is encoded (see rules below).

## Variants (split predeclared before any model work)

| Variant | Split | Terminals (VIN/GND/VOUT) |
|---|---|---|
| buck-dev-a | development | (3,18) / (3,21) / (47,18) |
| buck-dev-b | development | (3,10) / (3,13) / (47,28) |
| buck-res-a | reserved | (3,26) / (3,29) / (47,32) |
| buck-res-b | reserved | (3,32) / (3,35) / (47,10) |

All share the 50 × 40 mm outline, two copper layers, and the witness
functional topology; staging grids and terminal access differ per variant.

## Witnesses

Each variant's `witness.kicad_pcb` passes three fresh native evaluations
(measure + `kicad-cli drc --all-track-errors --severity-all` + Rust judge):
zero DRC violations, zero open connections, all six nets single physical
islands, all numeric checks inside limits. F.Cu carries short power/signal
stubs; the ground return is a B.Cu spine stitched with vias; U3.5 joins U3.3
through a B.Cu link.

## Negative controls (intended finding IDs)

Per variant: missing terminal connection (`unrouted:`), wrong raw copper net
(`wrong_net:`), moved protected terminal (`terminal_moved:J1`), changed rules
(`protected_context_changed`). On buck-dev-a additionally: short
(`kicad:shorting_items:` plus `shorted_cluster:`), clearance
(`kicad:clearance:`), outside footprint (`outside_outline:C9`), and a
DRC-clean locality failure (`input_locality:`, 18.1 mm vs 8.0 mm limit, no
`kicad:*` and no opens). Malformed (`missing-buck-evidence`) and truncated
(`truncated-connectivity`) packets are indeterminate (exit 2), never pass.
A gnd-strip recovery (remove, re-route B.Cu spine, re-stitch 8 vias) returns
to pass in 10 edits; invalid/budget/preflight calls are indeterminate without
mutating the board.

## Numerical benchmark rules (proxies, not TI requirements)

TI mandates short, wide, direct input/output loops and a quiet feedback node
without millimeter limits. Frozen proxies, each clearing the witness with
margin while rejecting far-flung placements:

- `input_locality_max_mm` 8.0 (witness max 7.4)
- `boot_locality_max_mm` 6.0 (witness max 5.9; tight by construction — C10
  sits beside U3 to keep the boot link a short hop while clearing the sw
  exit lane, and native positions are bit-deterministic so the margin is safe)
- `output_locality_max_mm` 14.0 (witness 12.8)
- `fb_locality_max_mm` 10.0 (witness 7.9), `fb_pair_max_mm` 6.0 (witness 5.4)
- `fb_sw_separation_min_mm` 1.0 (witness 2.5)
- `ground_return_max_mm` 4.0 (witness 0.0; vias at pad centers)
- power width 0.6 ≥ 0.5 mm, signal width 0.3 ≥ 0.2 mm

## Rerun

```sh
make -C harness-lab build check
python3 harness-lab/qualify_buck.py harness-lab/runs/<fresh-output>
```

Qualification exits nonzero on incomplete evidence. Full reports live under
the run directory; the compact receipt is
`harness-lab/evidence/buck-qualification-receipt.json` with the evidence
archive alongside it.

## Construction notes (red phase preserved)

- Test-first: `test_buck_boundary.py` began as a failing import
  (`ModuleNotFoundError: buck_native`) before any implementation existed.
- Footprint copies share pad UUIDs, which collapsed six pads out of the
  connectivity census; terminals are therefore built from scratch pads.
- KiCad's save order varies run to run, so hashing re-saved file bytes made
  `protected_sha256` flaky (observed 2 values in 3 runs). The adapter now
  digests the protected semantics in sorted order instead.
- Vias initially skipped the raw-net check and passed a wrong-net mutant;
  every copper kind is now cluster-verified.
- Older profiles are untouched: `src/main.rs` only dispatches on
  `contract.profile == "buck"`; their Rust unit tests still pass.
