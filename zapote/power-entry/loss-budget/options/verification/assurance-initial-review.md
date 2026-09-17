# PFC model-assurance review

Reviewed the frozen checkout at `80ae56830` read-only. I did not run Cargo
because the author owns the shared release target. `TEST-EVIDENCE.md` reports
the focused model-assurance and loss-budget test runs; this review is static
and adversarial.

## Blocking findings

1. **P1 — unresolved unknowns and assumptions still produce a numerical PASS.**
   `model_assurance.rs:265-269` derives `numerical_status` only from the
   structural `errors` list. It ignores `AssuranceInput.unknowns`, each
   `UnknownTerm.may_change_outcome`, and `Quantity.evidence_kind`. The
   production adapter supplies ten outcome-changing unknowns and marks gate,
   conduction, and gate-network terms as `Assumption`; nevertheless
   `pfc_loss_budget.rs:865` expects `numerical_verification == Pass`. This
   violates the guard contract that unresolved assumptions/unknowns cannot
   pass. Make the numerical dimension indeterminate (or fail closed) whenever
   an outcome-changing unknown or unverified assumption is present, and add a
   test that mutates/removes the unknown/assumption gate.

2. **P1 — generic fake measured evidence is accepted.**
   `model_assurance.rs:122-155` validates only labels, conditions, stale, and
   optional hash; it does not require a verified importer or distinguish
   `Measured` from `Assumption`/`Derived`. `assess` never inspects
   `Quantity.evidence_kind`, and `EvidenceRef.sha256` is optional. A caller
   can relabel an assumption as `Measured`, set `stale=false`, and obtain a
   numerical PASS without hardware bytes or an importer. Require a concrete
   verified measured-evidence binding (or keep the dimension IND/FAIL), and
   test the fake-label mutation.

3. **P1 — NaN result mutations bypass every production scenario term check.**
   `pfc_loss_budget.rs:164-169` uses only `(actual - expected).abs() > tol`;
   with `actual = NaN` the comparison is false, so a mutated RMS, overlap,
   Eoss, subtotal, or total is accepted by `verify_switching_scenario_binding`.
   Add explicit finite checks for both operands before tolerance arithmetic and
   a NaN mutation test (including a non-nominal scenario, since only the
   nominal scenario feeds assurance terms).

## Coverage gaps

- The 54 scenarios are generated (3 line values × 3 gate biases × 2
  temperatures × 3 transfer-charge points), and `run` calls the binding
  verifier for every scenario. The verifier independently recomputes branch
  moments, conduction, overlap, Eoss, switching/MOSFET/gate subtotals, and
  total. Existing tests exercise wrong RMS and doubled Eoss for one scenario.
  However, `temperature_c`, `gate_bias_v`, `rds_on_ohm`, and
  `current_transfer_charge_c` labels are not bound back to `simulation.inputs`;
  mutating those labels can misrepresent a sensitivity case while all current
  checks pass. Bind these fields to the expected grid/input values.
- The production nominal lookup explicitly selects line 120 V, gate 10 V,
  25 °C, 0.05 Ω, and 10 nC (`pfc_loss_budget.rs:664-673`), so it does not
  accidentally select the first 5 nC scenario.
- The independent fixture is byte-hash pinned and field-pinned to 400 V, 10 A,
  20 ns current transfer, 30 ns Miller, and 100 µJ; the production reference
  compares against the fixture and uses the fixed fixture SHA. The evidence
  label still says `SWITCHING-REVIEW-LESSONS.md` while the SHA is for
  `triangle-anchor.json`; use the actual fixture path/name to avoid a
  source/hash identity mismatch.
- Manufacturer PDF bytes are hash-checked and part IDs are gated before
  constructing loss terms. Runner source/native/board binding and final
  re-hashing are present. Physical applicability and hardware qualification in
  the new assurance report remain IND for structurally valid inputs, as
  required; no verified physical importer exists.
- If the self-consistent-wrong-kernel threat is intended to be covered, pin
  `simulation.model_version` and require `quadrature_checked`; neither is
  asserted by the production binding helper. One independent anchor does not
  detect a kernel that is deliberately wrong away from that point.

## Reviewed file hashes

```
b657723632d3b88a742961ffe2e94632af35273e3bb8d51e70f97cc0c090755a  zapote/packages/zapote-harness/src/model_assurance.rs
a233b1599656ed9918d0c882074098489091d648d38474680551b4df1b80186a  zapote/packages/zapote-harness/src/pfc_loss_budget.rs
5fa21e767a07bcc619058eefd6df2e3c3697eb846a2685daee89d3c887611cff  zapote/packages/zapote-harness/src/runner.rs
e38c6ec686beeb927445354f26096761cd9246a0ea4f32c32c72bc13fa7092ea  zapote/packages/zapote-harness/src/lib.rs
a59dafc68342b497615a6a94eb806e4721b43fb9cb9f8feb62b4b2a90e289a70  zapote/power-entry/loss-budget/options/harness/triangle-anchor.json
69f2e1969580ddd69e840d85d4c7710688c39e931640dfff0af00e6d43a43a9c  zapote/power-entry/loss-budget/options/harness/TEST-EVIDENCE.md
```
