# C2 handoff constraints

Execution instructions remain in ../../validation-plan/ROUND-4.md. This note records findings discovered while A, C1 and D1 run; it is not a completed loss result.

## Inputs

- C2 checkout: `/Users/bennet/.codex/worktrees/ps-r4-c2/temper`, branch `codex/ps-r4-c2`, frozen base `829ee9debc08ce239bc2dffe0938c4fec2429545`.
- Round-3 local raw restoration: **3327/3327 files verified**. Reverify before execution and run the sim-kit smoke test.
- A and C1 are uncommitted worker outputs until reviewed/integrated. Record their input hashes when copied; do not read changing files mid-aggregation.
- D1 is required for any board-qualified conclusion. Reference-inductance evaluation can proceed first, labeled accordingly.

## Evidence discovered during preparation

1. A event identity is `(ceiling_a, run_id, event_index)`. Power includes both pan and coil resistance. Both ceilings describe actual modeled current; neither is an approved firmware command.
2. A ideal bridge has no physical dead time. Its before/after-500-ns current and slope are useful inputs, but a reversal extrapolation from them is only a screen. A physical floating-node/tank commutation model or an explicit unresolved verdict is needed for the actual reversal question.
3. The strict legacy C1 metric uses absolute die VDS <= 5% of bus for 20 ns. At 10 V it can reject a successfully forward-diode-clamped device because the forward drop exceeds 0.5 V. Preserve that diagnostic, but use C1 signed-voltage/diode-clamp evidence to avoid assigning hard-turn-on Eoss to a forward-clamped device. Do not interpolate through absent or nonmonotonic threshold coverage.
4. C1 body-diode current is separate from external reverse current, which can include displacement current. Diode dwell persists after the incoming command until actual channel takeover. Use C1 measured occupancy/charge and right-censor flags rather than assuming it ends at the driver command.
5. Preliminary 42 A event sample had currents above the old A1 37 A energy-table boundary. C1 supplemental case records already retain the same vendor dissipative turn-off proxy at 40/60 A. A defensible bracketed extension must cite those records; do not silently extrapolate the old table. All these vendor-model heat proxies use the reference temperature, not a guaranteed hot maximum.
6. TI 399/443/487 ns is characterized at 50 kohm. Relative scaling to nominal39/51 kohm is ASSUMED and does not include resistor tolerance.

## Datasheet anchors and accounting

Infineon IPW65R018CFD7 Rev2.0, 2021-04-19 is already stored under task03 round3 sources. Table7 printed page6 gives VSDtyp1.0 V at58.2 A/25C, trr236typ/354max ns and Qrr2.3typ/4.6max uC at400 V,58.2 A,100 A/us. Diagram11 printed page9 contains forward-diode curves at25C/125C. Diagram15 printed page10 contains Eoss(V). Digitized curves must retain point coordinates, source page and interpolation limits.

Use actual waveform di/dt where available; differences from the Qrr test condition remain ASSUMED. Neither 400 V charge nor a 0–400 V effective capacitance is a guaranteed low-bus recovery/Eoss model. Avoid double-counting Eoss, recovery, outgoing dissipative energy or the two bridge legs. Below10 V and other uncovered events remain explicit unknown contributions, never zero masquerading as a complete total. Report covered subtotal, event/energy coverage and conditional sensitivity alongside any modeled total.

C2 evaluates the six modeled timing points for both ceilings, with no R9/R17 change. B, F4/F5 and capacitor current-rating qualification stay out of scope.

## Additional accounting checks from the actual deck

A1's `complementary_leg.cir` has a1nF capacitor directly across each device (`Csnh/Csnl`, `CSNUB=1n`). A hard turn-on calculation containing only MOSFET Eoss and recovery omits discharge of this external capacitance. Report that omission or include an explicitly modeled discharge-energy term with the dissipation allocation stated; do not label the smaller sum a complete transistor-loss estimate.

A binary failure of the20ns ZVS criterion also does not imply that the incoming device still has the full bus voltage at channel onset. The plan's full-bus Eoss hard-event term is a conservative screening convention only where justified. Use saved residual die voltage to report a partial-commutation sensitivity when possible; do not claim a precise loss advantage from binary classification alone. Recovery likewise requires evidence that the outgoing diode carried forward current, rather than applying Qrr to every failed ZVS test unconditionally.
