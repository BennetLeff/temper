# M-CORE attempt-001 — Can core + AC-winding loss be bounded tightly enough to settle the PFC frequency trade?

- **Task / attempt:** M-CORE / attempt-001 · **Kind:** source-then-compute
- **Campaign:** 2026-09-17-pfc-campaign · **Contract:** C1.1 (`0accd9bc…`, gate-checked)
- **Base revision:** `b1a9ad74de50f283762a488a28c19f764830cdee` (matches dispatch)
- **Deadline:** 2026-09-17T23:40:00Z · **Model/solver invocations:** 0 (dispatch)
- **Changed variable:** none physical — added core material/geometry fields for the
  three chokes and attempted a sourced bound on the unpublished core+AC term.

## 1. Verdict (one line)

**UNKNOWN: per-part core material identity AND core geometry (N, Ae, le, Ve) are
not published for 760801202 / 760801403 / 760800301, so neither the operating flux
swing nor the watt-level core loss can be established from primary sources.**

The DC-copper penalty does **not** kill the move (+6.75 W / +3.375 W against
19.3765 W / 11.8202 W savings), but the remaining core+AC term cannot be bounded
above (to prove survival) or below the headroom (to prove death).

## 2. Core identification (step 1)

All three are Würth **WE-TORPFC** toroidal PFC chokes, datasheet rev **001.001 /
2023-12-11**, 8 pages, PDFs hash-verified against the coordinator bundle.

| MPN | Size/type | L nom | R_DC max | I_SAT typ | Core material | Ae, le, Ve, AL, turns |
| --- | --- | --- | --- | --- | --- | --- |
| 760800301 (base) | T75 | 180 µH | 20 mΩ | 43 A | **not published** | **not published** |
| 760801202 (65 kHz) | T50 | 389 µH | 50 mΩ | 37 A | **not published** | **not published** |
| 760801403 (90 kHz) | T37 | 355 µH | 35 mΩ | 23 A | **not published** | **not published** |

**Material.** The datasheet does not name a core material; its only `Material`
fields (pp. 3–4) are packaging (`PET` tray, `Paper` paperboard). Würth's own
family presentation (`raw/we-torpfc-totem-pole-e-mobility.pdf`, p. 7, 27.06.2023)
says: *"Introducing WE-TORPFC (High Flux cores: Ni-Fe, Sendust: Al-Si-Fe)"* — the
series spans **two** materials with **no per-part mapping**. The part-number /
I_SAT covariance across the family (e.g. 760800202 I_SAT 19 A vs 760801202 I_SAT
37 A, same 389 µH / T50 / 50 mΩ) *suggests* two material grades, but no source
states which; that stays an inference, not an input.

**Geometry.** `Ae, le, Ve, AL, turns` are absent from the datasheet, the family
product page, the PFC-choke catalog table (its `n` column is `-` for WE-TORPFC),
and the LTspice/PSpice models (`raw/spice/WE-TORPFC.lib`: small-signal
`RP/CP/RS/L` only). Only **external package** dimensions are published
(T37 53×50, T50 72×45, T75 99×62 mm).

## 3. Material loss data sourced (step 2)

- `raw/we-torpfc-totem-pole-e-mobility.pdf` (2b0aaf9f…): family material statement above.
- `raw/mag-inc-high-flux-cores.html` (Magnetics, **core manufacturer**; HTML, clearly
  not a datasheet): High Flux = Ni‑Fe, **B_sat = 15 000 gauss = 1.5 T**, and core-loss
  density curves published. Used **only** as a saturation ceiling.
- `raw/material/magnetics-HF-toroid-{14,26,40,60}mu-core-loss-density.JPG`:
  the material's published core-loss-density curves — captured, but **not usable**
  without the per-part material and the core volume.

## 4. Flux-swing derivation and the bound (step 3)

For a uniform-flux toroid, `L(I)·I = N·Ae·B(I)`. Since `B ≤ B_sat`, the swing is

```
ΔB = L(I_pk)·ΔI/(N·Ae) ≤ ΔI·B_sat/I_pk = 4.2043·1.5/23.2719 = 0.271 T
```

— **L cancels**, so this is a genuine, geometry- and material-independent **upper**
bound on the peak-to-peak flux swing (conservative: at 23.27 A, 760801202 is well
below its 37 A I_SAT). **No lower bound** on ΔB exists (no published `N·Ae` upper bound).

Core loss is `P = Ve · p(ΔB, f)`. `Ve` is bracketed only extremely loosely:

| MPN | Ve lower (energy floor, B_sat 1.5 T, µ=14) | Ve upper (package bounding cylinder) | range |
| --- | ---: | ---: | ---: |
| 760801202 | 1.48 cm³ | 183 cm³ | **124×** |
| 760801403 | 1.03 cm³ | 110 cm³ | **107×** |

Even with the published loss-density curves, a ~100× volume span plus an unknown
per-part material makes `P_core` unbounded at the watt level. AC winding loss is
worse: no `R_ac/R_dc` at 65–90 kHz is published, and wire cross-section/turns are
not published, so no skin/proximity bound can be formed.

## 5. The explicit bound (step 4)

| Quantity | 760801202 | 760801403 |
| --- | ---: | ---: |
| Switching saving (maintained model) | 19.3765 W | 11.8202 W |
| DC copper @ 15 A rms (20 °C max) | 11.25 W | 7.875 W |
| ΔDC vs baseline | +6.75 W | +3.375 W |
| **Headroom for core+AC** | **12.6265 W** | **8.4452 W** |
| ΔB upper bound | 0.271 T | 0.271 T |
| **Core+AC upper bound** | **null** — not constructible | **null** — not constructible |
| Core+AC lower bound | 0 W (DC copper only) | 0 W (DC copper only) |

**Assumptions of the upper bound:** none can be stated because the bound cannot be
formed. The failure is not a conservative assumption; it is two missing primary
inputs (per-part material, core geometry). I did not substitute a guessed material,
a guessed fill factor, or a fit to the desired outcome. The zero-bias vs
worst-bias core-loss question is moot: the flux swing is upper-bounded but the
volume/material needed to turn it into watts is missing at *both* biases.

## 6. Why the trade is not decided (and what would decide it)

- Upper bound **< 12.63 W / 8.44 W** ⇒ move survives. **Not obtainable.**
- Lower bound **> 12.63 W / 8.44 W** ⇒ move dies. **Not obtainable** (lower bound is 0).
- So neither branch fires and the verdict is **UNKNOWN**.

The single missing observation: **Würth's core geometry + material for the three
parts, and the material's core-loss density (or a measured core/AC loss) at
65/90 kHz, 0–23.3 A bias, 4.2043 A pk-pk ripple.** With those, `P_core` is a
one-line calculation against the headroom above.

## 7. Case census, accounting, checker

- Source+arithmetic task: solver cases expected 0, attempted 0, valid 0, failed 0,
  unsupported 0, unrun 0. `numerical_status = NOT_RUN`; no G0 checker issued.
- Evidence: 3 datasheet PDFs (hash-verified), 1 manufacturer presentation, 2
  manufacturer web pages (HTML, labelled), 4 core-loss-curve images, SPICE model.
- Non-findings retained in `raw/capture_log.txt`: no per-part material, no geometry,
  no core-loss curve for the parts, no AC-resistance data; DigiKey attribute table
  unavailable. `checker_status = NOT_RUN`.
- Wall time ≈ 20 min; invocations 0; touched only `…/M-CORE/attempt-001/**`.
  No commits, no stash, deadline met.
- **Verdict: `UNKNOWN: per-part core material + core geometry (N, Ae, le, Ve)`.**

Pointers: `inputs.json` (core identification, material data, derivation),
`result.json` (ledger, `bound`, `verdict`),
`raw/compute_bound.py` + `raw/computed_bound.json` (arithmetic),
`raw/capture_log.txt` (every fetch and every non-finding).
