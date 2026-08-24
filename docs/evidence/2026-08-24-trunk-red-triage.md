<!-- provenance: commit=03d0f3697e4021f8e803c965c5424c794e767e48 dirty=true (this document plus the CI-wiring change it describes in §3; every measurement below was taken against `origin/main` at this commit or against CI run 32763303080, which is that commit's own Python Tests run) -->

# Trunk triage — `main` has not had a green `Python Tests` run since 2026-08-17

**Date:** 2026-08-24
**Base:** `origin/main` @ `03d0f3697`
**CI run under analysis:** [32763303080](https://github.com/BennetLeff/temper/actions/runs/32763303080) (`Python Tests`, `03d0f3697`)

## Bottom line

**63 completed `Python Tests` runs on `main`, zero successes, back to 2026-08-17.**
That is the headline, and it is more important than any individual failure below.

```
$ gh run list --branch main --workflow=python-tests.yml --limit 100 \
    --json conclusion,status | ...
completed runs sampled: 63
successes: 0
oldest sampled: 2026-08-17T22:06
```

`Required Python Tests` is the only required context on `main`. It aggregates
four jobs that are all red, so **every merge for the past week has required an
owner override.** Branch protection is not protecting anything; it is a
formality that each merge decides to route around.

**I expected these to be stale expectations — the shape the WASM registry gates
turned out to be. That guess was wrong.** Three of the four are real findings
the gates are correctly reporting, two of them on HV/mains safety. What has gone
stale is not the gates. It is the acting-on-them.

| Job | Root cause | Class |
|---|---|---|
| Cross-Source Consistency | `F1` pin 1 is on `ac_l` in atopile; the schematic net of that name has **zero** members | **REAL — HV/mains** |
| Core Tests | tank↔bus enforced clearance **2.0 mm** against a governing **6.3 mm** (PD2) / **10.0 mm** (PD3) creepage; pour containment now empty for all 4 tank refs | **REAL — HV safety + suspected vacuity regression** |
| Board, Provenance & Requirements | `K1`↔`R56` creepage **5.036 mm** across `DC_BUS<->LV_CONTROL` where reinforced is required; 13 steps failing, most cascading from it | **REAL — HV safety** |
| Invariant tests (io/validation/…) | 12 test files (121 tests) referenced by no CI job; 4 stale registry entries | **REAL coverage hole — fixed in this change** |

Only the fourth is safe for an agent to fix, and §3 fixes it. **The three HV
findings are deliberately left untouched** — re-baselining a live safety gate to
get a green tick is the exact failure mode this repo's own DRC-ceiling
convention exists to prevent, and none of them should be closed by anyone who
has not looked at the board.

---

## 1. The three findings I am not touching

### 1.1 Cross-Source — the mains fuse's line pin is unconnected in the schematic

```
ref      pin   net        domain      status
F1       1     ac_l       HV/mains    MISMATCH

('F1', '1') [HV/mains]: atopile net 'ac_l' has 1 members;
  schematic net of that name has 0 members;
  missing_in_schematic=[('F1', '1')] extra_in_schematic=[]
```

`F1` is the mains fuse and `ac_l` is the AC line. The atopile source says pin 1
is on that net; the exported schematic's net of the same name has no members at
all. This is precisely the "looks connected, isn't" class the gate's own header
says it exists to catch, and it is on the mains input of a mains-powered
appliance.

The gate is a hard failure and reports `1 mismatch(es), 0 unverifiable`. It is
not vacuous and it is not ambiguous.

**Run to ground in [`2026-08-24-ac-l-mains-no-connect.md`](./2026-08-24-ac-l-mains-no-connect.md).**
Short version: `scripts/gen_schematics.py` renders every single-node net as a
KiCad `no_connect` marker rather than a label. There are 29 such nets and for 28
of them that is correct; `ac_l` is the exception, because a `no_connect` asserts
a pin is *intentionally* unconnected and `ac_l` is where a panel-mount IEC C20
inlet lands mains Line. The committed schematic therefore carries an X on the
mains fuse's input pin. It is a representation defect, not a board defect — no
copper is wrong — and `oracle_verify()` could never have caught it, because it
skips single-node nets before comparing (`gen_schematics.py:1034-1036`). The fix
and the policy decision it needs are in §4 of that document; I did not apply it
because `kicad-cli` cannot run schematic operations on this machine, so I could
not have verified it.

### 1.2 Core Tests — tank↔bus creepage is enforced at 2.0 mm against a 6.3–10.0 mm requirement

`tests/placer/cp_sat/test_tank_creepage.py`, 7 failures, reproduced locally at
`03d0f3697`:

```
E  tank<->bus enforced clearance (2.0mm) is short of the governing PD3
   functional creepage (10.0mm)
E  assert 2.0 >= 6.3
E  HighVoltageTank.creepage_mm (6.3) is short of PD3 (10.0mm)
E  assert 'PD3' == 'PD2'
E  got 184 pairs -- re-derive against the new board if this is an intentional board change
E  pour containment changed: {'C25': [], 'C26': [], 'C27': [], 'R30': []}
E  pour-bounded shortfall changed: {}
```

Two separable things here, and they should not be conflated:

- **A stated safety shortfall.** Enforced 2.0 mm against 6.3 mm (PD2) and
  10.0 mm (PD3). Whether that is a real inadequacy or a disagreement between
  the enforcement layer and the SSOT figure is exactly the question, and it is
  an owner's question.
- **A suspected vacuity regression — investigated, and NOT vacuity.**
  `pour containment` is now empty for all four tank refs. I flagged that as the
  classic signature of a gate that stopped biting. **It is not**, and
  [`2026-08-24-tank-creepage-pour-containment.md`](./2026-08-24-tank-creepage-pour-containment.md)
  is the correction: every step of the detector runs and resolves correctly, the
  pads are 79–86 mm from the nearest `DC_BUS_RTN` pour, and the pads themselves
  are at **byte-identical coordinates** in the revision that wrote the
  expectation. The *pours* moved — `DC_BUS_RTN` outline area went 74,168 mm² to
  3,103 mm² when the creepage-aware zone generator (#1257) carved them back off
  the HV tank pads. Those two tests are stale against a real improvement and
  should be re-derived. One thing worth keeping came out of it: neither board
  revision stores a computed zone fill, so the old "2.0 mm pour-bounded" figure
  was inferred from *outline* containment rather than measured from copper —
  see that document's §3, and PR #1388 alongside it.

The `184 pairs` failure is the mildest of the seven: the expectation is
hardcoded `4 * 45` and the board now yields `4 * 46`, i.e. one component
entered the HV set. The test's own message says "re-derive against the new
board if this is an intentional board change" — but re-deriving it while the
six assertions above are red would be re-baselining around a safety finding.
It should be re-derived **after** 1.2's substance is settled, not before.

### 1.3 Board/Provenance — K1↔R56 reinforced creepage at 5.036 mm

13 steps fail in this job. They are not 13 defects; most cascade from one
`ClearanceViolation`:

```
ClearanceViolation(
    code='CREEPAGE_INSUFFICIENT',  severity='error',
    boundary='DC_BUS<->LV_CONTROL',  pair_kind='inter',
    ref_a='K1', ref_b='R56',  metric='creepage',
    measured_mm=5.035627474440737,
    insulation_type=<InsulationType.REINFORCED: 'reinforced'>,
    creepage_model='unbroken-surface (exact: geodesic == straight line)',
)
```

**Run to ground in [`2026-08-24-k1-isolation-barrier-triage.md`](./2026-08-24-k1-isolation-barrier-triage.md).**
Short version: the K1 **re-part succeeded** — its intra-footprint coil↔contact
gap is now **17.800 mm**, up from the 8.000 mm a sibling test still pins, and
that test crashes with `KeyError: '13'` because K1 went from an Omron G4A-E
(pads `A1/A2/13/14`) to a Schrack RT33K012 (pads `1/2/3/4`). What remains is
**placement, not part selection**: `K1`↔`R56` at 5.036 mm and `RT1`↔`K1` at
7.000 mm, both under the enforced 8.0 mm. The K1↔R56 geometry was corroborated
independently by a text-only parse of the board (4.549 mm rectangle-edge vs the
checker's 5.036 mm — the expected direction for rounded pad corners), so it is
real geometry rather than an instrument artifact.

The R42 gate-mutation sweep then fails for a *derived* reason worth stating
plainly, because it looks alarming and is not an independent defect:

```
baseline pristine verdict is 'error', manifest expects 'clean'
  -- the canary itself does not correctly classify the unmutated gate
```

That is the mutation harness reporting that its own unmutated baseline is no
longer clean — because the board now carries the violation above. Fix 1.3 and
that step follows. It is not a broken canary.

---

## 2. Why this went a week

Three mechanisms, all visible in the run history:

1. **The aggregator is all-or-nothing.** `Required Python Tests` is the single
   required context and it is red if any of ~10 jobs is red. Once it is red for
   one reason, it costs nothing extra to be red for a second, so reasons
   accumulate and no individual reason has an owner.
2. **Overrides are the merge path.** With the aggregator permanently red, every
   merge is an override, and an override is a judgement about which reds are
   "the usual ones." That judgement gets easier to make each time. I made two of
   them myself today, on #1473 and #1482.
3. **New reds are invisible against a red background.** §3's coverage hole —
   12 files running nowhere — has been reported by a green-when-clean gate for
   an unknown number of days, in a job that was already red for other reasons.
   Nobody was going to notice it.

Point 3 is the one that compounds. A red trunk does not merely delay fixes; it
destroys the signal that would tell you a *new* problem arrived.

---

## 3. What this change fixes: 121 tests that run in no CI job

`tests/validation/test_ci_test_file_registration.py` — the repo's own
anti-vacuity gate for CI name enumeration — reports:

```
New CI-uncovered test file(s) found -- referenced by no workflow job
(by name or by directory sweep): [
  'cli/test_repair_unplaced.py',
  'pcl/test_netclass_constraints_rust_differential.py',
  'requirements/test_iec60335_requirements_rust_differential.py',
  'router_v6/test_astar_nlayer_rust_differential.py',
  'router_v6/test_constraint_model_net_filter.py',
  'router_v6/test_constraints_design_rules_zone_hv_boundary.py',
  'router_v6/test_net_route_result.py',
  'router_v6/test_stage3_auto_batch.py',
  'router_v6/test_stage3_direct_solver.py',
  'router_v6/test_zone_pour_clearance.py',
  'router_v6/test_zone_pour_creepage.py',
  'router_v6/test_zone_pour_rust_wiring.py']
```

That gate exists because this repo has shipped the failure twice before — a
router_v6 group that named a deleted file and therefore collected **zero** tests
while reporting green, and a firmware suite that registered 11 of 20 binaries so
CI ran 70 of 385 assertions.

**Three of the twelve are `*_rust_differential.py`** — the pinned oracles
`AGENTS.md` makes load-bearing for every completed Rust migration ("make Rust
right → prove it against Python with a differential oracle → delete the Python →
keep the oracle"). An oracle that runs nowhere keeps nothing.

**Three more are the zone-pour clearance and creepage suites**, which is a
pointed thing to have unwired given §1.2 and §1.3.

**All 121 tests pass.** Verified locally at `03d0f3697` before wiring anything:

```
121 passed, 6 warnings in 50.09s
```

So this is a pure coverage gain with no failure debt attached. Wired as:

| Destination | Files | Tests | Floor |
|---|---:|---:|---|
| `Run Phase-5 report/explainability/clearance differentials` | 3 (the differentials) | 35 | `--min-tests` 105 → **140** (the job's convention is the exact count; verified it collects exactly 140) |
| `Run invariant tests (router_v6 group 3)` | 8 | 70 | `--min-tests` 500 → **570** (preserves the guard's absolute margin: it was 500 against ~785 non-slow, now 570 against 855) |
| `Run temper-placer tests (core only for CI speed)` | 1 (`cli/test_repair_unplaced.py`) | 16 | no guard on that step |

One more red cleared in passing, because it blocks this very change: the
**Evidence provenance gate** step was failing on
`docs/evidence/2026-08-23-hv-to-iso-creepage-figure-decision.md`, which landed
in #1466 with no `provenance:` line at all. Any PR touching `docs/evidence/` —
including this one — fails that step until it is stamped, so it is stamped here
with `commit=c9ade7db0…` and `dirty=UNKNOWN`, and a note asking #1466's author
to replace it if the real measurement commit differs. It is a one-line fix that
sat unnoticed for a day inside an already-red job, which is §2's third mechanism
in miniature.

Four stale registry entries pruned in the same change, all confirmed against
disk:

- `router_v6/test_astar_nlayer.py` — tracked as uncovered, but group 3 has
  named it for some time. Now actually covered; pruned.
- `manufacturing/test_tolerances.py`, `…_pbt.py`, `…_rust_differential.py` —
  tracked, **deleted from disk** by `eb2261e31` (#1411, "delete 66 orphaned Rust
  pyo3 kernels + 7 paired oracles") with their registry entries left behind.
  Same shape as open PR #1474, which repairs a different consumer of the same
  deletion. #1411 has more than one dangling reference and a sweep for others is
  worth doing.

The first two of those four were masked: the gate reports one assertion's worth
of drift at a time, so pruning the first surfaced the next three.

After the change, `tests/validation/test_ci_test_file_registration.py` is
**9 passed**.

---

## 4. Recommended order

1. **§1.1 first.** A mains-fuse pin with no schematic net is the highest-severity
   item here and probably the cheapest to resolve — it is one net in one file.
2. ~~**§1.2's vacuity half before its shortfall half.**~~ **Done** — it is not a
   vacuity regression; see §1.2. What remains there is the shortfall half (the
   four declared-figure assertions) plus two stale expectations to re-derive.
3. **§1.3** — triaged; see above. The two placement violations remain owner
   calls; the `KeyError` half is a mechanical test re-parameterisation.
4. **Re-derive the `4 * 45` expectation last**, once the board is settled.
5. **Separately, and regardless of the above: split the aggregator, or make it
   fail per-job.** As long as one required context stands for ten jobs, the
   repo cannot distinguish "one known problem" from "a new problem arrived," and
   §2's third mechanism will keep hiding things.

## 5. Reproducing

```bash
# the headline
gh run list --branch main --workflow=python-tests.yml --limit 100 \
  --json conclusion,status | jq '[.[]|select(.status=="completed")
  |select(.conclusion=="success")]|length'          # -> 0

cd packages/temper-placer
uv run pytest tests/placer/cp_sat/test_tank_creepage.py -q --tb=line    # §1.2, 7 failed
uv run pytest tests/validation/test_ci_test_file_registration.py -q     # §3, 9 passed after this change

# §3's 121, before wiring
uv run pytest tests/cli/test_repair_unplaced.py tests/pcl/*rust_differential.py \
  tests/requirements/test_iec60335_requirements_rust_differential.py \
  tests/router_v6/test_astar_nlayer_rust_differential.py \
  tests/router_v6/test_{constraint_model_net_filter,constraints_design_rules_zone_hv_boundary}.py \
  tests/router_v6/test_{net_route_result,stage3_auto_batch,stage3_direct_solver}.py \
  tests/router_v6/test_zone_pour_{clearance,creepage,rust_wiring}.py -q   # -> 121 passed
```

## 6. Sources

- CI run [32763303080](https://github.com/BennetLeff/temper/actions/runs/32763303080) — every failure quoted above.
- `packages/temper-placer/tests/validation/test_ci_test_file_registration.py` — §3's gate, and its docstring's account of the two prior instances.
- `docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md`, `docs/evidence/2026-08-07-full-tree-ci-name-enumeration-triage.md` — the surveys that gate came from.
- `AGENTS.md` — the differential-oracle discipline §3 invokes, and the DRC-ceiling re-measurement convention §Bottom-line invokes.
- PR #1388 (zone fill nondeterminism on the HV bus), PR #1474 (a sibling of §3's #1411 fallout).
