# Stage 18: RES_A to SELV/PE creepage at 12.6 mm (DECISIONS item 18)

> Board `3768a12675f8d61f91fc4a96dd267522e68f454f8f300634aca2ae16afc6dd1a`, copper.json `e6ad813b…`, Gerber ZIP
> `021bf8fd…`, tag `native21s18`. Run dirs: `worktrees/runs-native21/s18/` (passes `v18/i1..i2`, chain build `s18/`).

## Why

At the 28 A ceiling RES_A (the coil / bank node) is **297 V rms / 656 V pk to earth in normal use**
(`../owner-items/m6m10/coil-selv-28a/`, DECISIONS item 7). Reinforced creepage at PD3 / IIIa in the >250–400 V band
is **12.6 mm** (IEC 60335-1 Table 17 × 2, the repo's transcription), not the board-wide 8.0 mm floor. On stage 17b,
two SELV runs on B.Cu were under 12.6 mm from the bank's RES_A strip.

## Before / after (outer layers, same-layer straight line; `res_a_creepage18.py`)

| Layer | Pair | Stage 17b (`control17b.txt`) | Stage 18 (`res_a18.txt`) |
|---|---|---:|---:|
| B.Cu | RES_A – LINE_ZC_RAW | **8.145 mm** | **13.375 mm** |
| B.Cu | RES_A – V15_SELV | **9.400 mm** | **14.400 mm** |
| B.Cu | RES_A – PE (J6) | 19.204 mm | 19.204 mm |
| F.Cu | RES_A – any SELV/PE (incl. the J5 ring lug, 5 mm radius) | 20.393 mm | 20.393 mm |
| In1 / In2 (reported, solid insulation) | C152.1 (RES_A) – v3v3 / selv_gnd islands | 9.694 mm | 9.694 mm |

Other tank nets, outer-layer minimum: CRBLEED_1 70.15 mm (also held to 12.6 mm, below), CRBLEED_2 63.79, CRBLEED_3
58.44, COIL_FEED 20.45, SW_A 8.34, SW_B 8.145 mm (99 V rms: 8.0 mm floor, unchanged).

## Change (smallest that clears it)

`native-21/layout/patches21.py` stage 18: the two base B.Cu polylines are removed (`REMOVE`, boxes holding exactly
them) and re-laid by `add_stage18` with their base geometry outside the bank and 45° doglegs into lanes south of it:
LINE_ZC_RAW at y 127.5 (was 121.27–122.87), V15_SELV at y 128.6 (was 123.6), between x ≈ 137 and 187. Same widths
(0.25 / 0.4 mm), same end points and vias; no part, pour, via or other net moves (copper.json differs from 17b in
exactly these two tracks). No slot was needed, so JLC slot rules do not apply; clearance through air is the same
13.375 mm (≥ 3.0 mm). Images: `before-17b-BCu.png`, `after-18-BCu.png` (`plot_window18.py`; pads drawn on every
panel whatever their side).

## Gates added

- `rules21.RES_A_NETS = {res_a}`, `RES_A_CREEPAGE = 12.6` (from `write_rules21.py`); `rules21.clearance_on()` and
  `geom21.conflicts` apply it on F.Cu / B.Cu, so authored copper (`put()`) and the routing passes keep it.
- `write_rules21.py`: a last DRU rule `RES_A to SELV/PE: reinforced 12.6 mm, outer layers (stage 18)`,
  `(layer outer)`, clearance and creepage 12.6 mm. Inner layers keep the 8.0 mm SELV/PE rule. Also: net groups are
  now built from `sorted(nets)`, so the DRU text no longer follows the hash seed (17b "not fixed" item).
  **Negative control:** the 17b board's own DRU plus this rule gives 16 errors, all this rule, all on the two runs
  (8.145 … 9.445 mm, creepage 8.145 mm); stage 18 is 0 / 0 / parity 0 (`drc-control17b.txt`).
- `barrier21.py`: the first line now reports the 8.0 mm plan-view check **and** RES_A per outer layer at 12.6 mm
  (min per layer); exit 1 on either.
- `barrier_gate21.py`: the existing Rust binary (not rebuilt) also runs once per outer layer, HOT = RES_A, floor
  12.6 mm, on a subset of the verified evidence (that layer's RES_A / SELV / PE items, census recounted), so every
  pair it reports is same-layer copper. 17b: F.Cu 0, B.Cu 15 (min 8.14 mm). Stage 18: 0 / 0 (956 / 560 items).
- `plot_copper.py --dump` now writes each pad's copper `layers` (SMD side); `res_a_creepage18.py` falls back to the
  `evidence.json` beside an older dump.
- `res_a_creepage18.py` (this folder; run by `chain.sh`): every RES_A-to-SELV/PE pair per layer, asserts ≥ 12.6 mm on
  F.Cu / B.Cu. `--control` on the 17b dump must report exactly the 8.14 / 9.40 mm pairs (it does, `control17b.txt`).

## Inner layers: basis and flag

The repo's basis is DECISIONS item 7 ("paths through the inner-layer laminate are solid insulation") and item
2026-10-08 M11 (IEC 60335-1 29.3: reinforced solid insulation 2 mm, or 3 layers, or the 29.3.3 test). Every inner
RES_A copper item is ≥ 8.0 mm from all SELV/PE copper in plan view on every layer (barrier21 / Rust gate), so the
distance through laminate is ≥ 8.0 mm ≥ 2 mm. **Flag (certifier):** no repo record says whether the core/prepreg
interface on one inner layer is a cemented joint (solid) or a creepage path. If it is a creepage path, C152.1's inner
rings are 9.694 mm from the In1 v3v3 / In2 selv_gnd islands, under 12.6 mm; the fix would be pulling those SELV
islands back ~3 mm at x 150–170, y 122, or removing C152's inner rings (KiCad `FlashLayer` on the stage-18 board:
every RES_A THT pad, C21–C23 / C151 / C152 and J5, still flashes on In1 and In2).

## Which nets need 12.6 mm (`tank_taps18.py`, control RES_A 297.0 / 655.5 reproduced)

| Net (bleed-string tap) | L70 / C050 coil of record | Any L 70–90 µH |
|---|---:|---:|
| RES_A | 297.0 V rms / 655.5 pk | 314.1 / 690.4 |
| CRBLEED_1 (3/4) | 242.5 / 541.1 | **255.1** / 567.3 |
| CRBLEED_2 (1/2) | 189.6 / 426.7 | 197.7 / 444.2 |
| CRBLEED_3 (1/4) | 140.0 / 312.4 | 143.7 / 321.1 |
| SW_A, SW_B, COIL_FEED | 99.0 / 198.0 | 99.0 / 198.0 |

CRBLEED_1 is in the 8.0 mm band for the coil of record but 255 V rms for an L80/L90 coil, so
`res_a_creepage18.py` also holds it to 12.6 mm (it is 70 mm away). The DRU rule stays RES_A-only.

## Parts that straddle the tank and SELV/PE (datasheets read, not committed)

No footprint has a RES_A pad and a SELV/PE pad. T1 is the only part on the coil path, and its primary is the
**SW_A end** (T1.1 SW_A, T1.2 COIL_FEED → J2 → coil → J5 RES_A), so it sees 99 V rms / 198 V pk (crest rms 140 V),
not 297 / 656.

| Part | HOT side (working V to earth) | Rating (datasheet) | Verdict |
|---|---|---|---|
| T1 CST3015-100ED | SW_A / COIL_FEED, 99 V rms / 198 V pk, 35–60 kHz | Coilcraft doc 1608-1 rev 09/08/25: "designed to meet reinforced insulation, at least 8 mm creepage/clearance", 5000 V rms 1 min hipot between windings. **No working voltage, CTI / material group, PD or HF insulation rating stated** (0.78 to > 1000 kHz is the signal range) | PASS at the voltage it sees (≤ 250 V rms band: 8.0 mm reinforced; hipot 5 kV ≥ 3 kV). It would **not** meet 12.6 mm if it ever sat on RES_A. HF / CTI rating not established: Coilcraft question (existing open item, D5-BASIS) |
| U1 / U2 UCC21550BDWK | SW_A / SW_B / LOW, ≤ 99 V rms / 198 V pk | Reinforced; VIOWM 1500 V rms / 2121 V DC, VIORM 2121 V pk, CLR / CPG > 8 mm, CTI > 600 (group I), PD2 table | PASS |
| U9, U32–U34 ISO7710DW | LOW / SW_A / SW_B | Reinforced (VDE); VIOWM 1500 V rms, VIORM 2121 V pk, CLR / CPG 8 mm, CTI > 600 | PASS |
| U4 AMC1311BDWV | LOW (bus sense) | Reinforced; VIOWM 1500 V rms, VIORM 2120 V pk, CLR / CPG ≥ 8.5 mm, CTI ≥ 600, group I | PASS |
| U36 VOL628A-3X001T | ZC LED (mains, 140 V rms / 198 V pk) | Repo record (D5-AUDIT, Vishay doc 82401 rev 1.9 p.4): CLR / CPG 8.0 mm, VDE option 1 (download today returned HTML, not re-read) | PASS on record |
| PS1 IRM-20-15 | Mains, 140 V rms | Class II, UL / IEC 62368-1, 4.2 kV ac I/P–O/P | PASS |
| C3 / C4 DE1E3RA222MA4BP01F | Mains to PE, 140 V rms | Y-cap path, unchanged; datasheet distances still "not in table" (D5-AUDIT) | Not a RES_A part; open as before |

Mounting holes: H6 (nylon) is 8.40 mm from RES_A B.Cu copper at its wall. With the required ≥ 10 mm nylon standoff
(DECISIONS M4 / FAB-NOTE) the RES_A-to-chassis surface path is ≥ 8.4 − 1.4 + 10 ≈ 17 mm ≥ 12.6 mm.

No rating fails; no part changes.

## Files

`res_a_creepage18.py`, `res_a18.txt` / `res_a18.json` (stage 18), `control17b.txt`, `drc-control17b.txt`,
`tank_taps18.py` / `tank_taps18.txt`, `plot_window18.py`, `before-17b-BCu.png`, `after-18-BCu.png`.
