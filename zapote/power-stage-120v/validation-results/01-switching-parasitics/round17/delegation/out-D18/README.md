# D-18 — conditional loss and enclosure budget

**Reserve a shared PE-bonded forced-air sink with RθSA ≤0.15 °C/W, each MOSFET interface ≤1.0 °C/W, and ≥20 CFM delivered through the sink; flow from the coil/right end toward BR1/mains/left. The conditional worst device is Q5 at 105.59 °C with 50 °C inlet air, giving 19.41 °C to the 125 °C target.**

This is an enclosure design allocation, not a guaranteed loss bound, selected assembly or powered-operation release. The owner explicitly accepted a conditional budget using the 25 °C maximum scaled by the typical temperature characteristic, after the absence of a guaranteed hot RDS(on) maximum was raised. Source revision: `b30b3ae35a4bd3ad5c22d8c300c4640986e1232a`; analysis by OpenAI GPT-6, 2026-10-02. The source decision entries are labelled 2026-10-03; that is their recorded label, not this report's measurement date. No board, netlist, firmware or vendor model changed.

## What is calculated

[losses.py](losses.py) reads the committed round-3 tank cases, D-15 cycle proxies and D-13 hot records. [loss-table.csv](loss-table.csv) covers all 90 requested 120/140 V cases (five pan families, three corners, three power requests). [results.json](results.json) retains every per-device conduction/switching allocation, both airflow directions, temperature iterations, source hashes, diode diagnostics, sensitivities and the inherited unknown list. The `records` array preserves round 3’s scenario/ref/mechanism/watts/basis/source and sink/board-fraction format; its null-valued records are retained separately as `inherited_unknown_records`. Native-17 part identities and sink-device positions are checked against the older geometry intake. Native-18's value-only DT change is assumed to preserve these positions, subject to D-16's verification.

The thermal candidate set is the 62 cases below the earlier static CT minimum of 50.9 A. This is only a screening subset: it does not prove that they are deployable or that the remaining cases will be safely interrupted. Cases inside the 50.9–59.5 A static CT spread are marked separately; above 59.5 A is an unprotected steady stress, not a continuous heatsink requirement. D-17 must establish actual trip/gate-off behavior. No fault case is silently converted into a sustainable load.

### Loss accounting

- Conduction per MOSFET: `I_tank,rms²/2 × RDS(Tj)`, with `RDS(T)=18 mΩ × [1+1.2×(T−25)/125]`. This scales the 25 °C maximum by the linearized typical 15-to-33 mΩ temperature ratio. It is an owner-approved **estimate**, not a hot maximum. Each junction is iterated separately to a change below 1e-8 °C; this numerical tolerance says nothing about physical accuracy.
- D-15's 443 ns finite-window positive-terminal-power proxy is not dissipative switching heat. It already contains capacitive/diode energy and conduction tails. For an enclosure allowance, use the largest sampled HS and LS cycle proxy across its 170/198 V, 2/5/10/20/30/37 A and ESL 1.06/10 nH points, multiplied by the largest D-13 hot/cold energy ratio (1.242733). The resulting allocation is 12.7574 W/HS and 13.1537 W/LS at 36 kHz, scaled by each tank case's frequency. The maximizing cold sample is 198 V/2 A/10 nH, not full-load ZVS. This intentionally expensive allowance avoids inventing a line-cycle switching histogram.
- **There is no committed round-3 `inputs/switching-events.csv` in this base.** The former loss script references it but it is absent. Therefore these are design budgets, not reconstructed line-cycle losses. Events below 170 V, above 37 A, adverse commutations, untested current continua, temperature transfer to light-load events and leg-B differences remain unqualified. Even a maximum over samples is not a physical envelope. The real histogram and hot transfer can reduce or increase the budget.
- D-15 body-diode dead-time power is retained separately at each 443 ns point in `results.json`. At 37 A/1.06 nH it is 0.14647 W/switch at 170 V and 0.14513 W/switch at 198 V, at 36 kHz and 27 °C. **Do not add this to the overlap proxy**; that would double-count. Adding whole-cycle channel conduction to the proxy also overcounts its conduction tails; no subtraction is justified by available net-energy evidence.
- BR1: `2×1.05 V×(2√2/π)×I_input,rms`, with an assumed sinusoidal `I_input=Ptarget/(0.95×Vline)`. The full-power assumption is 15 A at 120 V; it is not a measured power factor or hot VF bound. The symmetric four-element junction model uses RθJC=1 °C/W per element, hence package-total heat times 1/4 in the junction-rise term.
- Gate network: assume 350 nC per 15 V gate transition, `4QgVf`, plus 0.045 W from the four 10 kΩ gate holdoffs at 50% duty. The 500 nC sensitivity is also recorded. Infineon's 234 nC point is only for a 0–10 V test and cannot certify charge at 15 V. This is a board-side dynamic-power allocation; actual resistor/driver partition, driver quiescent draw and supply-conversion heat remain unknown, not zero.

All MOSFET/BR1 modeled heat goes to the sink; R5, gate networks and other board parts remain board-side. The 90% sink sensitivity transfers the missing 10% to the board explicitly; it is not a cooling benefit for the complete enclosure. Round 3's capacitor ESR, CT, magnetic, auxiliary, snubber, unmodeled switching and supply unknowns remain in `inherited_unknowns_not_zero`; this does not close task B3's full board heat map.

## Per-device budget at the recommended cooling point

50 °C inlet, 0.15 °C/W common sink allocation, 1.0 °C/W MOS interface, 0.45 °C/W BR1 interface, right-to-left airflow, 20 CFM delivered. Watts include conduction plus the explicit switching allowance above. The complete case/mechanism table is in the CSV/JSON.

| Case | f kHz | Irms A | Q2 W | Q3 W | Q5 W | Q6 W | BR1 W | Sink W | Worst Tj °C | R5 nominal W | Gate allocation W |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cast_iron-high-120v-1710w | 32.773 | 21.469 | 18.305 | 18.759 | 18.531 | 18.835 | 28.360 | 102.790 | 94.54 | 0.461 | 0.733 |
| cast_iron-high-140v-1710w | 34.622 | 21.189 | 18.799 | 19.274 | 19.026 | 19.350 | 24.309 | 100.758 | 95.02 | 0.449 | 0.772 |
| carbon_or_430_steel-mid-120v-1710w | 35.899 | 25.724 | 22.816 | 23.379 | 23.232 | 23.518 | 28.360 | 121.305 | 104.67 | 0.662 | 0.799 |
| low_R_silargan_like-low-140v-855w | 45.727 | 23.119 | 24.383 | 25.033 | 24.737 | 25.152 | 12.154 | 111.460 | 105.59 | 0.534 | 1.005 |
| offset_or_small_pan-low-120v-1710w | 32.342 | 44.576 | 51.031 | 52.573 | 54.378 | 53.691 | 28.360 | 240.032 | 170.82 | 1.987 | 0.724 |

The last row is an above-CT stress; its steady result is **not** an approved operating point. The half-power case can be the thermal maximum because the deliberately fixed switching allowance increases with frequency. The tank grid includes frequencies outside the nominal 33–39 kHz full-power band and up to its controller ceiling; using each recorded frequency preserves that fact instead of forcing all cases to 36 kHz.

## Sink/interface budget and airflow

Use **40/50 °C air at the heatsink inlet inside the enclosure**, not room temperature. With `Psink=ΣPdevice`, the common-sink allocation is `Ts=Tin+RθSA×Psink`. A separate conservative spatial sensitivity adds `upstream heat/(ρcp×flow)` at each mounting site (ρ=1.09 kg/m³, cp=1005 J/kg·K are engineering assumptions). This is not CFD: it ignores longitudinal sink spreading and heat deposited between devices. Catalog RθSA already reflects its own air warming, so the added term is an explicit extra gradient allowance, not a claim that air heating is absent from a vendor curve. Qualification must compare the hottest mounting point to inlet air and avoid counting the same gradient twice.

`Tj=MOS local sink + Pmos×(0.28+RθCS)`; BR1 uses `local sink + Pbridge×(0.25+0.45)`. Both have a 125 °C design target here. Solve each case iteratively, then bisect RθSA at that limit over all 62 candidate cases:

| MOS interface °C/W | 40 °C, left→right max RθSA | 40 °C, right→left | 50 °C, left→right | 50 °C, right→left |
|---:|---:|---:|---:|---:|
| 0.50 | 0.4460 | 0.4457 | 0.3666 | 0.3658 |
| 1.00 | 0.3491 | 0.3709 | 0.2697 | 0.2915 |
| 1.75 | 0.2038 | 0.2216 | 0.1234 | 0.1347 |

These are conditional maxima, not procurement guarantees. The recommended 0.15/1.0 allocations leave room below them. Pad/contact sensitivity dominates: round 3's SIL PAD K-10 area transfer is about 1.75 °C/W and does not meet the recommended interface allocation; SIL PAD 400 is worse. Minimum TO-247 metal area is 151.2 mm² (Infineon drawing minus mounting hole). The interface budget includes both contacts, mounting pressure, spreading and any insulator: material bulk conductivity alone cannot prove it. An electrically insulating ceramic with grease/contact control is a candidate; no exact pad is qualified. BR1's assumed 0.45 °C/W uses optimistic whole-back contact and needs its own pressure/contact test. D5 electrical insulation and the PE bond remain mandatory.

Device order, viewed from the component side with sink at top: **left BR1 → Q5 → Q6 → Q3 → Q2 right**. Right-to-left gives the MOSFETs fresh air before BR1; left-to-right preheats them with bridge loss. At the recommended allocation the worst-device comparison across all candidate cases is:

| Inlet | Left→right worst °C / device | Right→left worst °C / device |
|---|---|---|
| 40 °C | 96.39 / Q2 | 94.48 / Q5 |
| 50 °C | 107.80 / Q2 | 105.59 / Q5 |

Recommend **right/coil inlet → left/mains exhaust** for placement decision D2. D2 is the decision identifier, not a previously approved direction. D6 still means mains left and coil right. Keep this a dedicated sink duct; do not draw coil/under-glass exhaust into its inlet or discharge hot air over the controller. With a better 0.5 °C/W MOS interface, BR1 can become the limiting device and the direction advantage can reverse; the recommendation is tied to the stated interface budget, not universal.

### Sensitivities at the nominal worst right-to-left case

| Change | Maximum Tj °C |
|---|---:|
| RDS ×1; switching ×1; interface 1.0 °C/W; 20 CFM; sink fraction 1 | 105.59 |
| RDS ×1.25; switching ×1; interface 1.0 °C/W; 20 CFM; sink fraction 1 | 110.81 |
| RDS ×1; switching ×1.25; interface 1.0 °C/W; 20 CFM; sink fraction 1 | 115.40 |
| RDS ×1; switching ×1; interface 0.5 °C/W; 20 CFM; sink fraction 1 | 92.19 |
| RDS ×1; switching ×1; interface 1.75 °C/W; 20 CFM; sink fraction 1 | 127.03 |
| RDS ×1; switching ×1; interface 1.0 °C/W; 10 CFM; sink fraction 1 | 113.45 |
| RDS ×1; switching ×1; interface 1.0 °C/W; 40 CFM; sink fraction 1 | 101.69 |
| RDS ×1; switching ×1; interface 1.0 °C/W; 20 CFM; sink fraction 0.9 | 99.50 |
| RDS ×1.25; switching ×1.25; interface 1.0 °C/W; 20 CFM; sink fraction 1 | 120.89 |

A separate sweep over all 62 candidates doubles BR1 interface resistance to 0.90 °C/W (109.80 °C maximum), raises its assumed VF by 20% (106.00 °C), and combines both (117.23 °C). These remain estimates; see `bridge_sensitivity_all_candidates`.

These are one-case sensitivities, not a recomputed envelope for all parameter combinations. The repeated S2 hot/71 A/280 V proxy sensitivity is retained separately; it is not a permissible continuous fault condition. The 125 °C target must be demonstrated with the assembled limits, including fan degradation, pad pressure and bridge asymmetry.

## Commercial examples and enclosure reservation

The official [Wakefield skived-fin assembly catalog, pp3–4](https://wakefieldthermal.com/content/catalogs/Catalog-SkivedFinHeatsinkAssembly.pdf) gives **simulated, fully ducted** assembly values, not a measured installed guarantee. Candidate **SFA2B1L** is catalogued at 0.094 °C/W with push/pull fans; its sink is 60 mm wide ×305 mm long, 60 mm fins plus 8 mm base. Reserve additional space for two 25 mm fans, guards, brackets and inlet/outlet clearance. **SFA2P3S** is 180×153 mm with the same fin/base heights, three push fans, and 0.039 °C/W. Both catalog points are below 0.15 °C/W; neither is a drop-in qualified assembly. The latter would need a different multi-source mounting/flow arrangement, so its catalog rating does not validate our serial airflow model.

The catalog fan is **DC0602512W2B-BT0**, 60×60×25 mm, 12 V/11.4 W each; free-air rating 55.5 CFM and shutoff pressure 1.17 inH₂O are different endpoints. Two or three fans exceed PS1's 21 W rating before any controller load, so these examples require a separately designed supply budget. They establish an available thermal/size class, not permission to connect to J4.1. The smaller single-fan SFA2P1S is 0.118 °C/W, but its 153 mm sink length must not be assumed to fit the entire existing device/contact span.

A slimmer candidate is **Fischer LA 6 200 12**, from the [manufacturer LA6 family sheet, printed D12](https://www.farnell.com/datasheets/17634.pdf): 62×74 mm profile, 200 mm body option, 60×60×25 mm fan. Its length-dependent curve must be confirmed for the ordered variant and actual mounting before claiming compliance; a distributor's generic 0.1 K/W listing is insufficient. The old Aavid 63730 forced-flow curve (round-3 source, pp1–2) does not substantiate 0.15 °C/W for the required cut length. No curve was fabricated from fan free-air CFM.

**Procurement remains conditional:** obtain the supplier's multi-source mounting curve and fan operating point, then measure ≥20 CFM through the complete filtered duct and the effective sink temperature rise at the five mounting sites. Final enclosure CAD needs the assembly drawing, mounting/clamp stack and fan/guard envelopes; body dimensions above exclude brackets/guards. No existing board or lead geometry is authorized to move by this report.

## R5

Vishay WSK2512R0010FEA is 1 W at 70 °C local ambient, linearly derating to zero at 170 °C (Rev 11-Dec-2023, pp1–3); the 1 mΩ range has ±250 ppm/°C and F is ±1%. The candidate-set maximum is **0.68504 W** using +1% and a +100 °C resistance-temperature allowance. It fits 1 W at 40/50/70 °C, and 0.70 W at 100 °C, but exceeds 0.45 W at 125 °C. Enclosure inlet temperature does not establish R5's local board environment or element temperature.

Keep R5 only with a validated sustained-current envelope and local ambient ≤100 °C under the stated resistance allowance. If 125 °C local ambient must be supported, a **≥2 W, 1 mΩ four-terminal** part is the minimum practical rating class for this candidate set; changing it needs owner approval and OCP/parasitic/layout review. Across all requested unprotected cases the calculated resistance-corner maximum is **2.0570 W**: no 1 W shunt may sustain that. D-17 protection timing and pulse energy, rather than a larger heatsink alone, determine fault survival.

## Sources, qualification and replay

- Infineon IPW65R018CFD7 Rev2.0, 2021-04-19: p3 RθJC max 0.28 °C/W and ratings; p5 RDS(on), Qg test conditions; p12 package. [Official PDF](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf). The hot maximum column is blank.
- Diodes GBJ2510, DS21221 Rev11-2 May2025 p2: VF point and per-element RθJC; p4 outline. [Official PDF](https://www.diodes.com/datasheet/download/GBJ2510.pdf). VF at one current/temperature and typical RθJC do not bound bridge loss or thermal asymmetry.
- Vishay WSK2512, document30108 Rev11-Dec-2023 pp1–3: rating/TCR/derating. [Official PDF](https://www.vishay.com/docs/30108/wsk2512.pdf).
- Henkel TIM guide2017 pp63/75 and round-3 `heatsink_requirement.md`: typical pressure-dependent SIL PAD impedances, transferred by contact area; source PDFs/hashes are already committed under round3 and hashed again here.
- D-15 `cycles.csv` / README and D-13 `results-main.json` / README: exact 443 ns overlap definitions, cold diode subtotals and hot proxy transfer. All selected rows are complete; any missing or aborted selected row makes this script fail. The underlying campaigns retain their own aborts and limits.

No new ngspice run was needed, so no vendor fetch or altered `itl4` setting is represented as a new simulation. No licensed model is committed. Rerun from root with `PYTHONDONTWRITEBYTECODE=1 python3.12 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D18/losses.py`; compare `results.json` and `loss-table.csv` with Git. Run `python3.12 -m unittest discover -s <out-D18> -p test_losses.py` for arithmetic checks.

Owner actions: accept the duct/space allocation and direction; choose the insulator/clamp and cooling assembly after supplier checks; resolve the fan supply; retain/upgrade R5 according to its measured local environment. Bench acceptance records inlet temperature, actual tank/current histogram, all device case and local sink temperatures, flow, pad pressure and electrical insulation. Infer junction temperature with validated package paths or direct electrical thermometry; do not equate a case thermocouple with Tj. Until then, this is a conditional enclosure proposal and task03 remains unqualified.
