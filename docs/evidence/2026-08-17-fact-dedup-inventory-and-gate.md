# Fact-deduplication inventory + mechanized gate — 2026-08-17

provenance: commit=e5b2d15b1dd0f8391dfef37a9dd45576b70ad1f6 dirty=true

Board sha256 at all points during this work: `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`
(committed `aec4bf1f8`; unmodified by this changeset — verified before and
after every step below).

Scope, per the task brief: **fact/value-level duplication** (safety/geometry
constants, thresholds, net names, layer/stackup facts, board metadata, metric
definitions, ratchet ceilings, BOM values). A separate SSOT-focused agent
owns **artifact/code-level duplication** (parallel implementations,
generated-vs-committed files, dead code) — not this doc's territory, and I
did not touch `scripts/check_duplicate_predicates.py` or
`scripts/duplicate_predicate_registry.py` beyond reading them.

---

## 1. What already exists (read first, per the task brief)

| Mechanism | Covers | State |
|---|---|---|
| `scripts/check_creepage_clearance_drift.py` (#1238) | Creepage/clearance mm figures across `.ato`/Python/YAML | Real, wired, RED by design (`[clearance/reinforced] 2.0 vs 6.0`, a genuine judgment call left to the owner) |
| `scripts/check_duplicate_predicates.py` + `duplicate_predicate_registry.py` (#1308) | Duplicated **code** (predicates/functions), not values | Real, wired into the required `Cross-Source Consistency Gates` job; `OPEN_FINDINGS` already tracks the HV-keyword-matcher re-divergence — sibling-agent territory, not touched here |
| `scripts/generate_kicad_dru.py` | SSOT → generated `.kicad_dru` | Already byte-identical to its SSOT output (positive example, not a gap) |
| `packages/temper-design-bundle/src/safety_value.rs` | `SafetyValue`/`Provenance` for IEC-table-derived clearance/creepage constants | The right abstraction for standards-table lookups specifically; does not generalize to non-table scalars (mains voltage, ratchet ceilings, board metadata) without forcing an awkward fit, so I built a sibling mechanism instead of stretching this one (see §3) |
| `packages/temper-geometry/src/layer_identity.rs` | 6-layer stackup fact | Already fixed: reads directly from the board file, "no separate copy to go stale" (its own test name) — checked, clean, not a gap |
| Thermal constants (`packages/temper-thermal/src/thermal_constants.rs`, PR #1243/#1254) | `DEFAULT_AMBIENT_C`, `T_J_DESIGN_MAX_C`, `FIRMWARE_TRIP_TS_C` | Checked against `pcb_spec.yaml` (60.0/125.0) and `firmware/config.yaml` (80.0) — all three agree. Clean. |
| OCP threshold (40A) | `firmware/config.yaml` `OVER_CURRENT_THRESHOLD` | Checked; only coincidentally near other 40A figures (IGBT device rating in `elec/src/main.ato` is a *different* quantity, not a duplicate of the same fact) |

## 2. Inventory: the fact family that IS diverging

**Mains voltage and pollution degree (`SafetySpec`)** — a real, live, currently
unresolved instance of "one fact, many homes, drifting," and per the task
brief's own callout, safety-relevant (IEC 60335-1 Table 15's rated-voltage
row shifts at 150V).

### Authority

**120V RMS ±10%, PD3.** Not a judgment call — determinable from repo evidence:

- `docs/specs/REQUIREMENTS.md` REQ-SYS-01: "AC Input Voltage: 120V RMS ±10%,
  US residential mains."
- `elec/src/main.ato:52-56`: `v_ac_nominal = 120V`, with its own
  `assert v_ac_nominal within 100V to 130V` (NEMA 5-15 tolerance).
- `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`: the voltage doubler exists
  *specifically* so the appliance needs no 240V input ("Compatible with
  120V/15A outlet (no 240V required)").
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Sec 2.1 (revision 1.4,
  2026-08-14) already corrected its own "120-240V RMS" row to match
  REQ-SYS-01 and states "No 240V variant is intended for this design."
- PD3: `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` + PR
  #1224/#1229, "PD3 governs (12.6mm reinforced, 10.0mm tank)."

### Homes and current values

| Home | Value | Agrees? |
|---|---|---|
| `elec/src/main.ato` `v_ac_nominal` | 120V | YES |
| `packages/temper-placer/configs/pcb_spec.yaml` `safety.mains_voltage_v` / `.pollution_degree` | 230.0 / 2 (PD2) | **NO** |
| `packages/temper-placer/src/temper_placer/core/design_rules.py` `ACMains` net-class `voltage_v` | 240.0 | **NO** |
| `packages/temper-design-bundle/src/specification_contracts.rs` `SafetySpec::new()` default | 230.0 / 2 (PD2) | **NO** |

Three homes still carry pre-decision values. This was already partially
discovered on 2026-08-14 (`HIGH_VOLTAGE_CLEARANCE_SPEC.md` revision-history
entry 1.4), which flagged the `pcb_spec.yaml` and `design_rules.py` sites and
explicitly declined to fix them ("should be reconciled to 120V by whoever
owns that config") — but that investigation was itself prose, in a document
that can drift; nothing mechanized the check, so it was not re-verified
since and a third home (`specification_contracts.rs`) was never named there.

### Why I did not fix it

The **value** is not in question. The **mechanical fix** is blocked:

- `design_rules.py`'s `ACMains.voltage_v=240.0` is differentially compared,
  field-for-field, against the **pinned** oracle
  `tests/core/_design_rules_py_oracle.py` (hash-pinned in
  `scripts/oracle_hashes.json`, itself carrying `voltage_v=240.0`).
  Confirmed: `voltage_v` is not dead metadata — `temper-drc-rs`'s
  `partial_discharge.rs` filters net classes by `voltage_v >= 60.0` for the
  inner-layer HV clearance multiplier rule (both 120 and 240 clear 60V
  identically, so this specific consumer's *behavior* would not change —
  but the field is live, not decorative, and the oracle still pins the
  literal value).
- `specification_contracts.rs`'s Rust `SafetySpec` default is the **only**
  runtime default in the system — Python's own `SafetySpec` is a bare
  re-export (`SafetySpec = _tdb.specification_contracts.SafetySpec`, no
  independent Python default to fix instead). It is differentially compared
  against the **pinned** oracle `tests/core/_specification_py_oracle.py`
  (`mains_voltage_v: float = 230.0`) and is asserted **directly** by
  `tests/core/test_specification.py::test_safety_spec_defaults` — itself a
  live instance of handoff §11's thesis: a passing, CI-required test
  asserting a wrong value, with a generic-sounding justification
  ("SafetySpec default values match IEC 60335-1 typical consumer
  appliance" — not true of this specific 120V design).
- `pcb_spec.yaml` is not itself oracle-pinned, but its value flows into the
  same derivation surface the pinned physics-oracle differential tests
  exercise (`pipeline/derivation.py` → `hv_lv_isolation_mm` →
  `_physics_oracle_py_oracle.py`, which defaults to loading this exact file
  when no explicit spec path is given). I could not, in the time available,
  exhaustively rule out that some path through that surface depends on the
  literal 230.0/PD2 values without running the full differential suite —
  and the prior, more thorough 2026-08-14 investigation reached the same
  conclusion and also declined to fix it in isolation.

Per the hard rules — **never delete/consolidate/re-pin a pinned oracle**,
and re-pinning is "a separate, deliberately-committed act" requiring
"exhaustive-divergence evidence" — fixing this properly is a coordinated PR
that (1) updates all three sites to 120.0/3, (2) re-pins both oracles with
the required evidence, and (3) corrects `test_safety_spec_defaults` and
`test_load_pcb_spec_yaml_has_safety`. That is out of scope for a mechanical
"cheap fix" here, and is exactly the shape of thing this task's hard rules
say to leave red with a precise, attributed finding rather than resolve by
fiat.

## 3. The gate

`scripts/check_fact_registry_drift.py` — an explicit, registry-driven gate
(same rationale as `duplicate_predicate_registry.py`: a hand-reviewed,
falsifiable list of proven sites, not a repo-wide regex sweep for the word
"voltage," which would drown in unrelated per-component ratings). Each
`Fact` names an authoritative value + source, and a tuple of `FactSite`
homes (file, description, a scoped regex). Exit codes mirror the existing
drift gates: 0 clean, 3 violation, 5 tool error (empty registry, missing
file, or a pattern that no longer matches — never silently "0 violations").

**Currently discovers 2 facts, 6 sites, and reports 5 divergences** — see
run output below.

### Proof of non-vacuity

`scripts/tests/test_check_fact_registry_drift.py`, 11 tests, all passing:

- `TestSyntheticRegistry` — a `tmp_path` fixture with a monkeypatched
  registry proves the mechanism itself, independent of the real repo:
  `test_mismatched_site_is_a_violation` (fires on real divergence),
  `test_reconciled_sites_are_clean` (identical registry shape, only file
  contents changed → goes green — the direct "not vacuous" proof: it *can*
  pass), `test_missing_file_is_a_tool_error_not_a_pass`,
  `test_renamed_field_is_a_tool_error_not_a_silent_pass`,
  `test_scope_anchor_prevents_cross_class_false_match`,
  `test_empty_registry_is_a_tool_error`,
  `test_fact_with_zero_homes_is_a_tool_error`.
- `TestRealRegistryKnownState` — runs against the **actual repo root** with
  the real registry: confirms `elec/src/main.ato` agrees with authority,
  pins the 5 known-divergent sites as an expected-red regression (so a
  future silent "fix" that isn't real would be caught, and a real fix would
  need to update this pin deliberately), and confirms the gate's overall
  exit state is VIOLATION on the real repo today.

```
$ uv run --no-sync python scripts/check_fact_registry_drift.py; echo "EXIT: $?"
=== board-spec/mains_voltage_v ===
  Authoritative: 120
  OK    elec/src/main.ato (atopile SSOT nominal AC input): 120
  DIFF  packages/temper-placer/configs/pcb_spec.yaml (...): 230
  DIFF  packages/temper-placer/.../design_rules.py (ACMains net-class metadata voltage_v): 240
  DIFF  packages/temper-design-bundle/.../specification_contracts.rs (...): 230

=== board-spec/pollution_degree ===
  Authoritative: 3
  DIFF  packages/temper-placer/configs/pcb_spec.yaml (...): 2
  DIFF  packages/temper-design-bundle/.../specification_contracts.rs (...): 2

FAILED -- a registered fact has homes with disagreeing values.
EXIT: 3
```

```
$ uv run --no-sync pytest scripts/tests/test_check_fact_registry_drift.py -q
...........
11 passed in 0.16s
```

### CI wiring — proven by trigger and job wiring, not by naming

Added to `board-provenance-requirements-gates` (`.github/workflows/python-tests.yml`),
immediately after the creepage/clearance drift gate's steps: unit tests, then
the gate itself, both guarded by `if: ${{ !cancelled() && steps.setup.outcome
== 'success' }}` and **not** `continue-on-error`.

**Deliberately in the same job as `check_creepage_clearance_drift.py`, not
in the required `Cross-Source Consistency Gates` job.** That job (the one
`check_duplicate_predicates.py` lives in) blocks every merge in the repo;
`board-provenance-requirements-gates` is explicitly documented, by the prior
agent who wired the creepage/clearance gate, as NOT in `required_contexts`
"so the red does not wedge merges" while still being "a visible, labelled
honest red." My finding has the identical shape (value is decided, fix is
blocked by an oracle-repin ceremony, not a live safety question needing
real-time resolution) — so I followed that precedent rather than
unilaterally making every PR in a repo with five active sibling agents fail
over a finding nobody can act on this session. This is a judgment call
worth flagging explicitly: **an owner may reasonably decide, once the
coordinated fix lands, to promote both this gate and the creepage/clearance
gate into `required_contexts`.**

Proof the job actually runs on the PR that introduces this gate (not just
after merge to main), using the repo's own checker logic:

```
$ python3 -c "
import sys; sys.path.insert(0, 'scripts')
from check_required_checks import load_manifest, job_should_run
from pathlib import Path
m = load_manifest(Path('.github/required-checks.json'))
changed = ['scripts/check_fact_registry_drift.py',
           'scripts/tests/test_check_fact_registry_drift.py',
           '.github/workflows/python-tests.yml']
print(job_should_run('Board, Provenance & Requirements Gates', changed, m))
"
True
```

`scripts/**` is a `catch_all_paths` entry in `.github/required-checks.json`,
so any PR touching this new script (or its test) triggers the job via the
same `job_should_run` logic the required-checks watcher itself uses —
verified, not asserted by naming. Also confirmed
`check_required_checks.validate_job_conditions` still passes (the
workflow's job `if:` conditions still match the manifest after this edit),
and the workflow YAML still parses.

## 4. What was fixed vs. left as open findings

**Fixed:** nothing required a value edit. Every divergence found either (a)
was already consistent (thermal constants, layer count) or (b) is the
`mains_voltage_v`/`pollution_degree` family, where the correct value is
known but the mechanical fix is blocked by pinned-oracle re-pin ceremony —
correctly a "leave it red" case per the hard rules, not a "cheap fix."

**Registered in `scripts/manifest.yaml`** (`check_fact_registry_drift.py`
entry, alphabetically placed, `disposition: ci-gate`) so the script-manifest
hygiene gate (`check_manifest_gate.py`) accounts for it — verified passing.
Also added the corresponding entry to `scripts/invocation_graph.json`
(minimal, targeted addition only — I deliberately did NOT run
`trace_invocations.py`'s full regeneration, which reflowed ~150 unrelated
manifest entries and touched other scripts' invocation lists; that is a
separate, broader hygiene action outside this task's scope and risked
colliding with concurrent sibling agents' own edits to the same files).

**Open finding, needs an owner** (the coordinated fix described in §2):

1. Update `pcb_spec.yaml` (`mains_voltage_v: 120.0`, `pollution_degree: 3`),
   `design_rules.py`'s `ACMains.voltage_v` (→120.0), and
   `specification_contracts.rs`'s `SafetySpec::new()` defaults (→120.0/3).
2. Re-pin `tests/core/_design_rules_py_oracle.py` and
   `tests/core/_specification_py_oracle.py` per the standing oracle re-pin
   ceremony (exhaustive-divergence evidence, per repo rules — not a agent
   fiat action).
3. Correct `tests/core/test_specification.py::test_safety_spec_defaults`
   and `test_load_pcb_spec_yaml_has_safety` to assert 120.0/3.
4. Re-run `scripts/check_fact_registry_drift.py` — it should go clean; if it
   doesn't, `TestRealRegistryKnownState`'s pins will need a deliberate
   update, documenting exactly what changed.
5. Once clean, an owner may consider promoting `board-provenance-
   requirements-gates`' two drift gates into `required_contexts`.

**Explicitly out of scope, owned elsewhere (not touched):**
- `PhysicsGate._GATE_NETS` / `physics/gate_drive.py` — sibling agent, PR #1310.
- HV-keyword-matcher re-divergence (`duplicate_predicate_registry.py`
  `OPEN_FINDINGS`, PR #1308) — already tracked by the code-duplication
  mechanism; not a value-level fact.
- `pcb/temper.kicad_pcb`, copper regeneration, `_astar_nlayer.py`/
  `pair_clearance.py` re-measurement, LOC-cap/hash-order trunk work — other
  active siblings' territory per coordination notes.
- Parallel implementations / generated-vs-committed files / dead code
  (e.g. `temper-constraints/src/ipc.rs`, the historical "4 IPC
  current-capacity calculators") — the separate SSOT-focused agent's
  artifact/code-duplication territory.

## 5. Status checklist

- [x] Inventory swept (creepage/clearance, thermal, layer-count, OCP,
      mains-voltage/pollution-degree; code-duplication left to the sibling
      agent)
- [x] Authority declared (120V/PD3, cited)
- [x] Gate script built, extending the existing registry-driven pattern
      (`duplicate_predicate_registry.py`'s rationale), not a parallel
      mechanism to the existing drift gates
- [x] Gate wired into a real CI job (`board-provenance-requirements-gates`),
      proven to trigger on the introducing PR via `job_should_run`, not
      continue-on-error'd
- [x] Gate proven non-vacuous: 11 passing tests, both directions
      (mismatch→violation, reconciled→clean), plus real-repo pins
- [x] Cheap unambiguous divergences fixed: none found (all real divergence
      is the pinned-oracle-blocked family above)
- [x] Judgment-call / blocked divergences left as open findings with the
      precise decision needed, left red
