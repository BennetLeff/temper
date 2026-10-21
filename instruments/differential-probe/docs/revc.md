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
| Enclosure | Not selected | **Hammond 1455N2201** extruded aluminium, 220 mm long, internal height 49.7 mm |
| Components | 140: 135 on the board + 5 hand-wired off-board | **105, all on the board**: 96 SMD + 9 THT (BNC, 2 toggles, 2 holders, 4 trimmers) |
| Unique MPNs | 45 | **42** |
| Tolerance-bearing parts (definition below) | 77 | **52** |
| HV divider resistors | 20 × 1 MΩ HVCB2512 | **10 × 2 MΩ HVCB2512** |
| Mounting holes | 6 | **4** |
| LV courtyard fill, top side | 14.4% of the 9,399 mm² LV region | **32.7%** of the 6,361 mm² LV region (bottom side 52.8%; both sides 42.7%) |
| Supply current, typical (amplifiers) | ~50 mA per rail (2 × ADA4817 + 3 × OPA810 + TL431 bias) | **~18 mA per rail** (4 OPA2810 channels + 1 OPA810) |
| BOM cost, 2 boards, dated 2026-10-20 | see [cost](#cost-dated-2026-10-20) | see [cost](#cost-dated-2026-10-20) |
| JLC bare-PCB quote, 5 pcs, 4 layers (HASL lead-free / ENIG) | $43.00 / $56.40 | **$36.80 / $49.30** |

**Tolerance-bearing parts** are the parts whose value tolerance enters a stated ratio, gain, pole or warning-threshold budget:

- HV resistors and capacitors.
- R11/R31 and the low-leg capacitor bank.
- The gain-setting resistors.
- R69/C61, R70 and R100–R102.
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
| C41/C51 | Fixed | 10 nF 1% C0G (C1206C103F5GACTU) |
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
| ×5 | 499 Ω / 2 kΩ | 5.008 |

Loaded DC ratios are 1000.59:1 and 199.80:1. Calibrate the full path.

Vendor PSpice model results (TI SBOMB66, `opa2810_a.lib` sha256 `b451809e…`) in [`validation/spice`](../validation/spice), with the lumped divider, R12 and a 1 MΩ ‖ 120 pF scope load:

| Range | −3 dB | Peaking | Phase at 60 kHz |
|---|---|---|---|
| Wide | 5.786 MHz | None | −0.938° |
| Fine | 5.252 MHz | None | −1.180° |

Saturating the unused ×5 stage moves the wide output by 16.7 nV. These are nominal model results, not stability or bandwidth qualification.

### 5. TL431s removed

Thresholds now come from one ladder per polarity across the regulated rail: 66.5 kΩ → LIM (input-warning node) → 1 kΩ → OUT_LIM (selected-output node) → 10 kΩ → GND. The BAV199 clamps return directly to ±4.8 V.

This removes U10, U11, R85, R86, R90 and R94: six parts. The rail accuracy is budgeted as ADP7142 ±1.8% and ADP7182 ADJ −2.95/+1.97%, plus 0.1% feedback resistors.

| Warning | Nominal | Latest trip (−25…85 °C, gain ≥ 98%) | Earliest trip | Limit |
|---|---|---|---|---|
| Per tip | 1,362.6 V | < 1,453.0 V | 1,267 V | 1,500 V |
| Selected output, wide | 1,238.7 V | < 1,341.6 V | 1,132 V | 1,500 V |
| Selected output, fine | 247.7 V | < 289.75 V | 206 V | 300 V |

The worst single-fault clamp current (one bottom bank open, 3 kVpk at 60 kHz) is 7.5 mA peak. That is below the minimum rail load of about 14.7 mA, so neither LDO is back-driven.

The OPA2810 input ESD diodes share some of this current, because BAV199 Vf (about 0.9 V) exceeds 0.5 V. R12/R32 (220 Ω) keep it under the 10 mA absolute maximum. This is a bench-check item.

### 6. Comparator and latch — partially done

The warning circuit loses six parts (item 5). The comparator/latch topology itself is kept: TLV1704 quad + TLV1702 dual + CD4013 + Q1.

The six comparisons (both polarities at both tips, plus both polarities of the selected output) need six channels. A quad plus a dual is the smallest standard combination. The alternatives considered were:

- Hysteresis-latched comparators, which need an extra channel and a separate reset injection.
- A single open-drain OR into an RC hold, which is not a latch.

Each saved at most one or two parts while weakening the latched-until-reset behaviour, so neither was adopted. **Declined.**

### 7. PCB-mount panel parts

| Part | MPN | Notes |
|---|---|---|
| BNC | Amphenol RF **031-5431-10RFX** | Right-angle PCB bulkhead. Panel D-hole 12.83 mm / 11.7 mm flat; panel ≤ 5 mm; axis 8.6 mm above the board. |
| Range switch | C&K **7101SDAV2BE** | Gold SPDT, threaded 1/4-40 bushing, AV2 vertical right-angle bracket. |
| Power switch | C&K **7201P3DAV2QE** | Silver DPDT, threaded. |
| 9 V holders | **MPD BH9VPC** × 2 | Bottom side, under the LV section. Pin 1 = +, as in the MPD drawing. |

The power switch carries about 20 mA, which is adequate for silver contacts. Threaded gold DPDT parts were not stocked; unthreaded `D9` bushings cannot take a panel nut.

All footprints are generated in [`tools/build.rs`](../tools/build.rs) `edge_parts`, from manufacturer dimensions:

- **BNC:** Ø0.89 mm pins on 2.54 mm; board locks Ø2.0 mm, 10.16 mm apart, 5.08 mm behind the pins; housing face 7.37 mm ahead of the pins.
- **Toggles:** contact rows on 0.150 in; support pins 0.200 in apart and 0.500 in ahead of row 1; all holes 0.073 in.
- **Holders:** the MPD rev J PCB layout.

**Verify against samples before fabrication:**

- **BNC pin orientation.** The signal pin is placed on the coax axis with the ground pin beside it. The Amphenol drawing would not render in this session, so this comes from transcribed dimensions.
- **Toggle geometry.** The 7101 single-column variant of the AV2 bracket was derived from the 7201 drawing.

None of these parts has a 3D model in the render.

### 8. Courtyard fill and mounting holes

Holes go from 6 to 4:

- **H1/H2:** grounded M3, at the panel end.
- **H3/H4:** unplated, at the tip end, one on each side of the notch. Use **nylon screws and standoffs** there.

The LV region (x ≥ 59 mm, 6,361 mm²) has 32.7% top-side courtyard coverage (Rev B: 14.4%) and 52.8% bottom-side coverage, from the two holders. That is 42.7% of the two-sided placement area.

**Only the two-sided figure meets ≥ 35%.** Reaching 35% on the top side alone needs a 150 × 64 mm board (estimated 35.7%), which means re-placing every band. I kept 150 × 70 mm, the stated stretch target. The holders still fit, and the extra 6 mm buys routing corridors (WIDE_SEL/FINE_SEL along the top edge). This can be reversed if the top-side number matters.

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

**Enclosure: Hammond 1455N2201** ([drawing](https://www.hammfg.com/files/parts/pdf/1455N2201.pdf); DigiKey $38.43, 52 in stock; Mouser not checked).

The board sits on four standoffs so its underside is **22.0 mm above the inner floor**, for example a 20 mm M3 standoff plus a 2 mm spacer. Use metal at H1/H2 and nylon at H3/H4. The BNC and toggle faces sit at the output end plate. 3-D setback from exposed HV conductors to metal, using the drawing's minimum internal height of 49.14 mm:

| Direction | Clearance |
|---|---|
| Down | 22.0 mm minus a 1 mm trimmed W_HV lead tail = 21 mm. The SMD HV parts have no tails. |
| Up | Lid at ≥ 49.14 mm; board top at 23.6 mm. HV parts are ≤ 1.1 mm (1812 C0G T max) and ≤ 0.76 mm (2512). Lead loops at W_HV must stay ≤ 5.5 mm high to keep ≥ 20 mm. |
| Sides | 12.5 mm from the board edge to the rib tips (95 mm internal width), plus ≥ 16 mm from the edge to the nearest HV copper: ≥ 28 mm. |
| Tip end | With the panel parts at the output plate, the 220 mm box leaves roughly 60 mm between the board's tip edge and the tip-end plate (confirm against the drawing's internal length). The leads leave through insulating feedthroughs; their selection is still open, as in Rev B. |

**Trimmer access.** Lid holes go over:

- CT1/CT2 at (62, 23) and (62, 47).
- The RV1/RV2 3296W top screws (bodies at x ≈ 62–71 mm, y = 7 / 63 mm; locate the screw from a sample).
- The SW3 reset at (120, 28.5).
- The D9 LED at (115, 24).

The lid is 25 mm above the board, so hole edges stay ≥ 20 mm from HV copper. The holders hang 20.6 mm under the board, leaving 1.4 mm. Put an insulating sheet on the floor.

Other enclosures considered:

- Hammond 1550G die-cast: internal height 51.1 mm, $30.46. Shorter, so the tip-end clearance is tight.
- 1455U2201: internal height 61.5 mm, $46.92. More than needed.

## Layout notes specific to Rev C

- **Routing.** Hand-authored in [`tools/layout.rs`](../tools/layout.rs), as in Rev B. **No autorouter was used.** Freerouting was only invoked with `--help`; nothing was routed with it or imported.
- **Analog chain.** It runs along the slot axis: U1 → U3 → R69/C61 → R70 → BNC. The range-select ×5 stage and latch sit above it; the warning comparators, ladders and LDOs sit below.
- **Matched lengths.** Tap-to-buffer inputs are 14.478 mm on both legs (the N side jogs to absorb U1's 1.27 mm pin offset). Buffer-to-subtractor paths are 7.565 mm on both legs. Both pairs are checked by `check_pcb.rs`.
- **Reference designators.** They are on the Fab layers. Silk carries outlines and board text only, so DRC including silk reports zero.
- **Component placement.** The holders mount on the bottom with their screw holes outboard. Bottom-flipping mirrors the part, so the top holder's contacts face the tap cell and the bottom holder's face the panel. BAT_P therefore runs on B.Cu along y = 27 mm.

## Rev B issues resolved on the way

These were open identity problems in [`procurement/quote-review.md`](../procurement/quote-review.md):

- R12/R32 are now the orderable `RT0805BRD07220RL`.
- D4–D7 name MDD SS14 (LCSC C2480).
- D8 is Vishay 1N4148W-E3-18 (LCSC C191428).

## Cost (dated 2026-10-20)

Filled in from distributor pages checked on 2026-10-20; see the table at the end of this section.

## Risks and open owner decisions

1. **HVCB2512BDE2M00 stock** (9 at DigiKey, 0 at LCSC). Choose between waiting or pre-ordering, and the 2 × 1 MΩ fallback re-layout.
2. **BNC and 7101 footprint orientation** must be checked against samples or drawings before fabrication.
3. **Top-side fill is 32.7%.** Accept it, or authorize the 150 × 64 mm re-placement.
4. **U12 kept as a separate OPA810.** Confirm, or ask for the ×2 + ×5 pairing.
5. **Kemet 1% C0G select-on-test kits** need sourcing. Several Rev C MPNs have no reviewed LCSC identity (see [`procurement/README.md`](../procurement/README.md)).
6. **Bench items.** Unchanged in kind from Rev B, plus:
   - Per-body VCR at 600 V.
   - OPA2810 input-stage crossover (≈ +2.3 V on +4.8 V) for the ×5 and driver inputs on the extended wide range.
   - Clamp current shared with the OPA2810 ESD diodes.
   - Range-switch transients with the PCB-mount switch.
