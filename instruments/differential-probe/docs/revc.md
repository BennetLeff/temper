# Rev C — compacted, simplified probe

Rev C keeps every Rev B function and removes parts, area and hand wiring. Both revisions are engineering prototypes; Rev C has no measured result yet. The evidence for each claim below is a regenerated file in this directory.

| Evidence | File |
|---|---|
| ERC (0 violations) | [`validation/erc.rpt`](../validation/erc.rpt) |
| Native DRC, `--all-track-errors` (0 violations, 0 unconnected) | [`validation/pcb-drc.json`](../validation/pcb-drc.json) |
| Schematic checks, ideal calculations, compensation coverage proof | [`validation/checks.txt`](../validation/checks.txt) |
| Board-to-schematic, mirror-symmetry and matched-length checks | [`validation/pcb-checks.txt`](../validation/pcb-checks.txt) |
| DRC negative and positive controls | [`validation/pcb-drc-oracle.txt`](../validation/pcb-drc-oracle.txt) |
| OPA2810/OPA810 vendor-model AC and saturation checks | [`validation/spice/results.txt`](../validation/spice/results.txt) |

Rev B is kept unchanged at commit `ca79d882f` (branch `codex/differential-probe-revb`), together with its documents ([circuit](circuit-revb.md), [build decision](revb-build-decision.md), [layout handoff](layout-revb-handoff.md)).

## Before and after

| | Rev B (`ca79d882f`) | Rev C |
|---|---|---|
| Board outline | 240 × 84 mm = 20,160 mm² (20,046 mm² net of slots and chamfers) | **150 × 70 mm = 10,500 mm² (10,328 mm² net)**, −48% |
| Copper layers | 4 | 4 (2-layer option evaluated below, not adopted) |
| Enclosure | Not selected | **Owner-designed**, not priced; the Hammond 1455N2201 (extruded aluminium, 220 mm long, internal height 49.7 mm) is the reference geometry ([requirements](#9-size-layers-enclosure)) |
| Components | 140: 135 on the board + 5 hand-wired off-board | **116, all on the board**: 103 SMD + 13 THT (2 BNCs, 2 toggles, reset button, 2 holders, 6 trimmers), plus the copper solder jumper JP1 |
| Unique MPNs | 45 | **46** |
| Tolerance-bearing parts (definition below) | 77 | **52** |
| HV divider resistors | 20 × 1 MΩ HVCB2512 | **10 × 2 MΩ** (HVCB2512, then 1% HV12 after the [cost-down](cost-down.md)) |
| Mounting holes | 6 | **4** |
| LV courtyard fill, top side | 14.4% of the 9,399 mm² LV region | **38.9%** of the 6,361 mm² LV region (bottom side 53.8%; both sides 46.3%; `validation/pcb-checks.txt`) |
| Supply current, typical (amplifiers) | ~50 mA per rail (2 × ADA4817 + 3 × OPA810 + TL431 bias) | **~18 mA per rail** (4 OPA2810 channels + 1 OPA810) |
| Component cost, 2 boards, dated 2026-10-20 | $768.27 | $535.81 (−30%); see [cost](#cost-dated-2026-10-20). **$148.10 after the [cost-down](cost-down.md) and [fee consolidation](fee-consolidation.md)** |
| JLC bare-PCB quote, 5 pcs, 4 layers (HASL lead-free / ENIG) | $43.00 / $56.40 | **$36.80 / $49.30** |

**Tolerance-bearing parts** are the parts whose value tolerance enters a stated ratio, gain, pole or warning-threshold budget:

- HV resistors and capacitors.
- R11/R31 and the low-leg capacitor bank.
- The gain-setting resistors.
- R69/C61, R70/C62 and R100–R102.
- R71/R72.
- The warning-threshold network.
- In Rev C only, the regulator feedback resistors R81–R84, because Rev C thresholds are derived from the rails.

Rev B's count includes its TL431 references and their resistors. Trimmers are counted as adjustment parts, not tolerance-bearing parts.

## What changed, item by item

### 1. 2 MΩ HV resistors (10 instead of 20)

Each compensated section is now one Stackpole **HVCB2512BDE2M00** (0.1%, 25 ppm/°C, D = 500-piece reel code) across one 33 pF / 3 kV C0G. Each leg is still 10 MΩ, five sections, 2000:1.

At 3 kV DC per tip, each body dissipates 0.180 W and sees 600 V. The datasheet working limit for this value is power-limited: √(2 W × 2 MΩ) = 2.0 kV at 70 °C, derated linearly to zero at 155 °C. Five bodies in series give the required at least two independent series impedances. For example, a 2 + 3 protective split leaves 1.5 kV and 1.125 W on each remaining body if the 3-body group is bypassed at 3 kV DC.

The 0.1% tolerance corners are unchanged from Rev B: five 0.1% bodies give the same string-tolerance corners as ten. The DC-trim range check in `checks.txt` still requires 7.000–18.003 Ω on the 50 Ω pot.

What gets worse:

- **Voltage coefficient per body doubles, from 300 V to 600 V.** The datasheet gives only a series-wide "1 to 200 ppm/V typical". No per-value VCR exists, so high-voltage linearity is a qualification item, as before.
- **Stock is the main risk.** On 2026-10-20 DigiKey listed 9 pieces ($14.50 each, $11.995 at 10; 18-week factory lead time). LCSC C4553702 listed 0. Two boards need 20. HVCB2512BDE1M00 (1 MΩ) had 2,889 pieces.

The fallback is two 1 MΩ bodies per section. This brings back Rev B's resistor count and needs a re-layout of each section; the pitch would grow by about one 2512 length. This is an **owner decision**.

**Superseded by the [cost-down](cost-down.md) (2026-10-20).** The sections now use Uni-Royal **HV121WF2004T4E** (2 MΩ, 1%, ±100 ppm/°C, 1 W at 70 °C, 3000 V working, 4000 V overload; JLC C2779442, 6,345 in stock). R11/R31 become 4.87 kΩ 0.1% and RV1/RV2 500 Ω, which covers a 1% string (77.6–187.4 Ω needed) and still covers a 0.1% one, so HVCB2512BDE2M00 is a drop-in upgrade. Costs: DC CMRR drift with temperature (254 instead of 60.5 ppm/°C worst case) and, at the ±3 kV extension only, the 2 + 3 split case above runs each remaining body at 112.5% of its 1 W rating (28% at the ±1.5 kV guarantee).

### 2. Leg pitch, inter-leg slot and DRC controls

The legs are now mirror images about the slot axis (y = 35 mm), not translated copies:

- **Leg layout.** Resistor rows face each other 16 mm apart. Capacitor rows sit 7 mm outboard, at 30 mm apart. Each leg's resistor/capacitor centroid is 11.5 mm from the axis, so the **leg pitch is 23 mm** (Rev B: 35 mm).
- **Inter-leg slot.** A 1.6 mm notch, open at the tip-end board edge, runs to x = 36 mm. Because it is open at the edge, there is no surface path around its tip-end. Opposite-leg creepage beyond its end is covered by the opposite-leg max-rank rules.
- **Spacing ranks.** Each 2 MΩ section is one 600 V rank (TIP = rank 5). Rules are 2 mm air / 4 mm creepage per rank:
  - Same leg: by rank difference.
  - Opposite legs: by the larger rank, within |V+|, |V−|, |V+ − V−| ≤ 3 kV.
  - Tip to LV: 10 mm / 20 mm.

  [`check_pcb.rs`](../tools/check_pcb.rs) maximizes every rank pair over the six vertices of that envelope.
- **Analytic margin.** The facing tip pads are 12.65 mm apart in air (≥ 10 mm). The notch supplies the 20 mm creepage.

`make pcb-oracle` shows each rule is active:

| Fixture | Result |
|---|---|
| GND track 6 mm from TIP_P | Fails the 10 mm air rule |
| C1 slot removed | Fails the 4 mm section creepage rule |
| **Notch closed** | Fails TIP_P–TIP_N 20 mm creepage |
| **Notch shortened to x = 23 mm** | Tips still pass; rank-4/rank-3 opposite-leg creepage fails at the notch end |
| Opposing tip pads 20.5 mm apart | Pass |
| Opposing tip pads 8 mm apart | Fail |

### 3. Compensation bank

Rev B used a seven-capacitor binary bank per leg. Rev C uses three capacitors plus the trimmer:

| Part | Role | Value |
|---|---|---|
| C41/C51 | Fixed | 10 nF 1% C0G/NP0 (C1206C103F5GACTU; Yageo CC1206FKNPO9BN103 after the [cost-down](cost-down.md)) |
| C42/C52 | Select-on-test S1 | Nominal 3.0 nF 1% (C0805C302F5GACTU), chosen from E24 1.8–3.9 nF |
| C43/C53 | Select-on-test S2 | Nominal 160 pF 1% (C0805C161F5GACTU), chosen from E24 0–360 pF |
| CT1/CT2 | Trimmer | GKG60015, 12–60 pF |

The requirement is 12,103.6–13,747.5 pF. This is the archived −8.26/+4.20% 60 kHz-versus-DC spread around 13,193.4 pF, less 2–15 pF of tap parasitics.

`check.rs` proves the two-stage selection has no gap at worst-case 1% tolerance:

1. Measure, choose S1 so the stage-1 residual (1,988.6–3,845.5 pF) is covered.
2. Re-measure, choose S2 for the stage-2 residual (12–416.4 pF).
3. Finish with the trimmer.

Adjacent select steps overlap by at least 29.4 pF (S1) and 11.1 pF (S2); that overlap is the allowable measurement error when choosing a value. The nominal fit leaves 33.4 pF for the trimmer plus parasitics.

Kemet 1% C0G availability for each E24 value was not checked. Buy the S1/S2 kits before the first calibration.

### 4. One amplifier family (OPA2810 / OPA810)

| Stage | Part | Channel use |
|---|---|---|
| Buffers | U1 = OPA2810IDR | One channel per leg on the slot axis |
| Subtractor and driver | U3 = OPA2810IDR | Channel 2 = fixed ×2 subtractor; channel 1 = coax driver. Channel roles are swapped from the natural order so neither path crosses the other. |
| ×5 stage | U12 = OPA810IDR (single) | — |

The ×5 stage is **deliberately not paired** with the subtractor. It is the stage driven into saturation in wide range, and keeping it off the subtractor's package and supply pins avoids inter-channel coupling that TI's one-channel-per-instance model cannot show. The data-sheet crosstalk is −93 dBc at 100 kHz. This departs from pairing ×2 with ×5; it costs one SOIC-8.

OPA2810 facts used:

- The JFET input stage holds to VS+ − 2.5 V typical (−3 V over temperature). On +4.8 V that is about +1.8 V; taps stay at or below 1.5 V.
- VOS is 1.5 mV max (2.4 mV at 85 °C).
- Absolute maximum input is the rails ± 0.5 V at 10 mA.
- Differential input is limited to ±7 V.

Gains:

| Stage | Network | Gain |
|---|---|---|
| Subtractor | 499 Ω / 1 kΩ | 2.004 |
| ×5 | 499 Ω / 2 kΩ (‖ R114 66.5 kΩ zero trim) | 5.008 (5.036 with the trim at mid-travel) |

Loaded DC ratios are 1003.91:1 and 198.69:1 with the zero trims at mid-travel (1000.59:1 and 199.80:1 without them). Calibrate the full path.

**Rev C feature: analog zero trims (RV3 wide, RV4 fine).** Each range has a 20 kΩ 3296W across the rails, injecting after the subtraction: RV3 into WIDE_SEL through R113 (10 kΩ), RV4 into U12's inverting node through R114 (66.5 kΩ). CMRR is untouched. They reach ±22.6 / ±139.3 mV at the BNC against worst untrimmed offsets of 19.2 / 92.7 mV. After trimming, the selected-path zero stays within 9.58 / 44.39 mV over −25…85 °C. The warning-budget zero limits therefore tighten from ±25 / ±130 mV to ±10 / ±45 mV, and the late trip falls by 15.3 V (wide) and 17.3 V (fine).

The cost is DC gain: −0.33% wide and +0.56% fine at mid-travel, calibrated out with the rest of the path. On wide, that is 0.33% less margin above the 98.82% calibrated-gain acceptance. Parts cost +$3.54 for two boards (strategy H, `validation/cost.txt`), with no new Extended feeder: the pots are owner-soldered THT, and both resistor MPNs are already on the board. Details are in [design.md](design.md#analog-zero-trims).

Vendor PSpice model results (TI SBOMB66, `opa2810_a.lib` sha256 `b451809e…`) in [`validation/spice`](../validation/spice), with the lumped divider, R12 and a 1 MΩ ‖ 120 pF scope load:

| Range | −3 dB | Peaking | Phase at 60 kHz |
|---|---|---|---|
| Wide | 5.769 MHz | None | −1.000° |
| Fine | 5.267 MHz | None | −1.243° |

The filter is R69 220 Ω / C61 47 pF plus C62 330 pF at the BNC through the bridged jumper JP1 (2026-10-21; [design](design.md#output-filter-and-driver)). It halves the wide full-band noise for the same bandwidth. Cutting JP1 gives 10.86 / 8.45 MHz. The single-pole filters before it gave 5.628 / 5.131 MHz (R69 220 Ω / C61 100 pF, [fee consolidation](fee-consolidation.md)) and 5.786 / 5.252 MHz (97.6 Ω / 180 pF) (`validation/spice/candidates.cir`).

Saturating the unused ×5 stage moves the wide output by 17.0 nV. These are nominal model results, not stability or bandwidth qualification.

### 5. TL431s removed

Thresholds now come from one ladder per polarity across the regulated rail: 66.5 kΩ → LIM (input-warning node) → 1 kΩ → OUT_LIM (selected-output node) → 10 kΩ → GND. The BAV199 clamps return directly to ±4.8 V.

This removes U10, U11, R85, R86, R90 and R94: six parts. The rail accuracy is budgeted as ADP7142 ±1.8% and ADP7182 ADJ −2.95/+1.97%, plus 0.1% feedback resistors. R88/R92 (1 kΩ) are 1% Basic parts since the [fee consolidation](fee-consolidation.md) (L1: +1.5 V per tip, +0.2 V wide, +0.04 V fine).

| Warning | Nominal | Latest trip (−25…85 °C, gain ≥ 98%) | Earliest trip | Limit |
|---|---|---|---|---|
| Per tip | 1,362.6 V | < 1,454.5 V | 1,266 V | 1,500 V |
| Selected output, wide | 1,238.7 V | < 1,326.5 V | 1,147 V | 1,500 V |
| Selected output, fine | 247.7 V | < 272.45 V | 222 V | 300 V |

The selected-output rows assume the zero trims are set (zero within ±10 / ±45 mV). Untrimmed, with the old ±25 / ±130 mV limits, they are < 1,341.8 V and < 289.79 V.

The worst single-fault clamp current (one bottom bank open, 3 kVpk at 60 kHz) is 7.5 mA peak. That is below the minimum rail load of about 14.7 mA, so neither LDO is back-driven.

The OPA2810 input ESD diodes share some of this current, because BAV199 Vf (about 0.9 V) exceeds 0.5 V. R12/R32 (220 Ω) keep it under the 10 mA absolute maximum. This is a bench-check item.

### 6. Comparator and latch — partially done

The warning circuit loses six parts (item 5). The comparator/latch topology itself is kept: TLV1704 quad + TLV1702 dual + CD4013 + Q1.

The six comparisons (both polarities at both tips, plus both polarities of the selected output) need six channels. A quad plus a dual is the smallest standard combination. The alternatives considered were:

- Hysteresis-latched comparators, which need an extra channel and a separate reset injection.
- A single open-drain OR into an RC hold, which is not a latch.

Each saved at most one or two parts while weakening the latched-until-reset behaviour, so neither was adopted. **Declined.**

**Rev C feature: trigger output (J4).** The CD4013's second flip-flop was unused. It now latches with the first and drives a second BNC through a PNP high-side stage (Q3, R110–R112, D10): 0 V idle, 4.45–4.92 V into 1 MΩ when latched, 0.42–0.48 V into 50 Ω. The scope can then trigger on the warning. It marks that the warning latched; it is not a peak-capture guarantee, and the latency estimate is 1.64 µs after the comparator output plus the comparator's typical 460 ns. Nothing on J4 can reach the warning latch. Details, ratings and margins are in [design.md](design.md#trigger-output-j4). Cost: +$7.42 for two boards (strategy H − E, `validation/cost.txt`), mostly the second owner-soldered BNC; two new JLC Basic resistors and no new Extended MPNs.

### 7. PCB-mount panel parts

| Part | MPN | Notes |
|---|---|---|
| BNC × 2 (J3 output, J4 trigger) | Amphenol RF **031-5431-10RFX** | Right-angle PCB bulkhead. Panel D-hole 12.83 mm / 11.7 mm flat each; panel ≤ 5 mm; axis 8.6 mm above the board. |
| Range switch | E-Switch **100SP1T1B5M7RE** (was C&K 7101SDAV2BE) | Gold SPDT, threaded 1/4-40 high-torque bushing, M7 vertical right-angle PC mount. |
| Power switch | E-Switch **100DP1T1B1M7QEH** (was C&K 7201P3DAV2QE) | Silver DPDT, threaded 1/4-40, M7. |
| 9 V holders | **MPD BH9VPC** × 2 | Bottom side, under the LV section. Pin 1 = +, as in the MPD drawing. |
| Latch reset (SW3) | C&K **PTS645SL43-2 LFS** (was PTS645SL43SMTR92 LFS) | 6 × 6 mm tactile, thru-hole, 4.3 mm actuator, 130 gf; soldered by the owner. Pressed through a lid hole at (131.85, 46.25). |

The power switch carries about 20 mA, which is adequate for silver contacts. Threaded gold DPDT parts were not stocked; unthreaded `D9` bushings cannot take a panel nut. The [cost-down](cost-down.md#5-toggles) replaced the C&K parts ($71.46 for two boards) with E-Switch 100-series M7 parts ($22.24), whose catalog hole pattern is the same as the AV2 bracket's.

**Reset button (SW3).** The SMT PTS645SL43SMTR92 LFS was not stocked at JLC, so JLC would global-source it, which for a switch costs a $20 commodity inspection plus a $3.07 Extended feeder. The C&K **PTS645SL43-2 LFS** is the same switch with thru-hole pins (same 6 × 6 mm body, 4.3 mm actuator, 130 gf); the owner solders it, which removes both fees (`validation/cost.txt`, strategy E).

- **Ratings** (Littelfuse/C&K PTS645 series datasheet): 50 mA at 12 V DC maximum, 10 µA at 1 V DC minimum; dielectric strength 250 V AC; contact resistance 100 mΩ maximum initial; insulation resistance 10¹¹ Ω minimum; 100,000 operations; −40 to +85 °C (DigiKey lists the same; the 2018 C&K sheet served by LCSC states −20 to +60 °C). In circuit the open switch sees 9.6 V (+4.8 V to RESET held at −4.8 V by R95), and closing it draws 96 µA DC through R95 plus the C95 discharge, as with the SMT part. **Approval basis: none listed**, as for the part it replaces; it is on the low-voltage side.
- **Placement.** Its old site (120, 28.5) lies over BT1, so thru-hole tails would hit the holder body. Both holders cover the whole LV band from x = 71.3 to 126.6 mm on the bottom; the only top-side space outside that band with room for its 9 × 7 mm courtyard is the panel strip between J3 and SW2, at (131.85, 46.25). The footprint carries a bottom-side courtyard over the tails, so DRC fails if it is ever moved back over a holder (`make pcb-oracle`, fixture `button-over-holder`). SW_P now passes under it on B.Cu; RESET reaches it by an In2 hop from (123.98, 26.25); its +4.8 V pins join the In2 pour.
- **Reach** is unchanged in kind: a lid hole over the button, as for the trimmers. The actuator top is 4.3 mm above the board.

All footprints are generated in [`tools/build.rs`](../tools/build.rs) `edge_parts`, from manufacturer dimensions:

- **BNC:** Ø0.89 mm pins on 2.54 mm; board locks Ø2.0 mm, 10.16 mm apart, 5.08 mm behind the pins; housing face 7.37 mm ahead of the pins.
- **Toggles:** contact rows on 0.150 in; support pins 0.200 in apart and 0.500 in ahead of row 1; all holes 0.073 in (E-Switch 100 catalog, M7-SP / M7-DP; identical to the C&K AV2 pattern).
- **Holders:** the MPD rev J PCB layout.
- **Reset button** (`SW_Tactile_CK_PTS645_THT`): C&K PTS645 drawing "S STRAIGHT" and its PCB layout: four Ø1.0 mm holes on 6.5 × 4.5 mm, pins 1–2 and 3–4 internally common (so each row's two pads share a number and both are connected), 0.7 × 0.3 mm legs 3.5 mm below the seating plane, 6 × 6 mm body.

**Verify against samples before fabrication:**

- **BNC pin orientation.** The signal pin is placed on the coax axis with the ground pin beside it. The Amphenol drawing would not render in this session, so this comes from transcribed dimensions.
- **Toggle fit.** The E-Switch M7-SP and M7-DP hole patterns are both drawn by the manufacturer (this removes the earlier "7101 derived from the 7201 drawing" item). The bushing axis height and the B5 flanged bushing against the 1.5 mm end plate are not dimensioned directly and must be checked on a sample.

None of these parts has a 3D model in the render.

### 8. Courtyard fill and mounting holes

Holes go from 6 to 4:

- **H1/H2:** grounded M3, at the panel end. H2 is at (145.5, 65.5). H1 moved from the (145.5, 4.5) corner to (131.0, 31.2), between SW1 and J3, because the trigger BNC J4 now occupies that corner.
- **H3/H4:** unplated, at the tip end, one on each side of the notch. Use **nylon screws and standoffs** there.

The LV region (x ≥ 59 mm, 6,361 mm²) has 38.9% top-side courtyard coverage (Rev B: 14.4%) and 53.8% bottom-side coverage, from the two holders and the reset button's tail keep-out. That is 46.3% of the two-sided placement area (`check_pcb.rs`). The same calculation gave 37.0 / 53.8 / 45.4% before the zero trims, 33.0 / 53.8 / 43.4% before the trigger output (J4 and its stage) was added, and 32.9 / 52.8 / 42.8% before the button moved.

**Top side and both sides now meet ≥ 35%**; the top side got there by adding the trigger output, not by shrinking the board. Before that, reaching 35% on the top side alone needed a 150 × 64 mm board (estimated 35.7%), which means re-placing every band. I kept 150 × 70 mm, the stated stretch target. The holders still fit, and the extra 6 mm buys routing corridors (WIDE_SEL/FINE_SEL along the top edge). This can be reversed if the top-side number matters.

### 9. Size, layers, enclosure

**Board.** 150 × 70 mm, within the ≤195 mm limit and on the stretch target.

**Layers.** Kept at 4. The 2-layer option is not clearly safe:

- Rev C's low-voltage routing relies on an unbroken In1 GND reference under the analog chain, and on In2/B.Cu pours for ±4.8 V. Both feed the CMRR and the stability margin of five 70 MHz amplifier channels.
- A 2-layer version would need a full re-route and new stability evidence.

| JLC, 5 pcs, 150 × 70 mm, 2026-10-20 | HASL lead-free | ENIG |
|---|---|---|
| 2 layers | $10.40 | $26.90 |
| 4 layers (includes $25 engineering fee) | $36.80 | $49.30 |
| **Saving if 2-layer were adopted** | **$26.40** | **$22.40** |

**Enclosure: owner-designed (2026-10-20).** The owner is designing the enclosure, so it is not priced. The **Hammond 1455N2201** ([drawing](https://www.hammfg.com/files/parts/pdf/1455N2201.pdf); DigiKey $38.43, 52 in stock on 2026-10-20) stays as the reference design: the setback figures below, `tools/leads.rs` and the printed wall insert ([`mech3d/`](../mech3d/README.md)) use its dimensions.

Any owner enclosure must provide:

1. **An earthed conductive shield around the board, fixed in position.** Bond it to GND at H1/H2 and both BNC shells. The per-leg compensation absorbs static strays but not movement after calibration: a 0.0066 pF change at a tap alone limits CMRR to 60 dB (`validation/leads/leads.txt`), so each node's stray capacitance to the shield must stay stable to about 0.01 pF. No flexing walls, loose lids or movable metal near the ladder.
2. **≥ 20 mm from every exposed HV conductor to metal**, in three dimensions: ladder copper and bodies, the W_HV landings, the trimmed lead tails (≤ 1 mm below the board) and the lead loops (≤ 5.5 mm above it).
3. **The tip-end insulating feedthrough and strain relief**: an insulating tip-end wall with two PG7 nylon glands (12.7 mm holes, 29.0 mm apart) and the printed lead bridge clamped under the H3/H4 nylon screws. The printed `wall-insert` (STEP in `mech3d/out/`) is the reference and can be merged into the owner's wall. The wall must also carry:
   - **the spine socket boss** on the outside, centred between the glands at the lead height: a 5.4 × 8.4 mm socket, 11 mm deep, in an 8 × 11 mm boss 12 mm long, with a vertical M3 pin hole 6 mm from the face;
   - **the bridge ledge** on the inside, 5 mm wide, its top at the board-top plane (23.6 mm above the floor), reaching 6 mm under the bridge;
   - **the gland axis height**: 26.61 mm above the inner floor in the reference (28.25 mm above the box underside). On the bench the box stands on a riser that puts the gland axis 50 mm above the stage-53 board top (71.7 mm for the reference box). An owner enclosure with a different axis height needs a different riser, not a different spine.
   - **trimmer-guide holes** in the lid: Ø7.2 mm over CT1/CT2, RV1/RV2 and the RV3/RV4 zero trims for the snap-in guides, lid 1.65 mm thick at the reference height (rebuild the guides with `make mech3d` if the lid differs).
4. **Board standoffs** that put the board underside 22.0 mm above the inner floor (the 9 V holders hang 20.6 mm below the board; insulating sheet on the floor): metal at H1/H2, nylon at H3/H4.
5. **Panel access**: an output panel (≤ 5 mm thick at the BNCs) with two BNC D-holes (Ø12.83 mm, 11.7 mm flat; J4 trigger at y = 7.72 mm and J3 output at y = 35.0 mm, both 8.6 mm above the board top) and the two 6.35 mm toggle holes (SW1 at y = 21.36 mm, SW2 at y = 56.0 mm, 6.35 mm above the board top). Board y is measured from the edge nearest J4; the panel order from that edge is J4, SW1, J3, SW2, with SW3 set back at (131.85, 46.25). The J4–SW1 pitch is 13.64 mm, so check that the BNC nut and the toggle nut or washer clear each other on the panel. Also provide holes for the SW3 reset button, the CT1/CT2, RV1/RV2 and RV3/RV4 trimmer tools and the D9 LED, with every hole edge ≥ 20 mm from HV copper.

The Hammond 1455N2201 numbers in this section are the reference design. To check an owner enclosure, re-enter its dimensions in the constants at the top of [`tools/leads.rs`](../tools/leads.rs) (the enclosure block `BOX_H`, `BOX_H_NOM`, `BOX_W`, `BOARD_UNDER`, `OUT_PANEL_X`, `BOX_L_INT`, and the tip-end wall block) and run `make check`: every setback gate and the section drawing regenerate, a failed gate stops the check, and `make mech3d` rebuilds the printed parts from the new geometry.

**Reference design: Hammond 1455N2201.**

The board sits on four standoffs so its underside is **22.0 mm above the inner floor**, for example a 20 mm M3 standoff plus a 2 mm spacer. Use metal at H1/H2 and nylon at H3/H4. The BNC and toggle faces sit at the output end plate. 3-D setback from exposed HV conductors to metal, using the drawing's minimum internal height of 49.14 mm:

| Direction | Clearance |
|---|---|
| Down | 22.0 mm minus a 1 mm trimmed W_HV lead tail = 21 mm. The SMD HV parts have no tails. |
| Up | Lid at ≥ 49.14 mm; board top at 23.6 mm. HV parts are ≤ 1.1 mm (1812 C0G T max) and ≤ 0.76 mm (2512). Lead loops at W_HV must stay ≤ 5.5 mm high to keep ≥ 20 mm; the printed lead bridge holds them at 4.65 mm. |
| Sides | 12.5 mm from the board edge to the rib tips (95 mm internal width), plus ≥ 16 mm from the edge to the nearest HV copper: ≥ 28 mm. |
| Tip end | With the panel parts at the output plate, the board's tip edge is 73.4 mm from the tip-end plate (the Hammond drawing: 220 mm extrusion plus a 1.6 mm polycarbonate bezel lip at each end). That wall is the **printed wall insert**, not aluminium, so the nearest metal at the tip end is the lid and floor. The leads leave through nylon glands and are carried on a printed lead bridge; see [HV leads](hv-leads.md). The lead conductor is 22.54 mm from the lid. |

**Trimmer access.** Lid holes go over:

- CT1/CT2 at (62, 23) and (62, 47).
- The RV1/RV2 3296W top screws (bodies at x ≈ 62–71 mm, y = 7 / 63 mm; locate the screw from a sample).
- The RV3/RV4 zero-trim 3296W screws (bodies along x = 68.6 mm, y ≈ 10–20 mm for RV4 and 50–60 mm for RV3; locate the screw from a sample). The same `trim-guide-rv` guide fits.
- The SW3 reset button at (131.85, 46.25), in the panel strip between the output BNC and the power switch.
- The D9 LED at (115, 24).

The lid is 25 mm above the board, so hole edges stay ≥ 20 mm from HV copper. The holders hang 20.6 mm under the board, leaving 1.4 mm. Put an insulating sheet on the floor.

Other enclosures considered:

- Hammond 1550G die-cast: internal height 51.1 mm, $30.46. Shorter, so the tip-end clearance is tight.
- 1455U2201: internal height 61.5 mm, $46.92. More than needed.

## Layout notes specific to Rev C

- **Routing.** Hand-authored in [`tools/layout.rs`](../tools/layout.rs), as in Rev B. **No autorouter was used.** Freerouting was only invoked with `--help`; nothing was routed with it or imported.
- **Analog chain.** It runs along the slot axis: U1 → U3 → R69/C61 → R70 → JP1/C62 at the BNC → BNC. The range-select ×5 stage and latch sit above it; the warning comparators, ladders and LDOs sit below.
- **Matched lengths.** Tap-to-buffer inputs are 14.478 mm on both legs (the N side jogs to absorb U1's 1.27 mm pin offset). Buffer-to-subtractor paths are 7.565 mm on both legs. Both pairs are checked by `check_pcb.rs`.
- **Reference designators.** They are on the Fab layers. Silk carries outlines and board text only, so DRC including silk reports zero.
- **Component placement.** The holders mount on the bottom with their screw holes outboard. Bottom-flipping mirrors the part, so the top holder's contacts face the tap cell and the bottom holder's face the panel. BAT_P therefore runs on B.Cu along y = 27 mm.

## Rev B issues resolved on the way

These were open identity problems in [`procurement/quote-review.md`](../procurement/quote-review.md):

- R12/R32 are now the orderable `RT0805BRD07220RL`.
- D4–D7 name MDD SS14 (LCSC C2480).
- D8 is Vishay 1N4148W-E3-18 (LCSC C191428).

## Cost (dated 2026-10-20)

Prices were read from public DigiKey and LCSC product pages on 2026-10-20, without logging in or adding anything to a cart. Mouser was not checked. Each unit price is the tier that covers two boards, from DigiKey where it had stock and from LCSC otherwise, with LCSC minimum quantities applied. The ledger is [`procurement/prices-2026-10-20.csv`](../procurement/prices-2026-10-20.csv); `python3 procurement/cost.py` reproduces the totals.

| Two prototype boards | Rev B | Rev C |
|---|---:|---:|
| Components (Rev B includes its 5 off-board parts) | $768.27 | $535.81 |
| HV divider resistors | $406.43 (40 × 1 MΩ) | $239.90 (20 × 2 MΩ) |
| Bare PCB, JLC 5 pcs, 4-layer HASL | $43.00 | $36.80 |
| Enclosure | none selected | owner-designed, not priced |
| **Total** | **$811.27** | **$572.61** (−29%) |
| HV leads, hardware and printed parts ([HV leads](hv-leads.md#parts-ratings-and-prices-2026-10-20)) | none selected | $142.43: bought parts $57.60 (generic parts at estimated prices $29.60), resin $84.83 |
| **Total with HV leads** | — | **$715.04** |

The [cost-down](cost-down.md) (2026-10-20) brings the Rev C components to $148.10 at the same ledger prices (with the [fee consolidation](fee-consolidation.md)) and adds a JLC assembly-fee model (`validation/cost.txt`).

Of the $232.46 component saving, the HV resistors account for $166.53 and removing the ADA4817s for $46.00. The PCB-mount switches ($71.46) cost about the same as Rev B's panel switches ($76.41).

Not included: shipping, tax, Digi-Reel fees, JLC assembly (needs an account upload) and the S1/S2 select-on-test capacitor kits. The HV leads, hardware and printed parts are priced separately in [HV leads](hv-leads.md#parts-ratings-and-prices-2026-10-20) and by `procurement/cost.py`.

Caveats on the prices:

- **HVCB2512BDE2M00** is priced at DigiKey's 10+ tier, but DigiKey had only 9 of the 20 needed and LCSC had none. See risk 1.
- **C0805C302F5GACTU and C0805C161F5GACTU** had no stock at either distributor; DigiKey sells them only as 4,000/8,000-piece reels. They are priced at LCSC's list price.
- **OPA2810IDR, BAV199, MMBT3906 and three RT0805 values** were out of stock at DigiKey until November–December 2026. They are priced at LCSC, which had stock.
- **Rev B's 1N4148W,115** was not found at either distributor, and its RT0805BRD07220L is not an orderable MPN. Both are priced as their Rev C replacements.

## Risks and open owner decisions

1. **HVCB2512BDE2M00 stock** (9 at DigiKey, 0 at LCSC). Resolved by the [cost-down](cost-down.md): 1% HV12 bodies stocked at JLC, HVCB kept as a drop-in upgrade.
2. **BNC footprint orientation and E-Switch toggle fit** must be checked against samples or drawings before fabrication.
3. **Top-side fill is 38.9%** with the trigger output and zero trims added; the 150 × 64 mm re-placement is no longer needed for the fill target.
4. **U12 kept as a separate OPA810.** Confirm, or ask for the ×2 + ×5 pairing.
5. **Kemet 1% C0G select-on-test kits** need sourcing. Several Rev C MPNs have no reviewed LCSC identity (see [`procurement/README.md`](../procurement/README.md)).
6. **Bench items.** Unchanged in kind from Rev B, plus:
   - Per-body VCR at 600 V.
   - OPA2810 input-stage crossover (≈ +2.3 V on +4.8 V) for the ×5 and driver inputs on the extended wide range.
   - Clamp current shared with the OPA2810 ESD diodes.
   - Range-switch transients with the PCB-mount switch (E-Switch does not state break-before-make).
   - Cost-down items ([cost-down](cost-down.md#new-bench-items)): DC ratio tracking with temperature and self-heating for the 1% HV12 string, 500 Ω trim settability, Yageo 1812 body height.
7. **HV leads ([HV leads](hv-leads.md#open-risks)).** Option B's per-tip estimates are 11.71–11.93 pF against the 12 pF target (probe 2 TIP− has 0.07 pF in hand); measure them docked. The generic lead wire is unrated and accepted only by incoming hipot. The printed tip-end wall opens the shield at the tip end; measure the shield edge current and CMRR with it fitted. Print one dock and one guide and fit-check them on stage 53 and the owner's enclosure before printing the rest.
