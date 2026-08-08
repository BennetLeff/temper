# DRC / Safety-Check Vacuity Audit (2026-08-08)

**Status: IN PROGRESS — this is an incremental checkpoint, committed early per
working-style instructions so partial results survive an interrupted session.
Sections marked `TODO` are not yet covered. See the bottom "Coverage" section
for what remains.**

## Flagged for immediate attention (not new danger — important context this audit surfaced)

Two things worth reading before the rest of this document, both verified by
directly running the scripts in this worktree (not just read):

1. **`scripts/check_isolation_keepout.py` — a real, CI-wired, currently-RED
   gate — is the honest counterpart to the vacuous `IsolationCheck` this
   audit descends from.** Running it (`uv run --with-editable
   packages/temper-placer python scripts/check_isolation_keepout.py`)
   against the real board **fails with exit code 3**: `pcb/temper.kicad_pcb`
   has zero keepout zones, so the required
   `MAINS_SELV_ISOLATION_BARRIER` region (≥8.0mm, all 4 copper layers,
   bisecting HV from SELV) does not physically exist. This is confirmed true
   on `main` too (`git show main:pcb/temper.kicad_pcb | grep -c
   MAINS_SELV_ISOLATION_BARRIER` → `0`), and the gate is wired into
   `.github/workflows/python-tests.yml:1414` with an explicit comment:
   *"Never `continue-on-error`: a gate that cannot run, or that finds the
   barrier missing, must exit non-zero."* This is **not a new finding** — the
   commit that added it (`ee3da42a`, "select PD2 protected-compartment
   architecture") and `docs/evidence/2026-07-28-isolation-keepout.md`
   document it deliberately: the team chose to "keep the missing board
   barrier explicit rather than claiming fabrication closure." Reported here
   because it is the single most relevant fact for anyone reasoning about the
   vacuous `IsolationCheck` Rust rule below: the *real* enforcement for this
   exact physical property exists, is well-built, and is currently failing
   loudly and correctly. Fixing `IsolationCheck` does not close this gap;
   only placing the physical keepout does.
2. **`scripts/check_creepage_clearance_drift.py` is a real, sophisticated,
   currently-failing gate that is wired into no CI workflow at all** —
   confirmed by `grep -rl check_creepage_clearance_drift .github/workflows/`
   (no matches) and by running it directly: exit code 3, "4 family/families
   with mismatched values," including that `scripts/generate_kicad_dru.py`
   (this project's real, evidenced clearance/creepage CI gate — see below)
   hardcodes the PD2 figure `HV_CREEPAGE_ENFORCED_MM = 8.0mm` while a PD3
   value `HV_CREEPAGE_PD3_MM = 12.6mm` sits declared-but-unused in the same
   file (`generate_kicad_dru.py:77-78`). This script is not vacuous — it is
   the opposite failure mode this audit is also watching for: a correctly-
   built check nobody ever calls. It has its own test file
   (`scripts/tests/test_check_creepage_clearance_drift.py`, which *is*
   CI-wired) but the gate script itself is orphaned. Recommend someone wire
   `uv run python scripts/check_creepage_clearance_drift.py` into
   `python-tests.yml` alongside the other `check_*.py` gates.

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

## Per-rule findings: HV/isolation-adjacent `routing/` rules

A systemic pattern recurs across every real-board DRC-invocation path traced
so far (`drc_ratchet.py::_run_rust_drc`, `drc_oracle.py`): both hardcode
`"voltage_v": None`, `"creepage_mm": None`, `"safety_category": None` for
every net class, and both hardcode `"zones": []` (this is `board.zones: Vec<CopperZone>`
— real copper-pour polygons — a *different* field from `constraints.zones:
Vec<ZoneDefinition>`, the placement-region list `IsolationCheck`/`IsolationSlotCheck`
read). `board_py_bridge.rs:316` extracts `voltage_v` with `extract_f64(dict,
"voltage_v", 0.0)`, so a `None` collapses to `0.0`. This one pattern
independently kills several more rules below.

| Rule | Claims | Actually checks | Structurally capable? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `IsolationBarrierCheck` (`routing/isolation_barrier.rs`) | No copper (trace or zone/pour) crosses a defined isolation barrier line | For each `constraints.isolation_barriers` entry, builds a vertical `geo::Line` and tests **real** intersection against every `board.traces` segment (`geo::Intersects`) and every `board.zones[i].polygon` (real `Polygon<f64>`, not a bounding box) — `isolation_barrier.rs:35,79`. This is the one rule in the whole registry that genuinely inspects pour/zone **polygon** geometry, contra the "no rule inspects zone/pour polygons" framing in the audit brief — the capability exists in code, it's just never fed real data (next column). | **Yes, structurally** (real line/polygon intersection, `geo` crate). | **0.** `temper_constraints.yaml` has no `isolation_barriers` key at all (confirmed by enumerating its top-level keys — see registry section above) → `constraints.isolation_barriers` deserializes to its `#[serde(default)]` empty `Vec` → `isolation_barrier.rs:137` returns `[]` immediately, before even reaching the trace/zone checks. Independently, `board.zones` (`CopperZone` polygons) is `[]` in every board-dict-building call site found (`drc_ratchet.py:374`, `drc_oracle.py:466`), so `check_zone_barrier_intersections` specifically could not fire even if a barrier existed. | **Not demonstrated.** Two independent zero-inputs (no barrier config, no pour geometry) block it; the trace-intersection half could in principle be exercised with a synthetic `constraints.isolation_barriers` entry plus `board.traces`, since traces ARE populated on the real board dict — not attempted this session. |
| `IsolationSlotCheck` (`routing/isolation_slot.rs`) | Isolation slot cut in copper (name contains "slot"/"isolation") is ≥ 2mm wide | Filters `constraints.zones` by 2 keywords (`slot`, `isolation`) in the zone **name** — same `constraints::ZoneDefinition{name, net_classes}` type as `IsolationCheck`, i.e. also has no bounds field, though this rule doesn't need one: for a name match it looks up a same-named `board.zones` `CopperZone` and measures the **real** polygon's bounding-box min dimension (`isolation_slot.rs:36-66,128-130`). | **Yes for the geometry step** (real polygon bbox math), **no for the zone-selection step** — a `ZoneDefinition` with no matching name is invisible regardless of what copper actually exists at that location; there's no fallback to "any copper narrower than 2mm near an HV/LV boundary." | **0.** Same 4 real zones (`power_zone`, `driver_zone`, `control_zone`, `interface_zone`) — none contain "slot" or "isolation" → `slot_zones.is_empty()` at `isolation_slot.rs:122` → `[]` immediately. Even hypothetically renaming a zone to match, `board.zones` is `[]` in every traced invocation, so `matching_copper_polygon` would return `None` and the rule would only ever emit the low-severity `SAF_SLT_001` "no copper zone polygon found" advisory (Info, not a real geometry check) rather than actually measuring width. | **No** — dead by the same `constraints.zones`-naming root cause as `IsolationCheck`, on top of the `board.zones` starvation shared with `IsolationBarrierCheck`. |
| `PartialDischargeCheck` (`routing/partial_discharge.rs`) | Inner-layer (`In1.Cu`/`In2.Cu`) HV traces need 1.5× outer-layer clearance to nearby copper | Filters `board.net_class_rules` by `rules.voltage_v >= 60.0`, collects nets in matching classes, then for each HV trace segment on an inner layer, computes **real** `geo::EuclideanDistance` to every other trace segment and compares to `base_clearance * 1.5` (`partial_discharge.rs:33-59,86-87`). Real, non-trivial geometry and a real per-class clearance lookup. | **Yes, structurally.** | The real board (`pcb/temper.kicad_pcb`) genuinely has `In1.Cu`/`In2.Cu` inner layers (confirmed: `grep -c "In1.Cu\|In2.Cu"` on the layer table = 2, 4-layer stackup), so this rule's degenerate case is not "board has no inner layers." But `voltage_v` is one of the fields hardcoded to `None`→`0.0` in both real-board-invocation paths found (`drc_ratchet.py:352`, `drc_oracle.py:337,410`); `0.0 >= 60.0` is always false, so `hv_class_names` is always empty through those paths → **0** HV inner traces examined, regardless of how many actually exist on the board. | **Not demonstrated through the traced real-board paths** (structurally would fail given a properly-populated `voltage_v`, e.g. `HighVoltage`'s real `340.0` from `netclass_rules.yaml` — not attempted directly against `run_drc()` with a hand-built dict this session, flagged as a cheap follow-up). |

Net effect for this group: one rule (`IsolationBarrierCheck`) is the strongest
counter-evidence in the codebase to "nothing inspects real pour polygons" —
the capability is real and well-written — but it is unreachable through every
invocation path this audit could find, for two independent reasons (empty
constraint list, empty zone-geometry input). `IsolationSlotCheck` repeats
`IsolationCheck`'s exact zone-naming defect. `PartialDischargeCheck` is
geometrically sound but is starved by the same `voltage_v: None` pattern that
starves the SSOT-declared branch of `HVLVSeparationCheck`.

## Per-rule finding: `emc/loop_area.rs` (high consequence for this board — gate-drive/commutation loop area on a 340V half-bridge)

| Rule | Claims | Actually checks | Structurally capable? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `LoopAreaCheck` (`emc/loop_area.rs`) | Bounding-box area of components on a critical current loop's nets must not exceed `max_area_mm2` (radiated-emission control) | For each `constraints.critical_loops` entry, collects components touching `loop_constraint.nets` (`loop_area.rs:26-32`), computes a **real** bbox area over component centers, compares to `max_area_mm2` (`loop_area.rs:68-107`). | **Yes, structurally**, and **proven** — `loop_area.rs` ships 4 in-crate unit tests (`loop_area_empty_board_no_violations`, `loop_area_under_threshold_no_violations`, `loop_area_over_threshold_violation`, `loop_area_no_max_no_violations`) exercising empty/under/over/unbounded cases; `loop_area_over_threshold_violation` constructs two components 50×10mm apart against a 200mm² max and asserts exactly 1 `EMC_LPA_001` `Warning` violation is produced (`loop_area.rs:212-244`). This is the **strongest non-vacuous rule found in this audit** by internal test evidence. | **0 on the real config, for a schema-mismatch reason distinct from every other finding above.** `temper_constraints.yaml`'s `critical_loops:` section has 4 real, named, safety-relevant entries — `high_side_gate_loop`, `low_side_gate_loop`, `power_stage_commutation` ("most critical"), `bootstrap` — but **every entry is defined by `pins: [[ref, pin], ...]`, never by `nets:`.** The Rust-facing schema, `temper_placer._constraint_types.topology.CriticalLoop` (`packages/temper-placer/src/temper_placer/_constraint_types/topology.py:6-19`), has both fields, with `nets: list[str] = Field(default_factory=list)` — so every one of the 4 real loops parses with `nets = []`. `drc_runner.py`'s conversion to the Rust-bound dict (`drc_runner.py:162-171`) forwards `"nets": l.nets` verbatim — i.e. `[]` — with **no pins→nets bridging step**. (`packages/temper-placer/src/temper_placer/core/loop_extractor.py` looks like it could be that bridge from its docstring, but it is a *separate, heuristic auto-extraction* system producing `auto_`-prefixed loops for placement scoring, not a converter feeding these 4 manually-authored YAML loops into `LoopAreaCheck`.) Verified: `python3 -c "import yaml; d=yaml.safe_load(open('packages/temper-placer/configs/temper_constraints.yaml')); print([l.get('nets') for l in d['critical_loops']])"` → `[None, None, None, None]`. `components_on_nets(board, &[])` returns an empty set, `involved_refs.len() < 2` short-circuits every one of the 4 loops before the area math ever runs (`loop_area.rs:74-75`) — even independent of the separately-confirmed `critical_loops: []` hardcoding in `drc_ratchet.py`/`drc_oracle.py`. | **Yes, on synthetic fixtures** (see the 4 unit tests above) — this is the one rule in the audit with in-repo proof it fires correctly. **No, on the real config** — none of the 4 real, named gate-drive/commutation/bootstrap loops for this 340V half-bridge can ever produce a violation as currently authored, because they use a key (`pins`) the Rust rule's schema doesn't read (`nets`), not because of a code defect in the rule itself. |

This is a third, independent species of vacuity beyond "geometry field missing" (`IsolationCheck`) and "collection always fed empty by the caller" (`IsolationBarrierCheck`, `PartialDischargeCheck`): **a real, populated config section written in a schema variant (`pins`) the consuming rule's field (`nets`) never reads**, silently degrading to the empty-list case with no error, warning, or type mismatch anywhere in the chain.

## Per-rule findings: general `drc/` geometry rules

Good news first: these are the healthiest rules in the registry. Unlike
`safety/` and the isolation-adjacent `routing/` rules, five of six read only
`board.components` / `board.traces` / `board.vias` — fields that ARE
populated (non-empty) in every real-board dict-building path traced in this
audit (`drc_ratchet.py`, `drc_oracle.py`), because those paths do forward
real component/trace/via data even while zeroing out zones/loops/isolation
config.

| Rule | Claims | Actually checks | Structurally capable? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `ClearanceCheck` (`drc/clearance.rs`) | Component-to-component clearance vs. net-class rules | Real `edge_distance_to()` (polygon/bbox) over every `board.all_components()` pair; threshold via `clearance_between()` (real per-class `clearance_mm` / explicit pair rules) — `clearance.rs:57-115`, `mod.rs:291-315`. | **Yes.** | Real board: 169 footprints → up to ~14,196 pairs; `temper_constraints.yaml` has 0 explicit `clearances` pair-rules but all 8 net classes have `clearance_mm`. | **Yes — empirically confirmed this session.** `clearance.rs` ships `#[test] clearance_at_exact_threshold_flagged`; `cargo test clearance_at_exact_threshold_flagged --manifest-path packages/temper-drc-rs/Cargo.toml` → **1 passed**. |
| `TraceClearanceCheck` (`drc/trace_clearance.rs`) | Trace-to-trace clearance, same layer | Real `EuclideanDistance` between same-layer trace-segment pairs vs. `clearance_between()` — `trace_clearance.rs:49-94`. | **Yes.** | Real board: 2290 trace segments (`grep -c "(segment " pcb/temper.kicad_pcb`); reads only `board.traces`/`board.nets`. | Not run directly this session; no structural blindness or zeroed-input dependency found. |
| `ViaSpacingCheck` (`drc/via_spacing.rs`) | Via-to-via spacing vs. pad diameter | Real center-distance minus half-pad-sum over every via pair — `via_spacing.rs:44-87` (`constraints` param unused). | **Yes.** | Real board: 48 vias → 1128 pairs; reads only `board.vias`. | Not run directly; structurally sound. |
| `CourtyardCheck::new(0.05)` (`drc/courtyard.rs`) | Courtyard-margin overlap, same layer | Real bbox-expand-and-intersect (`geo::Intersects`) — `courtyard.rs:34-72`; margin hardcoded `0.05` at registration (`mod.rs:234`), not read from `temper_constraints.yaml` (minor config-fidelity gap, not a vacuity). | **Yes.** | 169 real components. | Not run directly; geometrically capable. |
| `ComponentOverlapCheck` (`drc/component_overlap.rs`) | Overlapping same-layer components | Real `a.overlaps(b)` (polygon/bbox) — `component_overlap.rs:32-66`. | **Yes.** | 169 real components. | Not run directly; structurally sound. |
| `ZoneContainmentCheck` (`drc/zone_containment.rs`) | "Components are inside their designated zones" | Two-part: (1) `constraints.zones` (name+`net_classes` only — **not** the bounds-carrying type) indexes which net classes require containment (`zone_containment.rs:44-53`); (2) real point-in-polygon test (`geo::Contains`) against **`board.zones`** (`CopperZone.polygon` — real copper-pour geometry, a *different* "zone" from the `constraints::ZoneDefinition` that `IsolationCheck` reads) — `zone_containment.rs:61-92`. This is the **second** rule in the registry (after `IsolationBarrierCheck`) that genuinely inspects real pour polygons, reinforcing that "no rule inspects zone/pour polygons" is not quite right as a blanket claim — the capability exists in three places; the data just never arrives. | **Yes, geometrically.** | Only `interface_zone` in `temper_constraints.yaml` declares `net_classes` (`['ACMains']`) — the other 3 zones require nothing, so only ACMains-classed components are ever in scope. The real board has 96 KiCad zones on disk (`grep -c "(zone " pcb/temper.kicad_pcb`), but — as established above — `board.zones` is hardcoded to `[]` in every real-board-invocation path traced (`drc_ratchet.py:374`, `drc_oracle.py:466`), so through those paths this rule examines **0** of the 96 real pour polygons. | **Inverted failure mode — the opposite of vacuity.** With `board.zones == []`, `.any()` over an empty iterator is unconditionally `false`, so `is_inside_any_zone` is `false` for *every* ACMains-classed component regardless of true position (`zone_containment.rs:79-92,94`). Rather than silently passing, this rule would **always fire `DRC_ZON_001` for every in-scope component** — a guaranteed false-positive generator through the traced invocation paths, not a silent pass-through. Not run against the real board this session, but the logic at those line numbers is unambiguous. Worth flagging separately from every other finding in this document: some of these rules don't fail open (silent pass), they fail *noisy* (permanent false alarm), which is a different but related trust problem — alert fatigue that teaches reviewers to ignore the category. |

## Coverage — what has and has not been audited yet

Audited in depth: `safety/isolation.rs`, `safety/creepage.rs` (partial —
structural analysis done, real-config item count still TODO),
`safety/hv_lv_separation.rs` (partial — same), the CI-gating chain
(`ci_check_drc.py`, `drc_ratchet.py`, `drc_runner.py`, `generate_kicad_dru.py`,
`constraints.rs` deserialization boundary).

**Not yet audited (TODO, to be completed and committed incrementally):**
- `routing/`: `copper_pullback.rs`, `split_plane_crossing.rs`,
  `pad_entry_width.rs`, `parallel_run.rs`, `stitching_via_density.rs`,
  `power_pad_teardrop.rs`, `tht_thermal_relief.rs`
  (`isolation_barrier.rs`, `isolation_slot.rs`, `partial_discharge.rs` now
  covered above)
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
