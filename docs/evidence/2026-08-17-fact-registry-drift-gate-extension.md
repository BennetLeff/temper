# Fact-registry drift gate extension — 2026-08-17 (session 2)

provenance: commit=caec25d6137c5801e6aa974762b09371f210e894 dirty=false

Board sha256 at every point during this work: `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(committed; unmodified by this changeset — verified before and after every
step; `pcb/temper.kicad_pcb` never edited).

This document extends `docs/evidence/2026-08-17-fact-dedup-inventory-and-
gate.md` (PR #1311, merged) which built `scripts/check_fact_registry_drift.py`
and covered exactly one fact family (`mains_voltage_v`/`pollution_degree`).
Per the task brief's own incident table ("the huge surface area makes us
consistently resurface such facts"), this changeset extends the same gate
to the families that actually bit the project today: per-netclass via
diameter/drill (56 sub-fab-floor vias), the default via geometry, gate net
names, and a creepage-gate threshold duplicating an SSOT figure — plus two
new divergences this sweep found that were not in the brief's table.

## 1. Families registered

All in `scripts/check_fact_registry_drift.py`'s `REGISTRY`. The mechanism
itself grew `value_kind="str"` support (previously float/int only), needed
for the two net-name-valued families below.

| Family | Facts | Homes | Real-repo state |
|---|---|---|---|
| `default_via_diameter_mm` | 1 | 5 (design_rules.py, _parse_nets.py, stage0_data.py, constraints_design_rules.py, design_rules.rs) | **RED** — design_rules.rs's pyo3 `#[new]` default is 0.6mm, everyone else 0.9mm |
| `default_via_drill_mm` | 1 | 5 (same set) | CLEAN — all 0.3mm |
| `netclass_<Class>_via_diameter_mm` / `netclass_<Class>_via_drill_mm` | 26 (13 classes × 2 fields, table-driven) | 2 each (design_rules.py, netclass_rules.yaml) | CLEAN — the exact family that put 56 vias below the JLCPCB fab floor for 4 days; now the regression guard |
| `gate_drive_hs_net_name` / `gate_drive_ls_net_name` | 2 | 2 each (gates.py `_GATE_NETS`, gate_driver_constraints.yaml) | CLEAN — regression guard for PR #1310's fix |
| `gate_hs_net_current_rating_a` / `gate_ls_net_current_rating_a` | 2 | 2 each (gates.py `_DEFAULT_NET_CURRENTS`, ipc.rs `net_currents()`) | **TOOL ERROR (RED)** — new divergence, see §3 |
| `hv_lv_separation_gate_threshold_mm` | 1 | 2 (gates.py `_CREEPAGE_MIN_MM`, `IECCreepageGate` inline literal) | **RED** — 6.0mm vs the board's enforced 12.6mm PD3 figure, see §4 |

Plus the pre-existing `mains_voltage_v`/`pollution_degree` (2 facts, from
PR #1311), unchanged by this session — still red on `pcb_spec.yaml` and
`design_rules.py`'s `ACMains.voltage_v`, exactly as the task brief states.

Total: 2 (pre-existing) + 2 (via defaults) + 26 (per-netclass) + 4
(net-name) + 1 (creepage threshold) = **35 facts, 76 site checks**.

Overall gate exit state moved from VIOLATION (3) to **TOOL ERROR (5)**: the
two `gate_h*_net_current_rating_a` facts are missing citations, not wrong
values, and tool-error takes priority in the gate's exit-code selection —
this is by design (see `check_fact_registry_drift.py`'s own exit-code
doc: "never conflate a structurally-missing site with 0 violations").

## 2. Proof of non-vacuity per family

`scripts/tests/test_check_fact_registry_drift.py`: **25 tests** (was 11),
all passing.

- `TestStringValueKind` (3 tests) — proves the new `value_kind="str"`
  mechanism on a synthetic `tmp_path` registry: a stale net name is a
  violation, reconciled names are clean, and a citation that was never
  added at all (the exact shape of `gate_h*_net_current_rating_a`) is a
  TOOL ERROR, not a silent pass.
- `TestScopeAnchorFirstMatchAmbiguity` (2 tests) — a regression proof for
  a real bug this changeset caught in its own draft registry (see §3.1):
  proves a non-unique `scope_anchor` silently locks onto the wrong
  occurrence's window (fails closed as a tool error, not a false match),
  and proves the fix pattern (anchoring on an adjacent unique literal)
  finds the real value.
- `TestRealRegistryExtendedFamilies` (8 tests) — pins each new family's
  real-repo state: the known-red Rust via default, the 4 clean
  default-via-drill sites, all 26 netclass via facts clean (plus a named
  regression guard specifically for HighVoltageSignal, the class that
  actually broke), the 4 clean gate-net-name sites, the 4 known-red
  net-current tool-errors, and the 2 known-red creepage-threshold sites.
- `TestRealRegistryKnownState` (existing, from PR #1311) — updated:
  `test_gate_exits_violation_on_the_real_repo` renamed to
  `test_gate_exits_tool_error_on_the_real_repo` and its assertions
  updated to match the new exit state, with a note explaining why.

```
$ uvx --python 3.12 pytest scripts/tests/test_check_fact_registry_drift.py -q
25 passed in 0.16s

$ python3.12 scripts/check_fact_registry_drift.py; echo "EXIT: $?"
[... 35 facts printed, 76 site checks ...]
EXIT: 5
```

## 3. New divergences this sweep found (not in the task brief's table)

### 3.1 A real scope-anchor bug caught before it shipped

While writing the `default_via_diameter_mm`/`default_via_drill_mm` facts,
the first draft anchored the Rust `design_rules.rs` FactSite on the
generic marker `#[pyo3(signature = (`. Running the gate showed a TOOL
ERROR ("pattern did not match") instead of the expected DIFF. Cause:
that marker appears **three times** in `design_rules.rs` (`ViaTemplate::
new`, `DesignRules::new`, and a third pymethod) — `anchor_re.search()`
returns only the first match, `ViaTemplate::new`, whose 15-line window
never reaches `default_via_diameter` at all. Fixed by anchoring on the
adjacent literal `default_trace_width=0.2,`, which is unique in the file
(verified by grep). `TestScopeAnchorFirstMatchAmbiguity` pins both the
failure mode and the fix as a permanent regression proof — this exact
shape of bug (a scope anchor that isn't actually unique) could recur in
any future entry, and now has a named test documenting what it looks like
when caught.

### 3.2 `default_via_diameter_mm`: the Rust pyo3 bare-constructor default is stale

`packages/temper-design-bundle/src/design_rules.rs`'s `DesignRules::new()`
`#[pyo3(signature=...)]` defaults `default_via_diameter` to **0.6mm** —
the exact pre-2026-08-13 stale figure every other home of this fact was
raised away from (0.9mm). Traced: reachable only via a bare `DesignRules()`
Python construction with no kwargs. Grepped every such call site in
production (`router_v6/_astar_nlayer.py:1035`, `router_v6/
_astar_reconstruct.py:117`) — both import the **unrelated**
`stage0_data.DesignRules` Python dataclass (whose own default is correctly
0.9mm), not this Rust pyclass — confirmed by import-site grep, so this is
currently vestigial, not live. Same shape as the historical
`_parse_nets.py` "vestigial but live" incident the task brief cites: one
accidental refactor (a caller importing `core.design_rules.DesignRules`
instead and bare-constructing it) turns it live. **Not fixed**: this exact
default is field-for-field pinned by the pinned oracle `tests/core/
_design_rules_py_oracle.py` (`default_via_diameter: float = 0.6`), so a
mechanical fix requires the standing oracle re-pin ceremony — not an agent
fiat action, the same rule that blocked `mains_voltage_v`'s remaining two
sites in PR #1311's investigation.

### 3.3 `gate_h*_net_current_rating_a`: the ampacity gate never got the GATE_HS/GATE_LS rename

`PhysicsGate._GATE_NETS` was fixed 2026-08-17 (PR #1310, earlier session)
from `("GATE_H","GATE_L")` to `("GATE_HS","GATE_LS")`. A **different**
dict in the same file, `StackupGate._DEFAULT_NET_CURRENTS` (used by the
IPC-2221B ampacity DRC gate), and its Rust differential counterpart
`temper_drc_rs::ipc::net_currents()`, were never touched by that fix —
both still key on `"GATE_H"`/`"GATE_L"` only.

Traced by static analysis (this worktree has no pyo3 build available to
verify at runtime — noted as a limitation, not asserted as measured):
`StackupGate._resolve_net_current("GATE_HS")` —

1. `_DEFAULT_NET_CURRENTS.get("GATE_HS", 0.1)` — exact-match dict lookup,
   `"GATE_HS"` is not a key (only `"GATE_H"` is) → falls to the 0.1A
   unlisted-net default.
2. `temper_drc_rs.get_net_current("GATE_HS")` — Rust's case-insensitive
   **substring** match — `"GATE_HS".contains("GATE_H")` is `True` → would
   return the correct 2.0A.
3. `_resolve_net_current`'s own documented dispatch rule ("keep the Python
   exact-match as authority when it disagrees with Rust's substring
   answer") then returns the **Python** answer — 0.1A, the wrong one.

So the real board's `GATE_HS`/`GATE_LS` nets get the ampacity gate's
unlisted-signal-net default (0.1A) instead of their intended 2.0A
gate-drive citation. This existing test file, `tests/placer/cp_sat/
test_net_currents_rust_differential.py`, extensively documents the
Rust-vs-Python case/substring divergence but never questioned whether
`"GATE_H"`/`"GATE_L"` are even real board net names — they are not (see
§1's `gate_drive_hs_net_name` authority citation, `pcb/temper.kicad_pcb`'s
own net table).

**Registered as a TOOL ERROR** (the pattern searches for a `"GATE_HS"`
key that does not exist at either site — a missing citation, not a wrong
value), matching the gate's own fail-closed design.

**Not fixed here.** A rename ripples into `router_v6/
trace_width_assignment.py`'s `_resolve_current_a`: today, `GATE_H`/
`GATE_L` hit the "specific measured/cited current" branch (2.0A); after a
rename, an unrenamed `"GATE_H"` fixture net would instead fall through to
the keyword-match legacy-derivation branch (`_implied_legacy_current_a`),
changing the trace-width numbers that branch produces. Several tests in
`test_trace_width_assignment.py` use `"GATE_H"` as a fixture net name and
would need re-verification against the full differential/property suite —
work this agent could not complete without a pyo3 build in this worktree
(env constraints; `make venv-isolate`/`uv sync` were not run to keep this
turn bounded and avoid a multi-package Rust rebuild). Left as an open
finding, precise and attributed, for an agent that can run the full suite.

## 4. Open finding left red: `hv_lv_separation_gate_threshold_mm`

`packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` hardcodes
**6.0mm** in two places for HV↔LV net separation:

- `PhysicsGate._CREEPAGE_MIN_MM: float = 6.0`
- `IECCreepageGate.check()`'s inline `Violation(..., threshold=6.0,
  context={"required_mm": 6.0, ...})`

The board's actual enforced separation is **12.6mm** (PD3 reinforced
creepage, `scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM`,
matching `isolation_constants.py`'s `MIN_BARRIER_WIDTH_MM = 12.6`, both
citing docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md + PR
#1224/#1229).

`scripts/check_creepage_clearance_drift.py` (PR #1238) already discovers
`_CREEPAGE_MIN_MM` via its AST sweep but places it in the soft "FLAGGED
(needs human classification)" bucket (unspecified tier keyword), not
force-compared — verified by running it (`python3.12 scripts/
check_creepage_clearance_drift.py`, `packages/temper-placer/.../gates.py:848
(_CREEPAGE_MIN_MM): metric=creepage value=6.0mm (unspecified tier)` under
`=== FLAGGED ===`). It does **not** discover the `IECCreepageGate` inline
literals at all — they are keyword arguments inside a `Violation(...)`
call, not a named assignment its `_handle_assign` AST walk reaches. This
registry closes that specific gap by force-comparing both sites against
an explicit authority.

**Traced consequence, not just a report-label issue**: `DeltaMapper.
to_delta()` (`packages/temper-placer/src/temper_placer/placer/cp_sat/
delta_mapper.py` line ~153) reads `min_dist = violation.threshold`
directly from the `Violation` `IECCreepageGate` constructs — so the stale
6.0mm doesn't just mislabel a DRC finding, it sets the actual HV↔LV
placement-feedback separation distance the CP-SAT solver is asked to
enforce, 6.6mm short of the board's own declared PD3 bar. This matches
the task brief's own callout ("still leaking into `DeltaMapper`")
verbatim.

**Left red, not fixed, for two independent reasons:**

1. Hard rule: "NEVER change a clearance, creepage, copper-weight, or DRU
   threshold to make something pass." Registering the divergence is
   permitted; editing either 6.0 site is not.
2. Coordination: `netclass_constraints.py` + `IECCreepageGate` +
   `DeltaMapper` are explicitly a sibling agent's territory this session.

**Open finding for the owner/sibling**, precise decision needed: is
`IECCreepageGate` (which filters kicad-cli DRC `rule == "clearance"`
errors, not the `creepage` rule type `generate_kicad_dru.py` actually
emits, yet calls the result "creepage") supposed to track the 12.6mm
creepage figure, a different clearance figure, or is it measuring the
wrong DRC rule type entirely? This registry asserts 12.6mm as the
authority because that is the figure the rest of the codebase treats as
the board's enforced HV↔LV separation bar, but the clearance-vs-creepage
rule-type question is a judgment call this agent does not resolve.

## 5. What was NOT changed

- `pcb/temper.kicad_pcb` — untouched, sha256 verified unchanged before and
  after every step.
- No clearance/creepage/copper-weight/DRU threshold value edited anywhere.
- No pinned `_*_py_oracle.py` oracle re-pinned or deleted.
- `netclass_constraints.py`, `IECCreepageGate`, `DeltaMapper`,
  `domain_clearance.py` — not edited (sibling territory); the creepage-
  threshold divergence inside `IECCreepageGate`/`PhysicsGate` is
  registered but not fixed, per §4.
- `StackupGate._DEFAULT_NET_CURRENTS` / `temper_drc_rs::ipc::
  net_currents()` — not edited; registered as a known-red open finding
  per §3.3, deliberately not fixed given unverified downstream ripple.

## 6. Status checklist

- [x] Registry extended to cover all four "at minimum" families from the
      task brief: per-netclass via diameter/drill (+ `_parse_nets.py`'s
      default), safety-spec values (already covered by PR #1311, left
      as-is), a gate threshold duplicating an SSOT figure, board net
      names duplicated in code.
- [x] Swept for more: found and registered 2 new divergences beyond the
      brief's table (§3.2 Rust via default, §3.3 gate net-current
      citations), plus caught and fixed a real bug in this changeset's
      own draft registry before it shipped (§3.1).
- [x] Every entry machine-checked, fail-closed on divergence (VIOLATION),
      missing file (TOOL ERROR), and structural drift / non-unique-anchor
      (TOOL ERROR) — proven by `TestScopeAnchorFirstMatchAmbiguity` and
      `TestStringValueKind`.
- [x] Non-vacuity proven per family: 25 tests, both-direction synthetic
      proofs for every new mechanism, real-repo pins for every new fact.
- [x] Fixed only unambiguous divergences: none required a value edit in
      this session (the per-netclass via family and gate-net-name family
      were already reconciled by earlier same-day work; this changeset
      only added the regression guards for them).
- [x] Judgment calls / hard-rule-blocked divergences left red with a
      precise, attributed finding: `default_via_diameter_mm`'s Rust site
      (oracle-pinned), `hv_lv_separation_gate_threshold_mm` (hard rule +
      sibling territory + open rule-type question), `gate_h*_net_current_
      rating_a` (unverified downstream ripple).
- [x] Confirmed wired into `board-provenance-requirements-gates`
      (`.github/workflows/python-tests.yml`) — no structural workflow
      change needed (PR #1311 already wired both the unit-test step and
      the gate-script step, `if: !cancelled() && steps.setup.outcome ==
      'success'`, not `continue-on-error`); verified triggering via
      `check_required_checks.job_should_run` on this changeset's own
      files, and confirmed YAML still parses.
- [x] Board sha256 unchanged throughout:
      `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`.
