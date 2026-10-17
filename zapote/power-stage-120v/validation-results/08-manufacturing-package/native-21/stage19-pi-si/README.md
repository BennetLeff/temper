# Stage 19: converter-local capacitors, return paths, local bypass (DECISIONS item 19)

> Board `370fcf373c97241966f0bb9a077b513903354a20bcd659545819e9d363b3bd1c`, copper.json
> `f287dc4afc64bdf5d759fb237ae3771f71b1489268c91399e064e84c2af0ca72`, Gerber ZIP
> `67e1e07f594039504e6b633eb277a9ab8be2ea745711846e5892eb014cabff6b`, tag `native21s19`.
> Run dirs: `worktrees/runs-native21/s19/` (routing passes `p10/i1..i2`, chain build `s19/`, library-table DRC `libdrc/`).
> Findings from the stage-18 review (`output/preroute-stage18-2026-10-12/REPORT.md`, `output/return-path-stage18-2026-10-12/REPORT.md`):
> PI1, PI2, SI1, SI2. N1 / K6 are the other session's commit `365151b62` folded in (credited in DECISIONS item 19).

## Scripts (re-runnable)

| Script | Measures | Asserts |
|---|---|---|
| `pi_distances19.py BOARD [--control]` (KiCad python) | pad-centre distance, converter power pin to its cap's pad on the same net (the review's metric) | every supply side (U41 / U42 VOUT+, U26 OUT / IN / NR) and the 100 nF return sides <= 3.0 mm |
| `native-21/layout/gates/return_path19.py DUMP [--control]` | for each fast signal: reference under every 0.25 mm of track, coupled dedicated returns, every layer change and its transfer-cap distance | bus_fault_hot on ocp_kelvin_p end to end; ct_zc changes <= 3.0 mm; pwm_hb driver-side changes <= 3.0 mm; transition counts |
| `native-21/layout/gates/bypass_check.py BOARD OUT` (from `365151b62`) | IC supply / return pin to its 100 nF | N1 limits (11 ICs) |

`chain.sh` runs all three on every build; `regate.sh` runs `bypass_check.py` and fails on it.

## PI1 / PI2 (`pi19.txt`; control `control18-pi.txt` on the stage-18 board `3768a126…` reproduces the review)

| Check | Stage 18 (control) | Stage 19 | Return side, stage 19 |
|---|---:|---:|---|
| U41 VOUT+ 28/29 → C104 10 µF | 25.57 mm | **2.88 mm** | 5.70 mm to VOUT- (in the F.Cu n_ha pour, via to In1 n_ha beside it) |
| U41 VOUT+ → C75 100 nF | 46.48 mm | **2.79 mm** | **2.88 mm** to pin 31 |
| U42 VOUT+ → C108 10 µF | 26.53 mm | **2.79 mm** | 5.69 mm (pour + via) |
| U42 VOUT+ → C82 100 nF | 51.79 mm | **2.93 mm** | **2.86 mm** to pin 35 |
| U26 OUT 1 → C99 | 15.39 mm | **2.81 mm** | **2.81 mm** to GND 5 |
| U26 IN 15/16 → C98 | 14.03 mm | **2.62 mm** | 6.97 mm (component-side n_ls copper + via) |
| U26 NR 14 → C64 | 23.06 mm | **1.61 mm** | 5.19 mm (same) |

Moves: C104 / C75 / R92 / C71 (U41), C108 / C82 / C72 / R94 (U42) beside the VOUT pins (`place.py STAGE19_PI`); U26
3.2 mm east / 2.3 mm down into free board with C99 west, C98 north-east, C64 east and an F.Cu n_ls pour under its GND
side; C14 (U2's VCCI cap, also the pwm_hb transfer cap) under U2's VCCI pins. No part added or removed (353).
Datasheets read (downloaded to the session scratchpad, not committed): RECOM R24C2T25/R Rev.1-2024 p.5 (COUT1 2.2 µF
+ 100 nF VOUT+ to VOUT-) and p.13 (caps between 28/29 and 19-25/30-31/35-36 close to the IC; FB via near FBVOUT-);
TI SBVS204 9.1 (components near their pins, IN/OUT/GND returns joined by a wide component-side copper area).

## SI1 / SI2 (`return-path19.txt`; controls `control18-return-path.txt`, `control-review-dadcaad3-return-path.txt`)

| Signal | Stage 18 | Stage 19 |
|---|---|---|
| bus_fault_hot | In2 over the In1 ocp_kelvin_p / n_ls boundary at (119.035, 75.07); 150 of 251 samples over n_ls; Kelvin return 18.7 mm away | **0 samples over another net**; over the Kelvin pour, then beside (B.Cu, 0.25 mm gap) / under (In2) the Kelvin return to U9; longest unreferenced run 1.25 mm |
| ct_zc | 2 changes: (31.707, 164.595) 37.15 mm, U12.1 via 14.66 mm (stage-18 caps) | **1 change, U12.1 via-in-pad, C46 1.84 mm**; B.Cu to J4.13 |
| pwm_hb | 7 changes: 7.99 / 10.69 / 8.17 / 3.12 / 1.02 / 28.50 / 48.51 mm | 7 changes: driver side **2.39 (C14) / 2.00 (C142) / 2.43 (C47) mm**; J4 side 4.98 / 21.24 / 37.45 / 52.70 mm **OPEN** |
| pwm_lb | F.Cu, no via | F.Cu, no via (re-laid round C14) |

The review's own figures (54.39 / 37.45 / 21.24 mm, ct_zc 37.50 mm, all to C47) were measured on its board `dadcaad3…`
(stage-18 routing with the N1 cap moves); `--control` on that board's dump reproduces them and the crossing exactly.
On the integration stage-18 board the old cap row was still there, so the same vias give 48.51 / 28.50 / 1.02 mm and
37.15 mm (`--expect` figures in the control).

**Open at stage 19 (closed in 19b, below) (pwm_hb, J4 side):** the run from the SELV row to J4.7 crosses pwm_lb's F.Cu lane and the B.Cu fan of permit /
bias_bad / pwm_ha into J4; no v3v3-selv_gnd capacitor lies within 3 mm of its four changes there. Closing it needs either
three 100 nF transfer capacitors at (≈55, 129), (≈56, 157), (≈56, 175) (a schematic change) or a re-route of the SELV
J4 fan. The gate reports these as `open_reference_changes` instead of passing them.

## Other gates on board `370fcf37…` (`chain19.txt`; routing passes `passes19.txt`)

zone priority 25 / 0 equal; DRC 0 / 0 / parity 0 and, with the native-21 library tables, 0 violations and 0 warnings
(`drc-libtables19.json`); barrier21 0, RES_A outer 0 (F.Cu 20.393, B.Cu 13.375 mm); Rust gate 0 over 5,807 items, RES_A
outer 0 / 0 (969 / 584); D5 8.047 / 8.507 mm; fit 405 solids / 0 overlaps / 407 bodies / 0 hits; DFM PASS (746 vias);
Gerber review PASS (862 + 4 slots); bypass 11 / 11; Kelvin R35.2 158.08 mΩ, band 67.72–116.44 A, floor met at the bound;
B3 28 A h25 136.0 °C (R5.4); G6 PASS 50.8 % (`g6-native21s19.json`); audit.rs 79/79, frozen netlist PASS,
verify_source PASS (`audit19.txt`).

## Stage 19b: pwm_hb transfer caps (DECISIONS 19b)

Board `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`, copper.json `ce49f200…`, Gerber ZIP
`c9eaf0d9…` (`chain19b.txt`, `passes19b.txt`). Four 100 nF v3v3-selv_gnd caps C153-C156 (`c_ref_xfer_1..4`), one beside each
J4-side layer change, each pad with its own plane via (0.85-1.51 mm). `return-path19b.txt`: pwm_hb's seven changes are
2.39 / 2.00 / 2.43 / **2.72 / 1.12 / 1.12 / 1.12 mm** (C14 / C142 / C47 / C153 / C154 / C155 / C156); the gate now asserts
every pwm_hb change <= 3.0 mm and the transfer caps' plane vias <= 1.6 mm: PASS. `pi19b.txt` (unchanged), `bypass-check-
native21s19b.txt` 11/11, `drc-libtables19b.json` 0 / 0, `audit19b.txt` (audit.rs 80/80, verify_source 357). bias_bad is
reported, not asserted (ns-class edges from an LVC1G17, but a fail-safe status line that changes state only on a rail
fault; see DECISIONS 19b).
