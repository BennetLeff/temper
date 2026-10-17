# native-21 BOM and DFM simplification proposal

Status: **proposal only.** Nothing in the repo was changed. The designer implements the approved items.

Baseline:
- unit `zapote/power-stage-120v` at the `ps-integrate` worktree;
- `fab/bom-jlcpcb.csv` (95 BOM lines);
- `owner-items/order/bom-stock-2026-10.csv` (66 JLC-placed Extended types ≈ $198 in fees per order).

Part data was read live from JLC's public part endpoints on 2026-10-09. Raw JSON is cached in `raw/` and the helper is `jlc.py`. Datasheets are in `ds/`.

## Totals

| Set | Items | Unique BOM lines | JLC Extended types | JLC fee per order | No-stock lines resolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| **safe** | 25 | ±0 (−1 merge, −1 R34 line, +2 R34/R35 pair) | **−21 (66 → 45)** | **−$63** | **3** (R34; R77/R95/R110; R87/R105/R120) |
| needs-check | 4 | ±0 | −2 | −$6 | 2 more (U1/U2, U35) if accepted |

- Every item in the safe set keeps its footprint, pads and nets, so there are no copper changes.
- The part cost also falls slightly. Basic parts are cheaper, but that is not counted here.
- `python3 totals.py` reproduces these totals. It re-checks each new C-number's Basic/Extended class and stock and reported no problems.

## Ranked table

**Abbreviations.** Ext = Extended type; ±L = change in unique lines. "Spec" means the attributes on JLC's part listing (value, tolerance, voltage, dielectric or TCR, package). **Every item needs `audit.rs` IDENTITY edits** (section "Exact source edits").

### A. Extended → Basic, identical spec (safe)

| # | Change | Parts | Saving | Evidence | Risk |
| --- | --- | --- | --- | --- | --- |
| B1 | KEMET C0603C104K5RACTU → **Yageo CC0603KRX7R9BB104, C14663** | 37 × 100 nF 0603 | −1 Ext, $3. **Also fixes a stock risk:** LCSC has 0 and JLC 3,890, against 74 needed for 2 boards (185 for 5) | Both are 100 nF, ±10 %, 50 V, X7R, 0603. The same Yageo family is already Basic on the board (C49678, 0805) | safe |
| B2 | KEMET C0603C101J5GACTU → **Samsung CL10C101JB8NNNC, C14858** | C30, C72, C73 | −1 Ext | Both are 100 pF, ±5 %, 50 V, C0G, 0603 | safe |
| B3 | Murata GRM21BR71H105KA12L → **Samsung CL21B105KBFNNNE, C28323** | C145–C150 | −1 Ext | Both are 1 µF, ±10 %, 50 V, X7R, 0805. AMC1311 SBAS786C §10 asks only for "low-ESR 1 µF" | safe |
| B4 | Murata GRM31CR71H475KA12L → **FH 1206B475K500NT, C29823** | C130 (SN6507 soft-start) | −1 Ext | Both are 4.7 µF, ±10 %, 50 V, X7R, 1206. SN6507 allows C_SS from 0.05 to 10 µF (SLLSFM0A rec. op.) | safe |
| B5 | Murata GRM155R71E104KE14D → **Samsung CL05B104KB54PNC, C307331** | C110–C125 (F6 reservoir HF) | −1 Ext | Same 0402 X7R ±10 % 100 nF, rated **50 V instead of 25 V** (a superset). The cap sees only about 2 V DC. ECO.md's "≥ 320 nF effective" acceptance stays; obtain the Samsung DC-bias curve with the others. **The 0402 package stays:** it is the ESL-driven HF bank | safe |
| B6 | Yageo RC0603FR-0710KL → **Uniroyal 0603WAF1002T5E, C25804** | 13 × 10 k 1 % | −1 Ext | Both 10 kΩ, 1 %, ±100 ppm, 75 V, 0.1 W. The Yageo figures are from RC_L V.12 Table 2 and the Uniroyal ones from its datasheet V.3 §7 (`ds/`) | safe |
| B7 | RC0603FR-07100RL → **0603WAF1000T5E, C22775** | R6, R14 | −1 Ext | Same as B6 | safe |
| B8 | RC0603FR-07100KL → **0603WAF1003T5E, C25803** | R7, R15 | −1 Ext | Same as B6 | safe |
| B9 | RC0603FR-07330RL → **0603WAF3300T5E, C23138** | R8, R16 | −1 Ext | Same as B6 | safe |
| B10 | RC0603FR-071KL → **0603WAF1001T5E, C21190** | R47, R89, R107, R122 | −1 Ext | Same as B6 | safe |
| B11 | RC0603FR-075K6L → **0603WAF5601T5E, C23189** | R31 (REF25 bias) | −1 Ext | Same 1 %, 100 ppm. The audit's cathode-current corner uses only R and 1 % (REFERENCE-BIAS.md), so the result is unchanged: 121.4 µA | safe |
| B12 | RC0603FR-0733KL → **0603WAF3302T5E, C4216** | R125 | −1 Ext | Same as B6 | safe |
| B13 | RC0603JR-070RL → **0603WAF0000T5E, C21189** | R38 (functional earth) | −1 Ext | Both jumpers are under 50 mΩ, **rated 1 A and 2 A maximum** (Yageo RC_L V.12 Table 2; Uniroyal V.3 §7) | safe |
| B14 | RC1206FR-071KL → **1206W4F1001T5E, C4410** | R42 (CT input) | −1 Ext | Both are 1206 parts: 1 %, 100 ppm, 200 V, ¼ W | safe |
| B15 | RC1206FR-071RL → **1206W4F100KT5E, C17928** | R53, R54, R57, R58 (F6 1 Ω) | −1 Ext | Both 1 Ω, 1 %, ±200 ppm (Yageo row 1–10 Ω), ¼ W, 200 V | safe |
| B16 | Diodes 1N4148W-7-F → **Semtech 1N4148W, C81598** | D14–D16 | −1 Ext | Both 75 V, 150 mA, 4 ns, SOD-123. The circuit uses it as a series diode carrying µA to mA | safe |
| B17 | Diodes MMBT3904-7-F → **CJ MMBT3904, C20526** | Q7–Q9 | −1 Ext | Both 40 V, 200 mA, hFE 100–300, SOT-23 with the same B/E/C pinout. Used as a 10 k-biased switch | safe |

### B. Precision or value relaxed onto Basic, with the function proven unchanged (safe)

| # | Change | Parts | Saving | Validation | Risk |
| --- | --- | --- | --- | --- | --- |
| V1 | RT0603BRD074K99L (0.1 %) → **0603WAF4991T5E, C23046 (1 %, same value)** | R71, R72, R74, R75 (reservoir bleed), R94 (SN6507 SR) | −1 Ext | The bleed sets the shunt idle current (15 V / 4.99 k = 3.0 mA, `bias_sizing.py`), and ±1 % on that is irrelevant. For RSR, TI's allowed range is 4.8–21 kΩ, and 4.99 k −1 % −1.25 % (TCR) = 4.88 k stays inside it | safe |
| V2 | RT0603BRD0718K2L → **18 k 1 %, C25810** | R92 (SN6507 RCLK) | −1 Ext | TI's Table 8-1 itself says "Recommended **1 %** RCLK values", and f is roughly k/R (21 k gives 523 kHz). The change moves the clock by +1.1 %, from about 600 to about 607 kHz, inside ECO.md's 500–700 kHz acceptance. Higher f only lowers the transformer V·t | safe |
| V3 | RT0603BRD0730K1L → **30 k 1 %, C22984** | R93 (SN6507 RILIM) | −1 Ext. **Also fixes a stock risk:** only 1,183 at JLC | From the SLLSFM0A table: 18.2 k gives 1.30 A and 30.1 k gives 0.79 A, so ILIM ≈ 23.7 A·kΩ / R. 30 k ±1 % then gives 0.784–0.800 A typical, against TI's own 0.56–1.02 A spread at 30.1 k. The recommended range is 18–261 k | safe |
| V4 | RC1206FR-07120KL → **Uniroyal 1206W4F1003T5E, C17900 (100 k)** | R1, R2 (X-cap bleed) | −1 Ext | `calc_discharge.py`. **This fixes a latent miss:** with 120 k, X caps at +20 % take 1.025 s to fall from 198 V to 34 V (target ≤ 1 s, out-D22). With 100 k it is 0.854 s. Cost: +16 mW at 140 V; per resistor 49 mW of 250 mW and 99 V peak of 200 V | safe |
| M1 | Merge GRM32ER71H106KA12L **into UMK325AB7106KM-T (C386167)** | C9, C16, C24, C26, C132, C136, C140 | **−1 line**, −1 Ext | JLC lists both as 10 µF, **±10 %**, 50 V, X7R, 1210 (Taiyo Yuden "K" = ±10 %). The merge goes this way so that the 20 characterised F6 reservoir parts stay untouched. Stock: 5,317 against 135 needed for 5 boards | safe |

### C. No-stock lines resolved with stocked parts (safe by calculation)

| # | Change | Parts | Saving | Validation | Risk |
| --- | --- | --- | --- | --- | --- |
| S1 | R34/R35, 10.6 k / 10.0 k → **12.4 k (Yageo RT0603BRD0712K4L, C861102, 14,709 in stock) / 11.7 k (Vishay TNPW060311K7BEEA, C4553285, 2,957 in stock)**. Both are 0.1 %, 25 ppm, 0603 | R34, R35 | Resolves the blocker (10.6 k has 0 stock at JLC across 12+ makers). **+1 line, +1 Ext** | `calc_protection_bands.py` reruns the committed task-02 round-3 corner model unchanged. It reproduces the baseline at 49.73–97.98 A. The new pair gives **49.53–97.77 A**: 1.2137 V against 1.2136 V, the 44 A minimum is met, and the band stays inside D-31's survival range. The LM4040 minimum current rises from 121.4 to 139.2 µA, so there is less REF25 load. Thevenin resistance goes from 5.1 to 6.0 kΩ, keeping the C31 filter τ at about 6 µs. Alternative: 19.3 k / 18.2 k gives 50.18–98.56 A with ±0 lines, but it keeps R92's 18.2 k at 0.1 % (so V2 is not possible) and has a 9.4 kΩ Thevenin | safe (calc). **Re-run** `out-D31/retune.py` and the Kelvin-band tool so that 47.52–97.98 A is regenerated |
| S2 | R77/R95/R110, 6.12 k → **6.2 k, Yageo RT0603BRD076K2L, C136960 (91,153 in stock)**, same 0.1 %/25 ppm series | 3 | Resolves the blocker (6.12 k has 0 stock everywhere) | `calc_neg_rail.py` uses TLVH431BQ full-range 1.221–1.265 V and TL431AI 2.470–2.520 V plus 34 mV over temperature (`ds/`). The −2 V nominal moves +9.9 mV (1.999 → 2.009 V). The worst-case corner margins become: UV 0.099 → 0.109 V, **OV 0.081 → 0.071 V**, and the −1.6 V F6 bound 0.359 → 0.368 V. Both monitor edges still have margin. The F6 −1.6 V qualification (DECISIONS 2026-10-06) does not depend on the nominal | safe (calc). Update ECO.md and `bias_sizing.py` (`Rtop_ohm`) |
| S3 | R87/R105/R120, RT0603BRD07133KL → **Viking ARG03BTC1333, C1509631 (2,365 in stock)** | 3 | Resolves the blocker. This swap was already named in ORDER-PACKAGE but not yet applied to the source or audit | Both are 133 k, 0.1 %, 25 ppm, 75 V, 0.1 W, 0603. The JLC listing matches on every attribute | safe |

### D. Needs a check by the owner or designer (not in the safe totals)

| # | Change | Saving | What has to be checked |
| --- | --- | --- | --- |
| N1 | R3/R4 bus bleed 220 k → 100 k Basic (C17900) | −1 Ext | `calc_discharge.py`: bus discharge from 198 V to 60 V speeds up from 2.47 to 1.25 s. Each resistor then dissipates 98 mW of 250 mW at 198 V. They sit by D3/C5, so check the local ambient against Uniroyal's derating above 70 °C. (Merging onto 470 k instead would also save a line, but slows discharge to 4.35 s; **not recommended** because ORACLE notes the bleed already "takes seconds".) |
| N2 | R40/R41 CT bias 1 k 0.1 % → 1 k 1 % Basic (C21190) | −1 Ext | The CT trip band widens from **50.56–60.01 A to 49.18–61.61 A** (`calc_protection_bands.py`). The owner decides whether that is acceptable for the ~55 A trip; T1 is rated 88 A |
| N3 | U1/U2 UCC21550BDWKR (no stock) → **UCC21550BQDWKRQ1, C42216738** | Resolves no-stock | Only **10 in stock** at JLC, against 4 needed for 2 boards. JLC lists the same DWK-14, 9.2–25 V UVLO, 4/6 A. Still confirm: the pin map in the -Q1 datasheet; reinforced certificates (VDE/UL) covering the Q1 part number, for D5; and its DT-pin curve, since the audit's dead-time window uses the catalog SLUSE89C figures. Unverified |
| N4 | U35 SN6507DGQR → SN6507DGQRQ1, C7528027 | Resolves no-stock | From ORDER-PACKAGE: confirm the Q1 pinout. 64 in stock |

### E. Candidates that need bench evidence or a re-spin (no saving claimed)

- **R1/R2 removal.** The line-ZC string (4 × 16.5 k = 66 k plus the opto LED across L_FILT/N_FILT) already discharges both X caps through L1, with τ ≈ 0.13 s. However, the discharge argument would then rest on a signal circuit and its opto; that is a certification call. *Candidate; needs certifier.*
- **J7–J10 bring-up studs.** These are 4 REDCUBE studs with no stock, plus 2 jumpers. They are required by the native-20/21 bench rules (floating DC bring-up at J8/J10). For production only, solid copper links would delete 4 THR parts. *Candidate; production re-spin.*
- **C24 (V15_LS 10 µF).** It parallels the TPS7A47 outputs C99/C100 (2 × 10 µF) on the same nets. It is a legacy from PS2's direct output. Removing it saves a placement, not a line. *Candidate; needs a layout/LDO-stability check.*
- **U22/U23 SN74LVC1G32 (2-input OR) → SN74LVC1G332 (the 3-input OR already on the board, C input tied low).** This saves 1 line and 1 Ext, but changes SOT-23-5 to SOT-23-6, which is a copper change. *Next re-spin.*
- **Snubbers C12/C13/C19/C20 and D3 TVS.** Not proposed for removal. They are part of the decision matrices and the DC-LINK-CLAMP basis, and no simulation bounds their absence.

### F. No-stock lines with no validated equivalent (left as consigned or distributor buys)

- **ISO7710DWR (U9, U32–U34).**
  - Every default-high SOIC-16W variant at JLC (ISO7710DW, ISO7710QDWQ1) has 0 stock.
  - The SOIC-8 ISO7710DR (1,150 in stock) fails the 8 mm D5 creepage.
  - ISO7710F* parts default low, which the audit's default-low mutation test rejects.
  - Other makers' parts are not pin-compatible.
- **Kept on their recorded rationale:**
  - **CMC L1, X caps C1/C2, film C5/C6 and C21–C23:** D-22/EMI, FEM and tank analyses. R463N410000N2M (C3300362) also shows 0 stock and its suffix is unverified.
  - **D3:** the E3 RoHS variant also shows 0 stock, and DC-LINK-CLAMP.md forbids silent suffix changes.
  - **J6, REDCUBE, T2/T3.**
- **T1:** Coilcraft direct, per the procurement summary. CST3015-200ED is in stock but is 1:200, which is not equivalent.
- **6SVPC220M:** the low stock (13) covers 2 boards. 6SVPC220MV (875 in stock) lists 15 mΩ against 27 mΩ ESR. The 0.68 Ω damping makes that difference negligible, but it is *unverified against Panasonic*.

## DFM notes

- **The only 0402 parts (C110–C125) stay:** ECO.md's ESL budget needs them. Moving them to the Basic 0402 (B5) removes their Extended fee.
- **The 0.1 % population falls from 23 to 20 lines.** V1–V3 drop three 0.1 % lines. The remaining 0.1 % parts are dividers set by a recorded requirement: OCP, OVP, CT, monitors, dead time and bus sense.
- **THT count is unchanged; nothing was validated for an SMT swap.**
  - All THT parts are power, safety or connector parts with recorded selections.
  - The REDCUBE THR studs are best placed paste-in-hole at JLC once stocked (FAB-NOTE), rather than hand-soldered into 2 oz pours.
- **Panel and edges:** the L outline (290 × 190 bounding box with a tongue) has a notch on one long edge. Ask JLC whether they will add process rails for the SMT conveyor, or add 5 mm breakaway rails on the straight edges. *Advice only, not validated against JLC's current rules.*

## Exact source edits (safe set)

**`elec/src/parts.ato`.** Change `mpn` and `manufacturer`, and add `lcsc_id` if the build uses it. Each component class changes every instance it covers.

| Component | New MPN | Manufacturer |
| --- | --- | --- |
| `C100n0603` | `CC0603KRX7R9BB104` | YAGEO |
| `C100pC0G0603` | `CL10C101JB8NNNC` | Samsung Electro-Mechanics |
| `C1u0805` | `CL21B105KBFNNNE` | Samsung |
| `C10u1210` | `UMK325AB7106KM-T` | Taiyo Yuden |
| `R10k0603` | `0603WAF1002T5E` | UNI-ROYAL |
| `R100R0603` | `0603WAF1000T5E` | UNI-ROYAL |
| `R100k0603` | `0603WAF1003T5E` | UNI-ROYAL |
| `R330R0603` | `0603WAF3300T5E` | UNI-ROYAL |
| `R1k0603` | `0603WAF1001T5E` | UNI-ROYAL |
| `R5k6Bias` | `0603WAF5601T5E` | UNI-ROYAL |
| `FunctionalEarthLink` | `0603WAF0000T5E` | UNI-ROYAL |
| `R1k1206` | `1206W4F1001T5E` | UNI-ROYAL |
| `R120k1206` | `1206W4F1003T5E` | UNI-ROYAL |
| `R10k6Thin` | `RT0603BRD0712K4L` | Yageo |

Further `parts.ato` edits:
- `R120k1206`: also update its docstring to "tau 0.40 s".
- `R10k6Thin`: also rename it `R12k4Thin`.
- **Add** `R11k7Thin` = `TNPW060311K7BEEA` (Vishay), R_0603.

**`elec/src/f6_parts.ato`.**

| Component | New MPN | Manufacturer |
| --- | --- | --- |
| `Bias100n` | `CL05B104KB54PNC` | Samsung |
| `Gate1R` | `1206W4F100KT5E` | UNI-ROYAL |
| `BiasSilicon` | `1N4148W` | Semtech, C81598 |
| `BiasNpn` | `MMBT3904` | CJ, C20526 |
| `Bias4k99` | `0603WAF4991T5E` | UNI-ROYAL |
| `Bias18k2` | `0603WAF1802T5E` | UNI-ROYAL |
| `Bias30k1` | `0603WAF3002T5E` | UNI-ROYAL |
| `Bias4u7` | `1206B475K500NT` | FH |
| `Bias6k12` | `RT0603BRD076K2L` | Yageo |
| `Bias133k` | `ARG03BTC1333` | Viking Tech |
| `Line33k` | `0603WAF3302T5E` | UNI-ROYAL |

- The CJ datasheet (`ds/C20526.pdf`) gives the SOT-23 pin order as 1 base, 2 emitter, 3 collector, which matches `BiasNpn`.
- `Bias18k2` becomes 18 k: rename it `Bias18k`.
- `Bias30k1` becomes 30 k: rename it `Bias30k`.

**`elec/src/power_stage_120v.ato`.**
- `rb1a/rb1b.value = 100kohm`.
- `r_th_top.value = 12.4kohm`.
- `r_th_bot` becomes `new R11k7Thin` with `.value = 11.7kohm`.
- Update the OCP comment: "2.5 × 11.7/(12.4+11.7) = 1.2137 V".
- `bias_rclk.value = 18kohm`; `bias_rlim.value = 30kohm`.

**`elec/src/f6_bias.ato`.** `rtop.value = 6.2kohm`.

**`audit.rs`.**
- In `IDENTITY` and `BARRIER_PARTS`, replace each old MPN string with the new one:
  - `C0603C104K5RACTU`, `C0603C101J5GACTU`;
  - `RC0603FR-0710KL`, `RC0603FR-07100RL`, `RC0603FR-07330RL`, `RC0603FR-071KL`, `RC0603FR-075K6L`;
  - `RC0603JR-070RL` (also in the mutation tests near lines 1366, 1569 and 1593: keep a plausible 0 Ω MPN there);
  - `RC1206FR-071KL`, `RC1206FR-071RL`;
  - `1N4148W-7-F`, `MMBT3904-7-F`, `GRM155R71E104KE14D`;
  - `RT0603BRD074K99L`, `RT0603BRD0718K2L`, `RT0603BRD0730K1L`, `RT0603BRD076K12L`, `RT0603BRD07133KL`;
  - `r_th_top` → `RT0603BRD0712K4L`, `r_th_bot` → `TNPW060311K7BEEA`.
- In the `bias_ohm` match, add the arm `Some("0603WAF5601T5E") => Some(5_600.0)`.
- In `min_reference_cathode_current_ua`, change `ocp_threshold_load` from `20_500.0` to `24_100.0`. The existing constant is already stale: it is 10.5 k + 10 k, but the fitted part is 10.6 k.
- Update the comments on `r_th_*`.
- Run `audit` (74 tests), `verify_source.py`, and the frozen export.
- Regenerate `bom-jlcpcb.csv` (`scripts/apply_lcsc.py`) with the C-numbers above.

**Other files to refresh with the new values:**
- `validation-results/02-protection-timing/round3/thresholds.py` (`PARTS` and `expected_mpn` for R34/R35);
- `out-D31/retune.py`, and the Kelvin-band tool.

**Board:** a value/MPN change only. Poses, footprints and copper are identical, so the DECISIONS native-18 pattern applies (field-only board diff).

## Scripts and data in this folder

| Path | Contents |
| --- | --- |
| `jlc.py` | Live JLC search and detail queries (read-only public endpoints), cached in `raw/` |
| `dsfetch.py` | Fetches LCSC-hosted datasheets |
| `totals.py` | Summary totals, plus a live re-check of each new part's class and stock |
| `calc_protection_bands.py` | OCP and CT bands from the committed round-3 model; REF25 current. Output: `out/protection_bands.json` |
| `calc_neg_rail.py` | −2 V rail against the monitor window over component corners. Output: `out/neg_rail.json` |
| `calc_discharge.py` | X-cap and bus bleed times and dissipation. Output: `out/discharge.json` |
| `ds/` | Uniroyal V.3, Yageo RC_L V.12, SN6507 SLLSFM0A, TLVH431 SLVS555N, TL431 SLVS543S, and the LCSC datasheets for C81598, C20526, C307331, C29823, C17928 and C95177 |

**Unverified items, also flagged inline:**
- N3's -Q1 pinout and certificate;
- N4's pinout;
- the 6SVPC220MV ESR equivalence;
- the JLC process-rail advice.
