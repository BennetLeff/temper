# Rev E: firmware-controlled range switching (study, 2026-10-20)

**Recommendation.** Replace JP1–JP6 with three Panasonic **TQ2SA-L2-5V-Z** dual-coil latching DPDT signal relays (LCSC C2684450, JLC extended, 1,756 in stock, $2.27). Each relay switches one matched pair: pole 1 connects SOURCE_BUF to the range's RG node, and pole 2 connects TIA_OUT to the range's RF node. Each relay sits exactly where its two jumpers are now. Drive the coils low-side with basic AO3400A + 1N4148WS. That takes four GPIOs: one shared RESET and three SETs. C104 stays local and unswitched between TIA_SUM and TIA_OUT. Firmware selects the 100 kΩ range at boot.

Analog switches are rejected on two grounds. Their on-capacitance (77–148 pF) loads the TIA output, and the OPA2810 is specified for 35 pF. Their 2–4 Ω Ron, which drifts with temperature, adds 1.7–3 % to the 100 Ω range.

Nothing here is simulated yet. The SPICE cases that qualify the topology are listed in §6.

All values are from the vendor excerpts in `sources/rev-e/` unless marked **UNVERIFIED**. "Figure" values were read by eye from the rendered datasheet page and are noted at the end of the corresponding excerpt. JLC stock, price and library type come from `sources/rev-e/JLC-stock-range-switching-2026-10-20.txt`, which is JLC's parts API on 2026-10-20 at the first price break.

## 1. Nets today (`cad/design.json`)

| Part | Pins → nets |
|---|---|
| JP1 / JP2 / JP3 | SOURCE_BUF ↔ RG100 / RG5K / RG100K |
| R40 / R41 / R42 (100 Ω / 5 kΩ / 100 kΩ, 0.1 %) | RG100 / RG5K / RG100K → DUT_HI |
| JP4 / JP5 / JP6 | TIA_OUT ↔ RF100 / RF5K / RF100K |
| R43 / R44 / R45 | TIA_SUM ↔ RF100 / RF5K / RF100K |
| C104 100 pF C0G | TIA_SUM ↔ TIA_OUT (one capacitor for all ranges, not switched) |
| R94 22 Ω | DUT_LO ↔ TIA_SUM |
| U6A (OPA2810) | follower; output SOURCE_BUF |
| U7A (OPA2810) | TIA: −IN TIA_SUM, output TIA_OUT |
| R67 1 kΩ | TIA_OUT → B_INM (ADC channel B = LOW_BUF − TIA_OUT) |

The jumpers already sit on the low-impedance side: SOURCE_BUF on the source, TIA_OUT on the feedback. A relay contact placed in the same position keeps all contact parasitics off TIA_SUM. C104, which sets the TIA's high-frequency feedback, does not pass through any contact.

## 2. Candidate survey

### 2.1 Relays (all JLC extended; none is Basic or Preferred)

Open-contact capacitance is not given directly by any vendor; they give isolation (dB) at RF. I convert with C = |H| / (2π f · 50 Ω), which is the conservative reading. A network-analyser S21 basis (2·Z0 = 100 Ω) gives half these values. A 20 dB/decade slope in the vendor curve confirms a capacitive feedthrough. Contact-to-coil and pole-to-pole capacitances are not published for any of these parts (**UNVERIFIED**; §6 sweeps them).

| Part (LCSC) | Contact R | C_open (derived) | Insulation | Coil (5 V) | Latching | Mech. life | Package | Stock / price |
|---|---|---|---|---|---|---|---|---|
| **Panasonic TQ2SA-L2-5V-Z** (C2684450) | 75 mΩ max initial (6 V 1 A); figure: 28–38 mΩ, 30–48 mΩ over 10⁵ ops | ≈0.28 pF (fig. 11-(1): 61 dB @ 10 MHz, 41 dB @ 100 MHz) | ≥1,000 MΩ | 2 coils, 178 Ω, 28.1 mA, 140 mW per pulse; set/reset ≤3.75 V | yes, dual coil | 10⁸ | SMD 14 × 9 mm | 1,756 / $2.27 |
| Panasonic TQ2SA-5V-Z (C22686) | as above | as above | ≥1,000 MΩ | 178 Ω, 140 mW continuous | no | 10⁸ | 14 × 9 mm | 4,491 / $1.59 |
| **Omron G6K-2F-Y-TR DC5** (C47190; C2982926 is the same relay) | 100 mΩ max (10 mA 1 V); figure: 40–60 mΩ over life at 10 µA/10 mV | ≈0.16 pF (p.5: 86 dB @ 1 MHz, 46 dB @ 100 MHz) | ≥1,000 MΩ | 237 Ω, 21.1 mA, ≈100 mW continuous | no | 5 × 10⁷ | SMD 10 × 6.5 mm | 61,851 / $1.05 |
| Omron G6KU-2F-Y-TR DC5 (C2153173) | as G6K | as G6K | ≥1,000 MΩ | single winding, 237 Ω, ≈100 mW pulse, ≥10 ms; needs polarity reversal | yes, 1 coil | 5 × 10⁷ | 10 × 6.5 mm | 4,801 / $1.59 |
| Hongfa HFD4/5-SR (C64399) | 100 mΩ max (10 mA 30 mV) | ≈0.23 pF (43 dB typ @ 100 MHz, text) | ≥1,000 MΩ | 178 Ω, 140 mW | no (latching HFD4/4.5-LSR C2976892: single coil, 4.5 V, 2,256 stock) | 10⁸ | 10 × 6.5 mm | 41,727 / $1.45 |
| Fujitsu FTR-B3GA4.5Z-B10 (C126744) | 75 mΩ max (1 A 6 V) | not given | ≥1,000 MΩ | 4.5 V coil, 140 mW | no | 5 × 10⁷ | 10.6 × 7.2 mm | 3,516 / $1.27 |
| KEMET UD2-5NU-L8 (C1560626) | 100 mΩ max | not given | 1,000 MΩ | ≤140 mW | no | 5 × 10⁷ (10⁷ latch type) | 6.5 × 10.6 mm | 2,549 / $1.45 |
| KEMET EE2-5TNUH-L (C2653958) | not extracted | not given | not extracted | dual coil | yes, dual coil | not extracted | 15 × 7.5 mm | 324 / $2.83 |
| Panasonic AGQ200A4HZ (C490150) | 100 mΩ max | not given | not extracted | 4.5 V, 140 mW | no | 5 × 10⁷ | 10.6 × 7.2 mm | 24,068 / $1.27 |
| Omron G6J-2FS-Y-TR DC5 (C308989) | 100 mΩ max | figure not read | ≥1,000 MΩ | 140 mW | G6JU variant: 44 stock | 5 × 10⁷ | 10.6 × 5.7 mm | 787 / $1.26 |
| Coto / Standex reed relays | **UNVERIFIED**; the only JLC rows have no stock (e.g. SIP-1A05) | — | — | — | — | — | THT, hand-fit | not orderable at JLC |

Citations: `sources/rev-e/TQ2SA.txt` (spec table lines 30–66; types 145–166; figure notes at end), `G6K.txt` (ratings 140–232; the long-term-ON note quoted in §4.2; figure notes at end), `HFD4.txt` (contact data, coil data, HF table lines 30, 84, 112–154), `FTR-B3.txt`, `UD2.txt`, `AGQ.txt`, `G6J.txt`. EE2 data was not extracted; only JLC listing attributes were used.

### 2.2 Analog switches (supply ±15 V tables; each runs from ±12 V, and every listed part tolerates ≥30 V total)

C_off-feedthrough is derived from the off-isolation figure the same way: RL = 50 Ω, f as stated, C = |H| / (2π f · 50 Ω).

| Part (LCSC) | Ron typ/max 25 °C | Flatness | Ron drift | CS(off) / CD(off) / C(on) | Off-iso → C | Q_inj | Leakage IS(off) 25 °C | Supply | Stock / price |
|---|---|---|---|---|---|---|---|---|---|
| TI TMUX7219 SPDT (C2862901) | 2.1 / 2.9 Ω | 0.5 / 0.6 Ω | 0.01 Ω/°C | 33 / 48 / 148 pF | −75 dB @ 100 kHz → 5.7 pF | −10 pC | ±0.15 nA | ±4.5–±22 V (48 V abs) | 799 / $3.92 |
| TI TMUX7234 4×SPDT (C19184441) | 3.6 / 5.5 Ω | 0.4 / 1.5 Ω | 0.015 Ω/°C | 16 / 28 / 77 pF | −82 dB @ 100 kHz → 2.5 pF | 3 pC | ±0.4 nA | ±4.5–±22 V | 2,014 / $6.53 |
| TI TMUX7211 4×SPST (C3657378) | 2.0 / 2.7 Ω | 0.2 / 0.46 Ω | 0.008 Ω/°C | 28 / 45 / 145 pF | −70 dB @ 100 kHz → 10 pF | 60 pC | ±0.25 nA | ±4.5–±22 V | 1,890 / $4.71 |
| TI TMUX6209 diff 4:1 (C3658008) | 4 / 5.9 Ω | 0.4 / 1.5 Ω | 0.02 Ω/°C | 15 / 68 / 115 pF | −82 dB @ 100 kHz → 2.5 pF | 3 pC | ±0.4 nA | ±4.5–±18 V (38 V abs) | 266 / $6.60 |
| TI TMUX6111 4×SPST (C2673386) | 120 / 135 Ω | 23 / 33 Ω | 0.52 %/°C | 1.9 / 2.4 / 4.2 pF | −85 dB @ 1 MHz → 0.18 pF | 0.6 pC | 0.05 nA typ | ±5–±17 V | 192 / $5.12 |
| ADI ADG1419 SPDT (C22368) | 2.1 / 2.4 Ω | 0.4 / 0.5 Ω | — | 19 / 44 / 114 pF | −64 dB @ 1 MHz → 2.0 pF | −16 pC | ±0.5 nA | ±4.5–±16.5 V | 2,487 / $11.62 |
| ADI ADG1209 diff 4:1 (C654763) | 120 Ω typ | 20 Ω | — | 1 / 3.5 / 5 pF | −85 dB @ 1 MHz → 0.18 pF | 0.4 pC | 0.003 nA typ | ±5–±16.5 V | 939 / $10.52 |
| ADI ADG1401 SPST (C209446) | 1 Ω typ | 0.2 Ω | — | 36 / 41 / 187 pF | −58 dB @ 1 MHz → 4.0 pF | −12 pC | 0.05 nA typ | ±4.5–±16.5 V | 2,148 / $5.90 |
| ADI ADG1436 2×SPDT (C655227) | 1.5 Ω typ | 0.28 Ω | — | 23 / 50 / 120 pF | −80 dB @ 100 kHz → 3.2 pF | −20 pC | 0.04 nA typ | ±4.5–±16.5 V | 1,432 / $8.19 |
| ADI ADG5419 SPDT (C209440) | 13.5 / 15 Ω | 1.8 / 2.2 Ω | — | 12 / — / 55 pF | −60 dB @ 1 MHz → 3.2 pF | 130 pC | ±0.25 nA | ±9–±22 V | 7 / $8.68 |
| ADI ADG5436 2×SPDT (C657525) | 10 Ω typ | 0.6 Ω | — | 12 / 24 / 37 pF | −71 dB @ 1 MHz → 0.9 pF | −724 pC | 0.1 nA typ | ±5 V min | 3 / $19.43 |
| Maxim MAX14778 dual 4:1, ±25 V signal, 3–5.5 V supply (C1121866) | 0.84 / 1.5 Ω | 3 mΩ | — | C_IN 78 pF | −80 dB @ 100 kHz → 3.2 pF | 1,720 pC | ±200 nA (off) | 3–5.5 V, internal charge pump | 2,771 / $5.99 |
| Vishay DG419 SPDT (C6581) | 20 / 35 Ω | — | — | 8 / 8 / 35 pF | not extracted | 60 pC | ±0.25 nA | ±15 V | 2,764 / $1.98 |
| Vishay DG469 SPDT (C222452) | 3.6 / 6 Ω | 0.4 / 0.5 Ω | — | 37 / 85 / 125 pF | −57 dB @ 1 MHz → 4.5 pF | 58 pC | ±0.5 nA | ±15 V | 2,444 / $1.96 |
| Panasonic PhotoMOS AQY221N5V (C2982229) | 2.8 / 4.5 Ω | — | **UNVERIFIED** | C_out 1.1 / 1.5 pF; I/O 0.8 pF | — | — | 10 nA max | LED 5 mA continuous; 20 V load | 3,060 / $4.59 |

Citations: `sources/rev-e/<PART>.txt` (±15 V electrical-characteristics block; TI capacitance rows are in the same excerpt). The earlier rejects carry forward: TMUX6209 (above), and CD4052B at 20 V absolute maximum (`docs/rev-d-audit.md` §7, not re-verified here).

### 2.3 Why switches lose here

The family trades Ron against capacitance.

- **Low-Ron parts (1–4 Ω).** On-capacitance is 77–187 pF. In series between TIA_OUT and RF, that capacitance hangs on TIA_OUT behind only Ron. The OPA2810 is specified for "Capacitive load drive < 1 dB peaking, RS = 0 Ω: 35 pF" (`sources/ti/OPA2810.txt` line 406). The board already has 10.5 pF there. Ron is also 1.7–4.8 % of the 122 Ω low-range feedback. With 0.008–0.02 Ω/°C drift, that is 66–160 ppm/°C between calibration and use, before flatness (0.2–1.5 Ω over ±10 V) adds a signal-dependent term. Each unselected branch also adds 2.5–10 pF of off-feedthrough across the feedback. On the 100 kΩ range at 60 kHz, that is 11 % of the feedback admittance for TMUX7219 (§4).
- **Low-capacitance parts (TMUX6111, ADG1209: 1–5 pF).** Ron is 120–200 Ω, larger than the 100 Ω range's RF.
- **MAX14778.** It runs an internal charge pump next to the summing node and leaks up to ±200 nA.
- **PhotoMOS (AQY221N5V).** It is the only electronic option with relay-like capacitance (1.1 pF). It still puts 2.8–4.5 Ω of MOSFET Ron, whose temperature coefficient is unpublished, in the 100 Ω feedback, and it needs 5 mA of LED current per closed path. It would require Kelvin sensing (§3.3) to be usable, at $27 per board for six parts.

Relays give 28–60 mΩ contacts, 0.16–0.28 pF open capacitance and ≥1,000 MΩ insulation, for $1–2.3 each.

## 3. Recommended topology

### 3.1 Contacts (one relay per range, both poles move together)

| Relay | Pole 1 (source) | Pole 2 (feedback) | Replaces |
|---|---|---|---|
| K1, Low | COM = SOURCE_BUF, NO = RG100 | COM = TIA_OUT, NO = RF100 | JP1 + JP4 |
| K2, Medium | COM = SOURCE_BUF, NO = RG5K | COM = TIA_OUT, NO = RF5K | JP2 + JP5 |
| K3, High | COM = SOURCE_BUF, NO = RG100K | COM = TIA_OUT, NO = RF100K | JP3 + JP6 |

NC contacts stay unconnected: pad only, no copper. Grounding an NC would short SOURCE_BUF or TIA_OUT to ground on every reset relay.

The commons (armatures) go on the low-impedance driven nets. The larger armature capacitances, to the coil and to the other pole's armature, then land on SOURCE_BUF and TIA_OUT rather than on the high-impedance RGx/RFx nodes. The relay's internal geometry is **UNVERIFIED**, so check this against the footprint.

Because both poles of one relay move together, the source and feedback selections can never mismatch, unless a single pole fails. §5 covers that case.

The switch sits on the TIA_OUT side of RF, as the jumpers do now. An unselected branch then appears as R_unsel in series with C_open, connected from TIA_SUM to TIA_OUT, which only adds to the feedback capacitance. On the TIA_SUM side, the contact stub, the open-contact pad and the contact-to-coil capacitance would sit directly on the summing node.

### 3.2 Drive, GPIOs, default state

- **Coils.** Each relay has a SET coil and a RESET coil (TQ2SA-L2: 178 Ω, 28.1 mA at 5 V; set/reset voltage ≤3.75 V; `TQ2SA.txt` line 156).
- **SET drivers.** Each SET coil gets its own AO3400A low-side switch (C20917, basic), driven by RNG_SET_LO, RNG_SET_MED or RNG_SET_HI.
- **RESET driver.** The three RESET coils go in parallel on one AO3400A, driven by RNG_RESET.
- **Flyback.** One 1N4148WS (C2128, basic) across each coil, six in total.
- **Gates.** 100 kΩ gate pull-down and about 100 Ω series gate resistor on each MOSFET. RP2040 pads also reset with pull-down enabled (`sources/new/RP2040-datasheet.txt` line 22732, PDE reset 0x1).
- **GPIOs.** Four in total. Any four of 0, 1, 14–20, 22–24 work; choose them by routing, keeping the lines away from TIA_SUM.
- **Coil supply.** Use the digital 5 V, not 5VA, through about 2.2 Ω and 22 µF placed at the relays. This filters supply ripple off the coil nodes, which couple into the RF nodes through contact-to-coil capacitance. The worst pulse (three RESET coils, 84 mA) drops about 0.18 V, so the coil still sees ≥4.5 V at the 4.75 V supply minimum.
- **Coil drive voltage.** Panasonic recommends the 4.5 V coil "in case of 5 V transistor drive" (note 3, line 166). That note covers a saturated BJT's drop. An AO3400A drops millivolts at 28 mA, so the 5 V coil is correct.
- **Firmware sequence.** Source off (as for the existing source-off record), RESET pulse 20 ms, SET_k pulse 20 ms, wait 10 ms, source on, existing settle.
  - Panasonic gives set/reset time ≤4 ms. Omron gives a 10 ms minimum pulse for its latching relay. The TQ2SA-L2 minimum pulse width is not given (**UNVERIFIED**), so use 20 ms.
  - The TIA has no DC feedback for about 20 ms. With C104 still in place and OPA2810 bias ≤60 pA (`OPA2810.txt` line 365), it drifts at most 60 pA / 100 pF × 20 ms = 12 mV, so it does not saturate.
  - Contacts always switch dry: source off, nodes near 0 V.
- **Power-up.** The relays keep their last state through power-off, so firmware must not assume a state. At boot, firmware sends RESET then SET_HI to select the 100 kΩ range. That limits DUT current to ≤18 µA peak into a short and keeps TIA_OUT in range for any DUT.
- **Static power.** None. Coil current flows only during the 40 ms switching event. There is no coil heat near R43–R45 or C104 between calibration and use.

### 3.3 Kelvin sensing: not needed with relays

With channel B at TIA_OUT, the selected contact sits in series with RF. A Kelvin arrangement would take channel B from the RF node through a second contact, so the contact is driven inside the loop but not measured. That needs three more poles. §5 shows the contact error is ≤164 ppm and purely a gain error, so Kelvin sensing would buy nothing. It only becomes necessary for a switch with an ohm-level Ron, such as PhotoMOS or CMOS.

### 3.4 Readback

Latching relays have no spare pole for electrical state readback. Rev D decision 4b expected readback from relay ranging, so this needs a substitute. Wiring the NC contacts to a GPIO would bring a digital line onto SOURCE_BUF and TIA_OUT.

Use a measurement self-check instead. From the existing channels:

- A = V_HI − V_LO and B = I·Z_f, with Z_f = 22 Ω + RF‖C104.
- V_SOURCE_BUF = A + B·RG/Z_f, whatever the DUT.

Run the check at 1.5 kHz, where |Z_f| on the 100 kΩ range is within 0.5 % of RF. Firmware or the host compares A + B·RG/Z_f, computed with the commanded range's nominal RG and Z_f, against the source amplitude. Calibrate that amplitude once per board.

- A wrong range, a failed pole or no closure gives an error of 50× or more, so a 10 % window is ample.
- Two relays closed at once (a weld) keeps RG ≈ RF and passes the identity. That fault shows as a 0.1 % gain shift on calibration verification.

## 4. Leakage of unselected paths (worst case: 100 kΩ selected; 100 Ω and 5 kΩ branches open)

Each open feedback branch is R_unsel in series with C_open, from TIA_SUM to TIA_OUT. Below 100 kHz, 1/(ωC_open) ≥ 5 MΩ, which dwarfs R_unsel. The branch therefore acts as a plain capacitor in parallel with C104. The feedback admittance is |Y_f| = |1/100 kΩ + jω·100 pF|: 1.00 × 10⁻⁵ S at 1.5 kHz, 3.90 × 10⁻⁵ S at 60 kHz and 6.36 × 10⁻⁵ S at 100 kHz.

| C_open per branch | 1.5 kHz | 60 kHz | 100 kHz | Effective C104 |
|---|---|---|---|---|
| G6K 0.16 pF (both branches) | 0.03 % | 0.31 % | 0.32 % | 100.32 pF |
| TQ2SA 0.28 pF (both) | 0.05 % | 0.54 % | 0.55 % | 100.56 pF |
| 2 pF stress incl. pads (both, **UNVERIFIED** pad value) | 0.38 % | 3.9 % | 4.0 % | 104 pF |
| TMUX7219 5.7 pF, for comparison | 1.1 % | 11 % | 11 % | 111 pF |

Values are the leakage admittance as a fraction of |Y_f|.

- **Linear and calibrated.** All of this is LTI and is removed by the per-frequency three-standard calibration. What remains is drift: ±10 % in C_open (**UNVERIFIED**; relay geometry is mechanically fixed) leaves ≤0.06 % with TQ2SA.
- **5 kΩ range.** Selected with the 100 Ω and 100 kΩ branches open, it sees 0.10 % (60 kHz) and 0.17 % (100 kHz).
- **DC leakage.** Insulation ≥1,000 MΩ against RF = 100 kΩ is ≤0.01 %, real and also calibrated.
- **Source side.** Unselected RG branches leak in parallel with the selected RG. That changes only the source impedance, which the ratiometric A/B measurement does not use.
- **Pole-to-pole coupling.** In an unselected relay, coupling from SOURCE_BUF (pole 1) to RFx (pole 2) injects V_SOURCE_BUF·jωC_pp into TIA_SUM through R_unsel. It acts like a HI–LO stray. C_pp is not published (**UNVERIFIED**). At 0.5 pF it equals 5.3 MΩ at 60 kHz and 3.2 MΩ at 100 kHz. That is about 1.9 % / 3.1 % of the signal current for a 100 kΩ DUT on the 100 kΩ range. Open calibration removes it, and it is the same order as the existing board HI–LO coupling (0.158 pF, `Cbhisum`).
- **Coil coupling.** Contact-to-coil capacitance on an unselected RF node shunts TIA_SUM to the coil rail through R_unsel. It is not a feedback leak. Its cost is stability (§6) and coupling of coil-rail ripple, hence the 2.2 Ω / 22 µF filter.

## 5. Contact resistance on the 100 Ω range

Z_f(low) = 22 Ω + (100 Ω + R_c)‖C104. The contact also sits in the RG path, where it does not matter (§4).

R_c is about 28–48 mΩ (TQ2SA figures) and ≤75 mΩ initial (spec). Calibration absorbs the nominal value. What matters is the change between calibration and use. Neither vendor gives per-closure repeatability (**UNVERIFIED**). The published spreads bound it: about 18 mΩ across 120 contacts and 10⁵ operations for TQ2SA, and about 20 mΩ over life for G6K.

| ΔR_c | |ΔZ_f|/Z_f | Phase change at 60 kHz / 100 kHz |
|---|---|---|
| 20 mΩ | 164 ppm | 0.7 / 1.2 µrad |
| 25 mΩ | 205 ppm | 0.9 / 1.5 µrad |
| 100 mΩ (full max, never expected) | 820 ppm | 3.6 / 6.1 µrad |

This is a pure gain error. It scales |Z|, L and R together and leaves tan δ unchanged:

- On a 5–30 Ω coil, ≤205 ppm moves L by ≤0.02 % and a 50 mΩ R_ac by ≤10 µΩ.
- The 1 µrad phase term shifts a 30 Ω coil's R by about 30 µΩ.
- Compare the existing bench rule: the 20 Ω/100 Ω standard ratio must be known to 0.03 % (300 ppm).
- Contact TCR (metal, about 0.4 %/K, **UNVERIFIED**) gives about 0.16 mΩ/K, or 1.3 ppm/K: negligible.

Thermal EMF is irrelevant at AC.

For comparison, TMUX7219 Ron is 2.1 Ω, a 1.7 % offset, and its 0.01 Ω/°C drift is 82 ppm/°C.

## 6. SPICE qualification cases (`validation/stability-full-chain/`)

Add a mode `fixedrelay` to `loop_matrix.rs` and run it via `run.sh` as `final_fixedrelay`.

**Base.** Clone the `fixedextracted` `_revd_risolo22` cases:

- Board string `Cbj3 low 0 5.666p … Cbtiao tia 0 10.53p`.
- DUTs open, short and matched, plus coil50u on r100.
- Strays 0/100/220/470/1000 pF (r100) and 0/1000 pF (r5k, r100k).
- `caplead` 4.87 and 10 nH.
- RF lead 21.65 / 50.46 / 33.14 nH.
- `riso` 4.32 (the FDA value, unchanged).

**Template nodes.** `source` = SOURCE_BUF (X6A output), `hi` = DUT_HI, `low` = DUT_LO, `sum` = TIA_SUM, `tia` = TIA_OUT.

**Additions per case.** All of these are appended to the `dut` string, as `fixedextracted` already does for the board parasitics:

| Element | SPICE lines (k = each unselected range, R_k its value) | Nominal | Stress | Basis |
|---|---|---|---|---|
| Selected contact R | set `Case.r = R + Rc` (it applies to both RG and RF, each of which carries one contact) | 0.075 Ω | 0.075 Ω | TQ2SA max |
| Selected contact inductance | add to the `_lead` value: `lead = extracted + L_rel` | +10 nH | +20 nH | **UNVERIFIED** |
| Unselected feedback branch | `Ru{k} sum ru{k} {R_k}` / `Cocf{k} ru{k} tia {Coc}` / `Ccf{k} ru{k} 0 {Ccc}` | Coc 0.3 pF, Ccc 1 pF | Coc 2 pF, Ccc 5 pF | Coc: fig. 11-(1); Ccc **UNVERIFIED** |
| Unselected source branch | `Rgu{k} hi rgu{k} {R_k}` / `Cocs{k} rgu{k} source {Coc}` / `Ccs{k} rgu{k} 0 {Ccc}` | as above | as above | same |
| Unselected pole-to-pole | `Cpp{k} source ru{k} {Cpp}` / `Cppx{k} rgu{k} tia {Cpp}` | 0.5 pF | 2 pF | **UNVERIFIED** |
| Selected relay | `Ccsel_t tia 0 {Ccc}` / `Ccsel_s source 0 {Ccc}` / `Cppsel source tia {Cpp}` | 1 / 1 / 0.5 pF | 5 / 5 / 2 pF | **UNVERIFIED** |
| Extra TIA_OUT copper (relay pads, until re-extraction) | `Cdtia tia 0 {dC}` | 3 pF | 10 pF | estimate |

**Name.** `relay_{range}_{dut}_stray{s}_revd_risolo22_{set}_caplead{cl}_local100_lead{L}`, with set = `nom` or `str`. Keep `_risolo22`, `_caplead`, `_local100` and a trailing `_lead{L}`, because `circuit()` parses those tokens. Avoid the substrings `_local`, `_series` and `_damp` elsewhere in the name. Values for the unselected branches: r100 selected → k ∈ {5 kΩ, 100 kΩ}; r5k → {100 Ω, 100 kΩ}; r100k → {100 Ω, 5 kΩ}. The unselected 100 Ω branch with Ccc is the summing-node load to watch on r5k and r100k.

**Case groups:**

1. **Grid.** Nominal and stress sets × the 64 revd-extracted combinations = 128 cases, `tia` loop.
2. **Attribution.** For each range, open DUT, stray 0, caplead 10: the stress set with one parameter at a time (Coc, Ccc, Cpp, L_rel, dC, Rc), with all others nominal. 18 cases, `tia` loop.
3. **Other loops.** Add `drive`, `high` and `low` loops to stress-set r100 open stray 0 and 1000, and r100k open stray 0 and 1000. These are the cases where C_pp and Ccc couple SOURCE_BUF to TIA_OUT/TIA_SUM. That is 4 cases × 3 loops.
4. **Two-relays-closed fault** (weld, or a future make-before-break). For r100+r5k, r100+r100k and r5k+r100k, open DUT, stray 0: add `Rpar sum rfp {R2}` / `Lpar rfp tia 30n` / `RGpar source hi {R2}`. 3 cases.

The no-relay-closed state has no DC operating point (TIA DC loop open), so it cannot run as an AC loop case. §3.2 bounds its drift instead.

**Criteria.** Use the same criteria as `fixedextracted`: every downward crossing ≥45° and the minimum return difference reported. Compare against the Rev D as-built floor, 51.3° and |1+T| ≥ 0.573. Expect the stress set to cost a few degrees, mostly from dC: dropping the whole 10.5 pF of TIA_OUT copper was worth about 4.6°.

After the relay layout exists, re-extract `../layout-parasitics/` and replace the dC and Ccc guesses with extracted values. Also rerun `validation/power-spurs/` with the coil-rail filter, and the virtual-instrument budget with C_open drift ±10 %.

Size: about 150 `tia` runs plus 12 other-loop runs, at the existing 120 points/decade (4,800 for coil cases). This study did not run them.

## 7. Risks and open items

- **Relay parasitics.** Contact-to-coil capacitance, pole-to-pole capacitance, contact-path inductance and per-closure contact repeatability are unpublished for every candidate (**UNVERIFIED**). The §6 stress values bracket them. Measure one relay on the bench, or with a VNA, before ordering if the stress set comes close to 45°.
- **Converted capacitances.** The open-contact values depend on the 50 Ω conversion and on figures read by eye. They are within a factor of 2, and either value is ≤0.6 % of C104.
- **Stock.** TQ2SA-L2-5V-Z: 1,756 at JLC, adequate for 2–5 boards × 3. The second source with the same drive scheme is KEMET EE2-5TNUH-L (dual coil, 324 stock, different footprint).
- **Non-latching fallback.** Omron G6K-2F-Y-TR DC5 (C47190, 61,851 stock, $1.05, 0.16 pF) with three GPIOs. It draws ≈100 mW continuously while a range is selected, and has no range at all when de-energised. Unless K3 is wired on its NC contacts so that High is the default, the TIA then has no DC path; with K3 on NC, Low and Medium need two coils on (200 mW). Omron itself: "Using the Relay in a circuit where the Relay will be ON continuously for long periods … can lead to unstable contacts because the heat generated by the coil itself … We recommend using a latching relay" (`G6K.txt`, Correct Use). This is the main reason the latching part is preferred.
- **Single-winding latching** (G6KU-2F-Y, smaller and cheaper). It needs polarity reversal. One shared-common half-bridge plus three half-bridges would work, for example a DRV8833-class H-bridge with all coils off one common node. That adds a driver IC, and a P-FET high side cannot be switched off from 3.3 V GPIO without a level shift. The dual-coil part avoids both.
- **Latched state persists through power-off.** Firmware resets and selects High at every boot. With blank firmware the board keeps whatever range was last set, while the DDS source is still uncontrolled.
- **Self-check limits.** The §3.4 self-check catches a wrong range or a failed pole, but not two relays welded closed. Calibration verification catches the latter.
- **Layout.** The relays (14 × 9 mm each) go where JP1–JP6 are. R43–R45 stay at U7 with their TIA_SUM pads short. C104 stays local and unswitched. Route the coil drive lines away from TIA_SUM and RF100 and guard them with ground. Hand-route only.
- **Cost.** 3 × $2.27 + 4 × AO3400A + 6 × 1N4148WS + resistors, about $7.4 per board. That adds one extended line (the relay) and removes the six jumpers.
- **Not covered.** This study does not change channel B's tap point or the 22 Ω R_iso. It ran no simulation; the §6 cases decide.
