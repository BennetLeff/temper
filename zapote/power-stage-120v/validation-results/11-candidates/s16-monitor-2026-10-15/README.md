# S16: native-21 s43 rail-monitor worst case, and the fix

This is a desk study on the read-only snapshot at `cb48a12e6` (board of record s43; `PS` = `snap-cb48/zapote/power-stage-120v`). It covers analysis and component values only: there is no layout and no build, nothing was written under `worktrees/`, and nothing was committed. Every number below comes from a script here and is cited to a datasheet page or a repo line.

```
bash scripts/fetch.sh                 # datasheets -> dl/ (untrusted; read only through pdftotext -> dl/txt)
python3 -I scripts/manifest.py        # dl/MANIFEST.json: URL, revision, sha256
python3 -I scripts/monitor_wc.py      # model, controls, option searches -> results/monitor_wc.{json,md}
python3 -I scripts/loop_check.py      # neg-rail shunt loop phase margin with new divider loads -> results/loop_check.json
```

`monitor_wc.py --offline` runs from the cached JLC records in `dl/jlc-raw/` (untrusted; only named fields are read). `scripts/model.py` holds every input together with its citation.

## Answer

- **The defect is confirmed on a true worst-case stack. On RSS it is not confirmed.**
  - **Worst case.** With s43 values, the span-UV upper corner is 16.804 V, against an LS rail minimum of 16.575 V (−0.229 V). The span-OV lower corner is 17.192 V, against an LS maximum of 17.425 V (−0.233 V).
  - **The HS rails overlap too.** The HS rail model gives 16.577 to 17.247 V, so span OV clears neither rail. These corners are slightly inside the study's 16.869 / 17.135 V. The study's figures are reproduced exactly as control C1, under its 125 K TCR basis. Mine use a 60 K excursion and add the LM339B bias current and the TL431 |zKA| term.
  - **RSS (each limit taken as 3σ).** The threshold bands clear the rails' guaranteed limits by +0.071 V (UV) and +0.091 V (OV).
  - **Joint RSS.** Rail and threshold scatter combined gives 4.6σ and 4.7σ. Assuming normal distributions, that is about 2.3 ppm "refuses to start" and 1.2 ppm "nuisance OV trip" per rail.
  - **What drives it.** The TL431A's deviation over temperature (VI(dev), 34 mV) and its 25 °C tolerance dominate (`rss_contrib_V`: 0.221 and 0.163 V of the span-UV figure). LM339B Vos comes next at 0.072 V.
- **Option 1 (BOM-only re-centre) cannot fit inside the qualified F6 evidence.** The span-OV window's own worst-case width is 1.01–1.28 V, depending on the reference and the half-reference ratio. The qualified slot is only 0.575 V wide: from 17.425 V (LS maximum) to 18.0 V (the out-D33 hot-load campaign span).
  - The best BOM-only variant is TL431B with R79 = 4.42 k. It fixes the S16 rail overlaps (+0.096 / +0.144 V) and passes against the hard limits. But its span-OV upper corner is 18.60 V, 0.60 V above the hot-load basis, and its span-UV catch margin is only +0.069 V.
  - With the fitted TL431A, the span-UV window (1.16 V wide) does not even fit its own 1.075 V slot.
- **Recommended: option 2, candidate B re-tuned.** Each window gets its own TPS3701, and each threshold its own two-resistor divider.
  - All four thresholds sit inside the qualified basis on true worst case, including hysteresis.
  - Span OV is the tight one: +0.058 / +0.074 V. That is positive, but below my 0.5 % target, because the TPS3701 window is 0.452 V wide in a 0.575 V slot (at most ±0.061 V).
  - Cost is +$1.53 per board, +$766 per 500 boards (JLC basis), with −6 placements and −1 BOM line.
  - The study's own candidate-B dividers miss the hot-load basis: their span-OV upper corner is 18.31 V. The values below replace them.

## 1. The model (scripts/model.py)

### Circuit

From `elec/src/f6_bias.ato:112-227`. Designators are from `frozen/default.net`; MPNs are from `frozen/default.csv`.

- TL431AIDBZR (U17/U19/U21), REF tied to K, fed by rref 2.2 k RC1206FR (R59/R63/R65).
- Half-reference divider 10 k / 10 k (R79/R80, R97/R98, R112/R113).
- LM339BIDR (U29–U31). Its four open-collector outputs are wired-AND onto `good`. There is no feedback, so **trip = release (no hysteresis)**.
- Taps, top / bottom:
  - neg UV: 4.42 k / 10 k (R81/R82, R99/R100, R114/R115);
  - neg OV: 7.68 k / 10 k (R83/R84, …);
  - span UV: 120 k / 10 k (R85/R86, …);
  - span OV: 133 k ARG03BTC1333 / 10 k (R87/R88, …).

  Each tap has 1 nF C0G (C66–C69, C76–C79, C83–C86). The 1 nF caps are filters only and do not enter the static model.

### Worst-case and RSS method

- **Trip voltage:** `Vmon = (Vref·R80/(R79+R80) + ΣIB·(R79‖R80) + Vos − IB·(Rt‖Rb))·(Rt+Rb)/Rb`.
- **Worst case:** every parameter at its limit, with every vertex enumerated (1,024 per threshold). The function is monotonic in each parameter, so the vertices bound it.
- **RSS:** each limit is taken as 3σ, and the half-range effects are added in quadrature.

### Inputs

| Input | Value used | Source |
|---|---|---|
| TL431AI Vref | 2.470–2.520 V at 25 °C, IK 10 mA; ± VI(dev) 34 mV max (SOT-23-3, max − min over −40…85 °C) | SLVS543S Table 6.9 p.10 |
| TL431BI Vref | 2.483–2.507 V, VI(dev) 34 mV | SLVS543S Table 6.12 p.13 |
| TL431 \|zKA\| | 0–0.5 Ω × (IK − 10 mA). IK is 5.6–7.6 mA over spans of 15–19.5 V, giving ±2.2 mV | SLVS543S p.10 |
| LM339B | VIO ±5.5 mV (−40…85 °C); IB 0–50 nA out of each pin (4 inputs on halfref) | SLCS006Z Table 6.7 p.7 |
| TPS3701 | VIT−(INA) 397–403 mV, VIT+(INA) 400–413 mV, VIT+(INB) 397–403 mV, VIT−(INB) 387–400 mV; IIN ±25 nA; TJ −40…125 °C | SBVS240C Table 6.5 p.5 |
| Thin-film resistors | 0.1 % + 25 ppm/K × 60 K = ±0.25 % each, independent | Yageo RT V.16 p.2 (B = 0.1 %, D = 25 ppm) and p.5; Viking ARG A3 p.2 (B, C = 25 ppm); Vishay TNPW p.4 (E = 25 ppm) |
| rref RC1206FR | 1 % + 100 ppm/K (TCR assumed: the RC datasheet was not fetched). It moves Vref by less than 0.2 mV through \|zKA\| | Yageo F = 1 % |
| LS span | 17.0 V (ANY-OUT 1.4+6.4+6.4+1.6+0.8+0.4, `f6_bias.ato:63`) ±2.5 % overall accuracy (line, load, TJ −40…125 °C, lot), valid for VI ≥ VO + 1 V = 18 V. PS2 is 24 V; U26 TJ is 119.1 °C (B3), inside 125 °C | SBVS204G Table 5.5 p.6, §7.2.2.3 |
| HS span | VFB 2.4675–2.533 V × (1 + 63.4 k / 11 k) at 0.1 %/25 ppm, plus ripple ½ × 12.3 mV FB hysteresis × gain = ±42 mV → 16.577–17.247 V. Vendor ±1.5 % gives 16.656–17.163 V. **All RECOM figures are at TAMB 25 °C; no over-temperature figure is published (gap).** | R24C2T25/R Rev 1-2024 p.2 |
| −2 V rail (SRC−N) | TLVH431BQ VREF over the full range 1.221–1.265 V; ΔVref/ΔVKA 0…−2.7 mV/V × 0.77 V; Iref 0–1.0 µA × 6.2 k; \|zKA\| 0–0.4 Ω × (IK − 10 mA), with DC IK of 1.5–5 mA (HS) or 1.5–35 mA (LS, which carries 30 mA of HOT load); R77 6.2 k / R78 10 k at 0.1 %. Result: **1.9654–2.0757 V** (LS) and 1.9654–2.0594 V (HS) | SLVS555N Table 5.7 p.8; `f6_bias.ato:51-54, 99-110`; out-D33 `qualification-summary.json` hot_load_current_mA |

The span union is set by the LS rail at both ends: 16.575–17.425 V. The HS rail's minimum is 16.577 V. The LS rail fixes the window only as long as the unpublished RECOM temperature drift stays under about 0 % low and +1 % high.

### Temperature

- B3 `margins.json` (s43) has **no rows** for U16–U21 or U29–U31 (searched). The fallback is bay 61 °C (b3-ratings basis c18_h10) plus TL431 self-heat (2.5 V × 6.5 mA × 206 °C/W, SLVS543S p.5), which gives **64.3 °C expected**.
- The monitor ICs sit 11–13 mm from U26 (TJ 119 °C) and from U41/U42 (130–134 °C). So I bound the analysis at **85 °C**, the TL431AI / LM339B rated maximum, and use −10 °C cold (task-02 round-3 basis, `thresholds.py:241`). That is a TCR excursion of 60 K.
- Sensitivity runs at 39 K (−10…64 °C) and 100 K (125 °C local) are in `results/monitor_wc.json:sensitivity_dt`.
- If the monitor locale exceeds 85 °C, TL431AI and LM339B are outside their rated range.
  - The BOM-only escapes would be TL431AQ (C105255, 26,065 at JLC) and LM2901B, which has the same VIO ±5.5 mV over −40…125 °C (SLCS006Z Table 6.8 p.8).
  - TPS3701 is rated to TJ 125 °C, and option 2 stays positive at 100 K: span OV +0.022 V, span UV +0.030 V.
- **B3 should add probe rows at these parts** (open item).

### Controls (asserted in monitor_wc.py)

- **C1:** under the P4 assumptions (g05-g07 `tps3700_band.py`), the model reproduces the simplify-2026-10-15 `old_bands` to 1e-9: 15.578 / 16.869 / 17.135 / 18.557 V and the −2 V bands.
- **C2:** the study's candidate-B dividers, under the study's assumptions, reproduce its `band_V` and `release_band_V` to 1e-4.
- **`loop_check.py`** transcribes the out-D33 `rail_qualification.py` loop() and corners(). It reproduces the committed minimum phase margins (51.6177° at RTOP 6120 and 51.6200° at 6200) to 1e-6°.
  - With option 2's higher-impedance −2 V dividers the margin is 51.6186°, and with option 1c it is 51.6211°: unchanged.

## 2. What the windows must still do (allowed bands)

There are two bases:

- **Q** keeps every threshold inside the committed F6 qualification evidence, so no re-qualification is needed.
- **H** is hard ratings and physics.

| Threshold | Catch-side limit, Q | Catch-side limit, H | Rail-side limit |
|---|---|---|---|
| **span UV** (lower corner ≥) | **15.5 V**: the out-D33 negative-rail droop campaign ran at a 15.5 V span, "below the monitor's normal enable window" (`qualification-summary.json` edge_span_V; out-D33 README:70) | 12.26 V: VGS = span − neg ≥ 10 V at the CFD7's RDS(on) specification point (Table 4 p.5), with the neg-OV upper corner. The 2EDR8259X operating minimum of 8.5 V (Table 11 p.12) and UVLO on ≤ 8.5 V (Table 15 p.13) are lower | release (upper) corner ≤ **16.575 V** (LS minimum) |
| **span OV** (upper corner ≤) | **18.0 V**: the out-D33 hot-load campaign (upper shunt-current case) ran at an 18 V span (`hot_load_span_V`) | 21.0 V: 2EDR8259X VDD operating maximum (Table 11 p.12; abs max 22 V, Table 9 p.10). The CFD7 VGS limit of +20 V static (Table 2 p.3) allows span − neg ≤ 20, i.e. 21.75 V | lower corner ≥ **17.425 V** (LS maximum) |
| **neg UV** (lower corner ≥) | **1.754 V** = −1.6 V edge rule (DECISIONS.md:117) + nominal-component droop 0.154 V (D33 nominal static 1.24 × 1.612 = 1.9989 V; nominal-parts edge-screen worst −1.8446 V). This assumes a single fault: the rail regulation fails while the reservoirs are nominal | 1.506 V = the physical off-gate limit. The edge at the 1.9 V screen is 1.6 − (1.9 − 1.589)/1.25 = 1.351 V (out-D33 README:53, physical 1 Ω; DECISIONS.md:117 slope), plus 0.154 V | release corner ≤ **1.9654 V** (rail minimum) |
| **neg OV** (upper corner ≤) | **2.4 V**: out-D33 `edge-current-2.4V`, 26/26 switching cases pass at −2.4 V | 5.5 V (VGS_on ≥ 10 V at a 15.5 V span) | lower corner ≥ **2.0757 V** (rail maximum) |

- **What the OV windows catch.** An LDO pass short or a module feedback open drives the span to the raw rail (24 V or more), and either OV threshold below 21 V catches it. The OV does not remove that voltage; it only disables DIS.
- **What the UV windows catch.** An R77 short, an R78 open, or a TLVH431 short drives SRC−N to 1.24 V or 0 V, and both neg-UV designs catch it. An R77 open or a TLVH431 open lets src float toward P through the 4.99 k bleed, and neg OV catches it.
- **The −1.6 V edge rule at reservoir corners cannot be enforced by any monitor.** The rule at the D33 corner droop needs a static rail ≥ 1.885 V. That leaves an 80 mV slot below the 1.965 V rail minimum, and even the TPS3701's trip-to-release width (89 mV) does not fit it. So that rule rests on the rail's own tolerance, as DECISIONS 2026-10-06 "qualification by bounding" (ii) already states, and not on the monitor.

The margin target is a judgment: **0.5 % of the threshold**, to cover unmodelled drift, dynamic dips and model error.

- Below the target, a positive margin reads MARGINAL; a negative margin reads FAIL.
- **For UV, the rail-side check uses the rising (release) corner**, because that is the corner that decides "refuses to start".

## 3. s43 as built: results

| Threshold | Nominal | Worst-case band | Q (catch / rail) | H | RSS vs worst-case rail | Joint RSS |
|---|---:|---|---|---|---:|---|
| neg UV | 1.799 | 1.7395–1.8583 | −0.015 / +0.107 **FAIL** | PASS | +0.135 | 13σ |
| neg OV | 2.206 | 2.1313–2.2798 | +0.120 / +0.056 PASS | PASS | +0.091 | 10σ |
| span UV | 16.218 | 15.630–16.804 | +0.130 / **−0.229 FAIL** | **FAIL** | +0.071 | 4.6σ (2.3 ppm/rail) |
| span OV | 17.839 | 17.192–18.486 | **−0.485** / **−0.233 FAIL** | **FAIL** | +0.091 | 4.7σ (1.2 ppm/rail) |

Beyond S16's two rail overlaps, the model finds two further pre-existing gaps against the Q basis:

1. **The span-OV upper corner (18.49 V) is above the 18 V hot-load campaign span.** The shunt current there is not covered by the committed evidence. I estimate only +0.1 mA through the 4.99 k bleed, but that estimate is not committed evidence.
2. **The neg-UV lower corner (1.7395 V) is 15 mV below the single-fault edge-rule floor.** It is above the physical floor of 1.506 V.

## 4. Option 1: re-centre (BOM-only, same pads)

The search used E192 tops and BOM 0.1 % bottoms (10 k, 11 k, 11.7 k, 12.6 k), JLC stock ≥ 1,800, and the tiered selection in `select()`.

- **Feasibility against Q** (`results/monitor_wc.md`): each entry is the worst-case width at the slot centre / the slot, with the slack per side in brackets.

| Topology | neg UV | neg OV | span UV | span OV |
|---|---|---|---|---|
| TL431A, halfref 10k/10k | 0.123 / 0.211 (+0.044) | 0.151 / 0.324 (+0.087) | 1.161 / 1.075 (**−0.043**) | 1.284 / 0.575 (**−0.354**) |
| TL431B, halfref 10k/10k | 0.104 (+0.054) | 0.128 (+0.098) | 0.994 (+0.040) | 1.099 (**−0.262**) |
| TL431B, R79 6.2 k | 0.095 (+0.058) | 0.117 (+0.103) | 0.940 (+0.068) | 1.039 (**−0.232**) |
| TL431B, R79 4.42 k | 0.090 (+0.061) | 0.112 (+0.106) | 0.910 (+0.083) | 1.007 (**−0.216**) |
| TPS3701 (UV: trip-low to release-high) | 0.089 (+0.061) | 0.053 (+0.136) | 0.801 (+0.137) | 0.452 (**+0.061**) |

- **Span OV cannot fit the Q slot with any TL431/LM339B variant.** It needs a total stack of about ±1.6 %, and the reference alone is ±1.84 % (TL431B) or ±2.4 % (TL431A).
- **The best BOM-only variant is 1c-4420.**
  - Parts: TL431BIDBZR (C41283, 182,901 at JLC); R79 → 4.42 k (on the BOM); neg UV 750 Ω / 10 k; neg OV 2.94 k / 10 k; span UV 90.9 k / 11 k; span OV 104 k / 11 k.
  - Bands: neg UV 1.815–1.904; neg OV 2.183–2.294; span UV 15.569–16.479 (Q +0.069 / +0.096); span OV 17.569–18.598 (rail +0.144; **Q −0.598**; H +2.40).
  - Delta: +$0.167 per board, +1 net line, 0 placements.
  - It fixes S16 itself. But it needs the out-D33 hot-load campaign re-run at an 18.6 V span, and it leaves C2/C4/C7 as they are.
- **Rejected sub-options.**
  - **LM4040A25 (on the BOM, ±19 mV over the full range, SLOS456Q p.9) is not pin-compatible.** Its DBZ pinout is 1 = cathode, 2 = anode, 3 = float/anode (p.4), while the TL431 pads 1 and 2 are both on `ref` (TL431 DBZ: 1 K, 2 REF, p.4). Fitting it would short the reference, so it needs a copper change.
  - **TLVH431B (on the BOM) is no tighter.** Its full-range spec is 1.221–1.265 V (−1.5 / +2.0 %), and it needs every divider rescaled.

## 5. Option 2: candidate B, TPS3701 per window (recommended)

| Threshold | Divider (top / bottom) | Nominal | Trip, worst case | Release, worst case | Q catch / rail | Verdict |
|---|---|---:|---|---|---|---|
| neg UV (INA, U29/U30/U31) | 15.8 k / 4.42 k | 1.830 | 1.8087–1.8512 | 1.8223–**1.8971** | +0.054 / +0.068 | PASS |
| neg OV (INB, U29/U30/U31) | 28.4 k / 6.2 k | 2.232 | **2.2057**–2.2590 | 2.1502–2.2422 | +0.141 / +0.130 | PASS |
| span UV (INA, U47/U48/U49) | 240 k / 6.2 k | 15.884 | **15.682**–16.087 | 15.801–**16.486** | +0.182 / +0.089 | PASS |
| span OV (INB, U47/U48/U49) | 86.6 k / 2.0 k | 17.720 | **17.499–17.943** | 17.058–17.809 | +0.058 / +0.074 | MARGINAL (target 0.089) |

- **RSS against the worst-case rail:** +0.076, +0.139, +0.169 and +0.149 V. Joint RSS is ≥ 4.8σ.
- **Span OV recovery.** The release lower corner (17.06 V) is below the LS maximum. After a genuine OV trip, a rail sitting near its +2.5 % corner may stay "not good" until the span falls. That is the fail-safe direction and costs availability only.
- **Span OV is a tight slot.** To get span-OV margins above the 0.5 % target, re-run the hot-load campaign at about 18.2 V and re-centre. A 10 ppm top (RT0603BRB07) is not stocked.
- **Stock risk.** RT0603BRD0728K4L has 1,967 at JLC against 1,500 needed. Buy early.
- **TPS3701 pin abs max.** VINA/VINB abs max is 7 V (SBVS240C §6.1 p.4). The LM339B, by contrast, tolerates inputs at VCC (SLCS006Z p.7 note 1). See the FMEA C5 row below.

### Parts list (all three monitors; LS / HS-A / HS-B designators)

**Out:**

- U17 / U19 / U21 TL431AIDBZR (C23892).
- U29 / U30 / U31 LM339BIDR (C22416291, SOIC-14).
- R59 / R63 / R65 RC1206FR-072K2L (C114933).
- R79 / R97 / R112 and R80 / R98 / R113 RT0603BRD0710KL.

**In / changed:**

| Designators | Was | Becomes | MPN | LCSC | JLC stock |
|---|---|---|---|---|---:|
| U29 / U30 / U31 (neg window: VDD = p, GND = n, INA = uv, INB = ov, OUTA/OUTB = good) | LM339BIDR | TPS3701DDCR (SOT-23-6) | TPS3701DDCR | C132788 | 26,599 |
| U47 / U48 / U49, new (span window: INA = spanuv, INB = spanov, outputs = good) | — | TPS3701DDCR | TPS3701DDCR | C132788 | (same line, 6/board) |
| C169 / C170 / C171, new (VDD of U47–U49) | — | 100 nF | CC0603KRX7R9BB104 | C14663 (Basic) | 50 M |
| R81 / R99 / R114 (neg UV top) | 4.42 k | 15.8 k | RT0603BRD0715K8L (on BOM) | C861143 | 7,399 |
| R82 / R100 / R115 (neg UV bottom) | 10 k | 4.42 k | RT0603BRD074K42L (on BOM) | C861442 | 8,076 |
| R83 / R101 / R116 (neg OV top) | 7.68 k | 28.4 k | RT0603BRD0728K4L | C861281 | 1,967 |
| R84 / R102 / R117 (neg OV bottom) | 10 k | 6.2 k | RT0603BRD076K2L (on BOM) | C136960 | 90,071 |
| R85 / R103 / R118 (span UV top) | 120 k | 240 k | RT0603BRD07240KL | C515423 | 5,139 |
| R86 / R104 / R119 (span UV bottom) | 10 k | 6.2 k | RT0603BRD076K2L (on BOM) | C136960 | 90,071 |
| R87 / R105 / R120 (span OV top) | 133 k ARG03BTC1333 | 86.6 k | RT0603BRD0786K6L | C861580 | 10,896 |
| R88 / R106 / R121 (span OV bottom) | 10 k | 2.0 k | RT0603BRD072KL | C728588 | 14,213 |

Unchanged: the 1 nF tap caps, rpull (R91 / R109 / R124), the local 5 V LDO (U37–U39), and the existing 100 nF across p–n.

- The tap filters become 2–6 µs (today 3–9 µs).
- The `ref` and `halfref` nets disappear.

JLC stock and prices were fetched 2026-10-15 (≈ 21:45Z) and are recorded in `results/monitor_wc.json:parts` and `option2.picks`.

### Cost and lines at 500 boards (JLC basis, `line_delta()`)

- **+$1.532 per board, +$765.90 per 500.** TPS3701 costs $0.3457 at 3,000.
- **Placements: −6.**
- **Lines: −1 net.**
  - Removed: TL431AIDBZR, LM339BIDR, RC1206FR-072K2L, RT0603BRD077K68L, RT0603BRD07120KL, ARG03BTC1333.
  - Added: TPS3701DDCR, RT0603BRD0728K4L, RT0603BRD07240KL, RT0603BRD0786K6L, RT0603BRD072KL.
- This is a layout change: SOIC-14 + SOT-23 + 1206 + 2 × 0603 become 2 × SOT-23-6 + 0603 in each island (N_LS, N_HA, N_HB). There is no barrier crossing.

### FMEA (c24 §3a) rows to re-run, and changes to fail-safe direction

| Row | Change |
|---|---|
| C1 | Detection timing: TPS3701 tpd(HL) is 9.9 µs typical with no maximum (SBVS240C p.6), against the LM339B at about 1 µs. Re-run the ≤ 90 µs heartbeat budget (B4). |
| C2 | "Output open masks one threshold" now applies per TPS3701 output. Same class. |
| C3 | Unchanged (announced). |
| **C4** | The TL431 row goes. Today an open or short TL431 is **announced** (halfref goes to 8.5 V or 0 V and the UV trips). With the TPS3701 the reference is internal per IC, and a drift fault ("out of specification", 40 % of die modes in the TPS3702-Q1 FMD) can raise one window's OV or lower its UV **dormantly**, for one window (2 thresholds). **Fail-safe direction changes from announced to partial-dormant.** Obtain TI's FIT/FMD for the TPS3701 (none found; the TPS3700-Q1 FS document SLVAEM2A is the nearest proxy). |
| **C5** | Bottom-resistor open on a span divider puts the 17 V span on INA/INB through 240 k / 86.6 k, against a 7 V abs max (SBVS240C p.4). UV-bottom-open was already dormant and OV-bottom-open was announced. The **new question is whether the overstressed IC keeps its other channel**. Re-run with TI's pin FMA, or add a clamp at layout. Today's LM339B tolerates inputs at VCC. |
| C6 | Unchanged in class. |
| **C7** | The sliver closes: the TPS3701 runs from 1.8 V, and below UVLO OUTA is low (SBVS240C p.5 note 2). The "covered by UVLO" status becomes "caught". |
| New | One TPS3701 with VDD or GND open masks **one window** (2 thresholds). Today an LM339B supply fault masks all 4. Improvement. |
| New | The span-OV hysteresis means no automatic recovery when the rail sits above 17.06 V after an OV trip (fail-safe, availability only). |
| Metric | `fmea_metric.py` k-values and FIT; g05 `truth_table.py` with TPS3701 semantics. |

### Datasheet-ledger rows to update (`native-21/verification/datasheet-ledger/ledger.json`)

- **Remove:**
  - TL431AIDBZR (U17 / U19 / U21);
  - LM339BIDR (U29–U31);
  - RC1206FR-072K2L (R59 / R63 / R65);
  - RT0603BRD077K68L (R83 / R101 / R116);
  - RT0603BRD07120KL (R85 / R103 / R118);
  - ARG03BTC1333 (R87 / R105 / R120).
- **Add TPS3701DDCR** (U29–U31, U47–U49). It is a bias-supervision part, so audit it rather than leaving it UNAUDITED. Checks:
  - VDD 36 V operating / 40 V abs max, against a span of up to the 24 V raw rail under an LDO short;
  - VINx 7 V abs max, against the divider-open case (C5);
  - IOUT 10 mA, against 0.5 mA;
  - TJ 125 °C, against the local temperature;
  - VIT accuracy, SBVS240C Table 6.5.
- **Add new resistor rows:** RT0603BRD0728K4L, RT0603BRD07240KL, RT0603BRD0786K6L, RT0603BRD072KL.
- **Re-list designators** on these rows:
  - RT0603BRD0710KL (drop R79 / R80 / R82 / R84 / R86 / R88 / R97 / R98 / R100 / R102 / R104 / R106 / R112 / R113 / R115 / R117 / R119 / R121);
  - RT0603BRD0715K8L (+R81 / R99 / R114);
  - RT0603BRD074K42L (R81 / R99 / R114 → R82 / R100 / R115);
  - RT0603BRD076K2L (+R84 / R86 and their HS twins);
  - CC0603KRX7R9BB104 (+C169–C171).
- **2EDR8259XXUMA1:** the stress row "VDD at the span OV trip 17.84 V" becomes **17.94 V** (worst-case upper corner; ratio 0.854 of 21 V), cited to `results/monitor_wc.json`.
- **R24C2T25/R-R:** add the gap "output accuracy specified at 25 °C only". **TPS7A4700RGWR:** add the ±2.5 % overall-accuracy row (SBVS204G p.6) that the monitor windows now rely on.

### Other gates (from the study's brief B, still valid)

- `audit_f6.rs` RailMonitor rows and mutations;
- `verify_source.py`;
- the ECO "Mandatory rail monitor" thresholds (`ECO.md:73-77`): new nominal windows **−1.830…−2.232 V and 15.88…17.72 V**;
- the `bias_sizing.py` monitor allowance (about 6.7 mA less per rail);
- `bypass_check` for C169–C171;
- `return_path19` for `good`;
- B3.

Bench: a power-up capture of `good` with each window violated.

## Limits

- **Static analysis only.** Edge dips on SRC−N (up to 0.29 V at D33 corners) and P droop at gate edges are not modelled against the 2–6 µs tap filters. A UV trip on an edge dip would be a nuisance, not a mask.
- **Resistor load-life drift** is excluded. It is covered only by the margin target.
- **The RECOM over-temperature accuracy is unpublished.** The −2 V rail's DC shunt-current ranges are bounds I derived, not measurements.
- **The FMEA FIT figures were not re-run.** No TPS3701 FMD or pin FMA was found.

Sources searched for TI functional-safety documents: [TPS3700-Q1 FS information](https://www.ti.com/lit/fs/slvaem2a/slvaem2a.pdf), [TPS3702-Q1 FIT/FMD/pin FMA](https://www.ti.com/lit/pdf/sbva070), [TPS3703-Q1 FS information](https://www.ti.com/lit/fs/sbva072a/sbva072a.pdf).

## Decision (integration, 2026-10-15): option 1c-4420, not candidate B

**Adopted for the S16 stage: option 1c-4420.** TL431AIDBZR → TL431BIDBZR (U17/U19/U21) with R79 = 4.42 k and the tap
values in `results/monitor_wc.md` §"Option 1c-4420". It is BOM-only: no layout, no placements, +$0.17 per board.

**Its one qualified-basis miss is closed.** Span OV's worst-case upper corner, 18.60 V, sat above the 18 V hot-load span.
The out-D33 hot-load campaign was re-run at a **19 V span**: 128 / 128 pass, negmax −1.9159 V, shunt 21.6–64.5 mA
against the 70 mA limit (`round17/delegation/out-D33/rail-hot-19V/`). The qualified span-OV ceiling becomes 19.0 V.
Span UV catch margin +0.069 V sits inside the 15.5 V droop-campaign basis (positive, below the 0.5 % target).

**Candidate B (TPS3701 per window) not adopted**, for the same reason as simplification A and C: it weakens how
independently the protection fails.
- C4: a TL431 open or short today trips the UV and is announced. A drift in the TPS3701's internal reference can
  silently mask one window. No TPS3701 FMEDA exists.
- C5: an open bottom resistor puts the 17 V span on a 7 V input pin.
- Cost: +$1.53 per board, against +$0.17.

Candidate B stays the fallback if the TL431B stage fails its card.

**Carried as items:**
- the −2 V UV lower corner before the fix (1.7395 V, 15 mV under the −1.6 V edge-rule floor) is cleared by 1c-4420
  (lower corner 1.8146 V);
- the monitor parts have no B3 probe rows: local temperature is bounded at 85 °C, not solved;
- RECOM output accuracy over temperature is unpublished.

**The downloads `dl/` (datasheets, JLC part records) are not in git.** The durable copy is
`runs-native21/s16-monitor-dl/`; copy it back to `dl/` before an offline rerun. Hashes are in
`results/datasheet-manifest.json`.
