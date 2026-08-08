# DRC / Safety-Check Vacuity Audit (2026-08-08)

**Status: IN PROGRESS — this is an incremental checkpoint, committed early per
working-style instructions so partial results survive an interrupted session.
Sections marked `TODO` are not yet covered. See the bottom "Coverage" section
for what remains.**

## Why this document exists

`IsolationCheck` (`packages/temper-drc-rs/src/rules/safety/isolation.rs`) was
found to be both **structurally blind** (matches net-class *names*, never
checks position — because `constraints::ZoneDefinition` dropped the `bounds`
field that `drc_contracts::ZoneDefinition` still carries) and **dead**
against this project's own `temper_constraints.yaml` (no zone name matches
its isolation keywords, so it evaluates zero things on the real config).
This document audits every other DRC/safety rule and validator in the
project for the same two failure modes, per the brief in
`docs/plans/...` (see task description in git history / commit message).

This is an audit only. Findings are reported, not fixed — a separate agent
is repairing the isolation detector specifically.

## Top-line finding (flag before anything else)

**The entire 27-rule Rust DRC engine (`temper_drc_rs::create_default_registry()`,
covering all of `drc/`, `erc/`, `safety/`, `emc/`, `placement/`, `routing/`) is
not wired into CI as a pass/fail gate against the real board at all.**

- The actual CI ceiling gate is `.github/workflows/regression.yml:190`:
  `uv run python scripts/ci_check_drc.py --backend kicad-cli` — always the
  explicit `kicad-cli` backend. `scripts/ci_check_drc.py`'s own argparse
  default is likewise `kicad-cli`. Grepping every `.github/workflows/*.yml`
  file for `--backend rust` and for any other invocation of `ci_check_drc.py`
  found none.
- `kicad-cli` backend runs KiCad's own DRC against a generated `.kicad_dru`
  file (`scripts/generate_kicad_dru.py`), which is a real, independently
  evidenced clearance/creepage gate (uses kicad-cli 10.0.4's native
  `constraint creepage (min ...)` syntax; see that script's own comments
  citing `docs/evidence/2026-07-28-drc-creepage-constraint.md` for empirical
  verification that the constraint actually fires). So the board's *real*
  clearance/creepage enforcement, as shipped, lives there — not in the Rust
  `safety::*` rules this document is about.
- Consequence: the 27 Rust rules (including all three `safety/` rules) are
  built and imported in every CI workflow (`maturin develop`, "Verify
  temper-drc-rs loads") but are exercised only by (a) unit/differential
  tests against synthetic fixtures that assert rust-vs-python *parity* —
  meaningless if both sides are blind the same way, since parity tests
  cannot detect "both are always right because both never fire"; (b) the
  standalone `temper-drc` CLI (`drc_cli.py`), which no CI workflow calls;
  (c) `DrcRatchet`'s `"rust"` backend path (its class default — see
  `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py:243`)
  — but the one caller that runs on real PRs (`ci_check_drc.py`) always
  overrides this to `kicad-cli`.
- **Independently**, even if the `"rust"` backend were selected,
  `DrcRatchet._run_rust_drc` (`drc_ratchet.py` lines ~355–394) builds its
  `constraints_dict` from scratch with `zones: []`, `clearances: []`,
  `critical_loops: []`, `noise_domains: []`, `isolation_barriers: []`,
  `thermal_properties: []`, and every `net_class_rules[*].safety_category` /
  `.creepage_mm` / `.voltage_v` / `.max_current_rating` hardcoded to `None`,
  plus `hv_clearance_mm` hardcoded to `10.0` rather than read from
  `temper_constraints.yaml`. Through *this* path, `IsolationCheck`,
  `ZoneContainmentCheck`, `LoopAreaCheck`, `NoiseCouplingCheck`, and
  `IsolationBarrierCheck` would be dead a second, independent way (their
  input collections are always empty), regardless of each rule's own
  internal defects documented below.
- By contrast, the *other* Python→Rust conversion path,
  `temper_placer.validation.drc_runner._constraints_to_dict`
  (`drc_runner.py` line ~141–160), does forward zone bounds correctly
  (`"bounds": list(z.bounds)`), and the Python-facing `ZoneDefinition`
  pyclass (`drc_contracts.rs:1752`, exposed via `drc_types.py`) does carry a
  `bounds` field end-to-end from YAML through the dict boundary. The bounds
  data is thrown away at exactly one point: `constraints::ZoneDefinition`
  (`packages/temper-drc-rs/src/constraints.rs:31-35`) has no `bounds` field
  and no `#[serde(deny_unknown_fields)]`, so
  `serde_json::from_value(json_val)` (`constraints.rs:213`) silently drops
  the incoming `"bounds"` key during deserialization. This confirms the
  isolation defect is a single localized gap (missing field + a rule that
  never reads geometry) rather than a structural absence of bounds data
  anywhere upstream — useful context for whoever repairs it.

This does not mean the induction-cooker board ships without clearance/creepage
protection — `generate_kicad_dru.py` + kicad-cli appear to be a real,
evidenced gate for those two properties specifically. It does mean: (1) the
Rust safety layer audited below gives false confidence to anyone who reads
its code/tests without knowing it never runs against the real board in CI,
and (2) properties that `generate_kicad_dru.py` does *not* also encode
(isolation-zone component placement, HV/LV component-to-component separation,
package-level creepage-by-width) have **no enforcement at all** if the Rust
rules covering them are additionally blind/dead — which is exactly what the
per-rule sections below assess.

## Methodology

For each rule: read the implementation, identify every field/collection it
reads, check whether that field/collection is structurally capable of
carrying the geometry needed (grep the type definitions and every populator),
and count how many real items it would examine by tracing its inputs against
`packages/temper-placer/configs/temper_constraints.yaml` and
`pcb/temper.kicad_pcb` (via `python3`/`yaml`, `rg`, and `cargo test` where a
fixture-driven test exists). "Zero" is the finding being hunted for. Where
possible, a concrete failing input is constructed or an existing test is
cited that proves the rule *can* produce a non-empty violation list; where
not possible, that is stated explicitly as the strongest evidence of
vacuity.

Work was carried out in a dedicated worktree
(`audit/drc-vacuity-2026-08-08`, branched from `agent/router-combined`) so as
not to touch the primary checkout. No production code was modified.

## Rule registry (ground truth)

`packages/temper-drc-rs/src/rules/mod.rs::create_default_registry()` registers
27 rules:

| Category | Rules |
|---|---|
| `drc` | ClearanceCheck, ComponentOverlapCheck, CourtyardCheck(0.05), ZoneContainmentCheck, TraceClearanceCheck, ViaSpacingCheck |
| `erc` | NetConnectivityCheck, PowerDomainCheck, FloatingPinsCheck |
| `safety` | HVLVSeparationCheck, CreepageCheck(6.0), IsolationCheck |
| `emc` | LoopAreaCheck, NoiseCouplingCheck, GroundPlaneCheck |
| `placement` | ThermalViaCountCheck, WaveSolderKeepoutCheck |
| `routing` | ParallelRunCheck, StitchingViaDensityCheck, CopperPullbackCheck, IsolationBarrierCheck, ThtThermalReliefCheck, PowerPadTeardropCheck, PartialDischargeCheck, PadEntryWidthCheck, SplitPlaneCrossingCheck, IsolationSlotCheck |

Plus the standalone `packages/temper-drc-rs/src/req_safe_01.rs` (REQ-SAFE-01
validator, not part of the rule registry — invoked separately), the Python
validators under `packages/temper-placer/src/temper_placer/validation/`, and
the `scripts/check_*.py` gates.

## Per-rule findings: `safety/` category (highest consequence — audited in full)

| Rule | Claims | Actually checks | Structurally capable? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `IsolationCheck` (`safety/isolation.rs`) | No component except declared isolation devices inside an isolation zone | `constraints.zones` filtered by 6 name keywords (`iso/opto/coupler/transformer/gutter/slot`, `isolation.rs:19-20`); for matching zones, `zone.net_classes.iter().any(\|zc\| zc == comp.net_class)` — a **string equality on net-class name**, not a position test. `cx`/`cy` (line 91-92) are computed and put into the violation's `Location` payload only — never used for containment. | **No.** `constraints::ZoneDefinition` (`constraints.rs:31-35`) has only `{name, net_classes}` — no `bounds`/polygon field exists to compare against a component's position, even in principle. | **0.** `temper_constraints.yaml` defines 4 zones (`power_zone`, `driver_zone`, `control_zone`, `interface_zone`); none match the 6 keywords. `iso_zones` filters to an empty `Vec`, and `isolation.rs:79-81` returns `[]` immediately. Verified: `python3 -c "import yaml; d=yaml.safe_load(open('packages/temper-placer/configs/temper_constraints.yaml')); print(len(d['zones']))"` → `4`; none contain any of the 6 keywords. | **No — dead on real config, and structurally cannot fail even on a contrived config** (no geometry field exists to violate). |
| `CreepageCheck` (`safety/creepage.rs`) | "Verify isolation component width for creepage safety" — sufficient physical distance across the isolation barrier | For components matching `is_iso_component` (net_class_rules `safety_category == "iso"`, else keyword fallback on net_class name), checks `max(comp.width, comp.height) < min_iso_width_mm`. `min_iso_width_mm` is **hardcoded to `6.0`** at registration (`mod.rs:242`) — not read from `temper_constraints.yaml` (no `min_iso_width` key exists anywhere in that file or in the Rust `ConstraintSet` struct; the real per-class `creepage_mm` values that DO exist, e.g. `HighVoltage`/`ACMains` → `6.0` in `temper_constraints.yaml:net_class_rules`, are never read by this rule at all). | **Partially.** It does read real geometry (`comp.width`/`comp.height`), so it is not pure string-matching. But whole-package footprint size is a crude proxy for creepage distance (the shortest path along an insulating surface between two live conductors within/around the package) — package width is not creepage, and it says nothing about copper-to-copper creepage on the routed board (the thing `generate_kicad_dru.py`'s `constraint creepage` rules actually measure). It is also gated entirely by the same 8-keyword iso classifier as `IsolationCheck` (`iso/opto/coupler/isolator/transformer/adum/dcdc/mev1`) — no net class name in `temper_constraints.yaml` (`Signal, HighSpeed, Power, GND, GateDrive, HighVoltage, ACMains, HighCurrent`) matches any of those 8 keywords. | **0 by keyword fallback on the 8 net classes in `temper_constraints.yaml`.** The `safety_category=="iso"` declared path could in principle fire, but no net class anywhere in the codebase's SSOT manifests (`netclass_rules.yaml`, `temper_constraints.yaml`) declares `safety_category: "iso"` — grep confirms the only three values ever used are `HV`/`LV`/`AC`. So neither branch of `is_iso_component` can match on this project's real net classes; it would only fire for a component whose net-class *string* happens to contain one of the 8 keywords, which none currently do. | **Not demonstrated.** No isolation-transformer/optocoupler net class exists in the SSOT to exercise either branch. A synthetic component on a net class literally named e.g. `"opto"` with width/height < 6.0mm would trip it — confirming it is not *structurally* incapable like `IsolationCheck`, only currently unreachable given this board's net-class taxonomy. |
| `HVLVSeparationCheck` (`safety/hv_lv_separation.rs`) | IEC-60335-style HV/LV separation: edge-to-edge distance ≥ `hv_clearance_mm` | O(n²) pairwise loop over all components; `resolve_safety_category` prefers `net_class_rules.safety_category` (HV/LV/AC→HV), falls back to keyword match (`hv/line/ac/neutral/mains` vs `lv/signal/3v3/5v/gnd/analog`). For an HV/LV pair, computes **real bounding-box edge distance** `a.edge_distance_to(b)` against `constraints.hv_clearance_mm` (read from the real config — `10.0` in `temper_constraints.yaml:233` — not hardcoded in this rule). | **Yes, structurally** — the one of the three `safety/` rules that uses genuine geometry and a config-sourced threshold. But its *classification* step has a real gap (see next column). | Keyword-fallback check against the 8 real net classes (`python3` substring test): `HighVoltage`→HV (`"hv"`), `ACMains`→HV (`"ac"`,`"mains"`); `Signal`→LV (`"signal"`), `GND`→LV (`"gnd"`); **`GateDrive`, `Power`, and `HighCurrent` match neither list → `None`, i.e. invisible to this rule.** `HighCurrent` is described in `temper_constraints.yaml` itself as "High current power traces (IGBTs, bus caps)" at `voltage_v: 340.0` — a 340V/40A class arguably more dangerous than `HighVoltage` — yet by name alone it evades classification entirely. The SSOT manifest `packages/temper-placer/configs/netclass_rules.yaml` **does** declare correct `safety_category` values (`AC`/`HV`/`LV`) for the real per-net rules — but both real-board DRC-invocation call sites this audit traced (`drc_ratchet.py:354` and `drc_oracle.py:339,412`) hardcode `"safety_category": None` when building the dict handed to the Rust engine, so the declared-value branch never engages through those paths; only the untrusted keyword fallback runs. Component-pair count on the real board not obtained (would require loading `pcb/temper.kicad_pcb` through the full placer pipeline — outside this audit's time budget; flagged as a gap below). | **Not demonstrated in this session** (would need the real board loaded with `HighVoltage`/`Signal` component pairs closer than 10mm, or a synthetic fixture). Structurally the rule *can* fail — it is real geometry vs. a real threshold — but it demonstrably *cannot* fail for an HV violation for any component on `GateDrive`, `Power`, or `HighCurrent` net classes through either code path found, because those classes are never recognized as HV. |

## Coverage — what has and has not been audited yet

Audited in depth: `safety/isolation.rs`, `safety/creepage.rs` (partial —
structural analysis done, real-config item count still TODO),
`safety/hv_lv_separation.rs` (partial — same), the CI-gating chain
(`ci_check_drc.py`, `drc_ratchet.py`, `drc_runner.py`, `generate_kicad_dru.py`,
`constraints.rs` deserialization boundary).

**Not yet audited (TODO, to be completed and committed incrementally):**
- `drc/`: `clearance.rs`, `trace_clearance.rs`, `zone_containment.rs`,
  `via_spacing.rs`, `courtyard.rs`, `component_overlap.rs`
- `routing/`: `isolation_barrier.rs`, `isolation_slot.rs`,
  `partial_discharge.rs`, `copper_pullback.rs`, `split_plane_crossing.rs`,
  `pad_entry_width.rs`, `parallel_run.rs`, `stitching_via_density.rs`,
  `power_pad_teardrop.rs`, `tht_thermal_relief.rs`
- `emc/`: `ground_plane.rs`, `loop_area.rs`, `noise_coupling.rs`
- `erc/`: `floating_pins.rs`, `net_connectivity.rs`, `power_domain.rs`
- `placement/`: `thermal_via_count.rs`, `wave_solder_keepout.rs`
- `packages/temper-drc-rs/src/req_safe_01.rs` (REQ-SAFE-01 validator)
- Python `validation/` package: `rtd_safety.py`, `tht_check.py`,
  `geometric.py`, `drc.py`, `drc_fence.py`, `drc_oracle.py`, and others
- `scripts/check_*.py`: `check_isolation_keepout.py`,
  `check_hv_netclass_coverage.py`, `check_creepage_clearance_drift.py`,
  `check_net_classification.py`, `check_pad_orientation.py`,
  `check_board_containment.py`, and the remaining ~35 `check_*.py` scripts

Given the "rank by consequence" instruction, the plan is: finish the two
partial `safety/` rows first, then the isolation/HV-adjacent `routing/`
rules and `check_isolation_keepout.py` / `check_hv_netclass_coverage.py` /
`check_creepage_clearance_drift.py` (since `generate_kicad_dru.py`'s own
comments call `check_isolation_keepout.py` an "independent creepage
enforcement point" worth verifying), then `drc/clearance.rs` and
`trace_clearance.rs` (general clearance), then everything else in
descending consequence order, explicitly marking anything not reached by
the end of the session.
