# Protection revision 08: bounded inventory and smallest next candidate

This is a documentation-only recommendation bound to
`5dde29ab3e2f1223c2d33c129ced2cf647238307`. The 133-part source-build-07 /
native-05 construction is rejected and archived; the canonical candidate is
the restored 54-part source described by `protection/IMPLEMENTATION.md`,
`protection/ARCHITECTURE-REDUCTION.md`, and
`protection/REDUCTION-VERIFICATION.md`. No new hardware is selected and no
energized test is authorized.

## Circuit identities

| Artifact | Feedback and protection identity | Status |
|---|---|---|
| Canonical 54-part source `passive-reva/source/power_entry_passive_reva.ato` | UCC28180 VSENSE divider is fed from `hv_plus` (VB). It contains F1 and the NTC bypass relay, but no installed F2 or independent voltage detector. | Restored baseline and only canonical source. |
| Rejected source-build-07/native-05 experiment | Adds the VD/VB protection construction and routes VSENSE from `diode_positive` (VD). | Historical rejected experiment; its compiled evidence is not baseline or hardware evidence. |
| Accepted operating-matrix SPICE | `Rfb1 vb vsense 1meg`, `Rfb2 vsense 0 13k` (VB). | Authored behavioral model. A VD-feedback fixture is a new simulation candidate consistent with the prior ECO direction, not a correction to canonical hardware. |

## Existing protection inventory

| Function | Retained source fact | Model / qualification boundary |
|---|---|---|
| F1 mains fuse | `PfcFuseHolder` MPN `0031.2510` with replaceable `0034.3129` link is in series from AC_L before the CMC. | The accepted SPICE source has resistance and NTC but no fuse time-current, arc, or clearing model. F1 coordination remains open. |
| K1 NTC bypass | `RT33K012` COM/NO shorts the NTC when commanded; it does not disconnect mains. | `Sbypass` models the NTC short. It is not a source-current interruptor. |
| F2 proposal | `INTERFACE-DESIGN.md` retains **Mersen A70QS50-14F + US141/Z331153** as a normally healthy/closed offboard series-fuse candidate between VD and VB. | F2 is not installed in the canonical CAD/BOM and is not a controllable resettable actuator. Clearing, interconnect withstand, and continuity/open-state diagnostics are unqualified. |
| Independent VD/VB observation | Absent from the canonical 54-part board; added only in rejected source-build-07 and proposed future protection work. | `protection.inc` has separate `Bch_vd_raw`/`Bch_vb_raw`; `BYPASS-NEG` intentionally suppresses the aggregate fault. Its 651 V VD excursion is a negative-control result, not evidence for duplicating an unbypassed comparator. |
| Gate protection | Canonical source has VSENSE standby/inhibit behavior. A separate fresh-arm/gate-disable block is a candidate reduction direction, not integrated. | Default-off/reset applies to gate permission and re-arm. It does not open F2 or clear failed-MOS source current. |
| ISENSE clamp | Canonical source maps `BAT54H,115` A to the shunt-side node upstream of the 220 Ω path and K to controller ground. | Accepted SPICE uses `DCLAMP 0 isense BAV23C_ASSUMED_V2` after the 220 Ω path, with opposite negative-clamp orientation. Node, polarity, device, and VF/leakage are unresolved. |

There is no dedicated controlled upstream current interruptor in the canonical
source. F1 is passive protection and K1 is an NTC bypass. Neither provides a
measured failed-MOS clearing time. The source-fed path and F1 coordination
remain missing model coverage and hardware qualification.

## Smallest justified next revision

1. **New simulation candidate: local-VD feedback.** Add an A/B fixture that
   changes only the accepted model's retained 1 MΩ/13 kΩ controller-divider
   source from `vb` to a named local `vd` node. Keep an independent VBOV path,
   retain the existing VB feedback case, and compare both. This candidate is
   aligned with the prior F2-open ECO direction; it does not modify or relabel
   the canonical root source.

2. **Retain F2 as a healthy, normally closed fuse candidate.** Keep the
   VD-to-VB placement and the Mersen/US141 identity from
   `INTERFACE-DESIGN.md`. Do not model F2 as a resettable controlled switch.
   F2 clearing, loop withstand, interconnect, and continuity diagnostics remain
   open design work. The independent VBOV requirement remains when VD and VB
   separate.

3. **Leave failed-MOS source interruption unresolved.** Do not add an ideal
   `SRC_TRIP` switch. A future reduced witness may hold the MOS failed and
   compare source current with F2 healthy/open, while reporting local/bank
   energy. It must not turn an ideal disconnect into a hardware fix or invent
   an F1 clearing time.

## Focused checks (no 650 ms cold start)

### 1. Clamp/source-model fidelity

Use a short diode fixture with the shunt-side node, the 220 Ω path, and both
declared orientations. Drive small positive and negative ISENSE excursions and
record which direction conducts.

Pass criterion: the candidate names one explicit source/model node-polarity
mapping and the SPICE element matches it. This cannot prove low-current VF over
temperature/lot, PCL interaction, surge energy, or production survival.

### 2. Gate reset and deliberate re-arm

Exercise the existing gate-permission candidate with short logic/aux/permit
and fault/reset pulses. Start from invalid rails, inject a fault, then restore
rails without a new arm edge.

Pass criterion: gate permission is low at reset/rail loss; a fault removes
permission; rail return does not create an automatic run edge; a deliberate
new arm is required after qualification. This cannot prove driver delay,
failed-MOS interruption, F2 clearing, or physical restart energy.

### 3. Passive source-fed witness

Use a reduced `Lboost`/`Clocal`/`Cbank` fixture with the MOS channel held on;
compare F2 healthy and F2-open states while recording source current, VD, VB,
and the three stored-energy terms. Insert no ideal source interruptor.

Pass criterion: F2 opening is shown to affect the bank-side path while any
remaining line-fed source current and local-capacitor energy are reported as
unresolved. This cannot prove F1 I²t/arc behavior, clearing time, SOA,
thermal survival, or a hardware protection pass.

## Unresolved qualification

F1 line-fault coordination and clearing, Mersen/US141 F2 clearing and loop
withstand, offboard VD/VB interconnects, local-capacitor discharge, MOS/diode
SOA, capacitor ESR/ESL/ripple, ISENSE clamp node/polarity and VF/leakage, real
gate-driver timing, and any adopted D2 inrush-bypass graph remain open.
Existing detector traces, rejected source-build-07 evidence, and the
BYPASS-NEG negative control do not close those obligations.
