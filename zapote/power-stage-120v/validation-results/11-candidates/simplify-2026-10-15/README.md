# native-21 s43 simplification study: blocks that one integrated part or a simpler topology could replace

Desk study on the read-only snapshot at `cb48a12e6` (board of record s43, `PS` = `snap-cb48/zapote/power-stage-120v`).
This is a parts and topology study only: there is no layout, nothing was written under `worktrees/`, and nothing was committed.
Every number below comes from a script in `scripts/` or is cited to a file:line or a datasheet page.

```
python3 -I scripts/inventory.py        # block inventory; asserts the s43 card total $202.32      -> results/inventory.{json,md}
python3 -I scripts/monitor_tps3701.py  # candidate B thresholds; control = g05-g07 P4 old bands   -> results/monitor_tps3701.json
python3 -I scripts/ovp_band.py         # candidate A OVP band; control = task-02 round-3 model   -> results/ovp_band.json
python3 -I scripts/candidates.py       # placements / lines / $ per candidate, two price bases    -> results/candidates.{json,md}
python3 -I scripts/jlc_table.py        # the JLC records used (offline, from dl/jlc-raw)         -> results/jlc_parts.json
python3 -I scripts/manifest.py         # datasheet URL / revision / sha256                       -> dl/MANIFEST.json
```

Pass `--offline` to `monitor_tps3701.py` to forbid JLC look-ups. The cached JLC JSON in `dl/jlc-raw/` and the PDFs in
`dl/` are untrusted data, and the scripts read only named fields from them.

## Headline

- **The control and monitor logic is already lean, so consolidation is worth placements and BOM lines, not dollars.**
  - The three candidates worth building together (A + B + C) remove **14 placements and 3 BOM lines**.
  - They are roughly cost-neutral: **−$0.26 per board at JLC prices, −$1.21 on the scorecard's basis**.
  - On the way they close three safety corners (below).
  - The board's money is in the FETs, F1, PS2, L1 and the film capacitors. All of those are outside this study's scope.
- **A. Move the bus OVP onto the HOT5 supervisor's unused over-voltage channel** (U14's INB). U14 becomes a TPS3701, and
  the 3-input NAND becomes the Schmitt-input NAND2 already on the BOM.
  - Saves 6 placements, 1 line and **$1.24** per board.
  - Needs a G08 FMEA delta, because OVP and the HOT5 undervoltage check (HOT5-UV) then share one IC.
- **C. Put the CT positive trip and the CT zero-cross comparators in one TLV3202 dual** (U10 + U12). The negative trip
  stays on its own die.
  - Saves 2 placements and **$0.64** per board, but adds 1 line.
  - Low risk: the CT trip band and the zero-cross (ZC) offset need re-running.
- **B. Replace each rail monitor's TL431A + LM339B + reference network with two TPS3701 window detectors**, one per
  window.
  - Saves 6 placements and 2 lines, but costs **+$1.63** per board (JLC).
  - It earns its place on safety, not cost:
    - One IC fault now masks one window (two thresholds) instead of both windows (all four thresholds).
    - The "sliver" (the rail range where today's comparator is below its minimum supply) is closed.
    - Each rail draws about 6.7 mA less reference current.
    - The window bands get 2.5× tighter.
    - Under a worst-case tolerance stack, today's span-UV and span-OV corners overlap the rails' own tolerance (side
      finding S1). B fixes the trip corners. The span-OV release corner stays 0.07 V inside the LS rail's +2.5 %
      corner, which matters only after an OV trip.
- **Driver UVLO question: no monitor becomes redundant.**
  - The fitted 2EDR8259X has an 8 V output UVLO (turn-off threshold ≥ 6.6 V). It sees only VDD−VSS, acts per channel,
    and does not see the −2 V rail or an over-voltage.
  - Its 15 V sibling, the 2EDR9259X, overlaps only the span-UV check, per channel. JLC holds 12 (candidate D, on hold).
- **Merging the three monitors into shared quads is impossible without new barrier crossings.** They already are quads,
  one per floating domain (rejected R1).

## Price bases (read before the numbers)

Every $ figure is per board at the 500-board price break. Two bases are given:

- **card:** the scorecard's basis. It merges `sourcing/STOCK-2026-10-13*.csv` exactly as `native-21/layout/gates/scorecard.py`
  `cost()` does, and reproduces the s43 card's $202.32 (asserted).
  - 58 of the 93 lines are flagged `price_is_estimate`, most of them `ESTIMATE (class default)`, and several are far off:
    - LM4040A25: card $0.40, JLC $1.26;
    - TPS3700: $0.40 vs $0.83;
    - TL431A: $0.40 vs $0.049;
    - LVC1G logic: $0.40 vs $0.08–0.16;
    - TLV3201: $0.45 vs $0.61.
  - So the card mis-states logic and analog swaps. For example, B shows +$0.26 on the card against +$1.63 at JLC.
- **JLC:** the JLC 500-board price in `SNAPSHOT-2026-10-15.csv` where JLC lists the part (otherwise the card price), and
  the JLC ladder at qty × 500 for new MPNs (`results/jlc_parts.json`, fetched 2026-10-15 ≈ 21:00Z). Ranking uses this
  basis. On it, s43 totals $210.72: the FETs are dearer at JLC ($17.53 against DK $10.18).

## 1. Inventory of the s43 blocks

`results/inventory.md` / `.json` give every block's refs, lines and prices. Parts were assigned by hierarchical address
from `frozen/default.net` and MPNs read from `frozen/default.csv`: 351 parts, 93 lines.

| Block (group) | Function and safety role: what it detects, how fast, fail-safe direction | Parts | Lines touched / exclusive | $ card / JLC | DECISIONS / FMEA that depend on it |
|---|---|---:|---:|---:|---|
| **MON-LS / HA / HB** rail monitors (G07), ×3 identical | Windows per domain: −2 V rail SRC−N −1.80…−2.21 V and span P−N 16.22…17.84 V (nominal, `ECO.md:73-77`). TL431A → ½ ref; LM339B open-collector wired-AND `good`; 1 nF per input; TPS70950 local 5 V. Bad → `good` low → heartbeat stops → BIAS_GOOD low → DIS high in ≤ 90 µs (FMEA §6a). Fail-safe: dead LDO / unpowered side → not-good. Dormant: an LM339 output open (C2), half the divider opens and shorts (C5/C6), the "sliver" P−N 2.3–3.0 V (C7, covered by driver UVLO) | 22 each, 66 | 13 / 0 each | 1.76 / 0.94 each | F6 adoption 2026-10-05/06 (monitor mandatory, "UVLO does not see a collapsed negative rail"), 32, 33, 52; bom-simplification S2 (6.2 k split); FMEA c24 §3a C1–C7 |
| **LINK** HS→LS verdict links (G07) | U43 / U44 ISO6721FB carry HS-A / HS-B `good` to the LS vote; default LOW on side-1 loss or open input; OUT stuck HIGH is dormant for one HS rail | 6 | 2 / 1 | 0.81 / 0.85 | 33, 52; FMEA §6a, §6c |
| **HB** heartbeat + BIAS_GOOD (G07) | U45 oscillator gated by the LS `good` node (D18 / D20 HS vetoes) → U32 CA-IS3720HW (one reinforced crossing) → U46 → pump → hold → U40 → BIAS_GOOD. Any static state stops the wave; hold bleeds below VT− in ≤ 90 µs (≤ 123 µs with one pump cap shorted). U40 Y stuck high is dormant for all three rails (C8). Production screen of each HS veto (DECISIONS 52) | 20 | 11 / 3 | 1.43 / 1.16 | 32, 33, 34, 52; FMEA §6a–6c, C8; OPEN-ITEMS B8 |
| **BIAS-LS**: PS2 + TPS7A4700 + TLVH431 split (G06) | PS2 MPM-20-24 on TCO_L: opening the TCO loop removes all gate drive, HOT5 and OCP_OK (the UL 858 25.3.1 backstop, S15). TPS7A4700 17.0 V ±2.5 % span; TLVH431 (sink-only) holds LEG_RET ≈ 2 V above N_LS | 11 | 8 / 2 | 17.89 / 14.81 | 2026-10-06 (TCO-switched HOT supply), 47, 50, 56 (B3 line) |
| **BIAS-HA / HB**: RECOM R24C2T25 + split (G06) | Reinforced 5 kVAC module per HS, 16.91 V ±1.5 %; TLVH431 split; module PG unused | 15 each | 11 / 0 each | 8.32 / 8.36 each | 2026-10-09 (ALT-BIAS A1), 32 (reinforced confirmed), 49 (keep RECOM) |
| **HOT5 LDO** U3 (G06/G08) | 5 V for OCP / OVP / NAND / U9 / AMC side 1, returned on OCP_KELVIN_P (a loaded Kelvin reference) | 3 | 3 / 0 | 0.97 / 0.46 | BOM-REVIEW #2; FAULT-INTERFACE brownout; Kelvin budget |
| **RES** F6 VSS reservoirs ×4 (G05) | Per VSS: 2×10 µF + 2×1 µF + 4×100 nF 0402 + 220 µF via 0.68 Ω + 4.99 k bleed; keeps SRC−N ≤ −1.6 V at the edge (F6) | 44 | 6 / 3 | 3.53 / 3.66 | ECO "Supply and gate circuit"; 34 (CL32B106); c31 `mlcc_bias.py` |
| **DRV** drivers + pin decoupling (G05) | 2EDR8259X: reinforced, CMTI ≥ 150 V/ns (1.58×), dead time 408–569 ns, 8 V output UVLO, DIS active high (R73 / R76 alone hold an open DIS) | 18 | 7 / 3 | 3.35 / 4.13 | 31; c25 |
| **DIS** PERMIT/DIS logic (G05) | DIS = NAND(PERMIT, BIAS_GOOD) per leg; PERMIT float → 100 k → DIS high; independent per leg (D-25) | 10 | 5 / 2 | 0.86 / 0.20 | 27, 31; FMEA C9 / C10 |
| **GATE** gate networks ×4 (G05) | 68 Ω 2512 turn-on, 4.7 nF Cgs, PMEG6030EP + 1 Ω turn-off, 10 k hold-off; holds S4 at 49.7 V/ns, 244 A/µs | 20 | 5 / 4 | 1.09 / 1.06 | 54, 55, 57; ledger |
| **OCP** (G08) | R5 Kelvin, TLV3201 U6 vs LM4040 REF25 divider; band 67.77–116.44 A; chain 0.85–1.16 µs + 0.1 µs RC; output high = OK | 10 | 9 / 4 | 0.91 / 2.03 | 2026-10-10 (12.6 k / 11.7 k), 33 (R134 / C167); Kelvin budget; S15 |
| **OVP** (G08) | U7 TLV3201: VSENSE_IN vs REF25 × 140/150 → ≈280 V (band 272.1–288.0 V, round-3 model); a restart inhibit (plug-in overshoot asserts it 1.3–2.2 s, external review O1); its upper corner is the static bus maximum the D3 / C5C6 / ALT-BIAS ratings use | 5 | 5 / 1 | 0.48 / 0.69 | ORACLE-ANSWER (OVP); audit `swapped_ovp_comparator_inputs_fail`, `ovp_bypassing_isolator_path_fails`; S15 |
| **H5UV** HOT5 supervisor (G08) | U14 TPS3700 from V15_LS (independent of HOT5), INA = HOT5 × 10/115, falls 4.42–4.64 V; OUTA → R50 pull-up → U15 Schmitt → NAND.C. **INB is tied to ground and OUTB is unused** | 7 | 5 / 2 | 0.84 / 1.01 | FAULT-INTERFACE "Brownout correction"; audit "missing or mispowered HOT5 supervisor" |
| **FLT** fault NAND + U9 (G08) | BUS_FAULT_HOT = NAND3(OCP_OK, OVP_OK, HOT5_OK) → U9 CA-IS3720HW (default HIGH) → R134 / C167 → U13 | 5 | 3 / 1 | 0.91 / 0.62 | 33, 34; FAULT-INTERFACE truth table |
| **VSNS** bus divider + AMC1311 (G08) | 4×470 k / 15.8 k = 1/120 into AMC1311; VSENSE_IN is also the OVP input | 11 | 6 / 2 | 1.58 / 1.59 | 2026-10-03 (D-11: ±6 %) |
| **CT** tank-CT detector + fault OR (G09) | Burden, 1.65 V midpoint, clamps; U10 pos / U11 neg trip (band 64.55–76.09 A), U12 ZC to the controller; U13 OR3 → BUS_FAULT (fault-high) | 23 | 12 / 8 | 2.01 / 2.58 | 2026-10-10 (CT band); FAULT-INTERFACE |
| **LZC** line zero-cross (G09) | 4×16.5 k + VOL628A opto + G17 to J4.16; functional | 8 | 5 / 3 | 0.84 / 0.46 | 23 |
| XFER SELV transfer caps | Return-path caps by pwm_hb layer changes (layout-owned) | 5 | 1 / 0 | 0.04 / 0.04 | 19b, 52 |
| FET, other (mains, power path, tank, connectors) | out of scope | 8 + 41 | — | 142.8 / 155.8 | — |

The audit's counts carry over:

- **G07** is 92 parts: three 22-part monitors, the 6-part links and the 20-part heartbeat. The audit's "~17 per monitor"
  excludes the LDO and its caps.
- **G06** is 44 parts.
- **G05** is 92 parts without the FETs.

**Repeated small logic** (the "comparators / Schmitt / NAND, dividers, pull-ups" inventory):

| Kind | Parts | Domain |
|---|---|---|
| Fast comparators TLV3201 | U6 OCP, U7 OVP (HOT5 / KELVIN_P); U10 CT+, U11 CT−, U12 ZC (V3V3 / SELV) | 2 HOT + 3 SELV |
| Quad comparators LM339B | U29 / U30 / U31, one per bias domain (N_LS, N_HA, N_HB) | 3 floating domains |
| Supervisors TPS3700 | U14 (channel A used, **channel B spare**) | HOT / KELVIN_P |
| References | U5 LM4040A25 (REF25: OCP and OVP thresholds); U17 / U19 / U21 TL431A (monitors); U16 / U18 / U20 TLVH431 (splits) | |
| LVC1G logic | U8 G10 NAND3; U13 G332 OR3; U15 / U24 / U40 G17; U22 / U23 G00; U45 / U46 G132 | |
| Threshold dividers | OCP R34 / R35, OVP R36 / R37, HOT5-UV R48 / R49, CT refs R43–R46, monitors 8 per rail, bus R26–R30 | |
| Fail-safe pull-ups / downs | R7 / R15 (PERMIT), R73 / R76 (DIS), R50 (HOT5-UV), rpull ×3 (`good`), R125 (LZC), R135 (U46.A), R11 / R13 / R19 / R21 (gates) | each sets one node's safe default; none is shareable |

## 2. The specific questions

- **Does the 2EDR8259X UVLO make an external rail monitor redundant? No.**
  - The fitted 8 V option turns on at ≤ 8.5 V and off at ≥ 6.6 V (Table 15, p.13). It monitors only VDDx−VSSx.
  - It misses the −2 V rail (SRC−N), span over-voltage (the CFD7's 20 V gate) and span 8.5–16.2 V. It also acts on
    one channel only and reports nothing.
  - The family has a 15 V option (Table 1 p.1: **2EDR9259X**, same DSO-14 and DIS polarity). Its turn-on is ≤ 15.5 V
    and turn-off ≥ 13.7 V (Table 17 p.14), with operating minimum 15.6 V (Table 11 p.12). That covers span-UV below
    13.7–15.5 V on the affected channel only.
  - So no monitor IC can go. At most the 3 span-UV divider/cap parts per rail could go, and that would change the
    shutdown scope from "all four channels" to "the affected channel". Candidate D (on hold) is the swap without
    deleting anything, as a per-channel backstop.
  - The 12 V option exists only as the EN-polarity 2EDR6258X, which the audit's EN-sibling negative control rejects.
- **Merge the monitors' comparators into quads?**
  - They already are: one LM339B per domain.
  - The three domains float on N_LS, N_HA and N_HB (SW_A / SW_B swing up to 520 V). A shared comparator would pull
    analog sense nets across two barriers, which is forbidden (R1).
  - Inside a domain, the better move is the opposite: split the quad into one window IC per window (B).
- **One isolated-supply IC per island?** Each HS island already has one (RECOM, DECISIONS 49); the LS island's
  isolated supply is PS2. What remains discrete:
  - The HS TLVH431 split. The module's own COM regulator could replace it (ALT-BIAS A2, candidate F). But −2.5 V is
    the module minimum, there is no transient model, and it needs full F6 re-qualification: deferred.
  - The LS TPS7A4700 + split. A third RECOM costs +$3.4 and adds heat (R9).
- **Window supervisors.**
  - TPS3701 (36 V, ±0.75 %) is **$0.346 at JLC (26,599 in stock)**, cheaper than the fitted TPS3700 ($0.83) and
    pin-identical in DDC (SBVS240C p.3 = SBVS187G p.4).
  - That makes candidate A, and makes B affordable (the earlier P4 study priced TPS3700s at $0.80).
  - TLV6700 / TLV6710 are dearer ($0.67 / $1.64 at JLC).
- **Shared dividers.**
  - A 3-resistor ladder serving two thresholds (the earlier P4 design; also possible for the CT references) has a new
    single fault: if the middle resistor opens, the upper tap rises to the rail and the lower tap falls to ground. Both
    thresholds then read "OK", so the whole window is dormant. Today every threshold has its own divider. Rejected
    (R3).
  - Candidate A's tap in the bus divider's bottom leg is a shared divider. Its new fault modes are listed in its brief.

## 3. Ranked candidates

Net value means cost and parts saved, minus risk. "FMEA" marks a change to a safety argument: **re-run the FMEA before
adoption**. Numbers come from `results/candidates.json`; × 500 is per lot.

| Rank | Id | Change | Placements | Lines | $ / board JLC (card) | $ per 500 JLC | Risk | FMEA | Availability (JLC 2026-10-15) | Layout |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| 1 | **A** | OVP → U14's spare INB channel; U14 → TPS3701; NAND3 → G132 Schmitt NAND2; U7, U15, R36, R37, C33, C34, C49 out; R30 → 13.0 k + 2.74 k; R48 105 k → 102 k | **−6** | −1 | **−1.24** (−1.14) | −618 | medium | **yes** | TPS3701DDCR C132788 26,599; RT0603BRD0713KL 19,105; RT0603BRD072K74L 7,216; RT0603BRD07102KL 9,451; G132 on BOM; all Extended | G08 HOT / Kelvin island only; U8 SOT-23-6 → SOT-23-5; frees two SOT-23-5 and five 0603; no barrier part |
| 2 | **C** | U10 (CT+) + U12 (ZC) → TLV3202AIDR; U11 (CT−) stays single | −2 | +1 | **−0.64** (−0.31) | −320 | low–med | yes (light) | TLV3202AIDR C129325 7,339, Extended | SELV CT block (U10 / U12 are 4.8 mm apart at y −129.7); SOIC-8 replaces two SOT-23-5 and one 0603; check the SELV spine lock |
| 3 | **B** | Per rail: TL431A, LM339B, rref, ½-ref divider → two TPS3701 (one per window), own 2-R dividers, +100 nF | **−6** | −2 (−3 with A) | +1.63 (+0.26) | +817 | medium | **yes** (safety-positive) | TPS3701 as A; RT0603BRD0710K2L 13,263; RT0603BRD07453KL 5,264; RT0603BRD0744K2L 4,707; others on BOM | Each in its own island (N_LS, N_HA, N_HB); SOIC-14 + SOT-23 + 1206 + 2×0603 → 2×SOT-23-6 + 0603; no crossing |
| 4 | E | 2×10 µF → 1×22 µF (CL32B226KAJNNNE) per VSS; SRC−N sits at ≈2 V so DC bias is small | −4 | +1 | −0.63 (−0.63) | −313 | medium | F6 rail re-qual | C309062 90,706 | 4 VSS banks; frees four 1210 |
| 5 | A0 | Fallback if A's shared die is refused: U14 → TPS3701 + R48 → 102 k only (BOM-only) | 0 | 0 | −0.46 (−0.01) | −232 | low | threshold re-derivation | as A | none |
| 6 | D | U1 / U2 → 2EDR9259X (15 V UVLO), monitor kept | 0 | 0 | +0.48 (+0.97) | +238 | low | adds a backstop | **12 at JLC**: hold | same pads |
| 7 | F | HS split via the RECOM COM regulator (ALT-BIAS A2) | ≈ −4 | ≈ −1 | ≈ −0.75 (not costed in detail) | — | high | **yes** + full F6 | as built | HS islands |
| — | H | Delete C24 (V15_LS 10 µF) | −1 | 0 | −0.16 | −79 | unknown | no | — | **hold**: C24 sits 20 mm from U26 beside U3 / U14 (103.3, −62.2) and is V15_LS's only bulk there; needs a PI / LDO-input check |
| | **A+B+C** | build together (they share the TPS3701 line) | **−14** | **−3** | **−0.26** (−1.21) | −131 | | yes | | |

**Why B ranks above E although it costs money.**

- E saves $0.63 but adds a line and re-opens the F6 rail qualification for no functional gain.
- B removes more placements and lines and improves four FMEA rows:
  - C2 / C4: the die and reference single points are split;
  - C7: the sliver closes;
  - S1: the rail-tolerance corners are fixed.
- On cost alone B ranks last. If the owner reads net value as dollars only, take A + C (−8 placements, −$1.88) and
  hold B.

## 4. Candidate briefs (top 3)

### Brief A: OVP onto U14's spare over-voltage channel (G08)

**Mechanism.**

- U14's channel B (INB, rising-threshold over-voltage detector) is unused today. INB is tied to OCP_KELVIN_P and OUTB
  sits on the single-pin net `outb` (netlist).
- Feeding INB from a tap in the bus divider's bottom leg makes U14 a two-channel fault detector: OUTA low on HOT5 UV,
  OUTB low on bus OV, both open-drain on the same R50 pull-up.
- A Schmitt-input NAND2 then replaces the NAND3 and the separate Schmitt buffer U15.

**Parts out (8 placements):** U7 TLV3201AIDBVR; C34 100 nF; R36 10.0 k 0.1 %; R37 140 k 0.1 %; C33 1 nF C0G; U15
SN74LVC1G17DBVR; C49 100 nF; R30 15.8 k 0.1 %.

**Parts in / changed (2 new placements):**

- R30a 13.0 k 0.1 % RT0603BRD0713KL (C861121), VSENSE_IN → OV_TAP.
- R30b 2.74 k 0.1 % RT0603BRD072K74L (C861304), OV_TAP → OCP_KELVIN_P.
- U14 TPS3700DDCR → **TPS3701DDCR** (C132788).
  - Same DDC pinout.
  - VDD rated to 36 V against V15_LS, so the faulted 24 V raw rail also stays within the rating.
  - ±0.75 % thresholds.
- R48 105 k → **102 k** RT0603BRD07102KL (C861068). This keeps the HOT5-UV band on TPS3701's thresholds:
  - falling 4.41–4.55 V (today 4.42–4.64 V);
  - rising 4.45–4.66 V (today 4.52–4.68 V).
- U8 SN74LVC1G10DBVR (SOT-23-6) → **SN74LVC1G132DBVR** (SOT-23-5, existing line C403723).

**Netlist change.**

- U14.4 (INB): OCP_KELVIN_P → OV_TAP.
- U14.6 (OUTB): `outb` → HOT5_UV_RAW, which is wired-AND with OUTA; rename it e.g. HOT5_OV_OK_RAW.
- U8: A = OCP_OK_HOT, B = HOT5_UV_RAW, Y = BUS_FAULT_HOT, VCC = HOT5, GND = OCP_KELVIN_P. C35 stays.
- Nets deleted: OVP_THRESH, OVP_OK_HOT, HOT5_OK_HOT, `outb`.
- REF25's load falls by the 150 k OVP divider, so LM4040's cathode-current floor improves.

**Function equivalence** (`results/ovp_band.json`; the control reproduces today's band from the committed round-3 model).

| | Today (U7 + LM4040A + R36 / R37) | A (TPS3701 INB + R30a / b) |
|---|---|---|
| OVP trip band, −10 / 85 °C | 272.09–288.02 V | **269.61–284.03 V**: the upper corner (ratings basis) is 4.0 V lower, the lower corner 2.5 V lower (0.9 %) |
| Release | ≈ trip (1.2 mV hysteresis) | 262.8–281.9 V (TPS3701 VIT−(INB) 387–400 mV); a plug-in overshoot (O1: asserted 1.3–2.2 s) asserts up to ≈ 0.2–0.3 s longer (scaled by ln(272.1/262.8) / ln(370/280)) |
| Response | TLV3201 ≤ 55 ns + VSENSE_IN RC 15.7 µs | TPS3701 tpd(HL) 9.9 µs **typ, no max** (SBVS240C §6.6) + the same RC; the job is a restart inhibit on a ms-to-s pumped bus |
| Supply | HOT5 (lost with HOT5; HOT5-UV covers it) | V15_LS: OVP stays valid while HOT5 sags (improvement) |
| AMC1311 scale | 15.8 / 1895.8 | 15.74 / 1895.74: **−0.38 %**, inside D-11's ±6 %; update the controller's VBUS constant (120.0 → 120.45) |

- A strictly-inside pair needs 2.71 k 0.1 % plus 13.0 k (272.6–287.2 V). JLC has no 2.71 k 0.1 % in stock (every maker
  shows 0).
- The TPS3700 cannot meet the acceptance with stocked values, so A requires the TPS3701.

**Safety: the FMEA delta, to run before adoption.**

1. **New common die.** Under 60335-1 19.11.2 f) (all IC outputs in any state), a U14 fault masks OVP and HOT5-UV
   together. Today those are U7 and U14 separately.
   - OCP (U6) is untouched, so no single fault loses the shoot-through trip.
   - Losing OCP still needs a second fault (HOT5 sagging below TLV3201's 2.7 V).
2. **New divider modes.**
   - R30a open: OVP dormant, but VSENSE_IN floats high, so the AMC reads full scale and firmware sees an over-voltage.
   - R30b short: OVP dormant and the AMC reads 18 % low.
   - Today R30 short gives VSENSE = 0 (OVP dormant, obvious to firmware), and R30 open trips OVP.
3. **Accuracy and timing** as in the table. FAULT-INTERFACE's concern (a slow open-drain edge into ordinary logic) is now
   met by the NAND's own Schmitt input.

**Gates to re-run:**

- `audit.rs`:
  - the OVP rules (`swapped_ovp_comparator_inputs_fail`, `ovp_bypassing_isolator_path_fails`);
  - the HOT5-supervisor mutation tests;
  - the NAND identity;
  - `min_reference_cathode_current_ua` (drop the 150 k term);
  - new rules: INB on OV_TAP, OUTB on the NAND input, R30a / R30b identity.
- `verify_source.py`, and the frozen netlist (atopile 0.2.69).
- Task-02 OVP band and the Kelvin budget (HOT5 load −40–65 µA).
- FAULT-INTERFACE truth table: NAND3 → NAND2, and the HOT5-UV/OV row.
- OPEN-ITEMS S15's trip list (names U7).
- Datasheet ledger: TPS3701 entry and U8 row.
- Chain: DRC, `return_path19` (new OV_TAP net), `bypass_check` (U14 / C48), task 04.
- Controller: VBUS constant.

**REJECT if:**

- the certifier or the FMEA does not accept OVP and HOT5-UV on one IC (then build A0 only);
- the as-built resistor model puts the OVP upper corner above 288.0 V;
- the controller cannot plausibility-check VBUS against the R30a-open / R30b-short modes;
- OV_TAP cannot follow the old VSENSE_IN → U7 corridor inside the Kelvin pour. That corridor ends 4.6 mm from U14:
  U7 is at (108.4, −57.7), U14 at (108.4, −53.1) and R30 at (119.1, −68.4).

### Brief C: CT positive trip and zero-cross in one TLV3202 (G09)

**Parts out:** U12 TLV3201AIDBVR, C46 100 nF.

**Parts in:** U10 TLV3201 → **TLV3202AIDR** (SOIC-8, C129325, 7,339 in stock). C44 stays as its decoupler.

**Netlist:**

| TLV3202 pin | Net |
|---|---|
| 1OUT | CT_OC_POS |
| 1IN+ | CT_SENSE_MON |
| 1IN− | CT_REF_HI |
| 2OUT | CT_ZC |
| 2IN+ | CT_SENSE_MON |
| 2IN− | CT_S2 |
| VCC | V3V3 |
| GND | SELV_GND |

Both comparators already share their + input net. U11 (CT_OC_NEG) stays on its own die: the two trip polarities are
mutually redundant on a sinusoidal tank current, and a pos + neg pair would put both on one die (19.11.2 f).

**Equivalence.**

- Same 40 ns family.
- Offset: TLV3202 6 mV max over temperature against TLV3201's 4 mV (SBOS561C §6.5 / 6.7). At 0.015 V/A that widens the
  CT+ band by ≈ 0.13 A per side (64.55–76.09 → ≈ 64.4–76.2 A).
- Zero-cross offset grows from 0.27 A to 0.40 A worst case: about 0.9° instead of 0.6° at 25 A pk / 33 kHz, and more at
  light load.

**Safety.** The CT+ trip (safety) now shares a die with ZC (control and firmware phase). An IC fault loses CT+ and ZC
together. CT− still trips, and the DC-bus OCP stays independent on the HOT side.

**Gates:** re-run the CT band tool with Vos = 6 mV; firmware ZC calibration budget (DECISIONS 54's 5° latch lists
"zero-cross calibration error" as an S4 trigger); audit.rs CT comparator identity rows; ledger; SELV-block DRC and spine
lock (this block may sit in the locked SELV spine; take the spine owner).

**REJECT if:**

- the firmware ZC error budget cannot absorb +2 mV;
- the FMEA wants the CT+ trip off any die that carries a control signal;
- the SOIC-8 cannot sit where U10 / U12 / C46 are without disturbing the SELV spine.

### Brief B: rail monitor core → two TPS3701 per rail (G07)

**Per rail (LS / HS-A / HS-B; designators in that order):**

**Out:**

- the TL431A reference (U17 / U19 / U21);
- rref 2.2 k 1206 (R59 / R63 / R65);
- the ½-reference divider (R79–R80 / R97–R98 / R112–R113).

**Replaced:** LM339B (U29 / U30 / U31) → TPS3701DDCR "negative-rail window".

**Added:** one TPS3701DDCR "span window" and one 100 nF.

**Wiring:**

- **Negative-rail window IC:** VDD = p, GND = n, INA = `uv`, INB = `ov`.
- **Span window IC:** VDD = p, GND = n, INA = `spanuv`, INB = `spanov`.
- All four open-drain outputs go onto `good`. `rpull` (10 k to the local 5 V), the four 1 nF node caps, the LDO and
  `cmonitor` are unchanged.
- The `ref` and `halfref` nets disappear.

**Dividers** (each threshold keeps its own two resistors):

| Threshold | Top / bottom | Parts (JLC stock) | Nominal | Trip band | Today's band | Margin to rail (new / old) |
|---|---|---|---|---|---|---|
| neg UV (INA) | 7.68 k / 2.21 k | RT0603BRD077K68L / RT0603BRD072K21L (both on BOM) | 1.790 V | 1.765–1.815 | 1.737–1.862 | +0.108 / +0.107 V |
| neg OV (INB) | 10.2 k / 2.21 k | RT0603BRD0710K2L (13,263) / on BOM | 2.246 V | 2.214–2.279 | 2.127–2.285 | +0.099 / +0.068 V |
| span UV (INA) | 453 k / 11.7 k | RT0603BRD07453KL (5,264) / TNPW060311K7BEEA (on BOM) | 15.89 V | 15.63–16.15 | 15.58–16.87 | **+0.028 / −0.294 V** |
| span OV (INB) | 44.2 k / 1.00 k | RT0603BRD0744K2L (4,707) / RT0603BRD071KL (on BOM) | 18.08 V | 17.80–18.36 | 17.14–18.56 | trip +0.37 / −0.29 V; release −0.07 V |

How the table was computed:

- Bands use TPS3701 VIT 397–403 mV (SBVS240C §6.5), 0.1 % + 25 ppm × 125 K resistors, and ±25 nA input current.
- Every new band lies inside today's (`results/monitor_tps3701.json`); the control reproduces the P4 study's committed
  old bands.
- "Margin to rail" is measured on the binding side, including TPS3701 hysteresis (UV: start-up/release up to 413 mV;
  OV: release down to 387 mV). The rails are:
  - LS TPS7A4700 17.0 V ±2.5 % (SBVS204G p.6 "overall accuracy");
  - HS RECOM 16.91 V ±1.5 %;
  - neg 1.968–2.059 V (bom-simplification `neg_rail.json`).

**Safety (FMEA c24 §3a rows to re-run; all move in the safe direction):**

- **C2 (an output open masks one threshold):** same class as today.
- **New row: one IC fault, VDD or GND open.** The outputs go high-impedance and one window (2 thresholds) is masked.
  Today an LM339B supply-pin fault masks all four thresholds (both windows) of the rail.
- **C4 (TL431) disappears:** each TPS3701 has its own internal reference.
- **C7 (the sliver) closes:** TPS3701 works from VDD 1.8 V and drives OUTA low in UVLO (1.3–1.7 V); below V(POR) 0.8 V
  the 5 V pull-up is itself dead (§7.4).
- **Supply current:** each rail draws 6.7 mA less (the reference branch). That is ≈ 0.11 W per rail. The RECOM load falls
  8–14 %, partly undoing DECISIONS 55's +16 %. This is an estimate, not run through B3.
- **Timing:** TPS3701 tpd(HL) is 9.9 µs typ with no max, against LM339B ≈ 1 µs. It adds to the ≤ 90 µs heartbeat figure.
  Rail faults are ms-scale.
- **Power-up:** TPS3701 needs VDD > 1.8 V for ≈ 155 µs before its output is valid, against P−N ramps of ms. Capture it
  on the bench.

**Gates to re-run:**

- `audit_f6.rs` RailMonitor rows: the BiasComparator / BiasReference identity and window topology, and the mutation
  tests.
- `verify_source.py`.
- ECO "Mandatory rail monitor" thresholds.
- `bias_sizing.py`: the monitor allowance (14 mA → ≈ 4 mA).
- FMEA c24 §3a and `fmea_metric.py`.
- g05 `truth_table.py` with TPS3701 semantics (the sliver row now reads "caught").
- `bypass_check` for the new decouplers; `return_path19` for `good`; B3 (lower heat).

**REJECT if:**

- the real parts or stock break band dominance;
- a power-up capture shows `good` high while a window is violated;
- the owner will not pay +$1.63 per board (+$817 per 500) for these safety corners.

## 5. Rejected or held, and why

| # | Idea | Why not |
|---|---|---|
| R1 | One comparator package across the three monitors | The domains float on N_LS / N_HA / N_HB; sharing needs analog sense lines across two barriers (no added crossings allowed) |
| R2 | Driver UVLO in place of the monitor | 8 V option: §2. 15 V option (D): span-UV only, per channel; −2 V rail and OV unseen; JLC 12 in stock. Keep D as an optional backstop, not a deletion |
| R3 | Three-resistor ladders (monitor windows, CT refs), the P4 design | A middle-resistor open masks both thresholds of the window, or both CT polarities: a new dormant single fault for 1–2 placements |
| R4 | C-hot: U6 OCP + U7 OVP → TLV3202 | Same $0.64, but OCP Vos 6 mV → ±12 A band (today ±10 A; 1 mV = 2 A) and OCP + OVP on one die; A removes more and keeps OCP alone |
| R5 | U9 + U32 on one dual CA-IS3720 (both have a spare channel) | Different side-1 grounds (OCP_KELVIN_P vs N_LS); already rejected in g05 P2 |
| R6 | Both legs' DIS NANDs, or DIS + U40 / U46, in one quad Schmitt NAND | Removes the per-leg independent disable (D-25, FMEA C9); DIS stubs 47 mm apart; the hold node is high-impedance |
| R7 | D18 + D20 → one BAT54A | −1 placement, +1 line; one package for both HS vetoes (the source comment already rejects it) |
| R8 | Merge HOT5 LDO U3 with the LS 5 V U37 | Different grounds (OCP_KELVIN_P vs N_LS); it would load the Kelvin reference |
| R9 | LS span from a third RECOM instead of TPS7A4700 + split | +$3.4 per board and ≈ 1 W more heat |
| R10 | Split-output driver to delete the PMEG + 1 Ω turn-off path | No drop-in dual reinforced DIS driver with split outputs inside the DT window; re-qualifies CMTI (F6), D2 and D5. The PMEG's 7-piece JLC stock is a sourcing item |
| R11 | Delete gate hold-offs R11 / R13 / R19 / R21 | They hold the gates with the driver unpowered |
| R12 | 4 × 1206 line-ZC string → 2 × 2512 | Surge and voltage share on mains; ≈ $0 saving |
| R13 | Reservoir 2 × 1 µF → 1 × 2.2 µF (−4 more placements) | Held: the only 2.2 µF 25 V X7R 0603 in JLC stock found was an HRE part (C23692976, 3,139) with no DC-bias data; fold into E only with a characterised part |
| F | HS split via the module COM regulator (ALT-BIAS A2) | −2.5 V minimum (window re-scale) and no transient model; full F6 re-qualification; ALT-BIAS: "not for this lot" |
| H | Delete C24 | Hold: the only V15_LS bulk near U3 / U14 |

## 6. Side findings (pre-existing; not caused by any candidate)

- **S1. Today's span window overlaps the rails' tolerance at worst-case corners.**
  - Span-UV upper corner 16.87 V > LS TPS7A4700 minimum 16.575 V (±2.5 %, SBVS204G p.6) and > HS RECOM minimum 16.66 V.
  - Span-OV lower corner 17.135 V < LS maximum 17.425 V.
  - Under a full worst-case stack (TL431A + 34 mV drift, LM339B Vos, resistor corners), today's monitor can refuse to
    start or nuisance-trip.
  - Real units will rarely stack like this, but the corner fails on paper. B fixes it; or re-centre today's dividers.
- **S2. The scorecard prices 58 of 93 lines at estimates, mostly class defaults** (Price bases above), so A / B / C would score
  wrong. Refresh those rows in a stock addendum before scoring any of them.
- **S3. `SNAPSHOT-2026-10-15.csv` prices U41 / U42 (R24C2T25/R-R) at $0.0204.** This is a JLC "listed_no_stock"
  artefact; the card uses DK $7.37. The cost metric is unaffected, but the snapshot's $ columns are not usable for this
  row.
- **S4. The `libsource (part …)` field in `frozen/default.net` is not per-component.** R3, R4, R26 and R59 all read
  1206W4F1003T5E. MPNs must come from `default.csv`, as these scripts do.

## Datasheets (dl/, untrusted; `dl/MANIFEST.json` has full hashes)

| File | Source | Revision | sha256 (16) |
|---|---|---|---|
| 2edr8259.pdf | https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf | Rev 1.7, 2026-04-09 (= repo ledger hash) | f49391ca00e15397 |
| tps3701.pdf | https://www.ti.com/lit/ds/symlink/tps3701.pdf | SBVS240C (rev Feb 2019) | 27c94a6c3a243bf5 |
| tps3700.pdf | https://www.ti.com/lit/ds/symlink/tps3700.pdf | SBVS187G (rev Feb 2019) | 3bb7daed20b154bf |
| tlv3201.pdf | https://www.ti.com/lit/ds/symlink/tlv3201.pdf | SBOS561C (rev May 2024) | 1777bba814c74772 |
| lm339b.pdf | https://www.ti.com/lit/ds/symlink/lm339b.pdf | SLCS006Z (rev May 2025) | 406e7bd1ab1f2fb1 |
| tl431.pdf | https://www.ti.com/lit/ds/symlink/tl431.pdf | SLVS543S (rev May 2024) | ed2e90697de4e2c5 |
| tps7a47.pdf | https://www.ti.com/lit/ds/symlink/tps7a47.pdf | SBVS204G (rev May 2026) | 8ca46a9968923d2e |

JLC records (stock, class, price ladder, fetch time, URL) are in `results/jlc_parts.json`.

## Limits

- **Desk study.** There is no SPICE run. The TPS3701 and TLV3202 timing figures are datasheet typicals. The band
  calculations are worst-case vertex stacks on the repo's own models.
- **Price rows.** The JLC ladder prices for new parts are one day's public records. AEC grade is not relevant, since no
  candidate touches an automotive or agency-marked part. UL / VDE are unchanged because no candidate changes a
  `BARRIER_PARTS` member except D, which stays in the same certified family (2EDR, UL 1577 E311313 / IEC 60747-17
  40055138 on p.1).
- **Not checked:** DigiKey stock for the 2EDR9259X; the FMEA FIT figures for A / B / C (`fmea_metric.py` not re-run); any
  layout feasibility beyond positions in `positions-kicad.csv`.

## Integration verdict (2026-10-15)

Reproduced in the repo: each script reruns to byte-identical results from the unit path. The default PS path now
resolves to the unit; the JLC records moved from `dl/jlc-raw` to `scripts/jlc-raw`; the datasheet manifest is
`results/datasheet-manifest.json`; the PDFs are not committed.

- **S1 is taken as a correctness item: OPEN-ITEMS S16.** Fix order:
  1. Re-centre today's span and −2 V dividers (BOM-only), if a worst-case stack fits both rails' tolerance with margin.
  2. Otherwise candidate B.
- **A: not adopted.** OVP and the HOT5 undervoltage supervisor would share one IC, losing the independence between a
  protective trip and a supply supervisor, for $1.24 a board. A0 (BOM-only) is kept on file.
- **C: not adopted now.** A protective CT trip would share a die with the functional zero-cross, for $0.64 a board.
- **B: kept as S16's fallback fix.** It costs +$1.63 a board, isolates faults better and closes the sliver.
- **E: deferred.** It re-opens the F6 rail qualification.
- **S2 (scorecard price estimates): OPEN-ITEMS C8.** S3 (the RECOM snapshot price artefact) is noted there too.
