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
- **M8, F1:** the stock footprint's 102071 clips are rated 10 A. F1 moves to the 34.21 × 7.62 mm pattern for **Littelfuse 01220088Z (30 A)**, two per board, which get their own BOM line (`scripts/apply_lcsc.py`). **The fuse itself was undersized:** Littelfuse 326 takes a 25 % continuous derating plus temperature re-rating (≈ 97 % at 50 °C), so 20 A carries ≈ 14.5 A continuous against 14–16.5 A RMS line current. F1 becomes **0326025.MXP (25 A, same body, 400 A @ 250 Vac)**, ≈ 18.2 A continuous; the CMC (20 A), terminal (24 A) and BR1 (25 A) carry the line current, and the branch breaker protects the wiring (`sourcing/F1-J3-PARTS.md`). Source rebuilt (atopile 0.2.69, verify_source PASS, audit 74/74). **Then F1 → Eaton Bussmann MDA-25-R** (same day). 0326025's table gives no 125 Vac breaking figure, only 400 A @ 250 Vac. MDA-25-R breaks **10 kA @ 125 Vac and 1.5 kA @ 250 Vac**, typical melting I²t 734.7 A²s, cULus Recognized E19180. These are Eaton Technical Data 2002 (Nov 2025) pp.1–2, read by the owner in a browser; screenshots are in `sourcing/eaton-browser-2026-10-08/`. Eaton's p.4 derating is ~96 % at 50 °C, so about 18 A continuous with a 25 % margin. It is a BOM-only change in the same clips: the board copper is unchanged, and the BOM is regenerated from the source. It dominates 0326025 at every voltage. **Still open on F1, whichever part:** the prospective fault current at the 127 V high-line corner must stay within 1.5 kA, since no 10 kA figure applies above 125 Vac; plus the Recognized-component and clip acceptance, and clearing coordination with the enclosure's upstream MDA-30-R (melting I²t 734.7 vs 1096.7 A²s).
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
      | FET-row copper | 126 °C | 21 K to laminate Tg 150 |

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
