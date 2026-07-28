# PLL defaults fixed, resonant-frequency constant reconciled, range gate added

provenance: commit=63415d32adbd48f4907cbe3f1f37728a02fd3c9c dirty=false

**Date:** 2026-07-28
**Base:** `8838d524` (`docs/methodology-loop-discipline`), work done on branch
`fix/pll-defaults-and-range-gate` in an isolated worktree.
**Source docs read first, per the task:**
`docs/evidence/2026-07-28-pll-ratio-tracking-check.md`,
`docs/evidence/2026-07-27-inductance-range-sweep.md`,
`docs/evidence/2026-07-27-zvs-operating-point.md`.

## Summary

Four parts, all completed:

1. `PLL_DEFAULT_FREQ_HZ` (`firmware/components/control/pll_control.h:24`)
   fixed 35000 -> 47000, matching `elec/src/main.ato:91`'s `f_switching =
   47kHz`.
2. `DEFAULT_RESONANT_FREQ` (`pll_control.c:51`) reconciled from a stale
   `35800.0f "from RESONANT_TANK_DESIGN"` to `37580.0f`, the **loaded**
   resonant frequency at the project's L=150uH assumption, with the
   loaded-vs-unloaded choice verified against this file's own code (not
   asserted from the task's framing) -- see §2.
3. New gate, `scripts/check_pll_range_consistency.py`, cross-checks
   firmware vs. `main.ato` PLL range declarations. Wired into CI
   (`.github/workflows/python-tests.yml`, no `continue-on-error`) and
   `scripts/manifest.yaml`.
4. `main.ato` now declares `f_pll_tracking_min`/`f_pll_tracking_max`
   (30/50kHz, matching the firmware's real capability) with the 20-100kHz
   bound relabeled as an LC-tank theoretical figure, not firmware
   capability. The OPEN HARDWARE QUESTION (30-50kHz is known insufficient
   for the ratio-tracking ZVS mitigation, which needs 35.7-83.0kHz) is
   recorded prominently at the declaration site and repeated below.

**Falsifier (task Part 4), stated up front:** *"These constants can be
brought into agreement truthfully, by making the declaration match the
firmware's real capability. If instead agreement can only be reached by
widening the firmware to an unvalidated range, then the gate should FAIL
on the current tree and that failure is the deliverable."*

**Result: the falsifier does NOT fire.** Agreement was reached truthfully
-- `main.ato`'s declaration was lowered to 30-50kHz to match
`pll_control.h`'s real, already-shipped `PLL_MIN_FREQ_HZ`/
`PLL_MAX_FREQ_HZ`, not by raising the firmware toward the 83-100kHz the
ratio-tracking mitigation would need. `PLL_MAX_FREQ_HZ` was not touched.
The gate passes honestly (`0` exit), and the still-open question --
whether the firmware's real 30-50kHz range is *sufficient* for the
ratio-tracking mitigation -- is answered "no, known insufficient" and
recorded as an explicit human decision, not swept into a passing gate.

---

## Part 1 -- `PLL_DEFAULT_FREQ_HZ` 35000 -> 47000

Unambiguous, per the task and per
`docs/evidence/2026-07-27-zvs-operating-point.md`: at corrected coupling
K=0.79, 35kHz loses 100.7% of ZVS margin (full hard switching of the 1200V
IGBT half-bridge) for cast_iron/stainless. `main.ato` moved to 47kHz for
exactly this reason; the firmware was never updated. Changed at
`pll_control.h:24` (now documented inline with the full citation chain).
Used at `pll_control.c:60` (struct initializer), `:123` (`pll_init`),
`:353`/`:360` (`pll_reset`) -- all via the macro, no other literal
`35000`s existed in production firmware code.

## Part 2 -- `DEFAULT_RESONANT_FREQ` reconciled: LOADED, 37580.0f

**Decision: LOADED resonant frequency, 37580.0f Hz**, at the project's
L=150uH tank assumption, K=0.79 pan coupling. Source:
`docs/evidence/2026-07-27-inductance-range-sweep.md` §2.1 (L=150 row,
`f_res,loaded = 37.58kHz`), cross-checked by
`docs/evidence/2026-07-27-zvs-operating-point.md` ("loaded (~1.6x) ~
38kHz" at the same L).

**Why LOADED, verified against the code (not asserted from the task's
framing):** `pll_control.c`'s own `pll_is_frequency_safe()` uses an
*asymmetric* safety window around `resonant_freq` -- `FREQ_MARGIN_LOW_HZ
= 5000` below, `FREQ_MARGIN_HIGH_HZ = 10000` above -- with the comments
"Below resonance limit" / "Above resonance limit (allows inductive
margin)". An asymmetric margin only makes physical sense if `resonant_freq`
is the frequency the converter is expected to run **above** (this file's
own docstring: "We control t_zcd directly ... to ensure ZVS", i.e.
above-resonance/inductive-region operation). Checking the corrected
default operating point (47000Hz) against each candidate:

| Candidate | Value | 47000Hz offset | Fits `[res-5k, res+10k]`? |
|---|---|---|---|
| UNLOADED (L=150uH) | 23700Hz | +23300Hz | No -- blows through the +10kHz ceiling |
| LOADED (L=150uH) | 37580Hz | +9420Hz | Yes -- inside the +10kHz ceiling, 580Hz of headroom |

Only the loaded reading is consistent with the safety-bounds code that
already existed before this change. This is the check the task asked for
("verify that reasoning against the code rather than taking it from me")
and it confirms the loaded interpretation, not merely repeats it.

### A real gap this surfaces (not fixed here)

Lock **confirmation** (`pll_control.c:266`, `FREQ_TOLERANCE_HZ = 2000.0f`)
is a *separate*, symmetric, much tighter window on the same
`resonant_freq` field: `|current_freq - resonant_freq| < 2000`. At the
corrected operating point, `current_freq` (47000) sits **9420Hz** above
the corrected `resonant_freq` (37580) -- outside that window. Confirmed
empirically (`firmware/test/test_pll_only`, host build): swapping only the
two constants, with no other change, took the suite from 23/23 passing to
8/23 failing, 6 of which were every test that first drives the loop to
lock (`test_pll_locks_at_target_phase` and everything downstream of it).

Grep confirms `pll_set_resonant_frequency()` has no non-test caller
anywhere in this firmware (matching
`docs/evidence/2026-07-28-pll-ratio-tracking-check.md` §6's finding that
`pll_init()` also has none) -- so nothing in production ever recalibrates
`resonant_freq` away from this compile-time default either. **As shipped,
`check_pll_safety()` (`firmware/components/safety/safety.c:404`) would
never confirm lock at the corrected default operating point.**

This is a real, pre-existing internal inconsistency between two safety
mechanisms that happened to be masked by the old, physically-wrong
35000/35800 pairing (which sat only 800Hz apart, inside the 2000Hz lock
window, because the old design assumed near-critical, ratio~1.0
operation). Fixing `FREQ_TOLERANCE_HZ` (or changing the lock criterion, or
wiring a real calibration call) is a control-loop tuning decision left to
a human -- explicitly **not** made here, for the same reason
`PLL_MAX_FREQ_HZ` was not silently widened: retuning a safety-adjacent
constant to make something pass is the exact failure mode this task
exists to prevent. Documented in three places: `pll_control.c`'s
`DEFAULT_RESONANT_FREQ` comment, `firmware/test/test_pll_control.c`'s
`reset_pll()` fixture, and a new test that asserts the gap explicitly
(`test_pll_never_locks_at_uncalibrated_defaults`) so it is a tracked,
visible CI fact rather than a silent surprise.

**Firmware test suite, hand-verified (host build, `firmware/test/
CMakeLists.txt`'s `test_pll_only` target; `ctest`/CI does not currently
build this specific target -- see UNVERIFIED):**

| State | Result |
|---|---|
| Baseline (35000/35800, pre-fix) | 23/23 PASS |
| Raw constant swap only (47000/37580, no test changes) | 8/23 FAIL (2 literal-35000 assertions, 6 lock-dependent) |
| Full fix (constants + calibrated `reset_pll()` + new gap test) | 24/24 PASS |

All three states reproduced by hand via `cmake --build ... --target
test_pll_only && ./test_pll_only`, without `git stash` (constants edited
and reverted in place across three separate build directories).

---

## Part 3 -- `scripts/check_pll_range_consistency.py`

Follows the conventions of `check_stale_extensions.py`,
`check_net_classification.py`, `check_undeclared_imports.py`: exit
0/3/5, denominator reporting on every run, "discovered nothing to parse"
is a hard GATE ERROR (exit 5), never a vacuous pass.

**Parses:** `pll_control.h`'s `PLL_MIN_FREQ_HZ`/`PLL_MAX_FREQ_HZ`/
`PLL_DEFAULT_FREQ_HZ` (targeted per-name regex); `main.ato`'s
`f_switching`/`f_pll_tracking_min`/`f_pll_tracking_max` (targeted
per-name regex, normalizing Hz/kHz/MHz).

**Four checks, all required:**
1. declared `f_pll_tracking_min` == firmware `PLL_MIN_FREQ_HZ`
2. declared `f_pll_tracking_max` == firmware `PLL_MAX_FREQ_HZ`
3. `f_switching` falls inside `[PLL_MIN_FREQ_HZ, PLL_MAX_FREQ_HZ]`
4. `PLL_DEFAULT_FREQ_HZ` == `f_switching`

**Anti-vacuity:** any of the six named constants missing from its file is
a GATE ERROR (exit 5), not a smaller-but-valid check -- a partial
discovery is exactly how `main.ato`'s original 20-100kHz assertion kept
passing while checking nothing real.

**Fail-before/pass-after, verified against the real repo (not a stash):**

```
$ git show 8838d524:firmware/components/control/pll_control.h > /tmp/x/firmware/.../pll_control.h
$ git show 8838d524:elec/src/main.ato > /tmp/x/elec/src/main.ato
$ uv run --no-sync python scripts/check_pll_range_consistency.py --repo-root /tmp/x
=== PLL RANGE CONSISTENCY GATE ERROR ===
Reason: required PLL constant(s) not found -- elec/src/main.ato missing
['f_pll_tracking_min', 'f_pll_tracking_max']. Discovered 3/3 firmware
constant(s), 1/3 main.ato declaration(s).
EXIT: 5

$ uv run --no-sync python scripts/check_pll_range_consistency.py   # current tree
PLL range consistency gate -- 3/3 firmware constant(s) discovered, 3/3
main.ato declaration(s) discovered, 4 check(s) performed.
  [OK] declared tracking min matches firmware PLL_MIN_FREQ_HZ
  [OK] declared tracking max matches firmware PLL_MAX_FREQ_HZ
  [OK] f_switching within firmware's achievable range
  [OK] PLL_DEFAULT_FREQ_HZ matches f_switching
PASSED -- 4/4 check(s) agree.
EXIT: 0
```

**Unit tests:** `scripts/tests/test_check_pll_range_consistency.py`, 24
tests, 4 groups (`TestParsing`, `TestChecks`, `TestAntiVacuity`,
`TestHistoricalRegression`). The regression group reconstructs the actual
pre-fix defect shapes (default-frequency mismatch with tracking range
present; tracking range entirely undeclared; the 5x-overstatement shape
specifically) as controlled fixtures and proves the gate would have
caught each, plus a fixture proving the current, real "after" state
passes. All 24 pass (`uv run --no-sync python -m pytest
scripts/tests/test_check_pll_range_consistency.py -v`).

**Scope note, explicit in the module docstring and a dedicated test
(`test_widening_firmware_to_match_unvalidated_range_would_still_be_caught`):**
this gate only checks that firmware and `main.ato` **agree** with each
other from source text. It cannot and does not distinguish "the
declaration was lowered to match a truthful firmware capability" from
"the firmware was silently widened to an unvalidated range" -- both would
pass this specific gate, because both are internally consistent. Whether
`PLL_MAX_FREQ_HZ` is a hardware-validated value is a switching-loss/gate-
drive/snubber question outside what a text-consistency gate can verify;
it is recorded instead as a human-facing OPEN QUESTION at the `main.ato`
declaration site (Part 4) and here.

## Part 4 -- `main.ato` declares the firmware's real range

`elec/src/main.ato:91-138` now:
- keeps the `20kHz to 100kHz` assertion but relabels it "LC tank
  theoretical bound (NOT firmware capability)", with a note pointing at
  the real declaration below;
- adds `f_pll_tracking_min: frequency = 30kHz` /
  `f_pll_tracking_max: frequency = 50kHz`, matching
  `pll_control.h`'s `PLL_MIN_FREQ_HZ`/`PLL_MAX_FREQ_HZ` exactly, with
  `assert f_switching >= f_pll_tracking_min` / `<= f_pll_tracking_max`;
- records, at the declaration site, the OPEN HARDWARE QUESTION below.

**OPEN HARDWARE QUESTION (recorded, not resolved):**
`docs/evidence/2026-07-27-inductance-range-sweep.md` §3 finds the
ratio-tracking ZVS mitigation needs **35.7-83.0kHz** agility across the
plausible L in [50, 250]uH range. Every comparable real coil already
cited in this project's own evidence (Infineon AN235020, Wurth
760308101303, APHO2025) measures **47-50uH** -- the low end of that
range, where the required frequency (83.0kHz) is **highest**. The
firmware's real, declared-truthful 30-50kHz range is therefore **known to
be insufficient** for that mitigation if the real coil lands anywhere
near those references.

**What a human must decide to resolve this** (not decided here, per the
task's explicit instruction): whether the bridge, gate drive, and snubber
network can tolerate switching up to ~83-100kHz. That is a switching-loss
and hardware-validation question this project does not yet have bench
data for. If the answer is yes, `PLL_MAX_FREQ_HZ` can be raised (with
supporting hardware analysis) and this gate will continue to hold the two
files in agreement at the new value. If the answer is no, the
ratio-tracking mitigation is not viable as currently modelled and a
different mitigation (a measured/narrower coil L, a different tank
design, or accepting a bounded ZVS-loss operating region) is needed --
that is also not decided here.

---

## Verification

- New gate + all nine existing gates, exit 0:
  `check_pll_range_consistency` (new), `check_domain_partition`,
  `capacity_budget_gate`, `mpn_fabrication_gate`,
  `check_derived_doc_drift`, `check_copper_net_consistency`,
  `check_rust_drc_presence`, `check_undeclared_imports`,
  `check_stale_extensions`, `check_net_classification`. All ten run
  individually via `uv run --no-sync python scripts/<name>.py`, all exit
  0.
- `make netlist`: builds clean, all assertions PASSED including the four
  new PLL-range assertions (`f_pll_tracking_min < f_pll_tracking_max`,
  `f_switching >= f_pll_tracking_min`, `f_switching <=
  f_pll_tracking_max`) and the pre-existing `f_switching within 20kHz to
  100kHz` / `f_resonant_nominal within 20kHz to 35kHz`.
- `uv run --no-sync python -m pytest elec/validation -q`: 30 passed.
- `check_vacuous_gates.py`: passed (0 violations; the new gate script
  contains no unguarded `all()`).
- `ruff check` on both new files: passed.
- Firmware `test_pll_only`: 24/24 PASS (fail-before/pass-after detailed
  in Part 2).

## UNVERIFIED

- **Whether `test_pll_only` is built by CI at all.**
  `.github/workflows/firmware-tests.yml` only builds/runs
  `test_state_machine_only`, `test_fault_list_only`, and
  `test_sil_fault_injection` -- `test_pll_only` is not currently wired
  into that workflow. This predates this change (checked against
  `8838d524`) and is out of this task's scope (the task asked to wire the
  *range gate* into CI, not to close a pre-existing firmware-CI coverage
  gap); flagged rather than silently left unmentioned. All firmware
  verification above was done by hand, locally.
- **`scripts/check_manifest_gate.py`** fails on the current tree with
  `Script 'check_copper_net_consistency.py' has no manifest entry` --
  confirmed pre-existing at base commit `8838d524` (that script has no
  manifest entry there either, and this gate is not one of the nine named
  in this task). Not touched here; the new
  `check_pll_range_consistency.py` entry this change adds does not
  trigger any new manifest-gate failure.
- **`scripts/check_evidence_provenance.py`** fails on the current tree
  (exit 3) over several *pre-existing* evidence docs missing the
  `provenance: commit=... dirty=...` line, including
  `2026-07-28-pll-ratio-tracking-check.md` and
  `2026-07-27-inductance-range-sweep.md` -- both of the docs this task
  named as required reading. Confirmed pre-existing at `8838d524`. Not
  one of the nine gates named in this task; not touched here beyond
  giving this document itself a correct provenance line.
- **Whether `FREQ_TOLERANCE_HZ` (lock confirmation) should be widened, the
  lock criterion changed to phase-error-only, or a real resonance
  calibration call wired in** -- three candidate fixes for the gap in
  Part 2, none chosen here; a control-loop decision for a human.
- Everything already flagged UNVERIFIED in
  `docs/evidence/2026-07-28-pll-ratio-tracking-check.md` and
  `docs/evidence/2026-07-27-inductance-range-sweep.md` still applies
  unchanged (L=150uH is an estimate not a measurement; K=0.79 is
  extrapolated; the firmware's actual control law is fixed-phase-lag, not
  literal ratio-tracking; whether the PLL is wired into the production
  control loop at all is still not established by this change).
