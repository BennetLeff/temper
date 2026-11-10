<!-- Intent for independent layout reviews of Rev G100: copy into each frozen export as intent/README.md. -->
# Rev G100 design intent (requirements, not results)

Rev G100 is the Rev G LCR meter board (`rev-g/temper-lcr-rev-g.kicad_pcb`, 100 × 110 mm; its design data is in
`rev-g/design-rev-g.json`) laid out again on 100 × 100 mm. The new outline is x 50–150, y 45–145.

**Same circuit as Rev G**, with these exceptions:
- J5 is removed. J5 was a DNP 2-pin header that carried only GND and 3V3 for a debugger's VTREF.
  - The debugger is meant to take those two pins from test pads TP8 (3V3) and TP9 (GND), which should sit near the buttons.
  - SWD clock and data stay on J4.
- **Added after a datasheet audit (deliberate circuit changes):**
  - **D29 (SS14):** cathode on GND, anode on −12V, at the −12 V bulk C100. +12 V comes up 30–40 ms before −12 V; D29 must keep −12V from rising more than a Schottky drop above GND. It is reverse-biased by 12 V in normal operation.
  - **TP22:** a GND test pad beside J4, for the SWD debugger's ground.
  - **C15 (100 nF, USB_VBUS to GND)** is U16's IN bypass. TPS2553 asks for it "as close to the IC as possible". TP20 (VB, a USB_VBUS test pad) is no longer at U16.
  - **Value changes on the same lands:**
    - R101 1 → 0.33 Ω, the relay coil feed: the relay RESET must still see ≥ 3.75 V at the coils at VBUS 4.40 V;
    - R132 / R133 300 → 270 Ω, so the TLP172AM LEDs get ≥ 5 mA;
    - C85 to C0G;
    - C39 / C40 / C44 / C45 / C48 / C49 1 → 2.2 µF.
- **Layout requirements added with them:**
  - each LDO's (U11, U12) GND pin 4 tied to its exposed pad on F.Cu: TPS7A49 / TPS7A30 11.1, "must be tied directly";
  - each jack TVS (D21–D24) returns to GND through two vias;
  - the 5V path leaves U16 through two vias;
  - no USB_VBUS copper under J1's grounded shell beyond the pin exits.

**What was meant to change, and only this:**
- **Parts north, as rigid blocks:**
  - the USB power entry (U16 TPS2553 with R110, C113, R121, C16) and the 3V3 LDO (U3 AP2112K with C17) move 24 mm north;
  - the TPS65131 switcher block (U13, L1 / L2, D2 / D3, its capacitors and dividers, U17 LM3880 sequencer, C116–C118) moves 10 mm north.
- **Parts re-placed:**
  - U2 (QSPI flash, GD25Q16ESIGR in SOIC-8, pin-compatible with the W25Q16JV whose datasheet is included) with C8 / C11;
  - SW1 BOOTSEL and SW2 RESET;
  - the debug LEDs D19 / R117 (HB) and D20 / R118 (FLT);
  - R1, R7, R8, R9, R13, C14, C18 and R95.
- **Copper south of about y 107 was re-routed by hand.** No autorouter or path search was used.
- **The analog core and the jack-protection band are meant to be Rev G's copper, unchanged** (signal nets). This covers everything from the BNC row back through the relays, U6 / U7, the codec and the LDO pair. The exceptions are the GND additions above (the TVS vias, the LDO pin-4 bridges) and D29 with its two vias.
- **Mounting holes:** Rev F's pattern, (54, 54), (146, 54), (54, 141) and (146, 141).

The board is a 4-layer JLC04161H-7628 stackup:
- In1 is a solid GND plane;
- In2 and B.Cu carry signals plus a GND pour;
- F.Cu is 1 oz and the inner layers are 0.5 oz.

JLC assembles all SMT; the BNCs are hand-fitted.

**Constraints the layout must meet:**
- **JLC rules:** 4-layer 1 oz (`jlcpcb-4layer-1oz.json`). Silk text at least 1.0 mm high. The fab notes on Dwgs.User promise copper to edge ≥ 0.4 mm.
- **Craft rules (hand-routed):**
  - no T-junctions;
  - lands entered along a pad axis, through its centre;
  - 45° bends.
- **Supply copper** must carry the worst-case fault current at ≤ 10 °C rise (IPC-2152):
  - USB_VBUS and 5V: 1.17 A, the TPS2553 current-limit maximum. J1's VBUS pins count as one node, because a plug's VBUS contacts are tied inside it. The north pair's 0.2 mm exit (4.3 mm, in a 0.52 mm corridor) would exceed 10 °C only if a plug touched that pair alone, which is a double fault. This is an accepted deviation (FINDINGS G-PE-8);
  - RAW_P / 12V / RAW_N / −12V and LDOIN_P / LDOIN_N: 0.5 A;
  - 3V3, 3V3A and 5VA: 0.6 A.
- **USB hot-plug:** U16 IN must stay under the 6.5 V recommended maximum when plugged into a live USB-A port. C113's ground leg runs through R121, 1.5 Ω. The copper between J1 and U16 adds to the cable inductance.
- **USB D+ / D−:** Full-Speed rules are short-line and skew < 100 ps. The RP2040 USB pins go through R3 / R4.
- **QSPI flash:** keep the clock and data short, with the CLK series resistor R13 at the U1 end. U2 VCC needs its 100 nF (C11) at the pin.
- **The TPS65131 switcher** is the board's main magnetic aggressor (1.25–1.5 MHz; L1 / L2 and the switch loops). The TIA around U7 and the codec inputs are the victims. Distance matters.
- **M3 mounting holes:** no non-GND copper within 3.5 mm of a hole centre on B.Cu (metal standoffs; GND pour there is fine).
- **User access:** SW1 / SW2 must be pressable from above with the lid off. The debug LEDs must be visible.
- **Every reference designator** is on silk where it fits, and always on the assembly drawing (F.Fab).
- **Firmware:** `intent/pins.h` and `intent/jackguard.h` (built with `LCR_REV_G=1`); the GPIO map is unchanged from Rev G.
- **Earlier reviews are in `prior/`** (in an export). Do your own pass first and write it down. Only then read `prior/`, and add a separate section: what they missed, what they got wrong, and which dispositions you disagree with.
