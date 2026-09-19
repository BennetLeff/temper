# Startup-supply selection (bootstrap + AUX_15V cold start)

Status: SELECTED. This file appends to (does not rewrite) TIMING-REVIEW.md,
DECISION.md, and the prior `calc/bootstrap_corner.*` screen, all of which
remain as prior evidence. Model source: `calc/startup_model.rs` (compiled
`rustc -O`), raw outputs: `calc/outputs/`. Load inventory and supply
statements: `LOAD-INVENTORY.md`. ngspice cross-check:
`calc/outputs/xcheck_report.txt`.

## 1. What was wrong with the prior positions

The 1000 µF/25 V bulk (EEU-FC1E102) per leg is ~40× the computed charge
demand. Demand per 8.33 ms half-cycle: hold charge 4.015 mA × 8.33 ms =
33.4 µC + gate charge 240 nC (typ) ≈ 34 µC. At a 3 V droop budget that is
≈ 11 µF. The 1000 µF bulk exists without a demand derivation, and its
cold-start charge (2 × 1200 µF discharged through 2 × 47 Ω) draws
633 mA worst-known before any other AUX load — a 5 % margin to the
IRM-10-15 0.67 A nominal rating over an incomplete load sum
(LOAD-INVENTORY.md §4). Neither the 1000 µF nor the 47 Ω earned its place.
Both are replaced below. The 220 nF HF ceramic + 1 µF VDDA/B bypass stay:
240 nC into 1 µF is a 0.24 V switching step — derived, adequate.

## 2. Fix evaluation (small concrete set)

| Fix | Effect (numbers from `calc/outputs/`) | Verdict |
|---|---|---|
| (a1) Right-size C only: 100 µF, keep 47 Ω | Peak UNCHANGED (V/R sets peak, not C): still 633 mA total. Energy 133→13 mJ. Does not resolve the flag | Rejected alone |
| (a2) Larger R only: 220 Ω, keep 1000 µF | Peak 135 mA, but τ = 220 ms, 5τ ≈ 1.1 s charge — bootstrap lags the 30 ms rail rise; energy still 133 mJ/leg | Rejected |
| **(a3) SELECTED: C 100 µF + R 220 Ω** | Peak/leg 71.2 mA, total 146 mA (4.6× under nominal, 5.3× under hiccup-min). Worst hold-end 11.18 V @50 Hz (1.98 V over the 9.2 V floor), 10.72 V under assumed asymmetry (1.52 V). Energy 13.3 mJ/leg. Charge to 9.2 V in ≤ 38 ms at min source | **Selected** |
| (b1) Staggered/sequenced leg charging | Halves peak even at 47 Ω, but adds switches + sequencer + failure modes for a margin (a3) already provides passively | Rejected (complexity unjustified) |
| (b2) NTC/series inrush limiter | Aging drift, hot-restart blindness (hot NTC ≈ no limiting on the restart that matters), tolerance stack | Rejected |
| (c1) Bus-fed startup with aux takeover | New converter + isolation + handover logic; answers a question (a3) already answers with two passives | Rejected |
| (c2) Higher-rated aux (e.g. IRM-20-15, 20 W/1.33 A) | Treats the symptom; the 1000 µF stays unjustified; footprint/cost up. Kept as FALLBACK if bench B-2/B-3 uncover AUX loads > 100 mA | Fallback only |

Criteria applied: cold-start peak vs the IRM overload band with margin;
UVLO margins at worst-case hold (vs 8.9 rise-max, 8.4 fall-max, 9.2 floor);
recharge completeness at min line/high temp (hot corner holds with
1.98 V); resistor pulse vs the overload-test envelope + bench B-4;
BOM/footprint delta (both shrink).

## 3. Selected design (exact MPNs, values, tolerances)

- R_boot (R17/R18): **220 Ω, Panasonic ERJ-P08J221V** — 1206 (3216),
  ±5 %, TCR ±200 ppm/°C MAX, 0.66 W @70 °C, limiting element 500 V,
  overload-test 2×RCWV 5 s, AEC-Q200, −55…+155 °C (retained ERJP
  datasheet). Footprint `Resistor_SMD:R_1206_3216Metric` (exact KiCad).
- C_bulk (C10/C11): **100 µF/25 V, Panasonic EEU-FC1E101** — radial
  ø6.3 × 11.2 mm, P2.5 mm, ±20 % @120 Hz/20 °C, 290 mA rms ripple,
  0.35 Ω impedance, leakage ≤ 25 µA (0.01CV) after 2 min, 1000 h @105 °C
  (ø6.3 class), −55…+105 °C (retained FC-A datasheet). Footprint
  `Capacitor_THT:C_Radial_D6.3mm_H11.0mm_P2.50mm` (exact KiCad;
  H11.0 vs L11.2 nominal — 0.2 mm height-clearance note for layout).
- Unchanged: ES1J diodes, 220 nF bootstrap ceramics, 1 µF VDDA/B bypass,
  all gate/EN/VS/sense networks, IRM-10-15, UCC21530BQDWKRQ1, IPW60R017C7.

## 4. Margins (from `calc/outputs/startup_corners.csv`, `cold_charge*.csv`)

| Corner | Hold-end (V) | vs 8.9 rise | vs 8.4 fall | vs 9.2 floor |
|---|---|---|---|---|
| nominal 60 Hz | 12.98 | +4.08 | +4.58 | +3.78 |
| worst-hold 60 Hz (min rail+trough, max Vf/R, min C, max hold, Qg×2) | 11.23 | +2.33 | +2.83 | +2.03 |
| worst-hold 50 Hz | 11.18 | +2.28 | +2.78 | +1.98 |
| hot, min line (R @+155 °C via retained TCR) | 11.18 | +2.28 | +2.78 | +1.98 |
| assumed asymmetry (10 ms hold / 6.67 ms recharge) | 10.72 | +1.82 | +2.32 | +1.52 |
| prior-design restated (1000 µF + 47 Ω, ripple trough added) | 12.91 | +4.01 | +4.51 | +3.71 |

The restated prior corner differs from `bootstrap_corner.json` (13.010 V)
by the 0.1 V ripple trough now debited at the rail minimum — attributable,
not a discrepancy. Closure (closed-form vs 1-µs stepped integration):
worst 0.038 mV — PASS (< 2 mV). ngspice Parts A/B agree to ≤ 11 µV.

Cold start (both legs discharged, max rail, Vf_min assumed, R_min, C_max):
peak 71.2 mA/leg, **146.3 mA total** incl. 4 mA worst-known AUX base —
4.6× below the 0.67 A nominal rating, 5.3× below the 0.77 A hiccup-min.
Energy 13.3 mJ/leg (was 133 mJ). 9.2 V reached in 24.5 ms (ideal source),
27 ms (illustrative current-limit clamps that never bind), 37.6 ms
(analytic, min source) — all inside the IRM 600 ms setup / 30 ms rise
envelope. Charge τ = 25.1 ms; 5τ = 139 ms.

Resistor pulse (ERJ-P08J221V): 14.9 V peak across 220 Ω (71 mA), 13.3 mJ
in ~140 ms, ≈ 95 mW average over the charge; steady recharge dissipation
≈ mW. RCWV = √(0.66×220) = 12.05 V continuous — the 14.9 V peak exceeds
the CONTINUOUS rating for ~ms and sits inside the 2×RCWV/5 s overload-test
envelope with large time margin. That comparison is ILLUSTRATIVE (an
overload test is not a repetitive-pulse rating; no single-pulse curve is
in the retained datasheet) — bench B-4 owns pulse life. No protection or
endurance claim follows.

Brownout (parametric AUX sag at 50 Hz worst-hold electrics; IRM sub-85 Vac
behavior NULL per manufacturer): 9.2 V floor crossed at AUX ≈ 12.4 V;
8.4 V fall-max crossed at AUX ≈ 11.6 V; below that the driver is held off
by UVLO (gates off = pre-charge state, body-diode topology per REVIEW.md).
UVLO chatter in the ≈ 11.6–12.4 V band is CONJECTURE — it requires the
IRM output to dwell in that band during a sag, which no retained source
establishes. Bench B-8.

Interrupted mains: bootstrap drain 13→8 V at 4.015 mA on 80 µF takes
≈ 100 ms — the bootstrap outlasts the IRM hold-up (8 ms typ @115 Vac full
load; longer at our ~4 % load by physics, unquantified → assumed, bench
B-7), so a long dropout restarts as a benign cold start (71 mA/leg).

## 5. Corner set declaration

Declared corners (all in `startup_corners.csv` + §4): nominal 60 Hz;
worst-hold 60/50 Hz; hot min-line; assumed line asymmetry; brownout AUX
sweep (13/12/11/10.5 V); cold-start max-peak; cold-charge min-source;
current-limit clamp variants (770/670 mA, illustrative foldback — the
IRM hiccups, which is unmodeled); prior-design reference. Capacitor
tolerance ±20 % (retained FC), resistor ±5 % + TCR (retained ERJP),
ceramic DC-bias derating NULL (immaterial at 100 µF scale, bench B-6
covers the HF path only), diode Vf assumed pair (bench B-6), ESR cold
NULL (0.35 Ω nominal is 0.16 % of R — covered by inspection, cold rise
unbounded → bench B-5), storage-reform leakage NULL (bench B-5), mains
waveform quality NULL (asymmetry assumed, bench B-8), IRM transient loop
response NULL (bench B-2).

## 6. Bench-check list (execution out of scope; each binds a NULL/assumption)

| ID | Binds | Probe points | Waveform / procedure | Pass criterion |
|---|---|---|---|---|
| B-1 | Cold-start peak 146 mA | AUX_15V rail (diff), both R_boot currents (shunt or current probe) | First cold start from discharged bulks, 230 Vac and 115 Vac; capture 0–200 ms | Peak total < 400 mA (model + full NULL-load allowance); no IRM hiccup signature (rail monotonic after rise) |
| B-2 | IRM transient response (NULL) | AUX_15V at module pins, AC 100 MHz BW | Same shot as B-1; rail dip/delay vs load edge | Rail reaches 14.4 V within 100 ms of rise start; dip after rise < 1 V |
| B-3 | IR11688S VCC + MOT + sense currents (NULL §1 items 2,5,7) | AUX_15V series shunt; MOT/VS/SENSE node voltages | Powered steady state, both half-cycles | Sum of NULL items < 100 mA (else revisit fallback c2); record values into the ledger |
| B-4 | ERJ-P08 pulse life (illustrative §4) | R_boot body temp (IR) + resistance before/after | 50 cold starts, 5 min apart, max line | ΔR < 1 %; no body discoloration; vendor pulse curve requested in parallel |
| B-5 | Bulk ESR cold + storage leakage (NULL) | BOOT_x droop over one 10 ms half-cycle | −20 °C soak (or coldest available); first charge after ≥ 72 h unpowered storage | Hold-end ≥ 10.5 V in both; leakage settles under 100 µA within 2 min of bias |
| B-6 | ES1J Vf + 220 nF bias (assumed) | Diode Vf at 4 mA and 70 mA (bench supply); retain ES1J datasheet | Curve-tracer or source-meter sweep, hot + cold | Vf(4 mA) ≤ 1.1 V and Vf(71 mA) ≥ 0.4 V (screening band); datasheet retained in `sources/` |
| B-7 | Dropout ride-through (assumed) | AUX_15V, BOOT_A/B, GATE_Q1/Q2 | Mains interrupt 5/10/20/100 ms at 115 + 230 Vac | ≤ 10 ms: no UVLO entry (BOOT stays > 9.2 V); ≥ 100 ms: clean cold restart per B-1 envelope |
| B-8 | Sag/chatter (conjecture) | AUX_15V (slow), BOOT_x, driver OUTx | Variac sag 230→70 Vac over 1 s, hold, recover | Record AUX band where OUT stops/restarts; no latch-up or shoot-through on recovery (gates verified complementary before full power) |

## 7. Schematic changes (this selection)

`src/main.ato`: R17/R18 47 Ω → 220 Ω, MPN RH05047R0FE02 → ERJ-P08J221V;
C10/C11 1000 µF → 100 µF, MPN EEU-FC1E102 → EEU-FC1E101.
`src/components.ato`: BootstrapResistor footprint axial-power placeholder
→ `Resistor_SMD:R_1206_3216Metric`; BootstrapBulk footprint
`CP_Radial_D10.0mm_P5.00mm` → `Capacitor_THT:C_Radial_D6.3mm_H11.0mm_P2.50mm`;
comments updated (no new part class needed — value/MPN/footprint only).
`BOM.csv` rows R17–R18, C10–C11 updated. Build + native + ERC re-run
(BUILD.md receipt). SOURCES.md gains FC + ERJP rows. No PCB edited.
