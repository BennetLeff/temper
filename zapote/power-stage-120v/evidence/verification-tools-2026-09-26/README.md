# Verification-tool review evidence — 2026-09-26

This directory preserves the completed review receipt, its later tool-scoped
resolution, and two manual mutation artifacts. The copied receipts and logs
are **byte-for-byte unchanged**; their original absolute checkout and /tmp
paths are historical provenance. Use the relative links below when reading
this evidence from another checkout.

| Local artifact | SHA-256 | Meaning |
| --- | --- | --- |
| [review.json](review.json) | a9eab8d43b31dc30c267ff264f0e7060b2348988ad7422be39aa3981a640b293 | Completed CE review, run 20260926-130435-18f33ef2; verdict **Not ready** on the pre-fix verification-tool snapshot, with seven findings. |
| [ce-review-resolution-20260926.json](ce-review-resolution-20260926.json) | d8cade8133b18de6db7e91c9826d1ed3a78fcac6275aa94d7e708c48f4e95e80 | Later resolution of the seven findings, scoped to verification tools at the exact file hashes recorded inside the receipt. |
| [barrier-mutation3-drc.json](barrier-mutation3-drc.json) | ad7fa5f9164b7890e7400d06e501610dac404d063e7a5d8dd69f1f4d5cd02762 | KiCad DRC output from a saved-board barrier mutation. It contains 24 hits on the provisional SELV-to-HOT rule: 18 clearance and 6 creepage, among 57 total violations. |
| [angle-mutation.log](angle-mutation.log) | 534e96bebc0f4b791e5cf78697f6a873a0cad7aab5c177cb88ff2c2ae50c9205 | A 45-degree R27 pad mutation rejected by the Rust pad-escape validator with the named orthogonal-orientation error. |

The earlier **Not ready** verdict is not the verdict on the later tool code.
The resolution records each finding's disposition: six resolved in code/tests
and one by live KiCad mutation. Its focused Python run passed 16 tests; the
Rust native-parity, pad-escape and power-barrier suites each passed five
tests. The DRC artifact is a **manual regression proof**, not an automated
full-KiCad test or a clean-board DRC report. The orientation log includes a
KiCad/wx startup assertion before the meaningful pad-escape rejection.

At evidence capture, all 13 code-file SHA-256 values in the resolution
matched the canonical power-stage checkout, and the DRC artifact's SHA-256
matched the value recorded in the resolution. The four copied artifacts also
matched the source files from which they were copied. Those hashes identify
the reviewed tool state; later edits need fresh checks.

The resolution covers **verification tools only**. It does not approve route
coordinates, copper layout, CAD placement, the provisional D5 insulation
basis, fabrication, certification or powered operation. Package insulation,
physical bus overshoot and the remaining hardware tests still need their
own evidence.

[The supplemental review](ce-review-supplement-20260926.json) covers the later
KiCad-tab pose parser correction and the shunt Kelvin connectivity regression.
It verifies that an injected PCB bridge is detected. At that review's snapshot,
the routed board still had the previous ten comparator positions; the pose test
correctly failed. Final board validation must use the regenerated artifact.
Supplement SHA-256: `f26788c32b5b9094a5dac5217d68e00fe13b6e17f8ebace5315a2a5220f1e282`.

## Saved-copper identity guard

The [implementation receipt](copper-identity-implementation.json) and
[independent review](copper-identity-review.json) cover the later guard against
KiCad reassigning authored track/via nets during save. The reviewer found no
actionable defects in the four-file snapshot recorded in that receipt. Five
Rust cases and a real KiCad saved-via mutation passed. Final board receipts
are recorded separately under `native-06/verification/`.
