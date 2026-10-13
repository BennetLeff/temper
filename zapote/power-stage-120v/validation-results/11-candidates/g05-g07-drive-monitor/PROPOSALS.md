# G05 gate_drive + G07 bias_monitors_isolation: proposals (2026-10-13)

Scope: U1/U2 UCC21550 and their gate/off/permit/reservoir parts (96 placements, 22 lines); the three rail monitors, BIAS_BAD aggregation and
U32-U34 ISO7710 (93 placements, 19 lines). Nothing outside this folder was edited. Every number below comes from a script in
[`scripts/`](scripts) (all rerun with `python3 -I`, from `zapote/power-stage-120v`, offline) or from a cited source.

```
python3 -I validation-results/11-candidates/g05-g07-drive-monitor/scripts/parts_cost.py     # placements / lines / $ per proposal  -> results/parts_cost.json
python3 -I .../scripts/truth_table.py        # fail-safe truth tables, 1000 rail-state combinations + DIS table -> results/truth_table.md
python3 -I .../scripts/d5_via_nudge.py       # D5 pair and the effect of nudging it
python3 -I .../scripts/dt_window_check.py    # dead-time window vs candidate drivers (F6 swap)
python3 -I .../scripts/tps3700_band.py       # rejected option P4: threshold bands, cost, bias current -> results/tps3700_band.json
python3 -I .../scripts/jlc_fetch.py search|detail ...   # ONLINE helper that filled evidence/jlc-raw (cache lives in this folder)
```

## Ranking

Cost and counts are against the 357-placement / 92-line / $231.94 benchmark. "Scorecard $" is what `scorecard.py` will show with the
STOCK-2026-10-13 prices (many are class-default estimates: MMBT3904 $0.40, AO3400A $0.40, ISO7710DWR $1.287 from DK); "JLC-price $" uses the
live JLC tier for the qty x 500 boards (MMBT3904 is really $0.009, ISO7710DWR $2.37 on JLC, about $1.2 on DK/TI.com).

| Rank | Proposal | Placements | BOM lines | Parts $ @500 (scorecard / JLC-price) | Metric gains | Risk / effort | SAFETY |
|---|---|---:|---:|---|---|---|---|
| 1 | **P5** nudge the two DIS stub vias | 0 | 0 | 0 | `d5_hot_selv_mm` 8.047 -> **8.073** (+0.026 mm, capped by the next item) | low / copper nudge + DRC | touches the barrier margin: positive |
| 2 | **P3** PERMIT/DIS stage without FET and pull-up (NAND2, in place) | **-4** | **-1** (-2 Basic, +1 Ext) | -1.81 / -0.11 | V3V3 load -21 mA while PERMIT is high; allocated PERMIT-to-DIS rise 119 ns -> a gate delay (<= 6.4 ns, datasheet max at 50 pF), needs bench; one failure mode (FET short) deleted | low-med / schematic + 4 deletions, U22/U23 and U40 swapped in place | **SAFETY** (drive-disable logic) |
| 3 | **P2** HS monitors cross through ISO6721FB; one reinforced crossing for the monitor group | **-12** | -1 (-2 Basic, +1 Ext) | **-3.17 / -1.9 to -4.1** (see below) | reinforced barrier crossings 4 -> 2 (U33/U34 gone); two ISO7710 (0 stock, 12 wk) become ISO6721FB (JLC 5,306); F9: two of the three `bias_*_bad` plane-void runs disappear (needs chain); CMTI row 0.89 -> 1.05 (filtered) | med-high / re-layout of G07 + LS 5 V feed | **SAFETY** (fault path, barrier) |
| 4 | **P1** notice stage -> one inverter per rail | -9 | -2 (Basic) | -0.17 / +0.24 | part count only; stepping stone, superseded by P2 | low / G07 re-route | fault path (logic-level only) |

P2 contains P1's deletion (the NAND3 does the inversion), so adopt P2 **or** P1, not both. P3 and P5 are independent of both and of each other.
Combined P2 + P3 + P5: **-16 placements, -2 lines, scorecard -$4.97 (about -$2.0 on DK/TI.com-priced ISO7710, -$4.2 on JLC prices, because $1.5 of the scorecard figure is the estimated price of cheap discretes), D5 +0.026 mm.**
Honest size: these groups hold 189 of 357 placements but the removable part is small; the 92 + 22 + 93 count is mostly 100 nF/1 uF/10 uF
bypass and the F6 reservoirs, which are held by bypass 11/11, PI and the F6 rail qualification (see "considered and rejected").

## What I found out about the premises

1. **BIAS_BAD is not a J4 signal.** `BIAS_BAD` exists only between the monitors' OR3/filter (`U25`, `U40`) and the two `U22`/`U23` DIS gates
   (`power_stage_120v.ato:271,398,412,947`; `groups.json` interface list: only G05/G07). Its polarity is therefore free to change (P3 uses that).
   J4 carries pwm_ha/hb/la/lb and permit (G10 interface list).
2. **ISO7710F is not a drop-in and the audit forbids it** (`default_low_isolator_fails`, research/driver-isolator-alternatives.md). P1/P2 are
   designed so that every ISO7710 stays default-HIGH; the only default-LOW parts are the two new ISO6721FB, whose low output is read as "not good".
3. **UCC21550 is not zero-stock everywhere**: JLC has UCC21550ADWR 3,988 (C22427509, $0.96 at 1,000), BDWR 224 (C22445586), ADWKR 76 (C38941037,
   $1.45), CDWKR 47; TI.com holds 15,771 BDWKR (research file). F13 for U1/U2 is an ordering problem, not a design problem. Raw JLC records in
   `evidence/jlc-raw/`.
4. **F6 cannot be closed by part count.** The CMTI fix is a driver swap (research: 2EDR8259H 150 V/ns, NCP51561 200 V/ns bench-only). My addition:
   **no candidate fits the board's dead-time window.** `audit.rs DT_WINDOW_NS = (391, 498)` allows at most +-12.0 % total DT spread
   (`dt_window_check.py`); UCC21550 at 49.9 k 0.1 % reproduces audit.rs (396.6..488.0 ns), but NCP51561 is +-27.5 % at 20 k / +-20 % at 100 k
   (onsemi table: 145/200/255 and 800/1000/1200 ns) and 2EDR8259H is +-15 % (research note). Best fits: NCP51561 has none (40 k: 307..493; 54.9 k:
   429..670), 2EDR8259H at 46 k: 391..529 ns (31 ns over the upper edge). The D2 grid has to be rerun over a wider band **before** any CMTI swap.
   NCP51561 additionally: JLC stock 2 pcs (C5206739), DK lead 45 wk, CMTI "verified by bench test only" (datasheet note 19).
5. **D5 8.047 mm is the same stub on both legs.** The `leg_a-dis` via at (75.544, 58.797) against the `n_ha` B.Cu zone (and the mirror
   `leg_b-dis` via at (28.544, 58.797) against `n_hb`). The next items are 8.073 mm (v3v3 In2 track vs n_ha In1 zone) then 8.08-8.1 mm (pads),
   so the board floor is about 8.07-8.1, not 8.0.

## P5. D5: nudge the DIS stub vias (+0.026 mm)

**Change.** Move the layer-change via of `leg_a-dis` from (75.544, 58.797) by +0.1 mm in x (to 75.644) and the mirror via of `leg_b-dis`
(28.544 -> 28.644). Both are one-net stubs: U22.1 (pad centre 75.9575, 59.795) goes F.Cu -> via -> In1.Cu -> R8.1 via-in-pad; the straight F.Cu
route is blocked by the v3v3/selv_gnd/bias_bad copper at U22 (checked). Keep the F.Cu and In1 tracks attached to the moved via.

**Mechanism / effect.** `d5_via_nudge.py` recomputes the pair from the 19c copper dump: reproduces 8.047 mm, then +x by 0.10-0.20 mm gives
**8.073 mm**; -x makes it 7.947 (wrong way); +/-y barely helps. The gain is capped at 0.026 mm by the next item, so it is a tie-breaker, not margin
(rule 3 "strictly better on a performance metric").
**Interfaces.** G06 (n_ha/n_hb zones are the HOT side), G03 none. **Not checked:** DRC clearance of the moved via to U22 pads and the In1 tracks
(needs the chain). **Safety:** barrier margin goes up, nothing else. **Risk** low. **Effort** copper nudge + chain. **Rank cost** $0, 0 lines.

## P3. PERMIT/DIS stage: delete the FET and the 330 ohm pull-up (SAFETY: drive-disable logic)

**Change** (per leg, U22/U23 are the existing DIS-OR gates). Today: PERMIT -> 100 ohm -> `permit_gate` -> AO3400A (Q1/Q4) pulls the raw DIS node low
against a 330 ohm pull-up (R8/R16, ~10.5 mA per leg from V3V3 while PERMIT is high, DECISIONS D-31) -> SN74LVC1G32 OR with BIAS_BAD -> `driver_dis`
(+10 k pull-up) -> UCC21550 DIS.
New: `DIS = NAND(permit_gate, BIAS_GOOD)`.
- Delete Q1, Q4 (AO3400A, C20917) and R8, R16 (330 ohm); keep the 100 ohm series resistor, the 100 k gate pull-down and the 10 k DIS pull-up.
- U22/U23: SN74LVC1G32DBVR -> **SN74LVC1G00DBVR** (C7826, Extended, JLC 5,062, $0.084 at 500). SOT-23-5, pins 1 A, 2 B, 3 GND, 4 Y, 5 VCC, the same as the G32 it
  replaces, so no footprint change. Pin 1 = `permit_gate`, pin 2 = BIAS_GOOD.
- U40 (the Schmitt buffer after the 10 us RC): SN74LVC1G17DBVR -> **SN74LVC1G14DBVR** (C7835, inverting Schmitt, same SOT-23-5 footprint). Its output net
  becomes BIAS_GOOD. The 10 us filter is unchanged (a glitch toward bad still has to last >5.95 us to pass).

**Mechanism.** The FET + pull-up is only an inverter with a slow, power-burning output. A CMOS gate does the same job; DIS then switches with
the gate delay (SN74LVC1G10 datasheet SCES486E, same family and process: tpd max 3.8 ns at 3.3 V / 15 pF, 6.4 ns at 125 C / 50 pF; the G00 figure is from JLC's record, 3.8 ns at 3.3 V / 15 pF, not read in its own datasheet) instead of the allocated 119 ns rise (D-31).
Failure view: the FET's drain-source short (DIS stuck low = enabled) disappears; the gate-stuck-low case is the same class as the OR gate's today (it
already bypasses both PERMIT and BIAS_BAD). No new common point (`truth_table.py` section "Single output-stuck-at-good").

**Truth table** (`results/truth_table.md`, identical benchmark vs P3 for PERMIT = 1, 0, floating x BIAS_BAD = 0, 1): DIS = 0 only for PERMIT = 1 and
BIAS_BAD = 0. Floating PERMIT is held low by the 100 k; V3V3 absent leaves the driver below its VCCI UVLO (2.55-2.85 V, SLUSE89C), outputs low, as today.

**Scorecard.** placements -4 (Q1, Q4, R8, R16), lines -1 (AO3400A and 330 ohm lines gone, G32 line gone, G00 and G14 lines new), Extended +1,
parts $ -1.81 on the scorecard's estimates (JLC reality -$0.11), V3V3 load -21 mA at PERMIT high (2 x 10.5 mA, D-31). Allocated PERMIT-to-DIS
delay: 119 ns -> a gate delay: **bench** (the earlier ~0.35 us estimate was already called "not a bound"). No B3 input change (the 3.3 V rail is SELV).
**Interfaces.** J4 PERMIT (G10): the input now sees a CMOS gate (VIH 2.0 V min at 3.3 V; ESP32 VOH min 0.8 x VDD is 2.64 V) instead of an AO3400A gate (~1 V);
check the controller's drive level and the D-25 pull-down. `bias_bad` -> `bias_good` rename in G07 (U40, `bias_or` unchanged). `audit.rs` PermitFet/DisOr
identity rows and FAULT-INTERFACE.md. **Safety:** the disable path is shorter and has fewer parts; certifier question is only the logic change.
**Risk** low-med. **Effort** schematic + 4 deletions + 3 in-place swaps + local rewire at U22/U23 (the `dis` net disappears).

## P2. HS rail monitors reach the LS domain through a cheap functional isolator; one reinforced crossing for the monitor group (SAFETY)

**Change.**
- U33, U34 (ISO7710DWR on HS-A / HS-B): replace by **ISO6721FBDR** (TI, SOIC-8 narrow, JLC C5216431, Extended, 5,306 pcs, $0.41 at 500 / $0.39 at 1,000;
  two channels, one forward used, the reverse channel unused, input tied low). Default output LOW when side 1 is unpowered or IN open (datasheet "FB" option).
  Side 1 = the HS monitor's existing 5 V LDO (U38/U39, GND n_ha/n_hb); side 2 = the **LS 5 V rail** (U37 output, GND n_ls). Input = the comparator
  wired-AND "good" node pulled to the HS 5 V by the existing `rpull`.
- Delete in all three monitors the notice stage (dnotice, qnotice, rnotice 1 k, rbase 10 k): 12 placements (as P1). The comparator "good" node goes straight to
  `rpull`; "good" is positive logic (high = in window).
- New **NAND3 on the LS 5 V rail** (SN74LVC1G10DBVR, the existing U8 line, + one 100 nF; replaces U25 and its cap C88): inputs = LS "good" (wired-AND node),
  HS-A good, HS-B good. Its output drives U32's input. U32 stays **ISO7710DWR (default HIGH = bad)** and is the only reinforced crossing of the group.
- U25 (SN74LVC1G332 OR3 on the SELV side) is deleted; the RC filter, U40 and the DIS gates are unchanged (P3 composes: U40 -> G14).

**Mechanism.** A reinforced isolator ($2.3 on JLC, $1.2-1.3 DK/TI.com, 12 wk, zero stock on JLC/DK) is only needed where a signal crosses to SELV. The two HS
monitors cross HS-island to the LOW group, which the board already treats as functional (3.2 mm, the same barrier class as the driver's channel-to-channel
rating and the bias modules' secondaries), so a basic-class part serves. Datasheet values (TI ISO672x, SLLSFJ0F): VIORM 637 Vpk (vs 520 V worst sw excursion,
D-22 clamp target; margin 22 %), CLR/CPG > 4 mm (vs the 3.2 mm HOT-group rule), CMTI min 100 kV/us at VCM 1200 V (typ 150), default output Low for FB.
Fail-safe: any rail fault, collapsed rail or lost 5 V gives HS good = 0 -> NAND3 = 1 -> U32 IN high; LS 5 V lost gives U32 side 1 unpowered -> default HIGH.
**Truth table** (`truth_table.py`: 10 states per rail x 3 rails = 1,000 combinations, benchmark / P1 / P2 agree on every one; no violation). The only state
none of the three catches is the "sliver" P-N = 2.3-3.0 V (LDO above ISO UVLO, LM339B below its 3 V minimum): the benchmark has it too, and the driver's own
UVLO (6.5 V option A, 9.2 V option B) holds the gates low there.

**Scorecard.** placements -12 (notice 12; U25/C88 out, NAND3 + cap in), lines -1 (MMBT3904 and 1N4148W gone, ISO6721FBDR new Extended), parts $ **-3.17 on the scorecard** = -$1.80 (two ISO7710 at the STOCK csv's DK price $1.287 replaced by ISO6721FB at JLC $0.39) + -$1.37 (the notice parts at their class-default estimates; their real price is about $0.1). Real saving: **-$1.9** with DK/TI.com-priced ISO7710 ($1.17-1.29 at 500), **-$4.1** with JLC-priced ISO7710 ($2.37). ISO7710 units on the board 4 -> 2 (U9, U32). `cmti_gate_ratio_min` unchanged (gate class
only, 1.316); the filtered monitor rows go 0.89x (ISO7710 85 kV/us) -> 1.05x (ISO6721 100 kV/us), both "PASS on filter". D5: U33/U34 no longer straddle SELV; they leave the
`barrier_crossing_parts` list. `return_path_open_changes`: needs the chain (removes `bias_ha_bad`/`bias_hb_bad`, adds two LS-referenced "good" runs).
**Interfaces disturbed.** Nets removed: `bias_ha_bad`, `bias_hb_bad`; added: `good_ha`, `good_hb` (n_ls referenced, HS island to the NAND3), and the LS 5 V rail extended to
the HS isolators (HS-A ~40 mm, HS-B ~85 mm from U37 at x = 110; U33/U34 sit at x = 70.6 / 25.6). G06 owner: p_ha/n_ha/sw_a clearances at the new isolator footprints;
G10: no J4 change; G08: U9 untouched (its ground is the OCP Kelvin node, so it cannot share U32). If the 5 V feed is unacceptable, the alternative is one more TPS70950 per
HS monitor referenced to n_ls (+$0.31 each, no saving left on that rail): then P2 is -$2.7 only.
**SAFETY.** (a) Reinforced crossings of the monitor group 3 -> 1 (fewer; the removed ones are replaced by functional crossings with 4 mm creepage and
637 Vpk working margin); (b) **fault masking**: U32 stuck-low now hides all three rails where today a stuck ISO hides one. The chain already has three
common points (U25, U40, each DIS gate), `truth_table.py` counts it as +1; a power-up check (BIAS_BAD must be 1 with the bias off and 0 after) tests U32's high
state only. (c) `audit.rs` rules that name ISO7710 for the HS monitors and the default-low rule need an ISO6721FB exception. **Needs the certifier / FMEA**
for (a)-(c) before adoption. **Risk** med-high. **Effort** re-layout of G07 (two 16-pin isolator footprints become 8-pin, the SELV/HOT split of the monitors changes).

## P1. Notice stage -> one inverter per rail (stepping stone, superseded by P2)

**Change.** In each RailMonitor delete dnotice (1N4148W), qnotice (MMBT3904), rnotice (1 k), rbase (10 k); add one SN74LVC1G10DBVR (3 inputs tied = inverter;
the MPN is already on the board as U8) between the "good" node (pulled up by the existing `rpull`) and the ISO7710 input; share the rail's `civcc1` 100 nF.
ISO7710 (default HIGH) and the OR3/filter stay as they are, so `audit.rs` stays valid.
**Why it works.** The NPN only inverts and level-shifts the comparators' wired-AND to the 5 V domain. The 5 V pull-up already exists. Truth table: same
as the benchmark on all 1,000 combinations (the benchmark's extra dependence on "reference above 1.4 V" is redundant: a dead reference trips a comparator
anyway, see the TL431_OPEN/SHORT rows).
**Scorecard.** placements -9, lines -2 (both Basic), parts $ -0.17 scorecard / **+0.24 real** (a $0.11 gate replaces $0.035 of discrete parts). Value is part count and
area. **Why not F:** ISO7710F + NAND3 would save one more part per rail but it is the default-low part `audit.rs` rejects and needs the whole chain's polarity
changed (research note), so rejected. **Risk** low, **Effort** G07 re-route.

## Considered and rejected

| Idea | Why not |
|---|---|
| **P4**: TL431 + LM339B + 11 R per rail -> 2 x TPS3700 + 6 R | Works electrically: `tps3700_band.py` finds E96 ladders (neg rail 48.7k/2.32k/11.3k, span 499k/0.931k/11.5k) whose worst-case trip bands sit **inside** the benchmark's for all four thresholds (neg UV 1.758-1.843 vs 1.737-1.862 V; OV 2.168-2.245 vs 2.127-2.285 V; span 15.78-16.60 vs 15.58-16.87; 17.46-18.12 vs 17.14-18.56 V). It also removes the 6.6 mA reference branch per rail (0.33 W of 17 V bias power per board, which helps the RECOM modules' 1.7 W thermal question) and fails safe on loss of supply (OUTA low in UVLO). But **+$4.32 per board** (6 x $0.80 against $0.49) for -12 placements: about $0.36 per placement removed. Keep as the option if module thermals bind (needs bench). Supply: power the TPS3700 from the 5 V LDO, not P-N (20 V abs max vs a faulted 24 V rail). |
| ISO7710F in the monitors with the polarity reversed | audit.rs forbids default-low isolators; saves one part per rail over P1 only. |
| Swap U1/U2 to NCP51561 or 2EDR8259H for F6 | Fails the 391-498 ns dead-time window by construction (finding 4); NCP51561 stock/lead; not a part-count change. |
| Share one PERMIT path / one DIS gate between the two legs | Saves 7 placements per leg but removes the second independent disable path; D-25 keeps PERMIT/DIS as the independent hardware off-path. Needs FMEA; not proposed. |
| Use the RECOM modules' PG pin (primary-side, 90-110 % of FB) to replace the HS span comparators | PG window is +-10 % (15.3-18.7 V) against the monitor's 16.2-17.9 V, and the negative-rail window (UCC21550's UVLO does not see it, DECISIONS 2026-10-06 (4)) still needs the HS-side comparators and a crossing. |
| Drop the OV / span comparators | Span OV protects the CFD7 gate (20 V) against a module feedback fault; UVLO does not. Decision (4) keeps the full window. |
| Miller-clamp driver instead of the -2 V rail | Would delete the shunt, split, window comparators and reservoir roles (~20 parts per rail) but F6 shows S4/S5 fail unipolar everywhere (DECISIONS 2026-10-05); no clamp-driver model, no S4 deck: not provable here. A spike on `round17/d2/f6_legs.py` with a clamp-resistance parameter is the next step. |
| Fewer reservoir / bypass caps (the 16 CL05B104 chf, c_hs/c_ls stacks) | Stage 9 put the 100 nF + 1 uF stack at the driver pins for the 2.1 mm gate loop and the reservoir for the 740 nC edge charge; they have different jobs. Needs the chain (bypass 11/11, PI, rail qualification). |
| 5 V zener instead of TPS70950 per monitor | Saves $0.3 per rail but burns ~5 mA of the module budget; the 17 V rails are already thermally tight. |
| 4 x 6SVPC220M ($2.78, JLC stock 13) | The one G05 line that is both costly and low-stock; the 140-317 uF sensitivity in `bias_sizing.py` leaves room for a cheaper part but needs the rail qualification rerun: flagged, not proposed. |

## What other owners must check

- **G06 (bias):** P2 moves/changes U33/U34 at the HS islands and adds an LS 5 V feed; P5 touches the n_ha/n_hb zones' neighbourhood. Monitor current: P1/P2 leave the 6.6 mA
  reference branch per rail; only P4 removes it.
- **G10 (J4):** P3 changes only PERMIT's input threshold; PWM and J4 pinout unchanged.
- **G08:** U9 (ISO7710, BUS_FAULT) keeps its ISO7710 stock problem; buying ISO7710DWR from TI.com (10,764 pcs, research note) is the fix, no design change.
- **Lead:** update `audit.rs` for P2 (ISO6721FB, NAND3, U25), P3 (PermitFet/DisOr rows, BIAS_GOOD), and add a negative control for each. Update STOCK prices (the class-default estimates
  overstate every saving above except P2's ISO part).

## Unverified

- Everything in the truth tables is a logic-level model of the schematic, not a SPICE run; analog behaviour of the "sliver" and of comparator outputs with the supply below 3 V is by
  reasoning (LM339B minimum VCC 3 V, SLCS006Z).
- P3: DIS rise time with the real DIS-node capacitance; PERMIT input threshold with the controller; PERMIT-to-gate delay (bench).
- P2: ISO6721's behaviour under the 95 V/ns edge (rated CMTI 100 min at 1200 V, filtered by 10 us RC as today); creepage on the SOIC-8 footprint against the island edges; LS 5 V routing.
- P5: DRC clearance after the move. UCC21550/ISO6721/ISO7710 price tiers are JLC's public records of 2026-10-13; DK/TI.com prices come from the research note.
- Datasheets were read in a scratch directory (not stored): TPS3700 (2019 rev), TL431 SLVS543S, LM339B SLCS006Z, ISO7710 SLLSER9E, ISO6721 SLLSFJ0F, UCC21550 SLUSE89C, NCP51561 (onsemi), SN74LVC1G10 SCES486E.
