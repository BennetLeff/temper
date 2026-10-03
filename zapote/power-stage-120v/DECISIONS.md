# Placement decisions

This file records owner decisions. The owner approved the proposed D1–D3
and D6 defaults on 2026-09-25, then D5 as a conditional placement basis.
On 2026-09-26 the owner approved a revised 240 × 160 mm, four-layer design
basis. On 2026-09-26 the owner also gave renewed D4 approval for the revised
native-05 placement and native-06 routing, with three conditions (below).

| ID | Decision | Current status |
| --- | --- | --- |
| D1 | Maximum board outline | **Revised approval 2026-09-26:** 240 × 160 mm. Supersedes the 220 × 160 mm default. Owner reply: “Approve 240 × 160 mm, four layers”. |
| D2 | Heatsink and airflow | **Approved 2026-09-25:** shared PE-bonded heatsink along a long edge, with electrically insulated MOSFETs and bridge. Airflow direction is still not chosen. |
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
