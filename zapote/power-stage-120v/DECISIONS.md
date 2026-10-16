# Placement decisions

This file records owner decisions. The owner approved the proposed D1–D3
and D6 defaults on 2026-09-25, then D5 as a conditional placement basis.
On 2026-09-26 the owner approved a revised 240 × 160 mm, four-layer design
basis. On 2026-09-26 the owner also gave renewed D4 approval for the revised
native-05 placement and native-06 routing, with three conditions (below).

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | **Revised approval 2026-09-26:** 240 × 160 mm. Supersedes the 220 × 160 mm default. Owner reply: “Approve 240 × 160 mm, four layers”. |
| D2 | Heatsink and airflow | **Approved 2026-09-25:** shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. **Airflow decided 2026-10-03** (owner-delegated; see the 2026-10-03 cooling entry below): coil/right inlet → mains/left exhaust through a dedicated sink duct. |
| D3 | Physical stackup | **Revised approval 2026-09-26:** four copper layers. Supersedes the two-layer default. **Fabricator 2026-09-26: JLCPCB (owner).** Stackup is JLCPCB JLC041622-7628: 2 oz on all four layers (70 µm outer, 61 µm inner finished) and a 0.5 mm core between In1 and In2, ordered as nominal 1.6 mm (1.653 mm stackup sum). Designed to JLCPCB's 2 oz rules in native-08/09. Laminate CTI must be confirmed on the order; see FAB-JLCPCB.md. Layer-count approval does not establish inner-plane ampacity. |
| D4 | Review placement before routing | **Renewed conditional approval 2026-09-26 by the owner** (reply: “approve”) for native-05 placement and native-06 routing at `3c07eea57` (routed board SHA-256 `500cdb4b…`). Supersedes the native-04 approval at `341e3c70c`. Conditions: **(1)** before fabrication, widen BUS_P copper where the nominal screen showed only ~6% margin: the local In2 upper branch (demand/screen 0.945) and the western In2 neck (0.945 at 15 A). Routing only, no part moves. *Addressed in native-07* (board `68fb5234…`: local row 0.805, western neck with B.Cu parallel 0.443), and still met on the JLCPCB build native-09 at 61 µm inner copper (board `ccaa3859…`: 0.886 and 0.457); see native-09/verification/README.md; **(2)** at bring-up, measure `ocp_node` during hard switching at full current, and confirm the RC filter margin against false trips and trip delay for the 59 mm paired Kelvin run; **(3)** at bring-up, measure Vgs ringing on all four switches before raising current; the remedy is the gate resistor value, not placement. Routing rules stay as before: local-capacitor returns through R5 current pads 1/4; Kelvin pads 2/3 separate; gate drives paired with their source returns; overlapping bus/return copper; the provisional insulation rules enforced. Not a fabrication or powered-operation release. See PLACEMENT-REVIEW.md. |
| D5 | Insulation basis and barrier parts | **Conditionally approved 2026-09-25 by the owner:** single-point controller-ground–PE functional bond and an 8.0 mm minimum placement target. Use verified laminate group IIIa or better (not IIIb above 50 V). This authorizes provisional barrier placement, not insulation qualification. The source includes the removable 0 Ω functional link R38, placed beside the PE terminal inside the controller island in native-05; covered by the renewed D4 approval. Coilcraft evidence, applicable working-voltage/high-frequency rules and package/module certification scope remain open; increase spacing or change parts if those checks require it. See D5-BASIS.md. |
| D6 | Mains entry and coil exit edges | **Approved 2026-09-25:** mains left, coil right, viewed from the component side with the heatsink at the top. |


**D4 note, 2026-09-27:** the owner approved adding the tank-CT detector, so T1's secondary is terminated on this board (validation-results/06-controller-interface). That is a placement change: 21 parts on a new SELV island lobe by T1, and U13/C47 beside J4. **Renewed D4 approved by the owner on 2026-09-27** (reply: “approve”) for native-10 (placement) and native-11 (routed; electrical board `2fec2924…`, active presentation board `05141028…`), under conditions 1–3. Condition 1 still holds on native-11: the power screens are unchanged. Condition 2 adds a bench item: with the tank running, check CT_ZC and CT_MON for switching-node pickup, and verify the tank-CT trip at the ~55 A design point with injected primary current. Not a fabrication or powered-operation release.

**2026-09-27, native-12/13:** the owner approved two part-number swaps from validation task 02. D4/D5 change from BAT54H to BAS116H (hot leakage). R14/R6 change to 100 Ω and R16/R8 to 1 kΩ, which speeds the PERMIT → DIS path. Poses, footprints, pads, tracks and vias are identical to native-10/11. The zone refill differs by ≤ 0.10 mm². The D4 approval above therefore carries to native-12 (placement) and native-13 (routed; electrical `ce1cf636…`, active presentation board `8056fc95…`).

**2026-09-27, native-14/15:** the owner approved correcting C1/C2 (reply: “yes”) from KEMET R463R410000M1M, whose 27.5 mm pitch didn't fit the 22.5 mm footprint, to R463N410000N1M (22.5 mm pitch; validation task 07 round 2). A new footprint, `temper:KEMET_R463N410000N1M_P22.50_ReviewOnly`, and a maximum-body 3D envelope come with it. Poses, pads, tracks and vias are identical to native-12/13, and so are the placement metrics. The zone refill differs only in vertex order. The courtyard is 0.35 mm wider per side. C1 is now 1.56 mm from RV1. C2's C5/BR1 gaps and heat-zone margin are unchanged. **D4 carry-over to native-14 (placement) and native-15 (routed; electrical `bec1df67…`, active presentation board `a3ac1249…`) approved by the owner on 2026-09-27** (reply: “approved”), under the existing conditions. Not a fabrication or powered-operation release. See native-15/verification/README.md.

**2026-09-28, native-16/17:** the owner approved fixing a fabrication defect found in round-4 review (reply: “do 1-4”). Native-08 to native-15 had 23 PTH pads with no outer land, from a footprint parser that read `(remove_unused_layers no)` as yes. The builder now reads the flag by value. A deliberate policy keeps both outer lands and removes only unconnected inner rings. The JLCPCB check gates outer lands. Five small reroutes followed, including a 3.0 mm (was 3.6 mm) AC-neutral B.Cu run between J1 and F1. **Placement is unchanged** (poses, pads and placement metrics identical to native-14), so the D4 placement approval is unaffected. The pad policy and the neutral narrowing are design changes recorded for the owner's review. See native-17/verification/README.md.

**2026-10-03, native-18:** implements the 2026-10-03 dead-time resistor decision below: R9/R17 → RT0603BRD0749K9L (49.9 kΩ ±0.1 %). Only the two parts’ Value/MPN fields change; poses, footprints, pads and all copper are identical to native-17. Both FEM regions report UNCHANGED. Verification: [native-18/verification/README.md](native-18/verification/README.md). D4 placement-approval carry-over remains the owner’s call; not a fabrication or powered-operation release.

Part 4 §4.0 requires D1–D3 and D6 before deliberate placement. Part 4 §4.2
requires D5 resolution before barrier placement; the conditional basis above now
permits provisional barrier placement, with qualification still open. Section 4.5 requires written
placement approval before Part 5 routing. Native-05/native-06 are now the regenerated placement and routed review
artifacts. Their prototype checks are recorded in PLACEMENT-REVIEW.md. Renewed
D4 is conditionally approved; its condition 1 and physical qualification remain open. No fabrication package is released.

## Prototype source revision, 2026-09-25

The owner approved D3 MRT130KP295CV across BUS_P/HV_RET; two 2.7 µF/1000 V
TDK B32656G0275J000 bulk capacitors; four 100 nF/1000 V TDK
B32652A0104K000 local capacitors (two per leg, BUS_P to HV_RET); retention
of the CDE resonant capacitors; Phoenix 1704004 as the PCB PE branch; two
separate Würth 74650074 M4 coil terminals; smaller C3/C4 pads at 10 mm
pitch; and removable links on **both** rectifier rails. These choices are
implemented in the source revision. J1 is now L/N only (Phoenix 1711725),
J6 is the PE branch, J2/J5 are coil studs, and J7–J10 are link studs.
The external jumpers are deliberately absent from the source net joins.
With both removed, BR1 and J7/J9 still become mains-live if mains is
present; a floating bench source may connect only to J8 BUS_P and J10
HV_RET. Cord PE still bonds directly to the chassis stud, with a separate
branch to J6. The PE branch and C3/C4 footprint changes receive **no**
waiver from D5. See [ASSEMBLY.md](ASSEMBLY.md) and
[PROTOTYPE-POWER-LOOP.md](PROTOTYPE-POWER-LOOP.md).

This is source-level approval. The new 114-part native projection, deliberate
placement, complete copper, enclosure assembly, 20 A link capability at its
operating temperature, and powered qualification are separate checks. D4
is renewed for native-05/native-06 with the conditions above. The lab call and RCA 12A3
teardown remain outstanding.

**2026-10-03, dead-time resistors R9/R17 (implemented in [native-18](native-18/verification/README.md)):** decided under the owner's delegation of round-17 design decisions (reply: “ok keep driving and merging the design decisions”). Validation task 01 found that at the fitted 39 kΩ (≈ 348 ns nominal, ≈ 307–391 ns with tolerance) the turned-off MOSFET's gate exceeds the provisional hot-junction off-gate screen (< 1.9 V) in nominal operation, and 307 ns fails even at 25 °C. **Change R9 and R17 from RC0603FR-0739KL (39 kΩ ±1 %) to RT0603BRD0749K9L (49.9 kΩ ±0.1 %, ±25 ppm/°C), same 0603 footprint and nets** (estimated 396.6–488.0 ns). In simulation on the extracted board matrix, every nominal and overcurrent case then passes the 1.9 V screen with soft switching across that band and at 27/100/150 °C, for about +0.1 W per switch of switching-overlap loss. Value-only: no copper changes, so the board inductance extraction stands. Chosen over the negative-bias remedy (isolated negative supply, ≈ $115–119 and a layout change) because it fixes nominal operation at almost no cost; it does **not** fix the hard turn-on (S4) case, which stays open pending a measured body-diode recovery (double-pulse procedure in task 01 round 17, D-8). A standard ±1 % 49.9 kΩ part is not acceptable (minimum ≈ 389.6 ns). Evidence: `validation-results/01-switching-parasitics/FINDINGS.md` F7, round17 `delegation/out-D12`, `out-D13`, `out-D15`, `d2/results/grid-best-longdt/`. Reversible; not a fabrication or powered-operation release; confirm gate timing at bring-up.

**2026-10-03, bus-voltage sense (task 06, D-11), decided under the owner's delegation (reply: “you decide on those decisions”):** (1) **Accuracy/timing targets:** accept D-11's coarse targets, ±6 % at 170/198 V, ±5 V at zero, ±250 µs zero-cross timing, with 20 ksample/s time-stamped acquisition; the bus reading serves line-synchronous burst timing and telemetry only (power control uses the RTD and under-glass sensors), so a precision target would be unfounded; revisit when controller firmware exists. (2) **ADC allocation:** one unshared ESP32 **ADC1** channel at the controller's receiving connector, fed by D-11's OPA2388 receiver; ADC2 is excluded (Wi-Fi conflict); the controller revision must disconnect the existing `V_BUS_SENSE` driver on GPIO2 (ADC1_CH1) and reuse it. This is a requirement on the future controller board, not a power-board change. (3) **Early-fault policy:** approve the over-range latch at calibrated ADC ≥ 1.210 V: firmware stops PWM and latches a measurement-over-range fault; re-arm needs an explicit action after the reading is back in range; U7 remains the independent hardware OVP at 280 V, unchanged. Evidence: `validation-results/01-switching-parasitics/round17/delegation/out-D11/`, `validation-results/06-controller-interface/`. Not a qualification; D-11's physical-qualification list stands.

**2026-10-03, D4 carry-over for native-18, decided under the same delegation:** the D4 placement approval carries over to native-18 **only if** D-16's verification shows the native-13 pattern: poses, footprints, pads, tracks and vias identical to native-17, zone refill differing by ≤ 0.10 mm² per polygon, and `round17/scripts/leg_region_diff.py` reporting both legs `UNCHANGED`. Conditions 1–3 carry over unchanged. If any copper differs, the carry-over lapses and returns to the owner. Not a fabrication or powered-operation release. **Conditions met 2026-10-03** (PR #1640): the native-17 → native-18 board diff is exactly the R9/R17 Value and MPN properties (8 lines), with zone fills byte-identical, and an independent `leg_region_diff.py` run reports both legs UNCHANGED; the D4 approval therefore carries to native-18 under conditions 1–3.

**2026-10-03, cooling and R5 (task 03, D-18), decided under the owner's delegation (reply: “you decide on those decisions”):** (1) **Enclosure cooling allocation:** reserve a shared PE-bonded forced-air sink with RθSA ≤ 0.15 °C/W at the operating flow, ≥ 20 CFM delivered through the sink, and ≤ 1.0 °C/W per MOSFET interface (insulator + contact); airflow coil/right inlet → mains/left exhaust in a dedicated duct that neither draws coil/under-glass exhaust nor discharges over the controller (closes D2's airflow item). Design inlet temperature 50 °C inside the enclosure. Envelope class: D-18's examples (Wakefield SFA2B1L, 60 × 305 mm, 68 mm tall plus fans; Fischer LA 6 200 12 class); the specific assembly is chosen after the supplier's mounting curve and fan operating point are confirmed. (2) **Insulator:** SIL PAD K-10 (≈ 1.75 °C/W) and SIL PAD 400 are rejected; the interface must demonstrate ≤ 1.0 °C/W per device with the actual clamp pressure (candidate class: thin ceramic/AlN insulator with thermal compound), and keep the D5 insulation basis. (3) **Fan supply:** fans get a dedicated SELV 12 V supply sized for the selected fans (two 11.4 W fans already exceed PS1's 21 W); they are **not** fed from PS1 or J4.1. (4) **R5:** keep the Vishay WSK2512 1 mΩ, 1 W shunt (MPN corrected at integration 2026-10-05 to **WSK25121L000FEA**; native-19 uses its T2.21 mm footprint with larger current pads and a Kelvin pad R5.2 on `ocp_kelvin_p`; rating unchanged) on native-18/19; at the bench, confirm its local ambient ≤ 100 °C at the worst sustained operating point; if it exceeds that, change to a ≥ 2 W 1 mΩ four-terminal part with OCP, parasitic and layout review. Evidence: `validation-results/01-switching-parasitics/round17/delegation/out-D18/`. Conditional budget (switching allowance is a deliberately conservative proxy), not a selected assembly or powered-operation release.

**2026-10-03, controller timing and allocation (D-20 open items O05, O06, O07, O13), decided under the same delegation:** (1) **Controller-inserted gap (O07):** a fixed **200 ns** complementary gap (16 ticks at 12.5 ns), applied by the corrected HAL (D-21) to both transitions of both legs. It sits below the driver's DT-pin minimum (≈ 397 ns on native-18), so the UCC21550's longer-of rule leaves the DT pin in control, while the controller never commands overlapping inputs despite channel and harness skew (requirement R23). The gap is set at initialization only; any change requires both outputs of the leg forced low first; a missing or failed configuration inhibits PWM (R25). (2) **PWM allocation (O05):** both legs on one MCPWM group with a shared timer, one operator per leg, generator pairs complementary, legs 180° apart at 50 % duty; specific GPIOs are chosen in the controller schematic, avoiding strapping pins, and not the legacy GPIO4/5 pair alone (R21). (3) **Frequency-update policy (O06, part):** frequency and phase updates are applied only at the timer-zero event through the shadow registers (no mid-period change); the controller stays on the inductive side of resonance, inhibiting any update that would bring the tank-current zero crossing (CT_ZC) ahead of the switch-node transition, with the numeric margin to come from task 05's envelope and bring-up; burst start/stop always begins and ends with both legs off. (4) **Bus-sense validity (O13):** accept D-11's 150 µs stale deadline, < 100 mV invalid threshold and 1100 mV re-arm level, consistent with the 1.210 V over-range latch. The remaining D-20 items (O01–O04, O08–O12, O14) are controller-hardware, interlock, bench or D-17 matters and stay open with their named owners. Evidence: `validation-results/01-switching-parasitics/round17/delegation/out-D20/`. Requirements on the future controller; no power-board change.

**2026-10-05, mains inlet EMI module (task 07, D-19/D-22), decided under the owner's delegation (reply: “can you drive and decide on what to do”):** reserve in the enclosure a separate **20 A damped DM + CM inlet filter module, 110 × 80 × 50 mm, 8 W heat allowance (≈ $45 material estimate)**, wired after the appliance's upstream fuse/disconnect and before the board's existing filter, kept out of the heatsink exhaust duct. Basis: D-22's model shows conducted-emission margin ≥ 6 dB (worst 9.28 dB AV, 8.28 dB after a 1 dB planning reserve) across all 16 converged operating points with this stage, while the existing board filter alone exceeds the limits (D-19: −24 dB AV at 210 kHz) and a DM-only addition is insufficient. The module and its wiring corridor stay outside both legs' FEM regions (no extraction rerun). Model-based pre-check and enclosure allocation only: not a compliance result and not a release of the filter parts, whose physical, insulation, leakage-current and coupled-system qualification (`round17/delegation/out-D22/METHOD.md`) remain.

**2026-10-05, PWM safe state on firmware failure (D-25), S4 path (D-24) and driver model (D-23), decided under the owner's delegation (reply: “you do all that, you drive”):** (1) **Firmware (amend D-21, PR #1643):** every cleanup/failure path must end by re-asserting each PWM GPIO as a push-pull output driven low with pull-up disabled and pull-down enabled, *after* the MCPWM generators are deleted, because ESP-IDF's generator deletion calls `gpio_reset_pin()`, which disables the output and enables the weak pull-up (D-25, `gpio.c:436–448` at e0991fac). The host SDK stub must model that behaviour so a test fails on the current code. (2) **Controller hardware requirement (adds to D-20 R19/R28):** each PWM line gets an external pull-down ≤ 10 kΩ at the controller, so an undriven pin reads low independent of the ESP32 weak pull-up (≈ 45 kΩ) and the UCC21550 internal pull-down (≥ 50 kΩ only, D-20 J4 table): with those alone a floating input can sit between the 0.8 V and 2.3 V thresholds or above. A PWM initialisation failure must never assert PERMIT; PERMIT/DIS stays the independent hardware off-path. (3) **S4 hard turn-on:** D-24 found every completed model case failing but no physical bound on the body-diode recovery (answer c); the decision therefore needs one synchronised S4 commutation-waveform measurement (off-device die-equivalent VGS < 1.9 V and both die-equivalent VDS ≤ 520 V over D-24's corners), added to the D-8 double-pulse plan; F6 stays in reserve. (4) **Driver model:** TI's only available model (UCC21550B-Q1, SLUM881) did not converge in ngspice and is a proxy for the catalog part (D-23, indeterminate); instead build a datasheet-parametric UCC21550 model (D-26) to bound gate timing in simulation.

**2026-10-05, gate-driver modelling closed for now (D-23, D-26), decided under the owner's delegation:** two in-the-box attempts did not produce a validated UCC21550 model: TI's only published model (UCC21550B-Q1, an automotive proxy) does not converge in ngspice (D-23), and a datasheet-parametric model misses TI's loaded-output fixtures (D-26). D2 verdicts therefore keep the output-resistance approximation with D-2's boost sensitivity as its bound (D-26 reproduced all 36 approximation baselines; its 11 completed real-timing cases kept every S1/S2 verdict). D-26's 3 V gate-crossing gaps (109–229 ns) are a different reference plane from the 391–498 ns command-gap window and appear on the baseline deck as well; they do not contradict F7. Physical gate timing (input, driver output and MOSFET VGS crossings, both legs, both edges) is measured at bring-up per D-8 and D-20 R29.

**2026-10-05, prototype reconciliation (D-27), decided under the owner's delegation (“keep driving forward”):** (1) **Inter-leg modulation (C1):** the 2026-10-03 entry's "legs 180° apart at 50 % duty" is the **only approved operating point** until phase shift is validated. POWER-SECTION.md intends frequency control normally and fixed-frequency phase shift only below the ≈ 150 W frequency-control floor, noting that the lagging leg loses ZVS at deep phase shift; round 17 validated only the 180° point. Phase shift (A/B separation below half a period) is a named low-power mode, gated behind D-28's validation of the lagging leg's commutation current, ZVS, off-gate, losses and the CT phase inhibit. The prototype firmware may keep its phase-control structure but must cap separation at half a period (180°) until then. The 200 ns controller gap, shared timer, timer-zero-only updates and independent PERMIT are unchanged. (2) **Prototype PWM failure state (C2):** the prototype ESP32 firmware (`prototype-closure/round5/firmware/esp32/mcpwm_target.c`) must meet the 2026-10-05 PWM safe-state entry: one final pad-restoration path (push-pull low, pull-up disabled, pull-down enabled) after any resource cleanup, every partial-init/update failure routed through it, GPIO errors propagated, fault-injection tests with ESP-IDF's real reset semantics (D-29); request/PERMIT stays low independently; controller ≤ 10 kΩ PWM pull-downs are part of the hardware contract. (3) **Inlet EMI module clearance:** D-27's nominal fit leaves 0.20 mm between the D-22 module and the heatsink exhaust duct; require ≥ 5 mm air gap or a thermal barrier, and keep the module out of the exhaust path. Mechanical placement change, outside the leg FEM regions. (4) **Inlet module heat and startup (D-27 R42):** the prototype's startup/damper-open peaks exceed D-22's 8 W / 15 A screens; the module rating stays open until a coupled-system check with the real wiring (task 07 follow-up). (5) **Bus sensing:** the prototype controller packet's supervisor channel does not replace the 2026-10-03 bus-sense decisions (OPA2388 receiver, ADC1, 20 ksample/s, 150 µs freshness); those requirements stay open on the controller (D-27 R31–R35, R75).

**2026-10-05, protection closure (task 02 decision B, D-31), decided under the owner's delegation ("instead of delegating, can you just do it"):** (1) **R34 → 10.6 kΩ RT0603BRD07 (±0.1 %, 25 ppm/°C).** The shunt-OCP band moves from 38.44–85.55 A to **49.73–97.98 A**. That meets the ≥ 44 A nuisance-trip minimum at −10 and +85 °C. The 98 A maximum exceeds T1's 88 A only when the CT path has already failed, and D-31 shows fault turn-off up to 330 A keeps die VDS ≤ 350 V. No resistor-only value meets both limits (each 0.1 kΩ step moves the band about 11 A, and the band is about 48 A wide). A narrower band would need a tighter reference or offset and is not pursued now. **Implemented in [native-20](native-20/README.md)** (value-only; copper byte-identical to native-19; both leg regions UNCHANGED). (2) **Stiffen the DIS pull-up, R8/R16 1 kΩ → 330 Ω,** in the same revision (**implemented in native-20**). This saves about 250 ns of the 360.8 ns DIS-rise allocation. Before committing, check that the AO3400A sink current (about 10 mA at 3.465 V) and the VCCI rail load are within limits. (3) **Shoot-through is prevention-only.** No gate-off claim covers it (495 A is reached in about 55 ns). The UCC21550 input interlock, the dead time (F7) and the D-21 firmware safe state are the controls, with FC1 and the catch circuit as containment. (4) **DC-side items stay open as vendor questions:** FC1's DC clearing I²t and arc voltage at ≤ 280 V and the installed L/R; an HS400 hot or repeated pulse rating; LC1D18BD DC make/break. Until they are answered: **firmware allows one loaded precharge proof per cool-down**, and **contactors are never sequenced to break DC fault current** (gates off and fuse or catch first, contacts open last).

**2026-10-05, low-power control: no phase shift; 180° fixed phase plus line-synchronous bursts (F9), decided under the owner's delegation ("make a data driven decision or a decision that leans on what a great senior pcb designer would do"):** phase-shift control is **removed from this power stage's operating envelope**, not left open. Below the frequency-control floor (≈ 150–160 W, POWER-SECTION.md §4), power is set by **line-synchronous bursts of whole 8.33 ms half-cycles at 180°**, started and stopped at bus zero crossings. Why:
1. **Data:** D-28's waveform screens put the nominal ZVS boundary at **120–125° (170 V) and 100–110° (198 V)** for the 2 Ω load. Below that, the lagging leg hard-switches, which is the S4 failure mode (F2): unbounded diode recovery, and it fails without F6. Usable phase shift would therefore only cover a narrow band near 180°, which bursts already cover.
2. **Practice:** commercial induction stages keep every edge soft-switched and reach low power by frequency control plus burst/pulse-density modulation, not deep phase shift. A water bath's thermal time constant is minutes, so 20 s burst windows (sub-watt average resolution at half-cycle granularity) are invisible to the temperature loop.
3. ~~**Burst edges are soft**~~ **(corrected 2026-10-06):** bursts start and stop at **line** zero crossings for a whole-half-cycle current envelope. The switching edges themselves are *not* soft, though: with the bridge idle, the film bus capacitors hold the line peak, so the first edge hard-switches about 170 V (S5, FINDINGS F11; handled by F6). The bus is not a valid zero-cross source (see the 2026-10-06 line zero-cross entry).
4. **It costs nothing in hardware** and removes an unqualifiable mode from validation scope (no periodic-deck convergence campaign for phase sweeps).

Requirements this creates: (a) bursts run at or near the frequency-control floor, not at full power; (b) **the burst period scales with burst power: T ≥ max(2 s, 4.6·d^3.2/0.65^3.2), with a fixed 20 s default** (covers burst floors to 300 W). This replaces the 1 s window first written here: the flicker screen (`validation-results/07-conducted-emi/flicker/`, IEC 61000-3-3 Annex B with the 230 V reference impedance as proxy) shows 1 s windows fail Plt and the method's ≥ 1 s spacing. Minimum periods are 2.5 s at 160 W, 10.3 s at 250 W and 18.5 s at 300 W. Closing evidence: a 120 V-lamp flickermeter run on measured current. (c) The bootstrap hold-up during off-intervals is covered by docs/hardware/BOOTSTRAP_BURST_MODE_ANALYSIS.md and must be re-checked against the final burst timing. **Reversible:** phase shift can be re-qualified later on leg B's own matrix if a product need appears; nothing in hardware precludes it.

**2026-10-05, adopt remedy F6 (negative gate bias) with independently powered bias, in the enclosure re-layout (F2/F6), decided under the owner's delegation:** the next copper revision (the enclosure-driven re-layout) implements **D-12's independently powered −2 V variant**: regulated isolated +15/−6 V modules with a negative LDO to −2 V, 1 nF Cgs, a 1 Ω + **Nexperia PMEG6030EP** discharge branch, an isolated rail-window monitor gating DIS, and the PS2 replacement (D-12 ISOLATED-BIAS.md, about $119 material per board). Why:
1. **Data:** with the selected Schottky's vendor model (`round17/d2/f6_legs.py --diode pmeg`, `results/f6-legs-pmeg/`), F6 passes **all 288 decision cases on both legs at Tj 27/100/150 °C**. That includes all 108 S4 hard-turn-on cases: off-gate ≤ 1.27 V, inside the 1.9 V hot screen, and die VDS ≤ 490 V. Without F6, S4 fails everywhere (F2) and leg B reaches 537 V. The earlier 150 °C aborts were the placeholder diode.
2. **Failure severity:** S4's failure is a false turn-on, i.e. shoot-through on a 650 V bridge, which the protection chain cannot survive (D-31). Avoiding S4 through control alone (stay above resonance) relies on firmware and sensing working through every load transient (pan lift, boil-over). A senior designer adds a hardware margin here.
3. **Burst mode needs a bias that holds through off-time:** the low-power decision above uses bursts with off-intervals of up to about 20 s (20 s default burst period). Bootstrap high-side supplies and D-12's passive Zener/capacitor −2 V network both sag or re-transient at each burst start. Independent bias is up before PWM and stays up, which also retires the bootstrap hold-up question.
4. **Timing:** the enclosure re-layout already forces a new copper revision and FEM rerun of both legs, so F6's layout and FEM cost is absorbed there and not paid twice.

Not chosen: the passive −2 V/−4 V networks (+$5–9) because they don't reproduce the stiff source and collapse in bursts (D-12), and control-only S4 avoidance as the sole barrier. Still open: S4's physical recovery bound (D-24 answer c, one commutation measurement) and bias startup/sequencing qualification on the bench. Cost-down to revisit: one shared low-side module (both low sides reference `leg_ret`) would save one module. **Reversible** until the re-layout is released.

**2026-10-05, addendum to the F6 adoption: burst-start edge and native-20 bring-up, decided under the same delegation:** a new decision case, S5 (first hard turn-on after idle, 0 A, full bus held by the film capacitors), fails the off-gate screens in all 216 unipolar cases and passes all 216 with F6 (FINDINGS F11). Burst-mode low power makes this edge routine: it happens at every burst and every power-up. That is a second, independent reason F6 is required for the product. **For the native-20 prototype (unipolar drive)**, the bench rules are:
(1) the first power-ups run from a **current-limited DC source** (not the mains bus) at ≤ 50 V, rising to 170 V only after the first-edge capture;
(2) the partner's VGS (isolated probe) and bus current are captured at the first edge, in the same session as D-24's S4 commutation measurement;
(3) firmware on native-20 uses **continuous operation** (no burst cycling) until the capture shows the partner gate stays below 3.0 V.

**2026-10-06, BOM review: F6 bias architecture and HOT5 regulator (BOM-REVIEW-2026-10-06.md items 1–3), decided under the owner's delegation (owner asked for a review of waste and non-standard solutions):** (1) **F6's negative bias is built from one SELV-fed transformer driver** (SN6507 / UCC25800 class) on PS1's 15 V, with three reinforced-isolation transformers (HS-A, HS-B, shared LS), +15 V LDO and −2 V Zener/shunt split per secondary. This replaces D-12's four RECOM modules + four negative LDOs + second 21 W AC-DC (≈ $119, ~215 parts, module heat above its 1.7 W characteristic at 80 kHz) and **deletes PS2 and the bootstrap network**. Estimated ≈ $15–25 material. **Gates, any one of which reverses this to D-12's variant:** the PS1 budget closes with the D-20 controller allocation; a catalogue transformer meets the D5 reinforced basis; and F6 still passes all decision and startup cases with the real bias-source impedance (D-33). (2) **HOT5 regulator: a 30 V-input low-Iq LDO (TPS709 class) replaces the MC78L05**, removing ≈ 0.75 mV of the 2.13 mV Kelvin error (+0.8 A on the OCP band minimum). (3) The other BOM-review items stay candidates with stated evidence needs (EMI filter duplication: D-22 model plus D-36 packaging; dual comparators; on-board DC fuse after FC1's DC data). Why: this is the standard architecture for multi-channel isolated gate bias. It removes an entire AC-DC module and most of the added parts, and fixes a thermal over-rating the earlier proposal itself identified.

**2026-10-06, F6 bias architecture REVISED after an independent review (supersedes item (1) of the BOM-review entry above), decided under the owner's delegation:** an independent reviewer (Fable subagent, owner-requested) found that the SELV-fed design **bypasses the thermal-cutoff (TCO) power cut**. PS2 is the only supply on `TCO_L` (`power_stage_120v.ato:377–386`: "an open TCO removes all gate drive, the HOT 5 V rail and the OCP OK signal"), and D-12 had warned "do not move the supply to PS1". Moving the bias to PS1 would also add three reinforced SELV↔HOT barriers. Those transformers' capacitance would couple the switch nodes to PE through the R38 functional-earth link, a common-mode path D-22 never modelled. The savings were also overstated: about $39 of D-12's $119 is 44 × 10 µF at quantity-one prices, and roughly 100 of its parts are the rail monitor, which every variant keeps. The real difference is about $35–40. **Decision:**
- **(1) Keep a TCO-switched HOT-side AC-DC on `TCO_L`**, referenced to `leg_ret` and sized in D-33. The low sides take +15 V directly and a −2 V split from it.
- **(2) One transformer driver (SN6507 class) on that HOT-side rail** feeds two high-side transformers needing **functional isolation only** (`sw_a`/`sw_b` to `leg_ret`). Their common-mode current circulates inside the bridge, not through PE, and PS1 carries no gate load.
- **(3) −2 V rail specification**, from the off-bias sensitivity runs (`round17/d2/results/f6-vneg-*`):
  - it must stay **more negative than −1.6 V at the partner's edge** (S4 off-gate rises about 1.25 V per volt lost; at −1 V, 29/144 S4 cases exceed the 1.9 V hot screen);
  - it is regulated by a TLV431-class shunt, not a bare Zener;
  - **≥ 2.2 µF effective local reservoir** at each driver's VSS pins plus 100 nF, in a low-ESL loop (about 417 nC dumped per turn-off, about 0.2 V droop);
  - F6 is re-run with that source model before source freeze.
- **(4) The rail-window monitor stays mandatory.** UCC21550's UVLO does not see a collapsed negative rail.
- **(5) Unchanged:** the bootstrap network goes, and HOT5 gets a low-Iq LDO, with a star return to R5.2.
- **Fallback** if the HOT-side transformer path does not close: the bootstrap high side plus a regulated split, with a firmware low-side pre-charge before each burst. This replaces D-12's modules as the fallback.

**2026-10-06, line zero-cross detector added to native-21; bursts stay disabled until firmware uses it, decided under the owner's delegation (review of D-32, PR #1657):** D-32's burst scheduler takes zero crossings from the DC-bus sense (AMC1311) and faults if the bus exceeds 5 V at a crossing. That cannot work:
- with the bridge idle, the film bus capacitors hold the line peak (about 170 V), so the bus never crosses zero and the next burst never starts;
- at burst power (about 160 W, roughly 90 Ω equivalent load on about 5.8 µF), the bus valley lags the line by roughly 0.5 ms × 64 V/ms ≈ 30 V. This is an estimate, to be confirmed in D-33/bench;
- free-running a phase-locked loop through a 20 s idle is not an option: ±0.02 Hz of grid drift is up to about 2.7 ms against the ±250 µs allocation.

**Decision:**
- **native-21 adds an isolated line zero-cross detector**, the standard cooktop solution: high-value resistor string from L_FILT/N_FILT to an AC-input optocoupler with reinforced insulation (D5), SELV-side pull-up to V3V3, output `LINE_ZC` to the controller.
- **J4 pin:** `LINE_ZC` takes **p16**, one of the four SELV_GND returns, leaving three returns. This must be re-checked against the D-10/D-20 return allocation; if three returns fail it, J4 grows to 2×9.
- **Firmware:** `burst_enabled` must remain false until the scheduler takes crossings from `LINE_ZC`, with the same plausibility checks as D-32 (half-cycle spacing, staleness), and B2 passes. D-32's bus-based check stays as a cross-check only while the bridge is running.

Native-20 (no detector) runs continuous-only, as already ruled.

**2026-10-06, F6 rail qualification by bounding (unblocks D-33, PR #1660), decided under the owner's delegation:** D-33's coupled deck (TI shunt macro plus sub-nH reservoir ESL inside the switching transient) leaves 181/504 cases indeterminate in both solvers. **Every case it completed passed.** Qualification is split instead:
- **(i) Switching bound:** with the rail held at the −1.6 V limit for the whole event, all 504 cases pass (`round17/d2/results/f6-vneg-m1p6*`; worst off-gate 1.741 V vs 1.9 V).
- **(ii) Rail requirement:** the negative rail stays more negative than −1.6 V through every partner-edge window. This is shown with the standalone rail model (convergent) driven by the worst edge-current waveform, at component corners (capacitance −20 %/DC bias, ESR/ESL high, shunt reference and loop tolerance, temperature), and confirmed on the bench by measuring VSS-to-negative-rail at the edge.

D-33 proceeds to source on this basis. The coupled deck is kept as a diagnostic, not as a gate.

**2026-10-06, burst scheduler takes crossings from LINE_ZC only (D-32 follow-up), decided under the owner's delegation:** `burst_scheduler_step` now refuses any crossing record without `from_line_zc`, and the "bus ≤ 5 V at the crossing" rule is removed. That rule would have blocked bursts by design: the idle bus holds the line peak. `hal_bus_crossing.h` documents that adapters may set `from_line_zc` only for the native-21 LINE_ZC (J4.16) pulse centre, never for a VBUS-derived event. Tests cover a charged-bus start via LINE_ZC (allowed) and a non-LINE_ZC crossing (refused). The host suite passes 19/19. `burst_enabled` stays false by default. Still required before enabling: the GPIO-capture glue feeding `line_zc_edge` and calling `line_zc_poll` (the estimator itself is `firmware/components/power/line_zc.c`: pulse-centre, width/half-period qualification, 4-pulse lock, prediction, dropout/glitch unlock; host test `line_zc_tests` shows ≤ 65 µs error with ±50 µs edge jitter), the bench-calibrated centre offset, and bench B2.

**2026-10-06, native-21 packaging in R4 (D-36), decided under the owner's delegation, with the owner's input that enclosure connectors go on the rear wall:** native-20's 240 × 160 board fits nowhere in R4. The fit gate (`validation-plan/enclosure-fit/`) found 0 placements, blocked by the front-panel module, the centre-sensor service corridor and the coil-support legs. **Native-21 takes the front-middle band:**
- an outline of at most 290 × 140 mm;
- the BR1 + FET row compressed to about 106 mm on the board's rear edge, right of the corridor;
- an edge sink under the coil plate (114 × 44 fins × 73 mm), modelling 0.24 °C/W at 20 CFM and 0.21 at 30 CFM, inside D-18's 0.29 limit;
- right-wall inlet and rear-wall exhaust beside the rear mains connector.

The rear band (240 × 150) was rejected: the sink cannot be placed without crossing the corridor or giving up about 50 mm of board depth. Fan ≈ 30 CFM at ≈ 140 Pa and MOSFET interface ≤ 0.7 °C/W. **Reversible:** if the legs or the sensor corridor move, re-run `fit_gate.py --mode scan`.


**2026-10-08, native-21 power loop: keep the placement (FEM leg A first matrix), decided under the owner's delegation:** native-21's HF film row sits 6 mm further from the FETs than native-19's. It made room for F6's gate network (PMEG + 1 Ω + Cgs) directly under each gate pin. The FEM coarse reference shows the cost: the parallel commutation loop goes from 24.9 to 37.6 nH (+51 %), mostly in the path both film capacitors share (M12 +68 %). With F6 at the −1.6 V rail bound, the provisional native-21 matrix passes **252/252** decision and startup cases at 27/100/150 °C, the 1.9 V hot screen included. The worst margins are S4 die VDS 470 V (520 V limit), S2 446 V (585 V) and S5 440 V (`validation-results/01-switching-parasitics/round17/d2/README.md`, native-21 section; FINDINGS M11). **Why:** moving the film row back up would push F6's network off the gate pins, and that network is the gate-loop remedy the board was re-laid out for. The larger power loop costs voltage margin, not a verdict. **Reverses if** native-21's own corrections or fine extraction (remote `a21corr` / `campA21`), or leg B's native-21 matrix, fail a decision case. The first lever then is an SMD C0G bus decoupler bridging the drain/source pins inside the FET row, not a re-placement.

**2026-10-08, JLC via rule at 2 oz and via-in-pad, decided under the owner's delegation:** a verbatim re-read of JLC's capabilities page shows that the 2 oz **0.254 mm** figure is the **PTH annular ring** row (component holes). Vias have their own rule: "Via diameter should be 0.1mm (0.15mm preferred) larger than Via hole size", with no copper-weight dependence. `tools/jlc_dfm_check.py` had applied the PTH figure to vias, so it flagged native-21's 484 signal vias (0.6/0.3, ring 0.15 mm) as a DFM blocker. Upsizing them to 0.72/0.2 left dense blocks unroutable (the LS bias block is at 84 % courtyard area). **Decision:** keep the routed stage-5 copper with 0.6/0.3 vias. The gate now checks PTH ≥ 0.254 mm and vias ≥ 0.15 mm ring (three times JLC's via rule, kept as margin for 2 oz etch), and the native-21 build sets the same limits in KiCad's DRC. Result: PASS (723 vias, 112 PTH pads, minimum track 0.2 mm). **Via-in-pad:** the 44 vias inside SMD pads (left there by the dogbone pass) are ordered **epoxy-filled and capped (POFV)** for every 0.3 mm via, not reworked by hand: flat pads for paste, no solder wicking, one order note (FAB-JLCPCB.md). **Reverses if** JLC's file review applies 0.254 mm to vias. Then the board needs the LS-block re-layout recorded in native-21/FLOORPLAN.md (smaller passives or more area), not a blind via upsize. **Correction, same day:** "no legal spot" overstated it. The dogbone pass only tries straight F stubs ≤ 1.3 mm in 16 directions, and 42 of the 43 in-pad vias do have legal spots within 3 mm. A routed-stub trial (maze stub on F, maze rejoin on the inner layer) moved 15 more. Of the rest, 9 have a track running through the via and 19 sit in the densest blocks with no routable spot in a local box. **Kept as decided anyway:** R5's shunt current pads need their vias in the pad (R5.4 has no room outside it), so filled and capped vias are ordered regardless. Once every 0.3 mm via is filled and capped, a via in a pad is the controlled standard case; moving the others would add stubs and re-verification without electrical or yield gain.

**2026-10-08, native-21 tank current ceiling and the SW_B neck (task 04 round 5), decided under the owner's delegation:** the board's tank paths each ride on one 2 oz layer. After widening SW_B's 16 mm, 4.5 mm section to 8.1–9.3 mm (stage 6), the IPC-2221 20 K width screen passes at the nominal 21.5 A RMS tank current (120 V, 1710 W). The tightest section is SW_A at 7.0 mm: 18.8 K, 22.0 A screen. Task 05's 108 V low-R grid extreme needs **44.7 A RMS**, and this board cannot carry that. Copper rises ≈ 60–72 K. R5 dissipates 2.0 W against its 1 W rating. C21/C22 carry 18.2 A RMS against CDE's 10.3 A at 70 °C. **Decision (interim):** the controller limits tank RMS to **22 A** (the copper screen; C21/C22 would allow ~25 A, R5 31.6 A) and takes the power shortfall on low-R pans at low line. No firmware ceiling exists today, so this is a new controller requirement. **Owner choice outstanding:** keep the ceiling (product derating at the extreme), or require the extreme. The extreme would need about 2× tank-path copper (more layers on both legs) plus R5 and C21/C22 changes: a re-layout, not a patch.

**2026-10-08, two BOM parts that do not exist (LCSC survey), decided under the owner's delegation:** (1) R83/R101/R116 `RT0603BRD077K62L`: 7.62 kΩ is not an E192 value, and no 0.1 % part exists from any maker. They become **RT0603BRD077K68L** (7.68 kΩ, 0.1 %, 25 ppm). The three rail monitors' negative-window OV edge moves from −2.198 to −2.206 V (+0.35 %), inside the TL431's ±0.5 % and the LM339's offset, and the F6 −1.6 V qualification is unaffected (that is the other edge). (2) R51/R52/R55/R56 `RC1206FR-070R68L`: Yageo's RC series starts at 1 Ω. They become **RL1206FR-070R68L**, Yageo's low-ohm series: same 0.68 Ω, 1 %, 0.25 W, 1206. Both are value/MPN changes on unchanged footprints, made in `elec/src/f6_parts.ato` / `f6_bias.ato` and `audit.rs`. Source rebuilt with atopile 0.2.69, frozen exports refreshed (verify_source PASS, audit 74/74), board rebuilt with copper unchanged (parity 0). Sourcing record: `validation-results/08-manufacturing-package/native-21/sourcing/`.

**2026-10-08, operating envelope: tank current ceiling, approved by the owner (reply: "do all that", to the recommendation to write the envelope as a requirement):** native-21's operating envelope is **tank current ≤ 22 A RMS**, with output power reduced outside it (low line, low-resistance pans). This replaces the interim ceiling recorded above. Task 05's 108 V low-R grid extreme (44.7 A) is outside the envelope by requirement, not a design case. The binding limit is the tank copper's 20 K width screen (SW_A 7.0 mm: 22.0 A); then C21/C22's catalogue ripple (~25 A tank) and R5's 1 W rating (31.6 A). **New controller requirement:** the frequency/power control holds tank RMS ≤ 22 A in every pan/line case and reports when it is power-limited. OCP (47.5–98 A peak trip band) remains the fault protection, not the envelope limit. **Reverses if** the product must deliver full power into low-R pans at low line; that needs about 2× tank-path copper and a larger shunt and resonant capacitors (a re-layout).

**2026-10-08, stage 8: independent-review fixes, decided under the owner's delegation:** the pre-fab review (`validation-results/08-manufacturing-package/native-21/REVIEW-2026-10-08.md`, triage in `REVIEW-TRIAGE.md`) found 2 BLOCKERs and 14 MAJORs.
- **B1, high-side driver supply:** UCC21550 VDDA–VSSA had no capacitor in the source; the nearest bias-reservoir cap is on sw↔n_h, not p_h↔n_h. Each leg gets **c_hs 100 nF 0603 + c_hs_bulk 10 µF 0805** (C10/C11, C17/C18). The bulk is Murata GRM21BZ71E106KE15L (25 V X7R, LCSC C237493). Its DC-bias capacitance loss at the rail voltage is not credited. The 100 nF is the HF cap, and the 0805 is the largest that fits on the HOT side of the y 46.1 pin row. Pad-to-pin centre distances: 100 nF 4.3 mm, 10 µF 7.9 (leg A) / 8.6 mm (leg B), against 48–53 mm before. They can't go closer: the barrier runs just below the pin row, and OUTA leaves the adjacent pin straight up. The reservoir's 1206 bleed resistor (p_h→sw, no layout sensitivity) gave up that slot. On leg A the stack is planar on F.Cu: LOW-group In1 runs pass within the 3.2 mm HOT-group spacing, so no n_h via fits there. p_h takes a hand-laid column on the right (C10, C11, the bleed resistor), and n_h runs on the left to the reservoir's C50 (`layout/patches21.py` add_stage8). The LS 10 µF 1210 bulks (C9, C16) keep their stage-7 spots by the LS bias block, about 16 mm from VDDB. No free spot is closer: the nearest lay over SW_B's B.Cu tank lane, where vias would cut 3.2 mm holes in tank copper, and the spots over the n_ls pour are ≥ 15.6 mm away and hemmed in by C39's bus_p pin. The HF caps (100 nF C8, C15) are what moved to the VDDB pins. Caps stay ≥ 8.0 mm from the SELV pins (the first try put the 0805 at y 47.1, 7.48 mm, and the barrier gate caught it) and off the four OUT gate lanes. **Correction (stage-8 closure review, N1):** the gate-loop copper was *not* untouched. Rerouting round the new leg A stack lengthened the sw_a link from reservoir C50 to Q2's source from 24.1 to 44.5 mm, which is the return half of the high-side gate loop. Leg A's VSSA return to C10/C11 is also 30 mm, through vias near y 30.7. Both are being reworked (stage 9), and leg A's gate loop will be re-extracted.
- **B2, exposed pads:** 3 × 3 filled vias in each TPS7A4700 pad (U26–U28), 2 × 2 in SN6507 U35, after clearing other nets' inner-layer tracks from under the pad.
- **M3:** low-current THT pads get 0.5 mm × 4 spoke reliefs; the 15–45 A nets stay solid (`layout/pad_reliefs21.py`).
- **M5, barrier margin:** **kept at 8.0 mm**, not re-routed to 8.3. The 8.0 mm floor is the owner-approved provisional distance (D5-BASIS). The certification lab sets the final distance, and etch undercut widens copper gaps rather than narrowing them.
- **M7, J3:** JST B2P-VH (1.26 mm copper gap at line voltage) → **B2P3-VH(LF)(SN)**, the same series with post 2 omitted: 7.92 mm pitch, 5.22 mm gap, 250 V 10 A. Unshrouded, because the shrouded -FB-B's 14.9 × 10.8 mm courtyard doesn't fit between PS2 and F1. Hand-soldered.
- **M8, F1:** the stock footprint's 102071 clips are rated 10 A. F1 moves to the 34.21 × 7.62 mm pattern for **Littelfuse 01220088Z (30 A)**, two per board, which get their own BOM line (`scripts/apply_lcsc.py`). **The fuse itself was undersized:** Littelfuse 326 takes a 25 % continuous derating plus temperature re-rating (≈ 97 % at 50 °C), so 20 A carries ≈ 14.5 A continuous against 14–16.5 A RMS line current. F1 becomes **0326025.MXP (25 A, same body, 400 A @ 250 Vac)**, ≈ 18.2 A continuous; the CMC (20 A), terminal (24 A) and BR1 (25 A) carry the line current [2026-10-13 correction: 24 A was J1's IEC rating; its cULus group-B rating was 15 A and CSA 10 A, so stage 27 (item 29) fits the 30 A UL/CSA MKDS 5/2-9,5], and the branch breaker protects the wiring (`sourcing/F1-J3-PARTS.md`). Source rebuilt (atopile 0.2.69, verify_source PASS, audit 74/74). **Then F1 → Eaton Bussmann MDA-25-R** (same day). 0326025's table gives no 125 Vac breaking figure, only 400 A @ 250 Vac. MDA-25-R breaks **10 kA @ 125 Vac and 1.5 kA @ 250 Vac**, typical melting I²t 734.7 A²s, cULus Recognized E19180. These are Eaton Technical Data 2002 (Nov 2025) pp.1–2, read by the owner in a browser; screenshots are in `sourcing/eaton-browser-2026-10-08/`. Eaton's p.4 derating is ~96 % at 50 °C, so about 18 A continuous with a 25 % margin. It is a BOM-only change in the same clips: the board copper is unchanged, and the BOM is regenerated from the source. It dominates 0326025 at every voltage. **Still open on F1, whichever part:** the prospective fault current at the 127 V high-line corner must stay within 1.5 kA, since no 10 kA figure applies above 125 Vac; plus the Recognized-component and clip acceptance, and clearing coordination with the enclosure's upstream MDA-30-R (melting I²t 734.7 vs 1096.7 A²s).
- **M14, PE branch:** the J6 PE/Y-cap track stays thin. It carries Y-cap leakage only: the cord PE bonds to the chassis directly, and R38 is the single functional bond (D5-BASIS). R38 not sitting near J6 is recorded for the owner.
- **m7, fab note:** **ENIG** finish (0.5 mm HVSSOP, VQFN EPs, capped vias); CTI ≥ 175 V becomes a hard order condition, not a question; JLC order number removed.
- **m10:** T1 (CST3015) gets the SMD attribute.
- **m14:** JLC's 2 oz multilayer rule is 0.15/0.15 mm (re-read verbatim); the tightest copper gap is U35's 0.20 mm pad gap.

**Open (owner):** M6 coil-stud spacing, M10 outline and J4 harness, M11 heatsink HOT↔PE stack.

**2026-10-08, input current ≤ 15 A RMS (owner decision, relayed by the enclosure session as R21 DECISIONS N8 and confirmed here by the owner: "1, and go with (a) firmware estimate"):** the appliance keeps a NEMA 5-15P plug. Total RMS mains current stays ≤ 15 A at every line voltage, with margin for auxiliaries (fan, SELV/gate supplies, EMI losses) and sensing tolerance. Output power reduces at low line. F1 stays 25 A: a 20 A 326 fuse carries only about 14.5 A continuous after Littelfuse's derating. **Open (board side):** native-21 has no line-current measurement. ct_mon is the tank CT, and R5 feeds only the OCP comparator. The limit value depended on the sensing path: (a) a firmware estimate from tank current and the AMC1311 bus voltage, or (b) a hardware line-current sense (a board ECO). **The owner chose (a).**
- **Controller requirement (new, with the 22 A tank ceiling):** the controller regulates the **estimated power-stage line current I_ps,est ≤ 12.4 A RMS** at every line voltage and pan. It reduces output power to stay there and reports when it is power-limited.
- **Margin budget:** I_ps,est ≤ (15 A − I_aux) / (1 + e_est).
  - I_aux = 1.3 A covers both Mean Well IRM-20 modules at full load: 0.6 A typical each at 115 Vac (IRM-20-SPEC 2025-11-21), scaled to 108 V. Adding the two currents linearly overstates their RMS sum.
  - e_est = 10 % is a provisional estimator error.
- **Estimator inputs (no new hardware):**
  - bus voltage from U4 (AMC1311);
  - tank current from the T1 CT (ct_mon);
  - tank-current phase from ct_zc against the gate edges.
  - Inverter power is the square-wave fundamental (2√2/π)·V_bus·I_tank·cos φ, averaged over each half line cycle (the bus is unsmoothed). Input power divides that by a minimum inverter efficiency.
  - I_ps,est = P_in,est / V_line,rms, where V_line comes from the bus peak. PF ≈ 1 for the unsmoothed bus, and the PF error sits inside e_est.
- **Qualification (bench, before the limit is final):** measure true-RMS line current against I_ps,est over 108 / 120 / 132 V and the pan grid. The worst error e_max replaces the 10 %, and the limit is recomputed from the same formula; ±5 % would allow 13.0 A.
- **Consequence:** about 1.49 kW input at 120 V (1.34 kW at 108 V), against the 1.71 kW nominal case. The 15 A plug costs about 13 % of nominal power until the bench tightens e_est.
- **Not done here:** the firmware estimator and limit. No controller code exists for either this or the 22 A ceiling.
- **Correction, same day (firmware):** 12.4 A is the boundary where the conservative inlet bound I_ps·(1 + e_est) + I_aux reaches 15 A. That is the adapter's trip, not its regulation point. `fullbridge_adapter` regulates the reported inlet current at `inlet_target_a` ≤ 13.5 A and trips at 15 A, so the power stage is **held at (13.5 − 1.3)/1.1 = 11.1 A** (provisional), with the trip at 12.45 A. Input is about 1.33 kW at 120 V. Bench qualification of e_est raises the hold: ±5 % gives 11.6 A.
- **Firmware:** `firmware/components/power/input_limits.{c,h}` implements the estimate and the 22 A tank ceiling as pure functions, host-tested (`firmware/test/test_input_limits.c`, 6 tests; suite 21/21). The binding reports `inlet_bound_a` as the adapter's inlet current and min(pan model, `tank_ceiling_w`) as its pan budget, so the adapter is unchanged. Still to do: the controller binding (sampling U4 bus voltage, ct_mon and ct_zc phase), which waits on the controller hardware (enclosure CONTROLLER-ARCHITECTURE).

**2026-10-08, stage 9: closure-review rework of the driver decoupling (B1) and the leg A gate return (N1), decided under the owner's delegation:** the stage-8 closure review (`validation-results/08-manufacturing-package/native-21/REVIEW-TRIAGE.md`) found B1 only partly closed and found N1.
- **B1:** leg A's VDDA cap returned to VSSA through a 30 mm, two-via path. No n_h via fits under U1: LOW-group In1 runs (n_ls, leg_ret, v15_ls, the OCP Kelvin pair, the bias supplies) fill the HOT band within the 3.2 mm group spacing.
- **N1:** the sw_a link from Q2's source to the reservoir had grown from 24.1 to 44.5 mm.

**Decision:** the UCC21550's output pin sits between its VDD and VSS pins, so each channel gets a stack of 0805s centred on the output.
- **Geometry:** the 0805 pads (1.9 mm apart) land over VDDx / VSSx (2.53 mm). The output leaves its pin as a 0.3 mm neck through the 0.9 mm pad gap, with 0.3 mm clearance each side.
- **Contents:** 100 nF (Yageo CC0805KRX7R9BB104, C49678) and 1 µF (Murata GRM21BR71H105KA12L, C77083) per channel, plus the 10 µF on the high side.
- **Spacing:** the high- and low-side stacks' facing pads are 3.44 mm apart (≥ 3.2 mm).
- **Placement and copper:** `place.py` STACK; `patches21.py` add_stack re-lays the four output polylines unchanged beyond the neck.
- **Result:** every VDD–VSS loop is **2.07–2.2 mm with no vias**, on all four channels (stage 7: low side 24–119 mm through 2–4 vias).
- **N1:** with the bleed resistors back at their stage-7 spots, the sw_a link is again **24.1 mm**, identical to stage 7.

**Gate loops:** against the extracted copper, the only change is the 0.3 mm neck (≈ 7.5 mm long) and the stack beside it. A thin-strip estimate puts it at ≈ 0.9 nH. To bound it, both legs' decision matrices got **+2 nH on both gate-port diagonals** (`round17/d2/compose_stage9_bound.py`). F6 at −1.6 V (PMEG, 27/100/150 °C) still passes **252/252 per leg**: worst off-gate 1.145 V against 1.9 V, worst die VDS 490 V against 520 V. A full re-extraction is not needed for this change. The reviewer's doubt about which conductors the FEM gate ports close through stays with the FEM record.

**Board `e9d1cc4f…`:**
- DRC 0 errors / 0 unconnected / parity 0;
- both barrier gates 0;
- DFM PASS;
- Gerber review 882/882;
- D5 PASS (8.047 / 8.507 mm);
- Kelvin band 47.52–97.98 A;
- body collisions 0 and R4 fit 0 hits (413 solids);
- task 04 tank paths unchanged;
- B3: U26's pad cell 167 / 143 °C (stage 8: 162 / 138; stage 6: 176 / 152; grid-sensitive);
- source verify PASS (355 components), audit 74/74.

**Also fixed:**
- the dead In1 leg_ret stub (N3);
- the nylon legend (N2);
- the board-only planner, which counted its own previous holes and fiducials as copper and so moved every hole on each re-plan. The holes are now frozen at the positions the enclosure adopted while they stay legal.
- The fixing chain at the nylon holes is now a stated insulation requirement (M4).

**Open from the closure review:**
- **M1:** the AMC1311 has no 1 µF on either supply. The reviewer cites its datasheet; to be checked against TI's sheet before an ECO.
- **N6:** the D5 audit and the reviewer measure H4's wall-to-HOT distance differently (0.55 vs 1.20 mm). Both are under 8 mm, and the insulating fixing chain covers either. *Resolved after stage 11:* `d5_audit.py` ignored zone cut-outs and measured from the drill's bounding box; fixed, it reports 1.20 mm.

**2026-10-08, stage 10: AMC1311 1 µF supply caps (closure review M1), decided under the owner's delegation:** TI SBAS786C (rev. Jun 2022) §10 decouples each AMC1311 supply with "a low-ESR, 100-nF capacitor … parallel to a low-ESR, 1-µF capacitor". The board had only the 100 nF. C149 (VDD1, HOT5 → GND1 on ocp_kelvin_p) and C150 (VDD2, V3V3 → SELV_GND) are added, both 1 µF GRM21BR71H105KA12L 0805.
- **C150** sits 4.9 mm by copper from pin 8.
- **C149** sits 13.8 mm through 2 vias: there is no closer free 0805 spot on U4's HOT side, and C28's 100 nF (7.3 mm) stays the HF cap. Accepted for a 5 V, ~6 mA supply.
- **Audit:** C149.2 joins the audited ocp_kelvin_p membership (`audit.rs`). It carries no DC, and the Kelvin budget is unchanged (161.89 mΩ, 47.52–97.98 A).
- **Board `ef993141…`:** DRC 0 / 0 / parity 0, barrier gates 0, DFM PASS, Gerber review 888/888, D5 PASS, collisions 0, R4 0 hits, source verify PASS (357), audit 74/74.

**2026-10-08, stage 11: closure re-review minors, decided under the owner's delegation:** the stage-10 re-review (`REVIEW-STAGE10.md`) found no BLOCKER or MAJOR, and confirmed B1, N1 and the +2 nH gate-loop bound.
- **S10-1:** adding C150 before C29 in placement had pushed the AMC1311 VDD2 100 nF off its pin. The order is fixed: C29 is back at 2.40 mm with no vias.
- **N2:** hole and fiducial designators are on F.Fab. They collided with the washer rings, and the rings plus the H2–H7 legend mark the holes. The silk text planner now uses the real stroke-font width and a 1.5 mm edge margin. Silk warnings fell 13 → 3; the remaining three are the PS1/PS2 outlines and Q2 on BR1's box.
- **S10-2:** the probe map is regenerated.
- **Watch item:** re-routes over stages 8–11 thinned U26's In1 n_ls spreading plane, measured within 12 mm: 181 → 162 mm² (stage 7: 154). B3's grid-sensitive pad cell drifted from 162 to 178 °C. Not acted on: U26 is ~0.9 W with a datasheet θJA of ~35 °C/W. IR-check at first power-up (FAB-NOTE first-article list).
- **Board `e85a4c82…`:** DRC 0 / 0 / parity 0, barrier gates 0, DFM PASS, Gerber review 889/889, D5 PASS, Kelvin 47.52–97.98 A, collisions 0, R4 0 hits.

**2026-10-08, open (owner): nameplate voltage, 120 V or 120/127 V.** The external-confirmation drafts (`validation-results/08-manufacturing-package/native-21/sourcing/inquiries/`) surfaced a dependency. Under the nominal-voltage rule (UL 248-1: rating = nominal system voltage; interrupting test at rated +5 %), F1's MDA-25-R 10 kA @ 125 Vac covers a **120 V nominal** product. A product **rated 127 V nominal** (Mexico 220Y/127 V; ORACLE-ANSWER.md already uses a "Rated 127 V" column) falls under the 1.5 kA @ 250 Vac figure. That is below the repo's zero-impedance cord-limited bound (4.26 kA at 1.8 m), though above a realistic 15 m branch basis (~0.46 kA).
- **If 120 V only:** send the certifier draft as written.
- **If 127 V is on the nameplate:** either the lab accepts a branch-impedance fault basis, or F1 moves to a fuse with a ≥ 5 kA rating at 250 Vac (fallbacks listed in F1-CERTIFIER.md).

Also corrected the same day: FAB-JLCPCB.md no longer claims JLC uses NP-155F. JLC names no laminate for JLC041622-7628. Every candidate laminate with a public CTI is PLC 3 (175–249 V), which meets CTI ≥ 175 with no margin, so the written JLC confirmation is still required.

**2026-10-08, coil-stud spacing (review M6), owner decision** (approved "if that's what a senior PCB design engineer would do", on the recommendation in `validation-results/08-manufacturing-package/native-21/owner-items/m6m10/`): J2/J5 stay at **15.0 mm**.
- **Basis:** the J2–J5 insulation is functional. IEC 60335-1:2020 29.2.4 / Table 18 (PD3, IIIa) needs 4.2 mm creepage at the estimated ≤ 333 V rms coil-voltage bound (22 A ceiling, f ≥ 31.3 kHz), and the 5.0 mm tank rule covers ≤ 400 V rms. Clearance needs ≥ 1.3 mm (Table 16 PD3 + 0.5 mm).
- **Why not move J5:** the board's own minimum for this voltage is 5.0 mm (SW_A↔RES_A along 74 mm, and RES_A↔COIL_FEED at the studs), so moving J5 cannot raise it.
- **Why not bare lugs:** with bare lugs even 30 mm centres fail the "most unfavourable position" rule, because the lugs can be turned into contact.
- **Requirement:** insulated M4 ring terminals on J2/J5 (bare ring ≤ 10 mm, ring-to-ring ≥ 5.0 mm at any rotation). ASSEMBLY.md's 30 mm target is withdrawn.
- **Conditions:** the lug part (candidate TE 2-34853-1, 105 °C vinyl) is confirmed against the Litz cross-section and the lead temperature measured at the stud. The tank-voltage RMS convention goes to the certification lab.
- **Reverses if** the lab rates the line-modulated HF working voltage as carrier-crest RMS (5.65 mm at 636 V pk). That changes the board-wide tank rule to ≥ 5.7 mm (a re-layout of the SW_A/RES_A lanes), not just the studs. It also reverses if IEC 60664-4 Table 2 exceeds 5.0 mm.
- **28 A update (2026-10-12, `owner-items/m6m10/coil-voltage-28a/`, rerun reproduced):** the 333 V rms / 667 V pk bound applies at 22 A only. The coil voltage (J2–J5) at 28 A, in line-cycle RMS, depends on the load:
  - **With a pan (normal use):** 345 V rms for the round-6 pan cases on the L70 tank, and 362 V rms on any L. Table 18 needs 4.3–4.6 mm, so **the 5.0 mm rule holds**.
  - **No pan, at 28 A:** 409 V rms / 818 V pk (35 kHz floor, bank −10 %, 140 V line), which needs 5.16 mm. That fails by 0.16 mm on RES_A–COIL_FEED, RES_A–SW_A and the J2/J5 ring-to-ring gap.
  - **Decision: no copper change.**
    - Normal use never reaches the no-pan 28 A point: firmware holds a no-pan clamp at 22 A (`tank_freq.h` TANK_CEILING_DEFAULT_A; no-pan evidence on Q and R, with the `N21_FAULT_TANK_RMS` overrun latch). The working voltage in normal use is therefore ≤ 362 V rms.
    - The no-pan 28 A point needs a failed clamp. That is a clause-19 fault on functional insulation between two HOT nets: if the gap bridged, the shunt OCP would trip.
    - Confirmations: COMMISSIONING step 9a.6 tests the clamp, and the bench measures V(J2–J5) at 28 A with and without a pan.
  - **Fallback if the lab ties working voltage to the no-pan case:** raise the firmware floor to ≥ 36.2 kHz, or require the bank ≥ 0.465 µF (±5 % parts). Either brings the bound to ≤ 400 V rms with no copper change.
  - **Crest-RMS reading:** if the lab uses carrier-crest RMS, the coil lanes need about 7.4 mm and RES_A to HV_RET/N_LS/BUS_P needs 6.3 mm, a board-wide re-layout. The certifier question stands.
  - The board-side voltages in the study table replace the 333 V figure in ASSEMBLY.md and F1-CERTIFIER item 7.

**2026-10-08, native-21 outline and J4 position (review M10; amends D-36 / RELAYOUT L11, L15), owner decision** (same approval): the outline is **290 × 140 plus a 91 × 50 SELV tongue** (board x 0–91, y 140–190; R4/R25 world x 50–141, y 46–96).
- **J4 stays on the tongue's front edge.** The J4 lead to the front controller is 74 mm, lands at both ends, and stays in front of the Nomex SELV/HOT barrier (R25 route landings 50/50, all-pairs 0 unresolved). A rear-band J4 would need a ≥ 140 mm SELV lead across the HOT core (estimate).
- **L15's "rear"** applies to the enclosure's external connectors and the coil leads, not to the internal SELV harness.
- **Fit:** `board_in_enclosure.py` (L modelled) gives 417 bodies, 0 hits.
- **Reverses if** the controller moves rearward or the encoder/knob stack moves over the tongue.

**2026-10-08, M6 amendment: upturned coil terminals.** The enclosure's R26 model screened a horizontal lug barrel plus ≥ 10 mm of straight Litz from each stud in all four directions. Every one collides with board parts: board +x runs over C21/C22, −x over the U16/U26 block, +y over T1, and −y over the other stud and J7. The decision's insulation requirement stands: insulated M4 ring, bare ring ≤ 10 mm, ≥ 5.0 mm at any rotation. What changes is the termination: the ring tongue is formed 90° **upward**, with the barrel vertical and offset away from the other stud, so the Litz drops near-vertically within ~10 mm of each stud axis, as the R18 harness intended. The part (a moulded insulated upturned ring, or a bare upturned ring with dual-wall ≥ 150 °C heat-shrink to the ring) is chosen with the coil supplier against the Litz size and the measured stud temperature. TE 2-34853-1 (straight) is withdrawn as the candidate.

**2026-10-08, heatsink HOT↔PE insulation stack (review M11), owner decision** ("approved", on the recommendation in `validation-results/08-manufacturing-package/native-21/owner-items/m11/`).
- **Problem:** as modelled in R25, the PE-bonded edge sink sat on the board's rear edge. HOT copper was 0.6 mm from it on all four layers and the FET lead pads 1.97 mm; that fails even basic insulation.
- **Requirement: reinforced.** R38 ties PE to the controller return, and D5-BASIS keeps that barrier reinforced. Per IEC 60335-1 at PD3, IIIa: creepage 8.0 mm, clearance 2.0 mm, solid insulation 2 mm (or 3 layers, or the 29.3.3 test).
- **Decision:**
  - the sink is set back **8.0 mm** (world Y ≈ 244), with a **7.8 mm 6061/6082 aluminium spreader bar** whose lowest edge is ≥ 8.0 mm above the board top;
  - **2.00 mm AlN tiles** (≥ 150 W/mK, Kyocera AN216A class; lapped, flatness ≤ 0.03 mm; two tiles, Q5–Q6 and Q3–Q2–BR1) overhang the tab metal by 6.5 mm and count as reinforced by thickness. A 5 mm relief groove in the bar sits under the tile joint;
  - **non-conductive** metal-oxide-filled thermal compound on both faces (candidate DOWSIL TC-5622, held until a dielectric figure is confirmed);
  - a 0.5 mm GAP PAD HC 3.0 behind BR1;
  - a **stainless comb-spring clamp** screwed to the bar ≥ 14 mm above any tab metal, pressing 60–80 N per device through a 3 mm FR-4/G-10 strip. No screw goes through a TO-247 hole and no metal touches a package.
  - The enclosure moves the inlet hood, plenum, end cap and seals with the sink; its screen found no conflict.
- **Thermal:** 0.40–0.63 °C/W per FET against D-36's 0.7 budget; the bar adds ≈ 0.016 °C/W. The new HOT→PE paths measure 8.0–10.4 mm.
- **Board:** no change. Optional at a re-spin: move BR1 −0.465 mm in y to drop the gap pad.
- **Tests:** hipot type test 3000 Vac 60 s on the clamped assembly, routine 2000 Vac 1 s (Table 19), plus per-FET case-to-pedestal ΔT and clamp-force checks at bring-up.
- **Open:** AlN tile quote; a compound dielectric figure; the lab confirming the standard edition and whether earthed ELV allows basic insulation. Even basic needs this geometry.

**2026-10-08, M11 amendment (owner: "yep update"): insulator choice left open; per-device catalogue parts preferred.** The stack geometry stands, because it is needed in every case: the 0.6 mm HOT-to-sink gap fails even basic insulation. That means the sink set back 8 mm, the aluminium spreader bar, the insulated comb-spring clamp through FR-4, and nothing PE within 8 mm of HOT copper. The **insulator** is reopened for DFM.
1. **Preferred:** per-device catalogue insulators, one TO-247-size ceramic (AlN) piece per FET plus one for BR1, if the sourcing study shows they give the ≥ 6.5 mm overhang and fit the 0.7 °C/W budget. A 1 mm part is reinforced by the cl. 29.3.3 test route rather than the 2 mm thickness route.
2. **Fallback:** the two custom shared 2 mm AlN tiles. These are prototype-grade: brittle under spring load, flatness ≤ 0.03 mm, a custom RFQ, and they span devices of different heights.
3. **For production, asked of the certification lab:** is reinforced insulation required at the PE-bonded sink at all? In a Class I appliance an earthed sink normally needs only basic insulation, which would allow standard per-device silicone pads with insulated clips. The reinforced demand comes from R38's SELV-return-to-PE bond plus D5-BASIS's "reinforced with PE open" rule. If the lab accepts basic, revisit the stack. Longer term, revisit R38 so the sink is out of the reinforced path.

**2026-10-08, D-18(3) fan supply superseded, decided under the owner's delegation:** D-18 fed the fans from a dedicated SELV 12 V supply, not PS1 or J4.1, because it sized for two 11.4 W fans (22.8 W), more than PS1's 21 W. The enclosure now carries one fan, 0.63 A at 12 V (7.6 W). The integrated controller (`zapote/controller`, commit 7593ceed3) runs it from a 12 V buck on PS1 via J4.1, per the enclosure's R24/R25 CONTROLLER-SPEC.
- **Budget:** the controller's budget, with every part at datasheet maximum, puts PS1 at 12.4 W of 21 W. J4.1 carries well under the Micro-Fit 3.0 contact rating.
- **Input estimate:** the 1.3 A auxiliary allowance in the input-current estimate (both IRM-20 at full load) still covers it.
- **Reverses if** a second fan returns or PS1's load exceeds ~80 % of its rating at 50 °C internal ambient.

**2026-10-08, M11 insulator resolved: shared AlN tiles cut from stock plate, decided under the owner's delegation** (sourcing study `validation-results/08-manufacturing-package/native-21/owner-items/m11-sourcing/`). Per-device catalogue insulators were the preferred option, but they do not fit.
- **Pitch:** the FETs sit on an 18 mm pitch with 2 mm body gaps, so a per-device insulator with the 6.5 mm overhang (≈ 29 × 34 mm) is physically impossible.
- **Catalogue parts:** the stocked TO-247 ceramics are alumina, ≤ 25 mm tall (the stack needs z ≥ 32). There is no stocked AlN part and nothing for the GBJ.
- **Thermal:** 1 mm alumina reaches 0.82 °C/W conservatively, against the 0.7 limit.

**Decision:**
- **Tiles:** the two shared 2.0 mm AlN tiles (A: Q5+Q6; B: Q3+Q2+BR1), **cut from stock lapped 2.032 mm AlN plate** (Valley Design AlN-110, or Almath SUB1141142ALN 114 × 114 × 2 mm; 3 B + 2 A tiles per plate, 4 plates for 7 stacks). The 2-tile split is kept, because a 3-tile split's groove would take 1.1 mm of contact under Q2's tab.
- **Compound:** Electrolube HTCP20S (2.5 W/mK, 42 kV/mm, 10¹⁴ Ω·cm, metal-oxide filler) replaces the TC-5622 candidate, which publishes no dielectric data.
- **Gap pad:** GAP PAD HC 3.0 sheet GPHC3.0-0.020-02-0816, cut 32 × 22 mm.
- **Clamp and strip:** a custom 1.4310 comb spring to the §5.2 spec, and G-10 strips (CTI/RTI to be confirmed by UL card).
- **Estimate:** ≈ $350 per stack, ≈ $2.5k for 7.
- **Longest lead:** the AlN tiles (RFQ, cut and lap, 3–6 weeks); the RFQ text is ready (§1.2). The tiles gate powered tests on the real sink, not the PCB order.

**2026-10-08, nameplate voltage: 120 V, US/Canada (owner decision: "120 V only").** This closes the open item recorded earlier the same day.
- **F1:** the nominal-voltage rule supports MDA-25-R's 10 kA @ 125 Vac rating. The certifier inquiry goes out as the 120 V case.
- **Design range:** the electrical design keeps its coverage to 140 V line: insulation analysis, tank cases, and the 15 A input limit at low line.
- **Mexico is a separate, later market decision.** Its residential supply is nominally 127 V (220Y/127 V), and an appliance sold there carries NOM certification at its marked rating (to be confirmed with a NOM body, e.g. ANCE). A 120–127 V rating would reopen F1's interrupting-rating question. That needs either the lab's acceptance of a branch-impedance fault basis, or a fuse with ≥ 5 kA at 250 Vac (fallbacks in `sourcing/inquiries/F1-CERTIFIER.md`).

**2026-10-08, nameplate voltage revised: 120–127 V~ 60 Hz, US/Canada and Mexico from day 1 (owner: "to be clear i need day 1 mexico support").** This supersedes the 120 V-only entry above.
- **Unaffected:** the electrical design already covers 140 V line (127 V + 10 %): the insulation analysis (ORACLE-ANSWER.md "Rated 127 V"), the tank cases, TMOV20RP175E (175 Vac), the 650 V FETs and bus parts, and the IRM-20 modules (85–264 Vac).
- **Affected: F1 interrupting rating.** At 127 V nominal, MDA-25-R's 10 kA @ 125 Vac does not clearly apply, leaving 1.5 kA @ 250 Vac, against the cord-limited bound of up to 4.26 kA (1.8 m) or 7.66 kA (1.0 m) from a stiff source. The same applies to the enclosure's MDA-30-R inlet fuse.
- **Direction:** a fuse whose interrupting rating covers any branch fault at 127 V. A UL Class CC time-delay (600 Vac, 200 kA, 10 × 38 mm) is the leading candidate, which means a board ECO at F1 (clips and footprint). It is being checked for parts, fit and coordination before any change.
- **Fallback:** the certification lab accepts the upstream current-limiting fuse's let-through as F1's fault basis.
- **Certification:** NOM (Mexico) as well as UL/CSA; the body (e.g. ANCE/NYCE) is to be chosen.

**2026-10-09, F1 becomes a UL Class CC fuse (stage 12), decided under the owner's delegation (follows the 120–127 V nameplate):** `owner-items/f1cc/F1-RECOMMENDATION.md`.
- **Fuse:** F1 is **Littelfuse KLDR025.TXP** (alternate Eaton Bussmann LP-CC-25): Class CC (UL 248-4), 25 A time-delay, 600 Vac, **200 kA**, UL Listed. That is ≈ 24× the 4.7–8.4 kA cord-limited bound at 127 V + 10 %, for UL, CSA and NOM alike.
  - Carrying capacity: ≈ 10 % downrating at 50 °C (KLDR Rev 092821 p.6), so 25 × 0.75 × 0.90 ≈ 16.9 A continuous ≥ 15 A.
  - No time-delay 6.3 × 32 mm 25 A fuse with ≥ 5 kA at 250 V was found. The fast-acting Littelfuse 0505025.MXP (20 kA @ 500 V, data unverified) is the fallback only if the ECO were blocked.
- **Clips:** 2 × **Littelfuse 01250003H** (125 series, 30 A, LCSC C223911, hand-soldered) on a new footprint, `temper:Fuseholder_Clip-10.3x38mm_Littelfuse_125_Inline_P41.76x10.80mm_Slot1.2x2.5mm_Horizontal` (slotted PTH, 41.76 mm span).
- **Board ECO:**
  - F1 moves to (252.00, 7.25, 0°);
  - C1 moves +0.6 mm;
  - the F.Cu ac_l_in and l_f pours are redrawn (`layout/patches21.py` MAINS_POURS).
- **Open:**
  - the clip's 3D shape near the board (≥ 3.2 mm air to the l_f strip; B.Cu fallback in §5.3);
  - the 01250003H voltage rating and agency file on Littelfuse's own page;
  - LP-CC-25's I²t data.
- **Enclosure:** the inlet fuse is to be deleted (the two fuses cannot be selective), or else a Class CC 30 A in a Littelfuse 5710CC holder. MDA-30-R is not kept.

**2026-10-09, inlet fuse deleted (owner decision, relayed by the enclosure session, R28).** The D-22 EMI module sits "after the upstream fuse/disconnect"; that now reads **after the disconnect** only.
- **Disconnect:** the EC11 switched inlet.
- **Overcurrent protection:** the branch-circuit breaker plus F1 (Littelfuse KLDR025.TXP, UL Class CC, 25 A time-delay, 600 Vac / 200 kA, a Listed branch-circuit fuse). There is no inlet fuse, and MDA-30-R is removed.
- **Why:** the two fuses could not be made selective (KLDR025 clears at 1,710 A²s; KLDR030 melts at 300 A²s), so a second fuse added nothing.
- **Certification:** the memo asks the certifier to accept "branch breaker + Class CC F1, no inlet fuse".

**2026-10-09, BOM simplification, safe set (source only; the board is rebuilt in stage 13):** `validation-results/08-manufacturing-package/native-21/bom-simplification/PROPOSAL.md`. The owner's rule: no functional part removed; only changes whose equivalence is validated.
- **Scope:** 25 changes to MPNs or values only. Footprints, pads and nets are unchanged, and there are no copper changes.
- **Part-for-part swaps:** 17 Extended → Basic swaps of identical spec (B1–B17). B1, the 100 nF 0603, also clears a stock risk.
- **Relaxed precision:**
  - 4.99 k goes to 1 %;
  - R92 RCLK goes from 18.2 k to 18 k 1 % (≈ +1.1 % clock, inside 500–700 kHz);
  - R93 goes from 30.1 k to 30 k 1 %;
  - the GRM32ER 10 µF 1210 line merges into UMK325AB7106KM-T.
- **R1/R2 120 k → 100 k:** this fixes a latent miss. With 120 k and the X caps at +20 %, the discharge from 198 V to 34 V took 1.025 s, over the 1 s limit. It is now 0.854 s (`calc_discharge.py`).
- **No-stock lines resolved:**
  - **R34/R35 10.6 k / 10 k → 12.4 k / 11.7 k,** both 0.1 % 25 ppm. The round-3 corner model gives a shunt-OCP band of **49.53–97.77 A**, against 49.73–97.98 A before (`calc_protection_bands.py`). The LM4040 minimum current rises to 139.2 µA, and audit `ocp_threshold_load` is now 24.1 k.
  - **R77/R95/R110 6.12 k → 6.2 k:** −2 V nominal +10 mV; worst-case margins are UV 0.109 V, OV 0.071 V and −1.6 V bound 0.368 V (`calc_neg_rail.py`).
  - **R87/R105/R120 → Viking ARG03BTC1333,** the same 133 k 0.1 %.
- **Effect:** 66 → 45 JLC Extended types, about −$63 per order. The unique-line count is unchanged.
- **Checks:** audit PASS with 357 components, 74/74 tests, and verify_source PASS.
- **Not taken without a further check:** the R3/R4 bleed, R40/R41 at 1 %, the U1/U2 and U35 -Q1 parts. Also open: removing R1/R2 (needs the certifier), the J7–J10 studs (production re-spin), and the 3-input OR merge (re-spin).

**2026-10-09, resonant bank: 5 × TDK B32654A1104K000 (0.50 µF), stage 13, decided under the owner's delegation:** `validation-results/05-resonant-tank-envelope/round4-assumed-basis/` plus the independent review (scratch `bank-review/REVIEW.md`, summarised here).
- **Problem:** CDE gives the 942C parts' current only at 70 °C / 100 kHz and publishes no frequency rule. At 22 A tank current, each 0.22 µF part carries 8.96 A nominal and 10.05 A worst case at ±10 % share.
  - Round 4's √f bound (13.4 A tank) is valid but pessimistic: most of the 942C ESR is metallization, not dielectric loss.
  - On CDE's own curve shape, the bank is still **1.08–1.17× over** at 35 kHz.
  - 942C12P22K-F also has no distributor stock (24-week lead time).
- **Choice:** 5 × TDK B32654A1104K000 in parallel.
  - The part is 0.10 µF MKP, 1600 Vdc / 500 Vac, 14 × 24.5 × 31.5 mm, P27.5 (B3265*A data sheet pp. 3 and 22).
  - It is rated **7.3 A at 85 °C / 100 kHz**, and **0.86×** on TDK's own I_RMS-vs-f curve at 85 °C, read by eye (±10 %). *Corrected 2026-10-10:* digitized from the curve, it is **0.89×** at 22 A (`05-resonant-tank-envelope/round6-full-power/scripts/digitize_tdk_p57.py`).
  - Stock: 2,669 at DigiKey on 2026-10-09.
- **Rejected:** 942C16P1K-F × 5, which clears even the √f bound but needs 39 mm more than the slot.
- **Resonance:** 0.50 µF raises resonance 3.9 %. Round 4's 0.50 µF run gives a minimum f/f_res of 1.21 and no floor-limited cases. The bleed τ becomes 0.94 s.
- **Board:**
  - **Footprint and model:** a new footprint, `temper:TDK_B32654_P27.5_W14.0_L31.5_Radial`, and STEP model (`models3d/capacitors`).
  - **Layout:**
    - the caps go in one column (C21–C23, C151, C152), pins at x 163.0 / 190.5, rows y 53.7 / 68.5 / 82.5 / 97.05 / 111.6;
    - the res_a and sw_b B.Cu strips are re-cut (`patches21.py`);
    - the rows are bounded by the sw_b band (5 mm), the In1 n_ls / v24_raw runs (5 mm) and the SELV line_zc-raw run (8 mm).
- **Open (bench):** the bodies sit 0.55–0.8 mm apart at maximum dimensions, so the bank's large faces are mutually shadowed. Before releasing 22 A:
  - measure the case hot-spot of the middle cap at 22 A tank current, 35–45 kHz, in the enclosure's worst ambient, and keep the rise ≤ 20 K;
  - if that fails, add airflow across the bank, or cap the tank current at the measured limit;
  - digitise TDK p.57 properly.

**2026-10-09, heatsink mounting (to enclosure R30):** the sink is carried by the chassis, never by the board. Through the comb-spring clamp, the sink's mass and any shock would load the TO-247 solder joints and the FR-4.
- **Mounting:** two PE-bonded brackets from the base grip the sink's base flange or bottom fin. Thread-forming M3 with ≥ 4 mm engagement is the fallback; M4 is not used in the 4 mm wall. The sink stays a catalogue extrusion.
- **Clearance:** the brackets stay ≥ 8 mm from HOT copper, at Y ≥ 244.
- **Assembly order:** board → clamp loaded → bracket last. Bracket holes are slotted in Z, or the sink-to-spreader stack is held to ±0.3 mm.
- **Sink/bar PE bond (same day, to R30):** neither the sink's fin pack nor its base face can take a bolt stack, so the bond is made at an integral **ear on the 6061 spreader bar's X149 end**.
  - **Ear stack:** M4 through-bolt; external-tooth washers against bare, masked metal; nyloc nut; 14 AWG 105 °C green/yellow strap with ring lugs to the chassis star. It must be ≥ 8 mm from HOT copper at any lug rotation, checked in the stage-13 fit/D5 gates.
  - **Bar-to-sink joint:** this joint is part of the bond. At least two of the bar's fasteners carry toothed washers against masked metal, outside the thermal-compound footprint (IEC 60335-1 §28.2).
  - **Acceptance:** from a bare sink fin to the inlet PE pin, ≤ 0.1 Ω at 25 A for 120 s (§27.5).
  - **Hook contact:** the R30 hook brackets' contact is not counted as a bond.
- **Stage 13 board** (`d7baa28a…`, same day):
  - **Gates:** DRC 0 errors / 0 unconnected / parity 0; both barrier gates 0; D5 8.047 / 8.507 mm; JLC DFM PASS; Gerber review PASS (892 round holes + 4 slots); fit 415 solids with 0 overlaps and 0 R4 hits.
  - **Kelvin band:** 47.32–97.77 A.
  - **Task 04:** res_a 0.67 mΩ; sw_b within 2 %. B3 is unchanged.
  - **Open, firmware:** round 4's envelope tank peaks (47.25 A main grid, 47.73 A with tolerances) now sit at or just above the band's 47.32 A low corner. That corner needs every component at its worst-case limit at once, but the nuisance-trip margin is gone at the extreme corner. The firmware **tank-peak limit of about 45 A** (round 4, recommendation 3) is therefore required before 22 A operation, as is a bench measurement of the real trip threshold.

**2026-10-09, enclosure pose of native-21 was a mirror image; corrected pose adopted (found by the enclosure session, R30 exact-solid check; verified here).**
- **Problem:** board-local coordinates are KiCad's (x right, y down). The pose used from R4 through R30, world = (141 − x, 236 − y), flips x alone against a right-handed world. That is a reflection, and no real board can be mounted that way. The R4 fit results, the enclosure envelopes, the hole bosses and every world coordinate quoted for native-21 (e.g. "HOT edge X 140.4") describe that mirror image.
- **Decision (power stage):** the board stays as laid out. ICs cannot be mirrored, and the FEM and every gate are tied to this copper. The enclosure adopts **pose (a): world = (x − 149, 236 − y, 26 + z)**, keeping the FET row and sink at the rear.
  - The enclosure's interior mirrors about the board in R31: sink/duct at rear-left, J1 mains at the right, the SELV tongue / J4 at front-left, hole bosses at x − 149.
  - Rotating 180° instead would put the sink at the front, so it is rejected.
  - The controller's plan position and J4 mating are provisional until R31.
- **Fit gate:** `validation-plan/enclosure-fit/board_in_enclosure.py` now takes `--pose translate|rot180|mirror-legacy`. The legacy pose remains the default only so stage ≤ 13 records reproduce; R31 checks run with `--pose translate --x0 -149 --y0 236`.
- **Found in the same check, independent of the pose:**
  - Metal reaches Z 11.8, 0.8 mm above the PE base (Z 11). This was first read as the TO-247 drain tab; the enclosure session's sections show it is the **untrimmed FET lead tails** in the STEP model (14.2 mm below the board), while the bodies sit above the board. **Fix: an assembly rule.** Every THT lead is trimmed to ≤ 2.5 mm below the board bottom after soldering, so all HOT metal is at ≥ Z 23.5, ≥ 12.5 mm from the base (ASSEMBLY.md). The R31 pose is x − 141 (whole assembly mirrored about X = 0), which is pose (a) with a different origin.
  - The M11 tile face must sit at the TO-247 body's 5.0 mm nominal (4.83–5.21 mm), with the comb spring taking the tolerance. BR1's strip must be sized for its 4.8 mm maximum.

**2026-10-09, C1/C2 X2 → KEMET R463N410050N1K (stage 13b):** `validation-results/08-manufacturing-package/native-21/sourcing/ALTERNATES-2026-10-09.md`.
- **Why:** R463N410000N1M is at 24–38 weeks.
- **Equivalence:** same R46 series, N1 body, 310 Vac X2, approvals and 22.5 mm pitch. The differences are ±10 % tolerance (inside the ±20 % basis) and 25 mm leads, which are trimmed at assembly. Digi-Key has 955.
- **EMI:** the task-07 CM transfer is insensitive to it. DM moves ≤ 0.35 dB at 150–500 kHz; there are no DM results in the 1–2.5 MHz band, where it moves more.
- **Board:** a value-only rebuild (6556f536). All gates were rerun, with identical results.
- **Still blocked; these need the owner (samples are outward-facing):**
  - **C5/C6 (TDK B32656G0275J000):** no stocked equivalent. Ask TDK for samples of J000 or M000; fallback is a deviation to B32676G1905K000.
  - **T2/T3 (Würth 750320775):** ask Würth Midcom for samples or an allocation, 20 pcs for a 5-board lot; fallback is 750315240 with a footprint ECO.
  - **D3 (Microchip MRT130KP295CV):** Microchip samples or brokers; fallback is Littelfuse AK3-380C-Y with a footprint ECO and vendor clamp data.

**2026-10-09, enclosure R31 accepted (true pose) and BR1 interface:**
- **R31 pose:** `output/temper-manufacturing-r31`, world = (x − 141, 236 − y, 26 + z), built as a whole-assembly mirror about X = 0. The fascia controls are not mirrored (owner).
  - The stage-13 board STEP (9de60c6a, leads cut at 2.5 mm) sits in the assembly, and the enclosure session's exact-solid all-pairs check is 0 unresolved.
  - Hole map, checked here against the pose: H1 (144, 101) metal; H2 (−135, 56); H3 (−55, 56); H4 (−117, 162); H5 (−53, 136); H6 (−13, 182); H7 (53, 106).
  - HOT-edge distances, 3D: bond bolt stack 32.1 mm, lug 33.5 mm, sink brackets 20.1 / 22.4 mm.
  - Stage 13b changes only C1/C2's MPN (same body), so the check stands.
- **BR1:** with the tile face at Y 234.47 (+0.3 mm for the TO-247 nominal), BR1's body leaves a 0.67 mm gap (0.47–0.87 mm over its 4.4–4.8 mm thickness).
  - BR1's GAP PAD HC 3.0 becomes the **1.0 mm (0.040")** grade, compressed by the comb preload.
  - The FR-4 strip loads the pad and must not push BR1 onto the tile; no lead flex is relied on.
  - Estimate: about 0.67 mm / (3 W/mK × ~6 cm²) ≈ 0.37 K/W, inside the ≤ 1.0 °C/W interface budget.
  - The re-spin option to move BR1 toward the sink and drop the pad remains.

**2026-10-09, alternative-circuit studies for the three no-stock blocks: findings that hold whatever is fitted** (`validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/`; simulation and datasheet work only; scripts are in the session scratch and are to be committed with any adopted change):
1. **The F6 decks pin the bulk node with an ideal source,** so bulk capacitance and bulk-path inductance were never in the switching results.
   - With the bulk modelled explicitly, the S4 hard-turn-on case is sensitive to the bulk-path inductance: about +5 V die VDS per nH, with failures from about 28–32 nH. The estimate is about 20 nH ±50 % (ALT-C5C6).
   - **Action:** extract or measure the native-21 bulk path (the FET row to C5/C6) whatever capacitor is fitted.
2. **Charge injected through the high-side bias barrier at the partner leg's edge is not in the F6 rail budget.** It costs about 6–25 mV per pF on a high-side bank, against the committed 78.6 mV margin (ALT-BIAS).
   - The barrier must have a bounded coupling capacitance of about 4 pF maximum. 750320775 states 3 pF *typical* only.
   - **Action:** add the coupling current to the edge campaign for whatever is built.
3. **The recorded bootstrap fallback (2026-10-06) fails as written.**
   - The TLVH431 split only sinks, so the negative rail never forms after a pre-charge; a source/sink split carrying about 44 mA would be needed.
   - BIAS_BAD holds DIS through the burst idle, so the pre-charge cannot run.
   - It is withdrawn as a fallback.
4. **Unmodelled clamp case (ALT-D3):** gate-off at the line crest while the mains source inductance keeps driving current into the bus reaches about 578 V with no clamp (assumed 500 µH / 30 A). It sets the longest D3 pulse.
   - DC-LINK-CLAMP.md and ORACLE-ANSWER.md do not cover it.
   - **D3 is required before any bus above 150 V.** Bench bring-up without a qualified clamp stays at ≤ 150 V DC.

**2026-10-09, stage 14: bias modules, 9 µF bus capacitors, two-TVS bus clamp (owner approved: "approved, go ahead with stage 14").** Basis: `validation-results/08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/`.
1. **High-side bias: one RECOM R24C2T25/R-R per high side** (U41, U42), replacing the SN6507 (U35), T2/T3, D10–D13, L2/L3 and the HS TPS7A47s (U27/U28) with their passives.
   - **Circuit:**
     - the module's primary is on V24_RAW / N_LS, the same TCO-switched PS2 domain the SN6507 used;
     - a shared enable, CTRL = 24 V × 27/127 = 5.10 V (R62 100 k / R127 27 k);
     - its secondary gives a single 17 V output, 2.5 V × (1 + 63.4/11) = 16.91 V (RECOM p.4 values, 0.1 % resistors), into the unchanged TLVH431 split, reservoir and rail monitor;
     - COM and PG are left open (single-output configuration).
   - **Why it is not D-12 again** (the 2026-10-06 entries): D-12's rejected set was four SELV-fed modules, negative LDOs and a second AC-DC. This uses two modules on the existing TCO-switched HOT-side supply, so the TCO cut is kept, and it is a net reduction of 10 parts.
   - **Barrier:** coupling capacitance has a datasheet maximum (3.5 pF), against 750320775's 3 pF *typical*. It is reinforced (5 kVAC / 1.4 kVDC working), with CMTI 150 kV/µs.
   - **Evidence (ALT-BIAS):** the periodic rail campaign with the module as the source passes 128/128, worst −1.889 V (committed case −1.888 V). Startup reaches power-good at 6–13 ms against the module's 16 ms time-out with one split output cap dropped, which this design does.
   - **Open (bench):**
     - module temperature at the 60 kHz control-window maximum (~1.4 W) and at the 80 kHz F6 allocation (1.71 W against the 1.7 W typical, D-12's old concern);
     - the startup time;
     - the module's 10–16 MHz spread-spectrum emissions;
     - the edge-replay rail campaign including barrier coupling (finding 2 above).
   - **Netlist:** atopile now names three nets differently, `line_zc_raw`, `ldo_nr` and the LS TPS7A47's unused ANY-OUT pins `p2…p19`. They are mapped in the audit, the rules and the copper (`native-21/layout/stage14_migrate.py`).
2. **C5/C6: TDK B32676G1905K000** (9 µF ±10 %, 750 VDC, same pads; bus 18.4 µF).
   - **F6 with explicit bulk (ALT-C5C6):** 168/168 pass. Worst die VDS falls from 466/482 to 455/461 V, and off-gate from 0.53/0.78 to 0.13/0.51 V, from the lower ESL (12 against 19.2 nH).
   - **Costs:** about 80 % of TDK's self-heating allowance at an 85 °C case ambient. Bench: case temperature at 22 A.
   - **Changed behaviour:** the burst-power bus valley is 106 V against 33 V; bleed time ×3.3; inrush I²t ×6 (≤ 1.8 % of F1).
3. **D3 + D17: two Good-Ark 30KPA150CA in series**, midpoint on BUSBLEED_MID.
   - **Ratings:** clamp 466.8 V at 129.8 A, ≤ 520 V target; standoff 300 V against the 286 V corner (ALT-D3).
   - **Rule:** DC-LINK-CLAMP's no-silent-substitution rule is satisfied by this owner approval.
   - **Open:** the bench pulse qualification (ALT-D3 §5). Until it passes, the bench bus stays ≤ 150 V DC.
   - **Board:** D3 pads at 254.00 / 266.70; D17 at 270.54 / 283.24; R4 moves to (288.0, 103.5), 270° (pad-escape rects updated in `stage14_migrate.py`).
4. **Layout method:** every part that survives from stage 13b keeps its stage-13b pose (`native-21/layout/placement-stage13b.json`). The modules take T2/T3's spots, rotated 270° (primary up to the existing In1 trunk, whose bias_sw1/bias_sw2 tracks become n_ls/en_hs). Only the new parts are placed fresh.

**2026-10-09, enclosure R32 package (output/temper-r32-studies/R32-PLAN.md §4): power-stage dispositions.**
1. **Sink S8:** accepted. 6063, 8 mm base, 15 × 1.5 mm fins on a 3.0 mm gap; machined front face; 4 × M4 blind bond holes in the dry band; chem film, no masks.
   - §28.1 (enclosure position, clause intent): it restricts the screw material, not the threaded part. So it is **tapped 6063 with stainless ISO 4762 M4 screws**, about 7 mm engagement, with DIN 6797 locking (§28.3). **The certifier is to confirm.** Wire-thread inserts are held in reserve against Table 14 or E1b failures.
   - SINK-DRAWING-NOTES are updated to S8.
2. **D-18 requirement:** **R_SA ≤ 0.29 °C/W at ≥ 13 CFM delivered** replaces "0.15 at ≥ 20 CFM". The 0.15 was an allocation, and `requirement.py` reproduces the 0.2915 limit with 125.9 W, Tj 125 °C, 50 °C air and the M11 interface. Push blower (Delta BFB1012VH-F00) on PS1.
3. **Clamp stack:**
   - a seat-before-solder fixture (tab faces coplanar within 0.05 mm, square within 0.3°, with a 0.665 mm step at BR1);
   - comb acceptance 45–102 N per TO-247 (Infineon body A 4.70–5.30 mm), capped at Infineon's published maximum clip force if lower;
   - BR1 keeps the 1.0 mm Gap Pad, which retires the BR1-move re-spin;
   - the sink floats and is locked after the comb torque;
   - comb screws are 3 × M3 into the bar (clamp only).
4. **EMI below 150 kHz (new gap in D-22):** the 2f bus-ripple line screens at −4 to −25 dB at 9–150 kHz. The inlet module adds **≥ 100 µH DM**: ≥ 80 % at 15 A DC bias, rated 20 A, its heat stated against the module allowance.
   - Power-stage follow-up: damping of the ~16 kHz DM/X-cap resonance, and the LINE_ZC phase shift.
   - First powered unit: a conducted pre-scan from 9 kHz.
5. **Coil:** tuning and acceptance use the **installed** inductance: **R32 66.34 µH no-pan** (66.28 µH with the 1.27 mm walls). The seat ring stays one closed loop (joints ≤ 0.2 mΩ), because broken rings fail the 30 m field limit. Comb force stays 45–102 N: Infineon "Recommendations for Assembly of TO Packages" §4.3.2 limits only the pressure on the plastic, and 0.52 N/mm² is far below its 150 N/mm².
   - **Coil loss of record:** I²·R_ac with round 4's basis is **≈ 119 W at 22 A nominal, ≤ ≈ 198 W hot**; design for 200 W. Round 3's 48 W and the coil spec's 150–200 W are both superseded. The coil needs a ventilation bleed.
6. **Open (power stage):** magnetic pickup under the coil (140–640 µT at 31 kHz) on the R5 Kelvin, CT and LINE_ZC loops. At about 1 A per mV at R35.2, the loop area matters. To be computed from the R32 field map.
7. **Confirmed:**
   - RES_A / coil to SELV is 242 V rms / 640 V pk working (ORACLE Q2). **Superseded 2026-10-12** (`owner-items/m6m10/coil-selv-28a/`, rerun reproduced): ORACLE Q2 assumed in-phase tank current.
     - At 28 A the working voltage is **297 V rms / 656 V pk in normal use**, and 362 V rms / 791 V pk at the 29.4 A trip envelope.
     - Reinforced creepage at PD3 / IIIa in the >250–400 V band is **12.6 mm** (8.0 mm at PD2). The board-wide 8.0 mm HOT/SELV/PE floor therefore holds only for nets at ≤ 250 V rms. RES_A and the coil winding need 12.6 mm on outer-surface paths. Paths through the inner-layer laminate are solid insulation.
     - Stage-17b board measurement (outer layers, plan view): RES_A to SELV/PE is 8.14 mm to LINE_ZC_RAW and 9.40 mm to V15_SELV on B.Cu. Everything on F.Cu is ≥ 12.6 mm, and COIL_FEED has no outer-layer pair under 12.6 mm.
     - **Stage 18 fixes the two B.Cu gaps** (reroute, or a slot), adds a 12.6 mm RES_A-specific floor to the barrier gate, and checks T1's (CT) primary–secondary rating at 297 V rms reinforced and 35–60 kHz. **Done, item 18** (reroute: 13.375 / 14.400 mm; T1 sits on the SW_A end at 99 V rms, PASS).
     - Coil spec row 12b is updated to match. Certifier questions: PD2 for the potted winding system, and line-cycle RMS vs carrier-crest RMS.
   - J6 stays: H1 is a bare NPTH, so the board's PE comes only through J6;
   - H2–H7 keep nylon pan heads (PEEK socket heads if V-0 is ever required);
   - chem film finish on the bar and sink, with the E1b ≤ 0.1 Ω / 25 A test.
8. **Coil cooling and coil requirements (R32 study 02 follow-up, `02-cooling-acoustics-venting/coil_thermal.py`):**
   - **Cooling:** one push blower serves the sink and, through a ~27 % bleed, a sealed jet plenum under the coil (135 × Ø3 jets).
   - **Results:** typical 17 A gives a 102.5 °C winding. At 22 A with maximum R_ac and 50 °C inlet the winding reaches 140.7 °C; at 0.6× heat-transfer coefficient full speed holds 21.3 A at maximum R. Limits: mean winding ≤ 150 °C, ferrite ≤ 140 °C.
   - **Firmware (open):** fan drive = max(sink loop, coil loop); the coil loop holds the coil NTC (controller ADC1 "COIL") at 140 °C and derates tank current above 150 °C.
   - **Coil procurement requirements:**
     - Litz thermal class ≥ 200 °C;
     - R_ac ≤ 0.25 Ω at 40 kHz with the winding at 100 °C, with a measured curve (this retires the 0.41 Ω corner);
     - N87/N97-class ferrite bars, radial, leaving the 14 mm jet lanes clear.
   - **Pan-temperature cap: 250 °C (482 °F), owner decision 2026-10-09** ("250 c or 482 f is fine"). The firmware enforces it from the pan RTD by derating tank power, and it bounds the hot-glass hold that drives coil temperature. The 260 °C empty-pan case is a transient only.
9. **Coil-field pickup on the sense loops (R32 field map, `validation-results/02-protection-timing/coil-pickup/PICKUP.md`):** no fix needed. Figures are peak EMF at 31.1 A peak, pan / no-pan, from the stage-13b copper.
   - **OCP Kelvin pair:** 214 mm², 1.14 / 2.75 mV. At the tank-current peak the field is mostly in quadrature, so the shift there is 0.25 A in the model and 0.37 A at +50 % field.
   - **OCP most pessimistic stack:** 3.0 A, which still leaves 0.32 A of the 47.32 A low corner's margin to the 44 A minimum.
   - **CT loops:** 0.05 mV in the model (the sense/return layer swap cancels), 5.2 mV worst case, i.e. 0.35 A and 57 ns.
   - **LINE_ZC:** 16 ns or less.
   - **Coupling to the coil spec:** an air-core coil (2–5× field) would break only the most pessimistic OCP stack, so the ferrite-bar coil specification is also an OCP-margin item.
   - **Optional at a re-spin:** KELVIN_N's last 30 mm on In2 under the KELVIN_P pour (−56 % EMF), and C30/C31 at U6's pins.
10. **Full-power yield and the tank ceiling (2026-10-10; task 05 round 6, 18318042c, ASSUMED basis: no measured coil or pan).** At the 22 A ceiling, 13 % of pan cases reach the 1239 W hold (120 V, pooled). At 28 A, 85 % do (89 % on 220 mm pans).
   - **Firmware first, at any ceiling.** Today's firmware reaches the hold on about 0.2 % of pans, for three reasons:
     - it runs one commissioned frequency;
     - the 45 A peak trip caps the line RMS near 21 A;
     - the RMS trip compares per-sample AD8436 readings.
     Required changes:
     - **RMS trip:** use the half-cycle RMS from `input_limits`.
     - **Per-pan frequency loop:** approach from 60 kHz down and stop at the lowest f that keeps f ≥ max(35 kHz, 1.05 f_res), line RMS ≤ ceiling, inlet ≤ 11.1 A and peak ≤ trip − 3 A.
     - **Peak trip:** scale it with the ceiling, and lift the 50.9 A cap in `config_ok()`.
   - **Hardware is sized for 28 A (stage 15). The commissioned ceiling is a firmware parameter.** It ships at 22 A and rises in steps to 28 A only after bench evidence:
     - the bank hot-spot temperature; at 28 A the bank is 1.12× TDK's 85 °C curve;
     - the coil R_ac and winding temperature;
     - the switching loss.
     Each of these items is ASSUMED today.
   - **Kept:** the 70 µH coil and the 0.50 µF bank.
     - At 28 A, 80 and 90 µH lose yield to the 35 kHz floor (81 % and 59 %).
     - No smaller bank that fits the slot carries more than about 22 A.
   - **Stage 15 board changes, for 28 A (envelope peak 59.2 A):**
     - OCP trip floor ≥ 64 A, with the CT band about 64–76 A and the shunt band's low corner ≥ 64 A.
     - The shunt high corner (about 133 A) must be checked against the FET pulsed rating before release.
     - SW_A and SW_B copper ≥ 9.8 mm wide; SW_B needs a layout pass beside the FETs.
     - CT T1 and R5 are adequate.
   - **Coil RFQ:** target R_ac ≤ 0.23 Ω at 40 kHz / 100 °C (0.25 Ω holds 27.2 A at full blower); 0.25 Ω stays the acceptance limit.
   - **Sink:** unchanged until the switching loss is measured. The conservative basis would need R_SA ≤ 0.233 °C/W; the ZVS estimate gives Tj 82 °C.
11. **Stage 14 board complete (2026-10-10, board `3eb54216…`, copper.json `5a51cb0e…`).** The RECOM modules, C5/C6 and D3/D17 are routed.
    - **Gates:** DRC 0 / 0 / 0; barrier21 and the Rust gate 0 (5607 items); D5 8.047 / 8.507 mm; enclosure fit 0; JLC DFM PASS; Gerber review PASS (877 round holes plus 4 slots); Kelvin band 47.33–97.77 A.
    - **Hand links** (`patches21.add_stage14`, spots probed against the copper): three driver-to-module links the router could not find.
      - P_HB runs from U2's caps on In2 down x = 19.3, to R94.
      - The N_HB bank tail joins U42's B.Cu pour.
      - The N_HA bank tail drops on In1 into U41's In1 pour.
      - Each passes 8 mm from the SELV driver inputs and 3.2 mm from LS / v24 copper.
      - Two dead T3-era In2 runs were dropped (`stage14_migrate.py`).
    - **Module heat:** both modules have N_LS and N_Hx heat-spread pours on F.Cu and B.Cu. U42 also has In1 / In2 under its primary, because its edge island had it at 175 °C. B3 nominal h 10 / 25 is now U42 161.9 / 128.9 °C and U41 135.6 / 102.6 °C, so the board peak is unchanged from stage 13b.
    - **Bench gate:** module case temperature in the enclosure at 33 / 80 kHz (ALT-BIAS).
12. **R36 coil Litz and coil loss of record (2026-10-10; owner: first coils wound in-house on a G11 former, winder RFQ in parallel).**
    - **Litz confirmed:** 270 × 0.10 mm, type 2, grade-200 enamel, Nomex/PTFE serve, Ø2.4 bundle (2.12 mm² Cu), 21.9 turns, about 9.9 m.
    - **R_ac estimate** (`validation-results/05-resonant-tank-envelope/coil-litz/litz_rac.py`, on the enclosure's study-09 winding field +30 % for inter-bar leakage): **116–136 mΩ** at 40 kHz / 100 °C, against R_dc 110 mΩ. 0.08 mm strands gain ≤ 9 mΩ.
    - **Coil copper loss of record at 28 A:** 91–107 W expected, 196 W at the 0.25 Ω acceptance limit. The enclosure keeps its 200 W cooling basis; ferrite loss is added on top by the enclosure.
    - **Turns** were raised from 19.9 to 21.9 because 19.9 scales to about 61 µH, outside the 70 µH basis.
13. **Stage 15: 28 A tank hardware (2026-10-10, board `5b9dbd61…`, copper.json `1755a0cd…`; plan and scripts `validation-results/02-protection-timing/stage15-28A/`).**
    - **Protection** (value-only):
      - **R34 12.4 k → 12.6 k** (RT0603BRD0712K6L). The shunt band is 68.58–118.74 A, and 66.37 A after the Kelvin shift (66.30 A at the bound). The floor is 64.17 A: the 59.17 A envelope peak at 28 A, plus the 3.0 A pickup stack, plus 2 A.
      - **R43/R46 3.32 k → 2.21 k** (RT0603BRD072K21L). The CT band is 64.55–76.09 A.
      - **FETs at the new high corner:** worst turn-off current 178 A, against I_D,pulse 495 A (2.78×) and D-31's tested 330 A. CT flux is 46 of 638 V·µs.
      - **audit.rs:** 77/77, with two new tests that fail the stage-14 values.
    - **Copper** (outline edits, no part moves; `patches21.S15_ADD/S15_TRIM`):
      - SW_A's leg to T1 goes from 6.99 to 10.8 mm.
      - SW_B gains the y 46.8–50 band at the bank and 0.4–3.8 mm off the l_filt edge.
      - Proposal P-B2 is not taken: its l_filt trim cuts that mains pour in two.
      - SW_B beside the FETs (x 31–76) and SW_A's low-side link (2.83 mm over the Q3.S / Q2.D pads, now modelled as task 04 case `sw_a_low`: 6.69 mΩ against 3.82 mΩ for the high side) stay as they are.
    - **Gates:** DRC 0 / 0 / 0; barrier gates 0; D5 8.047 / 8.507 mm; fit 0; DFM PASS; Gerber review PASS; BUS_P span 4.130 %.
    - **B3 at the ceiling** (`b3/ceiling_sweep.py`, h 25, 1.05 × ceiling):
      - 22 / 24 / 26 A: board peak 133.4 / 133.7 / 133.9 °C, at the same parts as nominal operation.
      - **28 A: 142.0 °C**, in the FET-row tank copper (x 30–77, y 0–12), which becomes the board peak.
      - **Call:** this board supports a commissioned ceiling of **26 A**. 28 A requires either the FET-row rework (stage 15b: first the C56 gate-return via out of the SW_B lane, then R5 north; this re-opens the F6 / task 01 loop work) or bench IR of that copper at 28 A.
      - B3 changes: the bank rows are now TDK B32654 (ESR_typ 19.3 mΩ, tan δ limits, p.23 / p.35, board fraction 0.3). The "extreme" case is now the 29.4 A firmware trip instead of round 3's 44.7 A grid extreme.
    - **Firmware** (branch `fw/stage15-tank-ceiling`, `35fa8fe23` + `f582832a3`, host tests 23/23):
      - The trips are derived from the commissioned ceiling: 22 A by default, Kconfig up to 28 A.
      - Per-pan frequency loop with live PWM retime; the power request is tracked within ±6 %.
      - A no-pan clamp holds 22 A or less.
      - The peak ratio caps the effective ceiling at 27.2 A until the bench calibrates it.
      - **Not for the stage-14 board:** its CT corner at 50.56 A sits under the 50.7 A firmware peak trip.
      - The minimum continuous power is about 73–175 W at 60 kHz, so burst mode is open item H12.
    - **Open:**
      - the pickup basis C (any-phase stack, 70.48 A floor) closes on the bench at 45–55 kHz;
      - ~~bank over-voltage in a CT-failed double fault~~ **closed 2026-10-12** (`validation-results/02-protection-timing/bank-ov-double-fault/`, verdict INCONCLUSIVE as a bare number, accepted as follows). Bank: 5 × TDK B32654A1104K000, 1600 V DC rated, 2560 V factory test; TDK gives no single-event figure.
        - With the CT trips (and the CT-fed firmware peak/RMS trips) dead, only the shunt OCP (≤ 118.74 A) is left. Driven open-loop down to 15 kHz, the bank reaches 1702.4 V (1.064 × V_R).
        - The firmware already holds f ≥ 35 kHz in two places: `tank_freq` rejects configs with f_min < 35 kHz, and `n21_binding` refuses any retime below f_min before `pwm_update`.
        - With that floor, the CT-failed + loop-runaway case peaks at 1494.8 V (time-domain) and 1178.4 V (quasi-steady), both under 1600 V.
        - Getting below 35 kHz needs a third, independent fault (MCU program-flow or corrupted timer config) on top of the CT failure. That is outside IEC 60335-1 19.11's one-fault-at-a-time analysis, and even then the 1702 V stays under the 2560 V factory test.
        - No hardware change. Owner item (non-blocking): ask TDK for the single-event over-voltage rating of B32654A1104K000.
14. **Stage 15b: the board thermally supports the 28 A ceiling (2026-10-10, board `9a9c43c6…`, copper.json `a831e90c…`; study `validation-results/04-board-current-thermal/round5-native21/stage15b/`).**
    - **Root cause of stage 15's 142.0 °C at 28 A:**
      - **Mostly a B3 meshing artefact.** At the 1.0 mm mesh, the cell at (76.5, 9.5) has no copper, yet it received A4 copper heat from a pour edge inside it.
        - The energy-conserving fix (`stage15b/b3-model/thermal_snap.py`) puts the stage-15 FET row at 136.6 °C.
        - That result depends on the mesh: 126.9 °C at 0.5 mm and 128.6 °C at 0.25 mm.
      - **The real driver is SW_A's low-side path:** the B.Cu leg-A link (2.83 mm over the Q3.3 / Q2.2 keep-outs) and the F.Cu neck right of Q2.3.
    - **Fix c2h** (patches21 `S15_ADD/S15_TRIM`; no part moves; inner layers, R5, C38/C40 and the gate loops untouched):
      - the leg-A link's top goes 12.5 → 13.5 over x 50.5–70, and SW_B's lane bottom goes 15.7 → 16.7, keeping the 3.2 mm gap and stopping short of the C55 tie via;
      - the Q2.3 / BR1.1 F.Cu corner is filled.
      - **Task 01 / F6 stay closed.** The commutation-loop conductor widens only on its far edge, so a re-extraction is optional confirmation.
    - **Paths:** sw_a 3.75 mΩ, sw_a_low 6.37 mΩ (was 6.69), sw_b_high 6.65 mΩ (+1.2 %).
    - **Gates:** DRC 0 / 0 / 0; barrier gates 0; D5 8.047 / 8.507 mm; fit 0; DFM and Gerber review PASS; Kelvin 66.37–118.74 A (floor met at the bound).
    - **B3, committed thermal.py, h 25** (`b3/ceiling_sweep.py`): 22 / 24 / 26 / 28 A → 133.4 / 133.7 / 133.9 / **134.1 °C**, all at U26, the nominal peak part. **28 A is thermally supported.**
    - **Still open:**
      - h 10 (fan failure): the FET row is 198 °C at 28 A. The blower stall detection and derate own this (controller L3).
        - **Checked 2026-10-12** (`round5-native21/h10-stall/`, rerun reproduced).
          - The stall response owns the FET row: 92.8 °C at a 25 % hold, 65.1 °C stopped.
          - The lumped bound gives a true sink peak of 96.5 °C, under the 98.3 °C trip low corner, and a worst-FET Tj of 130.7 °C (≤ 140.6 °C across 36 sensitivity runs).
          - A persistent 25 % hold leaves the U42 pad cell at 152.6 °C, 2.6 K over the 150 °C limit; at 15 % or below it is ≤ 149.4 °C.
          - **Decision:** `BLOWER_STALL_POWER_CAP_PCT` goes from 25 to 10 % (149.1 °C). The hold only bridges the 8–23 s before the 2 K rule stops the tank.
          - The idle h 10 board (148.7 °C) is pessimistic: the bias rows are held at their 28 A values while the bridge is stopped. Bench IR at h 10 confirms it.
      - At the 0.25 mm mesh, R5's pad cell is 149 °C at 28 A (nominal 140 °C), which predates 15b. R5 runs at 0.86 W of its 1 W rating, so its derating needs a check.
        - **Checked 2026-10-12: FAIL** (`round5-native21/r5-derating/`, rerun reproduced).
          - WSK25121L000FEA (Vishay 30108) is 1 W at 70 °C, derating to 0 W at 170 °C.
          - 0.864 W is the dissipation at the 29.4 A trip; at 28 A it is 0.784 W.
          - With the pads at 149.2 °C max / 122.7 °C mean, the derated rating is 0.208 / 0.473 W.
          - The TCR keeps the trip floor: the low edge is 65.49 A against 64.17 A.
          - Item 4's fallback (a ≥ 2 W four-terminal shunt) is taken: stage 17, plan in `round5-native21/stage17-r5/`.
          - Item 4's "local ambient ≤ 100 °C" gate was too loose for this part.
      - Lead conduction to the heatsink is −5.6 / +0.5 K (ZVS / conservative switching). Its sign closes with the bench switching-loss measurement.
      - Bench list: FET-row IR at 28 A.
15. **Sink contingency and blower supply at 28 A (2026-10-12; enclosure R33 studies 10 and 11).**
    - **Sink load at 28 A** (round 6 `board-side-fets.csv`): basis A is 132.8 / 141.3 / 149.9 W at 40 / 45 / 50 kHz; basis B (ZVS) is 67.8 W. S8 plus the Delta BFB1012VH-F00 blower holds about 130 W at the 88.6 °C base.
    - **K1 sink:** skived or bonded fin, 1.0 / 2.5 mm, 20 fins, in S8's envelope. R_SA 0.214 °C/W holds 150 W at 0.75 drive.
      - Tj at K1, basis A, worst FET: **118.9 / 123.8 / 128.7 °C** at 40 / 45 / 50 kHz.
      - **Trigger:** keep S8 for the prototype. Go to K1 if the bench switching-loss measurement puts the 28 A sink load above **125 W**, before the commissioned ceiling rises past 26 A. K2 (2.0 mm gap) only if K1 measures short.
    - **Blower supply:** the blower is BFB1012VH-F00 (12 V, 1.42 A typical / 2.70 A maximum, 17 / 32.4 W). The coil at its 196 W acceptance limit needs about 0.9 drive, so the rail is budgeted for full speed: 33.5 W plus start-up.
      - That overloads PS1 (IRM-20-15) through the controller's blower buck, so **a separate blower supply** goes on the power board (stage 16, planning). Blower start or stall then cannot brown out the controller logic.
    - **Coil and rim NTCs:** Semitec 104GT-2 (GT-2 sheet p.18): Ø1.35 ± 0.15 mm glass bead; 100 kΩ ±3 %; B 4267 K ±2 %; −50…+300 °C; 0.6 mW/°C. Mounts are in enclosure R40. Rim self-heating is about 2.6 K at 250 °C, in the safe direction.
16. **Stage 16: separate blower supply (2026-10-12, board `e9481ed6…`, copper.json `4d062fd6…`; plan `validation-results/08-manufacturing-package/native-21/stage16-blower-supply/PLAN-16.md`).**
    - **PS3 = Mean Well IRM-60-15ST:**
      - 60 W, Class II, 62368-1 / 60335-1;
      - IRM-60-SPEC 2025-11-21: 109 × 52 × 33.5 mm, 4 × Ø3.5 holes on 98 × 33;
      - chassis-mounted at enclosure world (−139, 95) (R41).
      - It feeds the controller's blower buck through J13 (B2P-VH, controller (88, 86)). PS1 drops to about 4.8 W of its 21 W.
    - **Rejected options:**
      - a direct 12 V rail: the buck can't make 12.4 V from it, and PWM-ing a 3-wire blower's supply loses the tach;
      - upsizing PS1: it displaces 7–10 parts and keeps the blower on the logic rail.
    - **Power board:** a fused mains tap only.
      - **F2** (Schurter UMT 250 3403.0171, 3.15 A T, 200 A at 250 VAC) at (266.5, 118.4) takes L_FILT to the new net `blw_l`. **J11** (B2P3-VH) at (266.5, 125.8) carries blw_l / N_FILT.
      - blw_l is its own MAINS group (F2 can open). The three 1.0 mm tap tracks were laid by the router. No part moves.
      - Audit 78/78, with a new test failing F2 ahead of the filter, a J11 that bypasses F2, or the wrong fuse.
    - **Gates:** DRC 0 / 0 / 0; barrier21 and the Rust gate 0; D5 8.047 / 8.507 mm (unchanged); fit 0; DFM and Gerber review PASS; Kelvin 66.37–118.74 A; B3 at 28 A 133.9 °C (U26).
    - **Open:**
      - F2's breaking capacity is under the prospective fault at 127 V + 10 %. F1 is the backup; this is a certifier item, as F1 was.
      - Blower start current (bench G-B1).
      - The F2 height envelope is a 4.0 mm estimate (no 3D model).
      - **Inlet budget** (firmware `blower_aux`, merged 2026-10-12): PS3 is counted, scheduled from the blower drive. The allowance rises before the fan speeds up and drops to the worst case on an unknown drive, a fault or full speed.
        - Tank hold at 108 / 120 / 132 V, out of the 13.5 A regulated total:

          | Blower | Hold | Tank power |
          |---|---|---|
          | Off | 11.05 A | 1109 / 1233 / 1356 W |
          | Typical (drive 0.5) | 10.43 A | 1047 / 1164 / 1280 W |
          | Full | 9.94 A | 998 / 1109 / 1220 W |

        - The 1239 W hold of item 10 is met only with the blower off. With the blower running it is 6–10 % lower.
        - The round-6 yield figures assumed 11.1 A. The bench (COMMISSIONING step 8c) replaces the V³ model constants.
      - Controller: done on controller-layout (6e4cac49f, 2597045de; controller DECISIONS C33). J13 B2P-VH at (88, 85.65), confirmed by the enclosure session for R41; J13 pair 18 AWG (matches the JST 7 A AWG18 rating used in the controller check).
      - Firmware: BLW_PG on expander P16 (fw/blw-pg 21f053a15, merged).
        - A debounced PS3-absent blocks heating start ("NO BLOWER PWR").
        - A blower stall while driven is labelled "PS3 absent" or "blower failed"; both take the C28 derate and `FAULT_FAN_FAILURE`.
        - BLW_PG low while the tach turns latches a sense fault; BLW_PG is then ignored.
        - The PS3 inlet allowance is never reduced on BLW_PG = 0.
      - Accepted: if PS3 drops mid-cook while the fan law has the blower off (sink and coil below 50 °C), nothing derates until the fan law asks for the blower. The stall path then fires within about 1 s, far below the 88.6 °C fan setpoint and the 101.4 °C hardware trip. Derating directly on BLW_PG would let a stuck-low sense line derate falsely, and it cannot be checked for plausibility while the blower is idle.
      - Bench: a BLW_PG stuck low blocks starts until serviced (the conservative side). COMMISSIONING checks P16 high with PS3 on and low with it unplugged.
      - Enclosure R41 (temper-f7, `output/temper-manufacturing-r41/design/r41/DECISIONS.md`, `evidence/ps3/ps3-clearances.json`):
        - PS3 moved to (−139, 98), case Z36.5–70 (was (−139, 95), Z32.5–70), on an earthed 2.03 mm 5052 shelf bracket clearing native-21's parts up to Z30.4.
        - Clearances after the IRM-60-SPEC p.4 block model (blocks as scaled housings): DC block to HOT 9.01 mm (≥ 8), AC block to HOT 6.39 mm (≥ 3.2), AC block to SELV 40.0 mm (≥ 8), J13 pair to HOT 8.65 mm (≥ 8), J11 lead to SELV 15.8 mm (no sleeve needed), bracket to native-21 parts 2.93 mm (≥ 2.0 basic).
        - The DC-block margin is 1.0 mm against a block size scaled from the drawing (±2 mm): measure a PS3 sample before the enclosure release.
        - Screws: 4 × ISO 4762 M3×10 in PEM CLS-M3-2 nuts (M3×12 would come within 1.1 mm of native-21's parts).
      - Enclosure R42 (`output/temper-manufacturing-r42`, `evidence/ps3/check_ps3_retention.py`) adds cable ties at the J11 anchor and at both PS3 blocks. With each conductor end freed at its terminal, the margin to the other voltage class is +4.5 mm at J11, +33.1 mm at PS3 AC and +6.1 mm at PS3 DC.
        - **J13 end (decided 2026-10-12):** no tie fits there; the exit is 10.75 mm from the native-21 HOT block.
          - Primary: an insulating barrier (polycarbonate or Formex GK class, ≥ 0.4 mm, UL94 V-0, ≥ 105 °C). It is mounted on the enclosure or a standoff and sized so that a freed end's path around its edge to HOT is ≥ 8 mm. Modelled in R43, with the retention check extended.
          - Secondary basis for the certifier: the latched VHR housing plus the crimp.
        - Bench and R43: the mains lead runs 315 mm unsupported at 4.99 mm from the native-21 envelope, and its sag is not modelled. Add a mid-span tie if SELV parts lie there.
        - **R43 (closed):** the barrier is R43-J13-BARRIER, Formex GK-62, 1.575 mm, at X60–124, Y92.2–93.8, Z11–56, snapped into base slots. It also carries tie T_J13 through a die-cut slot 1.0 mm above the plug.
          - With the tie, the freed end stays ≥ 18.5 mm from HOT (geodesic); the flag alone would fail at 228.7 mm against the 297.4 mm needed.
          - ITW lists GK-62 as UL94 V-0 with an RTI of 115 °C.
          - Modelled flag temperature: 62 °C expected (40 °C kitchen), 96 °C with all allowances stacked (`output/temper-r33-studies/14-j13-flag-thermal/`).
          - Conditions:
            1. Yellow card for GK-62 (owner).
            2. Heat-stabilised PA66 tie rated ≥ 120 °C.
            3. Bench soak at 40 °C and 28 A, with thermocouples on the PS1 face, on the flag at the tie and in bay air, plus a 10 N hot pull test.
          - The span is HOT-to-HOT, 11.1 mm from SELV after worst-case droop, so it needs no mid-span support.
          - **PS1 margin:** the IRM-20 derating allows 5.4 W at the modelled 78 °C bay air, against the controller's 4.83 W (controller verify `ps1.p_total_W`). That is only 11 % margin. If the soak shows bay air above ~78 °C, PS1 moves to a cooler spot or goes up to the IRM-30 class.
          - Certifier question: can the courtyard of potted PS1 be replaced by its pins and solder joints as the clearance reference? Until the certifier answers, the conservative envelope stays.
        - Harness: J13 pair 2 × UL1007 18 AWG, 292 mm. J11 lead 2 × UL1015 18 AWG, 322 mm; its tie points move to R42.
        - The controller's J13 drop is rebased on contacts and copper at 80 °C: 172 mV, U2 headroom 0.92 V (controller-layout 0207a6974).
        - Coil field at PS3: 453–573 µT rms at the coil-side corner (study 12). Added bench item: PS3 ripple and stability at 28 A.
    - **Gate scripts** are now committed in `native-21/layout/gates/` (the scratchpad copies were lost).

17. **Stage 17: R5 = Bourns CSS2H-2512R-1L00F (2026-10-12, commit `65160f4b3`, board `e40f1e27…`, copper.json `4b6a5262…`, Gerber ZIP `b60ef50c…`; superseded as the board of record by 17b below: commit `866282334`, board `96501e7d…`, copper.json `b2107cd0…`, Gerber ZIP `897e581e…`; plan and evidence `validation-results/04-board-current-thermal/round5-native21/stage17-r5/`).** The gate values below are stage 17's; 17b lists the ones that moved.
    - **Why:** item 14's check failed the WSK25121L000FEA (0.864 W at the 29.4 A trip against 0.2084 W derated at 149.16 °C), and it has no JLC / LCSC stock. Item 4's fallback, a ≥ 2 W Kelvin shunt, is taken with PLAN-17's rank-1 part. BVS-M-R001-1.0 stays the unused fallback.
    - **Part:** Bourns CSS2H-2512R-1L00F, LCSC C4175647 (JLC Extended, 1,482 in stock on 2026-10-12). 1 mΩ ±1 %, 5 W at 70 °C terminal (linear to 0 at 170 °C), ±75 ppm/°C, AEC-Q200, H 0.78 mm max.
      - It stays 1 mΩ, so R34 12.6 k / R35 11.7 k, the reference and the CT dividers are unchanged.
    - **Land** (`libraries/temper.pretty/R_Shunt_Bourns_CSS2H-2512_Kelvin.kicad_mod`, measured from the datasheet p.2 drawing at 600 dpi):
      - two 1.80 × 3.40 mm current pads (pads 1 LEG_RET / 4 HV_RET) with a 3.40 mm gap;
      - a 0.40 mm sense lobe from each pad's inner edge into a 0.40 mm finger (pads 2 OCP_KELVIN_P / 3 OCP_KELVIN_N), 0.60 mm apart, running 1.50 mm past the pads to the west;
      - fingers net-tied to their current pad in the footprint (`net_tie_pad_groups`); the netlist keeps four nets. Pad numbers and nets are the WSK's, so audit.rs pin checks and `kelvin_plane.py` (sink R5.2) stand.
    - **Source:** `parts.ato` Shunt1m (MPN, maker, footprint); frozen exports from atopile 0.2.69, path-normalised to the ps-integrate tree (only R5's lines change; netlist `bd395b0b…`); `verify_source.py` asserts the MPN and footprint (353 parts); `audit.rs` **79/79** with a new test failing the WSK identity, and its footprint test now fails the WSK land (`stage17-r5/audit17.txt`).
    - **Copper** (`patches21.add_stage17`; no part moves):
      - The Kelvin pair leaves R5 as a tight pair from the finger tips (vias at (35.0, 12.1) / (35.0, 13.1)), runs on In1 under R5 to the stage-16 KP_MID / KN_MID, and keeps the stage-16 route from there (incr21 drops the old run as stale once R5's pads change; the patch re-lays it unchanged).
      - add_r5 judges R5's custom sense pads on their true outline (GEO knows only their bounding boxes).
      - Vias: LEG_RET 10 (unchanged count); HV_RET 6, was 9 (the pad's east half sits within 3.2 mm of SW_B's B.Cu lane, and the N finger takes the old north row). Worst R5 via at 34 A coherent: 8.78 A (was 7.27).
    - **Gates (board `e40f1e275bbaff8a5e61e224974fd401a44bcad2acefa0b92d50f85b6ce81ecd`):**
      - DRC 0 errors / 0 unconnected / schematic parity 0; plane splits 0 (warnings as stage 16, 9 dangling-track warnings).
      - barrier21 0; Rust barrier gate 0 violations over 5,626 items (existing `target-shared` binary, not rebuilt).
      - D5: HOT–SELV 8.047 mm, HOT–PE 8.507 mm (unchanged).
      - JLC DFM PASS (759 vias, 120 plated pads, minimum track 0.2 mm); Gerber review PASS (875/875 round holes + 4 slots; 0 silk on land); R5 box rendered from the Gerbers (`stage17-r5/r5-gerber-review.png`): paste only on the current pads, fingers mask-open.
      - Enclosure fit: 405 solids, 0 overlaps, 407 bodies in R4, 0 hits. R5 is a 0.78 mm envelope (no 3D model), z 1.6–2.38 mm, +0.13 mm over the WSK.
      - Kelvin (`budget-native21s17.json`): R35.2 157.80 mΩ (was 161.03), shift −2.17 A (bound −2.23 A).
      - OCP band (`stage17-r5/ocp_band17.py`, R5 at 75 ppm/°C; the 250 ppm control reproduces 68.58–118.74 A): 69.89–116.44 A before the Kelvin shift, **67.72–116.44 A after**, 67.66 A at the bound. Floor 64.17 A met (+3.49 A).
      - B3 (h 25, 1.0 mm): 22 / 24 / 26 / 28 A → 130.2 / 131.1 / 132.1 / **135.9 °C**. 22–26 A peak at U42; **28 A now peaks at R5.4** (stage 16: 133.9 °C at U26). Nominal h 10 / h 25: 163.2 / 129.1 °C. BUS_P span 4.129 %.
    - **G6, R5 derating (go/no-go): PASS** (`stage17-r5/g6.json`, `g6_r5_derating.py`; c28, 0.25 mm, h 25, 50 °C):
      - Heat: 0.864 W at the 29.4 A trip, on the current pads only (`thermal.py` `pad_numbers`; the fingers are not part terminals).
      - R5 pad cells: 134.81 °C max, 125.99 °C mean. Derated 1.759 W, so **margin 50.9 %** against the 20 % rule (a 20 % margin needs ≤ 148.4 °C). Worst case (1 % + 75 ppm at the pad max): 0.880 W, 50.0 %. Pad ≤ 160 °C; trip floor 67.48 A with the B3 rise.
      - Controls: the WSK's FAIL (0.864 W against 0.2084 W at 149.16 °C, −314.7 %) and the stage-16 solve (149.16 °C) both reproduce.
      - Sensitivity: heat on all four pads gives 134.34 °C (51.5 %). The stage-16 WSK board with heat on its current pads only is 123.43 °C, so most of item 14's 149 °C was heat put into the WSK's isolated sense pad. The WSK still fails there (0.47 W derated); the swap stands.
    - **Not re-run:** the commutation-loop FEM (PLAN-17 G8). The land span shrinks 8.26 → 7.0 mm on a return-path part with parallel copper; F6 stays closed on that basis until the next extraction.
    - **Found:** U26 reads 7 K lower than in stage 16 (126.1 against 133.0 °C, nominal h 25) with identical copper near it. The In1 `n_ls LS block` and `ocp_kelvin_p protection` pours have the same priority and abut at y 75.3, so the 0.3 mm boundary strip goes to whichever fills first. It is rebuild fill order, not stage 17. **Closed in 17b** (n_ls declared the winner; U26 126.1–127.4 °C on every build).
    - **Records:**
      - `round3/thresholds.py` keeps the WSK tuple as its default, because eight committed band records import it; it adds `SHUNT_CSS2H` for stage-17 and later calculations.
      - Item 4's "local ambient ≤ 100 °C" gate is superseded by G6's terminal-temperature rule. Item 14's "0.86 W at 28 A" is the 29.4 A trip value (0.784 W at 28 A).
      - The CPL centroid of an SMD part with paste-free pads now comes from its pasted pads, so R5 stays at (38.5, 12.6); no other placement moved.
    - **Open, Bourns (owner; not contacted):**
      - the rating basis: which point of the copper terminal "terminal temperature" means, and whether the older 5 W / 3 W two-curve copy still applies;
      - where the part's own sense contact sits relative to the recommended fingers, which leave the pad lobe, so lobe copper is in the sense path;
      - the element-to-terminal thermal resistance (no figure in the datasheet).
    - **Open, other:**
      - JLC placement preview of C4175647 on the project land (rotation and centroid);
      - bench IR of R5 at 28 A.
    - **17b, deterministic pour fill and the R5 via check (2026-10-12, commit `866282334`, board `96501e7d0e9b4903a145aa3bd0e45003a4fafe37ceef5259a7502bc9b11225a9`, copper.json `b2107cd0…`, Gerber ZIP `897e581e78db51731264589f028ff2f2933d8b2a916012eeb4656fc42b556b9a`; design-lead review follow-ups):**
      - **Fill order.** Seven different-net pour pairs were closer than their clearance at equal priority, and three more sat exactly at it. KiCad's fill order then chose the contested copper.
        - Between stages 14 and 17 that flipped In1 n_ls / ocp_kelvin_p (3.5 mm²) and four B.Cu pairs: sw_b / res_a at the bank (48 mm²), sw_a / sw_b, l_filt / sw_b and res_a / coil_feed.
        - `patches21.ZONE_WINNERS` now names each winner: In1 n_ls over the Kelvin pour (review call); the rest keep stage 15b's fill, the board item 14 accepted for 28 A. `resolve_zone_priorities` raises only what it must, keeping every existing order.
        - New gate `native-21/layout/gates/zone_priority_gate.py` (run first by `chain.sh`): 25 contested pairs, 0 at equal priority.
        - Three builds (the chain build and two after deleting every build product) agree within 0.038 mm² per net (`fill_hash.py`, `stage17-r5/fill17b.txt`); stage 17's own build differs from 17b by 23.6 mm² total.
        - The copper changed only in priorities; tracks and vias are the same.
      - **Gates on board `96501e7d…`:**
        - DRC 0 / 0 / parity 0 on all three builds; barrier21 0; Rust gate 0 over 5,626 items; D5 8.047 / 8.507 mm.
        - Fit 0 (405 solids, 407 bodies in R4, 0 hits); DFM PASS (759 vias); Gerber review PASS (875 + 4 slots).
        - Kelvin unchanged: R35.2 157.80 mΩ, band 67.72–116.44 A, 67.66 A at the bound.
        - B3 h 25: 22 / 24 / 26 / 28 A → 130.2 / 131.1 / 132.1 / **136.0 °C** (22–26 A at U42, 28 A at R5.4).
        - **U26 126.3 / 126.6 / 127.0 / 127.4 °C**; R5 115.5 / 121.8 / 128.6 / 136.0 °C (1.0 mm). Nominal h 10 / h 25: 163.2 / 129.1 °C.
        - **G6 PASS:** R5 pad cells 134.87 °C max / 126.03 °C mean (0.25 mm), 1.757 W derated, **margin 50.8 %**. The WSK FAIL and stage-16 149.16 °C controls reproduce.
      - **R5 HV_RET via current** (`stage17-r5/r5_vias17.py`, `r5_vias17.json`).
        - The criterion is `validation-plan/04-board-current-thermal.md:114`: report the maximum per-via current and the via temperature rise; > 3 A is a flag, not a fail; there's no rated limit.
        - Round 5 (`round5-native21/README.md:37-47`) accepted stage 6's 7.27 A (7.7 A per mm of barrel) as the coherent 34 A experiment; nothing in DECISIONS sets a limit.
        - Worst via (38.1, 15.0): 8.78 A at 34 A coherent (9.32 A/mm), 7.59 A at the 29.4 A trip. Barrel Joule heat is 0.029 W, mid-wall 0.28 K over the planes it joins.
        - Its B3 c28 cell is 133.04 °C, so the wall estimate is 133.31 °C: under the R5 pad maximum and G6's 148.39 °C terminal bound. 10 of 18 R5 vias are flagged (> 3 A).
        - **Meets the criterion; no via change.** More HV_RET vias would need SW_B's B.Cu lane (3.2 mm rule) pulled back from under R5's east / south edges, which costs tank copper.
      - **Not fixed:** `write_rules21.py` emits its DRU rule conditions in a different order per run. Same rules, so it doesn't affect the board; noted for a later cleanup.

18. **Stage 18: RES_A to SELV/PE at 12.6 mm on the outer layers (2026-10-12, board `3768a12675f8d61f91fc4a96dd267522e68f454f8f300634aca2ae16afc6dd1a`, copper.json `e6ad813b963ce3a8fffafbc90bfa99f1cbb1ae982981c60642cc501727137a99`, Gerber ZIP `021bf8fdebcd1840a418b5dad74cf142118ca06bbe15b94aa2c0d996fb4561bc`; evidence `validation-results/08-manufacturing-package/native-21/stage18-res-a-creepage/`).**
    - **Why:** item 7. RES_A is 297 V rms / 656 V pk to earth at 28 A, so reinforced creepage at PD3 / IIIa is 12.6 mm. Every other HOT net is ≤ 250 V rms and keeps 8.0 mm (`tank_taps18.py`: CRBLEED_1 242.5 V rms with the L70 coil, 255.1 V for any L 70–90 µH; CRBLEED_2/3 ≤ 198 V; SW_A / SW_B / COIL_FEED 99 V).
    - **Change:** the SELV LINE_ZC_RAW and V15_SELV runs on B.Cu leave the bank's RES_A strip (edge y 114.0 / 112.9) for lanes at y 127.5 / 128.6 between x ≈ 137 and 187, with 45° doglegs; base geometry elsewhere, same widths, ends and vias (`patches21.add_stage18`). copper.json differs from 17b in exactly these two tracks. No slot, no part, pour or via moves.
    - **Distances (outer layers, `res_a_creepage18.py`):**

      | Pair (B.Cu) | 17b | 18 |
      |---|---:|---:|
      | RES_A – LINE_ZC_RAW | 8.145 mm | **13.375 mm** |
      | RES_A – V15_SELV | 9.400 mm | **14.400 mm** |

      F.Cu min 20.393 mm (incl. the J5 ring lug, 5 mm radius); RES_A – PE 19.204 mm. The script's `--control` on the 17b dump reports exactly the two pairs.
    - **Gates added:** `rules21.RES_A_CREEPAGE` 12.6 / `clearance_on()` (authoring and routing on F.Cu / B.Cu); a last DRU rule `RES_A to SELV/PE ... (layer outer)` at 12.6 mm clearance and creepage (control: the 17b board with its own DRU plus this rule gives 16 errors, all this rule, all on the two runs); `barrier21.py` reports RES_A per outer layer; `barrier_gate21.py` runs the existing Rust binary per outer layer at 12.6 mm on the verified evidence subset (17b: B.Cu 15, F.Cu 0); `chain.sh` runs the evidence script. `write_rules21.py` builds its groups from `sorted(nets)`, closing 17b's DRU-order item.
    - **Inner layers:** treated as solid insulation (item 7; reinforced solid insulation 2 mm per IEC 60335-1 29.3, M11). All inner RES_A copper is ≥ 8.0 mm in plan view from SELV/PE on every layer. **Certifier question added:** is a same-layer inner path a cemented joint? If not, C152.1's inner rings are 9.694 mm from the In1 v3v3 / In2 selv_gnd islands (needs ~3 mm pull-back or ring removal).
    - **Straddling parts (datasheets read, not committed):** no footprint joins RES_A and SELV/PE. T1 CST3015-100ED is on the SW_A end of the coil (99 V rms / 198 V pk): Coilcraft states reinforced, ≥ 8 mm creepage/clearance, 5 kV rms 1 min, but no working voltage, CTI or HF / PD rating, so PASS at its own voltage and HF rating stays a Coilcraft question; it would not meet 12.6 mm on RES_A. UCC21550 / ISO7710 / AMC1311: reinforced, VIOWM 1500 V rms, VIORM 2120–2121 V pk, ≥ 8 mm, CTI ≥ 600. VOL628A 8.0 mm VDE (repo record), IRM-20 Class II 4.2 kV ac: mains only. H6 (nylon) is 8.40 mm from RES_A; with the ≥ 10 mm nylon standoff the path to chassis is ≈ 17 mm. **No rating fails; no part changes.**
    - **Gates on board `3768a126…` (tag `native21s18`):**
      - zone_priority_gate 25 contested, 0 equal; DRC 0 errors / 0 unconnected / parity 0, plane splits 0 (warnings as 17b);
      - barrier21 0 (8.0 mm) + RES_A outer 0 (min F.Cu 20.393, B.Cu 13.375); Rust gate 0 over 5,626 items, RES_A outer 0 / 0 (956 / 560 items; existing `target-shared` binary, not rebuilt);
      - D5 8.047 / 8.507 mm; fit 405 solids, 0 overlaps, 407 bodies in R4, 0 hits;
      - JLC DFM PASS (759 vias, 120 plated pads, 0.2 mm); Gerber review PASS (875/875 + 4 slots, 0 silk on land);
      - Kelvin unchanged: R35.2 157.80 mΩ, band 67.72–116.44 A, 67.66 A at the bound;
      - B3 h 25 22 / 24 / 26 / 28 A → 130.2 / 131.1 / 132.1 / 136.0 °C, every case within 0.01 K of 17b. G6 not re-run: no copper near R5 or any power part changed (B3 R5.4 peak 135.96 vs 135.97 °C);
      - audit.rs 79/79 and frozen-netlist PASS (rustc single file, `f46573fe79fd`); verify_source PASS (353 parts, hashes match).

19. **Stage 19: converter-local capacitors, fast-signal return paths, local bypass (2026-10-12, board `370fcf373c97241966f0bb9a077b513903354a20bcd659545819e9d363b3bd1c`, copper.json `f287dc4afc64bdf5d759fb237ae3771f71b1489268c91399e064e84c2af0ca72`, Gerber ZIP `67e1e07f594039504e6b633eb277a9ab8be2ea745711846e5892eb014cabff6b`; evidence `validation-results/08-manufacturing-package/native-21/stage19-pi-si/`).**
    - **Why:** the stage-18 review (`output/preroute-stage18-2026-10-12/REPORT.md`, `output/return-path-stage18-2026-10-12/REPORT.md`; its TH1 is withdrawn, R5 is already the CSS2H) found PI1 / PI2 (converter output and LDO caps 14–27 mm from their pins) and SI1 / SI2 (a protection signal across the In1 Kelvin / n_ls split, PWM and comparator layer changes far from any transfer capacitor). They were confirmed on this board.
    - **N1 / K6 folded in (credit: commit `365151b62`, `claude/native21-stage18-review`, the other session's work, its writers stopped):** the 11 dedicated 100 nF caps beside their ICs (C44 U10, C45 U11, C46 U12, C47 U13, C89 U24, C88 U25, C144 U40, C49 U15, C70 U29, C80 U30, C87 U31; `place.py STAGE19_MOVES`), its router links (`patches21.add_stage19`), `gates/bypass_check.py` (in `regate.sh`, fails the gate), `bypass_spots.py`, `trim_tails.py`, Q2 / C152 designators to F.Fab, the IRM-20 pin-1 override and its test-point re-plan. Applied as sources onto stage 18 (the 12.6 mm RES_A rule, the re-laid LINE_ZC_RAW / V15_SELV and 17b's pour priorities all stand); every generated file was rebuilt here, none copied (`claude/native21-stage19-review` `e89ef5467` served only as a guide). The thermal.py receipt fix (`b6d0e92f2`) is cherry-picked.
    - **PI1 (RECOM R24C2T25/R p.13: caps between VOUT+ 28/29 and VOUT- close to the IC):** each module's own HsSplit pair moves to its pins, the 1210 10 µF vertical under pin 28, the 0603 100 nF under pins 29–31; FB parts step aside (U42's FBVOUT pins drop to a via, as RECOM suggests, because U31 holds its 1210 further east). VOUT+ to cap: **U41 C104 2.88 / C75 2.79 mm, U42 C108 2.79 / C82 2.93 mm** (was 25.57 / 46.48, 26.53 / 51.79); the 100 nF VOUT- sides 2.88 / 2.86 mm. The driver-local reservoirs (C10 / C11 / C145, C17 / C18 / C147, the bias_h clusters) are separate parts at the drivers and are unchanged, so no part was added.
    - **PI2 (TI SBVS204 9.1):** U26 had U29 0.55 mm west and R31 / R35 1.1 mm north, so no cap fitted at its pins; it moves 3.2 mm east / 2.3 mm down into free board. OUT 1 → C99 **2.81 mm** (GND 5 2.81), IN 15/16 → C98 **2.62 mm**, NR 14 → C64 **1.61 mm** (was 15.39 / 14.03 / 23.06); EN 13 joins IN by a via; an F.Cu n_ls pour joins GND 4–10, the pad and the cap returns. C98's n pad sits 6.4 mm from the RES_A F.Cu strip (5.0 mm rule). The re-lay of the rails that served U26's old pins (PS2 v24_raw In1 feed, v15_ls, leg_ret, hot5) is explicit in `add_stage19_pi` / `add_stage19_si`.
    - **SI1:** bus_fault_hot leaves U8 over the In1 Kelvin pour, changes layer over Kelvin copper (a dead-end Kelvin via keeps the pour's west strip, cut off by the v24_raw trunk, as Kelvin), then runs beside the existing Kelvin return on B.Cu (0.25 mm gap) and directly under it after the return's lower 26 mm moves from B.Cu to In2 (same polyline, one via), and to U9 along the Kelvin chain. No second Kelvin path, so no Kelvin loop; R5's fingers and the pours are untouched. `return_path19.py`: **0 samples over another net (stage 18: 150 over n_ls), longest unreferenced run 1.25 mm**.
    - **SI2:** ct_zc runs B.Cu from U12.1's via-in-pad straight to J4.13: **1 change, C46 1.84 mm** (stage 18: 2, 37.15 / 14.66 mm). C14 (U2's VCCI cap, 8 mm from its pins) moves under U2's VCCI / GND pins, which also places it **2.39 mm** from the pwm_hb launch via; pwm_hb's hop over the permit / bias_bad B.Cu crossing now has its vias beside C142 (**2.00 mm**) and C47 (**2.43 mm**). pwm_lb stays on F.Cu with no via.
      - **Open:** pwm_hb's four J4-side changes (4.98 / 21.24 / 37.45 / 52.70 mm). From the SELV row to J4.7 it must cross pwm_lb's F.Cu lane and the B.Cu fan of permit / bias_bad / pwm_ha; no lane pair or via spot near an existing capacitor exists. Closing it needs three 100 nF v3v3–selv_gnd transfer caps at about (55, 129), (56, 157), (56, 175) (a schematic change) or a re-route of the SELV J4 fan; not done in stage 19. The gate lists them as open, not passed.
    - **Targets (asserted by the committed gates):** PI supply sides and the 100 nF return sides ≤ 3.0 mm (`pi_distances19.py`); bus_fault_hot on ocp_kelvin_p end to end (no sample over another net, unreferenced runs ≤ 1.5 mm), ct_zc changes ≤ 3.0 mm and ≤ 1, pwm_hb driver-side changes (y < 126) ≤ 3.0 mm and ≤ 7 (`return_path19.py`). Controls: the stage-18 board reproduces 25.57 / 26.53 / 14.03 / 15.39 / 23.06 mm and the SI1 crossing; the review's own board `dadcaad3…` reproduces its 54.39 / 37.45 / 21.24 / 37.50 mm exactly (on the integration stage-18 board the old cap row gives 48.51 / 28.50 / 1.02 / 37.15 mm).
    - **Gates on board `370fcf37…` (tag `native21s19`):**
      - zone_priority_gate 25 contested, 0 equal; DRC 0 errors / 0 unconnected / parity 0, plane splits 0; with the native-21 library tables 0 violations and 0 warnings (K6 closed);
      - barrier21 0 + RES_A outer 0 (F.Cu 20.393, B.Cu 13.375 mm); Rust gate 0 over 5,807 items, RES_A outer 0 / 0 (969 / 584; existing `target-shared` binary, not rebuilt);
      - D5 8.047 / 8.507 mm; fit 405 solids, 0 overlaps, 407 bodies in R4, 0 hits; JLC DFM PASS (746 vias); Gerber review PASS (862 + 4 slots); CPL rotation audit unchanged (276 / 10 / 47);
      - bypass_check 11/11; pi_distances19 PASS; return_path19 PASS;
      - Kelvin re-solved (the return moved to In2): R35.2 **158.08 mΩ** (was 157.80), shift −2.167 A (bound −2.237 A), band 67.72–116.44 A, floor 64.17 A met at the bound;
      - B3 h 25 22 / 24 / 26 / 28 A → 130.2 / 131.1 / 132.1 / **136.0 °C** (22–26 A at U42, 28 A at R5.4), as stage 18 (reported as-is; the thermal-model study follows). U26 pad-cell max 85.7–86.9 °C (stage 18 126.1–127.4, one hot cell; the nominal mean moved 83.7 → 81.7 °C). Nominal h 10 / h 25 163.2 / 129.1 °C;
      - G6 re-run: R5 pad max 134.86 °C, margin 50.8 %, PASS;
      - audit.rs 79/79 and frozen-netlist PASS; verify_source PASS (353 parts; no schematic change).
    - **19b, pwm_hb transfer capacitors and bias_bad (2026-10-12, board `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`, copper.json `ce49f20024545fe28f104e72f69c0d1362227a15145b3a1c3bd4b915199b6cf2`, schematic `e6993fa4…`, frozen netlist `8a7e1c4a…`, Gerber ZIP `c9eaf0d96091662cd25d0ef5a2d78e972f6123e1a1b4cb1c6d85804922e80ea3`; tag `native21s19b`; design-lead follow-up to 19's open item):**
      - **Change (schematic):** four 100 nF v3v3 ↔ selv_gnd caps `c_ref_xfer_1..4` = C153–C156 (`elec/src/power_stage_120v.ato`; same part as C47, YAGEO CC0603KRX7R9BB104, LCSC C14663, joining that BOM line: 92 lines, 357 placements). Frozen exports rebuilt with atopile 0.2.69 offline (`tools/build_source.py`), path-normalised to the ps-integrate tree; the netlist diff is the four parts and their two nets only. `verify_source.py` 357 parts + MPN check; `audit.rs` IDENTITY and per-pin expects plus a new test (rewire / wrong part must fail): **80/80**.
      - **Placement / copper:** one cap beside each of pwm_hb's four J4-side layer changes (`place.py STAGE19B_XFER`), at spots where both planes (In1 v3v3, In2 selv_gnd) lie under the cap, each pad with its own plane via (`patches21.plane_via`, 0.85–1.51 mm). The 4.98 mm change at (38.955, 127.075) got the 4th cap (C153, 2.72 mm): the nearer free spots are off the SELV pours (band edge, y < 126.5) or leave no via room (permit / bias_bad B.Cu, the 8 mm barrier). pwm_hb's route is unchanged.
      - **pwm_hb, every change now:** C14 2.39, C142 2.00, C47 2.43, **C153 2.72, C154 1.12, C155 1.12, C156 1.12 mm** (stage 19 J4 side 4.98 / 21.24 / 37.45 / 52.70; stage 18 7.99 / 10.69 / 8.17 / 3.12 / 1.02 / 28.50 / 48.51). `return_path19.py` now asserts every pwm_hb change ≤ 3.0 mm and the four caps' pad-to-plane-via ≤ 1.6 mm: PASS.
      - **bias_bad: left, recorded.** It is driven by U40 (SN74LVC1G17, push-pull; TI SCES351 tpd 1.5–4.6 ns at 3.3 V, 15 pF), so its edges are ns-class, not slow. It changes state only on a bias-rail fault (ms-scale rails, 10 µs RC + Schmitt ahead of U40) and at power-up, and its loads (U22 / U23 dis_or) can only assert the drivers' DIS, so a disturbance at a remote reference change can only add a ns-scale disable: the fail-safe direction, and not a repeating emission source. Its 7 changes (2.81–15.76 mm) and a 22 mm B.Cu stretch at the SELV band edge (y 127.2, x 44–66) stay reported, not asserted; treating it like pwm_hb would take ~6 more caps or moving it to F.Cu through the J4 fan. bias_bad_raw (before the RC) is the same.
      - **Gates on board `b19a4553…`:** zone priority 25 / 0 equal; DRC 0 / 0 / parity 0, with library tables 0 violations / 0 warnings; barrier21 0 + RES_A outer 0 (F.Cu 20.393, B.Cu 13.375 mm); Rust gate 0 over 5,829 items, RES_A outer 0 / 0 (992 / 589); D5 8.047 / 8.507; fit 409 solids / 0 overlaps / 411 bodies / 0 hits; DFM PASS (753 vias); Gerber review PASS (869 + 4 slots); CPL rotation audit 280 / 10 / 47 (the four caps OK); bypass 11/11; pi_distances19 PASS (unchanged); return_path19 PASS; audit.rs 80/80, frozen netlist PASS, verify_source PASS (357).
      - **Kelvin / B3 / G6:** copper differs from 19 only in selv_gnd / v3v3 (the caps and their vias) and one 3-segment In2 re-route of ocp_thresh at x 114–120, y 74.9 (router order; same ends, not a Kelvin net). Kelvin re-solved anyway by the chain: identical (R35.2 158.08 mΩ, band 67.72–116.44 A). B3 identical (28 A h25 136.0 °C at R5.4). G6 not re-run: no copper near R5 or any power part changed.
    - **19c, leg A's VCCI cap under U1: the benchmark board (2026-10-13, board `3d3a2c69c07a210262f0dc66789a2631e29370f6816c45869a7dea1813460d92`, copper.json `de81613da1d940b06b3ca1fb7ca6f129ea64fdfa785b5401d2b45d3e7895406d`, schematic and frozen netlist unchanged from 19b, Gerber ZIP `13a89376905c94bcb38aa581233de73ad994fde5824e4367c65cdbfd2bb158de`; tag `native21s19c`; rubric finding F9, `validation-results/09-rubric-review-s19b/`):**
      - **Change (placement only):** C7 (`leg_a.c_vcci`) moves from 8 mm below U1 to under its VCCI / GND pins 3 / 4 (`place.py STAGE19C`, (78.075, 57.85)), as C14 under U2 in stage 19. No part is added; the BOM and placements are unchanged.
      - **Result:** pwm_ha's driver-input change is 2.11 mm from C7 (19b 7.59, from C54) and pwm_la's 1.84 mm (19b 5.11). The routing passes re-laid pwm_la's dogleg round C7.
      - **Gate:** `return_path19.py` now asserts the transfer distance and plane continuity of every PWM input as well as ct_zc. The same gate FAILS on 19b (`stage19-pi-si/control19c-on-19b-return-path.txt`): that is the negative control.
      - **Not asserted, recorded:** permit, bus_fault, bus_fault_iso and the bias_*_bad lines. They change state only at start / stop or on a fault, and every disturbance can only disable the drivers. permit (6.0 mm), bias_bad (22.25 mm) and bias_ha_bad run over the plane void at the U32 / U33 isolation gap, where both SELV planes keep their clearance to the HOT side. Moving that bundle would re-lay it round U33 for no emission benefit; their susceptibility is the receivers' filtering (rubric OTT-27), not transfer caps.
      - **Gates on board `3d3a2c69…`:** zone priority 25 / 0 equal; DRC 0 / 0 / parity 0, with library tables 0 / 0 / 0; barrier21 0 + RES_A outer 0 (F.Cu 20.393, B.Cu 13.375 mm); Rust gate 0 over 5,837 items; D5 8.047 / 8.507; fit 409 / 0 / 411 / 0; DFM PASS (751 vias); Gerber review PASS (867 + 4 slots); CPL rotation audit 280 / 10 / 47 (C7's corrected-CPL row moved); bypass 11/11; pi_distances19 PASS; return_path19 PASS; audit.rs PASS, 80/80; the 7 router tails `trim_tails.py` reported were trimmed before the final chain. Kelvin identical (R35.2 158.08 mΩ, 67.72–116.44 A); B3 identical (28 A h25 136.0 °C at R5.4).
      - **Test points:** TP15 (pwm_la) moved to (81.2, 104.3) and shares its reference pad, so there is one reference TP fewer (14).
      - **Benchmark:** 19c is the board every simplification / improvement candidate is graded against (owner, 2026-10-13). Card, acceptance rule and the deficits it carries: `validation-results/10-benchmark/`; item 22.
20. **Conducted EMI on stage 19b (2026-10-12; `validation-results/07-conducted-emi/s19b/`, rerun reproduced bit-for-bit). Verdict: INCONCLUSIVE, updated 2026-10-13 to PASS.**
    - **2026-10-13 update (enclosure study 16):** coil-to-PE capacitance is 31.0 pF with the pan floating (28.5–35.1; +20 pF bound for board copper) and 91.4 pF with the pan earthed.
      - With these inputs the worst margin is 10.5 dB nominal and ≥ 6.5 dB in every sensitivity, so the verdict is **PASS**.
      - **Condition (rubric review 2026-10-13, OTT-18):** the PASS assumes the inlet module at ≥ 100 µH DM (18 µH + 2 × 41 µH). The 41 µH parts have no MPN; the D-22 module as specified (18 µH) gives −5.1 dB, board-only −39.3 dB. A one-sided 100 pF coil-to-PE split gives −0.8 dB, so the bench measures the split. Selecting the module parts is required before any EMI claim.
      - Pan earthed through a user (informational, not a compliance setup): 1.7–2.6 dB at 60 kHz. The shield / CM choke reserve stays, and the bench adds an earthed-pan run.
    - **Limits:** 47 CFR 18.307(a) induction cooking, now including the 9–150 kHz rows. Canada, Mexico and CISPR 14-1 below 150 kHz are for the lab to confirm.
    - **Worst predicted margin:**
      - 9–150 kHz: 7.8 dB QP at the 60 kHz switching fundamental (28 A, CM through the coil-to-PE capacitance), and 9.1 dB at 22 A.
      - 150 kHz–30 MHz: ≥ 22 dB AV (lumped model; above ~0.5 MHz not trusted).
      - The sensitivity minimum is 1.8 dB (3.1 dB at 22 A). Every low case comes from the coil-to-PE capacitance, an assumed 10–100 pF with no repo data.
    - **Decisions:**
      1. The inlet EMI module is mandatory at ≥ 100 µH DM. D-22's 18 µH misses 9–150 kHz by 5.1 dB; 80 µH still passes.
      2. No Y caps from the DC bus to PE: the model shows they pull the CM resonance into the switching band.
      3. Measure the coil-to-PE capacitance (sum and split per end, assembled) first, and ask the enclosure session for a geometric estimate from the R43 solids now.
      4. CM fixes held in reserve: a coil-side shield returned to bus_n (11.0 dB), or a 3.2 mH CM choke in the inlet module (10.5 dB nominal, 8.7 dB at 100 pF 70/30).
      5. At the next re-spin, reserve a PE test point, a spare Y2 footprint, a removable R38 and a current-probe window at J2/J5. Nothing is needed on 19b.
    - **Bench:** `BENCH-PRECOMPLIANCE.md` (LISN, 200 Hz / 9 kHz RBW, pan/no-pan, 22/28 A, sweep and burst, pass line = limit − 6 dB).
21. **Thermal conclusion at 28 A, restated on a converged model (2026-10-12; `validation-results/04-board-current-thermal/round5-native21/b3-convergence/`, controls rerun).** This replaces the unconditional "28 A is thermally supported" of items 14/17.
    - **Why it changed:** the legacy B3 peak (136.0 / 182.3 / 142.8 °C at 1 / 0.5 / 0.25 mm) was an artefact of point-depositing heat into binary-raster pad cells. The new model adds a datasheet junction network, flux over the exact pad overlap, area-fraction copper, and windows refined to 0.0625 mm. It converges to ≤ 2 K for every governing part.
    - **Margin with datasheet limits (28 A, 29.4 A tank, h25):**

      | Part | Converged | Margin |
      |---|---|---|
      | R5 | element 140 °C, terminal max 129.5 | 18.8 K to the 20 %-power terminal bound |
      | U41/U42 | Tj 105 °C | 45 K |
      | U26 | Tj 89 °C | 36 K |
      | UCC21550 | 79 °C | 70 K |
      | TPS70950 | 79 °C | 46 K |
      | Gate resistors | 107 °C | 43 K to a 155 °C class value (unverified) |
      | FET-row copper | 126 °C | 21 K to laminate Tg 150 (corrected in item 46: the use limit is the UL MOT 130 °C, and KB-6164 Tg is 140) |

    - **Depends on bench IR (no validated package limit or path):**
      - film caps: HF C38–41 at 5 K margin to 105 °C, bank C21 at 15 K, C5/C6 at 27 K;
      - L1;
      - PS1 / PS2: model case 86 / 98 °C against an 85 °C *ambient* rating. Judge these against the measured local air, not the case.
    - **Stall:** derated to 14 A at h10, the semiconductors keep 22–27 K. 28 A at h10 without the derate stays unsupported, as item 14 already says.
    - **Bench IR points:** listed in the study README (R5, U41/U42, U26, PS1/PS2 plus local air, bank and HF caps, FET-row copper, R58/R12, L1). If a U41/U42 body top reads > 125 °C at h25, θJB is more than 2× the datasheet value.

22. **Rubric desk studies and the benchmark (2026-10-13; `validation-results/09-rubric-review-s19b/RESOLUTION-PLAN.md`, `validation-results/10-benchmark/`).** Each study fixed its pass criterion before computing, carries controls, and reruns deterministically.
    - **F2, shoot-through containment (`02-protection-timing/shoot-through-f1/`): FAIL.** D-31 names "FC1 and the catch circuit" as containment, but the normal build runs on copper straps (no FC1) and the schematic has no catch circuit. With F1 (KLDR025) alone:
      - **BR1:** F1 clears at 1,710 A²s against GBJ2510's 510 A²s. No bridge survives a 25 A fuse's clearing energy (it would need about 3.4 kA²s), so **BR1 is sacrificial in a shoot-through**: a repair item, not a safety function. This departs from the BR1 half of the criterion fixed before the study, on purpose.
      - **Copper (the safety half):** the bridge side (x < 77 mm) reaches the strap studs and bulk caps through one congested corridor at x 77–84: on In1 the HV_RET plane is pinched by C39's bus_p pin clearance, an n_ha track / via and a bundle of signal tracks at y 39–46, leaving ribbons of 1.7 and 1.2 mm (widest single path 1.17 mm at (82.0, 38.2), 355 A²s, 0.21 × F1's clearing; summed ribbons about 2.9 mm, still under target). BUS_P on In2 pinches at (77.9, 26.4): 1.85 mm, 884 A²s. R5.4 reaches In1 through a 6-via field, 1,012 A²s at equal sharing. The task-04 DC run sees the same spot (In1 22.2 A/mm at (82.29, 37.63) at 15 A), so the isthmus is real copper, not a method artifact (an earlier neck at J10's press-fit annulus was one and is gone from the corrected method). A neck that opens at mains voltage can sustain an arc. **Decision:** every series neck of the rectifier / bus / return path must reach ≥ 2 × F1's clearing I²t (3,420 A²s). That is a copper change and the first fix candidate against the benchmark (scorecard `fuse_copper_fusing_ratio`).
      - The bus-cap dump (0.40–0.85 J) is local and no upstream fuse limits it.
    - **F4, F2 breaking capacity (`02-protection-timing/f2-coordination/`): FAIL.** F2 (UMT 250, 200 A at 250 VAC) melts at 11.6 A²s against F1's 226 A²s, so F2 always opens first and must break the fault alone: 0.37–3.6 kA at J11 across the source corners. F1 is not its backup. **Decision:** replace F2 with a ≥ 1,500 A 5 × 20 ceramic fuse in clips (candidate 02153.15MXP, LCSC C142723; the 1,500 A figure needs the datasheet), or drop the board's blower tap if a simplification candidate removes PS3's mains feed. Either is a layout change graded against the benchmark. The certifier item (stage 16) stays open.
    - **F5, leakage (`07-conducted-emi/leakage/`): FAIL.** Touch current with PE open at 132 V is 0.974 mA against UL 1026's 0.5 mA for portable appliances (clause unconfirmed; certifier question added). The Y capacitance alone (board 2.2 nF + D-22 module 6.9 nF per line) is 0.54 mA; the three IRM modules add 0.43 mA at their datasheet maximum. R38 is 0 Ω, so the SELV side is earthed and that leakage reaches PE. **Decision:** total Y capacitance ≤ 5.0 nF per line, including the inlet module. The EMI rerun with the module's real parts (F10) has to meet that, so the common-mode choke grows and the Y shrinks. The EMI PASS of item 20 assumed 6.9 nF Y and is conditional on this too.
    - **F6, isolator CMTI (`06-controller-interface/cmti/`): FAIL by the 1.5 × rule.** UCC21550 is rated 125 V/ns minimum against a modelled 95 V/ns hard edge (1.32 ×); every other crossing passes, passes on its 10 µs filter, or is open (no CMTI published: VOL628A, T1, the IRMs). The rating still exceeds the edge, so this is margin, not a predicted upset. **Decision:** the bench measures S4 / S5 dv/dt at bring-up; above 83 V/ns the turn-on gate resistance rises. UCC21550 also has no distributor stock until 2027-06 (F13), so a higher-CMTI driver is a priority simplification candidate (lead: onsemi NCP51561, pinout to check).
    - **F13, stock (`08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13.*`):** parts cost about $330 per power board at 5 and $232 at 500 (parts only). 10 lines have zero stock and 17 are single-source. The worst are UCC21550BDWKR (0 stock, next lot 2027-06), ISO7710DWR ×4 (0 stock, 12 weeks), L1 (TDK, 0 stock, 29 weeks), J6 and R5 (0 stock). Mouser was not reachable; the controller's JLC classes are mostly unrecorded.
    - **The benchmark (owner direction 2026-10-13):** stage 19c, with its scorecard (`native-21/layout/gates/scorecard.py`) and the acceptance rule fixed before any candidate: every gate passes, no performance metric is worse beyond its tolerance, and the candidate is cheaper / simpler or better. The deficits above are scorecard metrics, so fixing them is how a candidate scores better. Supplier contact (JLC CTI, TDK, Coilcraft, Mersen) waits until a winning candidate is chosen, except the JLC CTI question, which every candidate needs.
    - **D-31 wording:** "FC1 and the catch circuit as containment" does not describe the built board. Containment is F1 plus copper that survives F1's clearing energy (above), with BR1 sacrificial.
23. **Stage 20: first accepted candidate, BOM-only (2026-10-13; board `2d5a4b05a9a1e627132e4372cac5065d1ad72b19efd45a8b7b9e22c8de1b7acd`, copper.json `de81613d…` = 19c, schematic `61780840…`, frozen netlist `628bdb55a607f9536a3d66b3587c069913ebc4f54c38163345e854654aa2ab36`, Gerber ZIP `17feed2516c638680a3e8a392c77be7ec22fff0f87d853331f964a869644d0a8`; tag `native21s20`; proposals `validation-results/11-candidates/g04-g09-tank-detect/` P1–P3, queue `11-candidates/QUEUE.md`).**
    - **Changes (schematic values only, no footprint or copper change):**
      - T1 CST3015-100ED (1:100) → **CST3015-200ED** (1:200, same series outline and insulation statement), with R39 1.5 → **3.0 Ω** (RC1206FR-073RL). Volts per primary amp stay 0.015 V/A, so the CT trip (70.18 A, band 64.55–76.09 A), CT_MON and CT_ZC are unchanged in amps. Secondary volt-time at the 118.74 A shunt-band top falls from 7.2 % to 5.3 % of its limit, and burden loss halves. T1 becomes a JLC SMT part (C50132500, 64 in stock) instead of a consigned one.
      - U36 VOL628A-3X001T → **VOL628A-2X001T**. This is the same LSOP-4 package and VDE option, and it is stocked (C145344). The CTR bin is lower, which widens the zero-cross pulse about 1.6×. The firmware's 300 µs minimum pulse width is a bench check either way.
      - Bank C21–C23 / C151 / C152 K → **B32654A1104J000** (±5 %). The 28 A, 40 kHz ratio to TDK's current curve goes from 1.105 to 1.022, and the allowed tank current at 35 kHz from 24.8 to 26.8 A. F3's third-fault case drops from 1,702 to 1,683 V; it stays covered by the 35 kHz floor (DECISIONS 13).
      - The C49678 line is labelled Basic, which is JLC's own listing.
    - **Evidence:**
      - Atopile 0.2.69 rebuild: the diff is exactly the four parts.
      - audit.rs PASS, 80/80, with identity strings updated; verify_source PASS (357).
      - Chain on the 19c copper: every gate identical to 19c (DRC 0/0/0, barrier and RES_A 0, Rust 0 over 5,837 items, D5 8.047/8.507, fit 0, DFM PASS, Gerber review PASS, bypass 11/11, PI PASS, return_path PASS, Kelvin 67.72–116.44 A, B3 136.0 °C).
    - **Scorecard against the 19c benchmark: ACCEPT.**
      - Simpler: hand/consign lines 23 → 22 and zero-stock lines 10 → 9.
      - Better: `bank_ratio_tdk_28A_40k` 1.105 → 1.022.
      - Cost: parts are **+$2.89 at 500** ($231.94 → $234.83), all from the J bank. That is priced conservatively at the benchmark's DigiKey K price × JLC's J/K ratio (1.41). No T1 saving is claimed, because Coilcraft has not quoted the -200ED (`STOCK-2026-10-13-addendum-s20.csv`).
    - **Scorecard change, stated openly:** `bank_ratio_tdk_28A_40k` was added with this stage. It is one of item 21's 28 A thermal margins and was missing from the card. The 19c card received the same metric from the same script (1.105, K grade).
    - **Bench, unchanged in kind:**
      - CT trip injection (the D4 condition-2 step), which any T1 needs.
      - The ZC pulse width.
      - T1's interwinding capacitance (MAG-27), which is unpublished for both parts. The pickup it causes is independent of turns ratio for equal capacitance.
24. **F1 fuse class and the F5 leakage basis (2026-10-13; decision records `validation-results/12-decisions/F1-FUSE-DECISION.md` and `F5-LEAKAGE-DECISION.md`, scripts rerun, controls pass; owner asked for both to be resolved).**
    - **F1: keep the Class CC KLDR025.TXP.**
      - **Why:**
        - A Recognized supplemental fuse may be acceptable inside a Listed appliance (UL Code Authority note, read). The end-product short-circuit clause and its available-current level are in paywalled standards (UL 1026 / UL 858 / CSA C22.2 No. 64 / NMX-J-521) and were not read.
        - The cheaper candidate, Littelfuse 0505025.MXP (about −$26–29 per board), has no published clearing I²t, an unconfirmed 25 A interrupting rating and conflicting melting I²t (145 vs 210 A²s). It also does not close F2: the copper ratio rises only to 0.56–1.63 against a 2× target.
        - KLDR025's 200 kA Listed rating makes the unread test level moot (23.8× over the 8.4 kA bound). Its published let-through (about 540–634 A at 4.7–8.4 kA) is under a 1.5 kA F2, which helps F4.
      - **Saving taken instead:** re-source KLDR025 itself (web prices $22.55–26.54 against DigiKey $29.41; quotes needed).
      - **Reopen the 6.3×32 option only if** the lab confirms a supplemental fuse is acceptable for this product and states the short-circuit test current, and Littelfuse's own datasheet gives the clearing I²t at that current.
    - **F5: design to the 0.5 mA UL portable limit**, plug ground open, both polarities. 0.75 mA is the stationary and IEC 60335-1 Class I value, so 0.5 mA covers both. This replaces item 22's 0.25 mA (50 %) placeholder budget with a two-test basis:
      - **Test A:** ≤ 0.5 mA at 132 V, with Y at +20 % and the supply modules at their datasheet maximum.
      - **Test B:** ≤ 0.40 mA with the supply modules at 5 × measured typical, confirmed by an open-PE touch-current measurement on the first article in every configuration.
      - **Path that meets both:**
        - the inlet-module Y cut 6.9 → 2.2 nF (g01 P1), the main lever at about −0.28 mA;
        - deleting PS1 (g06 P1);
        - plus, by bench measurement, that PS2's leakage does not reach PE (g06 P3).
      - **Result:** 0.408 mA on Test A (82 %). Without P3 it is 0.551 mA on Test A (fail) and 0.364 mA on Test B (pass).
      - The benchmark's 0.974 mA fails both tests. Candidate 23 (QUEUE.md) carries the fix.
    - **Lab confirmations (open):**
      - the governing standard, clause and edition;
      - whether a countertop induction cooker is "portable";
      - the test voltage and meter network, and how the 35–60 kHz coil-to-PE current is treated;
      - Class CC and open-clip acceptance for CSA and NOM;
      - the first-article touch current.
25. **Stage 21: BR1 feeds the bus directly; the J7–J10 rail links are removed (2026-10-13; board `fac94215369b6c285472a98e4cc255def9739f19fe2cf43e3439f6884e2bcae3`, copper.json `b164d518…`, schematic `e25b32a9…`, frozen netlist `5be3b9f5042793951e01cd47778f2586a65b5b3987ae2116d6938c8d58ead208`, Gerber ZIP `553ac1468bb720774f31298651db3e133bd554ba3febe330035dfddae3c799bb`; tag `native21s21`; proposal `11-candidates/g02-g03-power-path/` A and C; scorecard `10-benchmark/scorecard-native21s21.json`).**
    - **Why:** every DC amp between BR1 and the bridge ran out to the strap studs at x 127–146 and back through one congested corridor at x 77–84. That corridor's In1 isthmus (1.17 mm, 355 A²s) fused at 0.21 × F1's clearing energy (item 22), cost about 2 W of DC loss, and put the bus and its return on non-overlapping layers through the corridor (F7).
    - **Change:**
      - Schematic: BR1.PLUS → BUS_P and BR1.MINUS → HV_RET. The RECT_P / RECT_N nets and the BusBringupLink module (J7–J10, 4 × Würth 74650074) are deleted (353 components).
      - Layout: `patches21.edit_zones` drops the rect pours and the J7–J10 stud lands, and merges the BR1 window (x 74–136, y 0.6–29) into the hv_ret (In1) and bus_p (In2) trunk outlines. Two same-priority intersecting zones are a KiCad DRC error; a first attempt hit it.
      - R5.4's via field becomes 5 × 0.8 / 0.5 mm, plus one existing 0.85 / 0.3 (`add_r5`).
      - Task 04's DC cases now source at BR1.1 and sink at BR1.4 (`run_cases.py`, `regate.sh`).
    - **Bring-up:** the bench build leaves BR1 unfitted and lands the floating supply in BR1's + / − holes. With no bridge fitted there is no galvanic mains path to the bus on either rail; ASSEMBLY.md is rewritten. The audit now pins BR1.1 to bus_p and BR1.4 to hv_ret, and a new mutation test fails BR1.4 moved to LEG_RET (shunt bypass). The two link tests are retired. audit.rs PASS, 79/79; audit_f6's designator-retention test exempts the deleted link paths. verify_source PASS (353).
    - **Gates (board `fac94215…`):**
      - DRC 0 / 0 / parity 0. Barrier21 and RES_A outer 0. Rust gate 0 over 5,813 items. D5 8.047 / 8.507.
      - Fit: 405 solids, 0 overlaps, 407 bodies, 0 hits. DFM PASS (751 vias). Gerber review PASS (851 holes + 4 slots).
      - Bypass 11/11. PI PASS. return_path PASS. CPL audit 279 / 10 / 50; the BOM / CPL designator check passes after the audit rerun.
      - **Task 04's BUS_P mesh span: 4.129 % → 2.921 %, passing its 3 % criterion for the first time since stage 6.**
      - Kelvin identical (67.72–116.44 A).
      - B3: 28 A h25 136.0 → **135.1 °C**; h10 197.4 → 192.4 °C; nominal h10 163.2 → 162.0 °C.
    - **Fault-copper (F2's copper half, `02-protection-timing/shoot-through-f1/s21_necks.py`, the same neck method; via fields with their actual drills):**
      - Every conductor neck now clears F1's 1,710 A²s. The lowest is L1 → BR1 AC1 at 1,747 A²s (1.02 ×).
      - The R5.4 via field is 2,342 A²s (1.37 ×). The corridor isthmus is gone.
      - The overall minimum, 1,698 A²s (0.993 ×), is the TO-247 drain land itself, which is terminal-limited. Its real path is the plated barrel in parallel with the soldered lead, which the method does not credit.
      - **Restated target:** item 22's "≥ 2 × F1 at every series neck" cannot be met at a TO-247 drain land on this footprint (g02-g03 section 0). The target becomes **every conductor neck ≥ 1 × F1's clearing I²t, with device-terminal lands reported**. `fuse_copper_fusing_ratio` stays the minimum over every row (0.993), so it remains conservative.
      - BR1 stays sacrificial in a shoot-through (item 22).
    - **Scorecard:**
      - **ACCEPT against 19c and against stage 20.** It is cheaper on parts at 500 (234.83 → **223.91**, −$10.92) and on placements (357 → 353). It is better on `fuse_copper_fusing_ratio` (0.208 → 0.993) and both B3 peaks.
      - Unchanged: every other metric, including the return path (39) and EMI (10.5 dB, not re-modelled; the input filter is unchanged).
    - **Stage-20 slip, caught here:** stage 20 changed parts but not copper, so the CPL rotation audit was not rerun. T1, U36 and the bank caps then moved from consign to JLC placement. The stage-21 rerun classifies them (NEEDS-PREVIEW 47 → 50). Rule: rerun `cpl-rotation-audit/audit.py` whenever the BOM's assembly class changes, not only when copper changes.
    - **Open:**
      - R5.4's 0.5 mm in-pad vias sit at JLC's fill limit, so confirm at order.
      - The F7 bulk-path benefit (about −4 nH in the g02-g03 plane screen) needs the loop re-extraction.
      - The removed studs' enclosure envelopes (J7–J10) can be released to temper-f7.
26. **Stage 21b: OCP Kelvin pickup fix, F8 (2026-10-13; board `c015804959add81e948055279cb78946e3a762ac9077c0b21bfbde3c89d0cb56`, copper.json `c608c724…`, schematic and netlist as stage 21, Gerber ZIP `bb7a54787dc08d06562da1c790109ab763707eede3a3a95bb03e862ccbfd3a39`; tag `native21s21b`; proposal `11-candidates/g06-g08-g10-supplies-sense-io/` P4; evidence `02-protection-timing/coil-pickup/s21b/`).**
    - **Why:** the F8 rerun found the as-built OCP Kelvin / comparator loops failing the pickup gate on the coil's field: any-phase +50 % stack ≤ 6.5 A at 59.2 A peak. The 19c copper gave 8.71 A at 60 kHz and 7.04 A at 45 kHz with a pan. KELVIN_N crossed the In1 ocp_kelvin_p pour on In1 (x 106.6, y 43.4–72.4) instead of running under it, and C30 / C31 sat 11–15 mm from U6.
    - **Change:**
      - KELVIN_N runs with KELVIN_P on In1 to (106.6, 55.9), drops through a via at (104.8, 55.9), the nearest legal spot (F.Cu there carries Kelvin_P / HOT5-monitor tracks), and runs to R33's via under the pour's footprint on In2 / B.Cu (`patches21.add_stage21b_kn`, linked last).
      - Single-layer In2 and B.Cu runs do not fit. A first mixed route put a via under bus_fault_hot and failed return_path19 SI1, so the layer-change via is kept out of a 1.2 mm corridor under bus_fault_hot's F.Cu run.
      - C30 (ocp_node) → (99.76, 63.09), 4.2 mm from U6.3 (was 12.3). C31 (ocp_thresh) → (102.93, 64.78), 6.1 mm from U6.4 (was 11.3). These are the nearest spots legal under the isolation-group clearances. `gates/bypass_spots.py` gained `--rules`; its flat 0.35 mm check had offered spots 3.2 mm-illegal to the bus_p divider R26.
      - The D5 via nudge (g05-g07 P5, +0.026 mm) is not taken: it is a tie-breaker on a router-owned via.
    - **Pickup (`coil-pickup/s21b/run_ocp.py`, same method, run on each stage's copper):**
      - **Control:** the copy reproduces the 19c result exactly (8.71 A).

      | Case | 19c | 21b |
      |---|---|---|
      | Pan, 60 kHz | 8.71 A | **4.78 A** (PASS) |
      | Pan, 45 kHz | 7.04 A | **3.87 A** |
      | Nominal peak shift, 60 kHz | 0.60 A | **0.19 A** (×1.5) |
      | No pan, conservative straight closure | 24.6 A | **13.9 A** |
      | No pan, closure following the return path | 16.3 A | **1.5 A** |

      - The no-pan conservative figure stays over 6.5 A. Normal firmware does not run the tank without a pan, and the 13b report shows the no-pan field in quadrature, so its any-phase stacking is non-physical. Recorded, not claimed as a pass.
    - **Gates (board `c0158049…`):** DRC 0 / 0 / 0, barrier and RES_A 0, Rust 0 (5,848), D5 8.047 / 8.507, fit 0, DFM PASS (752 vias), Gerber review PASS, bypass, PI and return_path PASS. Kelvin band 67.77–116.44 A (+0.05 A). B3 unchanged (135.1 °C). Fault copper unchanged (`s21b_necks.json`: 0.993 overall, 1.02 for conductors). CPL audit 279 / 10 / 50.
    - **Scorecard:** `ocp_pickup_stack_pan60_A` is added (lower is better, 0.1 A tolerance). It is back-filled from the same script on the 19c copper (8.71; stage 20 shares that copper) and on the stage-21 copper (8.71). **ACCEPT against 19c and 21:** better on pickup (8.71 → 4.78) and the Kelvin band low corner, at equal cost.
27. **Stage 22: DIS = NAND(PERMIT, BIAS_GOOD); the PERMIT inverter FETs go (2026-10-13; board `cab63cec89dbd3e5111467373d461759e6a4bc49cc1a929f5d05964d65efaba6`, copper.json `c1138ea7…`, schematic `a0d6b555…`, frozen netlist `f3c8b15822edf41f4d4469bcc92d98d2b3b578ef0e4ac815d800f9039b05bd4c`, Gerber ZIP `096d48a494e6d33151ce71ae6dc96ec9a9ad9fdea5af172a571501f114c409c1`; tag `native21s22`; proposal `11-candidates/g05-g07-drive-monitor/` P3; SAFETY: drive-disable logic).**
    - **Change:**
      - Per leg, the AO3400A (Q1 / Q4) that inverted PERMIT against a 330 Ω pull-up (R8 / R16, about 10.5 mA from V3V3 while enabled, D-31) and the SN74LVC1G32 OR are replaced by an SN74LVC1G00 NAND in the OR's place (U22 / U23, same SOT-23-5 pinout): DIS = NAND(permit_gate, BIAS_GOOD).
      - U40 becomes the inverting Schmitt SN74LVC1G14, so the filtered monitor output is BIAS_GOOD. The 100 Ω PERMIT series resistor, the 100 k pull-down, the 10 k DIS pull-up and the 10 µs filter are unchanged.
      - **Truth table identical:** DIS is low (drive enabled) only for PERMIT high AND bias good. PERMIT low, floating (100 k) or unpowered, or BIAS_BAD, gives DIS high (`g05-g07 truth_table.py`).
      - PERMIT-to-DIS goes from the allocated 119 ns RC rise to a gate delay (bench-qualified).
      - J4 PERMIT now drives a CMOS input: VIH 2.0 V against the ESP32's 2.64 V VOH minimum. That is a controller-side check.
    - **Evidence:**
      - Atopile rebuild: −4 parts (349); BOM 92 → 91 lines (AO3400A, 330 Ω and G32 out; G00 and G14 in). audit.rs PASS, 79/79: the PermitFet / r_dis_pu checks become NAND pin checks, a new mutation test fails a NAND input moved off permit_gate / bias_good and U40's output off bias_good, and the SELV-to-HOT test uses r_permit_pd. audit_f6 retention exempts the two deleted paths. verify_source PASS (349).
      - Layout: placement holds the surviving parts at their 21b poses. incr21 gains `RENAME_NETS` (base bias_bad copper → bias_good) and drops base tracks naming deleted pads. pwm_hb's fixed vias are reserved before pwm_lb is re-linked (with Q4 gone the router took (35.2, 125.0)).
      - Gates (board `cab63cec…`, new parallel chain): DRC 0 / 0 / 0 with no dangling copper. Barrier and RES_A 0. Rust 0 (5,815). D5 8.047 / 8.507. Fit 0 (401 solids). DFM PASS (744 vias). Gerber review PASS. Bypass, PI and return_path PASS. Kelvin 67.77–116.44 A. B3 c28 h25 135.1 °C. Fault copper 0.993 (`s22_necks.json`). OCP pickup 4.17 A at 60 kHz with a pan: the pass re-laid ocp_thresh all on F.Cu, a shorter loop. The pickup script's path search now also starts on F.Cu, and the 21b control is unchanged at 4.78 A.
    - **Scorecard: ACCEPT against 19c and 21b.**
      - Cheaper: −4 placements, −1 BOM line, parts $223.91 → $223.10 at 500 on the class-default logic prices both cards use. On real JLC prices the saving is about $0.1.
      - Better: return-path open changes 39 → 37; OCP pickup 4.78 → 4.17 A.
      - Extended lines 61 → 62 (G00 and G14 are Extended; the deleted parts were Basic): +$3 per order.
    - **Chain speed-up, recorded with this stage (same gates and outputs):**
      - `chain.sh` settles first: KiCad-reported dangling tracks / vias are trimmed and only the board is rebuilt. `trim_tails.py` now also removes dangling vias.
      - It then runs fit, fab, core regate, task 04 → B3, Kelvin and the copper gates as parallel blocks with per-block logs and exit status.
      - Task 04 and B3 are cached on content keys that exclude the board hash; every reuse is listed in the study's `outputs/cache.json`.
      - `plan_board_only21.text_spot` (silk text placement) went from 472 s to 11 s with identical output: an STRtree, the inset outline built once, and a nearest-first scan that keeps the old tie-break. Probe-note pad order is now sorted, because the dump order varied by build.
      - Measured on this stage: the old serial chain took about 21 min, of which the planner was about 8; the post-build blocks went from about 12 to about 10 min in parallel. The next signal-only stage should also hit the task-04 cache.
28. **Stage 26: C126–C129 6SVPC220M → 6SVPC220MV, BOM only (2026-10-13; board `d9eb6e9eef70577ef40b5c7ba54be91a5c217a1639b185f96ff6f56b190bbf24`, copper.json `c1138ea7…` unchanged from stage 22, schematic `973176bb…`, frozen netlist `b1e8d186ec8c2987f4c78ad43cfc200e92216120d8663e28cc64da6acfdea274`, Gerber ZIP `c1c34d21692f757a6674bcbb8ae2f8438e7d5ec22f86457d838ba55e3529b091`; tag `native21s26`; proposal `11-candidates/r2-cost/` R2-05).**
    - **Change:** the four high- and low-side bias bulk capacitors move to Panasonic's low-ESR variant of the same OS-CON SVPC part: 220 µF, 6.3 V, the same 6.3 × 5.9 mm can and land pattern. ESR is 15 mΩ against 27 mΩ, and the ripple rating is higher. Each capacitor sits behind the 0.68 Ω damping resistor, so the ESR change moves the damped impedance by under 2 %. LCSC C128504 has 845 in stock, against the old part's 13. Price at 500 boards: $0.491 against $0.696 each.
    - **Evidence:** the atopile rebuild changes only the four MPN fields (netlist and BOM diff). audit.rs PASS, 79/79. verify_source asserts the new MPN. The chain on the unchanged copper is clean: DRC 0, Rust 0 (5,815 items), D5 8.047 / 8.507 mm, fit 0, DFM PASS, Kelvin 67.77–116.44 A, task 04 39 / 39, B3 135.1 °C, fault copper 0.993, OCP pickup unchanged. The CPL rotation audit gives 277 / 48 / 10 and covers all 349 placements.
    - **Scorecard: ACCEPT against 19c and 22.** Parts cost at 500 boards goes from $223.10 to $222.28. Every gate and performance metric is identical to stage 22.
    - **Considered and not taken this round:**
      - **R2-01, deleting the D3 / D17 DC-link clamp (−$19.64).** DC-LINK-CLAMP.md requests at least 2 J of absorption at ≤ 520 V. The bus alone reaches that energy only at 547–592 V (`r2-cost/scripts/clamp_2j_check.py`), although every modelled event (≤ 0.46 J) stays at or below 379 V. This is an owner decision (QUEUE.md).
      - **R2-03, BR1 to the MDD GBJ2510.** BR1 sits in the seat-before-solder sink stack, and the MDD body thickness is unverified.
    - **Flow fixes recorded with this stage:**
      - `chain.sh` and `regate.sh` now set `pipefail`. A wrong PASSDIR once ran a whole chain because the planner's traceback was piped through grep, and summarize.py's exit status was hidden by `| tail`.
      - The task-04 and B3 cache keys are now computed by `copper_key.py` over the board's copper inputs: tracks, vias, pads, zone outlines and settings, and the rules files. KiCad's refill is not bit-reproducible: on the stage-22 rebuild the B3 peak moved from 162.04008064 to 162.04008119 °C, so a key over the filled copper never hit.
      - On a hit, the study keeps the export its results were computed on. A local `.npz` digest must also match, because the nodal-heat files are gitignored.
      - `dump_pads.py` sorts its output, so `pads.json` is stable.
      - The fab block runs the CPL rotation audit and asserts that it covers every CPL line. An exclusion counts only while the part still has no LCSC code. Stage 22's committed audit had excluded U22 / U23 / U40 as "no LCSC" because it ran before their codes were added, and this check fails on it.
      - Chain time on stage 26 is 769 s with one task-04 / B3 recompute, against 1,260 s for stage 22. A cache-hit run is about 380 s.
29. **Stage 27: J1 becomes a terminal rated for North America, the Phoenix MKDS 5/2-9,5 (2026-10-13; board `44644390f1ee41760407400ac4a620d97512e388c9902c625c50d84a37dfd124`, copper.json `ac376fbe45e9e2492fb9e28df4336d9ec92813c876f4a8341b42a12e53b1c61e`, schematic `5963327d…`, frozen netlist `0a54ae3fc223bb566d84acaf672bd1a0001a023e8b04bfb6aebf5b3fedac8e65`, Gerber ZIP `1e77ccaba84124fa613823485c39f6970107210c98188d67cdc207143ce40631`; tag `native21s27`; `13-external-review-2026-10-13/FINDINGS.md` #4 / #11, `11-candidates/c27-j1-terminal/`; SAFETY: mains entry).**
    - **Why:** J1, the Phoenix 1711725 (MKDS 3/2-5,08), is rated 24 A only under IEC. Its North-American ratings are 15 A cULus use group B (10 A group D) and 10 A CSA, against an input regulated to 13.5 A, a 15 A trip and a recorded 16.5 A envelope. The F1 note (item 160) used the IEC 24 A figure.
    - **Change:**
      - **J1 → Phoenix 1714971, MKDS 5/2-9,5:** UL/cUL use group B 30 A at 300 V, CSA 13631 30 A, UL file E60425, IEC 32 A, UL wire range 30–10 AWG. That puts J1 at 45–55 % of its rating across 13.5–16.5 A, and 83 % at F1's 25 A non-interrupting ceiling.
        - The ratings were read by the lead from the Phoenix catalogue extract (LCSC copy, 2017).
        - LCSC C92145, $1.03 at 500 (was $1.487).
      - **Footprint:** the new `temper:Phoenix_MKDS-5-2-9.52_1714971` is drawn from the dimensioned drawing in the 2010 extract (p.4).
        - Pitch 9.52 mm, holes Ø1.3 mm, 3.0 mm pads.
        - Pins 4.76 mm from each body end; pin row 7.9 / 4.6 mm from the front / rear faces.
        - Wire entry stays at the top (rear) edge.
        - The L–N copper gap goes from 2.48 to 6.52 mm.
      - **Placement:**
        - J1 pin 1 is at (274.6, 9.2), with the courtyard at its former top and right extents.
        - F1 moves 5.65 mm left; its courtyard is 0.7 mm from J3.
        - R1 / R2 move 0.9 mm down together; their bounded pad escapes follow (`MOVE_ESCAPES`, a new incr21 hook).
        - These overrides sit after place.py's stage-14 pose freeze (STAGE27_ORIGINS).
      - **Copper:**
        - The ac_l_in / l_f mains pours are redrawn: ac_l_in follows F1 and gains a tab round J1.1.
        - l_f's strip and the RV1 column start 3.2 mm below that tab. The strip is widened to 3.2 mm there for RV1's surge path.
        - Every outline-to-pad distance is ≥ 3.2 mm (checked with shapely before routing; DRC 0).
        - The router could not re-lay the R1.1 / R2.2 links in the 3.2 mm corner, so `add_stage27` puts back their base geometry.
    - **Evidence:**
      - **Source:** audit.rs PASS, 79/79; `j_mains` is now 1714971. verify_source asserts the MPN and footprint. Routing passes clean at i3 (unconnected 0, errors 0).
      - **Chain (board `44644390…`):**
        - The settle loop trimmed a dead leg_b-permit_gate In2 branch over 7 rebuilds.
        - DRC 0 / 0 / 0. Barrier 0, RES_A 0. Rust 0 (5,812).
        - D5 8.047 / 8.507. Fit 0, with a 22 mm J1 envelope since the part has no 3D model.
        - DFM PASS (744). CPL audit covers 349 of 349.
        - Kelvin 67.77–116.44 A. Task 04 39/39, BUS_P span 2.92 %. B3 135.1 °C. Fault copper 0.993. OCP pickup unchanged.
      - **Datasheet ledger:** J1 goes from VIOLATION to PARTIAL. The remaining gap is confirming the rating on UL Product iQ and CSA before certification.
    - **Scorecard: ACCEPT against 19c and 26.**
      - Cheaper: parts $222.28 → $221.82.
      - Better: ledger violations 2 → 1, unaudited SAFETY/POWER lines 2 → 0. The R1 / R2 bleed pair and the C12–C20 snubber caps were audited into the ledger with this stage.
      - Every other performance metric is identical.
    - **Flow fix:** the chain's settle loop now rebuilds after every trim, up to 8 builds, and fails if dangling copper remains. In this stage's first chain, the old 4-pass loop gated the board built before its last trim.
    - **Open:**
      - Overload coordination (FINDINGS #11) is now a margin question, not a failed rating. The certifier's abnormal-operation test, with the firmware current limit defeated, still applies.
      - The enclosure harness lands L / N 6.4 / 1.9 mm further left at the same rear edge (for the enclosure session's next harness revision).
30. **Stage 28: F2 becomes a 1.5 kA fuse with a 0.15 Ω fault-current limiter (2026-10-14; board `e3fe94099405ebcf2cccdd49695c969cad9473455cca3cc4df234a4a8ab323c6`, copper.json `88e296e68024f341a873fa8ac27e0d4d9e01257eb213ac8c3a23558544c44acd`, schematic `8da56e57…`, frozen netlist `fc960f956bd45183bedabad862355e0b29110ea54e802cfba0403ea83f557df1`, Gerber ZIP `b8c4cf3c45597b0bf2aa84d4d08a132c9520346dedca000ab18af0e589ac5801`; tag `native21s28`; F4, `11-candidates/c28-f2/`, `g06-g08-g10-supplies-sense-io/f2/`; SAFETY: branch fusing).**
    - **Why:** F2, the blower-tap fuse, was a UMT 250 3403.0171 rated to break 200 A (IEC), against a 373–3,567 A prospective fault at J11, and F1 cannot back it up. It was the last datasheet-ledger VIOLATION.
    - **Change:**
      - **F2 → Schurter UMT-H 3403.0279.23:** 3.15 A T, 15.4 × 5.35 mm SMD. Breaking capacity 1500 A at 277 VAC (UL 248-14, cURus E41599) and 1500 A at 250 VAC (IEC 60127-7). Melting I²t 39 A²s. The lead read the Schurter data sheet's 3.15 A row, note 2, and its land pattern.
      - **R130 → Vishay AC05 0.15 Ω 5 W, mounted upright, in series after F2:** blw_l → R130 → blw_lr → J11.1. With R130 at its −5 % limit and no other impedance, the J11 fault is at most 980 A, 65 % of 1.5 kA (`c28-f2/bounds.py`). It dissipates 0.30 W.
        - Pulse load: 0.54 of the AC05's ~125 A²s on the current-limiting clearing estimate, 0.94 at 3× melting.
        - The clearing I²t is unpublished, so a bench short at J11 settles it. The ledger keeps R130 PARTIAL until then.
        - R130 is a new designator. R8 / R16, freed at stage 22, stay vacant.
        - `incr21` now also drops base tracks that name a pad whose current net differs: the frozen base's v3v3 track to 'R8.2' would have landed on a reused R8.
      - **Footprints:** new `temper:Fuse_Schurter_UMT-H_15.4x5.35mm` and `temper:R_Axial_Vishay_AC05_D7.5mm_P5.08mm_Vertical`. blw_lr shares blw_l's potential group. The stage-16 routing group reaches the limiter. J11 does not move.
      - **Why not the 646 holder:** the Littelfuse 0215 in a 646 holder with cover (26.6 × 9.5 mm, 14.5 mm tall) and a lying AC05 could not be placed between PS1, D17 and H1 without breaking the 3.2 mm (HOT groups) or 8 mm (H1 / PE) rules. The 0215's leaded variant is NRND at LCSC.
      - **OCP routing lock:** the first stage-28 chain re-routed ocp_node / ocp_thresh, and the OCP pickup went back from 4.17 to 4.78 A. The scorecard rejected it. Both nets are now laid from stage 27's copper (`stage28_ocp_lock.json`, `add_stage28_ocp_lock`, base copper removed, nets HANDLED). Stage 22's gain is now deterministic rather than a router outcome.
    - **Evidence:**
      - audit.rs PASS, 79/79, with new checks: blw_l joins only F2 and R130, blw_lr only R130 and J11. New mutations: J11 on F2's output (limiter bypassed) and the old 200 A UMT 250 both fail.
      - verify_source 350.
      - Chain on board `e3fe9409…`: DRC 0 / 0 / 0, settled in 2 builds. Barrier and RES_A 0. Rust 0 (5,815). D5 8.047 / 8.507. Fit 0, with envelopes F2 5.4 mm and R130 24 mm. DFM PASS. CPL audit 350 of 350. Kelvin 67.77–116.44 A. Task 04 39/39. B3 135.1 °C. Fault copper 0.993. OCP pickup 4.17 A.
      - Datasheet ledger: F2 VERIFIED, R130 PARTIAL. **The gate passes: 0 violations, 0 unaudited SAFETY / POWER lines.**
    - **Scorecard: ACCEPT against 19c and 27.**
      - Better: `ledger_violations` 1 → 0.
      - Costs: parts +$0.34 at 500 ($221.82 → $222.16). One more line and placement (R130). JLC Extended lines +2. Zero-stock +1: the UMT-H is stocked at Digi-Key (7,183), not at LCSC/JLC.
      - Lines without an LCSC code −1.
    - **Bench:** a short at J11 with R130 fitted (record i(t), integrate I²t; R130 intact or open, never shorted). F2 / R130 temperature at the PS3 load.
31. **Stage 29: U1 / U2 become the Infineon 2EDR8259X with 8.2 Ω gates (2026-10-14; board `3ae1ddb47c8c4c4e7c26c663ce54248c8797651e0066dc3bf516225403cba128`, copper.json `88e296e6…` unchanged from stage 28, schematic `bbcab1c6…`, frozen netlist `f3b930968940d0da711917aeb6fa80f69a3b9a3dba51c5b3cdd7f7f50c3a5a2a`, Gerber ZIP `20ae8c0bf7b1c54397574e873baf3e98c361fd52897c79fcd40bbad8257646e7`; tag `native21s29`; F6, candidate 25, `11-candidates/c25-driver/`; SAFETY: gate drive).**
    - **Why:** the UCC21550BDWKR's 125 V/ns CMTI was 1.32× the modelled 95 V/ns hard edge, against the 1.5× rule (F6). It also had no distributor stock until 2027-06.
    - **Change:**
      - **U1 / U2 → 2EDR8259XXUMA1:** PG-DSO-14 in the DWK outline, so its pins 12/13/14 sit on footprint pads 14/15/16 and the signals keep their pads. Static CMTI ≥ 150 V/ns at 1500 V (Table 23, by characterisation). Reinforced, VIORM 1767 Vpk. VDD 8.5–21 V against the 17.0 V rails, with the span OV trip at 17.84 V. 2EDR8259HXUMA1 is the same-pad second source.
      - **R10 / R12 / R18 / R20 → 8.2 Ω** (FH RS-06L8R20FT). With the stronger output stage, 3.9 Ω failed 5 of 144 F6 cases at 595 V. 8.2 Ω passes 144/144, with the edge at 0.99× the as-built one.
      - **R9 / R17 stay 49.9 kΩ.** The 2EDR's ±15 % dead-time spread gives an estimated 408–569 ns. The audit window moves from [391, 498] (the pre-F6 unipolar deck) to [340, 600]: on the as-built F6 deck, 3095 / 3095 D2 runs pass over 340–600 ns at 27/100/150 °C and at the weak / strong corners (`c25-driver/results/dtband`).
      - **DIS polarity:** active high on both, but the 2EDR pulls DIS down internally (open = enabled), where the UCC21550 pulled it up. The NAND drive and R73 / R76 (10 k to V3V3) keep the truth table, and R73 / R76 now alone hold an open DIS disabled.
    - **Evidence:**
      - The atopile rebuild changes only the six MPNs; connectivity is identical.
      - audit.rs PASS, 80/80: new BARRIER_PARTS MPN, Rg identity checks, the 2EDR dead-time model (Table 19 interpolation as `dt_window.py`), and a negative control for the EN-polarity sibling 2EDR8258X.
      - verify_source asserts the new parts.
      - cmti_table.py regenerated. U1 / U2 1.316 FAIL → 1.579 PASS. The script had been stale since stage 20 (CST3015_100E), and its CT note now reads the turns from the MPN (200).
      - D5 audit: 2EDR package CPG/CLR 8.0 mm, material group II. D5-BASIS re-cited.
      - Chain on the unchanged copper: every gate clean, task 04 and B3 cache hits (374 s), CPL 350 / 350.
      - Ledger gate PASS (2EDR PARTIAL: the CMTI is a characterisation figure, and no DIS-to-output delay is specified).
    - **Scorecard: ACCEPT against 19c and 28.**
      - Better: `cmti_gate_ratio_min` 1.316 → 1.579 (F6 closed on the datasheet minimum).
      - Cheaper / simpler: zero-stock lines 10 → 9, hand / consign 22 → 21, no-LCSC-code 7 → 6.
      - Costs: parts +$0.52 at 500 (Digi-Key prices on the old part's channel), +1 Extended line.
    - **Bench:**
      1. S4/S5 dv/dt ≤ 100 V/ns for the 1.5× claim.
      2. Gate dead time cold / hot (expect 408–569 ns).
      3. DIS-to-output delay.
      4. Open-NAND fault with and without R73.
      5. 17 V start-up overshoot < 21 V.
      6. Driver and Rg temperature.
32. **Desk decisions after stage 29: candidates 24 and 29, the ledger follow-ups, the D-22 DM inductors and the F1 method (2026-10-14; no board change; `11-candidates/c24-monitor-fmea/` §6a, `12-decisions/d22-dm-inductor/`, `12-decisions/emi-fs-floor/`, `12-decisions/f1-data/`).**
    - **Candidate 24 (one monitor crossing instead of three): GO as stage 30, with the buffered heartbeat M1b.**
      - The SPICE gate (`m1_pump_spice.py`, 96 corners) rejected the FMEA's hand-sized M1. With U32 stuck **high**, the 2 × 100 nF pump caps discharged into the hold and kept BIAS_GOOD up for milliseconds: the isolator fault M1 was meant to announce stayed dormant. U32 also sourced 13–22 mA per edge against its 2 mA recommended output current.
      - M1b: U32 → SN74LVC1G17 buffer → 220 Ω → 2 × 1 nF C0G → BAT54S → 1 nF ∥ 49.9 k → U40 (G17). Every corner passes: start ≥ 0.148 V over VT+max, trip ≤ 90 µs (≤ 123 µs with one pump cap shorted), buffer peak 11.2 mA against a 16 mA VOH spec point.
      - Net against today: −3 placements, +2 BOM lines, about −$1.6 to −$3.8. Two zero-stock ISO7710s go, three reinforced HOT→SELV crossings become one, and dormant 3-rail masking exposure falls 62 %. It is better and cheaper, so it goes ahead. The FMEA §7 certifier questions apply equally to today's circuit, so they don't block the stage.
      - Stage 30 also takes the U9 BUS_FAULT RC (below), since both sit in the SELV fault interface. Bench: hold-node capture at 3.135 V / cold; DIS against a forced rail fault.
    - **Candidate 29 (inlet filter onto the board): NO-GO for the board; its filter network becomes the D-22 module spec (rev B).**
      - The model has no harness, so the c29 network performs the same off-board. Moving it onto the board adds +$29.7 to board parts, +9 placements and 6 hand lines, and grows the mains edge 50–95 mm. It saves only $6.74 per system.
      - Leakage needs the module Y reduced whichever way it is mounted: at 9.1 nF/line the 0.974 mA fails even a 0.75 mA stationary limit.
      - **D-22 rev B:** delete the module Y (all line-to-PE Y at C3/C4, 2.2 nF per line), stage-1 CM choke 3.6 mH nanocrystalline (KEMET SCF39XV class), D-22's X caps and damping kept, plus the DM inductors below.
      - `revb_check.py`: 10.8 / 6.6 dB, PASS; unchanged with the inductor at −20 % and with 0.3 % choke leakage. The control reproduces c29's 10.79 / 6.60.
      - Touch current then depends on the supply term: 0.562 mA with three supplies at datasheet maximum, 0.419 mA with PS1 deleted (candidate 23). The certifier's leakage basis (F5) decides which is needed.
    - **D-22 DM inductors (OTT-18 condition of item 20): Würth WE-HCFT 74437636355602, 56 µH (49.7 µH at 21 A), one per line.**
      - On D-22's own basis the 6 dB-in-every-sensitivity rule needs ≥ 40 µH per leg at 21 A, not g01's 32 µH, which was on a 3.2 mH-choke basis.
      - 74437636355602 gives 11.73 / 7.71 dB. Both inductors together dissipate 1.6 W, 44 % of the module's 3.6 W allowance. It costs $18.94 at 30+ and DigiKey had 61 in stock. `dm_emi_check.py` reran bit-identical.
      - Second choice is the 47 µH MnZn 7443763540470 (11.31 / 7.39 dB, 1,021 stock, 2.9 W), only after a warm bench check, since its hot saturation is unpublished.
      - **Rejected: raising the fs floor instead.** `fsfloor_yield.py` reruns round 6's Monte Carlo (its control reproduces the committed yields). Full-power yield at 28 A and 120 V falls from 84.7 % (35 kHz) to 61.4 % (40 kHz) and 21.8 % (45 kHz).
      - Open: a volume quote, no agency marks on any candidate (certifier), and a bench L at 21 A DC / 15 A rms on a warm sample.
    - **Ledger follow-ups:**
      - **U9 BUS_FAULT:** add 1 kΩ / 47 pF at U13.A in stage 30. It adds about 57 ns against a 0.85–1.16 µs OCP chain whose tank di/dt is about 3 A/µs (≈ 0.2 A), and removes the nuisance-trip path into the controller's async CLR. The bench probe at hard S4/S5 edges stays as evidence.
      - **L1 at 15 A:** no change. The 80 % rule holds to 67.7 °C local air against the 50 °C inlet basis. Bench: L1 local air at 15 A in the enclosure (`DECISIONS.md:836`).
      - **RECOM U41/U42 reinforced isolation:** confirmed (/R Rev 1-2024). Closed.
      - **C5/C6 ripple above 22 A:** unchanged bench condition (cap ambient ≤ 75 °C or a case measurement).
    - **F1: decided by gates, not by opinion (`f1-data/f1_decision.py`, controls reproduce the s29 0.993 ratio).**
      - Gates: interrupting ≥ 8.4 kA at ≥ 140 V; carrying 25 A × 0.75 × derate(50 °C) ≥ 15 A; inrush and surge pulse factors; total clearing I²t ≤ the governing copper neck (1,697.7 A²s on s29); F2 selectivity (melt ≥ 2 × F2 clearing); and agency basis.
      - **Result: no candidate passes every gate.**
        - KLDR025 (today) fails copper by 0.7 % (1,710 vs 1,698 A²s, copper at 105 °C).
        - **Bel 0ADEC9250-BE** (6.3 × 32 ceramic fast, 30 kA at 500 VAC, cURus E20624) passes every technical gate: total I²t 470 A²s (re-read from the PDF; measured at its 500 V test, so it bounds 140 V), a copper ratio of **3.61**. It is $18.86 per board cheaper (fuse + clips $3.77 vs $22.63).
        - Its only open gate is G6, the certifier's acceptance of a UL-Recognized 248-14 supplemental fuse in place of a Listed Class CC.
        - The Littelfuse 0505025 is also blocked by G4 (no published clearing I²t). KLKR025 saves $2.11 but has four unknowns.
      - **Decision:** KLDR025 stays until the certifier answers. That one answer is worth $18.86 per board (≈ $9.4k per 500), plus copper margin 0.99 → 3.61.
      - If the answer is yes, switch to Bel 0ADEC9250-BE in Littelfuse 01220088Z clips: footprint back to 6.3 × 32, the C1/pour revert of g01 P2, and a let-through test at 5 and 8.4 kA prospective at first article.
      - BR1 stays sacrificial with every candidate (≤ 255 A²s needed).
    - **Price correction (applies at the next stage's stock addendum):**
      - KLDR025.TXP is **$18.516 at 500**, not $29.412 (that was DigiKey's 10-piece price).
      - The two 01250003H clips ($2.057 each at 500) are not in the BOM and so never reached the card.
      - The card moves by −$10.90 for the fuse. The clips get a BOM line when F1 is next touched. The 19c card is restated with the same correction so the comparison stays like-for-like.
33. **Stage 30: the three bias-monitor crossings become one heartbeat (candidate 24, M1b as built) and U9 BUS_FAULT gets an RC (2026-10-14; board `4fcae4bf8971718d38fc2fc9cb257e2ec044de2914e6f31d2df0204b1736ddfd`, copper.json `b096631d8d87260002076b7f8fe22138c683606c9a4030d4a5cda9b4fc7a0725`, schematic `f0a179bd…`, frozen netlist `89950de34e5771fc1b78ee2f07d63c68f715deb35b43b4ccea8c65f18d30144e`, Gerber ZIP `ba738003a82a2c25c5040a0d10ddb8edab3d5442713dc923f79588ca97e88288`; tag `native21s30`; candidate 24, `11-candidates/c24-monitor-fmea/` §6b, `08-manufacturing-package/native-21/stage30-heartbeat/`; SAFETY: bias supervision, OCP interface).**
    - **Why:** item 32. One reinforced monitor crossing in place of three, two zero-stock ISO7710s gone, dormant masking exposure down, and the BUS_FAULT nuisance path into the permit latch's async CLR closed.
    - **Change:**
      - **Heartbeat:** the LS and HS-A verdicts gate an LS Schmitt-NAND oscillator (U45, SN74LVC1G132). Its wave crosses on U32 (ISO7710) to the SELV NAND U46 (SN74LVC1G132), then 220 Ω → pump (D19 BAT54S) → hold → U40 → BIAS_GOOD. HS-A's verdict reaches LS on U43 ISO6721FB (default LOW) and one half of D18 (now a BAT54S). The per-rail notice stages U33 / U34, Q7–Q9 and the bias OR U25 are deleted, and with them the BAT54A line.
      - **Deviation from M1b: HS-B crosses to SELV, not to LS.** HS-B's verdict goes on its own U44 ISO7710FDWR (reinforced, default LOW) at U34's stage-29 pose, and its output HSB_GOOD is U46's second input. The ISO6721FB HS-B → LS link would not route: `spot_scan.py` finds no legal pose straddling HS-B and LS, and the one cluster tried (3.5, 47) left HS-B and LS nets open on every pass. The rows y 47–60 are closed on all four layers (U42's n_ls pocket, the SELV 8 mm floor, the protected In2 `bus_p` trunk and the B.Cu `n_hb` strip; README). That is a router outcome, not a rerunnable proof.
      - Single-fault coverage is unchanged (FMEA §6b): every HS-B failure that M1b announced is announced here too, because U44 defaults LOW and a static U46 stops the pump. U44 stuck HIGH is dormant for HS-B only, as the M1b ISO6721FB stuck-high row was. The cost is two reinforced HOT → SELV crossings (U32, U44) instead of one; stage 29 had three. The FIT figures were not re-run for this variant.
      - **HSB_GOOD routing:** U44's SELV pocket is closed by the permit / PWM / bias_good bundle and the 8 mm floor, so HSB_GOOD leaves on one authored 25.9 mm In2 leg (selv_gnd plane). In2 rather than In1, because the outer layer over an In2 leg (B.Cu) carries 0 mm of return-path-asserted nets, against 13.7 mm of pwm_lb / pwm_hb on F.Cu over the In1 leg (`inner_leg_overlap.py`).
      - **U9 BUS_FAULT:** R134 1 kΩ / C167 100 pF between U9 and U13.A (item 32 said 47 pF). 100 pF reuses C30's Basic line (CL10C101JB8NNNC), so no line is added. τ = 100 ns adds about 0.1 µs to a 0.85–1.16 µs OCP chain (≈ 0.3 A at the tank's ~3 A/µs). A ns-wide CMTI upset on U9 no longer reaches the async CLR.
    - **Evidence:**
      - audit.rs PASS 81/81 (new rows and mutation tests in `audit_f6.rs`); verify_source PASS; 349 components, 94 BOM lines.
      - Ledger gate PASS, 0 violations (ISO7710FDWR entry added, BAT54A removed). cmti_table.py: 7 PASS, 0 FAIL, 6 OPEN.
      - Passes 0 unconnected / 0 errors. Chain `native21s30` CHAIN_DONE with every gate clean: D5 8.047 / 8.507 mm, DFM PASS (710 vias), RES_A outer 13.375 mm, bypass PASS, return path PASS, B3 c28_h25 135.2 °C / nominal_h10 162.1 °C, Kelvin band 67.77–116.44 A, OCP pickup 4.17 A, necks 0.993 (unchanged).
      - Stock: ISO7710FDWR C2859831, 29 in JLC stock at the 2026-10-13 survey, $3.27 at 5 / $2.31 at 500 (`STOCK-2026-10-13-addendum-s30.csv`).
    - **Scorecard: ACCEPT against 19c and 29** (`scorecard-native21s30.json`).
      - Better: `return_path_open_changes` 37 → 23.
      - Cheaper: placements 350 → 349; parts at 500 $211.78 → $210.57 (−$1.21), at 5 $320.66 → $318.44.
      - The KLDR price correction of item 32 (−$10.90) is in both sides: the 19c and s29 cards are restated ($231.94 → $221.04, $222.68 → $211.78; each card's `restated` block, and the same `scorecard.cost()` call without the fix file reproduces the as-scored values). Against the unrestated s29 card, stage 30 would have looked $12.11 cheaper.
      - Costs: BOM lines 92 → 94, Extended 65 → 68, single-source 16 → 19, B3 +0.1 °C on both cases; zero-stock unchanged at 9. Vias 745 → 710.
    - **Known weaknesses and open candidates:**
      - **C161 (U45 decoupling):** its n_ls pad returns over 11.6 mm of F.Cu track. No legal C161 pose and no legal via exist on this floor plan, so bypass_check's U45 n_ls limit is 6.0 mm (was 3.0) with the reason in the code. Candidate: re-pose U45 / C161 when the LS cluster next moves.
      - **U44 → ISO6721FB:** the second legal cluster (x 17–18.5, y 76.5–77) was never route-tested. If it routes, the ISO6721FB is about $1.93 per board cheaper at 500 and drops a reinforced crossing.
      - **U44 stock:** 29 at JLC. Check it before ordering.
      - The pump SPICE (`m1_pump_spice.py`) sized the drive on an SN74LVC1G17 buffer; U46 is a G132 of the same family and was not simulated separately.
    - **Bench:**
      1. Heartbeat trip time ≤ 90 µs from each rail fault (LS, HS-A, HS-B), with U46's output current per edge.
      2. U44 default LOW: unpower HS-B and open U44 IN; BIAS_GOOD must drop.
      3. Hold-node capture at 3.135 V / cold (item 32).
      4. BUS_FAULT at the U13.A pin at hard S4 / S5 edges, and the OCP trip delay with R134 / C167 fitted.
      5. S4 / S5 dv/dt (also item 31's CMTI basis).
34. **Stage 31: U9 / U32 / U44 become Chipanalog CA-IS3720HW / LW, and the 24 × 1210 10 µF become Samsung CL32B106KBJNNNE (2026-10-14; BOM only, copper.json `b096631d…` unchanged from stage 30; board `5ef1c37a41914825db33138bbbf765390b1fa5ae9ea4391b45c92fc8c2854bad`, schematic `307eda01…`, frozen netlist `f23302546e74894f099d3a79a888c0f915c3dbee5ae6020d3362d8f5c5cc42e7`, Gerber ZIP `f24f40fdde0a0fd54f4169c859e7a4672fd6a2d76ba70a3d13b91e1f0c9a7d07`; tag `native21s31`; `11-candidates/c31-bom/`; SAFETY: HOT → SELV isolation).**
    - **Why the layout candidates waited:**
      - 30a, the HS-B → LS ISO6721FB, is blocked. The second legal cluster still exists on the stage-30 board, but its LS nets would face the same closed y 47–60 band, and the SELV spine bars any route east.
      - 30b, C161, is blocked too: its column is taken on In1, In2 and B.Cu.
      - Both wait for the next LS-cluster move. That left the BOM's stock and price risks as the lever.
    - **Change:**
      - **U9 / U32: ISO7710DWR → CA-IS3720HW. U44: ISO7710FDWR → CA-IS3720LW.**
        - ISO7710DWR had zero stock at every source checked; ISO7710FDWR had 29 at JLC. JLC has 1,640 / 2,542 of the new parts.
        - Every used pin matches the ISO7710DW pinout, and the parts sit on the same TI DW0016B HV pads.
        - The spare second channel (pin 5 input, pin 12 output) stays on single-pin nets. A new audit.rs rule and mutation test enforce that.
        - Default output on side-A power loss **or an open input** is HIGH / LOW by suffix (Table 9-1), so FMEA §6b holds unchanged.
        - Reinforced (VDE 0884-17 40057278), UL 1577 E511334 at 5 kVrms, CLR / CPG 8 mm, CTI > 600.
        - CMTI min 100 kV/µs, against 85 for the ISO7710.
      - **24 × UMK325AB7106KM-T → CL32B106KBJNNNE.**
        - JLC had 3,921 of the Taiyo part against 12,000 per 500 boards, and TY-COMPAS lists it "non-preferred". JLC has 44,561 of the Samsung part.
        - It keeps more capacitance at bias, with −10 % tolerance and 100 °C: 17 V 3.16 → 5.26 µF, 24 V 2.22 → 3.87 µF. At 2–5 V it is within 3 %.
    - **Rejected:**
      - **Novosense NSi822xW** (CMTI min 200, which would meet the 1.5× rule): its datasheet gives no open-input output state, which FMEA §6b relies on, and the default-HIGH variant had 91 at JLC.
      - **BR1 → MDD GBJ2510** (R2-03): no UL file number found for the MDD part, and it saves only $0.37.
      - **D3 / D17 second sources:** every 30KPA150 variant has zero JLC stock, and DC-LINK-CLAMP.md forbids a silent change of suffix or family. That is the owner's sourcing round (`c31-bom/BUS-TVS.md`).
    - **Evidence:**
      - The atopile rebuild changes only the 27 MPNs: the nets section is byte-identical.
      - audit.rs PASS, 82/82 (new `isolator_spare_output_tied_to_rail_fails`); verify_source PASS (349 parts, 24 × CL32B106KBJNNNE).
      - Ledger gate PASS: CA-IS3720HW / LW PARTIAL (the CMTI gap is now 0.95, against 1.12), CL32B106KBJNNNE PARTIAL (was UNAUDITED).
      - The D5 audit table gains the CA-IS3720 package distances. It had shown ISO7710FDWR as "NOT IN TABLE" at stage 30.
      - cmti_table.py: 7 PASS, 0 FAIL, 6 OPEN.
      - `c31-bom/mlcc_bias.py` PASS: the driver VSS pairs keep 16.3 µF effective against the ECO's 10 µF. The RECOM P–N start-up bound holds: 21.4 µF nominal, against 41.4 µF simulated passing (ALT-BIAS §3.4).
      - Chain `native21s31` CHAIN_DONE on the stage-30 pass. Every gate is clean; task 04 and B3 hit the cache (copper unchanged); necks 0.993; OCP pickup rerun; ERC `ground_pin_not_ground` 5 → 1.
    - **Price basis:** the stock survey had carried UMK325AB7106KM-T at a class-default estimate ($0.12 at 500). It is corrected to the JLC ladder ($0.2186; `sourcing/STOCK-2026-10-13_pricefix-umk325.csv`). The 19c and s30 cards are restated ($221.04 → $223.41, $210.57 → $212.94; each card's restatement block, reproduced by the same `scorecard.cost()` call without the fix file).
    - **Scorecard: ACCEPT against 19c and 30** (`scorecard-native21s31.json`).
      - Cheaper: parts at 500 $212.94 → $208.08 (−$4.86), at 5 $318.55 → $313.28; zero-stock lines 9 → 8.
      - Every gate and performance metric is identical. The card has no metric for isolator CMTI or capacitance at bias, so those gains are recorded here and in the ledger.
      - Single-source lines stay at 19: Chipanalog replaces TI one for one.
    - **Open:**
      - s19b BP-04 is still unmet at 15 / 17 / 24 V with either 1210 part (57 / 53 / 39 % of nominal).
      - UL file E511334 is quoted from the datasheet and has not been looked up in UL Product iQ (certifier item).
      - Bench: U44 open-input and HS-B power-off default (item 33 bench 2), and U9 / U32 output levels at 3.3 V.
35. **Stage 32: via cleanup, 0.85/0.3 → 0.6/0.3, and three slow SELV hops move from B.Cu to In2 (2026-10-14; BOM unchanged; board `2fb346dc8277e4295d8ef88effabdcc71dcd363fcaa93604800ddc2872fbfa4e`, copper.json `d6f55dfedcd8b83f9260c41a7d3ed5091c9d02b8ee14db4f178d720b2a55bc63`, schematic `307eda01…` and frozen netlist `f2330254…` unchanged, Gerber ZIP `b9b25cb5ead3e32a442bd564fbf60108d4f28cd70691fa8cd134089075774043`; tag `native21s32`; layout only).**
    - **Why:** the stage-31 board carried 124 vias at 0.85/0.3, the route21 legacy default, beside 571 at the 0.6/0.3 standard. They have the same 0.3 mm drill, so the same barrel current, and every one of them is POFV. Two sizes of the same drill is one more line in the drill / fill setup with no electrical reason. Separately, 23 return-path reference changes were open, all on slow, unasserted nets.
    - **Change:**
      - **Via sizes:** `incr21.std_vias()` runs last in every pass, after the via-in-pad and merge steps, and turns each 0.85/0.3 via into 0.6/0.3. Routing still sees the old 0.85 ring, so the step only removes copper.
        - Where a same-net track or pad reached the old ring but would miss the new one, a stub joins it to the via centre, inside the old ring (18 stubs). The first pass lost C67.2 because only its rounded corner touched the old ring; the pad stub fixes that.
        - The defaults moved too: `route21.via()` 0.85 → 0.6 and `geom21.via_spot()` 0.85 → 0.6, plus the explicit 0.85 vias of the stage-21b Kelvin drop (ocp_kelvin_n) and the stage-30 U2.8 v3v3 drop.
        - **Kept at 0.85:** the 4 vias on the mains nets ac_n_in / l_filt / n_filt (STD_VIA_KEEP), including the stage-27 R2 via. Task 04 solves those nets on its 0.125 mm grid, which does not resolve a 0.15 mm ring. The first stage-32 chain failed task 04's topology check on exactly these three nets. The other option was to add them to task 04's fine-pitch set; it was not taken, because keeping a larger ring on mains copper costs nothing.
        - Result: 0.6/0.3 571 → 691; 0.85/0.3 124 → 4; 0.8/0.5 (5) and 1.6/0.8 (10) unchanged; 710 vias in total, as before.
      - **SELV hops on In2** (`patches21.add_stage32_in2`): in the SELV area F.Cu rides In1 (v3v3) and B.Cu rides In2 (selv_gnd), and B has no pour. So a line that ducks under an F run on B changes reference at both of its vias. A hop on In2 looks through the empty B to In1 on both sides, so neither via is a reference change.
        - HSB_GOOD's B leg (44.5, 129.0) → (49.2, 133.7) moves to In2, continuing the stage-30 In2 leg. The via at (44.5, 129.0) goes.
        - BUS_FAULT_ISO's B hop under pwm_lb, (39.025 → 36.025, 133.475), moves to In2.
        - BIAS_GOOD's branch to U40.4 is authored. The pair router had built it B → F → B → F through (69.2, 127.0), (68.463, 128.6) and (68.463, 133.0); it is now In2 from the trunk via. The via at (68.463, 128.6) goes.
        - There are 0 mm of asserted return-path nets on B within the hops' half-width + 0.5 mm. The nearest is pwm_ha, 0.79 mm from the BIAS_GOOD hop (centreline). return_path19 passes with 0 wrong-reference samples on every asserted net.
        - Router variance elsewhere: the ls_v5 run near U45 re-laid; n_ls +1 via, selv_gnd +2, v3v3 −1.
    - **Not closed (18 left):** the remaining changes need copper that is not cheap.
      - 11 sit where no pour reaches the via on at least one side: bus_fault_hot 3, ocp_ok_hot 1, ovp_ok_hot 2, mon_good_ha 4, and bias_good at (69.2, 127.0) on the In1 / In2 pour edge.
      - 7 are on long B runs whose F / B changes lie more than 3 mm from any v3v3–selv_gnd capacitor: permit 3, bias_good trunk 2, bus_fault 1, bus_fault_iso at (76.825, 125.875). bus_fault's via is boxed in by U13's pad column. Moving a via within 3 mm of C47 / C144 / C153 would need re-routing the PWM bundle.
      - The list is in `stage19-pi-si/return-path32.json`.
    - **Evidence:**
      - Passes `runs-native21/s32/p3`: i2 has 0 unconnected and 0 errors.
      - Chain `native21s32` CHAIN_DONE, every gate clean:
        - D5 8.047 / 8.507 mm; Rust barrier 0; RES_A outer 13.375 mm.
        - DFM PASS, 710 vias; bypass PASS; return path PASS.
        - Task 04: 39 scenarios, 0 failed, bus_p span 2.84 %.
        - B3 c28_h25 135.0 °C, nominal_h10 162.1 °C.
        - Kelvin band 67.77–116.44 A. R35.2 transfer 152.82 → 152.90 mΩ (the ocp_kelvin_p plane vias shrank).
      - Necks 0.993 (`s32_necks.json`); OCP pickup 4.17 A (`result-s32.json`). audit.rs PASS (BOM unchanged).
      - Bring-up probe planning places one more signal test point: 23 instead of 22, and PERMIT is no longer missing.
      - via_in_pad.py: 61 drills inside SMD pads, 78 at a pad edge (stage 31: 62 / 77). **Every 0.3 mm via still needs POFV**, so this stage does not remove the 4-layer POFV charge.
    - **Scorecard: ACCEPT against 19c and 31** (`scorecard-native21s32.json`). Better: `return_path_open_changes` 23 → 18, B3 c28_h25 135.2 → 135.0 °C (inside its 1 °C tolerance). Cost is identical (BOM unchanged), and every other gate and metric is the same.
    - **Open:** the via-in-pad census is unchanged, so the JLC 4-layer POFV premium still applies. Removing via-in-pad (R5 current fields, U26 thermal field, RECOM edges) is a separate study that needs R5 / U26 thermal re-validation.

36. **Fab spec and next study: keep 4-layer POFV, open a six-layer study (2026-10-14; no board change).**
    - **Data:** JLC instant quote 2026-10-14 (`validation-results/11-candidates/c33-six-layer/jlc-quote-2026-10-14.json`; 290 × 190 mm, 1.6 mm, ENIG, 2 / 2 oz, flying probe). At 500: 4 L plugged $15.25 per board, 4 L epoxy filled and capped (FAB-NOTE) $16.79, 6 L filled and capped (no POFV charge on 6 L) $16.18. At 5: $186.99 / $214.36 / $196.59. None of JLC's listed surcharges applies (`enig_area.py`: ENIG 3.1 % of top + bottom against 30 %; 451.5 cm² < 650 cm²).
    - **Decision 1: keep POFV on four layers.** The premium is $1.54 per board; removing via-in-pad would need the U26 thermal field, the R5 current fields and the U41 / U42 edge vias re-validated. Not worth it for $1.54.
    - **Decision 2: open candidate 33, six layers** (`c33-six-layer/PLAN.md`). It is $0.61 per board cheaper than today's spec and adds two planes for the routing-bound areas (30a / 30b, the 18 return-path open changes). The 8.0 mm barrier and 12.6 mm RES_A spacing are plan-view on every layer and every through-laminate path is ≥ 8.0 mm (item 18), so thinner dielectrics do not change the safety basis.
    - **Order:** the step-0 audit (`AUDIT-4L.md`) found the stack copied from native-20 by `build_native21.py` and hard-coded in six models (B3 also reads native-17's stack and silently drops unknown layers), so a behaviour-neutral refactor comes first, proved by unchanged s31 / s32 outputs. Then phase A (same outline, 6 L), then phase B: candidate 23 (PS1 deleted, controller request `c23-supply-topology/CONTROLLER-REQUEST.md`) with compaction. If phase A does not pay, candidate 23 goes ahead on four layers.
    - **Also filed:** the certifier / owner packet `08-manufacturing-package/native-21/owner-items/CERTIFIER-PACKET.md` (draft, not sent); IRM-20-15 / -24 ledger entries gain the 4.2 kVac I/P-O/P and < 0.25 mA ratings and the UL 62368-1 approval-basis gap.
    - **Reverses if:** a 6-layer Gerber quote prices the inner copper above the instant quote by more than $0.61 per board, or phase A fails a gate.

37. **Resonant bank basis and the tank ceiling; layout parallelisation plan (2026-10-14; records and scorecard metric only, no board change).**
    - **Bank basis:** the right figure is the J (±5 %) worst-share ratio at the 35 kHz window floor, the worst legal frequency for every TDK 1600 V curve (`validation-results/11-candidates/c34-bank-margin/`, `scripts/bank_margin.py`; it reproduces round 6's 1.117, bank_options' 1.022 and round 6's current table as controls). Today's 5 × B32654A1104J000 is **1.045** at 28 A, so it reaches TDK's 85 °C curve at 26.8 A and 0.85 of it at 22.8 A.
    - **Consequence for the ceiling (item 10):** the shipped 22 A ceiling stays inside the bank's 0.85 margin. Raising it toward 28 A needs the bank change as well as the bench evidence item 10 lists; bench evidence alone does not clear 1.045.
    - **Scorecard:** new metric `bank_ratio_tdk_28A_35k` (lower is better) beside the 40 kHz one; the 19c (K, 1.13), s31 and s32 (J, 1.045) cards gain it with a `restated_bank35k` block. A full re-score of s32 with the updated `scorecard.py` differs from its card only in that metric.
    - **Candidate 34 (QUEUE):** 5 × TDK B32643B8104J000 (100 nF ±5 %, 2000 Vdc, 22.5 mm pitch) is 0.831 / 0.796 at 35 / 50 kHz, same 0.50 µF. Browser stock check 2026-10-14: DigiKey 495-B32643B8104J000-ND not stocked, orderable, manufacturer lead time **28 weeks**, MOQ 2,080 at $1.30931; LCSC C3781430 out of stock; JLC 0; Mouser not readable (bot check). DigiKey's suggested substitute B32643H8104J000 (306 in stock) fails the margin (0.98 at 35 kHz, c34 README). The fallback 4 × B32643B8124J + 1 × B32643B8683J has no DigiKey listing for the 68 nF part. So candidate 34 is a long-lead order question; the stock / lead-time inquiry is in the outreach packet and should go out early.
    - **Layout parallelisation** (`validation-results/13-coupling/`, 126 controls, history AUC 0.81): part and value swaps run in parallel across all groups under the contract "same footprint, pin → net map, height envelope, heat ≤ its B3 input, ledger row". Layout work is scheduled by isolation island (HS-A, HS-B, LS, SELV; the function groups stay the review units) and in at most five workstreams, enforceable once the SELV spine (x 30-110, y 130-180) is locked like the stage-28 OCP lock. Order: the layer refactor lands, then six-layer phase A as one serial whole-board pass (with the candidate-34 footprint if the part is obtainable), then the SELV-spine lock on the winning board, then parallel lanes (30a / 30b; candidate 23 after the controller's J13 merge; candidate 34), merged one at a time through the scorecard against the contracts in `13-coupling/results/contracts.json`.

38. **Layer-stack refactor merged; depth basis for the six-layer study (2026-10-14; no board change).**
    - **Merged** (`63f175d1e`, `0561f5870`): `native-21/stackup.json` is tracked and is native-21's single layer-stack source; `build_native21.py` writes the board stack from it (it no longer copies native-20's); `native-21/layout/layers21.py` serves the layout scripts, gates and models; `$NATIVE21_STACKUP` swaps the stack. B3 now raises on copper on an unknown layer instead of dropping it. Proof: `validation-results/11-candidates/c33-six-layer/REFACTOR-PROOF.md` (86 / 86 artefacts equal on the same board file for s31 and s32; fresh rebuilds equal after removing KiCad UUIDs and zone-fill noise; scorecard compare: no change). Tests `test_layers21.py`, `b3/test_layers.py` and `sheet_solver --selftest` pass on the integration branch.
    - **F8 depths:** coil-pickup `loops.py` used In1 / In2 / B at 0.47 / 1.03 / 1.50 mm below F.Cu; the stack gives 0.501 / 1.062 / 1.563. On s32 copper the stack depths give 4.133 A against 4.173 A (`ocp_pickup_stack_pan60_A`, −1 %; old depths reproduce 4.173 exactly). The old values stay the default (`Z_DEPTH_OVERRIDE_MM`) so every committed result reproduces. **Decision:** the six-layer study scores with stack depths (`F8_Z=stackup`) for both its own boards and a re-run of s32, so every comparison is on one basis. The same rule applies to the sheet solver's fixed 1.6 mm barrel length (stack: 1.563 mm centre to centre).
    - **Chain cache trap (open, fix before phase A):** when scripts change but copper does not, task 04 takes a cache hit while B3 recomputes, and B3 then fails its board-hash check. Cache keys must include the hashes of the scripts they run.

39. **Six-layer phase A merged and accepted on the data; adoption pending checks (2026-10-14; candidate 33; board of record still s32).**
    - **Merged** from `claude/native21-six-layer` (cherry-picked as `1bbc23b3b`, `d71df9623`, `e4641c663`):
      - the chain cache fix: one model key for the task-04 and B3 caches (`gates/model_key.py`, `c33-six-layer/CACHE-PROOF.md`);
      - `native-21/stackup-6L.json`; `patches21.add_stage33` (image pours, stitch vias); `INCR21_FROZEN` (an accepted
        routed copper.json as the base, plus only the stage-33 layers);
      - return_path19 / scorecard judge a same-net stitch farther than 3.0 mm as an open change;
      - the evidence in `validation-results/11-candidates/c33-six-layer/` (PHASE-A.md).
    - **Plan A + In3 image:** In1 as today; In2 bus_p / selv_gnd, so bus_p / hv_ret are a 0.30 mm core pair (0.5 mm on
      four layers); In3 signal plus a bus_p image under the bridge (without it task 04's bus_p span was 3.17 % > 3 %);
      In4 images of v3v3, n_ha, n_hb, n_ls and ocp_kelvin_p, with no plane under the B-side switch nodes. Plan B (In4 as
      the plane) is rejected: +2.90 / +1.67 nH on the plane-pair screen against A's −1.28 / −0.74 nH.
    - **Board native21s33 (710c0a45):** stage 32's routed copper frozen as the base; one pass, 0 unconnected, 0 errors;
      CHAIN_DONE with every gate clean. **Scorecard ACCEPT against 19c, s32 and s32 restated on the stack basis**
      (item 38), with identical parts. Better against s32 restated: return-path open changes 18 → 8, worst asserted
      2.72 → 2.38 mm, B3 c28_h25 134.9 → 129.3 °C, nominal_h10 162.0 → 155.1 °C, OCP pickup 4.13 → 3.72 A, Kelvin band
      low 67.77 → 67.79 A. Nothing is worse. Bare board $16.18 against $16.79 per board at 500, but a 10–11 day build
      against 5–6.
    - **Re-checked on the integration branch after the merge:**
      - the scorecard compares reproduce both ACCEPTs;
      - return_path19 on the s32 copper dump is identical to s32's committed output (only the new, empty `stitches`
        keys and Python object ids differ), so the gate change is neutral on four layers;
      - `ROUTE4` is every layer on four layers, and `add_stage33` is a no-op without `image_planes`;
      - the spine-lock, trim-tails and datasheet-ledger controls pass;
      - `spine_lock.py` on s33: 0 removed, 128 added (THT pad copper on In3 / In4, the In4 v3v3 image, stitch vias).
        Every s32 spine item is still there.
    - **Not closed:** 30b (C161 still reaches n_ls through about 4.5 mm of In1; the In4 image is cut under bus_fault_hot).
      30a was not attempted. In the y 47–60 band HS-B can now cross on In2 and In4, but no cell is via-legal on every layer.
      Eight open changes remain where no pour reaches.
    - **Before adoption** (the stack becomes the board of record, copper-s33 becomes `layout/copper.json`, the FAB-NOTE
      moves to six layers):
      1. FEM re-extraction of the commutation loops on the six-layer copper (round-17 set-up: leg A 37.6, leg B 24.5 nH),
         with the F6 decision and startup cases re-run if either loop rises;
      2. the switch-node capacitance (screen 303 → 312 pF; sw_a 91 → 155 pF) against the ZVS dead-time margin;
      3. EMI: `emi_s19b.py` models only the outer-layer switch-node pours to the PE pedestal. Those are unchanged on s33
         (frozen base), and only the B.Cu depth moves (1.6 → 1.658 mm), so it is a confirmation run;
      4. a 6-layer Gerber quote of `native-21-gerbers-s33-6L.zip` (an upload to JLC: owner's yes first);
      5. the CTI / solid-insulation inquiry re-asked for JLC061622-1080A (owner's outreach).
    - **Touch leakage is not on the list.** `leakage_budget.py` counts only the Y capacitors and the supplies' datasheet
      maximum leakage; the BOM is identical, so it does not depend on the stack.
    - **Lanes:** the island lanes (13-coupling) start on the adopted board, and the SELV-spine lock is re-issued from its
      export, since 30a's new crossing room exists only on six layers. The BOM-only lane is not affected.
    - **Reverses if:** FEM or ZVS margin on the six-layer copper is worse than s32's, or the Gerber quote prices six
      layers above four-layer POFV.

40. **Six layers not adopted: the Gerber quote prices the pinned stack above four layers (2026-10-14; board of record stays s32, four layers).**
    - **Quote** (`validation-results/11-candidates/c33-six-layer/jlc-gerber-quote-2026-10-14.json`; owner approved the
      upload). JLC parsed the s33 Gerber ZIP as 6 layers, 290 × 190 mm. At 500, ENIG, 2 / 2 oz, epoxy filled and capped,
      flying probe:

      | build | per board | build time |
      |---|---|---|
      | 6 L, JLC061622-1080A pinned (the stack phase A was modelled and scored on) | **$19.11** (stackup fee $2.93) | 10–11 days |
      | 4 L, JLC041622-7628 pinned (FAB-JLCPCB.md requires it) | **$17.28** (stackup fee $0.49) | 5–6 days |
      | 6 L, "No requirement" | $16.18 | 10–11 days |
      | 4 L, "No requirement" | $16.79 | 5–6 days |

    - **What was wrong before:** items 36 and 39 compared $16.18 with $16.79. Both are "No requirement" prices, and the
      instant quote showed no stackup fee. Pinning a stack adds one, and the "No requirement" builds are not the stacks
      the designs assume:
      - six layers by default: 0.35 mm cores and two-ply outer prepreg, not 1080A's 0.30 mm and three-ply;
      - four layers by default: 3313 prepreg on a 0.96 mm core, not 7628's 0.5 mm.

      **The four-layer board of record costs $17.28 per board at 500, not $16.79.**
    - **Decision:** six layers on the pinned stack is $1.83 per board dearer ($915 per 500) and 5 days slower. Item 39's
      reversal condition holds, and the standing rule is that a change must be both cheaper and better. Six layers is not
      adopted. Phase A's tooling stays merged (stack file, images, frozen-base passes, cache fix). Its scorecard gains
      (return-path open changes 18 → 8, B3 −5.6 / −6.9 °C, OCP pickup 4.13 → 3.72 A) are the measure of what a later
      four-layer change has to match.
    - **Not pursued now: six layers on "No requirement".** That build is $1.10 per board below four layers pinned, but JLC
      does not say whether it is fixed. On a mains board whose loop, thermal and pickup models depend on dielectric depths,
      an unpinned stack is acceptable only if every gate passes over every stack JLC might build. That would mean
      scoring s33 on each JLC 6-layer 2 / 2 oz stack, or on the envelope of them. Question 6 of the CTI inquiry
      (`08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC-6L.md`) asks JLC whether the "No requirement" stack
      is fixed; the route reopens only if JLC says it is.
    - **Adoption checks (item 39), on record in `c33-six-layer/adoption/` (merged as `667184760`, `e241cb208`):**
      - **ZVS** (as-built F6 / 2EDR deck plus the screen's board node capacitance, 2016 runs: 170 / 198 / 280 V, typical /
        weak / strong driver, 27–150 °C; the zero-capacitance control reproduces 24 committed c25 rows to 0.5 mV): the
        margin at the 340 ns audit edge is leg A 151.1 → 150.6 ns, leg B 149.6 → 150.0 ns. The worse leg improves, and
        leg A loses 0.5 ns (0.3 %). ZVS holds at 37 A in every worst-corner case.
      - **EMI:** `emi_min_margin_dB` is 10.5 dB on both boards (the outer switch-node pours are identical; the control
        reproduces s19b's committed results).
      - **FEM: deferred.** Round 17's 37.6 / 24.5 nH came from native-21's first routed board (76ec8cca), not s32, so a
        comparison needs both boards re-extracted. The campaign is ready (`adoption/fem/chain_c33.sh`). The round-17
        mesher now takes `MESH_STACKUP` and refuses copper on a layer outside its stack; unset, it is unchanged
        (`test_stack_layers.py`, 4 pass, run in the `temper-fem` environment). The remote box was offline.
      - Nothing here argues against six layers on engineering grounds; the decision is on price alone.
    - **Lanes:** the island lanes and the SELV-spine lock stay on the four-layer s32 board (`selv_spine_lock.json` as
      committed). 30a / 30b stay blocked on four layers (stage 31 analysis), so the next layout lane is the SELV side
      (candidate 23) once the controller merges J13.

41. **Laminate CTI settled from public records: name KB-6164 on the order; the JLC inquiry is not needed (2026-10-14).**
    - **Evidence** (`validation-results/08-manufacturing-package/native-21/sourcing/inquiries/CTI-RESEARCH-2026-10-14.md`):
      - UL file E123995, published by Kingboard as a UL Product iQ reprint (QMTS2, last updated 2026-02-20): KB-616(X),
        with X = 0 or 4, CTI PLC 3 at 1.40 mm;
      - Kingboard's official TDS (2025-03-13): CTI ≥ 175 V per IEC 60112;
      - Kingboard's product table: 175 V.

      PLC 3 is group IIIa, which meets D5-BASIS with no margin. No JLC-selectable laminate has public PLC ≤ 2 evidence.
      Nan Ya publishes no CTI. Shengyi's TDS gives PLC 3, but no UL data was found.
    - **Decision:** order with Material Type "KB6164 - TG135" (+$0.28 per board at 500) and the stack named
      (JLC041622-7628), with the order remark "KB-6164 core with KB-6064 prepreg throughout; state the laminate on the
      shipment documents". FAB-NOTE.md and FAB-JLCPCB.md are updated. The CTI written-confirmation gate is replaced by
      the named material. `CTI-JLC.md` / `CTI-JLC-6L.md` are not sent.
    - **Residual (order remark, not a gate):** whether JLC also uses Kingboard prepreg in the named stack. JLC offers no
      per-order material certificate. The certifier still has to accept PLC 3 as evidence of IEC 60664-1 group IIIa
      (CERTIFIER-PACKET A3).
    - **Open, found by the same research: board thickness.** JLC publishes ±10 % for boards ≥ 1.0 mm, so 1.6 mm nominal can
      finish at 1.44 mm. FAB-NOTE requires 1.6–1.76 mm for the REDCUBE THR studs (review m7), and no published JLC option
      guarantees that at 1.6 mm. FAB-NOTE's own fallback is a 1.8 mm build: ±10 % gives 1.62–1.98 mm, inside the studs'
      1.6–2.0 mm. A 1.8 mm stack changes every dielectric depth, so it is a design candidate (re-run the chain, F8 and
      B3 on the stack file), not an order note. It is queued with the stud datasheet re-read first, to check whether
      1.6 mm is a hard minimum.

42. **Coil-terminal board thickness: the REDCUBE THR datasheet makes 1.6 mm a hard minimum; candidate 35 (SMT terminals) queued (2026-10-14; no board change).**
    - **Datasheet read** (Würth 74650074, WP-THRBU REDCUBE, rev 002.002, 2022-08-01; ledger entry updated, gate PASS):
      "PCB Thickness min 1.6 mm", max 2 mm; IR 50 A max at 20 °C, with no derating curve; 1.2 N·m. Wave soldering is not
      applicable; reflow is recommended.
    - **Conflict:** JLC publishes ±10 % for boards ≥ 1.0 mm, and its 4-layer thicknesses go 1.6 → 2.0 mm with no 1.8 mm
      (quote form; JLC stack data, 2 / 2 oz: 0.8 / 1.0 / 1.2 / 1.6 / 2.0). 1.6 mm can finish at 1.44 mm, and 2.0 mm can
      finish at 2.2 mm. FAB-NOTE's "re-stack at 1.8 mm" fallback does not exist at JLC.
    - **Interim (order):** keep 1.6 mm (JLC041622-7628, 1.633 mm nominal by layer sum). Add the order remark "finished
      thickness 1.60–1.76 mm required (terminal specification)". "Confirm production file" is selected, so JLC's
      engineering review answers it before production. That costs no time now.
    - **Candidate 35:** J2 / J5 → Würth WP-SMBU 7466004R (SMT, M4 internal through-hole thread, 50 A at 20 °C, 1.2 N·m,
      tape and reel; rev 001.003, 2023-07-03). Its datasheet states no PCB thickness, and it removes the THR process
      question. To check: footprint against the RES_A 12.6 mm keep-out, terminal heat in B3 at the 29.4 A trip (one F.Cu
      pad plus vias against four THT pads into every layer), and the lug and screw stack with the enclosure session.
      It goes in the tank (WS3) lane.

43. **Track-geometry hygiene measured and ratcheted (2026-10-15; scorecard metric, no board change).**
    - **Measured** (`native-21/layout/gates/track_geometry.py`, 7 controls in `test_track_geometry.py`) on s32: 81 % of
      track segments and 93 % of track length are octilinear, and 1,820 bends are 45°. But there are 104 right-angle
      corners (F 70, In1 20, B 9, In2 5), 206 acute corners including 44 fold-backs (a track doubling back on itself is
      redundant copper), and 704 mm of any-angle track. 19c: 110 / 198 / 35 / 699 mm. The numbers have not improved over
      the stages, because nothing measured them.
    - **Scorecard:** `track_acute_corners` and `track_fold_backs` are a strict ratchet (lower, tolerance 0).
      `track_right_angle_corners` (+5) and `track_any_angle_mm` (+25 mm) get a small allowance so a lane's new routes are
      not rejected for a bend or two. The s32 and 19c cards gain them (`restated_track_geometry`); a full s32 re-score
      differs from its card only in these four.
    - **Why it matters:** the electrical effect of a 90° corner at these edge rates is negligible. The reasons are
      manufacturability and review: acute copper corners are the DFM etch-trap flag, fold-backs are dead copper, and
      mitred octilinear routing is what a reviewer reads as finished work.
    - **Fix (planned):** a deterministic post-route cleanup pass (remove fold-backs, mitre right angles, open acute
      corners, snap any-angle runs where clearance allows). It is proved on s32 copper first, with the whole chain
      re-run, and applied as a final global pass after the island lanes merge, since it touches every island.

44. **Coil terminals J2 / J5 → Würth REDCUBE SMT 7466004R (stage 35, candidate 35; adopted, 2026-10-15). Board of
    record: s35 (board fba59ef3).**
    - **What:** both coil terminals change from the THR 74650074 to the WP-SMBU SMT 7466004R (M4 internal through-hole
      thread, 50 A at 20 °C, 1.2 N·m, −55…+150 °C, tape and reel; rev 001.003, 2023-07-03).
      - Footprint: Ø8.5 / Ø5.7 copper ring round a Ø5.2 NPTH, four paste segments; 20 land vias per terminal, 0.85 / 0.3
        (`patches21.add_stage35`), on stage 32's routed copper. Nothing else moves.
      - Closes DECISIONS 42: the SMT datasheet has no PCB-thickness limit, so the 1.6–2.0 mm conflict with JLC's ±10 %
        is gone, and FAB-NOTE's thickness remark is dropped.
    - **Why:**
      - JLC can assemble it: tape and reel on the standard SMT line, via Global Sourcing (DigiKey 8,856; Mouser 2,920).
        The THR part cannot be wave soldered (Würth) and JLC publishes no pin-in-paste service, so it would have been
        hand-soldered, unverified.
      - Cheaper: parts $206.44 against $208.08 per board at 500 ($311.47 / $313.28 at 5); one fewer hand / consign
        line and one fewer THT line.
    - **Evidence:**
      - Chain `native21s35` (board fba59ef3): DRC 0, RES_A outer F 20.393 / B 13.375 mm (unchanged), DFM 750 vias, FIT
        clean, SPINE_LOCK clean, Kelvin 67.77–116.44 A. Necks 0.993 and OCP pickup 4.17 A, as s32.
      - Integration scorecard re-score (`10-benchmark/scorecard-native21s35.json`): **ACCEPT against s32** (cheaper
        parts_usd_at_500 and hand_or_consign_lines; nothing worse). Track geometry is identical to s32 (104 / 206 / 44 /
        704.4 mm). Against 19c the compare is now REJECT, only on item 43's strict geometry ratchets
        (acute 206 vs 198, fold-backs 44 vs 35), which s32 fails identically; the planned cleanup pass (item 43) is the
        fix. `c35-smt-terminals/results/compare.txt` keeps both the branch and the re-score lines.
      - `validation-results/11-candidates/c35-smt-terminals/README.md`.
    - **Model change:** task 04 (`run_board.sink_contacts`) sinks a stud ring land (a pad with a hole and no drill) at
      24 equipotential points on its ring instead of the custom-pad anchor, which forced all the terminal current
      through one edge point and read the SMT terminal 13–42 K hot. Within 1 % of sinking every node under the Ø7 body;
      drilled leads (every other part) are unchanged (`scripts/terminal_sink.py`).
    - **Cost:**
      - Terminal copper 0.5–3.7 K warmer than the THR at every B3 point (c28_h25 J5 74.6 / J2 75.2 °C against
        72.3 / 73.9); the board peak is unchanged. Ledger: 103.45 / 150 °C at c28_h10.
      - The lug seat rises 2.5 mm (5.0 mm body): R26 coil-lead screen and screw length go to the enclosure session
        (`c35-smt-terminals/ENCLOSURE-REQUEST.md`).
      - Pull rating 300–410 N (design guide p.9): bench pull and torque test. 150 µm paste at J2 / J5 needs a stencil
        choice (step stencil or aperture). J2 / J5 CPL rows are NEEDS-PREVIEW.
    - **Reverses if:** the bench shows the soldered terminal failing the lug pull or torque, or running hotter at 28 A
      than the THR by more than the model's few kelvin; or JLC's file review refuses the part, the paste or the height.

45. **Sourcing snapshot, buildability metric and pre-order plan (2026-10-15; scorecard metric and records, no board
    change).** Study: `validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/` (`run_all.sh`
    reproduces every result offline).
    - **Snapshot** `sourcing/SNAPSHOT-2026-10-15.csv`: one numeric row per BOM line (JLC parts API for all 94 lines and
      40 alternates; Octopart public pages for 52 MPNs; DigiKey read in a browser for 9 before a bot check, which was
      not bypassed). Lines nothing could read today carry the 2026-10-13 DigiKey count and are flagged.
    - **Scorecard** (`scorecard.buildability`, `--snapshot`, latest `SNAPSHOT-*.csv` by default). For 5 and 500 boards:
      `lines_short_for` (no single source holds the need: consign-only or short), `jlc_assemblable_share` (JLC stock or
      one authorised distributor via Global Sourcing), `consign_lines`, `build_lead_wk` (worst factory lead among short
      lines), `short_lead_unknown`. In the compare, the first three are cost axes (lower better, share higher better).
      s35 card re-scored (differs only in these); s32 restated (`restated_buildability`); 19c has no snapshot join, so the
      compare skips these axes against it. A snapshot is dated: re-take it before comparing across dates.
    - **s32 / s35 (identical):** short for 5 / 500: 3 / 14; JLC-assemblable 0.968 / 0.851; consign 0 / 3 (KLDR025,
      B32676G1905K000, B32654A1104J000); **build lead 29 weeks (L1)**. Five "short" lines are read gaps, not proven
      shortages (DE1E3RA222MA4BP01F, PMEG6030EP, 6SVPC220MV, C0603C102J5GACTU, AC05000001507JAC00).
    - **L1 B82726S2203A020 sets the build date:** no authorised stock anywhere, 29-week factory lead; a 500-board build
      is ~2027-05-06 at the earliest if ordered now. Brokers (35,580) are not an acceptable source for a safety part.
      The same-series 24 A part (B82726S2243A020, 0.63 rating use) halves the CM inductance and drops DM leakage
      18 → 8 µH, so it is an EMI candidate (c29 / D-22 re-run), not a drop-in.
    - **C5 / C6 ripple (closes the S8 question on the vendor basis):** TDK's permissible-current curve is flat within
      −2.3 / +4.3 % over 10–95 kHz, so the repo's ESR basis holds (0.80 at 22 A reproduces; 1.12 / 1.30 at 26 / 28 A
      confirmed). The fitted part carries 28 A only with cap ambient ≤ 80.1 °C; no stocked part fixes 28 A at 85 °C.
      Preferred alternate: **B32676G1106K (10 µF / 750 V, same body)**, 1.25 at 28 A / 85 °C (≤ 80.8 °C for 28 A), DigiKey
      18,789 as "B32676G1106K Z 1" (18 wk); it replaces the fitted part once the "Z 1" suffix is shown to be the
      catalogue part (ESL ~+1 nH per site, ~+2.5 V die VDS; bus 18 → 20 µF). Bench gates above 22 A unchanged: cap
      ambient ≤ 75 °C and a C5 case-temperature measurement. Open: 28 % of the HF ripple power is above TDK's 95 kHz
      chart edge (if ESR rose as √f there, 28 A at 75 °C would read ~1.07).
    - **Resonant bank (S9):** no ≤ 0.85 option is in authorised stock (brokers only); c34 reproduces at 1.045.
    - **Corrections to the 2026-10-13 survey:** D3 / D17 30KPA150CA is stocked from its own maker (Good-Ark, DigiKey
      1,750): $8.17 per board instead of $19.64. R5, PS1, PS2, U26 are not short for 500 (JLC's own stock). Parts cost
      on the snapshot is $186.54 per board at 500 ($250.04 at 5); the scorecard's `parts_usd_*` stay on the 2026-10-13
      survey so the cards remain comparable.
    - **Pre-order plan:** README §4 (owner action; ordering is the owner's). Now: L1 × 520, VOL628A
      (JLC 172 + backorder), bank × 2,600 (part choice), C5 / C6 × 1,040, 2EDR8259X × 1,040, R463N410050N1K, 30KPA150CA
      × 1,040, J2 / J5 7466004R × 1,040, JLC reservations for TPS7A4700 and IRM-20-15, a Coilcraft quote for T1. By
      ~2027-02: the FETs, 1704004, KLDR025 split buy, 3403.0279.23.

46. **Board temperatures against ratings: a release gate and two ratchets; the board does not meet the laminate's MOT
    in still air at 22 A (2026-10-15; gate and records, no board change).** Audit:
    `validation-results/04-board-current-thermal/round5-native21/b3-ratings/audit-2026-10-15/README.md`.
    - **The legacy B3 peaks are mesh artefacts.** The committed thermal.py single-cell peaks (nominal_h10 162.1, c28_h25
      135.0 °C) move 40–50 K between 1, 0.5 and 0.25 mm grids and land on different parts. They stay on the card but
      leave the compare. The ratings are assessed on the committed body-level model (b3-convergence), at 0.25 and 0.5 mm
      with a 3× mesh allowance.
    - **Limits** (each quote re-checked on its page by `audit-2026-10-15/scripts/ratings.py`):
      - laminate KB-6164: UL E123995 (2026-02-20) multilayer MOT **130 °C**, RTI elec 130;
      - RECOM R24C2T25: Tj 150 °C;
      - TPS7A47: TJ 125 °C;
      - CSS2H shunt: element 170 °C, with terminal derating;
      - advisory: TDK MKP Top,max 110 °C (the repo had used 105), B82726 125 °C, 1206 155 °C (unverified).
      Tg is not a use limit: item 21's "21 K to laminate Tg 150" is corrected (the KB-6164 Tg is 140; the limit is
      MOT 130). The run_study.py c28 comment's "≤ 105 °C gate" was never enforced and is reworded.
    - **Basis:**
      - Still air, h 10. Enclosure R33 study 14 models the bay as "a well-mixed wrapper with no through-flow", and D-18
        ducts the blower through the sink only, so nothing supplies the h 25 "fan airflow over the board".
      - Bay air 55 °C (study 14 expected value at a 40 °C kitchen).
      - Cases: the 22 A default ceiling and the 28 A Kconfig ceiling, each at its 1.05× trip.
    - **Verdict (s32 = s35):** gate FAIL; laminate margin −56.4 K, rated parts −38.9 K.
      - At **22 A** the board copper at R5.4 is ~137 °C at 50 °C air, 12 K over the MOT at 55 °C. HF film C40 is at
        ~116 °C against 110.
      - At **28 A**, also R5's element (~197 °C against 170), the gate resistors and bank cap C21.
      - The stall derate (14.7 A) passes everything (+22 K).
      - Still-air ceiling meeting every gated limit: **20 A at 50 °C bay, 18 A at 55–61 °C**.
      - The U42 162 °C / PS2 / PS1 / L1 "hot list" was artefact: each part is inside its own limit on the body model.
    - **Known model biases**, worked by an analysis study before the layout fix is sized:
      - the FET drain-lead path to the sink is not modelled (stage 15b bounds it at about −26 K on the FET row, less at
        R5.4);
      - the c28 heat file is stale: U41/U42 at 40 kHz loss against the 60 kHz window; gate networks still UCC21550 /
        3.9 Ω against the fitted 2EDR8259X / 8.2 Ω.
      The body model now maps the 2EDR8259X to the DWK package class (ASSUMED, `thermal_body.spec_for`).
    - **Scorecard:**
      - `b3_ratings` is a **release gate**: shown on the card but outside the candidate-vs-benchmark rule while the
        benchmark itself fails it (`RELEASE_GATES`), as with leakage (S1).
      - `b3_laminate_margin_K` and `b3_rated_part_margin_K` are ratchets (higher is better, 1 K tolerance).
      - `margins.json` counts only for the board it was solved on (board_sha256 check). Each lane runs
        `b3-ratings/run_basis.py` (~6 min) after its chain.
      - s35 re-scored; s32 restated (`restated_b3_ratings`). Against s32, s35 is still ACCEPT.
    - **Release condition:** the board is not released for a still-air continuous ceiling above 18 A until the gate
      passes. Fixes, by leverage:
      1. board-face airflow (`b3-ratings/ENCLOSURE-REQUEST.md`; h 15 gives −18 K at 22 A);
      2. less tank-copper heat at R5.4 / the FET row (layout candidate 36: ×0.7 gives −16 K at 22 A, ×0.5 gives −26 K);
      3. a 0.5 mΩ shunt (R5's element −13 K at 22 A; changes the OCP / Kelvin budget);
      4. the commissioned still-air ceiling (firmware; the controller session's call, requested through the owner).
      A higher-Tg laminate gives 0 K (KB-6165 / KB-6167F have the same 130 °C MOT).
    - **Side finding (certifier packet A3):** KB-616(X)'s UL multilayer recognition lists max inner copper 35 µm, while
      the stack has 2 oz (61 µm) inner layers. KB-6164F / KB-6165F list 102 µm. Whether JLC's own recognition covers
      this stack is being checked (public sources only).
    - **Process note:** the task-04 `-heat.npz` outputs are gitignored. After candidate 35's cherry-pick, this worktree
      held s32 npz files beside s35 JSONs. `thermal.remap_a4`'s energy check refused them, and the s35 files were copied
      from the lane's worktree after a byte-identical JSON match and a per-case energy check.

47. **Touch leakage × conducted EMI: the S1 change set (2026-10-15; study and decision, no board change yet).** Study:
    `validation-results/07-conducted-emi/leakage/co-design-2026-10-15/` (`WRITEUP.md`; `run_all.py --reuse` re-runs
    all 23 controls, which pass from the committed copy; a clean full regeneration matched within 0.0 dB).
    - **Why candidate 23 alone cannot pass:** the IRM supplies at their datasheet maxima are 0.429 mA as built and
      0.286 mA without PS1, already over the 0.25 mA portable 50 % rule before any Y capacitance. The leakage limit
      needs lower-leakage supplies, not only fewer of them.
    - **Change set adopted (DESIGN touch 0.2412 mA, passing portable 50 % by 8.8 µA; s19b compliance minimum
      8.19 dB, 9.86 dB on temper-8d's corrected coil model):**
      1. delete PS1 (candidate 23; logic from PS3 over J13);
      2. PS2 IRM-20-24 → MEAN WELL **MPM-20-24**: same Case 219A, touch current < 80 µA at 264 VAC (MPM-20-SPEC
         2024-10-30 p.2); JLC C6675337, 5,047 in stock;
      3. PS3 (controller side, J13) IRM-60-15ST → **MPM-65-15ST**: same case, < 100 µA (MPM-65-SPEC p.2); JLC 0;
         a controller-session request;
      4. D-22 inlet module: remove its four Y caps (board C3 / C4 stay 2.2 nF / line);
      5. D-22 module choke TDK 1.6 mH → KEMET **SCF31X-220-2R1A011JH** (5.68 mH, 22 A, 500 VAC, 4.39 mΩ); with the Y at
         C3 / C4 the module CM choke must be ≥ 3.6 mH.
      About +$2.95 per system (MPM and choke prices estimated), 5 fewer parts.
    - **Robust variant, preferred if L1's footprint and stock allow:** L1 B82726S2203A020 → the same SCF31X
      (+$1.79, L1 re-layout). EMI minimum 11.51 dB, and the HF touch current (35–60 kHz, `hf_touch.py`) stays
      ≤ 0.244 mA at every corner. The recommended set reads 0.299 mA at the chokes −30 % corner through an unverified
      UL-style meter network. It also removes L1, the line that sets the build date (DECISIONS 45), if SCF31X is in
      authorised stock. SCF31X and MPM-65-15ST stock could not be read today (JLC lists neither in stock; Octopart
      returns 403 to scripted reads, not bypassed). The candidate-23 lane checks both before choosing.
    - **Rejected:**
      - a lower Y with the module Y removed alone: −9.5 dB, a CM resonance on 180 kHz at chokes −30 %;
      - X-cap changes: 0 dB, the binding lines are CM;
      - c29's SCF39XV-200-Z2R1A012JH: a 6-pin asymmetric-winding part, fit for an L / N filter unconfirmed, 37–68 weeks.
    - **Risks carried:**
      - the 8.8 µA margin flips if the supplies' maxima are 8 % higher or the basis changes. Measured supply leakage
        (one IRM-20-15 unit ~14× under its maximum) would open the space;
      - SCF31X DM leakage is unpublished (1 % assumed; at 0.3 % the minimum is 6.87 dB): measure a sample;
      - the 41 µH DM inductors still have no MPN.
    - **Certifier (packet A4):**
      - limit class;
      - datasheet-max summation and the 50 % budget;
      - the MPM approvals (IEC / ES / CSA 60601-1, where IRM-60 carries UL 62368-1);
      - which meter network applies at 35–60 kHz.
    - **temper-8d's split-R coil EMI model:** the physics is right (s19b hangs the coil-end capacitance on a node
      ~140 V from the real terminal). It changes no verdict: the scorecard nominal stays 10.48 dB, and the committed
      design's compliance minimum stays 6.50 dB (bound by X −20 % at 70 kHz). Adopting it in s19b is a model update for
      the next EMI round.

48. **Track-geometry cleanup pass (stage 37, candidate 37; DECISIONS 43's planned fix); tool adopted and proved on s35, to run last
    after the island lanes merge (2026-10-15; board `1900b038f54a9b0b1effac574c0cb4aa733dc6a2a186ef6371fe360840ff7ae5`,
    copper.json `f24e4bf8…`, schematic and frozen netlist unchanged from s35, Gerber ZIP `f6756eba…`; tag `native21s37`;
    `11-candidates/c37-geometry-cleanup/`; layout only).**
    - **What:** `native-21/layout/track_cleanup21.py` is a post-route transform of a finished copper.json. Its obstacle
      model is the export of the board built from that copper (pad shapes, fills, outline), and it refuses any other
      export. In order, each step repeated to a fixpoint:
      - fold-backs: a free tip is removed; a tip on a pad or via is de-duplicated;
      - acute corners: opened by an octilinear tangent mitre, or at pad / via tips by a square T;
      - right angles: mitred to 2 × 135°, with a leg of 3 × the width and at least 0.5 mm, down to the width;
      - any-angle segments: replaced by octilinear doglegs.
    - **Edit checks:** an edit is kept only if:
      - its added copper clears every other-net item and fill under rules21 + 0.02 mm;
      - it is no closer than before to the other side of the barrier or the RES_A 12.6 mm pair;
      - no fill can grow near the barrier or into the SELV-spine region;
      - the net's KiCad-rule connectivity partition is unchanged;
      - the geometry counts improve in severity order.
      res_a and the OCP sense nets are never edited. Pads, vias, zones, widths and parts never move. There are 45
      controls in `test_track_cleanup21.py`.
    - **On s35:** 625 edits.
      - Right angles 104 → 50, acute 206 → 23, fold-backs 44 → 3, any-angle 704.4 → 308.4 mm.
      - Track length −101.9 mm.
      - Chain CHAIN_DONE:
        - DRC 0 / 0 with the s35 warning set;
        - barrier 0; RES_A outer F 20.393 / B 13.375; D5 8.047 / 8.507 (all unchanged);
        - DFM 750 vias; SPINE_LOCK PASS; FIT clean;
        - Kelvin 67.77–116.44 A; necks 0.993; OCP pickup 4.17 A;
        - task 04 within 0.011 %;
        - B3 ratings margins −56.3 / −38.8 K (s35 −56.4 / −38.9).
      - Scorecard ACCEPT against s35 (better on the four geometry metrics and both B3 margins, nothing worse) and
        against s32. Against 19c it is ACCEPT; s35 was REJECT there, on item 43's ratchets only.
      - A second run on the s37 export makes 0 edits.
    - **Left, with reasons** (README section 6):
      - right angles: 21 are square exits from pads or vias whose inner corner lies inside the pad or via copper; 19 have
        arms too short for a real mitre; 8 are on the locked OCP sense nets or their pour; 1 is in the spine region;
      - acute corners: 7 are in the spine region and 4 on the locked nets;
      - any-angle: 117.5 mm is blocked by clearance, 47.8 mm by the barrier rule, and 64.8 mm is near-octilinear escapes
        too short for a dogleg.
    - **Side effects:**
      - The chain's board-only planner re-placed TP3, TP4, TP7 and TP30 by 0.5–1.0 mm along their own re-shaped tracks.
      - Chain fix: a B3 ratings FAIL verdict no longer ends the thermal block (`run_basis.py` exits 1 on a FAIL, under
        `set -e`). Every board fails that release gate today, so no lane's chain could reach CHAIN_DONE.
    - **Process:** the pass touches every island. It runs once, after the other lanes merge, on the merged copper and
      its export, followed by the chain. It is idempotent, so it is safe to re-run on any later board.
    - **Reverses if:** a fabricator review flags the square T junctions or the mitres, or a later lane needs the
      pre-cleanup geometry of a net. The pass can be re-run from that lane's copper.
    - **Merged (integration):** the tool, its tests, the chain fix (cherry-picked first, so lanes on 0aecdc56f could
      finish), the c37 records and the s37 card. **Not merged:** the s37 board commit (`5e81ba1c6` on
      `claude/native21-geometry-cleanup`). s35 stays the board of record until the other lanes land; then the pass runs
      on the merged copper.


49. **Bridge MOSFETs and HS bias supply: device study; a reverse-diode dv/dt violation found (2026-10-15; ledger and
    records, no board change).** Study: `validation-results/01-switching-parasitics/device-study-2026-10-15/README.md`.
    The vendor SPICE models and datasheets stay outside the repo (`dl/`, URLs and sha256 in the README).
    - **Controls reproduce:**
      - 128 / 128 committed c33 s32 ZVS rows (≤ 0.7 mV die VDS, 0 ns);
      - the 672-run as-built S1 sweep, exactly;
      - the R33 and round-6 FET thermal rows (0.0 °C);
      - the bias-sizing currents;
      - the CFD7 DigiKey price.
    - **New violation (S14):**
      - IPW65R018CFD7 Rev 2.0 (2021-04-19) Table 2 p.3 rates the **reverse-diode dv/dt at 70 V/ns** (VDS 0–400 V,
        ISD ≤ 58 A, Tj 25 °C, identical HS / LS with identical RG), and diF/dt at 1,300 A/µs (both read on the page by
        the integration session).
      - The modelled S4 hard-commutation case (IL −20 A: the incoming switch hard-commutates its partner's body diode)
        runs **85.8 V/ns** (ESL 10 nH; 81.9 at 1.06 nH) on the as-built deck, over the rating outright and 1.5× the
        80 % rule (56 V/ns).
      - The ledger had compared S4's edge only with the 120 V/ns MOSFET dv/dt. It now carries the diode rating and
        check, and IPW65R018CFD7 is VIOLATION. ledger_violations goes 0 → 1, restated on the s32 / s35 / s37 cards (same
        FETs and gate network), so it is a ratchet that a fix must lower. The ledger test names the known violations.
      - S4 was already an open risk for die VDS and off-gate (D-24); its bench measurement (D-8 double pulse) now also
        measures the commutation dv/dt.
      - **Fix: candidate 39, the gate network.** The commutating dv/dt is set by the incoming switch's turn-on, and in
        ZVS operation turn-on is lossless, so a slower turn-on (split R_on / R_off with a diode per gate; the 2EDR8259X
        has one output per channel) should cost little. Raising R_ext on CM8 to 15 Ω gives 62–67 V/ns in the proxy,
        still over 56.
    - **CM8 (IPW65R018CM8):**
      - $6.77 per board cheaper and a package drop-in (U06 inside the CFD7 tolerances); ZVS improves (worst t_trans
        145 vs 190 ns).
      - Its internal gate resistance is 1 Ω against 2.7 Ω, so a straight swap fails S4 (528 V die, 108 V/ns). With
        R_ext 12 Ω it matches the as-built case (440 V, 85 V/ns), but that rests on a proxy (the 029 CFD7 model, since
        no CM8 vendor model was obtainable).
      - DigiKey holds 482 against 2,000 needed for 500 boards, at a 24-week lead (CFD7 8 weeks); it has the same
        70 V/ns diode rating.
      - **Not adopted now.** Candidate 39 evaluates CFD7 and CM8 together with the turn-on fix, and takes CM8 if a vendor
        model and the stock clear.
      - Rejected:
        - 029CFD7 (2 K from 125 °C at trip on the deck basis);
        - 041CFD7;
        - IPZA65R025CM8 (4-pin re-spin, 52 weeks);
        - SiHG026N65E (10 V/ns diode);
        - SiHG041N65SF.
      - RDS(on),max at 25 °C ≤ 31.7 mΩ keeps Tj ≤ 125 °C at trip on S8.
    - **HS bias: keep the RECOM R24C2T25 (U41 / U42).**
      - The real output is 0.715 W at 50 kHz (36 % of the 2 W knee); module heat is 0.63–0.87 W.
      - A discrete UCC25800-Q1 / Würth 750319833 supply saves only $2.8–3.9 and is rejected:
        - UCC25800 has zero stock;
        - its transformer has 231 in stock, and its winding capacitance is typical only, against the ≤ 4 pF max
          ALT-BIAS needs;
        - its basic insulation runs at 65 % against the 50 % rule;
        - it needs a re-layout.
      - The 2EP1xxR is out (4.5–20 V supply, 24 V source); bootstrap stays rejected (DECISIONS:91).
      - Buy RECOM on T&R at the 750 break ($7.18): −$0.38 per board (pre-order plan).
    - **Ledger correction:** the RECOM "Pout" check compared the module's 1.71 W dissipation with the 2 W output knee. The
      output at the 80 kHz / 740 nC allocation is 1.396 W (69.8 %).
    - **Passed to the thermal refinement study:**
      - B3's 1.09 W per module is conservative (0.53–0.73 W at 33 kHz on the deck charge);
      - the K1 sink of item 15 (123.8 / 128.7 °C) was not reproduced.

50. **Stage 38 (candidate 23): the DECISIONS 47 supply change set built on s35; L1 kept (2026-10-15; adopted). Board of record: s38 (b5bf428d).** Records:
    `validation-results/11-candidates/c23-supply-topology/README.md`. Board native21s38 `b5bf428d`, chain CHAIN_DONE
    (`SPINE_OWNER=selv`). Scorecard ACCEPT against s35:
    - cheaper: parts $206.44 → $202.24 at 500, BOM lines 94 → 93, placements 349 → 348;
    - better: EMI 10.5 → 12.4 dB, touch current 0.974 → 0.241 mA;
    - nothing worse. The B3 ratings margins are unchanged (−56.4 / −38.9 K); the release gate stays open.

    **Built:**
    1. **PS1 deleted.** V15_SELV is gone, and J4.1 is not connected (single-pin SELV net `j4_nc1`). The controller
       must merge J13 into its logic rail and drop the J4.1 input before it powers a stage-38 board
       (`CONTROLLER-REQUEST.md` addendum 2).
    2. **PS2 → MEAN WELL MPM-20-24** on the unchanged IRM-20 footprint. Case 219A is identical: MPM-20-SPEC
       2024-10-30 p.4 = IRM-20-SPEC p.3.
       - Ledger: 44 % of 21.6 W; 90 % of the p.3 derating holds to 70.3 °C local air; 53 % of 264 VAC.
       - Approvals: IEC 60601-1 (2 × MOPP) and IEC 60335-1, no UL file, so it is a certifier item.
       - Sourcing: JLC C6675337 holds 5,047; the card uses the DigiKey basis, $12.60 at 500.

    **Not built:**
    3. **L1 stays TDK B82726S2203A020; the SCF31X is not taken.** Its 45 × 42 mm body does not fit the 47.96 × 32.81 mm
       slot without moving C1 / C5 / F1. That is compaction, which the lane brief ruled out (no moves outside the SELV / PS1 / L1 areas). Rating (68 %) and
       height (33 mm) are fine. DigiKey holds only 68. The robust variant (11.51 dB) waits for a re-layout, and L1
       still sets the 29-week build date.

    **Off-board, counted in the verdicts:**
    4. The D-22 module Y is removed and its choke becomes the SCF31X 5.68 mH (`MODULE-REQUEST.md`). PS3 is the
       MPM-65-15ST. Both are counted in the leakage and EMI results: touch 0.2412 mA (budget 0.25, margin 8.8 µA);
       s19b nominal 12.37 dB and minimum 8.19 dB.
       - Leakage rises to 0.653 mA with the module Y kept, and to 0.324 mA with an IRM-60 in PS3.
       - The scripts that write the scorecard inputs now model the s38 system: `leakage_budget.py`, and
         `emi_s19b.py` `MODULE_S38` with sensitivities relative to the nominal parts. Their s35 rows reproduce the
         committed 0.9741 mA / 10.48 dB.

    **Layout:**
    5. **The freed PS1 area stays clear.**
       - L_FILT: re-laid to F2 at 40.5 mm (was 60.5 mm), which removes one acute corner.
       - N_FILT: its J11 via becomes 0.85 / 0.3 at (256.8, 116.6). The old 0.6 ring had sat inside PS1.2, and on
         its own it failed task 04's topology preflight.
    6. **SELV spine lock re-issued by the selv lane.** The new baseline is `spine-baseline-native21s38-all-copper`.
       The only differences are J4.1's net and the v15_selv antipads filled in selv_gnd / v3v3.

    **Process:** the co-design study's manifest is now pinned to its base 0aecdc56f.

    **Reverses if:**
    - a controller cannot take the J13 merge (PS1 returns);
    - the module Y must stay (the leakage limit fails);
    - the certifier rejects the MPM approval basis.
    - **Integration re-score** (`10-benchmark/scorecard-native21s38.json`): it differs from the lane's card only in
      `ledger_violations` 0 → 1 (DECISIONS 49, merged after the lane branched). Still ACCEPT against s35 (restated to 1).
      `jlc_assemblable_share_500` reads 0.851 → 0.849 only because the deleted PS1 was itself a JLC-stocked line
      (79 / 93 against 80 / 94).
    - **Interface:** a stage-38 power board needs the controller's J13 merge before it is powered from an un-updated
      controller, where J4.1 is an open pin, so the failure is benign. Owner relay with addendum 2.

51. **B3 ratings model corrected: FET lead path, 60 kHz heat on the deck gate charge, film caps and gate resistors
    gated (2026-10-15; model and gate, no board change).** Study:
    `validation-results/04-board-current-thermal/round5-native21/b3-ratings/refine-2026-10-15/`. The integration session
    applied its patches and reproduced its end-to-end result on s38.
    - **Corrections (each with a control):**
      - **FET drain-lead path to the sink** (`thermal_body.py`, `body_runs.py`, `fet_case.py`):
        - lead conductance 0.0845 W/K central (0.020–0.280) from the IPW65R018CFD7 p.12 drawing;
        - sink on the S8 baseline (R_SA 0.29, 13 CFM, 50 °C inlet) and the firmware fan law: 88.6 °C, case
          94.6 / 98.0 °C;
        - G = 0 reproduces the old model exactly. 1.2 / 2.4 W leaves through the leads.
      - **c28 heat file at the 60 kHz window top, on the as-built deck gate charge** (382.6 nC worst edge, DECISIONS 49)
        (`make_heat_sources.py`):
        - U41 / U42 0.953 W each (checked against the RECOM Rev. 1-2024 p.2 curves);
        - U26 0.852, PS2 1.262 W;
        - driver and gate-network rows on the 2EDR8259X / 8.2 Ω / PMEG + 1 Ω topology.
        The 740 nC allocation stays the bias-sizing allowance. It is not a physical charge: on it the ceiling would be
        10.4 A. The bench gate-charge measurement confirms the deck value.
      - **Gated rows added** (`b3_ratings_gate.py`):
        - film caps C38–C41 at Top,max 110 °C (TDK B3265* June 2026 p.2 / p.35; body including self-heating);
        - gate resistors: element 155 °C, and the terminal-derating line 155 − 85·P / (0.8 · 0.25 W) (FH RS-06L p.2;
          1206 1/4 W at 70 °C → 0 at 155 °C).
        The bank caps stay advisory.
    - **s38 on the corrected model (bay 55 °C):**

      | | c22 | c28 |
      |---|---|---|
      | Laminate MOT 130 °C, 1 mm block | −2.5 K | −38.0 K |
      | Laminate, FET row | −1.6 K | −27.9 K |

      - **Rated parts −63.9 K: the 1206 gate resistor R12 fails its derating line** (−39.7 K at c22), and fails at every
        ceiling and basis. At ~21 A only a 2010 (+3.6 K) or a 2512 (+8.5 K) passes; at c28 none does (the terminal sits at
        159 °C from board heat).
      - C40 −3.1 K at c22. U42 Tj +24.5 K.
      - Card re-scored: `b3_laminate_margin_K` −56.4 → −38.0, `b3_rated_part_margin_K` −38.9 → −63.9 (more rows gated).
        This is a basis change, not a board change: earlier cards keep their old-basis values.
    - **Still-air ceiling on the laminate:** 21.5 A at bay 55 °C, 20.4 A at 61 °C. With the film-cap and gate-R element
      rows: 21.0 / 19.5 A. The gate-R derating row has no ceiling with 1206 parts.
      The release condition stays as item 46 (still-air ceiling ≤ 18 A requested) until candidates 36 and 39 land.
    - **Targets** (tank-copper Joule factor f near R5.4 / the FET row, for the laminate and film rows):

      | | f needed | with a 0.5 mΩ shunt |
      |---|---|---|
      | c22 | 0.895 | 0.975 |
      | c28 | 0.369 | 0.551 |

      The gate-resistor derating needs a package change (candidate 39: 2512, or moved out of the block). No copper
      factor fixes it.
    - **Laminate UL scope (S12): open on public sources.**
      - UL Product iQ needs a login, so the reading stopped there. JLC's public UL page lists E479892 JLC-4 (KB-6164,
        KB-6165, S1141, S1000H, S1000-2M) without copper limits.
      - Kingboard's QMTS2 rows give max internal copper 35 µm (KB-6164) and 54 µm (KB-6165), against our 61 µm. The
        KB-6164F / 6165F / 6167F rows allow 102 µm. JLC's "TG155" option links the KB-6165F datasheet.
      - So the KB-6164 named on the order (item 41, for CTI) may be outside its UL multilayer scope with 2 oz inner
        copper.
      - `native-21/stackup.json` still names Nan Ya NP-155F. It is corrected once the order laminate is settled.
      - This is an owner question to JLC: which recognised construction covers 4 L, 2 oz inner, CTI ≥ 175 V.
    - **Process:**
      - The c28 heat file is in the shared model key, so the next chain of every lane recomputes task 04 and B3 once.
      - The committed legacy `b3/outputs` (reference only) are from the old heat file until then.
      - s38's task-04 `-heat.npz` fields were copied from ps-selv after a JSON match and a 41 / 41 energy check (the
        second occurrence; a sync tool follows).

52. **Stage 40 (candidate 30): U44 becomes the ISO6721FB HS-B -> LS link (30a) and C161 reaches the n_ls plane (30b),
    built on s38 (2026-10-15; adopted). Board of record: s40 (33ed17f3).** Records: `validation-results/11-candidates/c30-ls-pocket/README.md`. Board native21s40
    `33ed17f3`, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS against the s38 baseline). Scorecard ACCEPT
    against s38:
    - cheaper: parts $202.24 -> $202.21 at 500, BOM lines 93 -> 92, JLC extended lines 67 -> 66;
    - better: return-path open changes 18 -> 15, acute corners 205 -> 199, right angles 103 -> 101, fold-backs 44 -> 43;
    - within tolerance: B3 laminate -38.0 -> -38.3 K, rated part -63.9 -> -64.1 K. `b3_ratings` fails on both boards
      (DECISIONS 51), so the release gate stays where 51 left it. Placements 348 -> 351, vias 747 -> 754.
    - unchanged: D5 8.047 / 8.507 mm, RES_A 13.375 mm, Kelvin band 67.77-116.44, OCP pickup 4.17 A, fuse ratio 0.993,
      EMI 12.4 dB, touch 0.241 mA, enclosure fit, task 04 39 / 0. Ledger violations stay at 1 (IPW65R018CFD7).

    **Built:**
    1. **30a: heartbeat M1b as drawn (FMEA §6a, recorded as §6c).** `HighBiasSelv` and its CA-IS3720LW go. U44 is an
       ISO6721FBDR `HighBiasLink` like U43 (C159 / C160 its caps), carrying HS-B's verdict (MON_GOOD_HB) to the LS
       domain. D20 (BAT54S, MID -> K2 half) ANDs it into the LS good node beside D18. R135 (10 k) holds U46's HSB_GOOD
       input at v3v3, so U46 is the buffer only. One reinforced HOT -> SELV crossing fewer.
    2. **C168, 100 nF v3v3 / selv_gnd, transfer cap for pwm_hb's via at (34.4, 110.6).** The removed isolator's SELV
       decoupler served it at 2.0 mm; without a replacement the change measured 16.5 mm and failed the asserted
       `return_path19` limit.
    3. **30b: C161's own via (0.42 mm) lands in the In1 n_ls LS-block plane.** `bypass_check.py` counts only vias that
       land in a filled pour of the net on a non-F layer; U45's 6.0 mm exception is retired (3.0 mm, as every other row).
       Under the new rule s38 fails U45 at 5.97 mm.

    **Layout:**
    4. **U44 at (3.25, 47.25, 270) in U42's pocket**, the only legal straddling pose (`spot_scan.py`). U42 (RECOM
       R24C2T25) keeps its part and pose.
    5. **The vote moves beside U43.** No legal via exists at x 56-125, y 44-51, and the LS In1 corridor is full, so
       MON_GOOD_HB could not reach the LS block. D18 and D20 sit beside U43; the GOOD node takes MON_GOOD_HA's old
       corridor lane. One corridor trace now carries both HS vetoes (FMEA §6c; neutral under 19.11.2's component
       faults).
    6. **Return paths.** MON_GOOD_HA's four open changes close (F n_ls pour over an In1 n_ls patch, U41 heat-spread
       pours extended to x 46.35, which keeps 8 mm to SELV). The GOOD node is now counted and keeps one open change at
       U45.1 (104.4, 99.65), the only legal via spot in an In1 island.

    **Gates:** `return_path19.py` reports MON_GOOD_HB and the GOOD node; `bypass_check.py` plane-landing rule and ISO6721
    U44 rows; ledger: CA-IS3720LW removed, U44 on the ISO6721FBDR row, D20 / R135 / C168 on existing rows.

    **Not done:** the other 14 return-path opens (SELV / Kelvin nets outside HS-B / LS). The QUEUE's -$1.93 is not
    reached: the card shows -$0.03 at 500.

    **Reverses if:**
    - the certifier wants HS-B's verdict on its own SELV crossing (the stage 30 §6b arrangement) rather than voted in the
      LS domain;
    - a corridor fault that silences both HS vetoes at once is judged credible beyond 19.11.2's component faults (then
      the vote returns to the LS block and MON_GOOD_HB needs an In2 route, which the s38 copper does not have);
    - the B3 tolerance on the FET row (0.2-0.4 K worse here) becomes binding once candidate 36 lands.

    **Integration review (adopted with one condition):**
    - **The GOOD-node open.** The LS good node is pulled up (rpull 10 k to the LS 5 V), and each HS link vetoes by pulling
      it low through its BAT54S half. So an open in the corridor trace between the vote (beside U43) and U45 reads "good"
      and masks both HS bias verdicts. That is a latent, undetected fault, not an announced trip.
      - The same latent mode existed before for HS-A's trace alone. The move doubles its scope, not its kind.
      - It is outside 19.11.2's component-terminal faults, and no legal re-route exists on s38 copper.
    - **Condition: an end-of-line functional test of each veto.** On every board, force MON_GOOD_HA low, then MON_GOOD_HB
      low (HS bias off, or the link input pulled down), and check that the heartbeat stops and BIAS_GOOD drops within its
      hold time. This detects a corridor open before the board ships and turns the latent mode into a production
      screen. Recorded for the bring-up / test plan (OPEN-ITEMS B8) and for the certifier with FMEA §6c.
    - **Re-score on integration:** identical to the lane's card. ACCEPT against s38.
    - **Process:** the stale task-04 fields after this cherry-pick (22 / 41 failing the energy check) were caught and
      synced by `a4_fields.py` (910ce7143). This is its first use.

53. **Stage 41 (candidate 36): tank / FET-row copper at R5, built on s40 (2026-10-15; adopted; board of record s41, d4b2445c). c22 laminate passes;
    C40 and c28 stay open on 2 oz outer copper; the 0.5 mΩ shunt is not adopted.** Records:
    `validation-results/11-candidates/c36-tank-copper/README.md`. Board native21s41 `d4b2445c`, chain CHAIN_DONE with no
    spine owner (SPINE_LOCK PASS). Scorecard ACCEPT against s40 (better `b3_laminate_margin_K` −38.3 → −25.2 K; nothing
    worse; parts, BOM, cost, vias identical).
    - **Built** (`patches21.edit_base41`, outlines `native-21/layout/stage41_pours.json` from `scripts/pours41.py`):
      1. F.Cu hv_ret spreader at R5.4: 86 mm², x 34.3–43, y 13.3–25.5, stopping 1.5 mm short of C40.2.
      2. F.Cu leg_ret from R5.1 east to Q3.1.
      3. New B.Cu leg_ret pour over R5.1's via field and Q6.3.
      4. The In1 leg-A neck under Q3.2 widened to y 14.7.
      5. Two of R5.4's six hv_ret vias moved north-west, so the sw_b B.Cu lane rises over R5. Its 4.4 mm pinch between
         R5.4 and C40.2 goes away.

      Nothing changes in the LS pocket, the HS-B band, the gate networks or the SELV side.
    - **B3 ratings rows, s40 → s41 (bay 55 °C):**

      | | c22 | c28 |
      |---|---|---|
      | Laminate, 1 mm block | −2.6 → **+1.2 K** | −38.3 → −25.1 K |
      | Laminate, FET row | −1.7 → **+1.1 K** | −28.2 → −25.2 K |
      | C40 | −3.2 → −2.7 K | −25.4 → −24.6 K |
      | C38 | −0.2 → +0.1 K | −22.5 → −22.2 K |
      | R5 terminal | +23.6 → +31.0 K | −20.8 → −9.1 K |

      Gate resistors (candidate 39): R12 derating −39.7 → −39.6 K at c22, −64.1 K at c28, unchanged; R12 element
      +15.7 → +18.3 K at c22.
    - **Still-air ceiling** (bay 55 °C; I_trip² interpolation between c22 and c28, which reproduces item 51's 21.5 /
      21.0 A on s38 and s40):
      - laminate 21.5 → **22.3 A**;
      - laminate + film 21.0 → **21.1 A** (C40 limits);
      - the gate-R derating row has no ceiling with 1206 parts.
      Bay 61 °C is not recomputed.
    - **Other metrics:**
      - Task 04: leg_a −15 % (1.72 → 1.46 mΩ); sw_b −1.2 %; hv_mixed +3.9 / +5.8 %, the cost of the via move, already
        in the rows above. bus_p span 2.835 %.
      - Fuse rows: hv_ret neck 3.10 → 2.89 mm, I²t 2492 → 2159 A²s against 1710; min ratio 0.993, unchanged.
      - Unchanged: Kelvin band 67.77–116.44 A, OCP pickup 4.17 A, D5 8.047 / 8.507 mm, RES_A 13.375 mm, return-path
        opens 15.
    - **Targets of item 51 not met:**
      - c22 C40 (−2.7 K);
      - every c28 laminate and film row (−25 K).

      Variants (pours only, extra vias) and what-ifs on the s40 base show that no 2 oz outer layout reaches them:
      - 3 oz outer copper would give c22 C40 +4.0 K and c28 laminate −9.6 K, but JLC offers 1 / 2 oz outer copper on
        multilayer boards only (capabilities page and copper-weight article, fetched 2026-10-15).
      - C40's rise is mostly the sw_b lane (11.9 K) and its own heat (3.85 K).
    - **0.5 mΩ shunt (CSS2H-2512R-L500F, same datasheet and footprint): not adopted.** It gives +0.9 K (c22 laminate),
      +2.3 K (C40) and +6.4 K (c28 laminate). But:
      - OCP pickup goes 4.17 → 8.35 A, over the 6.5 A gate;
      - with the same-trip divider the band low corner falls to 37.2 A, under the 64.17 A floor;
      - the floor-holding divider gives a 77–167 A band;
      - comparator Vos ±4 mV becomes ±16 A.

      It needs an OCP front-end rework. The controller-side constants for that case are in `CONTROLLER-REQUEST.md`.
      Today no controller constant reads R5.
    - **Release condition:** unchanged from items 46 / 51. The B3 gate still fails on R12 (candidate 39), on C40 at c22
      and on c28. The commissioned still-air ceiling request (≤ 18 A, or the measured ceiling once candidates 36 and 39
      land) stays with the owner. On this board, film and laminate alone would allow about 21 A at bay 55 °C.
    - **Reverses if:**
      - a 3 oz outer (or 6-layer with heavier outer) build is bought: re-run `scripts/basis_variant.py` with that
        stack-up;
      - the OCP front end is reworked for 0.5 mΩ;
      - the bench or FEM shows the hv_ret via move costs more than the body model's +4–6 % hv_mixed loss.

    **Integration review:**
    - Re-scored on integration: card identical to the lane's. ACCEPT against s40 (better `b3_laminate_margin_K`
      −38.3 → −25.2; nothing worse).
    - **Fusing headroom:** the hv_ret neck (R5.4 → BR1−) narrows 3.10 → 2.89 mm, I²t 2,492 → 2,159 A²s. That is 1.46 →
      1.26× F1's 1,710 A²s clearing I²t, still above the board's minimum (0.993 overall, 1.021 for conductor necks), so
      `fuse_copper_fusing_ratio` is unchanged. Recorded so a later lane does not spend the rest.
    - **What layout cannot do on 2 oz copper:** C40 at 22 A (−2.7 K) and every 28 A row. 3 oz outer copper would reach
      the 22 A rows (C40 +4.0 K), but JLC does not offer it on multilayer boards. So 28 A in still air is not
      supportable on this stack: it needs board-face airflow (`b3-ratings/ENCLOSURE-REQUEST.md`) or another fab.
    - **Still-air ceiling at bay 55 °C:** laminate 22.3 A, laminate + film 21.1 A (C40). The gate-resistor derating has
      no ceiling until candidate 39's package change. The controller request stays at ≤ 18 A until 39 lands; bay 61 °C
      needs a re-run of the targets on the s41 basis.
    - **The 0.5 mΩ shunt is not adopted:** at the same trip divider the OCP band's low corner falls under its floor, and
      at the floor-holding divider pickup is 8.35 A against the 6.5 A gate. It would need an OCP front-end rework.
      `c36-tank-copper/CONTROLLER-REQUEST.md` is conditional (no controller constant reads R5 today).

54. **Gate network for the S4 diode limits: R_on 68 Ω 2512 + Cgs 4.7 nF on the CFD7, built as candidate 39; CM8 + 39 Ω
    becomes a value-only swap (2026-10-15; study and decision).** Study:
    `validation-results/01-switching-parasitics/gate-network-2026-10-15/README.md`.
    - **Controls:**
      - 317 of 320 device-study rows reproduce within 1 mV (worst 0.2 V); energy rows match exactly;
      - split-vs-symmetric, open-branch, the CM8 proxy and the recovery-charge fixture against D-24 also pass.
    - **As built (8.2 Ω turn-on, PMEG + 1 Ω turn-off):** both diode limits are broken in S4.
      - dv/dt 85.8 V/ns against 70.
      - **diF/dt 2,101 A/µs against the 1,300 A/µs maximum diode commutation speed** (Table 2 p.3; now a second ledger
        check on IPW65R018CFD7).
      - **Mechanism:** the S4 edge is the body diode's recovery snap, so it scales with Qrr.
      - **The vendor model understates Qrr:** 1.74 µC against 2.30 µC typical and 4.60 µC maximum. At typical charge the
        as-built S4 runs 109–112 V/ns with die VDS 620 V, against the 520 V screen.
    - **S4 is a design case.** It is not steady state: firmware is meant to prevent capacitive operation, but it has never
      run. It arrives in bursts:
      - a non-magnetic pan at the 35 kHz floor;
      - a restart within ~250 ms;
      - a zero-cross calibration error;
      - a load transient.
      Each burst lasts until the 5° software latch acts: up to ~10.6 ms, 370–740 edges per leg. No hardware phase
      detector exists, so the per-edge rating applies. A hardware capacitive-mode detector goes to the controller
      session as a request.
    - **Decision:** R10 / R12 / R18 / R20 → **68 Ω 2512** (Uniroyal 25121WF680JT4E, JLC C50371, 3,131 in stock), and the
      gate Cgs → **4.7 nF C0G 0603** (Murata GRM1885C1H472JA01D, C85980). The PMEG6030EP + 1 Ω turn-off path is kept.
      - Full grid at typical charge: S4 49.7 / 49.2 V/ns, diF/dt 244 A/µs, 640 / 640 rows pass the c25 screens.
      - Turn-off is unchanged: E_off 8.7–9.0 µJ, S1 t_trans 190 ns, ZVS 80 / 80, worst off-gate +0.50 V.
      - Cost: turn-on is slower (4.8 V at 1 µs; upper bound +5.2 µJ conduction per edge), +61 nC per edge (+16 % RECOM
        load), +$0.11 per board, one new BOM line.
      - **2512 is required:** R_on dissipates 0.17–0.22 W at 60 kHz. On the 1 W at 70 °C → 0 at 155 °C line a 2512 allows
        a ~136 °C terminal, which also clears DECISIONS 51's gate-resistor derating failure.
      - Rejected:
        - 39 Ω on CFD7 (passes only on the understated vendor charge, 80 V/ns at typical);
        - a symmetric resistor without the diode branch (off-gate 2–6 V, E_off ×25);
        - an external Cgd (3–8 V/ns);
        - 100 Ω (too slow).
    - **CM8 route** (preferred if CM8 is adopted): 39 Ω 2512 with Cgs 1 nF passes 640 / 640 on both proxies.
      - Proxy B is Infineon's IPW60R016CM8 600 V twin model: 40.6 V/ns, 554–648 A/µs. Infineon publishes no 650 V CM8
        model.
      - The device study's "CM8 528 V fail" was an artefact of its proxy.
      - The same footprint takes it, so adopting CM8 later is a value change on R_on, Cgs and the FETs.
    - **Not closed by any tested network:** maximum Qrr (4.60 µC), where 47 Ω reads 106 V/ns. The D-8 double-pulse bench
      decides:
      - S4 at 198 / 280 V, −20 A, leg A with HS turning on, measuring dv/dt and diF/dt;
      - R_on 39 / 68 / 100 Ω × Cgs 1 / 4.7 nF;
      - a repeated-pulse run of several hundred S4 edges.
      Until then the ledger keeps both checks on the as-built stresses.
    - **Sourcing flag:** JLC holds 3 of the fitted PMEG6030EP,115. The JSMSEMI clone (C53114006) is not qualified.

55. **Stage 42 (candidate 39): the DECISIONS 54 gate network, built on s41 (2026-10-15; adopted; board of record s42, 9e075b4b). Adopt over the card's
    laminate REJECT. The regression is the network's own heat, which item 54 accepted, and the still-air ceiling becomes
    20.0 A at bay 55 °C / 18.3 A at bay 61 °C.** Records: `validation-results/11-candidates/c39-gate-network/README.md`.
    Board native21s42 `9e075b4b`, chain CHAIN_DONE with no spine owner (SPINE_LOCK PASS).
    - **Scorecard against s41: REJECT on `b3_laminate_margin_K` only** (−25.2 → −30.6 K, tolerance 1.0).
      - Better: `b3_rated_part_margin_K` −64.1 → −33.4 K. Every other gate and performance metric is unchanged:
        - DRC 0 / 0, barrier, RES_A 13.375 mm, D5 8.047 / 8.507 mm;
        - Kelvin 67.77–116.44 A, OCP pickup 4.17 A, fuse-copper 0.993;
        - task 04 39 / 0, return path 15, EMI, touch, CMTI.
      - Cost: +$0.14 / +$0.11 at 5 / 500 boards, one more BOM line (93), 753 vias (−1).
    - **Built:**
      - R10 / R12 / R18 / R20 → UniRoyal 25121WF680JT4E, 68 Ω 1 W 2512 (C50371), turned 180° on the same axis, centre
        y 12.4.
      - C55 / C56 / C62 / C63 → Murata GRM1885C1H472JA01D, 4.7 nF C0G 0603 (C85980).
      - Gate runs re-laid locally (`patches21.edit_base42`): gate down x g − 2.15 into pad 2; OUT under the body to pad 1.
      - Pull-downs 0.5 mm west and north. R11 is turned 180° with its sw_a via at (59.6, 13.3), which keeps the leg-A
        In1 fuse neck at 3.88 mm (2.87 on s41). The first build's via at (59.4, 9.7) cut it to 2.42 mm, ratio 0.882.
      - R10's redundant sw_a stub via is removed.
    - **Why the laminate moved** (s42 copper with the s41 heat file, `scripts/heat_swap.sh`):
      - The copper alone is neutral to better: FET row c28 −25.2 → −22.8 K, c22 block +1.2 → +4.3 K.
      - The network's +0.68 W (c28 basis: R_on 0.140 → 0.217 W ×4, R_off 0.036 → 0.063 W ×4, RECOM / U26 / PS2 +16 %
        charge) costs c28 −4.1 / −7.8 K (block / FET row) and c22 −11.1 K (block).
      - At c22 the hottest laminate is now R12's own gate pad.
      - No copper change on this candidate recovers it. The levers are listed below.
    - **B3 rows, s41 → s42 (bay 55 °C):**

      | | c22 | c28 |
      |---|---|---|
      | Laminate, 1 mm block | +1.2 → −6.8 K | −25.1 → −30.6 K |
      | Laminate, FET row | +1.1 → −3.5 K | −25.2 → −30.6 K |
      | C40 | −2.7 → −6.0 K | −24.6 → −27.8 K |
      | R_on terminal derating (worst) | −39.6 (1206) → −6.2 K (2512) | −64.1 → −33.4 K |
      | R_off R58 terminal derating | +19.4 → +1.8 K | −7.7 → −25.4 K |

    - **Still-air ceilings** (c36's I_trip² method, `scripts/ceilings.py`):
      - bay 55 °C: all gated rows **0.0 → 20.0 A** (laminate block, R10 derating). On s41 the 1206 gate resistors failed
        with no tank current. Laminate + film 21.1 → 20.0 A.
      - bay 61 °C, solved at 61 (not shifted): **18.3 A** (R10 derating), laminate + film 18.4 A.
      - So the commissioned still-air ceiling, still open with the owner since items 46 / 51 / 53 (≤ 18 A requested), is
        **≤ 20.0 A at bay 55 °C and ≤ 18.3 A at bay 61 °C** on this board. The 22 A c22 point is no longer supported in
        still air.
    - **Datasheet ledger (3 / 31 / 58 / 1):**
      - IPW65R018CFD7 VIOLATION → PARTIAL. S4 meets 70 V/ns and 1,300 A/µs at typical Qrr (49.7 V/ns, 244 A/µs). The
        maximum-Qrr basis stays open for the D-8 bench.
      - **25121WF680JT4E is the one VIOLATION:** at c22 its terminal (138.1 °C) allows 0.199 W, and 0.217 W is 109 %
        against the 80 % rule. It clears at the ≤ 20 A ceiling above or with airflow.
      - GRM1885C1H472JA01D is PARTIAL: its temperature is bounded only by the FET-row copper.
    - **Decision: adopt s42 as board of record; the laminate REJECT is overridden.** The S4 per-edge diode limits are a
      device-ruggedness case that item 54 made the binding one, and the thermal cost is item 54's own heat, measured here.
      Holding s41 keeps an S4 overrun of 1.6× diF/dt and a gate resistor that fails with no tank current.
    - **Open (not built):**
      - local spreading copper on the R_on pads (both nets are low-voltage to their own potential group);
      - airflow over the FET row;
      - the R_on power basis: charge split 0.217 W against the study's simulated ~0.17 W, to be settled by a gate-row IR
        reading on the bench;
      - the D-8 double-pulse bench for maximum Qrr;
      - the hardware capacitive-mode detector (`CONTROLLER-REQUEST.md`, requirement only).
    - **Release condition:** unchanged from items 46 / 51 / 53. The B3 gate still fails on c28 everywhere and, at c22, on
      the laminate, C40 and the R_on derating rows. The commissioned ceiling decision above is what closes c22.

    **Integration review:**
    - **Re-scored on integration:** cherry-picked as 5ff4aded2 / 139d6443c onto 10dde8438. The task-04 fields synced
      from ps-layers (`a4_fields.py`: 41 cases, board 9e075b4b). The card is identical to the lane's: REJECT on
      `b3_laminate_margin_K` only.
    - **Rust audit re-run here:** `audit.rs` 84 / 84 tests, PASS on `frozen/` (351 components, 183 nets).
    - **Gate-network source diff:** R10 / R12 / R18 / R20 and C55 / C56 / C62 / C63 only, read in
      `power_stage_120v.ato`. The PMEG + 1 Ω turn-off path is unchanged.
    - **Override, decided:** the card's laminate metric does not distinguish heat the fix needs from heat a layout
      wastes. Before overriding, look at the all-gated-row ceiling: it goes from 0 A (s41 could not be released at any
      current) to 20.0 / 18.3 A. The benchmark becomes s42; later candidates are compared against it.
    - **Release ceiling, decided: 18.0 A** (bay 61 °C, the enclosure's worst with B3 heat; 18.3 A rounded down).
      Rated on the worst bay, not the expected 55 °C, because no measurement yet bounds the bay.
      - The firmware's shipping commissioned ceiling goes 22 → 18 A: `TANK_CEILING_DEFAULT_A`, Kconfig
        `TEMPER_POWER_TANK_CEILING_DA` default 180 and `input_limits` default. This is a follow-on firmware commit.
      - Raising it needs:
        - a B3 basis at the higher ceiling that passes, which takes board-face airflow (`b3-ratings/ENCLOSURE-REQUEST.md`)
          or a bay-air measurement under 61 °C;
        - the bench R_on reading.
      - A bay-air sensor would let the firmware run 20 A when the bay reads ≤ 55 °C. That is a controller option, not
        built.
    - **Product consequence** (temper-8d nameplate-r1, OPEN-ITEMS S2): at 18 A pooled pan power is about 650 W at 120 V
      (0.42× the Control Freak). Board-face airflow is the lever that matters. On 2 oz copper, layout is worth about
      1 A.
    - **Ledger after the cherry-pick:** 3 / 31 / 58 / 1 (25121WF680JT4E). The two verification batches (S7, 27 lines)
      are applied on top in a later commit, and their isolator CMTI rows are re-evaluated at s42's 49.7 V/ns edge.

56. **B3 release basis set to the release ceiling: c18 at bay 61 °C, and I_line 13.5 A everywhere; firmware ships 18 A
    (2026-10-15; gate, records and firmware, no board change). s42 passes the release gate by +0.7 K.**
    - **Why:** after item 55 the `b3_ratings` gate still judged c22 / c28, which cannot pass in still air on this board, so
      it gated nothing. The release case `c18_h10` now decides it:
      - 18.0 A × 1.05 = 18.9 A trip, h 10, bay 61 °C (the enclosure's worst bay with B3 heat);
      - solved at that bay, not shifted.
    - **Ratchets:** `b3_laminate_margin_K` / `b3_rated_part_margin_K` stay on c22 / c28 at bay 55 °C, so cards from s32
      on stay comparable. New compared ratchet: `b3_release_margin_K` (higher is better, 1 K tolerance; cards without
      it are skipped).
    - **Line current:** 13.5 A in every case (`b3/run_study.py` `I_LINE_A`). That is the firmware inlet bound
      I_ps·1.10 + I_aux ≤ 13.5 A; the 11.1 A hold was not a bound (`b3-ratings/line-hold-2026-10-15/`). Three inputs
      move: the ac_l / ac_n copper, L1's row, and BR1's sink share.
    - **s42 (9e075b4b), release case:** PASS with no failing row.
      - R10 2512 derating +0.7 K, C40 +1.1 K, R20 +1.1 K.
      - Laminate block +4.1 K, FET row +7.0 K.
      - Ratchet rows move ≤ 0.1 K (laminate −30.6 → −30.7 K). L1 (advisory) −12 K, +25 K left.
      - Card: `b3_ratings` false → **true**. Against s41 it is still REJECT on the laminate ratchet only; that is
        overridden by item 55.
    - **Gated still-air ceiling at bay 61 °C / 13.5 A:** 18.3 A (R10), unchanged, so the 18.0 A release ceiling
      stands. The I_trip² interpolation agrees with the direct c18 solve within 0.2 K on R10 / R20 / C40 / FET row, and
      is 2.7 K conservative on the laminate block.
    - **Firmware** (1c98e4492, 7fc8da3bb; host tests 31 / 31):
      - `TANK_CEILING_DEFAULT_A` 22 → 18 A; it is also the no-pan clamp. Kconfig `TEMPER_POWER_TANK_CEILING_DA`
        default 180.
      - `COIL_SENSOR_FAULT_TANK_MAX_A` 22 → 18 A, and a test keeps it ≤ the default.
      - `config_ok` no longer accepts an RMS trip above the derived 1.05× (it allowed 1.1×, 19.8 A at 18 A, above the
        trip this rating is computed at).
      - `pan_min_rms_a` must sit below the no-pan clamp.
      - COMMISSIONING's raise ladder is now 18 → 20 → … → 28 A. Its new gate 0 is a passing B3 basis at the new
        ceiling (board-face airflow or a measured bay under 61 °C), plus the bench R_on reading.
      - The derived trips at 18 A: RMS 18.9, crest guard 27, peak 42.06 A.
    - **Margin is thin:** +0.7 K rests on the R_on 0.217 W charge-split bound (~0.17 W simulated). The bench IR
      reading of the gate row (S2) confirms it, or frees about 3 K.
    - **Cache note:** `run_study.py` is in `model_key.py`, so the next chain recomputes task 04 and B3 once.

57. **Stage 43 (candidate 43): DECISIONS 48 cleanup pass on s42, snubber source MPN fixed, ledger re-cited to s43
    (2026-10-15; board of record s43, 61447816). Card ACCEPT against s42.** Records: `11-candidates/c43-cleanup/README.md`.
    - **Cleanup:** `track_cleanup21.py` (unchanged) on s42's copper and export: 621 edits on 100 nets; nothing excluded.
      - Right angles 100 → 49, acute 199 → 23, fold-backs 43 → 3, any-angle 675.0 → 272.6 mm; track −97.3 mm.
      - Deterministic (copper `e5f7f90e`); a second run on the s43 export makes 0 edits.
      - Gate networks: no spacing fell, every gate loop is shorter (−2.6 to −4.9 mm).
      - Fuse necks are identical; Kelvin, OCP pickup and the spine lock are unchanged.
    - **Chain CHAIN_DONE, no spine owner:** DRC 0 / 0 (s42 warning set); barrier 0; RES_A 13.375; D5 8.047 / 8.507; DFM 753
      vias; FIT clean; task 04 39 / 0 (hv_dc −0.011 %, res_a +0.043 %). TP3 / TP4 / TP7 (refs TP26 / TP29) move 0.5–1.0 mm.
    - **B3:** release margin +0.7 → **+1.2 K** (worst row now C40; R10 +3.1 K); laminate ratchet −30.7 → −30.2 K;
      rated-part −33.4 → −32.3 K; `b3_ratings` PASS. Heat inputs are unchanged: the R_on rows gain 1–4 K from copper alone,
      and R53 / R54 lose up to 0.7 K.
    - **Source:** C12 / C13 / C19 / C20 GRM31A5C3A102JW01D (no such Murata part) → YAGEO CC1206JKNPOCBN102, the C113872
      the order already placed.
      - Same 1206 footprint, nets and designators. atopile 0.2.69 offline, refrozen.
      - `audit.rs` IDENTITY plus `stage43_snubber_mpn_holds` (85 / 85); `verify_source.py` asserts it.
      - The BOM line is plain JLC Extended (`apply_lcsc.py`; STOCK addendum s43 and snapshot s43 re-key the existing rows).
    - **Card:** better on 3 B3 margins and 4 geometry metrics. `jlc_extended_lines` 67 → 68 is a counting correction: the
      line was always Extended but labelled "JLC substitute". Price and stock are unchanged.
    - **Ledger 3 / 32 / 58 / 0, gate PASS:**
      - CC1206JKNPOCBN102 re-keyed and its source-MPN gap closed.
      - GRM1885C1H472JA01D re-cited to the c18 release case (FET row 122.1 °C ≤ 125 °C); the c22 overrun (132.6 °C) is an
        `owner: airflow route (c22/c28)` gap.
      - Every margins.json citation follows the s43 rows. The c22 worst R_on is now R12 (136.1 °C, 0.976 of the derated
        power).
    - **Decision:** adopt s43 as the board of record. The OPEN-ITEMS B5 cleanup is done on the merged copper. Later lanes
      re-run the pass after they merge (it is idempotent).

    **Integration review:**
    - **Cherry-pick:** 719084486 / cb7d7a76e onto 00be6ebc5, clean. Task-04 fields synced, board 61447816.
    - **Checks re-run here:** `audit.rs` PASS on `frozen/`; ledger gate PASS; tests (ledger, track geometry, spine lock,
      cleanup, jet strip) all pass.
    - **Card:** re-scored on integration. Identical to the lane's, plus the new `jet_strip_height` gate (PASS, max
      1.72 mm, C13), which the lane predates. ACCEPT against s42.
    - **The benchmark is now s43.** It is the first ACCEPT since s41 that needs no override.
    - **Follow-on (systemic):** the ledger cites `margins.json` by line range, so every B3 re-run moves the citations
      (this lane re-cited them all by hand). The ledger is to cite B3 rows by key (case + item) instead, resolved by
      `gate.py`.

58. **Stage 44 (candidate 44, SELV-spine lane): the SELV return-path pass, built on s43 (2026-10-15; adopted). Board of
    record s44, 2a84051f. Card ACCEPT against s43.** Records: `11-candidates/c44-selv-spine/README.md`. Chain
    CHAIN_DONE with `SPINE_OWNER=selv`.
    - **Opens 15 → 7 (OPEN-ITEMS S10).** All 8 SELV-net opens are closed: PERMIT ×3, BUS_FAULT, BUS_FAULT_ISO, BIAS_GOOD ×3.
      Each F↔B via of these slow SELV lines swaps the In1 v3v3 / In2 selv_gnd reference, and no cap was within 4.6–21 mm.
    - **The fix:**
      - seven 100 nF 0603 v3v3-selv_gnd transfer caps, **C169–C175** (`c_ref_xfer_6..12`), 1.10–2.60 mm from their vias;
      - each on its own plane vias 0.85 mm off the pad;
      - BUS_FAULT's U13 drop via moves 0.97 mm down its trunk (no cap pose within 3 mm of the old spot);
      - BIAS_GOOD's U40 In2 hop runs on to its leg-A drop, and its pour-edge via (no pour on either side) is removed.
    - **Card:**
      - better: `return_path_open_changes` 15 → 7, acute corners 23 → 22;
      - costs: parts $202.32 → $202.38 at 500, placements 351 → 358, vias 753 → 765. The caps share the existing JLC Basic
        line C14663 (no new BOM line or MPN);
      - unchanged: D5 8.047 / 8.507, RES_A 13.375, worst asserted 2.72 mm, Kelvin 67.77, OCP pickup 4.17 A, fuse ratio
        0.993, EMI 12.4 dB, touch 0.241 mA, CMTI 1.579, jet strip 1.72 mm;
      - B3 release +1.2 K, laminate −30.2 K, rated part −32.3 K, `b3_ratings` PASS (2 of 132 rows move 0.1 K).
      - Cleanup pass: 0 edits (idempotent).
    - **Left (7, HOT side, not this lane):** bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, the GOOD node at U45.1.
      - Their vias sit off the In1 `ocp_kelvin_p` / `n_ls` pours, with In2 / B bare.
      - Closing them needs HOT-domain Kelvin / n_ls copper on the stage-28-locked OCP nets.
      - That is a WS4 / G08 pass with the OCP pickup and Kelvin re-checked. S10 stays open for those 7.
    - **SELV-spine lock re-issued** (baseline `spine-baseline-native21s44`, board f27d5bba = the run-1 copper):
      - owner-scope differences: only C170 / C174's 4 plane vias and stubs, and 3.155 mm² of plane antipad per plane;
      - frozen_refs gains C169–C175.
    - **Gates tightened:**
      - `return_path19.XFER_CAPS` adds C169–C175 (pad-to-plane via ≤ 1.6 mm);
      - `audit.rs` IDENTITY and the net loop cover `c_ref_xfer_5..12`; new test `stage44_selv_transfer_caps_hold`, 86 / 86.
    - **Reverses if:** a lane needs the C169–C175 / BUS_FAULT via spots for other copper (then the opens come back), or
      bench SI shows the slow SELV lines need no transfer caps (−7 placements).
    - **Integration check (2026-10-15):** cherry-picked onto the integration branch with the task-04 fields synced;
      `audit.rs` PASS (358 / 183); the card re-scored there is identical to the lane's; ACCEPT vs s43; ledger, track,
      spine-lock, cleanup, jet-strip and scoped tests pass on the s44 board. FAB-NOTE moved to s44 (750 POFV vias,
      60 in pad, 75 at a pad edge; 859 plated holes). **The benchmark is now s44.**

59. **S16 follow-up: candidate B (TPS3701 per window) against the chosen 1c-4420, by side-by-side FMEA (2026-10-15;
    1c-4420 kept, B not adopted).** Study: `validation-results/11-candidates/s16-fmea-b-2026-10-15/` (s43 / 1c-4420 / B,
    rows C1–C9 of `c24-monitor-fmea` plus new rows; reruns byte-identical; S16 bands and c24 scores reproduced).
    - **Reference drift is bounded in both designs.** The companion UV / OV announces before any threshold passes its hard
      limit, TL431 and TPS3701 alike (worst dormant span OV: s43 19.51, 1c-4420 19.96, B 19.94 V; H = 21 V). The S16
      study's C4 objection holds only against the qualified basis, and equally for both.
    - **B as drawn is a regression:** an open span-divider bottom, or an INB-VDD pin short, puts 17 V on a 7 V input
      (SBVS240C p.4). TI documents no overstress behaviour, so span OV can be lost silently and no proof test covers it.
    - **B amended** (span bottoms split 2 × 10 k / 2 × 6.2 k, tops 193 k / 138 k; both TPS3701 VDD from the local 5 V)
      removes that path and beats 1c-4420 in all nine exposure cases: 16.7 vs 19.3 FIT·rails (−13 %), front end −42 %.
      Still worse: OV detection +27 µs typical (no maximum published for either part), C5 rate 2.8 vs 2.0 FIT / rail.
    - **Cost:** about +$1.49 / board over 1c-4420 plus a three-island layout change, for about 2.6 FIT·rails. Build it only
      if those islands are re-laid anyway, and then in the amended form (decouplers C176–C178; U47–U49).
    - **Found on the way:** no proof test covers dormant masking in any monitor variant (B8 screens only the HS veto
      corridor): OPEN-ITEMS B13. The c24 C7 sliver is narrower than recorded (LM339B minimum supply 2 V, not 3 V).
    - **Open:** TI TPS3701 FMD / pin FMA and INx clamp rating; bench tpd(LH) spread at 10 mV overdrive.
    - **Reverses if:** TI publishes TPS3701 overstress data that makes the as-drawn B safe, or the monitor islands are
      re-laid (then build amended B).

60. **Stage 45 (candidate 45): the S16 rail-monitor fix, option 1c-4420, BOM-only on s44 (2026-10-15; adopted with a cost
    override). Board 26ce9531, copper identical to s44. Card REJECT against s44 on cost alone (+1 BOM / Extended line).**
    Records: `11-candidates/c45-s16-monitor/README.md` (chain CHAIN_DONE, no spine owner).
    - **Change (×3 rails):**
      - U17 / U19 / U21 TL431AIDBZR → TL431BIDBZR;
      - R79 / R97 / R112 10 k → 4.42 k;
      - taps: neg UV 750 / 10 k, neg OV 2.94 k / 10 k, span UV 90.9 k / 11 k, span OV 104 k / 11 k;
      - same pads; `default.net` byte-identical; 24 instances change MPN.
    - **Bands** (re-derived from the frozen values with the S16 model; the 1c-4420 table reproduced to 1e-4):
      - span UV release ≤ 16.479 V against the 16.575 V rail minimum: **−0.229 → +0.096 V**;
      - span OV trip ≥ 17.569 V against the 17.425 V rail maximum: **−0.233 → +0.144 V**;
      - RSS +0.310 / +0.382 V; joint 6.0σ / 6.4σ (was 4.6σ / 4.7σ);
      - neg UV catch −0.015 → +0.060 V.
    - **Corners:** span-OV upper 18.60 V. That is inside the 19 V hot-load re-run (+0.40 V), and the 2EDR8259X VDD ratio is
      0.886 of 21 V. Span UV lower 15.569 V, MARGINAL (+0.069 V against 15.5 V).
    - **Card:** every gate and performance metric equals s44.
      - Cost: lines 93 → 94, Extended 68 → 69.
      - parts $202.38 → $201.60 is an estimate-basis artefact: on like-for-like JLC 2026-10-15 ladders the change is
        **+$0.181 / board**.
      - ACCEPT against s43 / s42; REJECT against s41 on the laminate ratchet (DECISIONS 55).
    - **Proposed: adopt with a cost override, as for S16 correctness.** The card has no metric for monitor tolerance.
      Buy RT0603BRD07750RL early (2,661 at JLC against 1,500 needed).
    - **Gates tightened:** `audit.rs` IDENTITY + `stage45_rail_monitor_values_hold` (87 / 87); `verify_source.py` values;
      ledger 3 / 37 / 54 / 0 of 94. **Open:** B3 probe rows at the monitors; JLC preview U17 / U19 / U21.
    - **Reverses if:** the islands are re-laid anyway (then amended candidate B, DECISIONS 59).
    - **Integration (2026-10-15): adopted with the cost override.** S16 is a worst-case correctness defect the card cannot
      score; the fix costs +$0.18 / board. The FMEA of this exact variant is DECISIONS 59 (V1). Cherry-picked with the
      card re-scored identical, audit.rs PASS, `cu_temp_basis` PASS, all tests pass on the s45 board. **Board of record
      and benchmark: s45.** FAB-NOTE moved to s45 (vias and drills as s44).

61. **S17: B3 on hot copper becomes the thermal basis; the release tank ceiling drops 18 → 17.5 A (2026-10-15; adopted).
    Board s45 unchanged (a1e6488f after the chain rebuild, geometry identical to 26ce9531 by `geom_diff45.py`).**
    Records: `round5-native21/b3-ratings/hot-copper-2026-10-15/README.md` (method, control, s42 BASIS) and its
    `s45-bay61/` direct solves; firmware 44cf184a7.
    - **Model.** Every A4 copper cell carries q20·(1 + α(T − 20 °C)), α = 0.00393 /K, solved exactly at each case's own
      bay with the current held at the 20 °C solution (an upper bound on loss by Thomson's principle). It is now the gate
      default; cold-copper run files are refused except in named controls. The 20 °C control reproduces the old
      `margins.json` byte for byte. Copper loss at the old release case rose ×1.31 (6.34 → 8.33 W).
    - **Ceiling, from direct bay-61 solves on s45** (copper rows; R10 2512 terminal derating binds; `ceilings.py`'s I²
      extrapolation is optimistic below 22 A and is not used):

      | Tank ceiling (A) | 16.5 | 17 | 17.25 | 17.5 | 17.75 | 18 |
      |---|---|---|---|---|---|---|
      | R10 margin (K) | +4.1 | +2.6 | +1.8 | **+1.0** | +0.2 | −0.7 |

      **Release case c18_h10 → c17.5_h10 @ 61 C, I_line 13.5 A.** 17.5 A is the highest step with positive margin on a
      0.25 A grid; it is not rounded up.
    - **Firmware (44cf184a7):** TANK_CEILING_DEFAULT_A 17.5, Kconfig 175 dA, COIL_SENSOR_FAULT_TANK_MAX_A 17.5; trips
      scale with it (peak 40.975, RMS 18.375, crest 26.25 A). The COMMISSIONING ladder now starts at 17.5. Host tests
      31 / 31 in this worktree.
    - **Card (s45 re-scored, the benchmark):** release margin +1.2 → **−17.6 K**, bound only by the 85 °C monitor ICs
      (est °C against 85 °C: U29 / U31 / U30 LM339B 102.6 / 101.3 / 96.5, U17 / U21 TL431B 92.4 / 85.3). Their B3 probe
      rows are new; they fail at any tank current in still air at bay 61, so the board is **not releasable until stage
      46** swaps them for 125 °C grades (TL431BQ, LM2901B, and U5's LM4040 Q-grade; BOM-only). At 125 °C the worst
      monitor row would be +22.4 K, leaving R10 (+1.0 K) as the release limiter. Ratchet: laminate −30.2 → −51.1 K, rated parts
      −32.3 → −51.3 K (c28, as before a capability-gap diagnostic, not a release claim). `cu_temp_basis` PASS.
    - **Ledger:** 13 c18 citations re-keyed to c17.5 with the hot values; derived limits for R5 (CSS2H), R22 (RC1206) and
      R10 / R12 (25121WF) recomputed from their derating curves; 34 ratios recomputed; gate PASS, no release row over
      its limit.
    - **G6 R5 derating** (c28 / h25, re-run on s42 hot copper by the B3 lane, hot-copper README) still passes:
      `g6_margin_pct` 62.7 → **32.6**, R5 pad 123.6 → 144.3 °C against the 148.4 °C bound. Re-run on s45 (board
      a1e6488f): the same 32.6 % (worst with tolerance and TCR 31.4 %; four-pad sensitivity 26.8 %), trip floor 67.5 A;
      `stage17-r5/g6-native21s45-hot.json`.
    - **Stale downstream:** the required jet h_top for the controller enclosure (45 / 59 W/m²K, temper-8d) was solved on
      cold copper and will rise. It is superseded and must be re-solved on hot copper before it is cited.
    - **Why not keep 18 A with a thermal candidate:** the heat-attribution levers (tank copper −20 % ≈ +1.75 A, bay 55
      ≈ +1.6 A, film self-heat ≈ +1.03 A, sink −10 K ≈ +0.92 A) each need a layout or enclosure change. 0.5 A of tank
      current is the cheapest correct answer now; a later candidate can buy it back and must show it on this basis.
    - **Reverses if:** a coupled solve with redistributed current (not fixed J) or bench thermocouples at R10 / R12 at
      17.5–18 A show ≥ 2 K more margin than this model; or a layout candidate raises the R10 row.

62. **Stage 46 (candidate 46): rail-monitor ICs on their 125 °C grades, BOM-only on s45 (2026-10-15; adopted). Board
    16a58861 (integration build), geometry identical to s45 a1e6488f; card ACCEPT against the hot-copper s45 card.**
    Records: `11-candidates/c46-monitor-grades/README.md` (lane build 7bfe8b76 on the c18 basis; the integration chain
    re-ran it on the c17.5 basis of item 61, `runs-native21/s46/chain46int.log`, CHAIN_DONE, no spine owner).
    - **Change:** U17 / U19 / U21 TL431BIDBZR → **TL431BQDBZR** (C190245, 17,789 at JLC); U29–U31 LM339BIDR →
      **LM2901BIDR** (C22427890, **1,966 against 1,500: buy early**). Same pads and pinouts; 6 instances; BOM stays at
      94 lines, 69 Extended; **+$0.12 / board** (v2 pricing $171.71 → $171.83 @ 500). The B3 gate now takes each
      monitor row's limit from the T_A grade of the MPN in the frozen BOM (`MONITOR_GRADES`); an unknown MPN stops it.
    - **B3 (hot copper, c17.5 @ 61):** worst monitor U29 102.6 °C, **+22.4 K** against 125 °C (c28: +19.0 K). Release
      margin −17.6 → **+1.0 K**, bound by R10 2512 terminal derating; **`b3_ratings` gate PASS** for the first time on
      hot copper. Ratchet unchanged (laminate −51.1, rated part −51.3 K).
    - **Bands on the 125 °C basis** (dividers unchanged; controls reproduce s45 to 1e-4): rail margins worst case neg
      UV +0.060, neg OV +0.105, span UV **+0.057** (was +0.096), span OV +0.102 V; joint RSS 6.0σ / 6.4σ unchanged. Span
      UV is MARGINAL against the 0.080 V target, still positive at the worst-case corner; the span-UV lower corner 15.53 V
      is +0.03 V over 15.5 V. Span-OV corner 18.643 V, +0.357 V under the 19 V hot-load re-run; 2EDR8259X VDD 0.888 of
      21 V.
    - **Card:** every gate and other metric equals s45; better `b3_release_margin_K`; `gates.b3_ratings` False → True.
      Audit 88 / 88 (with `stage46` checks), ledger PASS 3 / 38 / 53 / 0 of 94 (LM2901BIDR PARTIAL), all unit tests pass.
    - **U5 stays LM4040A25IDBZR, and is still over its rating:** no A-grade 125 °C LM4040 exists at TI, and the C25Q
      would raise the OVP upper corner by 2.16 V. The probe sweep reads U5 at 89.5 °C against 85 °C (−4.5 K at c18 @
      61), a report-only row the gate does not hold. **Open:** a cross-vendor search for a 0.1 % 125 °C 2.5 V shunt
      that holds the OVP and OCP corners is running; the row becomes gated when it lands.
    - **Integration note:** the lane's ledger refresh of 30 c18 citations was superseded by item 61's c17.5 re-cite; the
      new part entries were re-applied with `ledger46.py` on the integration margins.
    - **Not done:** FMEA C1–C7 re-run on the Q grades; the 15.5 V droop campaign at the span-UV corner; JLC preview of
      the 6 changed CPL lines (U17 / U19 / U21 180°, U29–U31 270°).
    - **Board of record and benchmark: s46.** FAB-NOTE moved to 16a58861 / gerbers 059681ec.
    - **Reverses if:** LM2901BIDR stock cannot cover the lot (fallback LM339BIDR fails the release case at any current).
