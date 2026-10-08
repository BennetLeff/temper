# Zapote: individual ERC/DRC findings and fab-house DFM limits

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Make zapote's checks usable on a real board. KiCad ERC/DRC results reach the agent as one finding per violation, with type, location, items and actual/required values. DFM checks run against real fab-house limits taken from a source-quoted vendor profile. One command checks any saved KiCad board.

**Architecture:**
- `zapote-harness::native_reports` keeps its four summary findings for compatibility and adds one finding per KiCad violation, parsed into typed structs. Malformed entries fail closed.
- `zapote-drc::manufacturing::FabricationLimits` gains optional per-rule limits. New P2 rules are checked only when the profile supplies their limit. The PTH-ring and via-ring limits are separate.
- Vendor profiles live in `zapote/fab-profiles/*.json`. Each carries verbatim quotes and the date the source was read. The unit runner and the new `zapote-check` CLI load a profile into the extractor receipt.
- The Python extractor stays a transport. It adds the hole kind and track width it already reads from pcbnew; it invents no limits.

**Tech Stack:** Rust (zapote workspace, `--locked`), KiCad 10 pcbnew Python (extractor), `kicad-cli`.

**Spec:** this plan. The facts it rests on:
- `native_reports.rs:134-158` reduces every KiCad result to four counts.
- `validation/p2/extract.py:162` writes zero limits.
- `jlc_dfm_check.py` applies the 2 oz PTH ring (0.254 mm) to vias, which is wrong per your vendor-rule note.
- JLC capabilities page, read 2026-10-08 (quotes below).

## Global constraints
- Rust owns rule logic and verdicts. Python only transports pcbnew data.
- A missing limit or input never becomes a pass. Report it as a coverage gap or an indeterminate.
- Numbers come from verbatim vendor quotes with a read date (vendor-rule memory).
- Never `git stash`. One worktree, one cargo build. Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## JLCPCB quotes (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-10-08)

| Rule | Quote |
|---|---|
| Track / space | 1 oz: "1- and 2-layer: 0.10 / 0.10 mm (4 / 4 mil)"; "Multilayer: 0.09 / 0.09 mm (3.5 / 3.5 mil)". 2 oz: "2-layer: 0.16 / 0.16 mm (6.5 / 6.5 mil)"; "Multilayer: 0.15 / 0.15 mm (6 / 6 mil)" |
| Via | "Min. Via hole size/diameter: 0.15/0.25mm"; "Via diameter should be 0.1mm(0.15mm preferred) larger than Via hole size." |
| PTH drill | "2-layer: 0.15 – 6.3 mm"; "Multilayer: 0.15 – 6.3 mm"; "Holes with diameter ≥ 6.3 mm are CNC routed from a smaller drilled hole." |
| PTH ring | 2-layer "1 oz: Recommended 0.25 mm or above; absolute minimum 0.18 mm", "2 oz: 0.254 mm or above"; multilayer "1 oz: Recommended 0.20 mm or above; absolute minimum 0.15 mm", "2 oz: 0.254 mm or above" |
| Hole spacing | "Via Hole-to-Hole Spacing: 0.2mm"; "Pad Hole-to-Hole Spacing: 0.45mm" |
| Edge | "Copper clearance from routed board edges: ≧0.2 mm" |
| NPTH | "Min. Non-plated holes: 0.50mm" |
| Size | "FR4(2-layer): 670 × 600 mm"; "FR4(4-layer): 663 × 593 mm" |

**Decisions:**
1. A profile's ring limit is the vendor's *absolute minimum*. The "recommended" figure is kept as a quote, not enforced.
2. Via ring = (diameter − hole) / 2 ≥ 0.05 mm, derived from "0.1mm larger".
3. Hole pairs: via/via uses the via rule (0.2 mm); every other pair, including a via/pad pair the vendor doesn't define, uses the stricter pad rule (0.45 mm). This is recorded in the profile's `notes`.
4. Track *spacing* stays with KiCad's native DRC (board rules). P2 adds a *minimum track width* check.

## Review focus
1. A new rule silently passes because its limit or input is missing. It must not appear in `checked_rules`, and missing per-object data must be indeterminate.
2. Vias judged against the PTH ring (the native-21 incident).
3. Per-violation parsing drops a field: unknown or missing `type`, `items`, or `pos` must fail the report contract, not be skipped.
4. Old receipts without the new fields (hole `kind`, `tracks`) must still deserialize, and their new rules must report a gap.
5. Per-violation findings on large boards (258 unconnected items on native-02) must keep reports usable; no quadratic work per violation.

---

### Task 1: Per-violation native findings
**Files:** `zapote/packages/zapote-harness/src/native_reports.rs`, `zapote/packages/zapote-harness/tests/native_reports.rs`

**Produces:** `pub struct NativeViolation { pub category: &'static str /* ERC|DRC|UNCONNECTED|SCHEMATIC_PARITY */, pub kind: String, pub severity: String, pub description: String, pub sheet: Option<String>, pub items: Vec<NativeItem> }`, `pub struct NativeItem { pub description: String, pub x_mm: f64, pub y_mm: f64, pub uuid: String }`, `pub fn violations(erc: &str, drc: &str) -> Result<Vec<NativeViolation>, String>`.

`validate` returns the existing four summary findings plus one `Finding` per violation:
- `rule`: `NATIVE.<CATEGORY>.<type>`
- `severity`: KiCad's severity
- `status`: `Fail`, matching the existing contract where any reported finding, including exclusions, fails
- `message`: KiCad's description
- `object`: each item as `"<description> @ (x, y) [uuid8]"`, joined with `"; "`
- `actual` / `required`: parsed from `(<constraint> <v> mm; actual <v> mm)` when present

Tests, using real captures:
- [ ] The `interlock/final-native-01` ERC gives 25 findings `NATIVE.ERC.endpoint_off_grid`; the first object contains `Symbol J1 Pin 1` and `@ (0.398, 0.626)`. The summary finding still starts with `"25 "`.
- [ ] Inject the real clearance violation from `fabrication/.../release-prep/interlock-drc-at-0p20mm.json` into the clean `final-native-04` DRC. This gives `NATIVE.DRC.clearance` with `actual = "0.1900 mm"` and `required = "0.2000 mm"`, an object naming both the Track and the Via, and overall status Fail.
- [ ] A violation missing `type`, `items`, or an item `pos` makes the report `NATIVE.REPORT_CONTRACT` Fail.
- [ ] Unconnected items become `NATIVE.UNCONNECTED.<type>` findings.
- [ ] All existing tests still pass.

### Task 2: FabricationLimits, hole kinds and new P2 rules
**Files:** `zapote/packages/zapote-drc/src/manufacturing.rs`, `zapote/packages/zapote-drc/tests/manufacturing_limits.rs` (new)

**Produces:**
- `FabricationLimits` gets these new fields, each `#[serde(default)]` and of type `Option<f64>` unless noted: `minimum_via_annular_ring_mm`, `minimum_track_width_mm`, `minimum_via_drill_mm`, `minimum_pth_drill_mm`, `maximum_pth_drill_mm`, `minimum_npth_drill_mm`, `minimum_via_hole_clearance_mm`, `minimum_copper_to_edge_mm`, and `maximum_board_mm: Option<[f64; 2]>`.
- `pub enum HoleKind { Via, Pth, Npth }`. `PadGeometry.kind: Option<HoleKind>` and `DrillHole.kind: Option<HoleKind>`, both `#[serde(default)]`.
- `ManufacturingInput.tracks: Vec<Track { id, layer, width_mm }>`, `#[serde(default)]`.
- New rule IDs: `DRC.P2.TRACK_WIDTH`, `DRC.P2.DRILL_SIZE`, `DRC.P2.EDGE_CLEARANCE`, `DRC.P2.BOARD_SIZE`.

Behavior:
- **Ring:** pads with kind `Via` use `minimum_via_annular_ring_mm`, falling back to the legacy limit only when that is None. Other plated pads use `minimum_annular_ring_mm`.
- **Hole pairs:** via/via uses the via clearance (falling back to the legacy limit), and any other pair uses `minimum_hole_clearance_mm`.
- **Coverage:** a new rule is added to `checked_rules` only when its limit is Some. If the limit is Some but the input lacks the data it needs (no kind, or no `tracks` field), report a coverage gap or an indeterminate, never a pass.
- **Edge clearance:** the minimum distance from each copper polygon to the outline boundary and to each cutout must be ≥ the limit. Copper outside the outline stays an `OUTLINE` failure.

Tests (TDD, synthetic polygons):
- [ ] A via ring of 0.06 passes with a via limit of 0.05 and a PTH limit of 0.254; a PTH pad with ring 0.2 fails.
- [ ] A 0.10 mm track fails a 0.15 limit, with actual and required set.
- [ ] Drill sizes: via 0.1 fails a 0.15 minimum; PTH 7.0 fails a 6.3 maximum; NPTH 0.4 fails 0.5.
- [ ] Holes 0.3 mm apart: a via/via pair passes 0.2; a PTH/PTH pair fails 0.45.
- [ ] Copper 0.1 mm from the outline fails a 0.2 limit; at 0.3 mm it passes.
- [ ] A 700 × 100 mm board fails a 670 × 600 maximum.
- [ ] Legacy receipts: an old JSON without the new fields deserializes, keeps the old results, and the new rules are absent from `checked_rules`.
- [ ] A profile with a track limit but an input with no `tracks` gives a coverage gap, not a pass.

### Task 3: Extractor transports hole kind and track width
**Files:** `zapote/validation/p2/extract.py`, `zapote/validation/p2/test_extract.py`
- Pads get `"kind": "pth" | "npth"`. Footprint holes get `"kind"` from the pad attribute. Via pad and hole entries get `"kind": "via"`.
- Tracks become `{"id", "layer", "width_mm"}` (arcs included, width from `GetWidth()`).
- `limits` stays empty. Profiles are applied by Rust callers.
- [ ] Extend `test_extract.py` to assert the new kinds and track widths on a real board; run it with KiCad's Python.

### Task 4: Vendor profiles, loader and runner wiring
**Files:**
- `zapote/fab-profiles/{jlcpcb-2layer-2oz,jlcpcb-4layer-1oz,jlcpcb-4layer-2oz}.json`
- `zapote/packages/zapote-drc/src/fab_profile.rs`
- `zapote/packages/zapote-harness/src/runner.rs`
- `zapote/validation/units.json`

**Produces:** schema `zapote.fab-profile.v1` with `{ name, vendor, source, read, limits: FabricationLimits-compatible, quotes: {field: "verbatim"}, notes }`, and `pub fn load_profile(path) -> Result<FabricationLimits, String>`. The loader rejects any limit that has no quote, so no number goes in unsourced.

Runner: `units.json` entries get an optional `"fab_profile"`, resolved relative to the manifest. When it is present, the receipt's `input.limits` is replaced before validation, and the profile's hash is recorded in `manufacturing-command.json`.

- [ ] Loader tests: the real profile files load; a limit without a quote is rejected; an unknown field is rejected.
- [ ] Assign profiles to the five units: RTD → `4layer-1oz`, others → `2layer-2oz`.

### Task 5: `zapote-check` — any board, one command
**Files:**
- `zapote/packages/zapote-harness/src/bin/zapote-check.rs`
- `zapote/packages/zapote-harness/src/board_check.rs`
- `zapote/Makefile` (`check-board BOARD=... PROFILE=...`)
- `zapote/CHECKS.md`

Inputs: `zapote-check --board B.kicad_pcb [--schematic S.kicad_sch] --profile P.json --kicad-cli K --python KICAD_PY --output DIR`.

What it does:
1. Runs `kicad-cli pcb drc` (and `sch erc` when a schematic is given) with the flags the contract requires, and writes the reports and command receipts.
2. Runs the P2 extractor and applies the profile.
3. Writes `report.json`, containing every finding and the hashes of the inputs, profile and tools.
4. Prints the failing findings grouped by rule, with location and actual/required values.

Exit codes: 0 when everything passes, 1 on any fail, 2 when the result is indeterminate or an input is missing.

- [ ] Integration test (ignored by default; needs KiCad), on `power-stage-120v/native-17`: run to completion, check that every finding has a rule and an object, and check that `report.json` binds the board hash.
- [ ] Run it on all five unit boards and native-17/native-21, and record the results in the PR (the ledger).

### Task 6: Verify and ship
- [ ] `cargo test --release --locked --workspace` (zapote) green. Clippy 1.97 is clean on the changed crates, if CI runs it on zapote; it doesn't today, so this is best-effort.
- [ ] `make -C zapote check-units` still runs. Compare the DFM results with the old run.
- [ ] Cross-check against an independent oracle: `jlc_dfm_check.py`, PTH pads and tracks only, since its via rule is known wrong.
- [ ] Open the PR, get CI green, merge.
