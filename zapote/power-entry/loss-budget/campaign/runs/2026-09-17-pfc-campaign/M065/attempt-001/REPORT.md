# M065 attempt-001 — 357.5 µH choke at operating bias for the 65 kHz boost PFC

- **Task ID:** M065 · **Attempt:** attempt-001 · **Kind:** source-only
- **Campaign:** 2026-09-17-pfc-campaign · **Contract:** C1.1 (`0accd9bc…`, hash verified)
- **Base revision:** `b1a9ad74de50f283762a488a28c19f764830cdee` (matches dispatch)
- **Deadline:** 2026-09-17T23:10:00Z · **Solver invocations:** 0 (per dispatch)
- **Hypothesis:** a physical choke can supply ≈357.528 µH effective at the 23.2719 A
  operating bias, carry 15.0 A rms / 23.2719 A peak / 4.2043 A pk-pk at 65 kHz, and add
  **less than 19.3765 W** of DC+AC+core loss over the retained Wurth 760800301.
- **Actual changed variable:** captured three exact WE-TORPFC catalog candidates at the
  65 kHz design point and digitized their L-vs-bias curves; no solver, model or CAD edit.

## 1. Baseline and candidates (exact identities, PDF hashes)

| Role | MPN | Size | PDF SHA-256 | Package |
| --- | --- | --- | --- | --- |
| baseline | **760800301** | T75 | `4b01fecaf517331dbc40cc291b2b0841904d8a221228b43541c72416c91217f8` | TH toroid, 4×0.8 mm pins + #4 bolt |
| candidate 1 | **760801202** | T50 | `e99128a5c3a315d0f6a98d875ace8bd460ed61c38d0fb8e4b870de7b70ec3aab` | TH toroid, 4×0.8 mm pins + #4 bolt |
| candidate 2 | **760801403** | T37 | `fc6d14407cbb0fb5f4e466fa4ea70ce546e0387bdef0002cb8921ef7f5e27e4a` | TH toroid, 4×0.7 mm pins + #4 bolt |
| candidate 3 | **760801321** | T75 | `5e16a6904ed2a69cc99a26104d0e1512bc299da3143ca7206b7ecc82052ea41c` | TH toroid, 8×0.7 mm pins + #4 bolt |

Manufacturer: Würth Elektronik eiSos GmbH & Co. KG (Midcom). All four documents are
Rev **001.001, dated 2023-12-11**, 8 pages, captured from the manufacturer datasheet URL
pattern `https://www.we-online.com/components/products/datasheet/<MPN>.pdf` (HTTP 200,
`application/pdf`, `Last-Modified 2025-01-15`). No HTML was hashed as a datasheet.

**Control reproduced:** the baseline bundle hash matches the coordinator's source bundle
(`zapote/power-entry/loss-budget/sources/760800301.pdf`). No numerical control was issued.

## 2. The key numbers at the envelope (15.0 A rms / 23.2719 A peak / 4.2043 A pk-pk / 65 kHz)

L-vs-bias is a **graph** on datasheet page 2 (no table), so it was digitized at 600 dpi
(`derived/digitize_l_curve.py`). Cross-check: for 760800301 and 760801202 the digitized
curve at the printed ISAT reads 0.698 / 0.687 of nominal, matching the family's
`|ΔL/L| < 30 %` definition. ±2 µH digitization uncertainty; typical curve, not a limit.

| MPN | L nom ±20 % | **L @ 23.27 A (typical curve)** | vs 357.528 µH target | R_DC max @20 °C | IR (no fan) | IR2 (4 m/s) | ISAT typ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 760800301 | 180 µH | **159.8 µH** | 0.45× | 20 mΩ | 24.5 A | 48 A | 43 A (`\|ΔL/L\|<30%`) |
| **760801202** | 389 µH | **350.1 µH** | **0.979×** | 50 mΩ | 11.5 A | 20 A | 37 A (`\|ΔL/L\|<30%`) |
| 760801403 | 355 µH | 338.8 µH | 0.948× | 35 mΩ | 12.3 A | 24.6 A | 23 A (curve disagrees) |
| 760801321 | 720 µH | 694.9 µH | 1.944× | 42 mΩ | 17.2 A | 31.6 A | 38 A (curve disagrees) |

**Candidate 1 (760801202) is the match**: 350.1 µH at bias, 2.1 % below the 357.528 µH
target, and the peak 23.2719 A is only 0.63× its ISAT.

## 3. Loss at this envelope — what is sourced and what is not

`R_DC` is published **max only, at 20 °C** (no typical). DC copper loss uses
`I_rms²·R_DC` (WORKER.md rule):

| MPN | DC copper @20 °C | Δ vs baseline | assumed 100 °C Δ* | AC winding @65 kHz | Core @65 kHz/bias |
| --- | ---: | ---: | ---: | --- | --- |
| 760800301 (base) | 4.500 W | — | — | **null** | **null** |
| 760801202 | 11.250 W | **+6.750 W** | +8.87 W | **null** | **null** |
| 760801403 | 7.875 W | +3.375 W | +4.44 W | **null** | **null** |
| 760801321 | 9.450 W | +4.950 W | +6.51 W | **null** | **null** |

\* **Assumed, not sourced:** 0.00393 /K copper coefficient applied to a 20 °C max DCR.

**AC winding loss and core loss are NOT published by any of the four datasheets**
(page 2 has only typical L-vs-current and typical ΔT-vs-current). Per the task rule,
core loss is **not** inferred from DCR. Therefore the full magnetic delta the decision
rule needs is `null` for every part — the DC-only delta is not the answer.

## 4. Case census

Source-only task: expected solver cases `not_applicable` (0 issued).
attempted 0 · valid 0 · failed 0 · unsupported 0 · unrun `not_applicable`.
Evidence records: 4 datasheet PDFs captured, 3 candidates + 1 baseline, 4 digitized curves,
3 source failures (all distributor/procurement, retained in `raw/capture_log.txt`).

## 5. Does the evidence support or refute the hypothesis?

- **A ~357.5 µH physical choke exists:** SUPPORTED for **760801202** (350.1 µH at bias).
- **Can it carry the envelope?** Peak/saturation: SUPPORTED (0.63× ISAT). Heating:
  **CONDITIONAL** — 15 A rms needs ≥4 m/s forced air (IR2 20 A); without a fan it is
  under-rated (IR 11.5 A). Assembly airflow is not supplied, so this is INDETERMINATE.
- **Is the increase < 19.3765 W?** **UNKNOWN.** DC copper is +6.75 W, leaving 12.63 W of
  headroom for the unpublished AC+core loss, but that term is not sourced for either the
  candidate or the baseline. The <19.38 W outcome is plausible but **not established**.

Evidence pointers: `inputs.json` (per-candidate record, `baseline_choke`, `source_failures`),
`result.json` (`magnetic_loss_ledger`, `constraint_findings`, `verdict_on_19_38_w`),
`raw/` (unmodified PDFs + headers + capture log + blocked-HTLM record),
`derived/l_vs_current_digitized.json` + `derived/digitize_l_curve.py` (L(bias) evidence).

## 6. Checker result and unresolved findings

Checker: `not_applicable` (source-only; no G0 checker). Unresolved:

1. **Baseline L at bias is 159.8 µH, not the 180 µH the frequency trade assumed.** The
   baseline's real ripple at its own L/129 kHz is ~4.74 A pk-pk, not 4.2043 A. The
   supplied envelope was used unchanged, but baseline-dependent terms carry this caveat.
2. **Printed ISAT contradicts the printed curve** for 760801403 (0.957) and 760801321
   (0.805). Both values are reported; 760801403 has no saturation margin at 23.27 A.
3. **Thermal rating is fan-conditional** for the two L-matched parts.
4. **Core + AC winding loss absent** for all four parts; the decision term is null.
5. **±20 % L tolerance**: a −20 % unit of 760801202 delivers ~280 µH at bias → ripple
   ~5.25 A pk-pk; ISAT for that unit is not established.
6. **Mass not published** for any part (null).

## 7. Recommended next observation

Request from Würth (or measure) the **core loss and AC winding resistance of 760801202
and 760800301 at 65 kHz across 0–23.3 A DC bias at 4.2043 A pk-pk ripple**. If the
manufacturer cannot supply it, measure both chokes on a B-H/calorimetric or
impedance-analyzer bench. Without it, the 65 kHz branch cannot be numerically ranked.
Corroborating secondary need: confirmation that the intended assembly provides ≥4 m/s
airflow at the choke.

## 8. Run record

Wall time ~10 min (16:16 → 16:26 UTC). Solver invocations 0 (budget 0).
Touched files: only `…/M065/attempt-001/**` (raw/, derived/, this report, `inputs.json`,
`result.json`, `manifest.json`). No commits, no stash. Deadline: met.

---

**Single most important missing curve:** the **core-loss (and AC-winding-resistance)
curve at 65 kHz vs DC bias, 0→23.3 A, at 4.2043 A pk-pk ripple**, for the candidate
760801202 and the retained baseline 760800301 — the one term that can consume the
19.3765 W switching saving and the only thing that turns the verdict from UNKNOWN.
