# Candidate 24 FMEA: bias-monitor consolidation (one reinforced crossing instead of three)

Date 2026-10-13. Desk study and one offline script. No build was run and no repo file outside this folder was edited.
Repo citations are `file:line` at HEAD `c91678354` (the working tree carries an unrelated, uncommitted stage-28 edit that
shifts `power_stage_120v.ato` by +5 lines after line 30).

```
python3 -I validation-results/11-candidates/c24-monitor-fmea/scripts/fmea_metric.py   # -> results/fmea_metric.{json,md}, exit 0 = invariants hold
```

**Verdict: GO, conditional on mitigation M1 (a dynamic heartbeat through U32). Do not adopt P2 as proposed.**

- **P2 as proposed** adds one dormant single point that hides all three rails: U32 stuck "good". It also adds two more,
  the NAND3 output stuck low and an over-voltage failure of the LS 5 V regulator U37.
  - The class is not new: today's chain already has five such points (U25, R126, C143, U40, and U22/U23 per leg).
  - Still, the failure rate of the modes that hide all three rails rises from 3.65 to 10.03 FIT (×2.7).
  - The rail-weighted dormant exposure rises 7 % (34.4 → 36.9 FIT·rails).
- **P2 + M1** does better than today in every sensitivity case: 13.0 against 34.4 FIT·rails (−62 %), and 1.8 against
  3.65 FIT on the all-three-rails modes.
- **Cost of M1:** +6 placements and +2 BOM lines, about +$0.15.
- **Net candidate change:** −6 placements (not −12), +1 BOM line, about −$1.75 per board with DK/TI-priced ISO7710
  (−$3.95 on JLC prices). The two zero-stock ISO7710s still go.

---

## 1. What the monitors protect, and where their output goes

**The monitored hazard.** F6 drives each FET with a −2 V off-bias. Losing that rail, or leaving its window, causes one of
three failures:
- **False turn-on:** S4/S5 hard turn-ons without the negative rail cause a false turn-on, i.e. shoot-through on a
  650 V bridge, "which the protection chain cannot survive" (`DECISIONS.md:90`). S5 occurs "at every burst and every
  power-up" (`DECISIONS.md:96`).
- **Gate overstress:** a span over-voltage overstresses the 20 V CFD7 gates (`PROPOSALS.md:150`).
- **No UVLO coverage:** UCC21550's UVLO does not see a collapsed negative rail, which is why the monitor is mandatory
  (`DECISIONS.md:111`).

The end consequence of a masked rail fault is therefore shoot-through or FET failure. Containment is F1 plus copper,
with BR1 sacrificial (`DECISIONS.md:839-848`).

**What each monitor detects** (`elec/src/f6_bias.ato:111-264`, `native-21/ECO.md:69-91`). There is one monitor per
domain: LS (`V15_LS / LEG_RET / N_LS`), HS-A and HS-B. Each has:
- an LM339B (U29/U30/U31) with four open-collector outputs wired together into one `good` node (`f6_bias.ato:176-189`);
- four window checks against a TL431 2.5 V reference halved to 1.25 V:
  - **negative rail:** SRC−N within −2.206 to −1.799 V;
  - **span:** P−N within 16.2 to 17.8 V;
- 1 nF on each comparator input.

What the window catches and misses:
- **Caught:** a dead reference (open or short) trips a comparator.
- **Caught:** a dead span leaves side 1 of the isolator unpowered, so its default output applies.
- **Missed:** the 2.3–3.0 V "sliver", where the LM339B is below its supply minimum. The driver UVLO holds the gates low
  there (`g05-g07-drive-monitor/results/truth_table.md`).

**Today's path to DIS.** The chain is shown in the §2 diagram. Nodes and citations:
- `good` reaches the NPN through D14–16 and Q7–9 (`f6_bias.ato:191-205`).
- `rpull` is the 10 k pull-up to the local 5 V (TPS70950 U37/U38/U39).
- The ISO7710s are U32/U33/U34 (`f6_bias.ato:206-243`).
- U25 is the OR3 (`power_stage_120v.ato:899-903`).
- The 10 k / 1 nF RC is R126/C143 (`:904-914`); U40 is the SN74LVC1G14 that outputs BIAS_GOOD (`:915-923`).
- U22/U23 compute `DIS = NAND(PERMIT, BIAS_GOOD)` per leg, with a 10 k pull-up on DIS (`:76-79`, `:140-153`;
  DECISIONS item 27, `DECISIONS.md:941-949`).

Logic levels and timing:
- **Healthy:** the NPN is on, IN is low and OUT (BAD) is low.
- **Fault:** any window violation, or a dead LDO (isolator side 1 unpowered), gives OUT high, so DIS goes high.
- **Timing:** rail faults are ms-scale (reservoirs), and the RC costs ~6–10 µs (`power_stage_120v.ato:904-906`).
- **No latch:** there is no hardware latch (`ECO.md:94-96`).

**Nobody reads BIAS_GOOD.** It reaches no J4 pin. J4 carries V15, V3V3, four PWMs, PERMIT, BUS_FAULT, VBUS±, CT_ZC, CT_MON,
LINE_ZC and returns (`power_stage_120v.ato:646-662`); `PROPOSALS.md:36-38` says the same. Consequences:
- No variant has any diagnostic of the monitor chain.
- Every fault that freezes the chain at "good" stays dormant for the product's life.
- The power-up check mentioned in `truth_table.md` ("BIAS_BAD must read 1 before …") has no reader on this board.

**Isolator default states (fetched 2026-10-13):**

| Part | Default output (input open or side 1 unpowered) | Side-1 thresholds | Side 2 unpowered | Source |
|---|---|---|---|---|
| ISO7710 (non-F) | **High** | Powered-up ≥ 2.25 V, powered-down ≤ 1.7 V; output undetermined between 1.7 and 2.25 V | Output undetermined | SLLSER9E §7.3 Table 7-1, §7.4 Table 7-2 and its notes 1–2, https://www.ti.com/lit/ds/symlink/iso7710.pdf |
| ISO6721FB | **Low** (F suffix); 1 forward + 1 reverse channel; basic insulation (3000 Vrms, VIORM 637 Vpk) | Powered-up ≥ 1.71 V, powered-down ≤ 1.05 V; undetermined at 1.89–2.25 V and 1.05–1.71 V | Output undetermined | SLLSFJ0F Table 8-1, Table 8-2 and notes 1/3, VIORM from the insulation-specifications table, https://www.ti.com/lit/ds/symlink/iso6721.pdf |

A note on the encoding. Both parts use on-off keying (SLLA504 / SFFS130 Fig. 1-1). The default state is the "no carrier"
state, and in both designs the "no carrier" state means bad / not good:
- **ISO7710 (non-F):** "good" (low) needs an active carrier.
- **ISO6721FB:** "good" (high) needs an active carrier.
- **Consequence:** a dead transmitter, a dead side 1 or an open input all fail safe. Only an active wrong state can mask:
  an output stage stuck at the good level, or an undetermined output.

**TI failure-mode data used** (fetched 2026-10-13, text in `evidence/ds/`, hashes in `evidence/ds/MANIFEST.txt`):

| Part | Rate (IEC TR 62380) | Die failure-mode distribution (FMD) | Source |
|---|---|---|---|
| ISO7710 DW-16 | 26 FIT | OUT undetermined 40 %, out of V/t spec 30 %, stuck to default 24 %, stuck high 3 %, stuck low 3 % | SLLA504 Tables 2-3, 3-1, https://www.ti.com/lit/pdf/SLLA504 |
| ISO6721(F) D-8 | 10 FIT | 35 / 30 / 25 / 5 / 5 % (same order) | SFFS130 Tables 2-1, 3-1, https://www.ti.com/lit/pdf/sffs130 |
| LVC1G logic (proxy: SN74LVC1G125-Q1 SOT-23) | 6 FIT | stuck-at 20 %, open (Hi-Z) 20 %, out of spec 40 %, any two pins shorted 20 % | SFFS754 Tables 2-1, 3-1, https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/151/SN74LVC1G125_2D00_Q1-FS.pdf |

TI publishes no functional-safety (FS) document for the G10, G14, G17, G132 or G332 parts. The proxy is the same LVC1G
family in the same package class.

Rates and modes for passives, the MMBT3904, the 1N4148W and the TPS70950 are **assumptions**, listed in the script
header. They are varied in the sensitivity block.

---

## 2. Block diagrams

### Today (stage 22): three reinforced crossings

```
 HS-A island (n_ha, rides SW_A)          HS-B island (n_hb, rides SW_B)          LS island (n_ls / LEG_RET)
 RECOM U41 -> P_HA/N_HA                  RECOM U42 -> P_HB/N_HB                  U26 TPS7A47 -> V15_LS/N_LS
 TL431 U19 + LM339B U30 (4 windows)      TL431 U21 + LM339B U31                  TL431 U17 + LM339B U29
   'good' --D15--Q8 (NPN inverter)          'good' --D16--Q9                       'good' --D14--Q7
   U38 5V --rpull--> IN                     U39 5V --rpull--> IN                   U37 5V --rpull--> IN
 ===[U33 ISO7710 reinforced]===          ===[U34 ISO7710 reinforced]===          ===[U32 ISO7710 reinforced]===   <- 8 mm D5 barrier
   BIAS_HA_BAD                              BIAS_HB_BAD                            BIAS_LS_BAD
        \______________________________________|______________________________________/
                                               v
 SELV (V3V3 from J4.3):         U25 OR3 -> R126 10k / C143 1nF -> U40 G14 -> BIAS_GOOD
                                       -> U22 NAND(PERMIT,BIAS_GOOD) -> DIS leg A (U1)
                                       -> U23 NAND(PERMIT,BIAS_GOOD) -> DIS leg B (U2)
 Readers of BIAS_GOOD: U22, U23 only. No J4 pin.
```

### Proposed P2 (`PROPOSALS.md:94-127`): one reinforced crossing

```
 HS-A island                               HS-B island
 LM339B U30 'good' --rpull(U38 5V)--> INB  LM339B U31 'good' --rpull(U39 5V)--> INB
 ---[ISO6721FB basic, side1 U38 5V]---     ---[ISO6721FB basic, side1 U39 5V]---   <- HS<->LS functional barrier (3.2 mm rule)
        OUTB = good_ha (LS 5V side)               OUTB = good_hb
                 \                               /
 LS island:  NAND3 (SN74LVC1G10 on U37 5V): inputs good_ls (LS wired-AND, rpull to U37), good_ha, good_hb
             output = "any bad" -> U32 IN
 ===[U32 ISO7710 reinforced, side1 = U37 LS 5V]===                                  <- the only 8 mm crossing of the group
 SELV:       R126/C143 RC -> U40 -> BIAS_GOOD -> U22/U23 (unchanged; U25 OR3 deleted)
```

This diagram shows only the changes; the notice stage (D14–16, Q7–9, rnotice, rbase) goes in all three monitors.

### P2 + M1 heartbeat (this FMEA's mitigation)

```
 HS-A / HS-B islands: as P2 (ISO6721FB, OUTB = good_hx, default LOW)
 LS island:
   good_ls node (LM339B U29 wired-AND, rpull 10k to U37 5V)
      <-- BAT54A (common anode at the node; cathodes to OUTB_A, OUTB_B): either HS "not good" pulls the node low
   U_osc SN74LVC1G132 (Schmitt NAND): A = node, B = RC (R_osc 4.99k from Y, C_osc 330 pF to n_ls)
      all good -> oscillates ~0.5-2 MHz;  any bad -> Y static HIGH
 ===[U32 ISO7710 reinforced]=== carries the square wave
 SELV: U32 OUT -> 100 nF + 100 nF (series) -> BAT54S (shunt to GND, series to hold) -> C_hold 1 nF || R_bleed 100k
       -> U40 SN74LVC1G17 (non-inverting Schmitt, swapped in place) -> BIAS_GOOD -> U22/U23 (unchanged)
 No wave (any stuck/static/unpowered element) -> hold bleeds below VT- in <= ~90 us -> BIAS_GOOD = 0 -> DIS high.
```

**Why the heartbeat fixes the gap.** In P2 the item that turns "one rail masked" into "three rails masked" is U32. A
static signal through U32 cannot tell "all good" from "U32 output stuck low". In M1 the safe signal is a square wave
whose energy is pumped into the hold node:
- **Static faults:** any stuck-high, stuck-low, open, unpowered, undetermined-static or default state of the
  oscillator, U32, the LS 5 V rail or the pump stops the wave. That drops BIAS_GOOD, so the fault is **announced**
  (the hob stops) instead of dormant.
- **Glitches:** a common-mode transient (CMTI glitch) can add or drop a pulse but cannot sustain a wave, so it neither
  masks a fault nor causes a nuisance trip; one missed pulse costs about 40 mV of the hold voltage.

---

## 3. FMEA

### Scales

| Score | S: system effect of this failure alone | O: mode rate (FIT = failures per 1e9 h) | D: detection in the field |
|---|---|---|---|
| 10 | Hazard from a single fault | — | — |
| 9 | — | — | Dormant: no diagnostic; found only after a rail fault does damage |
| 8 | Dormant loss of bias protection on 3 rails; the next rail fault on any rail gives shoot-through or gate overstress with drive enabled | — | — |
| 7 | Dormant loss of bias protection on 1–2 rails | — | — |
| 6 | — | > 15 FIT | — |
| 5 | Dormant loss of one window (partial) | 5–15 | — |
| 4 | — | 2–5 | Production test only (forced rail fault at end of line) |
| 3 | Announced: drive disabled, hob stops (availability only) | 0.5–2 | — |
| 2 | Nuisance or margin loss | 0.1–0.5 | — |
| 1 | No effect | < 0.1 | Announced immediately (the failure disables the drive) |

Risk priority number (RPN) = S × O × D. In the status column, **Dormant** means latent (the fault shows no symptom).
**Announced** means the failure itself disables the drive. The metric (§4) counts only dormant modes that mask a fault
(k > 0).

### 3a. Rows common to all variants (per rail unless noted; unchanged by candidate 24)

| # | Item / function | Failure mode | Local effect | System effect (does a bias fault still disable the drivers?) | Detection | S | O | D | RPN | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | Rail (the monitored event) | NEG UV/OV, SPAN UV/OV, rail dead | A comparator pulls `good` low, or the isolator's side 1 is unpowered so its default applies | Yes: DIS high within ~10 µs (today), ≤ 90 µs (M1) | Function | — | — | — | — | Announced |
| C2 | LM339B output stage (1 of 4) | Open (cannot pull low) | That window is never reported | Partly: the other three windows still trip; e.g. span-OV lost leaves gate overstress unseen | None | 5 | 2 | 9 | 90 | Dormant |
| C3 | LM339B | Output shorted low, or stuck tripped | `good` = 0 | Drive disabled | Hob will not run | 3 | 2 | 1 | 6 | Announced |
| C4 | TL431 reference | Open or short | `halfref` goes to 8.5 V or 0 V; the UV or OV comparators trip | Drive disabled (`truth_table.md` rows TL431_OPEN/SHORT) | Hob will not run | 3 | 2 | 1 | 6 | Announced |
| C5 | Divider resistors (8 per rail) | Open | Top resistor of a UV divider open: trips. Bottom resistor of a UV divider, or top of an OV divider, open: that window is lost | Half the cases announced, half partial-dormant (as C2) | None for the dormant half | 5 | 2 | 9 | 90 | Mixed |
| C6 | 1 nF input caps (4 per rail) | Short | UV input shorted: trips. OV input shorted: that window is lost | As C5 | None | 5 | 2 | 9 | 90 | Mixed |
| C7 | Supply (P−N) in the 2.3–3.0 V "sliver" | LM339B below its 3 V minimum while the isolator side 1 is up | `good` may float high | Not detected by any variant. The UCC21550 UVLO (9.2 V, option B) holds the outputs low | Driver UVLO | 3 | 1 | 1 | 3 | Covered by UVLO |
| C8 | U40 Schmitt → BIAS_GOOD | Y stuck high, Y open (U22/U23 inputs float), or a Y–VCC bridge | BIAS_GOOD reads 1 | **No** for all 3 rails. U40 sits after any isolator, so it stays a dormant single point in every variant | None | 8 | 3 | 9 | 216 | Dormant |
| C9 | U22 / U23 DIS NAND | Y stuck low | DIS low on that leg | **No** for that leg's rails (LS + its HS), **and PERMIT is also defeated** | None (the hob runs; PERMIT-low may not stop it) | 8 | 3 | 9 | 216 | Dormant |
| C10 | U22 / U23 | Y stuck high, or open (10 k pulls DIS high) | DIS high | Drive disabled | Hob will not run | 3 | 3 | 1 | 9 | Announced |
| C11 | V3V3 (J4.3) | Lost | SELV logic and UCC21550 VCCI are both unpowered | The driver holds its outputs low (VCCI UVLO, `truth_table.md`) | Controller | 3 | — | 1 | — | Announced |
| C12 | Gate solder joints at the inputs of the combining gate (manufacturing) | Open | Floating CMOS input | Can mask the rail on that input (today, P2) or all three (M1's G132 pin A) | **End-of-line forced-rail test** (recommended, §5) | 7–8 | 2 | 4 | 64 | Production-detectable |

### 3b. Today (stage 22): the rows that candidate 24 changes

| # | Item | Failure mode | Local effect | System effect | Detection | S | O | D | RPN | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | U32/U33/U34 ISO7710 (one rail each) | OUT stuck low (3 % of 26 FIT) | BAD reads low | **No**, for that 1 rail | None | 7 | 3 | 9 | 189 | Dormant |
| A2 | " | OUT undetermined (40 %) | BAD at either level | Possibly no, 1 rail | None | 7 | 6 | 9 | 378 | Dormant |
| A3 | " | Stuck at default (24 %), stuck high (3 %) | BAD = 1 | Drive disabled | Hob will not run | 3 | 5 | 1 | 15 | Announced |
| A4 | " | Side 1 (local 5 V LDO) lost | Default high | Drive disabled | Hob will not run | 3 | 3 | 1 | 9 | Announced |
| A5 | " | Side 2 (V3V3) lost | Output undetermined | Drivers off (C11) | — | 3 | — | 1 | — | Announced |
| A6 | " | CMTI glitch: U33/U34 rated 85 kV/µs min against ~95 V/ns edges (0.89×; `power_stage_120v.ato:904-906`) | Pulse ≤ µs at either level | Toward bad: absorbed by the RC (needs > 5.95 µs). Toward good during a fault: masks only for the pulse, and rail faults are ms-scale | — | 2 | — | 1 | — | Covered by filter |
| A7 | " | Barrier breakdown | **HS switch node shorted onto SELV** (U33/U34) | Shock hazard; reinforced insulation required, short excluded by VDE 0884-17 reinforced qualification | Type and routine test | 10 | 1 | 9 | 90 | Fault exclusion |
| A8 | " pins (DW-16, SLLA504 Table 4-8) | Adjacent short VCC1–IN | IN high, so BAD | Announced | — | 3 | 1 | 1 | 3 | Announced |
| A9 | Q7–9 MMBT3904 | C–E short | IN held low, so good | **No**, 1 rail | None | 7 | 2 | 9 | 126 | Dormant |
| A10 | D14–16 1N4148W | Short | NPN base sits at LM339B VOL ≤ 0.4 V at 4 mA (SLCS006Z §6.7); marginal at 125 °C | Possibly no, 1 rail | None | 7 | 2 | 9 | 126 | Dormant |
| A11 | rnotice / Q open, D open | Open | NPN off, so BAD | Announced | — | 3 | 2 | 1 | 6 | Announced |
| A12 | U37/U38/U39 TPS70950 | Output collapses to 0 | Isolator side 1 unpowered, default high | Announced | — | 3 | 3 | 1 | 9 | Announced |
| A13 | " | Pass element shorted: 15–17 V on the 5 V net | ISO7710 side 1 above its 6 V absolute maximum; state unknown | Possibly no, **1 rail** | None | 7 | 3 | 9 | 189 | Dormant |
| A14 | U25 OR3 (SELV) | Y stuck low (no fault) | BIAS_BAD_RAW = 0 | **No, all 3 rails** | None | 8 | 3 | 9 | 216 | Dormant |
| A15 | " | Y open | RC node floats | Possibly no, 3 rails | None | 8 | 3 | 9 | 216 | Dormant |
| A16 | " | Adjacent short A–GND or B–GND (SOT-23-6, pins 1–2, 2–3) | That input reads 0 | No, 1 rail | None | 7 | 3 | 9 | 189 | Dormant |
| A17 | R126 10 k | Open | U40 input floats on C143 | Possibly no, 3 rails | None | 8 | 2 | 9 | 144 | Dormant |
| A18 | C143 1 nF | Short | BIAS_BAD_FLT held low | **No, 3 rails** | None | 8 | 2 | 9 | 144 | Dormant |
| A19 | C143 open / R126 short | — | Filter lost | CMTI nuisance trips possible | Hob trips | 2 | 2 | 1 | 4 | Announced |

### 3c. P2 as proposed

| # | Item | Failure mode | Local effect | System effect | Detection | S | O | D | RPN | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | ISO6721FB (one HS rail each) | OUTB stuck high (5 % of 10 FIT) | good_hx = 1 | **No**, 1 rail | None | 7 | 2 | 9 | 126 | Dormant |
| B2 | " | OUTB undetermined (35 %) | Either level | Possibly no, 1 rail | None | 7 | 4 | 9 | 252 | Dormant |
| B3 | " | Stuck at default (low) or stuck low | Not good | Announced | — | 3 | 3 | 1 | 9 | Announced |
| B4 | " | Side 1 (U38/U39 HS 5 V) lost | Default **low**, i.e. not good | Announced | — | 3 | 3 | 1 | 9 | Announced |
| B5 | " | Side 2 (U37 LS 5 V) lost | OUTB undetermined, but NAND3 and U32 side 1 are also unpowered, so U32 defaults high | Announced | — | 3 | 3 | 1 | 9 | Announced |
| B6 | " | rpull open | INB internal pull-down (F input) reads low, i.e. not good | Announced | — | 3 | 2 | 1 | 6 | Announced |
| B7 | " pins (SFFS130 Table 4-4; reverse INA tied to GND2, OUTA no-connect) | OUTA–INB: INB forced low. GND1–INB: low. GND2–OUTB: low. OUTB–INA: OUTB forced low. INA–VCC2: shorts LS 5 V, so U32 defaults high | All read not good | Announced. The pinout is fail-safe for every adjacent short **because INA is tied low**; keep it that way | — | 3 | 1 | 1 | 3 | Announced |
| B8 | " | Channel crosstalk (reverse into forward) | The reverse channel is static low | Coupling can only pull toward low (not good) | — | 2 | 1 | 1 | 2 | Fail-safe |
| B9 | " | CMTI glitch (100 kV/µs min at VCM 1200 V, SLLSFJ0F §6.9 (5 V), against ~95 V/ns: 1.05×) | Pulse at NAND3, then U32 | As A6 | — | 2 | — | 1 | — | Covered by filter |
| B10 | " | Barrier breakdown (basic, VIORM 637 Vpk) | **SW_x shorted to the LS domain**: acts like a shorted low-side switch | Shoot-through at the next high-side on, cleared by F1. Same class as the UCC21550 channel-to-channel insulation already present. **No SELV exposure** (an improvement over A7 for two crossings) | — | 10 | 1 | 9 | 90 | Certifier question |
| B11 | U37 TPS70950 (now LS 5 V for NAND3, both ISO6721 side 2 and U32 side 1) | Pass element shorted: 15 V on the 5 V net | NAND3, ISO6721 side 2 and U32 side 1 all exceed their 6 V absolute maximum | Possibly no, **3 rails** (new common cause) | None | 8 | 3 | 9 | 216 | Dormant |
| B12 | " | Drifts into 1.7–2.25 V | U32 side 1 and ISO6721 side 2 output undetermined | Possibly no, 3 rails | None | 8 | 1 | 9 | 72 | Dormant |
| B13 | NAND3 SN74LVC1G10 | Y stuck low ("all good") | U32 IN low | **No, 3 rails** | None | 8 | 3 | 9 | 216 | Dormant |
| B14 | " | Y open | U32 IN open, so ISO7710 defaults **high** | Announced (better than A15) | — | 3 | 3 | 1 | 9 | Announced |
| B15 | " | Adjacent short C–VCC (pins 5–6; 1–2, 2–3 and 4–5 are safe) | Input C stuck good | No, 1 rail | None | 7 | 2 | 9 | 126 | Dormant |
| B16 | NAND3 inputs from OUTB | Open pin or trace | Floating CMOS input | Possibly no, 1 rail. P2 as drafted has **no pull-down** on good_ha/good_hb | None | 7 | 2 | 9 | 126 | Dormant |
| B17 | **U32 ISO7710 (now combined)** | OUT stuck low (3 %) | BIAS_BAD = 0 | **No, all 3 rails** (the risk stated in QUEUE.md:11) | None | 8 | 3 | 9 | 216 | **Dormant (new 3-rail point)** |
| B18 | " | OUT undetermined (40 %) | Either level | Possibly no, **3 rails** | None | 8 | 6 | 9 | 432 | **Dormant (new 3-rail point)** |
| B19 | " | Stuck at default or high; side 1 (U37) lost | BAD = 1 | Announced | — | 3 | 5 | 1 | 15 | Announced |
| B20 | " | CMTI: U32 now spans LS domain → SELV. LEG_RET moves at line and rectifier rates, not at SW edges | Fewer glitches than U33/U34 saw | — | — | 1 | — | 1 | — | — |
| B21 | R126, C143, U40, U22/U23 | As A17–A19, C8, C9 | | | | | | | | Unchanged |

### 3d. P2 + M1 heartbeat

Rows not listed here are as P2: B1–B10, B15 now in the diode-AND, B20 and B21 (with U40 as G17).

| # | Item | Failure mode | Local effect | System effect | Detection | S | O | D | RPN | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | BAT54A diode-AND (one diode per HS rail) | Open | That HS rail's veto is lost | **No, 1 rail** (as A1/B1 today) | None | 7 | 2 | 9 | 126 | Dormant |
| H2 | " | Short | ISO6721 OUTB (high, rail good) fights the LM339B sink (≥ 6 mA at 1.5 V, SLCS006Z §6.7) on the LS node | Possibly no, for an LS fault while that HS rail is good | None | 7 | 2 | 9 | 126 | Dormant |
| H3 | SN74LVC1G132 oscillator | Any stuck-at, Hi-Z, adjacent pin short (all give a static Y), or supply lost | No wave | Announced (hold bleeds, BIAS_GOOD = 0) | Hob stops | 3 | 3 | 1 | 9 | **Announced** |
| H4 | " | Out of spec (frequency or threshold) | Wave too slow or too fast | Usually nuisance. A corrupted A-input threshold could oscillate while A is low (counted at k_o, 0 in the base case) | Hob trips | 3 | 3 | 1 | 9 | Announced, mostly |
| H5 | R_osc / C_osc | Open or short | Static Y | Announced | — | 3 | 2 | 1 | 6 | Announced |
| H6 | **U32 ISO7710** | Stuck low, high, default, or undetermined-static; side 1 or side 2 lost | No wave | **Announced** (this was B17/B18) | Hob stops | 3 | 5 | 1 | 15 | **Announced** |
| H7 | U32 | CMTI glitch | One extra or missing pulse | Cannot sustain a wave, so no masking and no nuisance | — | 1 | — | 1 | — | — |
| H8 | U37 LS 5 V | Pass element shorted (15 V) | G132 above its 6.5 V absolute maximum | Oscillator damaged, so the wave stops: announced (was B11) | — | 3 | 3 | 1 | 9 | Announced |
| H9 | U37 | Drifts into 1.89–2.25 V | ISO6721 OUTB undetermined while G132 (works down to 1.65 V) may still run | Possibly no, HS rails | None | 7 | 1 | 9 | 63 | Dormant (rare) |
| H10 | C_pump (2 × 100 nF in series) | One shorts | DC still blocked by the other | No effect alone; a second short makes the scheme static | None | 2 | 2 | 9 | 36 | Dormant, needs a 2nd fault |
| H11 | C_pump | Open | No transfer | Announced | — | 3 | 2 | 1 | 6 | Announced |
| H12 | BAT54S pump diodes | Shunt open or short; series open | No DC restore or no transfer | Announced | — | 3 | 2 | 1 | 6 | Announced |
| H13 | " | Series short | The hold follows the AC; no DC passes during a fault | Nuisance or toggling, never a mask (DC is blocked by C_pump) | Hob trips | 2 | 2 | 1 | 4 | Announced |
| H14 | C_hold 1 nF | Short | Hold = 0 | Announced | — | 3 | 2 | 1 | 6 | Announced |
| H15 | " | Open | U40 follows the wave, so DIS chatters | Drive malfunction, announced. The UCC21550 interlock and dead time are unaffected | Hob misbehaves or trips | 3 | 2 | 1 | 6 | Announced |
| H16 | R_bleed 100 k | Open | Hold keeps its charge when the wave stops (U40 input leakage only) | Possibly no, 3 rails | None | 8 | 2 | 9 | 144 | Dormant (same order as A17). Optional fix: two bleed resistors in parallel, +1 placement |
| H17 | U40 SN74LVC1G17 | Y stuck high, Y open, Y–VCC | BIAS_GOOD = 1 | No, 3 rails. The A–GND bridge is now **safe** (it was a mask with the inverting G14) | None | 8 | 3 | 9 | 216 | Dormant (as C8) |
| H18 | Detection latency | — | Wave stop → hold below VT− | ≤ 89 µs worst case (script) against ~6–10 µs today. Rail faults are ms-scale (`power_stage_120v.ato:904-906`) | B4 timing rerun | 2 | — | 4 | — | Margin |

---

## 4. Quantified exposure (`results/fmea_metric.md`)

The metric is the rail-weighted dormant masking rate, RWL:

- **Definition:** RWL = Σ over failure modes of (FIT × P(mode masks) × rails hidden).
- **Why it works:** no variant has a diagnostic, so P(rail fault meets a pre-existing mask) ≈ RWL × λ_rail × T²/2.
- **Consequence:** RWL ratios are hazard ratios, and λ_rail cancels.
- **U22/U23:** they contribute 2.4 FIT·rails in every variant and are kept out of the comparison.

| Variant | RWL [FIT·rails] | FIT of modes hiding all 3 rails |
|---|---:|---:|
| A: today (stage 22) | **34.44** | **3.65** |
| P1 (reference: per-rail inverter) | 34.29 | 3.65 |
| P2 as proposed | 36.89 (+7 %) | 10.03 (×2.7) |
| **P2 + M1 heartbeat** | **13.0 (−62 %)** | **1.8 (−51 %)** |

Sensitivity (RWL):

| Case | A | P1 | P2 | P2 + M1 |
|---|---:|---:|---:|---:|
| Base (k_u = 0.5, k_o = 0, passives as assumed) | 34.4 | 34.3 | 36.9 | 13.0 |
| Undetermined always masks (k_u = 1) | 57.2 | 57.1 | 63.4 | 20.9 |
| Undetermined never masks (k_u = 0) | 11.6 | 11.5 | 10.4 | 5.1 |
| Out-of-spec masks half (k_o = 0.5) | 53.3 | 56.8 | 58.8 | 23.2 |
| Passives ×5 | 47.6 | 39.7 | 42.3 | 19.8 |
| LDO over-voltage ×3 | 40.4 | 40.3 | 46.9 | 17.0 |
| Worst (k_u = 1, k_o = 0.5, passives ×5) | 91.7 | 87.4 | 93.1 | 40.3 |

How to read this:
- **P2 against today:**
  - P2's rail-weighted exposure is within ±10 % of today, because deleting the NPN/diode notice stage removes per-rail
    masks.
  - Its exposure to a single fault that hides **all three** rails nearly triples.
  - P2 is lower than today only when the undetermined state is assumed never to mask.
- **M1:** it beats today in every case; the script asserts this as an invariant.
- **Absolute figures:** these are reliability-handbook figures (IEC TR 62380) for ranking, not field predictions.

---

## 5. The key question, answered

**Can a single failure in the consolidated design leave a bias fault undetected while the drivers stay enabled?**

**Yes, for P2 as proposed.** Each of these failures is silent on its own:
- U32 stuck low or undetermined (B17/B18);
- NAND3 output stuck low (B13);
- U37 over-voltage damaging the LS-side logic (B11).

None changes behaviour until a rail later leaves its window, so it stays dormant for the product's life. When that rail
fault comes, on any of the three rails, the drivers keep switching:
- a lost negative rail gives S4/S5 false turn-on, i.e. shoot-through;
- a span over-voltage overstresses the gates.

The controller cannot see either the dormant fault or the rail fault, because BIAS_GOOD reaches no J4 pin.

**Is that worse than today?** It is **worse in degree, not in kind.** Today's chain already has dormant single points
that hide all three rails: U25 stuck low or open, R126 open, C143 short, U40 stuck high, open or bridged. U22/U23 stuck
low also hides a leg's rails **and** PERMIT.

P2 moves U32 from hiding one rail to hiding three, and U32 is the largest single contributor: the ISO7710 is 26 FIT
with 43 % of its modes stuck low or undetermined. The FIT of modes that hide all three rails therefore goes from 3.65 to
10.03.

The proposal's note that a power-up check "tests U32's high state only" (`PROPOSALS.md:125`) is moot. No circuit or
controller reads BIAS_BAD, so that check cannot be built without a new J4 signal.

**Mitigations considered:**

| Mitigation | Effect on the new 3-rail single point | Cost | Verdict |
|---|---|---|---|
| **M1: toggling heartbeat through U32** (diode-AND veto, G132 gated oscillator, SELV charge pump, U40 → G17) | Every U32, oscillator, LS 5 V and pump fault becomes announced. The NAND3 is gone; the diode-AND has no 3-rail mode. Leaves only U40, R_bleed and U22/U23, which are dormant today too | +6 placements, +2 lines, about +$0.15 | **Adopt** |
| M2: controller power-on test forcing a fault | Needs a controller → HOT test input: another reinforced crossing, plus a readback pin. J4 is full (`power_stage_120v.ato:646-662`) | J4 2×9 plus controller change plus a crossing | Reject: defeats the candidate |
| M3: ISO6721FB second (reverse) channel echoes the first | Tests only the ISO6721, not U32 (the new common point); the echo comparison would need its own crossing | +2–4 parts | Reject: wrong target |
| M4: BIAS_GOOD merged into BUS_FAULT (J4.10) for a power-up readback | BUS_FAULT is already high at power-up (U9 defaults high until HOT5 is valid, `FAULT-INTERFACE.md:13-18`), so the controller cannot tell the bias contribution apart. It also changes the interlock's latch semantics | +2 placements (NOR3 swap + NAND2) | Reject as the primary measure. Keep as a later diagnostic option if J4 grows |
| M5: dual-channel reinforced isolator (ISO7720-class) with complementary encoding plus a SELV check gate | U32 stops being a single point, but the loss of redundancy stays dormant and a common-die failure remains | About +6 placements, a different isolator line | Reject: M1 is cheaper and self-revealing |
| (P1 instead of P2) | No new common point | −9 placements but keeps three reinforced ISO7710s (two of them zero-stock) | Fallback if M1 fails its bench check |

**M1 circuit and sizing** (`fmea_metric.py heartbeat_sizing`; thresholds from SCES546E §5.5 and SCES351Y Table 5-1):
- **Oscillator:** G132 on LS 5 V with 4.99 k / 330 pF runs at 0.52–2.2 MHz across the threshold corners (period
  0.46–1.93 µs). ISO7710 is rated 100 Mbps.
- **Diode-AND low level:** ISO6721 VOL ≤ 0.4 V at 4 mA (SLLSFJ0F §6.9) plus a 0.35 V Schottky gives 0.75 V, against G132's
  VT− ≥ 1.41 V at 4.5 V: 0.66 V margin.
- **Pump:**
  - Peak voltage: from J4.3 at 3.135 V min, minus ISO7710 VOH ≤ 0.3 V, minus two Schottky drops, the peak is ≥ 2.135 V.
  - Hold: with 2 × 100 nF series pump and 1 nF / 100 k hold, the hold sits at 2.13 V with 41 mV ripple.
  - Margins: 0.17 V over G17's VT+ max of 1.92 V (start), and 0.89 V over its VT− max (run).
- **Fault response:** ≤ 89 µs from the wave stopping to BIAS_GOOD = 0, at the slowest VT− of 0.89 V.
- **Parts lines:** all passives reuse existing lines (C100n0603, C330pC0G0603, 1 nF C0G, R100k0603, Bias4k99), and U40
  moves to the G17 line (already used by U15 and U24).
- **Assumptions:** the Schottky Vf of 0.35 V is assumed, not cited.
- **Still to verify:** SPICE with the ISO7710 output impedance, then a bench capture of DIS against a forced rail fault.

**Recommended in every variant (not counted in the cost).** Add an end-of-line forced-rail test:
- Pull each monitor's `uv` node low through a test pad.
- Check that DIS is high and the driver outputs are low.

This catches manufacturing-induced dormant masks (row C12: solder opens or bridges at gate inputs, NAND3/G132 pin A,
U40) that no field mechanism catches. `ECO.md:93-94` already asks for these captures at bring-up.

---

## 6. Recommendation

**GO for candidate 24 with M1 (heartbeat), at the following net change** (`results/fmea_metric.json` → `placements`):

| | Placements | BOM lines | $ per board at 500 |
|---|---:|---:|---:|
| P2 as proposed (`PROPOSALS.md:116`) | −12 | −1 | −1.9 (DK/TI-priced ISO7710) / −4.1 (JLC) |
| M1 heartbeat | **+6** | +2 | ≈ +0.15 (estimate; prices not looked up) |
| **Net** | **−6** | **+1** | **≈ −1.75 / −3.95** |

M1's part changes:
- **Out:** NAND3 + its 100 nF, R126, C143.
- **In:** BAT54A, SN74LVC1G132 + 100 nF, 4.99 k, 330 pF, 2 × 100 nF, BAT54S, 1 nF, 100 k.
- **Swapped in place:** U40 SN74LVC1G14 → SN74LVC1G17.
- **Lines:** +BAT54A, +BAT54S, +SN74LVC1G132, −SN74LVC1G14.

What candidate 24 keeps:
- two zero-stock ISO7710s off the BOM (ISO7710 count 4 → 2);
- monitor-group reinforced HOT→SELV crossings 3 → 1, which also removes two places where a barrier failure would put the
  switch node onto SELV (A7 against B10);
- one 8 mm barrier to hold in layout instead of three;
- −62 % dormant masking exposure against today.

Conditions:
1. **Implement M1, not bare P2.** Keep the ISO6721FB reverse input INA tied to GND2 and OUTA unconnected; this makes the
   pin-short analysis (B7) fail-safe.
2. **Schematic checks before layout:**
   - SPICE the pump and oscillator with the ISO7710 output model at the 3.135 V / −40 / 125 °C corners.
   - Confirm stock and JLC class for BAT54A, BAT54S and SN74LVC1G132.
3. **Timing:** rerun the B4 timing endpoint (comparator → driver output, `ECO.md:98-100`) with ≤ 90 µs. Get bench
   evidence that the fastest real rail collapse (a module output short, or a gate short) cannot cross the −1.6 V F6
   limit within ~100 µs.
4. **Audit:** `audit.rs` needs the ISO6721FB default-low exception, the G132/pump/G17 identity checks, and a mutation
   test that removes the pump series cap (proving that a static path fails).
5. Optional, +1 placement: a second R_bleed in parallel removes H16, the last 3-rail dormant mode that M1 introduces.
6. The certifier questions below must be answered before the stage is accepted.

If M1 fails its SPICE or bench margin check, fall back to **P1** (−9 placements, no new common point; `PROPOSALS.md:129-139`).

## 6a. SPICE check of the pump (2026-10-14): the hand-sized M1 fails, the buffered M1b passes

```
python3 -I validation-results/11-candidates/c24-monitor-fmea/scripts/m1_pump_spice.py   # ngspice, ~3 min, exit 0 = chosen design passes every corner
```

**Method.** ngspice corner sweep, 96 corners per design:
- VCC2 at 3.135 and 3.465 V; −40, 25 and 125 °C;
- oscillator period 0.42 µs and 2.09 µs (the G132 threshold, LS 5 V, R and C extremes);
- two driver output resistances;
- G17 input leakage at ±5 µA;
- the wave stopping either stuck low or stuck high.

Each design is also rerun with one of the two series pump caps shorted (H10). BAT54 is fitted to the Diodes DS11005 VF **maxima**. G17 thresholds are interpolated between the datasheet's 3 V and 4.5 V rows. The four checks:

| Check | Pass condition |
|---|---|
| Start | Hold ≥ VT+max + 0.1 V |
| Missed pulse | One missed pulse leaves the hold ≥ VT−max + 0.1 V |
| Trip | Wave stopped → hold < VT−min within 150 µs |
| Drive | Driver peak current ≤ its limit |

**The hand-sized M1 (U32 drives 2 × 100 nF straight, 100 k bleed) fails in two ways:**
- **Stuck high masks the trip.** When U32's output stops high, the 50 nF pump capacitance discharges *into* the 1 nF hold through the series diode, and the hold stays up for milliseconds. U32 stuck high, the most likely isolator fault, would then be dormant: the very gap M1 was meant to close. Stuck low trips in 76–162 µs (slow, because the +5 µA input leakage holds the hold up).
- **U32 is overdriven.** Each edge pulls 13–22 mA through U32's output, against the ISO7710's recommended ±2 mA at 3.3 V (SLLSER9E 5.3; absolute maximum 15 mA).

Fixing either with a series resistor and small pump caps straight off U32 fails the start margin (designs A–E in the JSON). An R limiting the current to 2 mA cannot move enough charge at the fast oscillator corner, and the 5:1 period spread prevents tuning around it.

**Adopted, M1b (design J):**
- U32 OUT drives an SN74LVC1G17 buffer (the existing G17 line, plus its 100 nF).
- The pump: buffer → 220 Ω → 2 × 1 nF C0G in series → BAT54S → C_hold 1 nF ∥ R_bleed 49.9 k → U40 (G17).

| Corner set | Start margin | Missed-pulse margin | Trip (worst) | Buffer peak |
|---|---|---|---|---|
| J, 96 corners | ≥ 0.148 V | ≥ 0.78 V | ≤ 90.3 µs | 11.2 mA (limit 16 mA: VOH spec point; recommended 24 mA, absolute maximum 50 mA) |
| J, one pump cap shorted | ≥ 0.245 V | ≥ 0.87 V | ≤ 122.9 µs | 11.3 mA |

The worst start corner is 3.135 V, −40 °C, slowest oscillator. The thin 0.148 V is ripple at the 2.09 µs period. A bench capture of the hold node at the cold, low-rail corner confirms it.

**Changes against §6:**
- **Placements:** M1b adds the buffer, its 100 nF and the 220 Ω to M1, so M1b is +9 and the candidate nets **−3** (not −6).
- **Bleed:** 49.9 k (existing line) replaces 100 k.
- **Pump caps:** 2 × 1 nF C0G (existing line) replace 2 × 100 nF.
- **Lines:** a new 220 Ω line (0603). Net BOM lines are +2 against today: P2 −1, M1 +2 (+BAT54A, +BAT54S, +G132, −G14), M1b +1 (220 Ω).
- **Cost:** ≈ −$1.6 (DK) / −$3.8 (JLC).
- **Detection latency:** ≤ 90 µs nominal-fault, ≤ 123 µs with a latent pump-cap short. Rail faults are ms-scale.
- **FMEA rows:** H3–H18 are unchanged in kind. The buffer is one more element whose every static fault stops the wave, so it is announced. R_s 220 Ω open is announced; R_s shorted puts the buffer over its limit but the scheme still works (nuisance-free); latent.

**Verdict on the gate:** condition 2 (SPICE) is met by M1b. Conditions 3–4 (B4 timing with ≤ 123 µs, audit.rs) follow in the stage build.

## 6b. As built (stage 30, 2026-10-14): HS-B crosses to SELV on its own default-LOW isolator

The board could not take M1b exactly as drawn. HS-A's ISO6721FB link (U43) routes. HS-B's does not: on the stage-29 floor
plan, every row between the HS-B bank and the LS domain is closed on all four layers. U42's n_ls pocket, the SELV 8 mm
keep-out, the protected In2 `bus_p` trunk and the B.Cu `n_hb` strip block it, and only grandfathered power copper crosses
the band. `08-manufacturing-package/native-21/stage30-heartbeat/spot_scan.py` finds no legal U44 pose that straddles
HS-B and LS. As built:

```
 HS-A: as M1b (U43 ISO6721FB -> MON_GOOD_HA -> one half of D18 BAT54S into the LS good node)
 HS-B: LM339B U31 'good' --rpull--> U44 ISO7710F IN (reinforced, DW-16, default LOW; at U34's stage-29 pose)
 SELV: U32 OUT (heartbeat) -> U46 SN74LVC1G132 B;  U44 OUT (HSB_GOOD) -> U46 A
       U46 Y -> 220 ohm -> pump -> hold -> U40 -> BIAS_GOOD   (the pump is AC-coupled: the NAND's inversion is irrelevant)
```

How each HS-B failure is detected, compared with M1b:
- **HS-B rail bad, U31 or U39 dead, U44 side 1 unpowered, or U44 IN open.** U44 outputs LOW (SLLSER9E 7.3,
  Tables 7-1 and 7-2), so U46's output sits static HIGH, the pump stops and the trip is **announced**. This is the same
  outcome as the ISO6721FB's default LOW stopping the LS oscillator.
- **U44 output stuck LOW, or U46 stuck at any static level.** The wave stops and the trip is **announced**.
- **U44 output stuck HIGH.** This is **dormant** for HS-B only, exactly like the M1b ISO6721FB stuck-high row. The LS and
  HS-A verdicts still stop the oscillator.
- **CMTI upset on U44 (85 kV/us minimum against the 95 V/ns model; it lasts about 5.5 ns).** It adds or blocks at most
  one pump edge. That is the same argument and the same missed-pulse margin as for U32 (`results/m1_pump_spice.json`,
  design J).

The single-fault coverage is therefore unchanged. The changes are these:
- The group has two reinforced HOT-to-SELV crossings (U32 and U44) instead of one. The stage-29 board had three.
- U46 changes from G17 to G132. The G132 is already in the BOM for the oscillator, so this adds no line.
- D18 changes from BAT54A to BAT54S. The BAT54S is already in the BOM for the pump, so this removes the BAT54A line.

The FIT figures in `scripts/fmea_metric.py` were not re-run for this variant.

## 7. Questions for the certifier

1. **Protective electronic circuit (PEC) status.** Is the F6 rail-window monitor plus the DIS path a protective
   electronic circuit under IEC 60335-1 cl. 19.11 (and the UL 1026 / UL 858 equivalent)? If so:
   - Is a negative-rail collapse, or a bias-module failure, a fault condition under 19.11.2 that the PEC must cover?
   - Which PEC component faults will the lab apply under 19.11.3 when repeating that test?
2. **Dormant PEC faults.** Today's design (and every variant) has dormant single PEC faults that hide all rails: U40
   stuck high, and U22/U23 stuck low, which also defeats PERMIT. Is "one fault at a time" (19.11) sufficient, or does the
   lab expect such faults to be detected? For example, an IEC/UL 60730-1 Annex H class-B-style periodic test, or an
   end-of-line test only.
3. **Credit for dynamic signals.** Does a dynamic (heartbeat / charge-pump) signal get credit as a self-checking measure,
   so that isolator, oscillator and pump faults count as announced (fail-safe) rather than dormant?
4. **Barrier fault exclusion.** ISO6721FB is basic (VDE 0884-17, 3 kVrms, VIORM 637 Vpk) and sits between the HS and LS
   HOT islands as functional insulation. Can its barrier short be excluded (TI cites the IEC 61800-5-2 conditions,
   SFFS130 §3)? Or must it be simulated as a short under 19.11.2 a), which equals a shorted low-side switch? The same
   question applies to the UCC21550 channel-to-channel insulation already on the board.
5. **Shoot-through outcome.** Does a shoot-through cleared by F1, with BR1 sacrificial (`DECISIONS.md:839-848`), meet
   19.13? That outcome is what a masked rail fault ultimately leads to in every variant, so it sets the severity of all
   the dormant rows.
6. **Response time.** Is a PEC response time of ≤ ~90 µs (M1) acceptable against today's ~10 µs, given that rail faults
   are ms-scale? Is there a normative limit?
7. **Crossing count.** Is reducing the monitor group's reinforced HOT→SELV crossings from three to one acceptable without
   any per-signal requirement? This is a positive change for D5. (As built, two: see section 6b.)

## Evidence and limits

- **Script:** `scripts/fmea_metric.py`, offline, deterministic, exits non-zero if an invariant breaks. Outputs:
  `results/fmea_metric.json` and `results/fmea_metric.md`.
- **Datasheets:** extracted text in `evidence/ds/*.txt`, with URLs, revisions and PDF sha256 in `evidence/ds/MANIFEST.txt`
  (fetched 2026-10-13). They are SLLSER9E, SLLSFJ0F, SLLA504, SFFS130, SFFS754, SCES546E, SCES351Y, SCES486E, SCES218AA,
  SLCS006Z and SBVS186H.
- **Not verified:**
  - Rates and modes of passives, transistors, diodes and the LDO (assumed; sensitivity shown).
  - Logic-gate rates (proxy part).
  - The "undetermined" masking probability (k_u, swept 0–1).
  - Heartbeat analog behaviour (hand sizing only; SPICE and bench pending).
  - Prices of the M1 parts.
  - Whether the LM339B output stage, the "sliver", and the ISO outputs at 1.7–2.25 V behave as assumed (no simulation).
- **Not covered:** the controller-side PERMIT path, and the bias rails' own failure rates (they cancel in the ratios).
