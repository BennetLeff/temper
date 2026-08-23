<!-- provenance: commit=e4107ab0fd1432dc05a8f7f49621fbf401025fb4 dirty=UNKNOWN -->
# DRC / Safety-Check Vacuity Audit (2026-08-08)

**Status: complete for the scope this session reached.** Every `safety/`
rule, every `drc/` rule, every `erc/` and `emc/` and `placement/` rule, the
three isolation/HV-adjacent `routing/` rules, `req_safe_01.rs`, the
highest-priority Python validators, and five isolation/creepage/HV-adjacent
`scripts/check_*.py` gates were audited with real-config item counts and,
where possible, a demonstrated pass/fail test. Roughly a dozen lower-priority
`routing/` rules and ~40 non-safety-adjacent `check_*.py` scripts were not
reached — see the "Coverage" section at the bottom for the explicit list, per
this audit's instruction to say plainly what wasn't covered.

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

## Per-rule findings: remaining `emc/`, `erc/`, `placement/` rules

| Rule | Claims | Actually checks | Structurally capable? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `NoiseCouplingCheck` (`emc/noise_coupling.rs`) | Aggressor (noisy) vs. victim (sensitive) component clearance | Real `edge_distance_to()` vs. real `clearance_between()` for pairs where one side is "noisy" and the other "sensitive" by 5+4 net-class-name keyword lists (`noise_coupling.rs:16-31,82-95`). | **Yes, structurally**, and **proven** — 5 in-repo unit tests including an exact-threshold case. | **0.** Of the real board's 8 net classes, exactly 1 (`Power`) matches a noisy keyword; **0 match any of the 4 sensitive keywords** (`analog/sensor/small_signal/victim`) — verified by direct substring test in `python3`. `is_noise_case` requires one noisy AND one sensitive component; with 0 sensitive-matching classes, it is always `false`. | **Yes on synthetic fixtures, no on the real config** — cannot fire for any real component pair, because the "victim" side of the classifier has no real net class it can ever match. |
| `GroundPlaneCheck` (`emc/ground_plane.rs`) | Noisy (di/dt) components must sit over a ground/return zone | Filters `constraints.zones` by 3 keywords (`gnd/ground/return`) in the zone **name**; for each noisy-classed component, requires a matching-named zone whose `net_classes` also lists the component's class (`ground_plane.rs:58-77`) — pure string matching, no geometry (doesn't even use `comp.center`). | **No** — same missing-geometry pattern as `IsolationCheck`, plus **no early return** when 0 zones match (unlike `IsolationCheck`, which does bail at 0 matching zones). | Real board's 4 zones (`power_zone`, `driver_zone`, `control_zone`, `interface_zone`) — **none** contain `gnd`/`ground`/`return` → `gnd_zone_names` is empty. | **Inverted failure mode, same as `ZoneContainmentCheck`.** Because there is no early return, every real component on the one noisy-matching class (`Power`) is **unconditionally flagged** `EMC_GND_001` — a guaranteed false positive for every `Power`-classed part on the board, not a silent pass. |
| `ThermalViaCountCheck` (`placement/thermal_via_count.rs`) | Power-dissipating components need `ceil(0.7 × watts)` thermal vias under their footprint | Real bbox-overlap counting of `board.vias` under `board.electrical_components` where `power_dissipation_w > 0` (`thermal_via_count.rs:46-74`); `constraints` param unused. Ships 5 passing unit tests. | **Yes, structurally, and proven on synthetic fixtures.** | **0, for two independent reasons through the traced real-board paths.** (1) The rule's own degenerate case bails immediately `if board.vias.is_empty()` (`thermal_via_count.rs:42-44`) — and `"vias"` is never a key in either `drc_ratchet.py`'s or `drc_oracle.py`'s board-dict construction, so `board.vias` is always `[]` there. (2) Independently, `"power_dissipation_w": None` is hardcoded per component in both of those same builders (`drc_ratchet.py:330`, `drc_oracle.py:311,387`) — so even with vias present, no component would ever have `Some(p) if p > 0.0`. Either defect alone is sufficient to kill this rule; both are present. | **Not demonstrated on the real board.** For a 340V/40A induction-cooker power stage (IGBTs, bus caps — this project's own `HighCurrent` net-class description), thermal-via adequacy is a real safety property; this rule cannot currently verify it through any traced invocation path. |
| `WaveSolderKeepoutCheck` (`placement/wave_solder_keepout.rs`) | Bottom-side SMD parts must be ≥5mm from THT pads (wave-solder DFM) | Real bbox-expand distance check over `board.all_components()` filtered by `side`/`package_type` (`wave_solder_keepout.rs:37-75`). | **Yes** — reads only `board.components`, populated in the traced real-board paths. | Not counted this session (DFM category, lower safety consequence — deprioritized per the audit's own ranking instruction). | Not attempted; no structural blindness found. |
| `FloatingPinsCheck` (`erc/floating_pins.rs`) | Every electrical component must belong to ≥1 net | Real set-membership check: `board.nets` vs. `board.electrical_components` (`floating_pins.rs:41-50`). Ships 5 passing unit tests covering the empty/connected/floating/mixed cases. | **Yes.** | Reads only `board.nets`/`board.electrical_components`, populated in the traced real-board paths; count not obtained this session but no zeroed-dependency found. | Proven on synthetic fixtures (`floating_pins_unconnected_component_violation`, `floating_pins_mixed_connected_and_floating`); not run against the real board this session. |
| **`PowerDomainCheck`** (`erc/power_domain.rs`) | "Placeholder — U4" (its own `description()` says exactly this) | **Nothing.** `fn check(&self, _board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> { vec![] }` — literally, unconditionally, with both parameters explicitly unused (`power_domain.rs:24-26`). | **No — not "cannot detect its target" but "has no target at all."** This is not a bug in a check; it is an unimplemented stub still live in `create_default_registry()` (`mod.rs:239`), indistinguishable from a real rule to any caller. | **N/A — 0 by construction, for any input whatsoever, including a maximally adversarial one.** | **No — cannot fail. Not "vacuous on this config," but structurally, permanently incapable of ever producing a violation for any board or constraint set that will ever exist.** This is the most extreme finding in the entire audit. |
| **`NetConnectivityCheck`** (`erc/net_connectivity.rs`) | "Verify each net has at least two connected (non-mechanical) components" (real, specific docstring — reads as a finished rule) | Computes real per-net connection counts into `_filtered_connection_counts` (`net_connectivity.rs:35-42`) — note the leading underscore, which suppresses Rust's unused-variable lint — **then discards it and returns `vec![]` unconditionally** (`net_connectivity.rs:47`), with an in-code `TODO(temper-xxx)` admitting it. | **No — same category as `PowerDomainCheck`, but more deceptive**: it *looks* like a working check (real computation happens, real docstring, real requirement stated), while the result is thrown away deliberately. | **0 by construction.** | **No — cannot fail**, for the same reason as `PowerDomainCheck`. Also registered in `create_default_registry()` (`mod.rs:238`). |
| — (cross-cutting, no rule involved) | — | **No rule in the entire 27-rule registry reads `constraints.thermal_constraints` at all** — confirmed by `grep -rl thermal_constraints packages/temper-drc-rs/src/rules/` returning no matches. | N/A | `temper_constraints.yaml`'s `thermal:` section has 2 real, safety-relevant entries (`Q1`/`Q2` IGBTs must be near the top edge for thermal interface; LDOs/Buck must be ≥15mm apart to avoid logic hot spots) and is correctly forwarded end-to-end by `drc_runner.py`'s `_constraints_to_dict` — **the data is real and plumbed, there is simply no consumer.** | N/A — there is no rule to fail. Worth flagging given the task's own priority ranking calls out "thermal limits" explicitly, and this project is a mains-connected induction cooker with a 340V IGBT half-bridge. |

**`PowerDomainCheck` and `NetConnectivityCheck` are the single most severe findings in this audit** — more severe than `IsolationCheck`, because they require no adversarial config, no keyword-matching gap, no board topology quirk: they are unconditional `vec![]` returns, permanently, by construction, shipped as two of the registry's "15 migrated checks" / "27 rules" (`mod.rs`'s own header comment says "15 migrated checks (U4)" while `create_default_registry()` registers 27 — these two stubs are part of that gap between the documented count and the delivered count). Anyone trusting `erc_power_domain` or `erc_net_connectivity` in a violation report, dashboard, or "0 ERC violations" summary is trusting two checks that cannot ever contribute a non-zero number.

## Per-rule findings: `req_safe_01.rs` and Python validators

| Item | Claims | Actually checks | Structurally capable? | Items examined on real config | Wired into CI? | Demonstrated failable? |
|---|---|---|---|---|---|---|
| `req_safe_01.rs` (REQ-SAFE-01, `packages/temper-drc-rs/src/req_safe_01.rs`) | IEC 60335 domain clearance/creepage compliance (ports `verify_iec60335_compliance` from the Python `requirements/validators/{clearance,_copper}.py`) | Builds a `CopperModel` from real per-pad geometry (`Pad{cx, cy, width, height, shape, rotation_rad, net}`) and computes real pad-to-pad reach/clearance/creepage via `temper_geometry` primitives. Grepped the whole file for `zone`/`pour`/`polygon`/`Zone` (both cases) — **zero matches**: confirmed component/pad-geometry only, exactly as the audit brief that spawned this document states; it cannot see copper pours or zone fills at all. | **Yes, for pad-level geometry** — real position/rotation/shape and real distance computation; **no, for anything zone/pour-related** — that's out of scope by design, not a bug. | 169 real footprints on `pcb/temper.kicad_pcb`; count of pad-pairs examined not independently re-run this session, but exercised via its own real-board-fixture test suite. | **Yes** — `tests/requirements/safety/` (`test_clearance.py`, `test_clearance_copper.py`, `test_runb_audit_lie.py`) runs in `.github/workflows/python-tests.yml:1121`. | **Yes, decisively — the strongest non-vacuous, CI-wired safety check found in this entire audit.** `test_runb_audit_lie.py` documents a real historical incident (issue #523 gap 2): a placer candidate ("run-B") passed the solver's own weaker center-to-center audit (0 violations) but this validator found 3→12 real violations on the identical placement, including a pad pair at 0.320mm copper-to-copper spacing that a center-distance check structurally cannot see. Worth naming as a positive counter-example and a template for what a real fix of the Rust `safety/` rules should look like. |
| `rtd_safety.py` | PT100/MAX31865 electrical fault-window model (short/open thresholds, VBIAS limits) | Out of category — a deterministic electrical-parameter reference model for firmware/schematic review, not a PCB-layout geometry check; doesn't read `pcb/temper.kicad_pcb` or `temper_constraints.yaml` at all. | N/A | N/A | Not checked (out of this audit's geometry-vacuity scope) | Flagged only so its absence from the geometry findings isn't mistaken for an oversight — it is a different artifact class and would need a separate electrical-parameter audit. |
| `tht_check.py` (`validate_hole_clearance`) | THT hole-to-hole collision detection | Computes each pad's absolute position as `pos[i] + pad.position`, **explicitly ignoring component rotation** — `tht_check.py:52-53`: `# Calculate absolute position (assuming 0 rotation for now) # TODO: Support rotation`. | **No, for the majority of the real board.** `pcb/temper.kicad_pcb` has 802 three-parameter `(at x y rot)` placements, of which 665 carry non-zero rotation (grep-verified by the researching fork). Any rotated component's holes are checked at the wrong position — both false negatives and false positives are possible. | **0 — this function has no caller anywhere in `packages/temper-placer/src`** (repo-wide grep for `validate_hole_clearance`/`tht_check` outside its own file finds only 3 test files: an oracle pin and two differential/PBT tests). | No — absent from every `.github/workflows/*.yml`. | **Not demonstrable in a live path — it is dead code with a real geometry bug baked in, matching this audit's target double-defect pattern exactly** (structurally blind for rotated components, and never called in production). |
| `geometric.py` | Placement-time overlap/board-boundary/HV-LV/zone/keepout validation | Delegates real compute to `temper_drc_rs.geometric_validate` (Rust kernel) fed by real rotated-AABB and pairwise-distance kernels; its zone representation is `Placement.zones: dict[str, tuple(x0,y0,x1,y1)]` — a **real rectangular-bounds** type, distinct from and not sharing `constraints::ZoneDefinition`'s missing-`bounds` defect. | Likely yes, structurally — not independently verified against the real config this session (flagged gap). | Not verified this session. | Not checked. | Not attempted — flagged as a follow-up; it appears structurally sounder than the Rust `safety/` rules and may be worth pointing a future fix at as a template, alongside REQ-SAFE-01. |
| `drc_fence.py` | Per-stage DRC orchestration wrapping `CheckRunner` | Pure orchestration — no independent geometry logic; correctness is entirely a function of its `Placement`/`ConstraintSet` inputs, which (via `drc_runner.py`'s `_constraints_to_dict`) are the one conversion path in this audit that forwards zone bounds correctly. | N/A (orchestration layer) | Depends on caller. | Not checked directly. | N/A in isolation. |
| `preflight.py` | Pre-optimization sanity checks (tool availability, zone assignment/fit, impossible-constraint detection) | Real Rust kernel for zone-AABB-overlap/bounds checks, but scoped to **before placement exists** — a setup guard, not a post-placement safety gate. | Yes, for its narrower stated purpose. | Not verified this session. | Not checked. | Out of category — not miscounted as a failed safety check, just a different kind of check. |
| `router_v6/constraints_drc_oracle.py`'s `DRCOracle` (**correction to an earlier over-read**) | A self-contained, real-time, spatial-index (cKDTree) DRC oracle used by the router and the deterministic placement pipeline (`deterministic/state.py` imports **this** `DRCOracle`, not `validation/drc_oracle.py`'s same-named class) | Independently verified: `deterministic/stages/{drc_validation,connectivity_validation,drc_sweep}.py` all call `state.drc_oracle.validate_all()`/`.geometry`, and `deterministic/stages/setup.py:115` constructs it (`DRCOracle(rules=matrix)`) from real parsed KiCad pad positions and a real `ClearanceMatrix`. It does **not** call `temper_drc_rs.run_drc()` and does **not** share the `None`/`[]`-hardcoding pattern found in `drc_ratchet.py`/`validation/drc_oracle.py` — those are a *different* class of the same name in a different module. | Not fully audited — out of this session's file list — but the earlier working hypothesis (passed up from a research fork) that this live pipeline routes through the vacuous board-dict builders in `packages/temper-placer/src/temper_placer/validation/drc_oracle.py` is **incorrect and is retracted here**; `validation/drc_oracle.py`'s `DRCOracle` class has no `validate_all()` method at all. | Not counted this session. | Live in the deterministic pipeline, not a CI script per se. | Not attempted — flagged as a genuine, higher-value follow-up than the retracted claim: this router-side oracle (with its own `INTERNAL_LAYER_CREEPAGE_FACTOR` creepage-reduction model, `constraints_drc_oracle.py:69`) is a completely separate implementation of HV/creepage-adjacent logic that this audit did not have time to fully vet, and deserves its own pass. |

Correction note: a research fork initially reported that `validation/drc_oracle.py`'s `None`-hardcoded board-dict builders might be reachable from the live deterministic placement pipeline via `state.drc_oracle.validate_all()`, which would have escalated the top-line CI-gating finding substantially (vacuity reaching live placement validation, not just an unused diagnostic backend). Tracing the actual import (`deterministic/state.py:16`: `from temper_placer.router_v6.constraints_drc_oracle import DRCOracle, Violation`) shows `state.drc_oracle` is a different, self-contained `DRCOracle` class in a different file that does not go through `temper_drc_rs.run_drc()` at all. That escalation does **not** hold up and is retracted; documented here rather than silently dropped, per this audit's own standard of showing work.

## Per-rule findings: `scripts/check_*.py` isolation/creepage-adjacent gates

These five scripts turned out to be the **healthiest part of this entire
audit** — real geometry or real AST analysis, CI-wired, and (mostly)
currently passing because they're catching real things. `check_isolation_keepout.py`
and `check_creepage_clearance_drift.py` are covered in the flagged section at
the top of this document; summarized again here for table completeness.

| Script | Claims | Actually checks | Wired into CI? | Items examined on real config | Demonstrated failable? |
|---|---|---|---|---|---|
| `check_isolation_keepout.py` | Physical mains↔SELV keepout barrier exists, spans all 4 copper layers, ≥8.0mm wide, bisects HV/SELV, no copper intrudes | Real geometry — parses `pcb/temper.kicad_pcb` directly: 169 footprints, 527 pads (103 HV / 421 SELV split — sums to more than 527 because of shared/ambiguous pads per its own accounting), 2434 copper items (segments+arcs+vias+non-keepout zones). | **Yes** — `python-tests.yml:1414`, never `continue-on-error` (explicit comment says so). | 169 footprints, 527 pads, 2434 copper items, 0 keepout zones found on the real board. | **Yes — currently failing, exit 3, verified by running it this session.** See the flagged section above. |
| `check_hv_netclass_coverage.py` | Every manifest-declared HV net has a net class; every net class emits a real DRC rule | Cross-references `elec/domain_manifest.yaml`'s HV domain against `TEMPER_NET_ASSIGNMENTS` and `generate_kicad_dru.py`'s generated output — real coverage logic, not presence-of-key. | Yes — `python-tests.yml:1278` (+ unit tests at 1265). | 21 HV-domain nets, 11 net classes. | Not currently failing, but its own docstring cites a real, previously-confirmed defect it exists to catch (`+170V_BUS` silently resolving to no net class, confirmed on `origin/main` 2026-07-29) — demonstrated historically, currently green. |
| `check_creepage_clearance_drift.py` | Cross-check every creepage/clearance figure declared across `.ato`/Python/YAML for drift | AST/line-level discovery scan (not a hand-maintained file list) across `elec/`, `scripts/`, `packages/`, `configs/`. | **No** — see flagged section above; confirmed absent from every workflow. | Dozens of real declaration sites (32 contributing files, 125 declarations, 6 comparable families). | **Yes — currently failing, exit 3, verified by running it this session** (4 mismatched families). |
| `check_net_classification.py` | Catch HV/SELV substring-classification bugs (false positives AND negatives) in Python net-classification code | AST scan for substring/`in`-based net-name classification, scoped to `packages/temper-placer/src/temper_placer/**/*.py` and `elec/validation/**/*.py` — **Python-only; cannot see `.rs` files at all.** | Yes — `python-tests.yml:1666` (+ tests at 1654). | Full AST walk of those globs; some `UNRESOLVED` call sites reported informationally. | Currently passing, but its own docstring documents 5 confirmed historical instances of exactly this bug shape, all previously fixed in Python. **Directly relevant cross-reference**: this project has fixed this precise keyword/substring-classification bug class multiple times in Python, but this scanner structurally cannot see the same bug shape living today in `packages/temper-drc-rs/src/rules/safety/{isolation,creepage,hv_lv_separation}.rs` or `routing/partial_discharge.rs` — different language, entirely outside this scanner's glob. |
| `check_pad_orientation.py` | Catch footprint rotations where pad angle wasn't co-rotated, causing intra-footprint copper shorts | Pure geometric analysis of the board's own bytes (pad `(at x y angle)` vs. footprint angle, overlap test) — no external lookup. | Yes — `python-tests.yml:1387` (+ tests at 1372). | 169 footprints, 527 pads, 1713 different-net pad pairs. | Currently passing; docstring cites a previously-measured real failure on this exact board (55/60 shorting items traced to this bug class before the fix) — real and evidenced, not vacuous. |

Net assessment for this group: 4 of 5 scripts are real, CI-wired, and doing
genuine work (2 passing, 1 — `check_isolation_keepout.py` — currently and
correctly red). The exception, `check_creepage_clearance_drift.py`, is a
correctly-built check that nobody calls, the mirror-image failure mode from
most of the rest of this document.

## Ranked list — vacuous or blind rules, by safety consequence

Highest consequence first. "Cannot fail" means: no input this audit could
construct, real or synthetic, makes the rule produce a violation through any
traced real-board invocation path (some are also structurally incapable even
on a hand-built fixture; noted per row).

1. **`IsolationCheck`** (`safety/isolation.rs`) — geometry-blind by
   construction (`constraints::ZoneDefinition` has no `bounds`/polygon
   field) *and* dead on the real config (0 of 4 zones match its keyword
   list). The seed finding this audit descends from; another agent is
   already repairing it.
2. **`PowerDomainCheck`** (`erc/power_domain.rs`) and **`NetConnectivityCheck`**
   (`erc/net_connectivity.rs`) — undisguised `vec![]` stubs, unconditionally,
   for any input. More extreme than #1 (no config or keyword dependency at
   all) but lower real-world consequence today only because ERC
   connectivity/power-domain issues are (partially) caught elsewhere in the
   pipeline (netlist reconciliation, KiCad ERC). Still shipped
   indistinguishably from real checks in the default registry.
3. **No rule consumes `constraints.thermal_constraints`** — 2 real,
   populated, correctly-plumbed thermal entries for this board's IGBT
   half-bridge (edge placement, LDO/Buck spread) have zero consumers among
   27 registered rules. `ThermalViaCountCheck` sounds related but checks an
   unrelated property (via count) and is independently dead via the
   `power_dissipation_w: None` / `vias: []` pattern below.
4. **`ThermalViaCountCheck`** (`placement/thermal_via_count.rs`) — real
   geometry, proven on synthetic fixtures, but dead through every traced
   real-board path for two independent reasons (`board.vias` never
   populated, `power_dissipation_w` hardcoded `None`) on a board with a
   340V/40A power stage.
5. **`HVLVSeparationCheck`** (`safety/hv_lv_separation.rs`) — real geometry
   and real threshold (the most structurally sound of the three `safety/`
   rules), but its keyword-fallback classifier misses `HighCurrent`
   (340V/40A IGBTs/bus-caps by its own description) entirely, and the
   correctly-declared SSOT `safety_category` values in `netclass_rules.yaml`
   never reach it through the two real-board call sites traced.
6. **`IsolationBarrierCheck`** (`routing/isolation_barrier.rs`) — genuinely
   inspects real trace and pour-polygon geometry (a real counter-example to
   "nothing inspects pours") but `constraints.isolation_barriers` is never
   populated (no such key exists in `temper_constraints.yaml`) and
   `board.zones` is `[]` in every traced path.
7. **`PartialDischargeCheck`** (`routing/partial_discharge.rs`) — real
   inner-layer trace-to-trace geometry on a genuinely 4-layer board, starved
   by the same `voltage_v: None` pattern.
8. **`IsolationSlotCheck`** (`routing/isolation_slot.rs`) and
   **`CreepageCheck`** (`safety/creepage.rs`) — same zone-keyword /
   iso-keyword dead-on-real-config pattern as #1, but structurally capable
   (unlike #1) if the taxonomy changed.
9. **`LoopAreaCheck`** (`emc/loop_area.rs`) — the best-tested rule in the
   registry (4 passing unit tests proving real failability) but dead on the
   real config for a schema mismatch: all 4 real critical-loop entries
   (including the "most critical" main commutation loop on a 340V
   half-bridge) are authored with `pins:`, the rule reads `nets:`.
10. **`NoiseCouplingCheck`** (`emc/noise_coupling.rs`) — real geometry,
    proven on fixtures, dead on real config (0 of 8 net classes match any
    "sensitive" keyword).
11. **`ZoneContainmentCheck`** (`drc/zone_containment.rs`) and
    **`GroundPlaneCheck`** (`emc/ground_plane.rs`) — inverted failure mode:
    with `board.zones == []`, both unconditionally fire for every
    in-scope component regardless of true position, rather than staying
    silent. Noise/alert-fatigue risk rather than blindness, flagged
    separately as a distinct failure class.
12. **`tht_check.py`'s `validate_hole_clearance`** — rotation-blind
    (explicit `# TODO: Support rotation` against a board where 665/802
    placements are rotated) *and* dead code (0 callers in production,
    confirmed by repo-wide grep) — the exact double-defect this audit was
    commissioned to hunt for, just in Python rather than Rust.

**Not vacuous — named because they're the positive counter-examples that
calibrate the rest of this list**: `req_safe_01.rs` (REQ-SAFE-01, CI-wired,
demonstrated failable via a real historical incident in
`test_runb_audit_lie.py`), `ClearanceCheck`/`TraceClearanceCheck`/
`ViaSpacingCheck`/`CourtyardCheck`/`ComponentOverlapCheck` (real geometry,
real thresholds, reading fields that survive every real-board path traced),
`FloatingPinsCheck`, `check_isolation_keepout.py` (currently red for a real
reason), `check_hv_netclass_coverage.py`, and `check_pad_orientation.py`.

## Recommendations

1. **Do not let `PowerDomainCheck`/`NetConnectivityCheck` ship silently as
   "15 migrated checks."** Either implement them or remove them from
   `create_default_registry()` and the "27 rules" / "15 migrated checks"
   counts until they are; a stub indistinguishable from a real check is
   worse than an absent one.
2. **Wire `check_creepage_clearance_drift.py` into `python-tests.yml`** — it
   is real, already has a passing unit-test harness, and is currently
   finding real drift (including in `generate_kicad_dru.py` itself).
3. **Treat the `constraints.thermal_constraints` non-consumption as a gap
   to close, not just document** — this board has a real, populated thermal
   constraint set for its highest-power components with zero enforcement
   anywhere in the 27-rule registry.
4. Whoever fixes `IsolationCheck` should know `check_isolation_keepout.py`
   already owns the *real* enforcement of the same physical property (and is
   currently red for a legitimate, tracked reason) — the Rust rule fix is
   about restoring signal to a diagnostic/CI-diagnostic path, not about
   closing the board's actual isolation gap.
5. **Audit `board_dict`/`constraints_dict` construction as a single, shared
   root cause**, not per-rule. `drc_ratchet.py::_run_rust_drc` and
   `validation/drc_oracle.py`'s two board-dict builders each independently
   hardcode `zones: []`, `isolation_barriers: []`, `critical_loops: []`,
   `thermal_constraints: []` (implicitly, by omission), and
   `safety_category`/`creepage_mm`/`voltage_v`/`power_dissipation_w: None`
   per component/net-class. Fixing these two call sites to forward real data
   (the way `drc_runner.py::_constraints_to_dict` already correctly does)
   would restore a working `constraints.isolation_barriers`,
   `constraints.zones` (with bounds, once `constraints::ZoneDefinition` gets
   one), HV classification, and thermal-via checking in one shared place,
   rather than four+ separate per-rule fixes.
6. **`packages/temper-placer.../core/loop_extractor.py` is not a `pins→nets`
   bridge** — if `LoopAreaCheck` is meant to see the 4 real critical loops in
   `temper_constraints.yaml`, something needs to resolve `pins:` (component,
   pin) tuples to net names before they reach the Rust-bound dict; today
   nothing does.
7. **`router_v6/constraints_drc_oracle.py`'s `DRCOracle`** (the one
   genuinely live in the deterministic placement pipeline) was discovered
   but not audited this session — it has its own creepage-adjacent modeling
   (`INTERNAL_LAYER_CREEPAGE_FACTOR`) independent of everything else in this
   document and deserves a dedicated pass before anyone assumes either that
   it shares these defects or that it's clean.
8. **Treat `req_safe_01.rs` and `check_isolation_keepout.py`/
   `check_pad_orientation.py`/`check_hv_netclass_coverage.py` as the fix
   template**, not the Rust `safety/` rules as currently written — they
   demonstrate this project already knows how to build a real,
   currently-failable, CI-wired geometry check; the `safety/` rules
   diverged from that pattern somewhere.

## Coverage — what was and was not reached this session

**Audited in depth, with real-config item counts and/or a demonstrated
failability test where one exists:** all three `safety/` rules; the
CI-gating chain end to end (`ci_check_drc.py` → `drc_ratchet.py` →
`drc_runner.py`/`drc_oracle.py` → `generate_kicad_dru.py` → the
`constraints.rs` deserialization boundary); all 6 `drc/` rules; `emc/`'s
`loop_area.rs`, `noise_coupling.rs`, `ground_plane.rs`; `erc/`'s all 3 rules;
`placement/`'s both rules; `routing/`'s `isolation_barrier.rs`,
`isolation_slot.rs`, `partial_discharge.rs`; `req_safe_01.rs`; the Python
validators `rtd_safety.py`, `tht_check.py`, `geometric.py`, `drc_fence.py`,
`preflight.py`, and both same-named `DRCOracle` classes; five
isolation/creepage-adjacent `scripts/check_*.py` gates
(`check_isolation_keepout.py`, `check_hv_netclass_coverage.py`,
`check_creepage_clearance_drift.py`, `check_net_classification.py`,
`check_pad_orientation.py`).

**Explicitly not reached this session (say so plainly, per instructions) —
lower safety consequence per this document's own ranking rationale, but not
verified vacuous or sound either way:**
- `routing/`: `copper_pullback.rs`, `split_plane_crossing.rs`,
  `pad_entry_width.rs`, `parallel_run.rs`, `stitching_via_density.rs`,
  `power_pad_teardrop.rs`, `tht_thermal_relief.rs` — none of these are named
  isolation/HV/creepage/thermal in this project's own terminology, which is
  why they were deprioritized, but that is an inference from their names,
  not a verification.
- The remaining ~40 `scripts/check_*.py` gates not in the isolation/
  creepage/HV/net-classification group above (e.g. `check_board_containment.py`,
  `check_domain_partition.py`, `check_fault_list_consistency.py`,
  `check_footprint_drift.py`, `check_pll_range_consistency.py`,
  `check_regression.py`, `check_vacuous_gates.py` itself — worth noting
  `check_vacuous_gates.py` exists and its own vacuity was not checked here,
  which would be a fittingly recursive gap to close next — and others).
- `router_v6/constraints_drc_oracle.py`'s `DRCOracle` beyond confirming it
  exists, is live, and does not share the `None`-hardcoding pattern found
  elsewhere — its own internal correctness (including its
  `INTERNAL_LAYER_CREEPAGE_FACTOR` creepage model) was not vetted.
- `packages/temper-placer/src/temper_placer/requirements/validators/`
  beyond `req_safe_01.rs`'s Rust port (e.g. `_copper.py`, `_geometry.py`,
  `clearance.py` themselves, as opposed to the Rust port's fidelity to
  them).
- Any rule or script not named above, including all `Dfm`-category and
  purely stylistic rules, per the audit brief's own instruction to
  deprioritize those.
