# Revision 20 input provenance and qualification boundary

Date: 2026-09-22. This record answers which Revision 20 stimulus values come from the design, a manufacturer, or only the simulation fixture. It does not select an AUX producer or redefine a system requirement.

## The source path is not frozen

The latest **compiled** 136-component candidate leaves `aux_15v` as an external boundary. Its [Revision 11 contract](../interface-defaults-11/INTERFACE-CONTRACT.md) requires a producer or independent limiter to hold the consuming devices below their 18 V recommended supply maximum, including faults; the [source integration record](../reference-revision-09/source-candidate/README.md) explicitly omits HOT AUX and logic5 producers. This candidate therefore contains no physical source from which a fault impedance or waveform can be calculated.

Other records describe distinct *proposals*. The [interface design](../../INTERFACE-DESIGN.md) proposes a direct Mean Well **IRM-10-15** producer. The older [controller supply experiment](../controller-integration-06/supply/README.md) uses **IRM-10-24 → TPS7A4701 set to 15 V → TPS54202 set to 5 V**. The [2026-09-22 selection review](../../../../../docs/evidence/2026-09-22-power-entry-selection-review/supplies.md) revisits that historical chain and evaluates a downstream cutoff; it does not install either path in Revision 11. The earlier on-board IRM-10-15 source-build is also a separate experiment, not the current compiled candidate.

Mean Well's [IRM-10 data sheet](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF) gives rated voltage/current, ripple, tolerance and protection trigger ranges for its variants. Those rows are not a time-domain guarantee of output peak, rise/fall slew, source impedance, energy or hold duration during a module fault. The earlier [physical source review](../interface-physical-14/aux/report.md) already made this boundary explicit for the 24 V variant. Neither the 15 V variant's protection trigger range nor the 24 V variant's range can be treated as a fault waveform at `AUX_RAW`. A regulator pass-through fault applies only if that regulator path is actually selected.

## Value ledger

| Input or requirement | Provenance | Usable conclusion |
| --- | --- | --- |
| 14.25–15.75 V at consuming AUX pins during RUN | Chosen [interface proposal](../../INTERFACE-DESIGN.md), reinforced by the [Rev 11 contract](../interface-defaults-11/INTERFACE-CONTRACT.md). | Normal operating objective; not measured producer behavior. |
| 14.625 and 15.75 V startup endpoints | Provisional [Rev 15 bench worksheet](../interface-active-15/bench-plan.md). | Legitimate sensitivity endpoints, not guaranteed assembly extrema. |
| 35 V `AUX_RAW` fault | Explicit [Rev 15 engineering assumption](../interface-active-15/clamp/design.md), inherited from the [Rev 14 source review](../interface-physical-14/aux/report.md). | Investigative fault amplitude only; no manufacturer waveform, impedance or duration follows. |
| 0.5 Ω source, 15→35 V in 1 ms, 50 ms hold, 1 ms return | Declared in [Revision 20 `surge-refined.cir`](surge-refined.cir). | Synthetic fixture. The resulting 16.3507 V peak and latch-off apply to this stimulus, not all 35 V faults. |
| 130 Ω load | Declared in [Revision 20 `surge-refined.cir`](surge-refined.cir). It draws about 115 mA at nominal output. | Synthetic resistive stand-in, not the converter's startup or state-dependent load. |
| 114.473684 mA | [Rev 14 load audit](../interface-physical-14/load-audit.md) from historical 75 mA AUX and 75 mA logic5 allocations plus assumed buck efficiency. | Conditional arithmetic, incomplete for added circuits, relay corners and startup. The 130 Ω fixture does not validate it. |
| Buck startup | [TPS54202 data sheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf) states a **typical** 5 ms internal soft start. [Rev 17 review](../interface-integration-17/README.md) identifies the retained enable divider and unresolved load steps. | A typical chip timing value cannot supply the assembled AUX input-current waveform. |
| Output ride-through during a fault | [Rev 19 conclusion](../interface-dynamics-19/README.md) says it has not been established as a product requirement. | The observed latch-off is a modeled loss of AUX. Whether it rejects the architecture depends on a system-level continuity requirement and allowable interruption/restart sequence. |

The [mains surge contract](../../../../../docs/specs/SURGE_CONTRACT.md) gives the generator impedance for an AC-line immunity test. It does **not** specify the effective source impedance at this HOT-referenced 15 V rail after an AC/DC module, regulator or fault emulator; substituting that 2 Ω/12 Ω generator impedance into the AUX fixture would mix different interfaces.

## Evidence needed for the next acceptance run

1. Bind one producer architecture and exact circuit/output network to the same candidate as the clamp. Name the fault under test: module output overvoltage, regulator pass-through, wiring fault or injected laboratory source. These have different available current and duration.
2. For that fault, obtain a guaranteed manufacturer envelope or measured, uncertainty-bounded `AUX_RAW` voltage/current waveform and effective source impedance at the clamp pins. Record rise/fall, hold duration, source current limit/hiccup and starting output charge. A programmable fault source can intentionally cover a wider declared envelope, but the chosen settings must remain labeled as test requirements rather than manufacturer facts.
3. Bind the actual AUX consumers and startup order. Capture the buck input current and output-capacitor charging separately from the physical 15 V capacitance; include relay/PWM enabled and inhibited states, driver switching load, temperature and component tolerance.
4. State whether the driver supply may disappear during a fault, for how long, and what reset/reauthorization sequence is required. The current logical requirement that a fault clears RUN does not by itself specify AUX ride-through.
5. Rerun the [Revision 19 transient matrix](../interface-dynamics-19/transient-matrix.md) with those conditions and evaluate FET stress against applicable hot SOA. Retain measured pin waveforms and the prototype bench results separately from nominal model outputs.
