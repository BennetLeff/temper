# Luna follow-up review — 2026-09-10

This follow-up retains the current BOM and the unapproved datasheet-model
development path. It does not qualify the buck or consume scored harness
slots.

[Regression verification](tests/README.md): 50 Rust tests and 138 Python tests
pass. The production PCB and empty approval registry retain their original
SHA-256 identities. Changes remain local and uncommitted.

## Transient investigation

The [controlled experiments](transient-resolution/README.md) isolate current
command, feedback, switch activity and inductor current. The 2.880473 V dip
does not involve the modeled 4.76 A current limit: the command peaks near
0.946 A. Changing assumed proportional gain and output capacitance changes
the dip. These experiments identify sensitivity to unpublished controller
dynamics; they do not measure the real IC's response.

Host review found that the first pulse-gating variant included the unchanged
parent model. Those runs are explicitly invalidated. The corrected local-model
replay still reaches 2.880473 V, and its load-release peak worsens to
3.761389 V. That variant is not adopted. The host checked all 25 entries in
the retained transient hash manifest against their actual bytes.

The canonical parameter ledger now correctly attributes the existing 20 mA
zero-current threshold to TI section 8.4.4. Its 2 mA smoothing width remains
a numerical assumption. The model bytes are unchanged; earlier copied ledgers
remain historical snapshots.

## Component review

The [revised calculation](margin-resolution/README.md) uses instantaneous
inductor peak current for the capacitor ESR edge, and includes 450 kHz,
4.48 uH and 3.465 V corners. The resulting ideal normal-operation peak is
1.679 A. A rounded 1.70 A screen is useful for normal-operation analysis;
it does not replace the separate 8.35 A hot fault screen.

The 125 mV input-ripple proposal is rejected as a closure criterion because
it has no system-budget basis. The input network must determine how upstream
source impedance affects the waveform; adding `Ipeak * Rsource` to C9 ripple
was an invalid shortcut and has been removed. The [upstream review](margin-resolution/upstream-budget-review.md)
identifies PS1 and the existing measurement procedures. The selected capacitor
values remain sensitivity assumptions, not guaranteed combined-condition
minima.

## Startup protocol

The [startup instrument](startup-protocol-resolution/README.md) demonstrates
why an ideal constant-current sink is unsuitable at a discharged output.
The validator now requires actual load current to follow
`load_a * clamp(VOUT / 0.1 V, 0, 1)` within the existing tolerance. The fixed
0.1 V threshold is fixture semantics, not an IC specification. Above it the
full declared load is required. Rise, overshoot, final voltage, settling and
capture-duration requirements are unchanged.

The corrected contract has tests for intermediate output voltage, full-load
removal, under-load, falsely declared zero load and requirements/constant
agreement. Earlier qualification receipts predate this evaluator and
requirements revision; they remain historical evidence, not current admission.

## Still required for qualification

The [binary collector](full-scenario-readiness/README.md) now admits real
full-resolution files without embedding their data into JSON. A 4,015,356-row
native startup capture passed the corrected protocol in the real evaluator;
the whole packet remains blocked for absent model approval and missing cases.
Host verification measured about 166.4 MiB peak resident memory for that case.
Exact settings-manifest bytes now prevent Python/Rust float-format differences
from causing false identity mismatches.

Independent evidence must establish claim-specific accuracy for the model's
transient response, effective capacitance under the selected conditions and
hot-inductor behavior. A manufacturer model is optional; a datasheet-derived
model still needs independent validation for claims depending on unpublished
compensation. Once those receipts are reviewed and bound to the actual
artifacts, recollect qualification and engineering results, then run preflight,
four development slots and six reserved evaluation slots. No approval entries
have been manufactured and no physical measurements have been claimed.
