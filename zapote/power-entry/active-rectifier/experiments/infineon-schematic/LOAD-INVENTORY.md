# AUX_15V DC load inventory (Infineon active-bridge experiment)

Source of schematic truth: `src/main.ato` (279 lines). Every current below is
traced to a named net/component in that file. Per
`zapote/skills/electrical-model-review/SKILL.md`, each number carries
typical/min/max/assumed/measured + conditions + exact part, or NULL with the
named missing input. Nothing here is a protection or qualification claim.

Retained sources in `sources/`:

| Shorthand | File | SHA256 (prefix) |
|---|---|---|
| TI | `ti-ucc21530-q1.pdf` (SLUSDG3F, rev Sep 2024) | `5df00414…` |
| IRM | `harness-lab/audits/buck-final-20260910/margin-resolution/IRM-10-SPEC.PDF` (spec 2025-08-08) | `1aab6b30…` (per SOURCES.md) |
| FC | `panasonic-fc-a-series.pdf` (FC-A radial datasheet, 01-Dec-22, via Octopart) | `31d50abf…` |
| ERJP | `panasonic-erj-p-series.pdf` (ERJ PA2/P03/PA3/P06/P08/PM8/P14 datasheet, via RS Online) | `3bb6b21a…` |
| FET | `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-ACTIVE/attempt-001/raw/Infineon-IPW60R017C7.pdf` | per SOURCES.md |

NOT retained (values depending on them are NULL below): IR11688S datasheet,
BSP300H6327XUSA1 datasheet, ES1J datasheet, Kemet C0805C224K5RACTU DC-bias
curve, RH05047R0FE02 pulse/package drawing, Yageo RC0603FR tolerance spec,
mains waveform/quality record.

## 1. Direct AUX_15V loads (AUX_15V rail to HOT_GND or via input-side pins)

| # | Path (nets/components per `src/main.ato`) | Value | Kind/condition | Source |
|---|---|---|---|---|
| 1a | UCC21530 VCCI (pins 3+8; TI pin table: pin 8 "internally shorted to pin 3" — ONE load, not two) | 2.0 mA | MAX quiescent, VINA=VINB=0 V, TJ −40…+150 °C | TI p.7 (typ 1.4 mA). Table header states VVCCI = 3.3/5 V; this design runs VCCI = 15 V, so applying the table at 15 V is an ASSUMED extension (input-side bias assumed supply-independent; no evidence retained) |
| 1b | UCC21530 VCCI operating (INA/INB switching) | 3.5 mA per channel | MAX at f = 500 kHz, COUT = 100 pF | TI p.7. Condition DOES NOT match this use (INA/INB switch at line rate, ~50–120 Hz edges, not 500 kHz). At line rate the dynamic term is negligible; steady draw is bounded by 1a + gate-charge energy on the VDDA/B side. The 500 kHz number is recorded for provenance, NOT used as an operating bound |
| 2 | IR11688S VCC (pin 2, `sr.VCC ~ AUX_15V`) | NULL | Missing input: IR11688S datasheet (VCC quiescent + operating + gate-drive supply current). Expected small (controller + 2 low-side gates at line rate) — expectation is not evidence | — |
| 3 | VS divider R2 47k / R3 150R (`r_vs_top.p1 ~ AUX_15V`) | 326 µA at max rail (15.375 V / 47.15 kΩ); 318 µA at nom | Illustrative (computed from marked values; resistor tolerance spec not retained, ±1 % assumed from Yageo `FR` coding — unretained). VS pin input current NULL (missing: IR11688S VS pin characteristics) | schematic values |
| 4 | EN divider R14 10k pull-up / R15 100k pull-down | 140 µA at max rail (15.375/110k); node ≈ 13.98 V max rail | Illustrative, same tolerance caveat. EN pin input current NULL (TI gives thresholds VENH/VENL only, no input-current spec) | schematic values + TI p.7/§7.4.1 |
| 5 | MOT R1 100k to GND (`sr.MOT ~ r_mot.p1`) | NULL | Missing input: IR11688S MOT pin voltage/current characteristic. Resistor current cannot be bounded without the pin voltage | — |
| 6 | BSP300 gates tied to AUX_15V (2× `sense_x.G ~ AUX_15V`) | NULL | Missing input: BSP300H6327XUSA1 datasheet (gate leakage). Expected ~0 DC — expectation, not evidence | — |
| 7 | BSP300 source → 100 Ω → SENSE_A/B nodes | NULL | Missing inputs: BSP300 bias current + IR11688S VD1/VD2 pin input current. Both datasheets absent | — |
| 8 | Low-side gate pull-downs R12/R13 10k (GATE_Q3/Q4 → HOT_GND), driven by IR11688S Gate1/Gate2 from VCC=AUX | 1.5 mA MAX each when its gate is high (15.375/10k, max rail); combined average ≈ 1.5 mA under complementary 50 % drive (assumed drive pattern — IR11688S timing not retained) | MAX per-gate by Ohm's law on marked values; average ASSUMED | schematic values |
| 9 | DT network R16 10k + C7 1 nF | 80 µA through R16, sourced from the DT pin to GND — NOT an AUX_15V load (recorded to close the pin) | TI §7.4.2.2: "steady state voltage at the DT pin is about 0.8 V" (typical/approx wording — not a MAX bound) | TI §7.4.2.2 |
| 10 | Bypass caps C1 4.7 µF / C2 100 nF DC leakage | NULL (assumed negligible, pA–nA class — assumption, not evidence) | Missing input: none required for sizing; listed so the audit trail closes | — |

Worst-known direct-AUX DC total (operating, gates switching, max rail):
2.0 (VCCI) + 0.33 (VS) + 0.14 (EN) + 1.5 (LS pull-down avg) ≈ **3.97 mA**,
plus NULL items 2, 5, 6, 7, 10. Steady state is ~0.6 % of the IRM 0.67 A
rating before the bootstrap recharge paths — the rail is unloaded in
steady state; the stress is the cold-start transient (§3).

## 2. Bootstrap-path loads (AUX_15V → R_boot → ES1J → BOOT_x → HS_x, per leg)

| # | Load | Value | Kind/condition | Source |
|---|---|---|---|---|
| 11 | UCC21530 VDDA/B quiescent (one per leg) | 2.5 mA MAX each (typ 1.0), VINA/B = 0 V, TJ −40…+150 °C, VDDA/B = 15 V | MAX. Table condition matches (15 V row). Line-rate switching adds negligible dynamic vs quiescent; gate-charge energy handled in item 14 | TI p.7 |
| 12 | High-side gate pull-down R10/R11 10k (GATE_Q1→HS_L, Q2→HS_N) | 1.49 mA MAX each when its gate is high (14.875 V max boot / 10 kΩ). Model uses continuous MAX (conservative: duty ≈ 50 %, average ≈ 0.75 mA) | MAX by Ohm's law; continuous-use ASSUMED conservative | schematic values |
| 13 | Bulk electrolytic leakage (one per leg) | 1000 µF/25 V (old): 250 µA MAX (0.01CV, after 2 min, +20 °C). 100 µF/25 V (selected): 25 µA MAX, same conditions | MAX per FC datasheet. Cold: lower (datasheet: leakage falls with temperature — qualitative). After long unpowered storage: elevated until reformed (FC application notes) — first-charge value NULL, bench item B-5 | FC specifications + §application notes |
| 14 | MOSFET gate charge per commutation | 240 nC TYP per device (Qg; Qgs 50 / Qgd 85 nC typ). NO MAX published | TYP at VDD = 400 V, ID = 58.2 A, VGS 0→10 V — conditions DO NOT match (this bridge: ≈170 V peak, ≈15 A, VGS 0→≈13 V). Worst-case charge NULL. Model uses 240 nC screening + ×2 sensitivity, both ASSUMED | FET datasheet p.2/5 (via retained campaign PDF + txt extraction) |
| 15 | 220 nF bootstrap ceramic DC-bias derating | NULL | Missing input: Kemet C0805C224K5RACTU DC-bias curve. Immaterial to hold-up at 100 µF bulk scale (0.2 %); relevant only to the HF switching transient alongside the 1 µF VDDA/B bypass | — |
| 16 | ES1J diode Vf | 0.6 V min / 1.1 V max ASSUMED screening pair (prior model) | Missing input: ES1J datasheet. Both ends ASSUMED, bench item B-6. Polarity of use: Vf_min at max rail sizes the peak charge current; Vf_max at min rail sizes hold/recharge | prior screen, unretained |

Hold current per leg used by the model (MAX-known screening sum):
I_hold = 2.5 mA (item 11) + 1.49 mA (item 12, continuous-conservative)
+ 0.025 mA (item 13, selected cap) = **4.02 mA MAX-known** (old screen:
4.18 mA with the 1000 µF leakage). Gate charge (item 14) is applied as a
discrete Qg/C step at each commutation, not folded into I_hold.

## 3. The supply: what IRM-10-SPEC.PDF does and does not say

Does say (IRM-10-15 column; Note 1: parameters at 230 Vac / rated load /
25 °C unless stated):

- RATED CURRENT 0.67 A, CURRENT RANGE 0–0.67 A (no minimum load), RATED
  POWER 10.05 W, VOLTAGE TOLERANCE ±2.5 % (setup + line + load),
  RIPPLE & NOISE 200 mVpp MAX (20 MHz, twisted pair + 0.1/47 µF).
- SETUP, RISE TIME: 600 ms / 30 ms AT FULL LOAD. Note 4: setup measured at
  FIRST COLD START; ON/OFF cycling may INCREASE setup time.
- HOLD UP TIME (Typ.): 30 ms / 230 Vac, 8 ms / 115 Vac AT FULL LOAD.
  TYPICAL — not a minimum; and at our ~4 % load the hold-up is longer by
  physics but unquantified (no curve) → extended hold-up ASSUMED, bench B-7.
- OVERLOAD: 115 %–190 % rated output power; protection type HICCUP MODE,
  auto-recovery. I.e. guaranteed NO trip below 0.77 A; guaranteed trip by
  1.27 A; behavior between is a lot/band scatter, and the transient
  (hiccup off-time, restart) is unspecified.
- OVER VOLTAGE: 17.25–20.25 V, shutoff + zener clamp.
- INPUT: 85–305 Vac, 47–440 Hz. Output derating vs input voltage curve
  exists (figure, values not digitized — digitized curve NULL).

Does NOT say (all NULL for this analysis):

- No current-limit / foldback VALUE below the hiccup band (the 100–115 %
  band, 0.67–0.77 A, is unspecified behavior, not guaranteed headroom).
- No output transient response to a step load (the cold-start RC load
  draws full current the instant the output rises — the loop response to
  that edge is unspecified).
- No sub-85 Vac brownout output curve (recharge starvation below minimum
  input is unmodeled by the manufacturer; §4 of STARTUP-SELECTION treats
  it parametrically and assigns bench B-8).
- No startup current-limit vs time, no minimum-load stability bound
  beyond the 0 A range endpoint.

## 4. The flagged question, quantified with worst-KNOWN numbers (old design)

Cold start, both bulks discharged, max rail (15.375 V + 100 mV ripple
peak = 15.475 V), Vf_min 0.6 V (assumed), R = 47 Ω:
per leg (15.475 − 0.6)/47 = **316 mA**; two legs **633 mA**; + §1
worst-known ≈ 4 mA + NULL items (2, 5, 6, 7 open) ≈ **≈637 mA worst-known**
vs 670 mA nominal rating → **33 mA (≈5 %) margin**, with three NULL loads
unbounded and the 100–115 % supply band unspecified. The flag is
CONFIRMED as an insufficient-margin finding: not an established failure
(hiccup is guaranteed only above 770 mA and no failure was measured), but
a 5 % margin over an incomplete load sum against a nominal rating is not a
supported design. The selection in STARTUP-SELECTION.md resolves it by
removing the oversize that causes it, not by re-rating the supply.
