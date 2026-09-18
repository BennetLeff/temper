# M090 — Choke screen for 258.2 µH at operating bias (90 kHz boost PFC)

- **Task / attempt**: M090 / attempt-001
- **Hypothesis**: a physical choke of ≈258.215 µH effective at operating bias can
  carry 15.0 A rms / 23.2719 A peak / 4.2043 A pk-pk at 90 kHz, and its increase
  in DC+AC+core loss over the retained Würth 760800301 is **< 11.8202 W**.
- **Changed variable**: effective boost inductance 180 µH → 258.215 µH at held
  `L·f` (switching frequency 129.107 kHz → 90 kHz). Source-only: no solver, no
  model/CAD/board edit. `numerical_status = NOT_RUN`.
- **Envelope** (identical at all frequencies): 120 Vrms, 400 V bus, 1796.310 W,
  15.0 A rms, 23.2719 A peak, 4.2043 A pk-pk.

## 1. Identities and what was measured

Baseline: **Würth 760800301** (WE-TORPFC, T75), datasheet rev 001.001 / 2023-12-11,
`raw/760800301.pdf`, SHA-256 `4b01feca…c91217f8` (full digest in `inputs.json`).

Candidates (all Würth WE-TORPFC, rev 001.001 / 2023-12-11, captured to `raw/`):

| # | MPN | L_nom | R_DC max | I_R (40 K) | I_R2 (4 m/s) | I_SAT typ | size | PDF SHA-256 (prefix) |
|---|---|---|---|---|---|---|---|---|
| 1 | **760801403** | 355 µH | 35 mΩ | 12.3 A | 24.6 A | 23 A | T37 | `fc6d1440…` |
| 2 | 760801202 | 389 µH | 50 mΩ | 11.5 A | 20 A | 37 A | T50 | `e99128a5…` |
| 3 | 760801101 | 255 µH | 36 mΩ | 11.2 A | 21.7 A | 24 A | T43 | `e93d8a5d…` |

Screened/rejected: **760800202** (389 µH, I_SAT 19 A) and **760800403**
(355 µH, I_SAT 9.5 A) — both hard-saturate before the 23.2719 A peak.

L vs bias was **digitized** from each published "Typical Inductance vs. Current"
curve (page 2, 300 dpi) with `raw/extract_choke_data.py` → `raw/extraction.json`.
The curve is typical (100 kHz / 100 mV, 20 °C), not a guaranteed limit.

## 2. L at 23.2719 A (the operating peak)

| part | L_nom | L @ 23.2719 A (typ) | % of nom | vs 258.215 target | worst-case low (−20 %) |
|---|---|---|---|---|---|
| 760800301 (base) | 180 µH | **159.7 µH** | 88.7 % | — | — |
| **760801403** | 355 µH | **242.7 µH** | 68.4 % | **−6.0 %** | ~194 µH |
| 760801202 | 389 µH | 350.4 µH | 90.1 % | +35.7 % | ~280 µH |
| 760801101 | 255 µH | 183.1 µH | 71.8 % | −29.1 % | ~147 µH |

Interpretation ambiguity, stated explicitly: the model's 258.215 µH is a
**constant-L equivalent**. The baseline's *own* published curve falls to
159.7 µH at the peak, so the model is ≈13 % optimistic about the baseline there.
If the candidate is required to derate like the baseline, the bias-matched target
is ≈229 µH at peak; on that reading **760801403 (242.7 µH) is the closest match**.
760801101 matches the *nominal* 258 µH but loses 29 % of it at the peak, so its
in-circuit ripple would be ≈5.9 A pk-pk — over the 4.2043 A budget.

## 3. DC loss at the envelope (15.0 A rms) — the only directly sourceable term

`P_DC = I_rms² · R_DC,max`. Hot values use `dt_est` (square law from I_R) and
copper α = 0.00393/K — **derived estimates, not datasheet measurements**.

| part | P_DC @20 °C | P_DC hot (no fan, est) | Δ vs baseline @20 °C | Δ hot (est) |
|---|---|---|---|---|
| 760800301 | 4.50 W | 4.77 W | — | — |
| 760801403 | 7.88 W | 9.72 W | +3.38 W | +4.95 W |
| 760801202 | 11.25 W | 14.26 W | +6.75 W | +9.49 W |
| 760801101 | 8.10 W | 10.38 W | +3.60 W | +5.62 W |

Typical DCR is **not published** (max only). No AC winding loss and no core loss
is published for any part in this family (family datasheets carry only DCR, the
typical L(I) curve, the temperature-rise curve, and ratings). Those terms are
left **null with reasons**; DCR is never substituted for them.

## 4. Thermal and saturation, kept strictly separate

- **Heating (15.0 A rms)**: every candidate's *no-fan* 40 K rating is 11.2–12.3 A,
  below the envelope; estimated no-fan rise 60–72 K. All candidates reach
  15 A only with **4 m/s forced air** (I_R2 = 20–24.6 A → estimated 15–22 K).
- **Saturation (23.2719 A peak)**: 760801202 has 13.7 A margin (I_SAT 37 A);
  760801403 is **1.2 % above** its I_SAT (23 A); 760801101 is 0.73 A below its
  I_SAT (24 A) but has already lost 28 % of L.
- Dimensions/mass: T37 = 53×50 mm, T50 = 72×45 mm, T43 = 60×34 mm (baseline T75
  = 99×62 mm). **Mass is not published** (null).
- Procurement observation (2026-09-17, DigiKey highlight, not device
  performance): 760801403 $32.32 / 260 pcs; 760800202 $28.92 / 5 pcs;
  baseline 760800301 $36.74 / 51 pcs. Price/stock for 760801101 and 760801202
  not captured (recorded in `source_failures`).

## 5. Does the hypothesis hold?

- A catalog part with **guaranteed ≈258 µH at bias AND ≥15 A rms AND published
  core/AC loss** does **not** exist in this family → no complete catalog option.
- Best candidate **760801403** has the smallest DC delta (~3.4 W at 20 °C, ~5.0 W
  hot) and leaves roughly **6.8–8.5 W** of the 11.82 W saving for core+AC.
  760801202's DC-only delta is already ~9.5 W hot — little room left.
- **Core loss is unpublished and is not negligible**: the candidate is a much
  smaller core (T37) carrying ~2× the inductance, so ΔB (and core loss) is
  expected to be materially higher than the baseline's. AC winding loss at
  90 kHz / 4.2 A pk-pk is also unpublished.
- Verdict: `magnetic_delta_status = UNKNOWN`. A <11.82 W delta is **plausible**
  for 760801403 but **not established**. No candidate is ranked.

## 6. Case counts and checker

- Cases (source-only): expected 0, attempted 0, valid 0, failed 0, unsupported 0,
  unrun 0. `numerical_status = NOT_RUN`; `checker_status = NOT_RUN`
  (no G0 checker for a source-only task); `physical_qualification = NOT_PERFORMED`.
- Unresolved: core loss (all parts); AC winding loss (all parts); DCR typical;
  mass; L-at-bias tolerance/temperature; the constant-L vs bias-derated target
  ambiguity; thermal dependence on 4 m/s forced air.

## 7. Recommended next observation

Obtain **core loss at 90 kHz and the 23.27 A DC-bias operating point** for
760801403 and for the retained 760800301 (manufacturer loss tool or vendor loss
statement), then compute the DC+AC+core delta against 11.8202 W.

## 8. Accounting

Wall time ≈55 min; solver invocations 0; deadline 2026-09-17T23:10Z met with a
completed handback. Touched files: `raw/` (6 datasheet PDFs, catalog HTML,
`extract_choke_data.py`, `extraction.json`), `inputs.json`, `result.json`,
`REPORT.md`, `manifest.json`. No commits, no stash, no writes outside the
allowed directory.

---

**Single most important missing curve: core-loss vs DC bias (or vs ΔB) at
90 kHz for 760801403 and for the retained 760800301.** Core loss is the one
term that decides whether the magnetic delta stays under 11.82 W, it differs
materially between the two cores, and no source in this family publishes it.
