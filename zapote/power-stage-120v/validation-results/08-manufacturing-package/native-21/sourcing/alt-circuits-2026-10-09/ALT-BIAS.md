# Native-21 block 2: alternative circuits for the high-side F6 bias (T2/T3 + SN6507)

Scope: `zapote/power-stage-120v`, branch `codex/power-stage-integration`, stage 13b, 2026-10-09.
The scope changed during the task: block 2 only, in more depth. Notes on blocks 1 and 3 are in Appendix A.

**What I did and did not do:**
- I read the repo and changed nothing in it. Everything is in this folder.
- I made no purchases, carts, quotes, logins or forms.
- Datasheets were downloaded to `dl-bias/` in this scratch folder, not to the repo.
- The TI TLVH431 macro (SLVM672) and its per-corner derivatives are read **in place** from the repo's git-ignored `out-D33/.models/`. They are never copied.
- ngspice ran with at most 8 parallel workers.

## 0. Answer first

| Rank | Option | Circuit | Key evidence | Re-validation | Parts Δ (board) | Stock (lot needs 20) |
|---|---|---|---|---|---|---|
| **1** | **A1: integrated isolated bias module, one per high side, single 17 V output, feeding the *unchanged* TLVH431 split, reservoir and monitor** | RECOM **R24C2T25/R-R** (reinforced, 36-SSOP). Pin-compatible second source: TI **UCC14241-Q1**. It replaces T2/T3, the SN6507 block, 4 rectifiers, 2 filter chokes and **both high-side TPS7A47s** | The repo's rail campaign was re-run with a module source model in place of the 17 V/1 Ω Thevenin source: **128/128 pass**, worst −1.8892 V against the committed −1.8883 V. The baseline reproduces the committed `periodic.json` to the printed digit. Barrier is 3.5 pF **max** (the basis has 3 pF typ and no maximum); §2 shows ≤ ≈ 4 pF max is what the F6 rail budget can absorb. CMTI is 150 kV/µs ≥ 95 V/ns. Reinforced 1000 Vrms / 1.4 kVDC working, so it meets *both* readings of the insulation conflict | No FEM expected (outside the A21/B21 crops plus 10 mm; confirm with `leg_region_diff.py`). F6 switching: none (rail ≤ −1.6 V bound unchanged). Rail: re-run with module source (done here, periodic; edge-waveform replay still to do). New: module thermal (1.0–1.7 W each), startup inside the 16 ms soft-start time-out (sim §3.4), bench-check the module's EMI. Audit: `audit_f6.rs` transformer, rectifier, SN6507 and HS-LDO rows | **≈ −10** | R24C2T25/R-R: **1,205** at Digi-Key, $8.40 |
| **2** | **A3: unregulated 2 W gate-drive SIP module, +20 V output, into the *unchanged* TPS7A47 + TLVH431 split** | Murata **MGJ2D242005SC** (+20 V rail only) | Downstream circuit identical to what was qualified. Efficiency 82 % typ, which keeps the PS2 budget at the basis value (9.3 W vs 9.6 W at 80 kHz). CMTI > 200 kV/µs characterised. Coupling 4 pF typ (no max): it costs up to ≈ 0.1 V of the HS rail margin at the conservative CM edge (§2) | No FEM expected. No F6 or rail rerun (the source into the TPS7A47 changes from 17.3–18.9 V to about 18.4–21.6 V). TPS7A47 headroom/dissipation check. THT footprint and inner-layer clearances. CM sweep at 4–10 pF | **≈ −15** | **606** at Digi-Key, $9.49 |
| 3 | A2: as A1, but the module's own COM regulator makes the split (+15.5/−2.5 V) and the HS TLVH431 split is deleted | R24C2T25/R-R or UCC14240/UCC14241 | −2.5 V is the module's minimum COM–VEE. That is deeper than −2 V and inside D-6's −2…−4 V F6 family | **Full F6 rail re-qualification**: the module's hysteretic COM regulator and RLIM replace the TLVH431 macro and there is no vendor transient model. Monitor windows re-scaled. Reservoir re-sized to TI's COUT2/COUT3 ratio rule. Not for this lot | ≈ −20 | as A1 |
| 4 | B1: keep SN6507, stocked WE **750315240** (1:1.1, reinforced, UL) with SN6507 duty-cycle control and 200 V rectifiers | 750315240 + RDC + MURS120T3G | §5 sim | Footprint ECO; Cww 18 pF **max** puts ≈ 5× the basis CM charge into the LS rail (§2); F6/LS rail re-run with the CM adder | ≈ +2 | 90 (52 wk) |
| 5 | C: recorded fallback, bootstrap high side + regulated split | UF4007-class diode per HS | **Fails as recorded.** The native-21 split is a *sink-only* TLVH431, and the bootstrap charge returns through N→SW, which collapses the negative rail (§6 sim). A bidirectional split is needed. Also, BIAS_BAD holds DIS during the idle, so the firmware LS pre-charge **cannot happen** unless the monitor/DIS logic changes | New split circuit plus full rail re-qualification, DIS/monitor logic change, F6 S5 burst-start re-run | ≈ −20 (+ new split) | stocked |

**Recommended path:**
- **Prototype A1 first**, on two to four boards of the lot.
- **Fit A3 on the other boards**, or hold it as the immediate fallback.

Both fit inside the existing T2/T3 courtyards (A3 extends about 7 mm along x into space freed by L2/L3 and the rectifiers). Both leave the qualified F6 split, reservoir and monitor untouched.

**A1 is better than the original even if 750320775 arrives:**
- It has a *bounded* barrier capacitance (3.5 pF max against 3 pF typ with no maximum).
- It is reinforced, which removes the bias_sizing/DECISIONS insulation conflict for good.
- Its span regulation is ±1.5 % (module) against ±2.5 % (TPS7A47).
- It removes about 10 parts, two TPS7A47 EP thermal pads and two 600 kHz drive nets of 50 and 94 mm (U35 → T2/T3).
- The price is about +2.5 W of HOT-side heat at the 80 kHz allocation, and the module's thermal and EMI must be checked on the bench.

## 1. Recorded requirements (with source)

| # | Requirement | Recorded value | Source |
|---|---|---|---|
| R1 | Topology | Two high-side domains (HS-A on SW_A, HS-B on SW_B). Each has a 17 V span P–N, and a TLVH431 shunt holds SW 2 V above N (+15/−2 V). The low side is fed directly from PS2 IRM-20-24 (unchanged here) | ECO.md "Supply and gate circuit"; `f6_bias.ato` HighBias/RegulatedSplit; `power_stage_120v.ato:863-950` |
| R2 | F6 negative bound | The negative rail stays more negative than **−1.6 V** through every partner-edge window. The switching side is shown at a fixed −1.6 V (504/504) | DECISIONS 2026-10-06 "F6 rail qualification by bounding"; DECISIONS 2026-10-06 revised item (3) |
| R3 | Rail evidence to preserve | 7,972 rail cases pass; worst −1.678614 V (78.6 mV margin). Periodic 740 nC campaign worst −1.888341 V | out-D33/README.md; `qualification-summary.json`; `rail-qualified/periodic.json` |
| R4 | Shunt / reservoir | TLVH431-class shunt (not a Zener), ≥ 2.2 µF effective + 100 nF at VSS, as built: 2×10 µF + 2×1 µF + 4×100 nF + 220 µF via 0.68 Ω per VSS. Shunt current < 70 mA | DECISIONS 2026-10-06 rev. (3); ECO.md; `f6_bias.ato` BiasReservoir |
| R5 | Load per HS channel | 740 nC edge allowance. 47.3 / 52.5 / **82.1 mA** at 33 / 40 / 80 kHz (includes 14 mA monitor allowance) | `native-21/bias_sizing.py`, `bias-sizing.json` |
| R6 | Span tolerance / monitor windows | TPS7A47 ±2.5 % overall. Monitor windows: span 16.218–17.839 V, negative −2.198…−1.799 V (nominal) | ECO.md (TPS7A47 note, "Mandatory rail monitor") |
| R7 | Driver limits | UCC21550B VDDx–VSSx 9.2–25 V recommended, 30 V absolute; UVLO rising 7.7–8.9 V; driver barrier ~1.2 pF | TI UCC21550 datasheet (ti.com/lit/ds/symlink/ucc21550.pdf): Abs. Max., Recommended Operating Conditions, electrical table (`dl-bias/ucc21550.txt` lines 191, 228–236, 325, 450–454) |
| R8 | Insulation | **Functional HOT↔HOT** (SW_x to LEG_RET/N_LS); no path to PS1/PE (resolution below) | DECISIONS 2026-10-06 revised item (2); ECO.md "The high-side transformers are HOT↔HOT functional barriers" |
| R9 | Barrier stress | SW_x swings 0 → ≤ 286 V (static OVP corner) at 33–80 kHz, with ≤ 520 V transient target. That is ≈ 0.2 kV rms-equivalent and **0.52 kVpk** at > 30 kHz | DC-LINK-CLAMP.md §1 and table |
| R10 | dv/dt | 10 V/ns ZVS; up to 95 V/ns hard edges (S4/S5) | ECO.md rail-monitor paragraph |
| R11 | Coupling | Basis Cww 3 pF **typ, not a max**; "sweep separately" | ECO.md; bias_sizing.py `Cww_status` |
| R12 | Startup / burst | Bias up before PWM and held through 20 s burst idles. The rail monitor gates DIS (UVLO does not see a collapsed negative rail). Measured startup wait is set at bring-up | DECISIONS 2026-10-05 F6 adoption item 3; 2026-10-06 rev. (4); ECO.md |
| R13 | Supply / TCO | Bias power from IRM-20-24 on TCO_L only (21.6 W; 9.59 W allocation at 80 kHz). Never from PS1 | DECISIONS 2026-10-06 revised; `audit_f6.rs` test `bias_source_cannot_move_to_ps1` |
| R14 | Space | T2 at (56.5, 66.2), courtyard 12.0 × 14.2 mm (primary pads at y 60.67, secondary at y 71.73). T3 at (10.2, 61.2). U35 SN6507 at (104.2, 87.2), so BIAS_SW1/2 runs ≈ 50 mm to T2 and ≈ 94 mm to T3. A21 FEM crop (37.9, 4.2)–(89.6, 46.1), B21 (2.4, 4.2)–(42.6, 46.1) | stage-13b board (`sim/board_fp.tsv`); `round17/scripts/mesh25d_hybrid.py:71-72` |
| R15 | Lot | 20 pieces per line (5 boards × (2 + 2 spares)) | ALTERNATES-2026-10-09.md |

**Insulation conflict, resolved from DECISIONS.**
- `bias_sizing.py` records `reinforced_working_Vrms: 500`. That is the 750320775's catalogue rating, carried from the BOM-review architecture of 2026-10-06 item (1), in which the transformers were SELV↔HOT and had to meet the D5 reinforced basis.
- The **revised** 2026-10-06 entry explicitly *supersedes item (1)*. It puts the driver on the HOT-side 24 V and calls the two high-side barriers "**functional isolation only (`sw_a`/`sw_b` to `leg_ret`)**". ECO.md repeats this.
- **Functional governs.** The real need is R9: 0.52 kVpk repetitive at > 30 kHz, plus 150 V/ns-class dv/dt.
- Every option below states its rating against R9. A1 (R24C2T25/R, UCC14241) also meets the stale reinforced-500 Vrms reading, so the conflict stops mattering.

## 2. Common-mode current through the bias barrier (applies to every option)

The barrier capacitance pumps C·dv/dt from SW_x into the N_LS/V24_RAW domain at the high side's own rising edge. That edge is also the **LS partner edge**, so the current flows *into* N_LS (toward 0 V, the bad direction) exactly inside the window R2 is measured over.

**2a. Network scenario** (`sim/cm_inject.py`, `sim/cm/results.json`). This is not an extraction.
- **Edge:** SW 0 → 520 V at 10 or 95 V/ns, then a damped ring to 280 V whose slope is bounded by the same dv/dt.
- **Coupling path:** Cio to the primary pins (10 µF + 100 nF), then 20 or 80 nH of routing to the LS split and the native-21 LS reservoir (with ESL).

| Barrier | Cio (pF) | 10 V/ns: peak / charge / ΔV at LS VSS | 95 V/ns: peak / charge / ΔV at LS VSS |
|---|---:|---|---|
| UCC21550's own barrier (reference, exists today) | 1.2 | 14 mA / 0.29 nC / 10 mV | 134 mA / 0.34 nC / 92 mV |
| **Basis** 750320775 (typ) | 3.0 | 33 mA / 0.73 nC / 18 mV | 315 mA / 0.84 nC / 173 mV |
| **A1** R24C2T25/R, UCC14241 (**max**) | 3.5 | 39 mA / 0.86 nC / 20 mV | 369 mA / 0.98 nC / 192 mV |
| **A3** MGJ2 (typ) | 4.0 | 44 mA / 0.98 nC / 21 mV | 419 mA / 1.12 nC / 208 mV |
| **B1** 750315240 (max) | 18 | 188 mA / 4.4 nC / 50 mV | 1.79 A / 5.0 nC / 480 mV |
| 750319697 (typ) | 25 | 258 mA / 6.1 nC / 57 mV | 2.45 A / 7.0 nC / 543 mV |

The ΔV at LS VSS is an ESL-dominated spike lasting a few ns. The routing inductance (20 vs 80 nH) changes nothing at the reservoir. ΔV at the primary pins and at V24_RAW is in `results.json`: 0.07–1.3 V for ≤ 4 pF, up to 6 V for 25 pF.

**2b. CM adder inside the repo's rail campaign** (`sim/a1_rail.py cm<pF>`).
- **Setup:** LS bank (banks = 2, 64 corners × 33/80 kHz). The full C × 95 V/ns rectangle runs for the entire 0 → 520 V ramp, 400 ns after the bank's own turn-off, and the ring's return charge is ignored (conservative).
- **Results:**

| Bank (corners) | Cio | CM current edge | Worst rail window max | Δ vs same corners, no CM (base) | Pass (< −1.6 V) |
|---|---:|---|---:|---:|---|
| HS (banks = 1, 64 × 33 kHz) | 0 (base) | — | −1.888341 V | — | 64/64 |
| HS | 3.0 | 0.3 ns (rectangle) | −1.812999 V | +75 mV | 64/64 |
| HS | 3.5 | 0.3 ns | −1.800413 V | +88 mV | 64/64 |
| HS | 3.5 | 1 ns | −1.855493 V | +33 mV | 64/64 |
| HS | 3.5 | 2 ns | −1.867345 V | +21 mV | 64/64 |
| HS | 4.0 | 0.3 ns | −1.787826 V | +101 mV | 64/64 |
| HS | **18** | 0.3 ns | **−1.435458 V** | **+453 mV** | **0/64** |
| LS (banks = 2, 64 × 33/80 kHz) | 0 (base) | — | −1.896784 V | — | 128/128 |
| LS | 3.0 | 0.3 ns | −1.859099 V (refined at 0.5 ns step) | +37.6 mV | 128/128 |
| LS | 3.5 | 0.3 ns | −1.852796 V | +44 mV | 128/128 |
| LS | 18 | 0.3 ns | −1.669987 V | +226 mV | 128/128 |

Files: `sim/rail/cm*-b1.json`, `cm*-b2.json`, `cm3.5-r1-b1.json`, `cm3.5-r2-b1.json`, `refine-cm.json`.
- One LS case at 3 pF printed +137 mV at the campaign's 5 ns step. Refined at 0.5 ns it is +37.6 mV (a sampling artefact); the other refined cases agree to < 0.1 mV.
- A further `cm25` LS run overlapped with the HS runs and briefly exceeded the 8-worker limit. Its result is not used.

**Reading.**
- **The barrier's CM current is an unmodelled term in the F6 rail budget for every option, including the basis.** It enters at the partner edge, in the bad direction.
- At the conservative 0.3 ns current edge it costs ≈ 25 mV/pF on a high-side bank and ≈ 12.5 mV/pF on the shared LS bank. At 1–2 ns (more physical for a 95 V/ns edge with finite d²v/dt) it costs ≈ 6–9 mV/pF on the HS bank.
- The committed edge-campaign margin is 78.6 mV. So:
  - the basis 3 pF *typ* would already consume 18–75 mV of it;
  - A1's 3.5 pF *max* consumes 21–88 mV;
  - A3's 4 pF *typ* consumes 24–101 mV;
  - an 18 pF part (B1) fails outright.
- **Derived requirement:** barrier capacitance ≤ ≈ 4 pF *maximum*. Fold the CM source into the edge campaign (`rail_qualification.py --edges`) as a re-validation item for whichever option is built, including the original transformer.
- A1 is the only option with a published maximum that meets this.

## 3. Option A1 (rank 1): integrated isolated bias module, single 17 V output, into the existing split

### 3.1 Circuit (per high side; HS-B identical with SW_B/P_HB/N_HB)

```
# primary, N_LS domain (same domain the SN6507 used)
U_HA  R24C2T25/R-R (or UCC14241QDWNRQ1, same pinout)
  PVIN(7), AVIN(6)       -> V24_RAW            CIN: 2 x 10 uF 50 V 1210 (UMK325AB7106KM-T, already in BOM) + 100 nF, pins 7-8
  AVIN(6)-PGND(5)        -> 330 pF C0G (RECOM pin note)
  PGND(1,2,5,8..18)      -> N_LS
  CTRL/ENA(4)            -> EN_HS (shared with U_HB): V24_RAW -100 k- EN_HS -27 k- N_LS  (4.97-5.23 V at 24 V +/-2.5 %;
                            UCC14241 VEN_IR 1.25-1.95 V; 5.5 V rec / 7 V abs max)
  PG(3)                  -> test point only, 10 k to EN_HS (primary side; never crosses a barrier)
# secondary, SW_A domain
  VOUT-/VEE(19-27,30,31,36) -> N_HA
  VOUT+/VDD(28,29)          -> P_HA           COUT at pins: existing split cout1/cout2 2 x 10 uF + chf 100 nF, moved to the module pins
  FBVOUT+/FBVDD(34)        -> P_HA -60.9 k 0.1 %- FB -10.5 k 0.1 %- N_HA ; 330 pF FB-N_HA   => 2.5 x (1+60.9/10.5) = 17.000 V
  FBVOUT-/FBVEE(33)        -> tied to FB (single-output configuration: RECOM p.4 "connect FBVOUT- to FBVOUT+ and leave COM open"; TI Fig.12-2)
  COM/RLIM(32)             -> open
  FBCOM/VEEA(35)           -> N_HA (single short trace to the FB resistor ground)
# unchanged from native-21 (RegulatedSplit minus its LDO, plus RailMonitor and BiasReservoir)
  shunt TLVH431BQDBZR K=SW_A A=N_HA REF=fb ; rtop 6.2 k SW_A-fb ; rbot 10 k fb-N_HA
  RailMonitor(src=SW_A, p=P_HA, n=N_HA) ; leg_a.bias_h BiasReservoir ; driver c_hs bank
# deleted
  T2, D10, D11, L2, bias_ha.craw, bias_ha.split.ldo (U27 TPS7A4700), .cnr, .cin
  shared: U35 SN6507 + bias_rclk, bias_rlim, bias_css, bias_rsr, bias_cin, bias_chf, bias_rsn1/csn1, bias_rsn2/csn2
```

| MPN | Role | Key ratings (source, page) | Digi-Key stock / price (read 2026-10-09 ≈ 20:05–20:12Z) |
|---|---|---|---|
| **RECOM R24C2T25/R-R** | HS-A, HS-B module | 21–27 V in (UVLO 19–21 V rising); 15–25 V total out; ±1.5 % with 0.1 % FB resistors; 2 W average (2.5 W for 5 s); ≤ 100 mA out+; 53 % typ efficiency; soft-start 3 ms, 16 ms time-out; **reinforced 5 kVAC / 1.4 kVDC working**; VIORM 1.4 kVpk; **Cio 3.5 pF**; **CMTI 150 kV/µs**; 36-SSOP. R24C2T25/R Rev.1-2024 pp.1–4, 7–8, 12 (`dl-bias/R24C2T25_R.pdf`, from https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf) | **1,205**, $8.40 (1). https://www.digikey.com/en/products/result?keywords=R24C2T25 |
| TI UCC14241QDWNRQ1 | Pin-compatible second source (same pin map: VEE/VDD/RLIM=COM/FBVEE/FBVDD/VEEA=FBCOM) | 21–27 V in; VDD–VEE 15–25 V; ±1.3 %; 2.0 W at TA ≤ 85 °C; VIOWM 1000 Vrms / 1414 VDC (reinforced, VDE 0884-17 target); CIO < 3.5 pF; CMTI > 150 V/ns; SOA Fig.10-1: ≥ 2 W to ≈ 85 °C at 15 V. SLUSF09A pp.1, 3–5, 7, 13, 30 | **0** (24 due 2027-02-15, 726 due 2027-04-01), $8.91. https://www.digikey.com/en/products/result?keywords=UCC14241QDWNRQ1 |
| TI UCC14240QDWNRQ1 | In-stock pin-compatible part, **basic** isolation | VDD–VEE **18–25 V** (cannot make 17 V; see note); VIOWM 850 Vrms / 1202 VDC; CIO < 3.5 pF; CMTI 150 V/ns. SLUSE80C pp.5–7, 9 | **1,468**, $9.51. https://www.digikey.com/en/products/result?keywords=UCC14240QDWNRQ1 |
| RT0603BRD0760K9L / RT0603BRD0710K5L | FB divider (0.1 %, 25 ppm) | — | Yageo RT family (not individually read) |

**Note on UCC14240.** It is in stock but its minimum VDD–VEE is 18 V. Using it means either a +16/−2 V drive, which leaves the qualified +15 V turn-on, or re-scaling the span monitor (`rspanuv_top`/`rspanov_top`, 120 k/133 k → about 133 k/147 k). Use it only if neither R24C2T25/R nor UCC14241 can be had.

### 3.2 Requirement check

| Req | A1 result |
|---|---|
| R1/R4 split, reservoir, shunt | Unchanged parts and nets. Only the source upstream of P–N changes |
| R2/R3 F6 bound | **Periodic rail campaign, module source** (`sim/a1_rail.py module`, `sim/rail/module-b1.json`). Model: source-only, 100 mA ceiling, 16.745 V (−1.5 %) set point with ±34 mV hysteresis ripple, 10.1 µF COUT. Result over 64 HS corners × 33/80 kHz: **128/128 pass, worst −1.889177 V**. The same corners with the committed 15.5 V/1 Ω source give −1.888341 V (`sim/rail/base-b12.json` reproduces the committed `periodic.json`, 256/256, max diff 0.0 V). Module minus base per case: −2.1 … 0.0 mV. Max shunt 28 mA (< 70 mA); min span 16.70 V. This is expected: the source reaches the negative rail only through the 4.99 k bleed and the P–N reservoir. The edge-waveform replay could not be re-run because `waveforms.npz` is not in the worktree (git-ignored, needs the vendor switching decks). The 15.5 V edge campaign already brackets a source that is *stiffer and higher* (16.75–17.26 V), so the edge result carries over, but it is listed as a re-validation item |
| R6 span | 17.000 V ± 1.5 % → 16.745–17.255 V, inside 16.218–17.839 V with more margin than the TPS7A47 (±2.5 % → 16.575–17.425 V). Ripple ≈ ±34 mV (10 mV × 6.8) |
| R7 driver | 17 V span; UCC21550B 9.2–25 V ✔ |
| R8/R9 insulation | Reinforced: VIOWM 1000 Vrms, 1.4 kVDC working, VIORM 1.4 kVpk ≥ 0.52 kVpk. Package CLR/CPG > 8 mm, CTI > 600 V, material group I. Meets both the functional basis and the stale reinforced-500 Vrms reading |
| R10 CMTI | 150 kV/µs ≥ 95 V/ns (1.58×). The basis transformer has no CMTI notion. For a module, a CMTI event is a regulation upset, not a logic error, and the reservoir holds the rail for ms |
| R11 coupling | **3.5 pF maximum** (datasheet) against the basis 3 pF typical. §2: +17 % CM charge vs the basis typical; adder in §2b: +21…+88 mV on an HS bank (still 64/64 pass in the periodic campaign); fold it into the edge campaign |
| R12 startup / burst | Module UVLO 19–21 V rising, 17–19 V falling, so it is up whenever PS2 is up and holds through burst idles (no switching dependence). Startup sim in §3.4. **Latch-off on OPP/OTP or a missed 16 ms soft-start:** CTRL comes from V24_RAW, so recovery needs a PS2 cycle. BIAS_BAD keeps DIS asserted meanwhile, which is safe |
| R13 supply | Same source (V24_RAW/N_LS from IRM-20-24 on TCO_L). PS2 allocation (`sim/budget.py`): 6.81 / 7.45 / **11.10 W** at 33 / 40 / 80 kHz (45 % efficiency allocation; 53 % typ). That is 51 % of 21.6 W at 80 kHz, against the basis 9.59 W (44 %). At 40 % efficiency: 11.88 W (55 %) |
| Thermal | Module loss 0.98 / 1.09 / **1.71 W** each (45 % allocation). RECOM: 1.7 W typ dissipation, 2.45 W max internal loss, 2 W output derating knee at 82 °C on its 50 × 50 mm 70 µm EVM. TI ΨJA 29.5 °C/W (EVM) → +29…+50 °C rise. **Must be checked in the enclosure;** this is the main cost of A1. The HS TPS7A47 heat (0.25 W each) goes away |
| R14 space | 36-SSOP 12.83 × 7.5 mm body (≈ 10.3 mm over leads). It fits inside T2's 12.0 × 14.2 mm courtyard rotated −90° (VIN/GNDP row toward y 60.7 where T2's primary was; VEE/VDD row toward y 71.7). The area freed by L2, D10, D11 and U27 is spare. T3 is the same. Board area around T2 (x 40–70, y 55–73) is open except C16 and TP9 at y ≤ 54 |

### 3.3 What must be re-validated

- **FEM.** None expected. The module sits where T2/T3 were, ≥ 14 mm outside the A21/B21 crops (mesher margin 10 mm). However, `n_ha`/`n_hb`/`n_ls` are loop nets, so **run `leg_region_diff.py`** (20 mm) on the ECO board, and re-solve only if it flags in-region copper.
- **F6 switching.** None. The −1.6 V bound and its 504/504 evidence are untouched.
- **Rail.** Done here for the periodic campaign (128/128). The edge-replay campaign must be re-run once `edge_currents.py` waveforms are regenerated (8 workers, vendor models local). Bench: VSS-to-negative-rail at the partner edge (already a DECISIONS bench gate).
- **D-33 transformer check.** Retired. Replace it with module bench checks: startup within 16 ms at full reservoir, CTRL-divider thresholds, latch behaviour, thermal at 33/80 kHz in the enclosure, and 10–16 MHz spread-spectrum emissions (TI SLUSF09A §11.3; the conducted-EMI deck has no such source).
- **D5.** No HOT↔SELV change; the module is HOT↔HOT and so is not a `BARRIER_PARTS` entry. Keep the ≥ 8 mm package footprint and copper pull-back between N_LS-domain and SW_x-domain copper under the module, with no inner-layer copper bridging under the body.
- **audit.rs / audit_f6.rs.**
  - Replace the `bias_ha/hb.transformer` / `.da` / `.db` / `.filter` / `.craw` rows (`audit_f6.rs:199-219`) and the `bias_driver` SN6507 rows (`:220-243`) with module pin rows: VIN/AVIN = v24_raw, PGND = n_ls, VDD = p_hx, VEE/FBCOM = n_hx, FB pins = local fb net, CTRL = en_hs.
  - Drop the HS entries from the TPS7A47 ANY-OUT loop at `:310` (`"bias_ha.split"`, `"bias_hb.split"`); the LS stays.
  - MPN pins in audit.rs: `bias_ha.transformer`/`bias_hb.transformer` (`:461`, `:500`) become `bias_ha.module`/`bias_hb.module` = R24C2T25/R-R.
  - Port `bias_source_cannot_move_to_ps1` (`audit_f6.rs:421-425`) to module pin 7 rewired to v15_selv.
- **ato.** Split `RegulatedSplit` into `SpanLdo` (LS only) and `Split` (shunt/rtop/rbot/cout/chf). Add `IsoBiasModule`. Add a new `ReviewOnly` DWN0036A footprint per the RECOM p.13 / TI land pattern.

### 3.4 Startup (`sim/a1_startup.py`, `sim/startup/results.json`)

| Soft-start current ceiling | Span reaches 90 % (PG, 15.3 V) | Span ≥ 16.218 V (monitor) | SW−N ≥ 1.799 V (monitor) | Final span / negative |
|---|---:|---:|---:|---|
| 60 mA (pessimistic) | **13.3 ms** | 14.2 ms | 145 ms | 17.02 V / −2.010 V |
| 118 mA (2 W / 17 V) | 6.2 ms | 6.6 ms | 141 ms | 17.00 V / −2.010 V |

- With the full 41.4 µF on P–N, PG is reached inside the module's **16 ms soft-start time-out** at both current ceilings, but only with 2.7 ms to spare at the pessimistic one.
- **Design action:** fit only the module's own 10 µF + 100 nF plus the driver bank on P–N, i.e. move the split's `cout1`/`cout2` to the module pins and drop one of them. That cuts 10 µF and gives ≈ 10.5 ms at 60 mA. Bench-measure the startup.
- The negative window (≈ 0.14 s) is set by the 4.99 k bleed charging the 242 µF SW–N reservoir. It is identical to the native-21 basis, because the module does not touch that path. The monitor holds DIS until then (R12).

### 3.5 Part count

| | Per HS | Shared | Board |
|---|---:|---:|---:|
| Removed | T, 2 × PMEG10030, 74404064101, craw, TPS7A4700, cnr, cin = 8 | SN6507 + RCLK, RLIM, CSS, RSR, CIN, CHF, 2 × (680 Ω + 100 pF) = 11 | −27 |
| Added | module, 2 × FB R, CFB 330 pF, 2 × CIN 10 µF, CIN 100 nF, CAVIN 330 pF = 8 | CTRL divider 2 R + PG pull-up = 3 | +19 |
| **Net** | | | **≈ −8 to −10** |

Unique lines removed: 750320775, SN6507DGQR, PMEG10030ELPX, 74404064101, Bias18k/30k/680/100p (if unused elsewhere). Added: R24C2T25/R-R, 60.9 k, 10.5 k. TPS7A4700 stays, for the LS only.

### 3.6 Risks

1. Module thermal at the 80 kHz allocation (≈ 1.7 W each). Mitigation: VEE/GNDP copper pours per the RECOM layout notes; the realistic 33–40 kHz load is 1.0–1.1 W.
2. A 10–16 MHz carrier inside the conducted band, unmodelled. It stays in the HOT domain, with the CM path to SW only.
3. Startup capacitance against the 16 ms time-out (§3.4).
4. Single-source in stock today (RECOM). TI UCC14241 restocks in 2027.
5. The R24C2T25/R VOUT− < −2.5 V note is irrelevant here (single-output mode).

## 4. Option A3 (rank 2): MGJ2D242005SC (+20 V output only) into the unchanged TPS7A47 + split

```
U_HA MGJ2D242005SC (SIP-7, 19.5 x 9.8 x 12.5 mm, pins 2.54 mm: 1 +VIN, 2 -VIN, 5 -VOUT, 6 0V, 7 +VOUT)
  1 -> V24_RAW, 2 -> N_LS, 1 uF + 100 nF local
  7 (+20 V) -> bias_ha-raw (existing craw 10 uF stays), 6 (0 V) -> N_HA, 5 (-5 V) -> 10 k preload to pin 6 (otherwise open)
  existing RegulatedSplit (TPS7A4700 17 V span, TLVH431 split), RailMonitor, BiasReservoir: unchanged
deleted: T2, D10, D11, L2 (and the SN6507 block as in A1)
```

**Evidence (Murata KDC_MGJ2_U01; `dl-bias/mgj2.pdf`, p.1, 2–3, 7, 13):**
- Ratings: 24 V in (21.6–26.4 V), +20 V/80 mA, 2 W rated −40…100 °C.
- Load regulation 6 % typ / 8 % max. Envelope for the 152005 sister: +4 % … −5 %. Line 1.2 %/%.
- Efficiency 82 % typ. Isolation capacitance 4 pF typ. CMTI characterised > 200 kV/µs.
- 2.4 kVDC continuous barrier withstand for functional use (PD-based). UL basic 300 Vrms, reinforced 150 Vrms. 10 % minimum load (≥ 20 mA housekeeping meets it).

**Headroom:** 20 V × (1 − 5 %) × (1 − 3 % line) ≈ 18.4 V worst. The TPS7A47 needs 17 V plus dropout (≤ 0.3 V at 100 mA), so ≈ 1.1 V margin. Light load is ≤ ≈ 21 V, well under 36 V. HS LDO heat ≤ (21 − 17) × 82 mA = 0.33 W.

**Load:** the 82.1 mA allocation at 80 kHz is 3 % over the 80 mA rating. The actual monitor draw is ≈ 10 mA against the 14 mA allowance, so ≈ 78 mA, and the rating is a 2 W (100 mA at 20 V) power rating. Flag it, and re-check if 80 kHz operation is real.

**Insulation:** functional basis met (2.4 kVDC ≫ 0.52 kVpk). It **does not** meet the stale reinforced-500 Vrms reading, so this option depends on the DECISIONS functional basis.

**Stock:** MGJ2D242005SC **606** at Digi-Key, $9.49 (https://www.digikey.com/en/products/result?keywords=MGJ2D24, ≈ 20:09Z).
- Second source with weaker specs: RECOM **R24P22005D**. 1,557 in stock, $10.11. 3 pF typ / 10 pF max; CMTI only "qualified 65 kV/µs" (< 95 V/ns); ±5 % accuracy; 10 % load regulation; basic. RECOM RxxP2xxyyD rev., `dl-bias/RxxP2xxyy.pdf`.

**Re-validation:**
- No F6 or rail rerun: the qualified source model is the TPS7A47 output.
- TPS7A47 input-range check.
- THT SIP footprint: inner-layer pull-back for the SW-domain pins; wave or hand solder like the other THT parts.
- CM sweep at 4–10 pF (§2: 4 pF typ ≈ +33 % charge vs basis typ).
- `audit_f6.rs` transformer/rectifier/filter rows → module rows; SN6507 rows deleted.
- No FEM expected (same location, confirm with `leg_region_diff.py`).

**Part count:** per HS −4 (T, 2 diodes, choke), +3 (module, 1 µF, preload). Shared −11. **≈ −13 to −15.**

**Why rank 2 and not 1:**
- Through-hole SIP, 19.5 mm long.
- Unregulated: the TPS7A47 stays, along with its ±2.5 %.
- No published maximum coupling capacitance.
- Fails the stale reinforced reading.
- It is, however, the **lowest re-validation and best-efficiency** option. If A1's thermal or EMI bench result is poor, A3 is the answer.

## 5. Option B1 (rank 4): stocked push-pull transformer, redesigned rectifier/regulator

**Circuit:**
- SN6507 kept.
- T2/T3 → WE **750315240** (1:1.1, reinforced 550 Vrms / UL E205930, 46 V·µs, 6-pad 13.74 mm footprint per ALTERNATES §2).
- **RDC on the SN6507 DC pin** (duty-cycle control, SN6507 SLLSFM0A §8.3.3, Eq.1, p.12) to bring the 26 V secondary down to ≈ 20 V.
- Rectifiers → **MURS120T3G** (200 V, 1 A, 35 ns; Digi-Key **62,766** in stock, $0.60, ≈ 20:20Z).
- TPS7A47 and split unchanged.

`sim/optb_xfmr.py` uses the out-D33 `transformer_check.py` harness: 2 cores, L min, DCR max × 1.4, 1 Ω RON, 680 Ω/100 pF snubbers, 80 µH/1 Ω filter, 85 mA load clipped below 17 V. Results are in `sim/xfmr/results.json`.

In this harness the basis 750320775 rows give 17.87–19.18 V out, a 72–94 V rectifier reverse peak and 0.44–0.47 A switch peak.
- These outputs sit 0.1–0.3 V above the committed `results.json`, because the on-time here is D·T − 10 ns rather than T/2 − 70 ns. Compare the rows below with these basis rows, not with the committed file.

| 750315240, k = 0.97 | Duty | Out min (23.3 V in / 24.7 V in) | Rectifier reverse | Switch peak | Verdict |
|---|---:|---|---|---|---|
| PMEG10030 (100 V), as in ALTERNATES | 0.48 | 22.7–25.2 V | **117 V** (in breakdown) | 0.72–0.90 A | ✘ (diode, switch current) |
| MURS120 (200 V) | 0.48 | 21.9–24.1 V | 172–184 V | 0.38–0.43 A | ✘ (reverse ≥ 0.86 × 200 V, and output too high: 0.5–0.6 W more LDO heat) |
| **MURS120** | **0.40** | **18.4–20.0 V** | 83–141 V | 0.35–0.43 A | **✔ on paper**: > 17.3 V headroom, ≤ 0.71 × 200 V, < 0.5 A |
| MURS120 | 0.36 | 16.4–17.8 V | 84–141 V | 0.33–0.42 A | ✘ (out < 17.3 V at 23.3 V / 700 kHz) |

- RDC for D = 0.40 at VCC = 24 V, RCLK = 18 k: SN6507 Eq.1 gives ≈ 0.816 × 0.40 × 24 × 19 − 1 ≈ 148 kΩ. This applies the datasheet equation as written, and it must be checked on the bench.
- The k = 0.995 MURS120 rows did not conserve energy (for example 46 V out from 0.29 W in). They are discarded as non-converged.
- The 750315240 leakage is unpublished, so k remains a bench item.

**Blockers:**
- Footprint ECO.
- Cww 18 pF **max** → §2: 5.0 nC per edge and a ≈ 0.48 V ESL spike at LS VSS at 95 V/ns; rail adder in §2b: **0/64 HS corners pass** at 18 pF.
- 52-week factory lead, with only 90 in stock.
- Rank 4.

## 6. Option C (rank 5): recorded bootstrap fallback

DECISIONS 2026-10-06 rev.: "bootstrap high side plus a regulated split, with a firmware low-side pre-charge before each burst". `sim/optc_boot.py`:
- **Setup:** V24_RAW → 2.2 Ω → 1 kV diode → RAW_HS; TPS7A47 17 V span; **the native-21 TLVH431 split**; 740 nC gate pulls/dumps; LS pre-charge 3 ms, then 33 kHz.

| Split | Phase | SW−N at end of pre-charge | Span P−N | Average midpoint current | Running (33 kHz): SW−N window |
|---|---|---:|---:|---:|---|
| **native-21 TLVH431 (sink-only)** | 2.9 ms LS pre-charge | **+0.00002 V (negative rail collapsed to 0 V)** | 17.00 V | — | the full sequence aborts at the first HS edge (time step too small at the bootstrap node); the rail never forms |
| ideal bidirectional 2 V split (0.5 Ω) | pre-charge | −1.990 V | 17.00 V | 20–33 mA *sourced* N←SW | worst −1.787 V (≤ −1.6 ✔); midpoint must carry **44 mA** average; bootstrap 47 mA average |

(`sim/boot/results.json`.) The negative rail does not merely sag: with the recorded split it **never forms**.

**Why it fails as recorded:**
- The bootstrap charge enters P via the LDO and must return to LEG_RET through **N → SW** (the LS FET). Through the reservoir that is the direction that *discharges* SW–N.
- The TLVH431 can only sink SW → N, and the 4.99 k bleed supplies ≈ 3 mA against ≈ 50–80 mA of average bootstrap current.
- A working split must **source and sink** the full HS load current at the midpoint (≈ 0.1 A push-pull buffer around the reference). That is a new circuit and a full rail re-qualification.

**Second, logic blocker.**
- During a 20 s burst idle the HS rail decays, so its monitor asserts BIAS_BAD → DIS (both UCC21550 channels, by design, `audit_f6` `rail_bad_cannot_bypass_disable`).
- The firmware LS pre-charge is therefore **blocked by the very interlock F6 made mandatory**, unless the HS monitors are re-routed to gate INA only. That reverses an audited safety rule.
- Burst-start (S5) edges would also run on a freshly recharged bootstrap.

**Rank:** last.

## 7. Considered and not pursued

- **Traco TDR/TMR/TEL 2 W:** ±15 V symmetric, 1.5 kVDC, no CMTI/Cio data. Not gate-drive parts.
- **Murata MGJ2D241802SC (+18/−2.5 V):** 1 in stock.
- **MGJ2D241505SC as a 20 V source:** its −5 V leg is rated 40 mA < 82 mA.
- **Mornsun QA-series:** no Digi-Key read done.
- **D-12's R15C2T25/R:** 15 V input, would need PS2 changed back.

## 8. Recommendation

1. **Prototype A1** (R24C2T25/R-R, 4 + 2 spare per board) on the lot.
   - Bench gates, in order: startup and latch; VSS rail at the partner edge (DECISIONS bench gate); module case temperature at 33/80 kHz in the enclosure; conducted EMI scan with the bridge idle and running.
   - Keep the TLVH431 split, reservoir and monitor exactly as qualified.
2. **Hold A3** (MGJ2D242005SC, 606 in stock) as the fallback. It is the fastest path if A1's heat or EMI disappoints, and needs no rail or F6 rerun.
3. **Do not pursue the bootstrap fallback** as recorded; the DECISIONS fallback line should be corrected (§6).
4. **Even if 750320775 arrives, A1 is the better production circuit.** Its bounded Cio, reinforced rating, tighter span, fewer parts and absence of 600 kHz cross-board drive nets outweigh the ≈ 2.5 W extra heat, provided bench thermal passes.

## Files in this folder

- `ALT-CIRCUITS.md` (this report)
- `sim/cm_inject.py`, `sim/cm/`: CM network sweep
- `sim/a1_rail.py`, `sim/reparse_module.py`, `sim/rail/*.json`: rail campaigns (base reproduction, module, CM adders)
- `sim/a1_startup.py`, `sim/startup/`: A1 startup
- `sim/optb_xfmr.py`, `sim/xfmr/`: option B
- `sim/optc_boot.py`, `sim/boot/`: option C
- `sim/budget.py`, `sim/budget.json`: PS2 budget
- `sim/board_fp.py`, `sim/board_fp.tsv`, `sim/pads.py`: board geometry dump
- `dl-bias/`: datasheets (scratch only)

## Appendix A: blocks 1 and 3 (scope removed; notes only)

- **Block 1 (C5/C6).** No work beyond reading BUS-CAP-SCREEN.md and round17 "Bulk current mode".
  - The bulk branch is outside the leg crops except port P5 in variant A5.
  - Paralleling smaller 2-pin film parts changes P5 copper and needs a FEM re-extraction.
  - A 3-part split on the same 4-pin pads does not exist (ALTERNATES §1).
- **Block 3 (D3).** No work beyond reading DC-LINK-CLAMP.md: stand-off > 286 V, ≤ 520 V at ≈ 100 A including layout, ≥ 2 J, MOV-coordination note.
