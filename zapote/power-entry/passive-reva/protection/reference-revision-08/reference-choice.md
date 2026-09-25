# Reference revision 08: PFC architecture choice

## Decision for the next simulation revision

Retain the single-phase **UCC28180 CCM** architecture. Use the UCC28180EVM-573 and TIDA-00779 Rev D as wiring and protection references, then model the Temper low-line case explicitly. Do not treat either reference as a scaled 1.8 kW qualification, and do not import a reference efficiency, current rating, magnetics rating, or protection result.

This is a simulation-revision decision, not a hardware-qualified BOM. The existing campaign is already a UCC28180 surrogate; retaining the controller preserves a runnable control boundary and makes each new deviation visible. Moving to UCC28063 would require a new two-phase transition-mode power stage, controller model binding, current-sharing behavior, and a new fault graph before it could answer the same question.

## Target and the low-line constraint

The working product target is 120 VAC, 60 Hz, approximately 1800 W **appliance input**, with a 108–132 VAC study range, a retained 15 A RMS input screen, and a nominal 390 V DC bus. This is not an 1800 W DC-output requirement. At unity power factor, the current screen permits 1620 W at 108 V, 1800 W at 120 V, and 1980 W at 132 V; the separate 1800 W input cap still applies. Nonunity PF reduces the current-limited real-input ceiling. Conversion and auxiliary losses then reduce available DC output, and inverter/coupling losses further reduce pan heat. Therefore 1800 W input cannot be promised at 108 V while retaining a hard 15 A screen.

The prior accepted low-line point was 108 V / 1242.52 W resistive load with 13.412 A RMS in the authored model. It does not establish 1800 W operation, continuous-range behavior, or whole-appliance current. Resolve source/model feedback and clamp discrepancies with focused checks first. A later power sweep must report current margin after explicit auxiliary allocation.

## Comparison

| Question | Retain UCC28180 CCM | Switch to UCC28063 interleaved TM |
|---|---|---|
| Controller and topology | One single-phase CCM boost stage; UCC28180 is the controller already represented by the local surrogate. TI describes an 8-pin average-current CCM controller with programmable 18–250 kHz operation and integrated gate drive. | Two natural-interleaved transition-mode boost stages. TI says both channels are masters synchronized to the same frequency; each stage has its own inductor, switch, diode and sensing path. |
| Relevant TI wiring anchors | EVM-573: 85–265 VAC, 390 V, 360 W, 120 kHz average-current control (guide pp. 1–2, 4, 6). TIDA-00779 Rev D: same UCC28180, 390 V-class CCM stage; guide p. 1 states 3.5 kW and 190–270 VAC full-load range. | PMP10948: two stages, one 750 W and one 550 W, 380 V nominal and 90–264 VAC input (TI PMP10948 tool page). Its “1300 W” is the sum of two stage outputs; it is not evidence for one 1300 W shared-bus module. |
| Low-line evidence | TIDA's published full-load range begins at 190 VAC. Its schematic has a separate 156–265 VAC note, so neither establishes 108 VAC. The 15 A/108 V boundary must be solved for Temper. | PMP10948 reports 95.6% at 120 VAC and 1300 W output, but that is a two-stage 750/550 W design. No 108 VAC, 1800 W, one-bus result is available to inherit. Its reported efficiency is evidence about that board only. |
| Magnetics and current | One choke and one switching path simplify the first low-line experiment. TIDA's 180 µH value was calculated for 3.5 kW at 190 VAC, 45 kHz and a 40% ripple target (guide pp. 5–6); it cannot be copied to a 108 VAC/1800 W design. EVM's 327 µH/360 W values are a second, lower-power anchor (guide p. 6 schematic/BOM). | Two chokes can divide current and reduce per-phase ripple, but each must be sized for its own TM peak current, zero-current detection and thermal envelope. PMP10948's split outputs and magnetics are not a single-bus 1800 W template. |
| Control/model availability | Existing UCC28180 surrogate, local fixtures, and reference deviations are already bound. The next work is parameter and protection correlation, not a controller migration. | TI lists a UCC28063 PSpice transient model (SLUM207) and setup tool (SLUC292), but the local campaign has no validated UCC28063 binding. A model import is not evidence until it reproduces reference waveforms and protection behavior in this simulator. |
| Implementation effort and risk | Lowest next-revision risk. Still requires explicit low-line current budget, nonlinear magnetic/thermal limits, real bias, inrush path, feedback placement, failed-switch interruption, and clamp evidence. | Highest next-revision risk: new two-channel control, phase synchronization/balance, TM frequency variation and ZCD, duplicated fault paths, and a changed inrush/protection graph. A headline power number does not offset these unknowns. |

The choice is therefore about evidence and model closure, not which reference has the larger wattage. UCC28063 remains a credible later architecture if its hard gates below are met.

## What is inherited and what is new

Requirements inherited by either architecture:

- 120 VAC nominal, 108–132 VAC study range, 1800 W appliance-input benchmark, nominal 390 V bus, and the retained 15 A RMS modeled screen.
- Existing normal-operation screens (bus, drift, current and all-trace voltage limits) as authored-model checks only; they are not hardware ratings.
- Protection requirements for gate-independent failed-switch interruption, F2 isolation, local VD and bulk VB energy, detector coverage, clearing time, restart interlock, and clamp characterization.
- The rule that a reference design, efficiency number, or vendor model does not transfer qualification to Temper.

New obligations for this UCC28180 revision:

- Allocate PFC, auxiliary, inverter and coupling losses before choosing a DC-bus power point; show the 108 V/15 A derating explicitly.
- Re-size or parameterize the boost choke from low-line peak current, ripple, saturation and thermal data; do not reuse 180 µH or 327 µH by headline power.
- Bind the control loop to a UCC28180 reference delta matrix (EVM-573 versus TIDA Rev D versus local surrogate), including frequency, shunt/filter, feedback/follower, bias, driver, compensation and inrush connectivity.
- Decide whether the TIDA D2 inrush-bypass path is present. If present, redraw the fault graph and rerun protection analysis; old F2/diode evidence cannot be transferred across that topology change.
- Replace ideal auxiliary rails with an explicit bias/startup budget before making a whole-appliance power claim.

Additional obligations if the project later switches to UCC28063:

- Define one shared 390 V bus and a documented power split; the PMP10948 750 W and 550 W outputs cannot be silently treated as one 1300 W module.
- Demonstrate a 108 V current/thermal design under the 15 A screen (or explicitly change the screen) at the allocated PFC input power.
- Bind and regression-test the UCC28063 model, including natural interleaving, ZCD, phase balance, current sense and startup/fault recovery, against TI's published reference waveforms.
- Close per-phase choke, switch, diode, shunt, gate-driver and capacitor stresses, including mismatch and one-phase-failed behavior.
- Extend the protection graph and fault campaign to two independently conducting channels and their shared bus/inrush paths.

## Reconsideration triggers and adoption evidence

Investigate interleaving if the single-phase design cannot meet its low-line
current, ripple, magnetic or thermal budget, or a concrete two-phase comparison
shows a material advantage. Investigation can begin before qualification.
Adopting a replacement as a validated design would require:

1. A TI source or a new measured model demonstrates the intended single shared 390 V bus at the required Temper power; a summed 750 W + 550 W PMP10948 label is insufficient.
2. A low-line budget closes at 108 V with the retained 15 A screen, including auxiliary and downstream losses, or the product requirement is explicitly revised.
3. The UCC28063 transient model is imported and independently checked against TI's 120 VAC reference behavior; efficiency is not copied as a parameter.
4. Per-phase magnetics/current sharing and thermal margins are calculated for the actual 108–132 VAC envelope, including startup and one-phase fault behavior.
5. The two-phase protection and restart graph is implemented and its fault campaign reaches the same evidence standard as the current single-phase path.

The immediate next step is a short UCC28180 feedback fixture and a source-bound
candidate. A new three-voltage campaign follows only after feedback/clamp
fidelity and the intended power allocations are resolved. Neither TI reference
is a qualified Temper design.

## Bounded source notes

- [TI UCC28180 product page](https://www.ti.com/product/UCC28180): controller is described as single-phase CCM, average-current mode, 18–250 kHz programmable, with integrated gate drive; UCC28180EVM-573 is identified as a 360 W, 390 V, 120 kHz board. The local EVM guide is `operating-matrix-07/host/reference-sources-107/sluuat3.pdf`, pp. 1–2, 4, 6, 8–9.
- [TI TIDA-00779 design guide Rev D](https://www.ti.com/lit/pdf/TIDUBE1): p. 1 describes a UCC28180 CCM 3.5 kW appliance PFC and 190–270 VAC full-load range; p. 3 identifies the UCC28180/UCC27524/UCC28881 blocks; pp. 5–6 calculate 180 µH at 45 kHz and 40% ripple; p. 8 describes the onboard bias supply and inrush relay. The retained Rev D schematic is `operating-matrix-07/host/reference-sources-107/tidrka5.pdf`, sheets 1–2.
- [TI PMP10948 page](https://www.ti.com/tool/PMP10948): overview states two UCC28063 PFC stages, 750 W and 550 W, 90–264 VAC, 380 V nominal; it reports 95.6% at 120 VAC/1300 W and 98% at 220 VAC/1300 W. The test report's 120 VAC current/voltage waveform is p. 8 (`TIDUBC5.pdf`).
- [TI UCC28063 product page](https://www.ti.com/product/UCC28063) and [datasheet](https://www.ti.com/lit/ds/symlink/ucc28063.pdf): product page lists interleaved transition mode, >750 W applications and a 300 W universal-input EVM; datasheet Rev C p. 14 describes both channels as synchronized masters and lists ripple cancellation, phase management, inrush-safe current limiting and dual-path OVP. These are controller capabilities, not Temper validation.
