# Native-18 verification, 2026-10-02: dead-time resistor value revision

Native-18 implements the **2026-10-03 R9/R17 owner decision** in
[DECISIONS.md](../../DECISIONS.md), under [D-16](../../validation-results/01-switching-parasitics/round17/delegation/D16-native18-dt-resistors.md).
Both resistors change from RC0603FR-0739KL (39 kΩ ±1 %) to
**RT0603BRD0749K9L (49.9 kΩ ±0.1 %, ±25 ppm/°C)**. The source class is
`R49k9Dt`; both leg instances retain the same 0603 footprint and nets.
The decision estimates 396.6–488.0 ns; this revision does not add a new timing
measurement or change the 1.9 V screen.

The starting board is native-17's active presentation board:
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
Native-18 SHA-256:
`fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002`.
Reversing four substitutions (R9/R17 Value and MPN) reproduces the original
board bytes exactly. The schematic has two corresponding substitutions.
**Every pose, footprint, pad, track, via, zone fill, label and 3D model is
otherwise byte-identical.** No saved zone refill delta was accepted.

| Check | Result |
| --- | --- |
| Fresh source build / audit | Compiled and exported; 135 components / 83 nets; PASS |
| Source parity | PASS: 135 footprints, 388 copper pads, 368 unique source pins |
| Authored copper identity | PASS: 641 tracks, 177 vias, six inherited route batches |
| Saved copper export vs native-17 presentation | Identical items, census and items hash; only board path/hash differ |
| Full DRC, in-memory refill + three repeats | Exact prior violation lists: 36 library notices, 3 L1/J3 silk overlaps, 0 copper findings, 0 schematic mismatch |
| Opens | Only the intended R5 Kelvin split; full pad clusters identical. DRC's representative open endpoints vary |
| PTH outer lands / JLCPCB | PASS: 116/116 on both F.Cu and B.Cu |
| Saved stackup | PASS |
| Barrier | 0 (Rust) and 0 (pinned Python oracle) |
| Hardware surface | 0 normal / 0 bring-up hits |
| Placement metrics | Identical, excluding board path |
| Power screens | Identical output: 0.886 / 0.457 |
| Source audit mutation tests | 53/53 (historical fixtures retained; new frozen source separately audited above) |
| Board tests | 46/46, existing suite retargeted to native-18 in temporary copies; no assertion changes |
| FEM region comparison | Both legs UNCHANGED; no FEM rerun |

Exact [leg-region-diff.txt](leg-region-diff.txt):

```text
leg A: UNCHANGED -> no FEM rerun
leg B: UNCHANGED -> no FEM rerun
RESULT {"stackup_changed": false, "fet_flags": [], "rerun_needed": false, "legs": {"A": "UNCHANGED", "B": "UNCHANGED"}}
```

## Generation and provenance

`tools/build_source.py` compiled unchanged source first, reproducing the
historical BOM and netlist after source-directory normalization, then compiled
the changed source into `source-build-01`. Its three fresh exports are frozen
in [../frozen/](../frozen/); the unit's historical `frozen/` is unchanged so
older revisions and test fixtures keep their original inputs.
The BOM changes only the R9/R17 row (MPN and description). The netlist is
identical after source-path normalization. Atopile 0.2.69 aliases component
values by footprint in that netlist; the per-instance resolved export and BOM
supply the part/value authority. The resolved attributes differ only at
`leg_a.r_dt` and `leg_b.r_dt`, for MPN and value.

The routed board and schematic were copied from native-17 and patched only at
those field occurrences. `tools/build_native.py` was inspected, but not run:
it generates an unrouted placement and applies the stackup/PTH policy; it has
no operation that preserves this routed presentation board. Rebuilding and
routing it would exceed the exact-change scope. The existing native parity,
copper identity, saved-stackup and assembly validators were run against the
result instead. This is a bounded field revision, not a claim that the native
builder or bridge was rerun.

The source manifest updates the two component records, the two corresponding
source-attribute records, and the fresh source input hashes/path. Its original
`board_sha256` and `strict_bridge_extension` remain historical generation
provenance: the former anchors the inherited route-receipt chain, not the
current routed board. The added `value_only_revision` block binds the actual
native-17/native-18 board hashes and explains that distinction. Libraries,
route receipts, stackup, rules, project and schematic layout are byte-identical.

Existing Rust validator binaries were reused. **No Rust workspace or native
bridge was built.** Only the standalone `audit.rs` executable and its test
harness were compiled, as used by the source-audit gate. Commands and return
codes are in [commands.json](commands.json), [drc-commands.json](drc-commands.json)
and [probe-commands.json](probe-commands.json). Test adaptation and input hashes
are in [board-tests-receipt.json](board-tests-receipt.json); source compilation
is in [source-build-receipt.json](source-build-receipt.json).

To repeat the bounded identity comparison from the repository root:

```sh
python3 zapote/power-stage-120v/native-18/verification/verify_identity.py
```

Its saved result is [identity.json](identity.json). The negative checks in
[identity-negative-checks.json](identity-negative-checks.json) reject a stale
board MPN, a reverted source value and disabled Python assertions. Runtime,
source and reused validator hashes are in [run-provenance.json](run-provenance.json). The other receipts contain
absolute paths used during measurement; substitute local checkout/runtime
paths when replaying. Run commands from `zapote/power-stage-120v/`.
The four power probe scripts are inherited from native-17, with only the
hardware probe's unit path made relative to its new location. The copper
export retains native-17's documented `IsOnLayer` inner-ring overcount; these
unchanged screening results are not a new current/thermal qualification.

## Owner handback

**D4 placement-approval carry-over remains the owner's call.** No such
approval is asserted here. S4 hard turn-on remains open under the recorded
decision; confirm gate timing during authorized bring-up.
**Not a fabrication or powered-operation release.**
