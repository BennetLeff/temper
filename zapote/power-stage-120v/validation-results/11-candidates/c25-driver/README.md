# Candidate 25: U1/U2 UCC21550BDWKR -> Infineon 2EDR8259 (study, 2026-10-13/14)

Analysis only. No ato, KiCad, cargo or chain runs, and no edits outside this folder. The datasheets were read in a
scratch directory and are not in the repo:

- Infineon EiceDRIVER 2EDR8259H / 2EDRx259X / 2EDRx258X datasheet, Rev 1.7 (2026-04-09), fetched 2026-10-13:
  <https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf>
  (sha256 `f49391ca…33ae33`).
- TI UCC21550 SLUSE89C (Aug 2024), fetched 2026-10-13: <https://www.ti.com/lit/ds/symlink/ucc21550.pdf>
  (sha256 `5f80a86a…c6ba`).

Rerun everything from `zapote/power-stage-120v`, using local ngspice 45.2. The remote FEM box is **not** needed:
it only extracts the inductance matrices (D1), and this study reuses the committed native-21 matrices.

```
python3 -I  validation-results/11-candidates/c25-driver/scripts/dt_window.py
python3 -B  validation-results/11-candidates/c25-driver/scripts/d2_c25.py repro    # reproduces 2 committed as-built rows exactly
python3 -B  validation-results/11-candidates/c25-driver/scripts/d2_c25.py edge     # 864 runs, ~15 min on 8 workers
python3 -B  validation-results/11-candidates/c25-driver/scripts/d2_c25.py dtband   # 3096 runs, ~50 min
python3 -I  validation-results/11-candidates/c25-driver/scripts/summarize_c25.py
python3 -I  validation-results/11-candidates/c25-driver/scripts/jlc_query.py s 2EDR8259   # cached in raw/
```

## Verdict

**GO as a BOM + Rg change** (driver MPN plus R10/R12/R18/R20 3.9 Ω → 8.2 Ω). It needs no footprint change, no
copper change and no logic change. R9/R17 stay at 49.9 kΩ. audit.rs needs new driver data and a wider dead-time
window, which this run supports.

- **Pin and footprint:** compatible with `lib:SOIC16W_Isolated` as it stands.
  - 2EDR8259**X** (DSO-14) has the DWK's exact physical outline. It needs only a pin-map rename: its pins 12/13/14
    go on footprint pads 14/15/16.
  - 2EDR8259**H** (DSO-16) has the same pin numbers as UCC21550 DW16. Its NC leads 12/13 sit unsoldered where the
    footprint has no pads.
- **Rg is mandatory, not optional.**
  - With 3.9 Ω kept, 5 of 96 hard-switching cases exceed 520 V die VDS (up to 595 V). The worst edge is also 26 %
    faster, so the CMTI ratio falls to 1.26.
  - With 8.2 Ω, 144/144 cases pass. The worst edge is 0.99× the as-built edge, so **cmti_gate_ratio_min = 150/95 =
    1.58** (1.59 on the deck ratio).
- **Dead time:** the ±15 % DTC spread cannot fit the ±12.0 % audit window at any resistor value.
  - With 49.9 kΩ the estimate is **408–569 ns**.
  - On the as-built F6 deck (−1.6 V off bias, PMEG discharge), the 2EDR + 8.2 Ω drive passes **3095/3095 completed
    runs from 340 to 600 ns**, with typical, strong and weak output corners, both legs and 27/100/150 °C.
  - One run hit a solver abort. It passes on rerun at 0.1 ns step and at the neighbouring ESL.
  - So DT_WINDOW_NS can move from (391, 498) to (340, 600) for this driver.
- **Metrics:**
  - `zero_stock_lines` 9 → 8.
  - `parts_usd_at_5` +$0.65 (318.23 → ~318.88) and `parts_usd_at_500` +$0.52 (221.82 → ~222.34), at Digi-Key prices.
  - `cmti_gate_ratio_min` 1.316 → 1.58.
  - Lines, placements and vias unchanged.

## 1. Package and pinout

| Body pos. | UCC21550BDWK (now; footprint pad) | 2EDR8259H (PG-DSO-16) | 2EDR8259X (PG-DSO-14, its pin no.) |
|---|---|---|---|
| 1 | INA | INA | INA (1) |
| 2 | INB | INB | INB (2) |
| 3, 8 | VCCI | VDDI | VDDI (3, 8) |
| 4 | GND | GNDI | GNDI (4) |
| 5 | DIS, active high, **internal pull-UP 50–185 kΩ** (open = disabled) | DIS, active high, **internal pull-DOWN** (open = **enabled**) | same as H |
| 6 | DT: R to GND sets DT; open/VCCI = overlap allowed; ≤150 Ω = interlock | STP/DTC: R to GNDI (1.2–100 kΩ) = STP + DT; open/VDDI = both off; GNDI = STP only | same |
| 7 | NC | NC | NC (7) |
| 9 / 10 / 11 | VSSB / OUTB / VDDB | GNDB / OUTB / VDDB | (9 / 10 / 11) |
| 12, 13 | **absent** | **NC leads present** (no pads on the footprint) | **absent** |
| 14 / 15 / 16 | VSSA / OUTA / VDDA | GNDA / OUTA / VDDA | GNDA / OUTA / VDDA (**12 / 13 / 14**) |

Sources: Infineon Table 2 p.3–4 and Figure 2; TI Table 4-1 and Figure 4-2.

Body and lead geometry match:
- Infineon Figures 22/25 (p.31/33): 10.3 × 7.5 mm body, 10.3 mm lead span, 1.27 mm pitch, 0.4 mm lead width, foot
  0.81 ± 0.4 mm. These are the same MS-013 dimensions as TI DW/DWK.
- In Figure 25 the DSO-14 top row sits at ±1.905 / 3.175 / 4.445 mm, i.e. the DWK positions with 12/13 removed.
- The existing pads (1.65 × 0.6 mm at x = ±4.875, 8.10 mm copper gap; FOOTPRINTS.md F8) are close to Infineon's
  recommended land (1.8 × 0.65 mm on a 10 mm centre span, 8.2 mm gap; Figure 23 p.32). The lead tip is at 5.15 mm,
  inside the pad's outer edge at 5.70 mm, so no footprint change is needed.

Differences that matter:
- **DIS default polarity flips.** The board drives DIS from the SN74LVC1G00 NAND (U22/U23) with the 10 kΩ pull-up
  R73/R76, so the truth table is unchanged.
  - Fault case, NAND output open: R73/R76 still hold DIS at about 3.0 V (10 kΩ against the internal pull-down, minus
    27 µA × 10 kΩ input leakage), above VINH max 2.36 V. Outputs stay disabled.
  - With the 2EDR, R73/R76 is the **only** thing that keeps an open DIS disabled. TI's internal pull-up no longer
    backs it up, so the existing audit_f6 check on `r_driver_dis` becomes safety-relevant.
- **DT formula changes**: TI tDT ≈ 8.6·R + 13 (SLUSE89C eq. 1). Infineon tdt = 10·R (Table 6 p.8). Both use the
  same "longer of programmed or input dead time" rule (Infineon section 2.4 and Figure 14; TI 7.4.2.2). The
  controller's 200 ns gap (D-20 O07) stays below the pin, so the pin is still in control.
- **Channel-to-channel:**
  - TI DWK rates |VSSA–VSSB| at 1850 V (footprint descr.). Infineon gives **no** channel-to-channel voltage, only
    creepage: 2.5 mm (H) / 3.3 mm (X) (Table 25 p.19).
  - Switch-node swing is ≤280 V bus, up to ~520 V die peak. This is functional insulation, about 200 V rms.
  - My estimate from IEC 60664-1 Table F.5 (PD2, material group II) is 1.4–1.8 mm needed, so 2.5 mm suffices. That
    is an estimate, not an Infineon rating.
  - The X variant restores the DWK's lead-free gap and avoids two floating leads over v15_ls / n_hb copper. **Prefer
    X; use H as the second source.**
- **NC leads 12/13 (H only):** they float over solder mask with no pad. Infineon's 2.5 mm creepage already counts
  them as interrupting conductors.

## 2. Electrical fit

| Item | UCC21550B (SLUSE89C) | 2EDR8259 (Rev 1.7) | Fit on native-21 |
|---|---|---|---|
| Output supply | 8 V UVLO: on 7.7–8.9 V, off 7.2–8.4 V; abs 30 V | 8 V UVLO: on ≤ 8.5 V (typ 8.0), off ≥ 6.6 V; **operating 8.5–21 V, abs 22 V** (Tables 9/11/15) | Both rails are **17.0 V VDD–VSS**. HS: RECOM 16.91 V (`f6_bias.ato:370`). LS: TPS7A4700 17.0 V (`f6_bias.ato:62`); "v15_ls" is a legacy name. Span OV monitor trips DIS at 1.2475 × 14.3 = 17.84 V. Margin to 21 V operating is 4.0 V; to 22 V abs it is 5 V (TI: 13 V). A shorted regulator (24 V raw) would exceed 22 V, but it would also exceed the MOSFET's ±20 V VGS. Bench: start-up overshoot < 21 V. |
| Input supply | VCCI 3–5.5 V, UVLO on 2.55–2.85 V | VDDI 3–17 V, UVLO on ≤ 2.95 V, off ≥ 2.55 V (Table 13) | 3.3 V rail, minimum 3.135 V (02-protection-timing) → 0.185 V margin to the 2.95 V start threshold |
| Logic inputs | VIH ≤ 2.3 V, VIL ≥ 0.8 V, pull-down 50–185 kΩ | VINH ≤ **2.36 V**, VINL ≥ 0.9 V, hysteresis ≥ 0.38 V, pull-down 150 kΩ typ (Table 18) | 3.3 V CMOS fine. ESP32 VOH min 2.64 V leaves 0.28 V (TI: 0.34 V). D-25's ≤ 10 kΩ controller pull-down still governs. DIS threshold in `02-protection-timing/scripts/detector_chain.py:71` moves 2.30 → 2.36 V. |
| Propagation | 26/33/45 ns; tDM ≤ 5 ns; PWD ≤ 5 ns | on 33/38/47, off 30/36/46 ns; part-to-part ≤ 6/8 ns; ch-ch −4…4 / −5.5…3 ns; PWD −5…5.5 ns (Table 21) | Equivalent. Leg-to-leg skew is bounded at 8 ns; TI has no part-to-part spec. |
| DIS → OUT | 27/48/80 ns (5.9) | **not tabulated** (Figure 6 only) | The protection chain budget uses 80 ns. 2EDR needs a bench number or an Infineon answer; the chain is about 1 µs, so this is not decisive. |
| Output stage | ROH 5 Ω DC + 1.47 Ω NMOS boost (7.3.4); ROL 0.55 Ω; 4 / 6 A | Ron_SRC 0.6 / 0.95 / 1.5 Ω, Ron_SNK 0.24 / 0.39 / 0.62 Ω; 5 / 9 A (Table 20) | See the Rg section below |
| CMTI | \|CMH\|, \|CML\| ≥ 125 V/ns at 1500 V | **≥ 150 V/ns static**, H and L, at 1500 V (Table 23 p.17) | 150 / 95 = **1.58 ≥ 1.5** |
| Isolation | Reinforced; VIORM 2121 Vpk; VIOWM 1500 Vrms; VIOTM 7071; VIOSM 10 kV; CPG/CLR > 8 mm; CTI > 600 (MG I) | Reinforced (IEC 60747-17 cert 40055138); UL1577 5.7 kVrms (E311313); VIORM 1767 Vpk; VIOWM 1250 Vrms; VIOTM / VIMP 8000 Vpk; VIOSM 11 kV; CPG/CLR **8 mm**; CTI > 400 (**MG II**), PD2; OVC I–IV ≤ 150 Vrms mains (Table 24) | Working voltage is ≪ 1767 Vpk, so it is OK. D5-BASIS cites the TI tables as MG I: re-cite as MG II. Package 8 mm = the 8.0 mm floor, not > 8. The board laminate (≥ IIIa) still governs. |
| Fail-safe | VCCI UVLO → outputs low (1.2–7 µs); VDD UVLO → low; active pull-down 1.6–2 V at 200 mA unpowered | VDDI < UVLO → outputs low, no data (Table 8); tSTOP,VDDI min 600 / typ 750 ns (**no max**); VDDx UVLO → low with active clamp 0.79–1.45 V at 10 mA unpowered (Table 20); CT watchdog | Same safe state (both outputs low). The RailMonitor / BIAS_GOOD DIS path is unchanged. |

### Gate resistor (the real change)

Gate charge is about 234 nC (IPW65R018CFD7). The turn-on path is driver + Rg + Rg,int 2.7 Ω.
- UCC with the deck's 5 Ω: 11.6 Ω.
- UCC with TI's boost (1.136 Ω): 7.7 Ω.
- 2EDR with 3.9 Ω: 7.6 Ω.
- 2EDR with **8.2 Ω**: **11.85 Ω**, which restores the as-built model's edge.

D2 edge study (`results/edge/`): 443 ns, S1/S2/S4/S5, both legs, 27/150 °C, both directions, ESL 1.06/10 nH, 144
cases per variant. The deck is the as-built native-21 F6 deck. It reproduces the committed rows exactly
(`results/repro/`), and the dv/dt probes do not perturb it.

| Driver model | pass (incl. 1.9 V) | max die VDS | max off-gate | fastest 20–80 % hard edge | vs as-built | 95 V/ns-scaled edge | CMTI ratio |
|---|---|---|---|---|---|---|---|
| UCC21550, ROH 5 Ω, Rg 3.9 (as built) | 144/144 | 490.2 V | 1.10 V | 76.3 V/ns | 1.00 | 95 | 1.316 |
| UCC21550 with TI boost 1.136 Ω (sensitivity) | 136/143 | 594.3 V | 1.54 V | 94.4 V/ns | 1.24 | 118 | 1.06 |
| 2EDR, Rg 3.9 Ω (BOM-only swap) | **139/144** | **595.2 V** | 1.32 V | 96.0 V/ns | 1.26 | 120 | **1.25** |
| **2EDR, Rg 8.2 Ω** | **144/144** | 501.8 V | −0.22 V | 75.8 V/ns | **0.99** | 94 | **1.59** |
| 2EDR, Rg 8.2 Ω, strong corner (0.6 / 0.24 Ω) | 144/144 | 513.7 V | −0.39 V | 76.1 V/ns | 1.00 | 95 | 1.58 |
| 2EDR, Rg 8.2 Ω, weak corner (1.5 / 0.62 Ω) | 144/144 | 487.3 V | −0.01 V | 75.0 V/ns | 0.98 | 93 | 1.61 |

Notes on the edge study:
- The 95 V/ns rule comes from the round-17 unipolar grid, and the F6 deck's absolute edges are slower. The CMTI
  column therefore scales 95 V/ns by fastest-edge(new) / fastest-edge(as-built).
- Instantaneous ddt() peaks are 0.2 ns-step ringing artefacts (kV/ns) and are not used.
- Side finding: the as-built 1.316 and its 490 V rest on the 5 Ω static ROH. TI's own description of the transient
  NMOS boost moves the UCC case to 594 V and 1.06. The 2EDR has no unmodelled boost: its Ron is the whole pull-up.

Part for R10/R12/R18/R20: **8.2 Ω 1 % 1206**.
- FH RS-06L8R20FT, LCSC C323355: 4,660 in stock, $0.0124 at 1 / $0.0083 at 1500.
- Yageo RC1206FR-078R2L, C488973: only 16 in stock.
- Dissipation is about 234 nC × 17 V × 36 kHz ≈ 0.14 W per gate in total, of which ≤ 0.06 W in Rg (1206: 0.25 W).

## 3. Dead time

Source: `scripts/dt_window.py` and `results/dt_window.json`, from Infineon Table 19 p.15.
- Datasheet points: 10 k gives 85/100/115 ns, 30 k gives 255/300/345 ns, 100 k gives 800/950/1100 ns. The 100 k
  point is characterisation only.
- Min/max apply over the full operating range.
- Method as in audit.rs `dead_time_window_ns`: interpolate the columns, then stack 0.1 % tolerance and 25 ppm/K over
  125 K. The window is the envelope of linear and ratio-of-10·R interpolation.

| R (RT0603BRD07, 0.1 %) | typ | window | fits 391–498? |
|---|---|---|---|
| 44.2 kΩ | 432 ns | 364.1–505.8 ns | no (both edges) |
| 47.5 kΩ | 463 ns | 389.7–542.5 ns | no |
| **49.9 kΩ (R9/R17 today)** | 485 ns | **408.3–569.0 ns** | no (upper) |
| UCC21550 at 49.9 kΩ (audit reference) | 443 ns | 396.6–488.0 ns | yes |

- The audit window is ±12.0 % wide and the part spread is ±15 %, so no resistor fits.
  - Lowest R that keeps the lower edge at or above 391 ns: 48.7 kΩ.
  - Highest R that keeps the upper edge at or below 498 ns: 43.2 kΩ.
- **D2 rerun over the wider band** (`results/dtband/`): 2EDR + Rg 8.2 Ω on the as-built deck; S1/S2/S4/S5; both legs;
  both directions; ESL 1.06/10 nH; dead times 340, 364, 391, 408, 443, 500, 530, 562, 600 ns at 27/100/150 °C. The
  weak and strong output corners were run at 340/364/562/600 ns, 27/150 °C.
  - **3095/3095 completed runs pass**, including the 1.9 V hot screen, the model threshold, VDS ≤ 520/585 V and
    |VGS| ≤ 30 V. S1 has ZVS in every case.
  - Max die VDS is 513.9 V (strong corner, S4, 562 ns).
  - Max off-gate is +0.03 V (weak corner, S4, 340 ns). S1/S2 off-gate stays ≤ −0.43 V.
  - The fastest 20–80 % edge in the band is 76.1 V/ns.
  - One run aborted (A, 27 °C, S4 170 V, 340 ns, ESL 10 nH, "timestep too small" at node bus, the known isolated
    signature). It passes at 0.1 ns step (−1.24 V, 436 V) and at ESL 9.5/10.5 nH (`results/dtband-rerun/`).
- **Why the audit window no longer binds:** 391–498 came from `grid-best-longdt`, which is the unipolar pre-F6 deck
  (the 1.9 V hot screen failed at 348 ns). With F6 as built, the off gate sits at about −0.9 V in S1, and
  dead time stops being the constraint anywhere in 340–600 ns. This is consistent with FINDINGS F1: "a gate-drive
  remedy (F6) that passes at 307 ns".
- **Resistor choice: keep 49.9 kΩ.** That is no BOM change on R9/R17, the window is 408–569 ns, and it is biased away
  from the dangerous short edge.
  - The longer typical (485 vs 443 ns) costs about +0.04 W per switch of diode conduction (D-15 scaling).
  - 44.2 kΩ (C861410, 4,967 stock) also passes (364–506 ns) if a centred window is preferred.

audit.rs changes for adoption (not made here):
- `BARRIER_PARTS` lines 256–257: the new MPN.
- `dead_time_window_ns`: a 2EDR formula (Table 19 interpolation, as `dt_window.py`).
- `DT_WINDOW_NS` (391, 498) → (340, 600), citing `c25-driver/results/dtband`.
- The `dead_time_window_matches_d12` test.
- A negative control for the EN-polarity sibling 2EDR8258X (EN active high, open = disabled), mirroring the
  ISO7710FDWR control.

The CMTI table needs a new DATA row (`06-controller-interface/cmti/cmti_table.py`).

## 4. Availability and price (read 2026-10-13 / 14)

| Source | 2EDR8259HXUMA1 (DSO-16) | 2EDR8259XXUMA1 (DSO-14) |
|---|---|---|
| Digi-Key | **2,406**; $2.38 / 1.763 (10) / 1.4399 (100) / 1.3207 (500); T&R 1,500+ $1.2506; 39 wk | **1,043**; same prices |
| JLC / LCSC (Extended) | **C17531538**, 43 pcs; $3.02 / 2.58 (10) / 2.02 (100) / 1.8875 (500) | **C17455725**, 97 pcs; $2.67 / 2.24 (10) / 1.69 (100) / 1.5677 (500) |
| Newark (findchips) | 2,456; $1.31–2.52 | 500; $1.31–2.52 |
| Avnet | 0 | 1,500 (T&R) $0.96–1.01 |
| Mouser | not verified (page timeouts) | not verified |

- The research note said "not on LCSC". JLC's search API returns both parts now (`raw/q_*.json`).
- Baseline U1/U2 line (STOCK-2026-10-13.csv): UCC21550BDWKR, consign, $1.409 at 5 boards / $1.03682 at 500 (DK),
  ZERO_STOCK_ALL_CHECKED_SOURCES.

| Per board (2 drivers + 4 Rg) | at 5 boards | at 500 boards |
|---|---|---|
| Drivers, DK (10 / 1000 pcs at the 500 tier) | 2 × 1.763 = 3.526 (+0.708) | 2 × 1.3207 = 2.641 (+0.568) |
| Drivers via JLC instead (X) | 2 × 2.2366 = 4.473 (+1.655) | 2 × 1.5677 = 3.135 (+1.062) |
| Rg 3.9 Ω Yageo → 8.2 Ω FH (4 pcs) | −0.059 | −0.047 |
| **Net (DK drivers)** | **+$0.65** | **+$0.52** |

Supply notes:
- 5 boards need 10 drivers; any source covers that, including JLC for X (97) and H (43).
- 500 boards need 1,000 drivers. That needs H at DK (2,406) or Newark (2,456), or X across DK + Avnet + Newark
  (3,043). JLC stock covers neither.
- Lead time is 39 weeks at DK. Infineon is the single source; no pin-compatible second manufacturer was verified.
  NCP51561BB is pin-7-different; see the research note.

## 5. Recommendation

**GO, BOM + Rg.** Change:
- U1/U2 → 2EDR8259XXUMA1 (preferred), or 2EDR8259HXUMA1 as the same-footprint second source.
- R10/R12/R18/R20 → 8.2 Ω.
- In `parts.ato`, a new component with the same footprint and pads:
  - X: INA 1, INB 2, VDDI 3/8, GNDI 4, DIS 5, STP_DTC 6, NC 7, GNDB 9, OUTB 10, VDDB 11, GNDA→pad 14, OUTA→pad 15,
    VDDA→pad 16.
- audit.rs data as in section 3.

There are no net, footprint or copper changes. R9/R17 stay 49.9 kΩ.

Expected scorecard:
- `cmti_gate_ratio_min` **1.316 → 1.58**: F6 closes on the datasheet minimum.
- `zero_stock_lines` **9 → 8**.
- `parts_usd_at_5` **+$0.65**, `parts_usd_at_500` **+$0.52**.
- `single_source_lines` unchanged (16).
- `jlc_extended_lines` unchanged if bought at DK and consigned. If JLC-sourced: +1 extended, −1 hand/consign.
- Performance in D2:
  - S4 max die VDS 490 → 502 V. Still passes 520 V; leg A/B worst at 443 ns.
  - S4 off-gate +1.10 → −0.22 V.
  - S2 off-gate +0.07 → −0.54 V.

Do **not** adopt it as a BOM-only swap with 3.9 Ω: that case fails 5/96 hard cases (595 V) and lowers the CMTI ratio
to 1.25.

Bench verification (adds to D-8 / BRINGUP):
1. S4/S5 dv/dt on SW_A and SW_B with the 8.2 Ω part. The CMTI claim needs ≤ 100 V/ns for 1.5×. Probe INA/INB and
   OUTA/OUTB for glitches during hard edges, as the cmti README item 4.
2. Dead time at the gates, both legs and both edges, cold and hot. Expect 408–569 ns. Confirm the controller's
   200 ns gap leaves the pin in control.
3. DIS → OUT delay (not in the datasheet) inside the PERMIT/OCP trip chain.
4. Fault injection:
   - Lift the U22/U23 output: outputs must stay disabled through R73/R76.
   - Remove R73 on a sacrificial board to show the dependency.
5. V3V3 brown-out to the 2.55–2.95 V UVLO, and loss of VDDA/VDDB: outputs low, clamp level, recovery time.
6. 17 V rail start-up overshoot < 21 V, both HS RECOM and LS TPS7A4700.
7. Driver and Rg temperature at maximum frequency.
8. Ask Infineon for a channel-to-channel working-voltage rating, and the DIS response time.

## Limits

- The driver is the deck's output-resistance approximation, not an Infineon model: no propagation delay, no current
  limit, no UVLO. DT in the deck is the output-command separation.
- S3 light load was not rerun. That deck set has no S3, so ZVS at 2–10 A is not claimed.
- The 100 kΩ datasheet row used in the interpolation is characterisation-only.
- The edge comparison is relative to the as-built model, not a measurement.
- Mouser stock and the Infineon channel-to-channel voltage rating are unverified.
