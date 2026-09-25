# Operating-matrix-07 interim engineering report

**Status: interim, source-bound, and not a hardware qualification.** The
campaign establishes behavior at nine accepted modeled normal points and has
completed the DIODE-SHORT capture. SW-SHORT remains indeterminate after an
endpoint abort; BOTH-SHORT capture is complete and its checker is still live; BYPASS-NEG is prepared but
unexecuted. No result here is a fuse, thermal, SOA, safety, production, or
component-survival claim.

## What the normal matrix establishes

The [accepted nine-point matrix](operating-envelope-checkpoint-53.md) applies
the unchanged event-aware screens: finite and nondecreasing rows, endpoint
tolerance, all-row electrical extrema, three-cycle drift, equal-time audits,
and armed/enabled fractions. Modeled points span 108, 120, and 132 VAC with
approximately 359–1,392 W resistive output. The most limiting recorded
margins are 1.588 A to the 15 A input-current screen, 0.000844 drift fraction
to the 0.005 limit, 5.724 V to the settled-bus lower bound, and 10.018 V to
the |VGS| bound; the [margin receipt](normal-screen-margins-89.md) retains
exact values. These are discrete cold-start model screens, not an interpolated
continuous operating envelope or selected-part rating.

The local deck is a single 180 uH boost stage with generic diode/MOS models,
ideal zero-volt branch probes, a 2,240 uF bank, 19.8 uF local VD capacitance,
and an ideal closed F2. `UCC28180_FN` is an authored nominal functional
surrogate. Its `RFREQ=16.2k` parameter corresponds to approximately **129,107
Hz**, not 16.2 kHz. The model therefore remains materially different from TI's
reference architectures.

## Independent case dispositions

| Case | Interim disposition | Defensible reading |
| --- | --- | --- |
| F2-START | Accepted modeled screens | Startup sequence only; no settled-fault or fuse claim. |
| F2-CREST | Accepted modeled screens | Exact scripted ideal-F2 case; no causal interruption or hardware claim. |
| F2-ZERO | Accepted modeled screens | Zero-phase ideal-F2 behavior; bank isolation does not cover every source/local path. |
| SW-SHORT | **Indeterminate** | Solver stopped before endpoint; no protection-gap category was assigned. Gate-low samples were ordinary PWM context, not latch proof. |
| DIODE-SHORT | **Fail: detector event window** | Injection-to-detector delay was 3.121 ms against a 2 ms window. Same-row diagnostics show modeled passive/bank paths after sampled control-off predicates, but no acceptance or physical-current claim. See [failure verdict](../faults/settled-diode-short-64/full-DIODE-SHORT/campaign-verdict-98.json) and [same-row stress review](../faults/coincident-stress-observability-99/parent-result-review-103.md). |
| BOTH-SHORT | **Capture complete; checker live / not dispositioned** | Failed-MOS plus diode terminal graph remains under parent review; no result yet. |
| BYPASS-NEG | **Prepared, unexecuted** | Frozen bypass rejection would occur before waveform evaluation; a future capture needs separate waveform observability. |

The DIODE-SHORT graph shorts `sw` to `vd` through one modeled diode-side
terminal path while Msw remains gate-controlled. The source path
bridge → Lboost → sw, the local VD capacitor, and the VB bank/F2 path remain
distinct. At one sampled row, approximately 78.5 A in Lboost and 77.8 A in
F2/VD-side current coexist with q/en low, a 46 microvolt gate, and essentially
zero MOS channel current. At another, −229.1 A F2 current and +231.2 A channel
current coexist while Lboost is near zero, consistent with a bank-fed modeled
path by sign convention. These are sampled topology observations, not
continuous, causal, thermal, or hardware evidence. The −326.5 kA
`Vdboost1sense` extreme is a current through the idealized zero-volt sense and
1 mOhm short network, not a physical diode-die or package current.

For SW-SHORT/BOTH-SHORT, the gate-independent failed MOS branch is source-fed
around F2; bank isolation alone cannot interrupt it. A defensible protection
function therefore needs independent interruption of that branch, defined
actuation/clearing/restart behavior, and explicit accounting for VD/VB stored
energy. This is a functional requirement, not a selected electronic topology.

## Model/reference gap

TI's [PMP10948](https://www.ti.com/tool/PMP10948) is a 1,300 W design using
two interleaved **UCC28063** transition-mode stages, not the same controller as
the local UCC28180 surrogate. TI's [UCC28180EVM-573](https://www.ti.com/tool/UCC28180EVM-573)
is a 360 W, 390 V CCM boost; [TIDA-00779](https://www.ti.com/tool/TIDA-00779)
is a same-controller 3.5 kW CCM design at 190–270 VAC. These references ground
architecture and power context; they do not validate this deck's 108–132 VAC
induction-load behavior, authored compensation, current-sense scaling,
magnetic saturation, thermal paths, EMI, or protection thresholds.

The user clarified that the target is matching the Breville Control Freak.
The [working power target](power-target-105.md) interprets its 120 V / 1800 W
appliance rating as a nominal mains-input benchmark. It is not a requirement
for 1800 W DC output or 1800 W delivered to the pan. DC-bus output must account
for conversion losses and auxiliary consumption; these budgets remain open.
With a retained 15 A RMS input constraint, 108 V permits at most 1620 W real
input even at unity power factor, so low-line derating is still required.
PMP10948 efficiency is not inherited by our design. Ideal auxiliary rails and
a resistive load do not validate whole-appliance consumption or cooking parity.

## Remaining evidence needed

Each remaining case needs its own source/tool hashes, complete endpoint,
healthy prefix, phase, event timing, and electrical receipt. Future protection
work should separately observe source/failed-branch current, VD/VB/F2 current,
MOS channel current, VD/VB voltages, and comparator timing. The local ISENSE
shunt is bridge-side instrumentation and is not a complete bank-discharge
measurement. Hardware selection, DC clearing, arc/restrike, thermal/SOA, and
restart behavior remain open engineering work.

## Material model limits and reproduction

- The [controller-model audit](ucc28180-vendor-model-availability.md) confirms
  TI TINA transient and PSpice average assets exist, but the retained encrypted
  assets do not directly run in this ngspice campaign. Controller correlation
  remains unestablished; the surrogate must stay explicitly labeled.
- The selected [inductor audit](inductor-manufacturer-audit-72/parent-disposition.md)
  bounds the fixed 180 uH model: saturation, temperature and core-loss behavior
  are absent. Nominal or typical vendor numbers are not guaranteed margins.
- The [clamp review](../clamp/limiting-envelope-13/parent-review.json) records
  sensitivity fixtures, not guaranteed low-current forward-voltage behavior
  over temperature and lot. The saved integrated ISENSE case did not exercise
  peak-current-limit operation; it cannot qualify clamp/current-limit coexistence.
- Generic MOS/diode models, nominal capacitors and ideal F2 omit material
  parasitics, thermal/SOA, arc and clearing behavior. Physical survival remains
  unqualified.

The [historical reproducibility index](reproducibility-index-87.json) records
older source/checker/archive identities. New evidence is bound by the linked
case verdict, parent stress review and their recorded SHA-256 hashes. This
interim report is not yet a final complete campaign index; BOTH/BYPASS need
terminal disposition and incorporation. Reproduction must retain failed raw
traces, legacy timestamp rejections and case-specific event-aware audits.
