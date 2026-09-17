# K-SILICON attempt-001 — IPZ60R040C7 source capture and parameter extraction

- **Task ID:** K-SILICON · **Attempt:** attempt-001 · **Kind:** source-only
- **Campaign:** 2026-09-17-pfc-campaign · **Contract:** C1 (3bf1125f…)
- **Base revision:** `1e0d8132d66e16027bbe4f6b21844b2d208b87d2` (matches dispatch; `git rev-parse HEAD` confirmed)
- **Deadline:** 2026-09-17T22:30:00Z · **Solver invocations:** 0 (per dispatch)
- **Wall time:** ~4 min (21:20 → 21:24 UTC)

## Question

Can an exact Kelvin-source device plus its required drive/thermal assembly beat the
common reference? This attempt answers only the source half for the specified
candidate: capture the exact manufacturer datasheet for **IPZ60R040C7** and extract
the six parameters the maintained Rust model consumes.

## Exact part and document identity

| Field | Value |
| --- | --- |
| Manufacturer | Infineon Technologies AG |
| Order code (datasheet) | **IPZ60R040C7** |
| OPN (product page HTML) | IPZ60R040C7XKSA1 (ordering observation only) |
| Package | **PG-TO247-4** (TO247 4-pin) |
| Marking | 60C7040 |
| Kelvin source | **Yes** — separate Driver Source (pin 3) and Power Source (pin 2); Drain pin 1, Gate pin 4 |
| Datasheet | "600V CoolMOS C7 Power Transistor IPZ60R040C7", **Rev. 2.0 Final, 2015-05-08**, 15 pages |
| URL | `https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipz60r040c7-datasheet-en.pdf` |
| HTTP | 200, `application/pdf`, 1 553 797 bytes, `last-modified 2026-06-08` |
| Local bytes | `raw/IPZ60R040C7-infineon.pdf` |
| **SHA-256** | **`b1ea13f87f17a27336ea5a25ef01bad2d154c54140d8a4b1307e5f0289d6c089`** |
| File verification | starts `%PDF-1.7`; `file` = "PDF document, version 1.7"; `pdfinfo` parses 15 pages |

Capture succeeded on the first attempt against the primary Infineon CDN. No mirror
was needed, so `source_failures` is empty. One secondary HTML product-page fetch
(2 446 403 bytes) is retained at `raw/product-page-IPZ60R040C7.html` **for the
ordering code only** — it is HTML, not a datasheet, and carries no device performance.

## The six model parameters

Consumer: `pfc_drive_experiment::Device` at
`zapote/packages/zapote-harness/src/pfc_drive_experiment.rs:42` →
`zapote_erc::pfc_switching::Config`.

**All four gate-side values carry a gate bias of VGS = 0 to 10 V.**

| # | Parameter | Value (SI) | As published | Condition | Page / figure | Typ or guar. |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `qg_c` | 1.07e-7 C | 107 nC | VDD=400 V, ID=24.9 A, VGS=0→10 V | p.6 Table 6 (also p.2 Table 1) | typical |
| 2 | `qgd_c` | 3.6e-8 C | 36 nC | VDD=400 V, ID=24.9 A, VGS=0→10 V | p.6 Table 6 | typical |
| 3 | `plateau_v` | 5.0 V | 5.0 V | VDD=400 V, ID=24.9 A, VGS=0→10 V | p.6 Table 6 (curve p.10 Diag. 10) | typical |
| 4 | `intrinsic_gate_r_ohm` | 0.77 Ω | 0.77 Ω | f=1 MHz, open drain | p.6 Table 4 (RG) | typical |
| 5 | `eoss_j` | 1.26e-5 J | 12.6 µJ | VDS=400 V (Co(er)=158 pF, 0…400 V) | p.2 Table 1; p.11 Diag. 15 | typical |
| 6 | `rds_max_ohm` | 0.040 Ω | 40 mΩ | VGS=10 V, ID=24.9 A, **Tj=25 °C** | p.6 Table 4 Max; p.2 Table 1 | **guaranteed (Max)** |

`eoss_j` cross-check: Table 1 states 12.6 µJ @ 400 V and Diagram 15's curve ends at
≈12.6 µJ at 400 V; ½·Co(er)·400² = ½·158 pF·160 000 = 12.64 µJ. Consistent.

**All six were sourced. None is null.** No value was inferred (no peak-current
impedance, no Qg−Qgd substitution, no hot-RDS from a 25 °C typical).

## Gate-bias applicability (the campaign gate)

The campaign rule is that a number measured at −5/+18 V is **not** applicable at
0/+15 V. The symmetric caution applies here:

- `qg_c`, `qgd_c`, `plateau_v` are measured at **VGS = 0 to 10 V**.
- `rds_max_ohm` is measured at **VGS = 10 V**.
- The datasheet publishes **no** gate-charge, plateau, switching-time or switching-energy
  data at 0/+15 V or at −5/+18 V.

Therefore these values are directly applicable only to a 0/+10 V (or lower) drive.
A 0/+15 V campaign case would draw more charge than 107 nC, and the increment is
**not quantified by this document** — it must not be inferred. `eoss_j` depends on
VDS only (VGS=0), so it is gate-bias independent.

## Device ratings (for completeness)

- **VDS:** 600 V (V(BR)DSS min, VGS=0, ID=1 mA, p.6 Table 4). Table 1 also lists
  "VDS @ Tj,max = 650 V" (breakdown at max junction temperature).
- **ID:** 50 A @ TC=25 °C, 32 A @ TC=100 °C (p.4 Table 2); 73 A continuous @ Tj<150 °C
  (p.2 Table 1); ID,pulse 211 A (p.4 Table 2).
- VGS static ±20 V, dynamic ±30 V (AC f>1 Hz); Ptot 227 W @ TC=25 °C; Tj −55…150 °C;
  RthJC 0.55 K/W.

## What is missing and why

1. **0/+15 V (and −5/+18 V) gate-charge / plateau data** — not in this datasheet.
   The chosen drive bias cannot be populated from this source alone.
2. **Switching energy (Eon/Eoff)** — this datasheet has no inductive-load switching-energy
   curves at all (only switching times, Tables 5/9, and a gate-charge curve, Diagram 10).
   Switching loss for IPZ60R040C7 is therefore unsourced by this document.
3. **Hot guaranteed RDS(on)** — only typical 0.077 Ω at Tj=150 °C; no maximum and no
   stated 25→150 °C guarantee factor.
4. **Driver and thermal assembly** — outside this source-only task; not captured here.

## Recommended next observation

Obtain the exact gate driver's output resistance and the assembled gate-loop
impedance at the campaign's actual bias, then either capture a gate-bias-matched
(0/+15 V) switching-energy source for this part, or explicitly label the 0/+10 V
extracted charges as a non-applicable-bias anchor. Until a gate-bias-matched
switching-energy source exists, IPZ60R040C7 cannot be numerically ranked against
the reference — a Qgd-only comparison is explicitly excluded by the task's stop rule.

## Evidence pointers

- `inputs.json` — part/document identity, ratings, six parameters, applicability verdict.
- `result.json` — status axes (`FINISHED` / `NOT_REVIEWED` / `NOT_RUN` / `INDETERMINATE` /
  `INCOMPLETE` / `NOT_PERFORMED`), parameter block, constraint findings.
- `raw/` — unmodified captured bytes (PDF + headers + product-page HTML).
- `derived/` — pdftotext layout and page renders (pages 2, 6, 11).
- `manifest.json` — SHA-256 of every produced file except itself.
