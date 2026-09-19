# Candidate connection and spacing graph

This is a design sketch for the next unit. It is deliberately not a netlist
or a release waiver.

| Function | Candidate | Domain / connection | Evidence or open question |
| --- | --- | --- | --- |
| Low-side SR controller | Infineon IR11688S | VCC/logic on the bias domain; `VD1`/`VD2` sense Q3/Q4 VDS through the reference filter and T1/T2 extension; `Gate1`/`Gate2` to Q3/Q4 | Infineon active-bridge appnote pp. 6--9, 17; bare controller drain-sense limit is 200 V, so the 800 V extension is mandatory for this use |
| Sense extension | BSP300H6327XUSA1 ×2 | Each device couples a line-domain sense node to an IR11688S input through the reference resistor/capacitor network | Reference BOM p. 19; exact device sourcing and SOA at this use are open |
| High-side driver | TI UCC21530DWKR | `VSSA` = Q1 source / L-side floating domain; `VSSB` = Q2 source / N-side floating domain; `OUTA`→Q1 gate, `OUTB`→Q2 gate; VCCI = logic domain | TI datasheet pp. 1--6, 18, 33--35; direct pin mapping is not claimed |
| High-side bias | Two isolated or otherwise valid floating supplies | VDDA–VSSA and VDDB–VSSB each within the selected UCC21530DWKR 12 V-UVLO range (13.5–25 V); local bypass at each channel | TI recommends local VDD bypass and a short bootstrap loop where bootstrap is used (datasheet p. 33). A single 12 V rail is below the selected variant's guaranteed turn-on range and cannot be assumed to serve both floating domains |
| Active bridge switches | IPW60R017C7 ×4 (current candidate) or a future 600 V device | Q1/Q2 high side; Q3/Q4 low side; two devices conduct in each line half-cycle | Current board source/native identity; hot RDS(on), package isolation and surge survival remain open |
| Passive surge path | Existing passive bridge retained in parallel | AC input to rectified bus path, independent of active gate state | Infineon appnote p. 15 explicitly retains a diode bridge for surge protection |
| PFC interface | Existing UCC28180 boost stage | Active bridge V+ / V− feed the existing F2 / bus / boost path; no controller replacement in this experiment | Project source and current board; verify U20 diode-side sensing and F2 fault behavior again after any topology change |

## Timing and state requirements

The line bridge is a 50/60 Hz synchronous rectifier. Positive half-cycle
conduction is Q1+Q4; negative half-cycle conduction is Q2+Q3, matching the
Infineon reference's control description (appnote p. 6). The design must retain
the reference's turn-on blanking, minimum-on-time, regulation and reset
behavior (pp. 8--10), and separately prove that the UCC21530 path does not
turn on both high-side domains or overlap an incompatible low-side command.

The fault contract must distinguish healthy switch shutdown from failed-short
MOSFETs. The UCC21530 disable/UVLO behavior can force outputs low, but it cannot
interrupt a MOSFET that has failed short. F2 and the retained passive bridge
therefore remain in the fault review; no gate-driver feature is credited as a
failed-short interrupter.

## Spacing matrix

| Path | Candidate datum | Construction decision |
| --- | --- | --- |
| UCC21530 input-to-output | >8 mm external clearance and >8 mm creepage; 5.7 kVrms reinforced isolation | Preserve package-side distance and keep PCB copper/cutouts from reducing it; verify against the selected appliance standard |
| UCC21530 output A ↔ output B | 1850 V internal output-to-output isolation; 3.3 mm channel spacing in DWK | Treat L and N high-side output domains as separate HOT domains on the PCB; do not merge their pads or routes just because both are “high side” |
| UCC21530 logic ↔ any HOT copper | Input/output reinforced barrier | Place a board keepout/cutout under and around the package as recommended on datasheet pp. 33--35; exact creepage is a board requirement |
| IR11688S sense network ↔ line | 200 V native sense capability, extended by T1/T2 in reference | Retain and re-derive the extension; no direct line connection to the bare controller |
| MOSFET drain/tab/heatsink | 600 V devices, TO-247-3 current candidate | Treat tabs as electrically live and provide an engineered isolated heatsink; this is a mechanical/thermal gate, not a DRC-only spacing check |

The UCC21530 datasheet is stronger evidence than the TEA SO16 package for the
controller-to-controller spacing question, but it does not establish the
complete PCB insulation path or the product compliance route.

## First-order conduction screen

At the maintained 120 Vac, 15 A RMS operating point, two MOSFETs conduct in
series. The illustrative channel-loss screen is:

`P_channel ≈ 2 × I_RMS² × RDS(on)`

| Per-device RDS(on) used | Two-device channel loss | Compared with 28.304 W constant-drop bridge screen |
| ---: | ---: | ---: |
| 17 mΩ (current candidate nominal screen) | 7.65 W | 20.65 W lower |
| 22 mΩ (Infineon reference device) | 9.90 W | 18.40 W lower |
| 30 mΩ (hot sensitivity only) | 13.50 W | 14.80 W lower |

These are algebraic screens, not qualified losses. They omit the bridge body
diode interval, switching/overlap at commutation, gate-driver bias, reverse
recovery, surge current, hot RDS(on) guarantees and thermal spreading. The
device comparison remains useful because it says the architecture has a large
nominal conduction lever, while leaving the same unknowns that blocked the
TEA route from being silently converted into a pass.
