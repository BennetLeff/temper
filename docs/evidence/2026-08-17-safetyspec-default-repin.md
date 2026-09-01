<!-- provenance: commit=41eaa9a3d54b15bb9342dc42357a4bde3f3663d2 dirty=UNKNOWN -->
# SafetySpec default correction: 230.0V/PD2 → 120.0V/PD3 (independently validated authority + exhaustive-divergence sweep)

2026-08-17. Board sha256 `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
(unchanged by this document/commit — verified before and after). Main at
session start: `775a7a40e`. This work follows the two oracle re-pins in
`docs/evidence/2026-08-17-oracle-repin-1-via-validation-plane-vias-sort.md`
and `docs/evidence/2026-08-17-oracle-repin-2-graph-oracle-networkx-removal.md`,
which resolved the two entangling drifts blocking this fix from being
attempted at all.

## Scope

This executes the `specification_contracts.rs` portion of
`docs/evidence/2026-08-17-fact-dedup-inventory-and-gate.md`'s 5-step
coordinated-fix plan (§4). **Deliberately narrower than that plan's full
scope**: `pcb_spec.yaml` and `design_rules.py`'s `ACMains.voltage_v` remain
unfixed (see "What remains open" below) — both require additional,
separately-scoped work (a derivation-surface sweep and a second oracle
re-pin, respectively) that the task briefing for this session scoped out
("correct SafetySpec's defaults").

## Independent validation of the authority (120V RMS / PD3), before touching a safety value

Per this task's hard rule ("validate #1311's authority determination
independently before changing a safety value"), re-derived from primary
sources, not taken from the fact-dedup document's word:

- `docs/specs/REQUIREMENTS.md` REQ-SYS-01 (read directly): "AC Input
  Voltage: 120V RMS ±10%" / "US residential mains".
- `elec/src/main.ato:52,56` (read directly): `v_ac_nominal = 120V`;
  `assert v_ac_nominal within 100V to 130V` (NEMA 5-15 tolerance).
- `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md` (read directly): "The Temper
  induction cooker uses a full-wave voltage doubler to convert 120VAC
  mains..."; "Compatible with 120V/15A outlet (no 240V required)".
- `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` (read
  directly): "PD3 governs the as-built board" — the board is forced-air
  vented with no sealed compartment (IEC 60335-2-6 cl. 29.2 Addition).
  Confirmed this decision is actually enforced in code, not just
  documented: `packages/temper-placer/src/temper_placer/core/
  isolation_constants.py`'s `MIN_BARRIER_WIDTH_MM = 12.6` (PD3, not the
  PD2 8.0mm it carried before PR #1229) and `scripts/generate_kicad_dru.py`'s
  `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM`.

Conclusion: independent re-derivation agrees with the fact-dedup document's
determination. 120.0V / PD3 is the correct authoritative value, not a
judgment call.

## Exhaustive-divergence sweep before re-pinning

Per the hard rule ("fix behaviour first, prove every divergence
conservative across an exhaustive sweep, then re-pin with the evidence"):

1. **Repo-wide grep for every bare `SafetySpec()` / `_OracleSafetySpec()`
   construction site** (not trusting the fact-dedup document's claim that
   "no production code constructs SafetySpec() bare" — re-verified myself):

   ```
   $ grep -rn "SafetySpec()" --include="*.py" --include="*.rs" .
   packages/temper-placer/tests/core/test_specification.py           (test_safety_spec_defaults)
   packages/temper-placer/tests/core/test_specification_rust_differential.py  (test_safety_spec_defaults_identical)
   ```

   Exactly two sites, both tests, both already known. The only production
   constructor call, `temper_placer/core/specification.py:50`
   (`SafetySpec(**safety_data)`), only fires when `pcb_spec.yaml`'s
   `safety:` key is present, and **always with explicit values from that
   YAML** — the bare-constructor default is never reached by any
   production code path. Independently confirms the "latent trap, not a
   live divergence" classification.

2. **Grep for every other reference to the stale literal `230.0` / bare
   `pollution_degree == 2` inside the specification test family**, to find
   any additional test relying on the default without directly testing it
   by name — none found; every other `230.0`/`2` occurrence in
   `test_specification.py` / `test_specification_rust_differential.py`
   either (a) tests `pcb_spec.yaml`-loaded values (unaffected — that file
   is untouched) or (b) passes the value **explicitly** as a constructor
   argument (unaffected by a default change).

3. **Live differential run before the fix** (this session's own
   `make venv-isolate` worktree venv):
   `pytest tests/core/test_specification.py tests/core/
   test_specification_rust_differential.py` — 27 tests, all pass at the
   pre-fix 230.0/PD2 default (baseline, confirming nothing else was
   already broken before this change).

## The fix

Both sides moved together in one change (required — they are
differentially compared field-for-field):

- `packages/temper-design-bundle/src/specification_contracts.rs`:
  `SafetySpec::new()`'s `opt_or(py, mains_voltage_v, 230.0_f64)` →
  `120.0_f64`; `opt_or(py, pollution_degree, 2_i64)` → `3_i64`. Doc comment
  added on the struct recording the authority and the "no bare production
  constructor" finding.
- `packages/temper-placer/tests/core/_specification_py_oracle.py`:
  `_OracleSafetySpec`'s dataclass defaults `mains_voltage_v: float = 230.0`
  → `120.0`, `pollution_degree: int = 2` → `3`.
- `scripts/oracle_hashes.json`: re-pinned via `scripts/update_oracle_hashes.py`
  (the repo's own tool, not a hand edit) — exactly one entry changed:
  `_specification_py_oracle.py` `621cd52c8511...` → `d2ecf6a99449...`.

Rebuilt the `temper-design-bundle` pyo3 extension into **this worktree's
own venv** (`make venv-isolate`'d earlier this session; never the shared
repo `.venv`) via `maturin develop --release --manifest-path
packages/temper-design-bundle/Cargo.toml`.

## Verification after the fix

1. `pytest tests/core/test_specification.py tests/core/
   test_specification_rust_differential.py -q` — **before** fixing
   `test_safety_spec_defaults` itself: 26 passed, exactly 1 failed
   (`test_safety_spec_defaults`, with the expected `120.0 != 230.0`
   mismatch) — proving the Rust side and the re-pinned oracle now agree
   with each other at the new value, with **zero** other divergence
   anywhere in the 27-test suite.
2. `scripts/check_oracle_hashes.py` → `167/167 oracle files OK`.
3. `scripts/check_fact_registry_drift.py` → `specification_contracts.rs`
   now reports `OK` for both `mains_voltage_v` and `pollution_degree`
   (previously `DIFF`); `pcb_spec.yaml`/`design_rules.py` still report
   `DIFF` as expected (untouched, out of scope — see below). Gate still
   exits 3 (violation) — correctly, since those two sites remain
   genuinely divergent.
4. `cargo test --lib --no-default-features -p temper-design-bundle` — 51
   passed, unaffected (the `python`-feature-gated `SafetySpec` pyclass
   isn't compiled under `--no-default-features`, so this is a
   no-regression check on the CI-required job, not a test of the change
   itself — the differential pytest suite above is this migration's actual
   correctness oracle per the repo's own architecture).
5. Re-ran everything after also fixing `test_safety_spec_defaults` (see
   the companion commit) — `pytest tests/core/test_specification.py
   tests/core/test_specification_rust_differential.py -q` → 27/27 pass.

## `scripts/check_fact_registry_drift.py` and its tests updated to match

The gate's own registry `notes=` fields, module docstring, and
`scripts/tests/test_check_fact_registry_drift.py`'s
`TestRealRegistryKnownState.test_known_divergent_sites_are_still_divergent`
pin were updated in the same change set: the two
`specification_contracts.rs` entries were removed from the `known_red`
expected-red pin (per that test's own documented instruction — "if this
test ever fails because a site now MATCHES... update this pin, don't just
delete it"), and a new positive-confirmation test
(`test_specification_contracts_rs_now_agrees_with_authority`) was added so
a future regression back toward 230.0/PD2 fails loudly rather than merely
being absent from a list. `scripts/tests/test_check_fact_registry_drift.py`
— 12/12 pass (11 pre-existing + 1 new).

## What remains open (not fixed this session, deliberately)

- **`packages/temper-placer/configs/pcb_spec.yaml`** (`mains_voltage_v:
  230.0`, `pollution_degree: 2`) — not oracle-pinned itself, but its value
  flows into `pipeline/derivation.py`'s `hv_lv_isolation_mm` derivation,
  which `_physics_oracle_py_oracle.py` (a pinned oracle) exercises when no
  explicit spec path is given. Fixing it safely requires running that
  full physics-differential surface, which was out of this session's
  scope (`check_fact_registry_drift.py` and its evidence-doc precursor
  both independently reached the same conclusion — this is not a new
  finding).
- **`packages/temper-placer/src/temper_placer/core/design_rules.py`**'s
  `ACMains.voltage_v=240.0` — differentially pinned against
  `tests/core/_design_rules_py_oracle.py`, a **separate** oracle from the
  one re-pinned here. Fixing it requires its own re-pin ceremony with its
  own exhaustive-divergence evidence (its consumer,
  `temper-drc-rs::partial_discharge.rs`'s `>=60V` filter, is not affected
  behaviorally — both 120 and 240 clear 60V identically — but the pinning
  discipline still requires a dedicated, evidenced act, not a
  drive-by edit riding on this commit).

Both remain correctly reported `DIFF` by `check_fact_registry_drift.py`
(exit 3), which is the intended, honest state — not a regression, not
silently swept under this fix.

`pcb/temper.kicad_pcb` — not touched; sha256 reverified unchanged after
this change (`33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`).
