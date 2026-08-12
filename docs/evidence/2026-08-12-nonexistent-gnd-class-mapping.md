<!-- provenance: written on branch fix/nonexistent-gnd-class-mapping, rebased onto origin/main at c43c50927 (after #1083/#1084 merged). pcb/temper.kicad_pcb is NOT modified at any point in this session. All measurements below are fresh, taken in this session, against the real repo files; none is copied from a prior document. -->

# `design_rules.py`'s `"gnd"`/`"PWR_RTN"` → `"GND"` mapping named a class `pcb/temper.kicad_pro` never declared. `"GND"` was real Python-side data, not an invented name — which is exactly why the defect was invisible from inside the placer.

**Verdict up front.** `packages/temper-placer/src/temper_placer/core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` mapped `"gnd"` (the board's largest net, 86 pads) and `"PWR_RTN"` to a class named `"GND"`. `pcb/temper.kicad_pro` declares ten netclasses as of this session (`Default`, `Power`, `HighVoltage`, `HighVoltageTank`, `GateDriveHV`, `GateDriveSELV`, `HighVoltageIsolated`, `ACMains`, `FinePitch`, `Differential`) — `"GND"` is not one of them, and never has been (confirmed by `git log --all -S'"name": "GND"' -- pcb/temper.kicad_pro`: zero hits, ever). Reassigned to the classes the two in-flight kicad_pro decisions already settled on: `gnd` → `Power` (PR #1087, open), `PWR_RTN` → `HighVoltage` (PR #1083, **merged** during this session — see §4). No netclass parameter *value* changed.

Measured: the CP-SAT netclass+courtyard constraint count on the real board is **unchanged** (15,996 → 15,996) and the 8-isolator isolation barrier still **solves optimal** with all 8 hard-constrained, both before and after (§5). A real, substantive side effect *was* found and is not silently absorbed: `gnd` loses F.Cu/B.Cu zone-pour eligibility and would now be routed by A* instead (§6) — flagged prominently, not fixed here, since fixing it would mean assigning `Power.routing_strategy` a value, and this task's own rule is not to change a netclass parameter value.

---

## 1. What `"GND"` turned out to be

`"GND"` is not an invented, never-real class name — it is a genuine `NetClassRules` row in `TEMPER_NET_CLASSES` (same module), with real, distinct parameters (`trace_width=1.0`, `clearance=0.3`, `via_diameter=1.0`, `via_drill=0.5`, `dru_priority=60`, `routing_strategy="plane_preferred"`), present since the module's creation:

```
$ git log --oneline -S'"GND": NetClassRules' -- packages/temper-placer/src/temper_placer/core/design_rules.py
4f315fd0d test/debug: Add diagnostic script for fixed positions
$ git show 4f315fd0d -- packages/temper-placer/src/temper_placer/core/design_rules.py | head -5
diff --git a/.../design_rules.py b/.../design_rules.py
new file mode 100644
```

`design_rules.py` was **created** by `4f315fd0d` (2025-12-25) and the `"GND"` `NetClassRules` entry was there from the first line — it was never renamed, never migrated away from a once-real kicad_pro class. It was authored directly in the Python table and never mirrored into `pcb/temper.kicad_pro`'s `net_settings.classes`.

The `gnd`/`PWR_RTN` → `"GND"` *assignment* is a separate, later addition — `"PWR_RTN": "GND"` landed in `8c5471a37` (2026-07-19, "assign production-board nets"), `"gnd": "GND"` landed in `b6bf871e9`/`e701103a8` (#1042, 2026-08-11). Both commits pointed at a class that already existed in the Python table (so nothing looked broken from inside the placer — `get_rules_for_net` resolved a real, non-default object every time) but had never existed in `kicad_pro`.

**`"GND"` also exists as a third, independent copy** in `packages/temper-placer/configs/netclass_rules.yaml:170-176` (its own `GND:` class block, `clearance: 0.3`, `trace_width: 1.0`, `layer: "In1.Cu"`, no `routing_strategy` field — that field doesn't exist in the YAML schema at all). This file's own net→class *assignment* table is not independent, though: `packages/temper-design-bundle/src/loaders.rs:381-385` shows `load_netclass_rules()` calls `design_rules.net_class_assignments.update(TEMPER_NET_ASSIGNMENTS)` — it imports `TEMPER_NET_ASSIGNMENTS` from `design_rules.py` directly. So the two-line fix in `design_rules.py` is the single point of control for which class name `gnd`/`PWR_RTN` resolve to everywhere in this codebase (verified in §5/§6 below, both of which exercise the `netclass_rules.yaml`-loaded path). `netclass_rules.yaml`'s own `GND:` class block did not need editing.

**`docs/specs/NET_CLASS_SPECIFICATION.md`** (§3.2, "Power (Low Voltage Rails)") has never had a separate GND class either — it lists **"GND (control ground)"** as an assigned net of **Power**. This is the spec `docs/evidence/2026-08-12-selv-net-assignment.md` (PR #1087) grounds its `gnd` → `Power` choice in, and this fix mirrors that choice into `design_rules.py`.

## 2. What the placer does with an unresolvable class name

Traced `DesignRules::get_rules_for_net` (`packages/temper-design-bundle/src/design_rules.rs:704-746`), the pyo3 port of the pre-migration Python `DesignRules.get_rules_for_net`:

- **Tier 2/3** (explicit `net_class_assignments` lookup): `if let Some(nc) = &net_class && let Some(rules) = self.net_classes.bind(py).get_item(nc.as_str())? { return ...; }` — the `&& let` chain means a class *name* present in the assignment table but **absent** from `net_classes` does **not** raise. The `if let` on the `get_item` result is simply `None`, the condition is false, and control falls through silently to Tier 4 (the ground/power/HV name-pattern cascade), then Tier 5 (`default_net_class_rules()` — `Default`, `dru_priority=999`, whatever `default_clearance`/`default_trace_width` happen to be, typically the thinnest class on the board).

**Confirmed empirically** — an assignment naming a class that exists in *neither* table:

```
>>> dr.net_class_assignments['totally_fake_signal_net'] = 'NoSuchClass'
>>> dr.get_rules_for_net('totally_fake_signal_net')
NetClassRules(name='Default', clearance=0.15, trace_width=0.2, dru_priority=999, ...)
```

This **is** the fail-open shape the task brief named ("`unwrap_or("Unknown")` defaulting safety rules to the thinnest on the board") — real, present, silent. **But it is not what this specific defect exercised.** `"GND"` is present in `TEMPER_NET_CLASSES` (§1), so Tier 3's `get_item("GND")` **succeeds** and returns the real `"GND"` `NetClassRules` object — `gnd`/`PWR_RTN` never fell through to Tier 4/5, never silently downgraded to `Default`. Confirmed:

```
>>> dr.get_rules_for_net('gnd').name, dr.get_rules_for_net('gnd').clearance
('GND', 0.3)
>>> dr.get_rules_for_net('PWR_RTN').name, dr.get_rules_for_net('PWR_RTN').clearance
('GND', 0.3)
```

Also confirmed: `gnd`'s Tier-4 ground-pattern fallback (`is_ground_net("gnd")` → `True`) lands on the exact same `"GND"` object Tier 3 does — `classes.get_item("GND")` succeeds there too. This is *why* the defect was measured byte-identical whether `gnd` was mapped or left unassigned entirely (`docs/evidence/2026-08-12-selv-net-assignment.md`, §1.2): both paths in `get_rules_for_net` terminate at the identical, real, kicad_pro-invisible object. **This defect's actual shape is not "fail-open to a default," it is "resolves consistently to a class that exists on one side of the two-file SSOT and not the other."** A genuinely fail-open case would need a class name absent from *both* tables — that shape exists and is real in this codebase (demonstrated above), but `gnd`/`PWR_RTN` → `"GND"` was not an instance of it.

## 3. Why it was inert on the fabrication path — reconciling with the kicad_pro-side measurement

`docs/evidence/2026-08-12-selv-net-assignment.md` §1.2 (PR #1087) measured `kicad-cli` DRC `clearance` byte-identical (386, both samples) whether `kicad_pro`'s own `net_settings.netclass_assignments["gnd"]` was `"GND"` (undeclared) or absent entirely. That measurement is **independent of, and does not depend on**, `design_rules.py`'s table — `kicad_pro` and `design_rules.py` are two separate SSOTs (§1), and the SELV-net-assignment PR touches only `kicad_pro`. `kicad-cli`'s own DRC engine treats an assignment naming an undeclared class as absent, matching (by a different mechanism, in a different codebase, in Rust vs. C++) the same "silently ignore, don't raise" shape §2 found in the Python/Rust placer's `get_rules_for_net`.

## 4. Two in-flight PRs — one now merged

- **PR #1083** (`fix/unassigned-hv-domain-nets`) assigned `PWR_RTN` → `HighVoltage` in `kicad_pro`. **Merged into `origin/main` as `42c73e21f` during this session** (confirmed: `gh pr view 1083 --json state,mergedAt` → `MERGED`). Its own commit message explicitly names this task's defect: *"PWR_RTN was present there \[`design_rules.py`\] (mapped to `"GND"`, a separate open question)."* This fix is that open question, resolved to match.
- **PR #1087** (`fix/unassigned-selv-nets`) assigned `gnd` → `Power` in `kicad_pro`, grounded in `NET_CLASS_SPECIFICATION.md` §3.2. Still **open** as of this writing (confirmed via `gh pr view 1087`). Not contested against #1083 — the two PRs assign different, non-overlapping nets.

`design_rules.py` now names the same classes both PRs settled on for `kicad_pro`.

## 5. Measured placement effect: constraint count and the 8-isolator barrier

Reused production functions directly (not reimplemented): `generate_netclass_separated_constraints`, `courtyard_clearance_mm`, `load_netclass_rules`, `parse_kicad_pcb` (the exact `_build_constraints` helper `test_golden_board_pumpkin_real_board.py` uses), plus `classify_domain_partition`, `load_domain_manifest_nets`, `compute_pad_groups`, `evaluate_isolator_feasibility` from `isolation_barrier.py` for the barrier. Solved with the pinned Pumpkin engine (`scripts/verify_pumpkin_engine.py` verified `VERIFIED`, sha256 `7ff153f4…`, source commit `5bbf650d…`) against the real, current `pcb/temper.kicad_pcb` (169 components — this board predates the `feat/board-sync-and-placement` reconciliation the `2026-08-12-isolation-barrier-pumpkin-placement.md` evidence doc used, so its isolator set is the *pre-reconciliation* one, `{C6, K1, K2, K3, PS1, T1, U3, U7}`, not that doc's `{…, T2, U6}`).

| | Pre-fix (`gnd`/`PWR_RTN` → `"GND"`) | Post-fix (`gnd`→`Power`, `PWR_RTN`→`HighVoltage`) |
|---|---:|---:|
| `gnd` resolved clearance | 0.3mm | 0.5mm |
| `PWR_RTN` resolved clearance | 0.3mm | 2.0mm |
| netclass-auto SEPARATED constraints | 9,714 | 9,714 |
| courtyard-backfill SEPARATED constraints | 6,282 | 6,282 |
| **total base constraints** | **15,996** | **15,996** |
| + isolation-barrier constraints (8 isolators, PD2/8.0mm, horizontal) | 173 | 173 |
| **total constraints, full model** | **16,169** | **16,169** |
| Pumpkin solve, all 8 isolators hard | `optimal`, 1754ms | `optimal`, 1773ms |
| Per-isolator feasibility (all 8) | all `feasible=true` | all `feasible=true` (identical numbers — geometric, netclass-independent) |

**The constraint count does not move**, unlike #1061's `Power.clearance` 0.25→0.5 change, which crossed the courtyard-backfill τ=0.4mm threshold for every `Power`-classed pair on the board and moved the count materially. `generate_netclass_separated_constraints` assigns each *component* a single dominant net class (`_resolve_component_net_class`, highest-`dru_priority` net wins) and only emits a constraint for *cross-class* component pairs — the pair either exists or doesn't based on whether two components' classes differ, not on the class's own clearance value. Reclassifying `gnd`/`PWR_RTN` changed which value those existing cross-class pairs carry (verified: `gnd`'s pairwise clearance rows now read 0.5mm not 0.3mm; `PWR_RTN`'s read 2.0mm not 0.3mm) but did not add or remove any pair on this board — no component that previously differed from its neighbor on class now happens to match it, or vice versa. **The isolation barrier holds identically**: all 8 isolators individually feasible at the 8.0mm bar, unaffected (isolator feasibility is pure pad/board geometry, independent of netclass); the full joint model (barrier + netclass + courtyard) solves `optimal` both before and after, at effectively the same wall time (1.75s vs 1.77s, within solver noise).

## 6. Zone-pour and routing-strategy side effect — real, measured, not fixed here

`router_v6/_zone_pour_stitch.py::_zone_layers_for_net` and `_net_policy.py::_should_route` are two of the production consumers that import `TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES` from `design_rules.py` **directly** (not through `netclass_rules.yaml`), and `_zone_layers_for_net` reads the *explicit* assignment (`TEMPER_NET_ASSIGNMENTS.get(net_name)`), not the pattern-fallback cascade §2 traced. `design_rules.py`'s own comment at the `gnd`/`PWR_RTN` lines (pre-fix) called `"GND"`'s `routing_strategy="plane_preferred"` *"the load-bearing half"* connecting a real routing decision (skip `gnd` in Stage-4 A*, rely on the zone pour) to the class that justifies it.

Measured, before/after, on the real repo:

| | `gnd` | `PWR_RTN` |
|---|---|---|
| Zone-pour layers, pre-fix | `["F.Cu", "B.Cu"]` (0.3mm) | `["F.Cu", "B.Cu"]` (0.3mm) |
| Zone-pour layers, post-fix | **`[]`** | `["F.Cu", "B.Cu"]` (2.0mm) |
| `_should_route` (A*-routed), pre-fix | `False` (zone-covered) | `False` (zone-covered) |
| `_should_route` (A*-routed), post-fix | **`True`** | `False` (zone-covered) |
| Continuity-exempt (single hull, not clustered), pre-fix | n/a (own In1.Cu plane) | Yes (`"GND"` in `_CONTINUITY_EXEMPT_CLASSES`) |
| Continuity-exempt, post-fix | n/a | **No** (`"HighVoltage"` not in that set — same clustering `_zone_pour_stitch.py`'s R6 update already applied to `SW_NODE`/`DC_BUS_RTN`) |

`Power.routing_strategy` is `None` (the dataclass default) and `HighVoltage.routing_strategy` is `"plane_required"` (still zone-eligible, just under a different tier). Consequence: `gnd` **loses** its F.Cu/B.Cu zone-pour eligibility and would now be attempted by A* path routing instead of being excluded as zone-covered. `gnd`'s **dedicated In1.Cu ground-plane pour** (`router_v6/_ground_plane.py`, the "first real In1.Cu ground-plane generator," #1022/#1041) is **unaffected** — it targets the literal net name `"gnd"` directly and never consults `TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES` at all. `PWR_RTN` keeps zone-pour eligibility (now via `plane_required` instead of `plane_preferred`) but loses the `"GND"`-class continuity exemption that let its zone stay one board-spanning hull rather than clustering per-component.

**This is not fixed in this change.** Fixing it would mean giving `Power` a `routing_strategy` value it does not currently have — a netclass *parameter* change, which both this task's rules and #1061's settlement explicitly place out of scope. It is reported here, prominently, as the honest cost of following the two in-flight PRs' class choice rather than inventing a new one: `gnd`'s zone-pour/A* routing behavior changes, `PWR_RTN`'s zone-clustering behavior changes, and the actual clearance values placer-side both nets get are now materially different (0.3mm → 0.5mm / 2.0mm) from what they were. None of it was exercised by the CP-SAT constraint-count/isolation-barrier measurement in §5 because that measurement is upstream of routing — it is a `route_pcb()`-stage (router_v6) consequence, not a `solve_placement()`-stage one.

## 7. The gate: `check_netclass_class_param_correspondence.py`, extended (PROPERTY 2)

PR #1056/#1061 landed this gate's PROPERTY 1 — parameter agreement for classes declared in *both* `pcb/temper.kicad_pro` and `TEMPER_NET_CLASSES` by name. It explicitly disclaimed the property this defect needed: *"a class present in only one \[table\]… has nothing to disagree with and is not a defect this gate's invariant covers."* `"GND"` is exactly that shape — present in `TEMPER_NET_CLASSES`, absent from `kicad_pro`'s `net_settings.classes` — so PROPERTY 1 could never have caught it no matter how many times it ran.

Added PROPERTY 2 to the same script (extended, not a new gate, per this task's own instruction): for every net named in `TEMPER_NET_ASSIGNMENTS`, the class it maps to must be declared in **both** tables. Shown failing on the pre-fix state and passing after, both in a unit-test-independent direct CLI run and in the extended `TestRealRepoIntegration` test:

```
$ git show HEAD~1:.../design_rules.py > .../design_rules.py   # ONLY design_rules.py reverted
$ uv run python scripts/check_netclass_class_param_correspondence.py; echo "exit: $?"
=== PROPERTY 2 -- UNRESOLVED CLASS REFERENCES (BLOCKING): 2 ===
  VIOLATION net 'PWR_RTN' -> class 'GND', not declared in: pcb/temper.kicad_pro net_settings.classes
  VIOLATION net 'gnd' -> class 'GND', not declared in: pcb/temper.kicad_pro net_settings.classes
=== PROPERTY 2 -- KNOWN UNRESOLVED (INFORMATIONAL, not blocking): 1 ===
  KNOWN net 'CGND' -> class 'GND', not declared in: pcb/temper.kicad_pro net_settings.classes
FAILED -- 0 field mismatch(es), 2 unresolved class reference(s)
exit: 3

$ git checkout -- .../design_rules.py   # this fix restored
$ uv run python scripts/check_netclass_class_param_correspondence.py; echo "exit: $?"
=== PROPERTY 2 -- UNRESOLVED CLASS REFERENCES (BLOCKING): 0 ===
=== PROPERTY 2 -- KNOWN UNRESOLVED (INFORMATIONAL, not blocking): 1 ===
  KNOWN net 'CGND' -> class 'GND', not declared in: pcb/temper.kicad_pro net_settings.classes
Net-class correspondence gate passed
exit: 0
```

**`CGND` remains, deliberately, out of this fix's scope.** `TEMPER_NET_ASSIGNMENTS` still carries `"CGND": "GND"` — the *third* mapping naming the retired `"GND"` class, unaddressed by this task's two-mapping brief. The line's own comment (unchanged by this fix) is explicit that resolving it is "an open, deliberately-reserved decision… removing it is that decision's job, not this line's" — `CGND` names zero nets on the real board (0 references in `pcb/temper.kicad_pcb`, checked 2026-08-11 and again in this session), so the unresolved reference is real but inert, not a live hazard. PROPERTY 2's new `_KNOWN_UNRESOLVED_ASSIGNMENTS` carve-out (one entry, `{"CGND"}`, with its own citation — the same convention `check_hv_netclass_coverage.py` already uses for its own scope carve-outs) reports it every run, never silently, without blocking CI on a decision this task does not make. **This is the gate's own honest limit, not a loophole**: promoting `CGND` from known to blocking is exactly the follow-up its own carve-out comment names.

The gate is wired **BLOCKING** in CI (`.github/workflows/python-tests.yml`, "Net-class parameter correspondence gate (Gate 6)," no `continue-on-error`, per #1061's "Gate 6 is now blocking" landing) — PROPERTY 2 is added to the same blocking step, not a separate advisory one. 8 new/updated tests in `scripts/tests/test_check_netclass_class_param_correspondence.py` (`TestReferencedClassExistence`: falsifier, control, reverse-direction falsifier, mutation-clears-violation, known-carve-out-not-blocking, known-carve-out-does-not-mask-a-real-violation, empty-assignments-anti-vacuity; plus 4 `TestHelperUnits` unit tests for `check_referenced_classes_exist`); 6 pre-existing `TestMutations`/`TestAntiVacuity` tests updated to pass an explicit, non-interfering `net_assignments` override so PROPERTY 2's now-live default (the real `TEMPER_NET_ASSIGNMENTS`) doesn't perturb tests that are only exercising PROPERTY 1. All 30 tests in the file pass; `test_gate_passes_clean_on_real_repo` now additionally asserts PROPERTY 2 is clean (0 blocking, 1 known — `CGND`) against the real, current repo.

## 8. Known pre-existing gap, not introduced by this fix

`packages/temper-placer/tests/core/_design_rules_py_oracle.py` (the frozen, pinned pre-migration Python oracle the Rust `design_rules.rs` port is checked bit-identical against) is **already stale** on `origin/main` before this fix — `test_design_rules_rust_differential.py::test_module_constants_identical`/`test_create_temper_design_rules_identical`/`test_get_rules_for_net_classification_cascade_identical` **already fail** (confirmed by reproduction: reverted only `design_rules.py` to its pre-fix content and re-ran — same 3 failures, for `HighVoltage.clearance` and `+15V` param mismatches unrelated to this change). The oracle also never had a `"gnd"` entry at all (only `PWR_RTN`/`CGND` → `"GND"`), so it was already diverging from `design_rules.py`'s live `TEMPER_NET_ASSIGNMENTS` before this session. This fix changes *which* assertion inside `test_get_rules_for_net_classification_cascade_identical` trips first (`PWR_RTN` instead of `+15V`) but does not turn a passing test red or a failing test count up. The oracle file carries an explicit `DO NOT EDIT THE SEMANTICS` contract (`_design_rules_py_oracle.py`'s own module docstring: re-pinning must be a whole-file operation from a new base, not a hand-edit) — not touched here. A full oracle re-pin is a separate, already-overdue maintenance task (`HighVoltage.clearance`/`+15V` have been diverging since at least #1061/#1084) this fix does not attempt.
