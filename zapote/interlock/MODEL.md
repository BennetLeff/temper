# Interlock model and evidence boundaries

The source uses two SN74LVC14A Schmitt inverter packages, a CD74HC30 eight-input NAND, an SN74LVC1G74 flip-flop, an SN74LVC1G08 AND and a TPS3823 supervisor. Seven inverted fault signals and the combined SENSOR_LIVE / watchdog-good signal feed the NAND. Inverting its output produces ALL_GOOD, which directly drives the flip-flop's asynchronous clear. D and preset are tied high. An inverted RESET_N creates the positive clock edge.

For a stable, powered circuit outside timing exclusion windows:

```
ALL_GOOD = no asserted faults AND SENSOR_LIVE AND WDT_RESET_N
Q_next = 0                       if ALL_GOOD = 0
         1                       if ALL_GOOD = 1 and fresh reset edge
         Q_previous              otherwise
PERMIT = Q; LATCHED_FAULT = NOT Q
```

The distinction between Q state and a reset pulse matters: PERMIT must remain high after the pulse ends. Fault removal releases clear but does not clock the latch. A held reset input therefore cannot restart it after a fault. The supervisor's startup reset establishes the initial disabled state; the flip-flop alone has no guaranteed power-up state.

## Manufacturer grounding

- [TI SN74LVC1G74](https://www.ti.com/lit/ds/symlink/sn74lvc1g74.pdf): DCU pin map CLK1, D2, QBAR3, GND4, Q5, CLR_N6, PRE_N7, VCC8. Q and QBAR must not be interchanged. The functional table supplies asynchronous clear and positive-edge behavior.
- [TI TPS3823](https://www.ti.com/lit/ds/symlink/tps3823.pdf): DBV RESET_N1, GND2, MR_N3, WDI4, VDD5. WDI high impedance can disable the watchdog; TI recommends 1 kΩ WDI-to-ground to prevent that. The selected device's watchdog timeout is 0.9–2.5 s (1.6 s typical), and reset delay is 120–300 ms (200 ms typical).
- [TI SN74LVC14A](https://www.ti.com/lit/ds/symlink/sn74lvc14a.pdf): Schmitt input pairs are 1→2, 3→4, 5→6, 9→8, 11→10, 13→12. GND7 and VCC14. The unused sixth control input is grounded and its output is intentionally unconnected.
- [TI CD74HC30](https://www.ti.com/lit/ds/symlink/cd74hc30.pdf): A1/B2/C3/D4/E5/F6/G11/H12; Y8/GND7/VCC14. Pins 9, 10 and 13 are NC. The HC device uses CMOS input thresholds; do not apply its 2 V supply threshold row directly to a 3.3 V circuit.
- [TI SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf): A1/B2/GND3/Y4/VCC5.

At the contract's lowest supply, a 10 kΩ +1% fault pullup with 20 µA downward leakage gives 3.135 − 10100×0.000020 = 2.933 V. This exceeds the LVC14A's 2.0 V maximum positive Schmitt threshold in the relevant supply range. It is a conditional open-conductor margin, not evidence for arbitrary cable capacitance, contamination, remote clamp current or power sequencing.

The Rust model must resolve actual source pin nets before evaluating gate behavior; an independently hardcoded truth function agreeing with its own tests is insufficient. Source/native parity then proves that the board implements that evaluated graph. Separate mutation tests must break reset retention, polarity, clear routing, pull values and disconnected native clusters.

## Still outside the model

Propagation delays, simultaneous clock/clear recovery or removal violations, metastability, brownout ramps, transient immunity, component failures, real watchdog timing and downstream gate shutdown need qualification. A combinational truth table does not measure nanosecond fault latency or watchdog elapsed time. Full qualification therefore remains INDETERMINATE even when the conditional digital construction checks pass.

TPS3823 rail supervision does not implement the original cooker's separate UVL-02 thresholds. That protection needs a dedicated producer through AUX or a later explicitly reviewed integration design. The SENSOR_LIVE producer is also an outstanding integration obligation.

The shared legacy `elec/src/components.ato` TPS3823 definition reverses RESET/GND. This standalone source uses a verified local definition; it does not silently certify or modify the legacy full-board design. Reconciliation of that donor belongs in a separately validated change.

## Board profile

Rev A uses two copper layers, 1.6 mm total thickness, 0.20 mm signal tracks, 0.60/0.30 mm vias and a 0.15 mm minimum copper clearance. The original VSSOP-8 flip-flop footprint has 0.15 mm adjacent-pad gaps; the initial generic 0.20 mm floor conflicted with that selected package. The final profile explicitly accepts 0.15 mm for this low-voltage unit and preserves the original land pattern. This is a fabrication requirement to confirm with the eventual supplier, not an insulation rating or a waiver for shorts. Ground is poured on both sides and filled by KiCad. Bypass pad-centre distances are below 3 mm; this does not measure supply-loop impedance.
