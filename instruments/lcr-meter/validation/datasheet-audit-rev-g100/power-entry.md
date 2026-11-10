# Datasheet audit, group `power-entry`, Temper LCR meter Rev G100 (2026-11-09)

Scope: J1 (HRO TYPE-C-31-M-12) with R1/R2 (CC Rd) and its VBUS / GND / shield pins; D1 (SRV05-4); U16 (TPS2553DBVR) with R110, C113, R121, C15, C16; U3 (AP2112K-3.3) with C17 / C18; FB1 and the 5V distribution (C117, the trunk from U16 to the switcher, relays and LEDs); every passive on USB_VBUS, VBUS_ILIM, VBUS_DAMP, CC1/CC2 and the 5V entry (including R5/R6 USB_SENSE).

Board facts come from `cad/temper-lcr.kicad_pcb` read with KiCad's pcbnew (read-only), `validation/datasheet-audit-rev-g100/{parts,nets}.txt`, `cad/design.json` and `validation/rev-g100/*.json`.

Key G100 coordinates (mm):
- J1 (54, 132), rotated −90. VBUS pads A4/B9 at (57.67, 129.6) and A9/B4 at (57.67, 134.4).
- C15 (62.0, 137.0); D1 (63, 132).
- U16 (55.6, 115.9): IN pins 1 / 3 at (56.74, 116.85 / 114.95), OUT pin 6 at (54.46, 116.85).
- C113 (59.2, 116.0); R121 (61.0, 117.7); R110 (52.0, 115.9); C16 (55.0, 118.9).
- U3 (56.85, 121.9); C17 (60.0, 121.65); C18 (64.75, 125.0).
- FB1 (53, 97); C117 (118.6, 137.6); L1 (131.5, 141.2); VB test pad (59.25, 112.9).

Scratch simulations (ngspice 45.2) were run to check two layout questions. They are not repository evidence. The scripts are next to this report: `power-entry-sim-hotplug.py` and `power-entry-sim-short.py`.

## 1. Findings

| id | severity | refs | requirement (citation, verbatim) | board fact | why it matters | suggested fix |
|---|---|---|---|---|---|---|
| G-PE-1 | **MISSING** | U16.1/.3, C15, C113, R121 | TPS2553 SLVS841F pin table, IN: "connect a 0.1 µF or greater ceramic capacitor from IN to GND as close to the IC as possible". 7.3: "Input de-coupling capacitance, IN to GND 0.1 µF min". 12.1: "placing the 100-nF bypass capacitor near the IN and GND pins, and make the connections using a low-inductance trace" | The only ceramic within 3 mm of IN is C113, and R121 (1.5 Ω) sits in its ground leg. Above 1/(2π·4.7 µF·1.5 Ω) = 23 kHz the IN node therefore sees ≥ 1.5 Ω, not a bypass. The 100 nF (C15) sits at J1 (61.2, 137.0), about 29 mm of copper from U16.1: 0.73 + 2.7 + 1.4 mm F.Cu, a via, 9.7 + 4.0 + 0.8 + 7.9 mm of 0.5 mm B.Cu, a via, then 1.9 mm F.Cu. Rev F had it about 8 mm away. `hotplug_spice.py` puts C15 on the U16 IN node ("C15 vbus 0 100n", the same node as C113), so the simulated circuit is not the built one | IN has no local HF decoupling for the charge pump and the 2 µs short-circuit response. The node that R121 was sized for no longer exists as simulated. My as-built-order sweep (C15 at the J1 node, 20–30 nH to U16, 96 corners) gives a worst of 6.17 V, so hot-plug is still fine. Simply **adding** a second 100 nF at U16 gives 6.62 V (1 of 96 corners over 6.5 V), because two 100 nF caps ring | **Move C15** (do not add a second cap) to U16.1/.3 → GND via (55.6, 115.9). That is exactly the topology `hotplug_spice.py` already proves (6.251 V with 30 nH). Keep D1 at J1 |
| G-PE-2 | RISK (medium, unverified) | U16 IN, C113 + R121, D1 | TPS2553 10.2.1.2.4: "Additional input capacitance may be needed on the input to reduce voltage overshoot from exceeding the absolute maximum voltage of the device during heavy transient conditions." 7.1: IN max 7 V. 7.5: tIOS "Response time to short circuit … 2 µs" (typ only) | Nobody has simulated a short on 5V while the board runs. Scratch model: U16 is 85 mΩ until tIOS = 2 µs, then ramps to 1.17 A over 100 ns. The short is 50 mΩ at OUT, with C16. The cable is 0.3–1.5 µH and 0.05–0.2 Ω. Results by host port current limit: 1.5 A: ≤ 5.5 V. 3 A: ≤ 6.8 V (0 / 24 at or over 7 V). 5 A: 8.2–9.2 V (23–24 / 24 over 7 V). Unlimited source (bench supply or charger): 16–26 V. IN also collapses to 0.1–0.8 V, below UVLO, before the overshoot | R121 makes this case worse. The interrupted cable current steps the IN node by I × 1.5 Ω. D1 (VBR ≥ 6 V, VC 15 V max at 4 A) does not hold 7 V. A short on 5V is already a board fault, but U16 is the part meant to survive it | Add an "output short" row to `hotplug_spice.py` using TI's TPS2553 PSpice model before deciding. If it is confirmed: either accept it (U16 is sacrificial in a fault) or add a DNP SOD-123 TVS footprint at U16 IN. Record the decision |
| G-PE-3 | VIOLATION (low impact; accepted earlier) | D1.5 | SRV05-4 (Hongjiacheng Rev 2.1), Electrical Characteristics: "Peak Reverse Working Voltage VRWM … Max 5.0 V"; IR max 5.0 µA is specified only at VRWM = 5.0 V; VBR min 6.0 V at 1 mA | D1.5 is on USB_VBUS: 4.40–5.5 V steady, and 6.25 V on hot-plug | Above 5.0 V, leakage is not specified (it is bounded only by 1 mA at 6.0 V). `docs/rev-e-plan.md` (2026-10-21) argues the case for 5.25 V. That argument holds functionally (no precision node on VBUS), but the datasheet limit is still exceeded up to 5.5 V | Accept and record it as accepted. Alternatively use an array with VRWM ≥ 5.5 V, or leave pin 5 open (the internal zener still clamps D±, but VBUS then loses its TVS) |
| G-PE-4 | RISK (known FLAG, carried) | U16.3 EN = VBUS, 5V bulk | TPS2553 10.2.3.1.1: "Functions must: – Limit inrush currents – Power up at <100 mA". 11.2: "high-power functions must draw less than 100 mA at power up" | The full load (about 0.46 A, an estimate) is on from attach. The 5V net behind U16 holds C117 330 + C80/C82 20 + C112 22 + C16 1 ≈ 373 µF nominal. That is 1.87 mC at 5 V, delivered at 0.99–1.17 A for about 1.6–1.9 ms. USB's 10 µF ∥ 44 Ω rule implies 50 µC, so this is 37× | `regulator_check.json` FLAG and the Rev F README PE-2 accept it. That holds for PC root ports. It fails on a strict bus-powered hub, which allows 100 mA until configuration. The firmware now declares bus-powered, 500 mA (`firmware-rev-e/src/usb_descriptors.c:38`) | No change for G100. Test on a bus-powered hub at bring-up (bring-up §2.5 already plans it) |
| G-PE-5 | RISK (low) | R5/R6 → U1.16 (GPIO13) | RP2040 datasheet 5.5.3.1: "Voltage at IO VPIN −0.5 … IOVDD + 0.5 V" | VBUS reaches GPIO13 as VBUS/2 (2.2–2.75 V) before 3V3 exists. That gap is U16's ton (≤ 3 ms) plus U3's start. Source: 100 k ∥ 100 k = 50 kΩ | Injection is at most (2.75 − 0.5) / 50 kΩ ≈ 45 µA, for a few ms per plug-in, into the unpowered IOVDD. That is below any latch-up concern but above the abs-max text. Rev F PE-13 checked only the powered case | Accept. Or raise R5/R6 to 470 k / 470 k (≤ 10 µA). GPIO13 is a digital input, so the input leakage is fine |
| G-PE-6 | RISK (low, G100-new) | 5V trunk vias | No datasheet limit applies; this is the project's own IPC-2152 check | The whole 5V trunk and the FB1 branch leave U16 through one 0.45 / 0.30 mm via at (54.462, 117.75). `current_check.json`: 1.17 A against a capacity of 1.338 A (13 % margin). The In2 riser at x 99 is 0.9 mm against 0.875 mm needed (3 %). The trunk is 110.5 mΩ, about 130 mm (Rev F 49.8 mΩ); U13 VIN min is 4.266 V | One via defect (thin plating) puts the whole board on one barrel at the current limit. 51 mV of trunk drop at 0.46 A is acceptable | Add a second via beside (54.462, 117.75), and one at (99, 127) / (99, 143.95) |
| G-PE-7 | RISK (low, carried since Rev F) | J1, USB_VBUS | HRO TYPE-C-31-M-12 drawing: top-mount shell (GND) seated on the PCB; no keep-out shown | A 0.2 mm F.Cu USB_VBUS loop runs under J1's body: x 55.80, y 127.36–136.64 (9.3 mm), plus spurs at y 126.92 / 137.08. It is 0.15–0.7 mm from the SH legs, with solder mask as the only insulation to the GND shell. The loop is redundant: the two VBUS pad pairs already join through the B.Cu feed (vias (57.2, 126.2) and (61.225, 135.9)) | Mask scuffs at insertion could short VBUS to the shell. U16 sits downstream, so the host port takes the short | Delete the loop (the segments from (55.798, 127.364) round to (58.602, 134.993)), or move it to In2 |
| G-PE-8 | RISK (evidence, low) | J1 north VBUS neck | Project rule (`current_check.py`): "each receptacle VBUS pin is a separate source case" | The north pad A4/B9 leaves only through 5 mm of 0.2 mm F.Cu. `current_check.json` charges it 0.626 A max, not 1.17 A, so the single-pin case was apparently not solved as described. At 1.17 A, 0.38 mm is needed | Only matters if a plug makes contact on one VBUS pair for long (a worn plug) | Widen that neck to 0.4 mm, or fix the check |
| G-PE-9 | OK-NOTE | hot-plug 30 nH allowance | `docs/rev-g100-plan.md` §2: 30 nH covers J1 → U16 | Estimate: 22.4 mm of 0.5 mm B.Cu over In2 GND at 0.21 mm (≈ 0.3–0.6 nH/mm), about 7 mm of F.Cu over In1 and 2 vias, ≈ 12–20 nH. As-built-order sweep: 0 nH gives 6.16 V, 20 nH 6.17 V, 30 nH 6.17 V | The plan's allowance is conservative | None |
| G-PE-10 | OK-NOTE | U16, R110 | 9.5.1, eq. 1: "15 kΩ ≤ RILIM ≤ 232 kΩ", "traces … as short as possible". 7.3: IOUT ≤ 1.2 A (TJ ≤ 125 °C). 7.4: RθJA 182.6 °C/W | IOSmax = 22980 / 23.76^0.94 = 1169 mA; IOSnom = 23950 / 24^0.977 = 1073 mA; IOSmin = 25230 / 24.24^1.016 = 989 mA. ILIM trace is 3.0 mm. P = 0.135 × 0.46² = 29 mW (+5 °C); at 1.17 A, 185 mW (+34 °C). EN = IN (≤ 6.5 V, VIH 1.1 V). FAULT open (legal). GND pin goes to a via under the body 1.1 mm away | Fine | None |
| G-PE-11 | OK-NOTE | U3, C16, C17, C18 | AP2112 DS39724 Rev 2-2: VIN 2.5–6.0 V (ROC), 6.5 V abs max. VDROP 3.3 V: 200 mV max at 300 mA. "Stable with 1.0µF". Note 4: X7R / X5R if 1 µF. θJA SOT25 184 °C/W | VIN min = 4.40 − 0.015 (feed) − 0.062 (U16) = 4.32 V. Headroom is > 0.9 V against ≤ 0.2 V dropout. C16 (1 µF X7R 50 V) is 2.0 mm from pin 1; worst effective ≈ 0.9 × 0.9 × 0.85 = 0.69 µF. C17 is 2.0 mm from pin 5, plus C18 10 µF and the 3V3 100 nF caps. Pd = (5.5 − 3.3) × 0.1 A = 0.22 W, +40 °C. EN to VIN, NC open. Start-up surge: the U3 node sits upstream of the 110 mΩ trunk. With U16 in limit acting as a current source, the trunk adds voltage on U3's side, so `startup_surge.py`'s 3.86 V still bounds U3 | Fine. CIN is a little under the typical-application 1 µF at the cold corner. The datasheet sets no minimum | None |
| G-PE-12 | OK-NOTE | C117 | Nichicon PCG catalog CAT.8100H: PCG1A331MCL1GS is 10 V (surge 11.5 V), 330 µF ±20 %, ESR 23 mΩ, 3100 mA rms, leakage 660 µA. "In case peak temperature is 260°C or less, reflow soldering shall be once." | 5.5 V max, 55 % of rating. 13 mm from L1, about 98 mm of trunk from U16. TPS2553 12.1 asks for an electrolytic on OUT "when large transient currents are expected"; those transients are at U13, so placing it at the load is right | **One reflow only.** Tell the assembler: no second-side reflow, and hand rework only | Add it to the assembly notes |
| G-PE-13 | OK-NOTE | FB1 | Sunlord spec GZ10190000 Rev 01: 100 ± 25 Ω at 100 MHz, DCR ≤ 0.15 Ω, Ir 800 mA (20 °C rise) | It carries U15's 5VA (about 60 mA): 9 mV, 7.5 % of Ir. G100 feeds it from U16's via by a 0.4 mm B.Cu branch, upstream of the switcher trunk | Rev F PE-15's 25–60 kHz peaking note still applies | None |
| G-PE-14 | OK-NOTE | J1, R1, R2 | HRO drawing (2020-12-08, rev A): 5 A / 20 V; pin table. Type-C Rd 5.1 k | The footprint's pads are identical to KiCad's `Connector_USB` library (diffed). The pin map matches; SBU is open. R1/R2 are 5.1 k 1 % on each CC. A1/B12 and A12/B1 tie to the SH legs, and SH is GND on all four legs. The receptacle face is 0.34 mm inside the left edge (`board-envelope.json`) | Fine | None |

## 2. Versus the Rev F audit (`validation/datasheet-audit-rev-f/power-entry.md` and its README dispositions)

**Missed or wrong in Rev F:**
- **PE-14** said "C113 at IN and C16 at OUT per 12.1". The PE-1 fix then put R121 in C113's ground leg, which removed the low-impedance ceramic at IN, and nobody rechecked 12.1. On Rev F, C15 was about 8 mm from U16, which was marginal. G100's 24 mm move makes it about 29 mm. The hot-plug model still places C15 at U16 IN, so the model and the board disagree. See G-PE-1.
- **No output-short or interrupted-current case** was considered for U16 IN. PE-1 covered hot-plug only. See G-PE-2.
- **PE-6** rated the SRV05-4 VRWM exceedance RISK (low). The board does exceed a datasheet maximum (5.0 V against 5.5 V), so it is a VIOLATION, accepted on the functional argument. See G-PE-3.
- **PE-13** checked GPIO13 only with IOVDD up. It missed the window at plug-in when IOVDD is not yet up. See G-PE-5.
- The 0.2 mm VBUS loop under J1's shell has been on every revision since Rev F and was not flagged. See G-PE-7.

**Changed by G / G100:**
- U16, C113, R121, R110, C16, U3 and C17 moved 24 mm north. C15, D1 and J1 stayed. VBUS now reaches U16 over about 29 mm (B.Cu, 2 vias) from J1's south pins.
- The 5V trunk runs from 49.8 to 110.5 mΩ, through a single via at U16 (G-PE-6). U13 VIN min is 4.266 V.
- FB1's branch now leaves before the trunk, which is good for 5VA.
- The VB / GND test pads moved with U16 and are still on U16 IN.

**Rev F items now closed:**
- PE-3 is fixed in firmware (`usb_descriptors.c:38`, 500 mA bus-powered).
- PE-5 is fixed by U17 + C117. The plan argues that the trunk does not change the start-up result, and I agree: U16 in limit acts as a current source.
- PE-15 / FB1: the datasheet has now been retrieved, and the values are confirmed.
- PE-16: C113 is now 4.7 µF 25 V X5R (CL21A475KAQNNNE), not 1 µF. The sweep takes 0.54–1.1 of its nominal value.

**Rev F items still open:**
- PE-2 / PE-4, unconfigured draw and inrush. The 330 µF C117 raises the inrush charge to about 1.9 mC. See G-PE-4.
- PE-7, FAULT unconnected. G100 put U16 in a new strip, so the "no area" reason should be rechecked.
- PE-8, reverse-comparator resets.

## 3. Debug and bring-up features worth adding

1. **5V pad at U16 OUT / C16**, a bare 1 mm pad beside the existing VB pad (59.25, 112.9). It is a DC node, so the added capacitance does not matter.
   - VB − 5V(U16) is U16's drop: 0.46 A × 85–135 mΩ = 39–62 mV. That gives a current reading without a meter.
   - 5V(U16) − the TP at (100.5, 126.5) is the new trunk drop, 51 mV predicted.
   - Cost: none.
2. **U16 FAULT pad plus a 100 k pull-up** to USB_VBUS (or to 3V3 into a spare GPIO). It shows current-limit hiccups and reverse trips (Rev F PE-7 / PE-8).
   - Cost: 2 parts.
   - FAULT is open-drain, so there is no analog impact.
3. **0 Ω link from EN (U16.3) to IN, with a pad on the EN side.**
   - Bring-up can then hold U16 off to check the VBUS side alone.
   - It is also the hook for the PE-2 / G-PE-4 GPIO-enable fix.
   - Cost: one 0603. EN draws ≤ 0.5 µA.
4. **DNP SOD-123 TVS footprint at U16 IN** (VB node to the GND via), for G-PE-2 if the TI-model sweep confirms the overshoot.
   - Cost: area only.
5. **CC1 pad** on R1's trace. It reads the source's advertised Rp current (Default, 1.5 A or 3 A).
   - Cost: none; CC is DC.
6. **Do not add pads on ILIM** (9.5.1: keep its traces short). For D± use the R3 / R4 pads.

## 4. Parts checked and documents used

| part | document |
|---|---|
| U16 TPS2553DBVR (C55266) | TI SLVS841F (Nov 2008, rev Aug 2016), `sources/ti/TPS2553.txt`. Sections: pin table, 7.1, 7.3, 7.4, 7.5, 9.3.1–9.3.6, 9.5.1 eq. 1, 10.1.1, 10.2.1.2.3–4, 10.2.3, 11.1–11.3, 12.1 |
| R110 24 k 1 % (C23352), C113 4.7 µF 25 V X5R (C1779), R121 1.5 Ω (C22769), C15 100 nF (C14663), C16 1 µF 50 V X7R (C28323) | TPS2553 as above. Samsung CL21 family PDF https://datasheet.lcsc.com/datasheet/pdf/02336ea48ea44ca18c72517dd3cb7b47.pdf (linked, not parsed for DC-bias curves) |
| U3 AP2112K-3.3TRG1 (C51118) | Diodes DS39724 Rev 2-2 (June 2017), `sources/new/AP2112.txt`. Sections: pins, abs max, ROC, 3.3 V table, application note, SOT25 land pattern |
| C17 1 µF X7R, C18 10 µF 25 V X5R (C15850) | AP2112 as above. Samsung CL21 PDF as above |
| D1 SRV05-4 (C7420376, Zhuhai Hongjiacheng Rev 2.1) | https://datasheet.lcsc.com/datasheet/pdf/c94a8eedc13753364c00c764db36d52a.pdf, sha256 90157fa2…5f82, saved at `scratchpad/datasheet-audit-g100/pdfs/power-entry/srv05.pdf` |
| J1 TYPE-C-31-M-12 (C165948) | HRO drawing (2020-12-08, rev A): https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf, sha256 6ae33d50…1a9e (`pdfs/power-entry/hro.pdf`). Footprint `cad/LCR.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod`, pads diffed against the KiCad library |
| R1 / R2 5.1 k (C23186), R5 / R6 100 k (C25803) | RP2040 datasheet 5.5.3.1 (`sources/new/RP2040-datasheet.txt` line 46270). Type-C spec not retrieved; Rd as cited in the repo |
| FB1 GZ2012D101TF (C1015) | Sunlord spec GZ10190000 Rev 01: https://atta.szlcsc.com/upload/public/pdf/source/20250718/5DE1598387527632E7DC3776CC0B4356.pdf, sha256 6404f3d1…a5be (`pdfs/power-entry/fb1.pdf`) |
| C117 PCG1A331MCL1GS (C433208) | Nichicon PCG catalog CAT.8100H: https://datasheet.lcsc.com/datasheet/pdf/698b61208cdf22d4cecca6fb036b0f8f.pdf, sha256 63c8763e…e663 (`pdfs/power-entry/c117-pcg.pdf`) |
| 5V-net context: C80 / C82 / C83, R80, R101 / C112, R113, L1, U13 | Checked only as the trunk's endpoints. The switcher, relay and LED groups own them |
| Repo evidence | `docs/rev-g100-plan.md`, `docs/rev-f-plan.md` (2026-10-29/30 rows), `docs/rev-e-plan.md` (2026-10-21 rows), `validation/rev-g100/{regulator-check,current_check,hotplug-spice,passive-ratings-check,board-envelope}.json`, `validation/power-spurs/hotplug_spice.py`, `cad/design.json` board testpoints, `firmware-rev-e/src/usb_descriptors.c` |
