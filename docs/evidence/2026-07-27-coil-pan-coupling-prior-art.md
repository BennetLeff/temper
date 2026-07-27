# Coil-to-pan coupling and reflected resistance — literature synthesis

**Date:** 2026-07-27
**Method:** Web literature search + direct document fetch (WebSearch/WebFetch), no
simulation, no bench hardware. Every number below is either quoted from a document
actually fetched and read (URL given), or explicitly marked UNVERIFIED because the
source was paywalled/blocked and only a search-engine snippet or abstract could be
seen.
**Question:** can published `R_eff` (reflected pan resistance) and coupling `k`
values for domestic induction hobs resolve the coil spec (`TANK_COIL_SPECIFICATION.md`),
the OCP-01-vs-1800W conflict (`2026-07-26-ocp01-vs-full-power-current.md`), and the
bus-ripple transfer function (`BUS_CAPACITANCE_DERIVATION.md`)?

## Falsifier, stated before searching

*"This synthesis fails if the published values span more than an order of
magnitude, because then no design value can be chosen from literature alone."*

**Result: conditional fire.** Pooling every measured number found (0.055 Ω to
4.5 Ω) spans **~82×** — the falsifier fires outright if all sources are treated as
equivalent. But one of those numbers (APHO2025, see below) was taken on a
2 cm × 2 cm test coupon, not a full pan on a full coil — a different coupled area
by roughly two orders of magnitude, not a different *R_eff regime*. Restricting to
sources that characterize a full coil with a full pan/pot on top (Infineon
measured, IJCRT design-assumed), the spread is **2.0–4.5 Ω, ~2.25×** — inside one
order of magnitude, and the falsifier does **not** fire for that comparable set.
Both readings are reported below rather than silently picking one; which framing
you accept determines whether you read this as "literature settles it" or
"literature doesn't settle it." I lean toward the second, narrower framing, but
flag the judgment call explicitly.

## Values found, with source and conditions

| Value | Source | Measured or modeled | Conditions | Notes |
|---|---|---|---|---|
| `L_unloaded ≈ 48–50 µH` (flat vs. f) | Infineon AN235020 *EVAL_2KW_SiC_IH*, Fig. 9 | **Measured** (impedance sweep, coil alone) | 90–150 kHz sweep, 2 kW-class flat spiral coil, no pot | Fetched directly, full PDF read |
| `L_loaded (with pot) ≈ 19–20 µH`, declining slightly with f | same, Fig. 9 | **Measured** | Same coil, stainless stockpot placed on top per Fig. 8b | Pan not explicitly typed beyond "cookware suitable for induction cooking"; looks like a stainless stockpot in the photo, not cast iron |
| **Loaded/unloaded L ratio ≈ 0.39–0.40** | derived from the two rows above | Measured→derived | 90–150 kHz | The most directly transferable number found — a real full-size coil under a real pot |
| `R_unloaded (coil only) ≈ 0.2–0.4 Ω` | same, Fig. 9 | **Measured** | 90–150 kHz, no pot | Coil's own AC resistance |
| `R_with-pot ≈ 3.6–4.9 Ω` (rising with f) | same, Fig. 9 | **Measured** | 90–150 kHz, stainless pot on coil | Read off a chart, not a data table — treat as ±10% |
| **`R_eff (reflected) ≈ 3.3–4.5 Ω`** | derived: `R_with-pot − R_unloaded` | Measured→derived | 90–150 kHz | Frequency is 2.5–4.3× our 35 kHz target — not directly usable without a scaling assumption |
| Board tested to 2000 W, 320–340 V DC bus, `I_AC` = 0–20 A_rms rated | Infineon AN235020, Table 2/§4 | Measured (board spec) | 100–140 kHz switching | Full-power waveform capture exists (Fig. 6) but the OCR of that scope screenshot was not legible enough to extract a trustworthy I_tank number — not used |
| `R_eff ≈ 2 Ω` design input, giving `I_tank = 30 A_rms` at `P = 1.8 kW` | Indhuja & Christy Mano Raj, *"Design and Development of Voltage Fed Series Resonant Inverter for Induction Heating Applications,"* IJCRT vol. 10 iss. 6, June 2022, ijcrt.org/papers/IJCRT22A6083.pdf | **Assumed design value, then simulated in PLECS** — not measured from a real pan | 23 kHz, 1.8 kW target, half-bridge VFSRI | Self-consistent: 30² × 2 = 1800 W exactly. Text states "the reflected resistance of the induction heating coil is estimated up to 2Ω" — an estimate, not a citation to a measurement |
| `L = 25 µH` loaded, `6.3 µH` unloaded (iron workpiece) | same IJCRT paper, §3.2 | Modeled/simulated | 20–30 kHz target band | **Not comparable to our geometry** — this is a solenoid coil wound *around* a cylindrical iron rod workpiece (like a heating collar), so inserting the core *raises* L. Our design and Infineon's are flat pancake coils with a pan sitting *on top*, which *lowers* L. Included only as a caution against conflating topologies |
| `R_LOAD (SS410, ferromagnetic stainless, µr≈700) = 137.7 mΩ` | Gunawan, Kwee, Kwee, Yendi, Mudrick, *"Physics of Induction Cooking,"* Asian Physics Olympiad 2025 experimental solution, apho2025.sa | **Measured** (linear regression of P_tot vs. I_rms²) | 40 kHz, small tabletop demo coil, **2 cm × 2 cm × 0.7 mm test coupon**, I_rms 0.44–0.93 A | Real bench measurement, but on a test coupon covering a small fraction of coil area at milliwatt-scale current — not a full pan-on-coil system. Included for the qualitative finding below, not as an R_eff data point at hob scale |
| `R_LOAD (Aluminum) = 54.6 mΩ` | same | Measured | 40 kHz, same coupon geometry | SS410/Al ratio ≈ 2.5× — qualitatively confirms permeability-driven R_LOAD, consistent with pan_load.sub's own (unsourced) material ordering |
| Coil `L ≈ 48.7 µH` (avg of 4 measurements), `R_L ≈ 0.48–0.57 Ω` | same, §1.4, cross-checked against Würth Elektronik 760308101303 datasheet (`L=47 µH, R_L=0.46 Ω`) | Measured, cross-checked against datasheet | Coil alone, no pan, various C | Off-the-shelf commercial coil, coincidentally close in scale to Infineon's unloaded L |
| "Pan resistance... adding 20 Ω to 100 Ω in series would clearly change this substantially" | Bill Schweber / *Electronic Design*, "Induction Cooking: How Do Coil/Pan Characteristics Affect Heating Ability?" electronicdesign.com | Qualitative/illustrative, not a measured design value | Unstated frequency, generic discussion of a "standard 110 µH coil" | No k, no Q, no tank current given. Read the full article; this is the only numeric content it has, and it is a hypothetical range for illustrating damping, not a claimed real R_pan |
| `k = 0.2–0.6` (cast iron `0.4–0.6`, stainless `0.2–0.4`, aluminum `0.1–0.2`); `R_pan`: cast iron `5–15 Ω`, stainless `15–50 Ω`, aluminum `50–200 Ω`; "reflected resistance: 3–20 ohm... peak coil current 30–50 A for 2 kW" | **This repo's own** `simulation/models/pan_load.sub` header comments | **Unsourced** — no citation in the file | 30–40 kHz stated in comments | Not new evidence — this is the file the project already knows is wrong (implied Q 143). Listed here only so it isn't mistaken for an external source; it carries no citation and should not be treated as corroboration |

### What the numbers say about R_eff at 35 kHz specifically

No source found gives a **directly measured R_eff at 35 kHz for a full pan on a
full coil**. The two full-scale, full-coupling-area data points are:

- Infineon (measured, 90–150 kHz): R_eff ≈ 3.3–4.5 Ω
- IJCRT (assumed/simulated, 23 kHz): R_eff = 2 Ω

If R_eff falls with frequency roughly as √f (skin-effect argument, itself not
verified against either source — proximity effects and pan permeability
nonlinearity are not captured by this scaling), extrapolating Infineon's
90 kHz figure (~3.6 Ω) down to 35 kHz gives **R_eff ≈ 3.6 × √(35/90) ≈ 2.2 Ω**.
That lands within ~10% of the IJCRT design assumption at 23 kHz (2 Ω) — two
independent sources, one measured-then-scaled and one design-assumed, agreeing
to within the scaling method's own uncertainty. **This agreement is suggestive,
not proof** — I did not find a source that validates √f scaling for this specific
geometry, so treat the 35 kHz figure as an extrapolation with real uncertainty,
not a literature-established value.

## Recommended value, stated with its confidence level

**Literature does not settle a design value for `R_eff` to the precision needed
to specify coil `L`.** It does, however, shift the prior meaningfully:

- Two independent, differently-sourced data points (one measured hardware,
  scaled in frequency; one professional design assumption at a frequency and
  power close to this project's target) **both land at R_eff ≈ 2–2.2 Ω**, well
  above both the project's own `~1.12 Ω "typical"` figure and the `1.43 Ω`
  needed to clear OCP-01 at 1800 W.
- Neither is a direct 35 kHz measurement of a full pan. Neither carries pan
  material, diameter, or gap specifics matching this project's coil. Treat
  **R_eff ≈ 2 Ω as a plausible planning value for a ferromagnetic pan at ~35
  kHz**, not a specified one — it should be replaced by a bench measurement
  before it is used to size anything.
- **Coupling coefficient `k`:** no source found gives a directly measured,
  cited `k` for a full domestic coil-pan pair. This remains completely open —
  bench measurement is the only way to get it.
- **Loaded/unloaded L ratio ≈ 0.40** (Infineon, measured, though at 90–150 kHz)
  is the single most transferable number in this whole search, because it comes
  from an actual instrumented sweep of a real coil under a real pot in a
  geometry similar to this project's (flat coil, pan on top).

## OCP-01 vs. 1800 W — conflict assessment

The project's own analysis (`2026-07-26-ocp01-vs-full-power-current.md`) states
a "typical" 1.8 kW hob runs ~40 A RMS, implying `R_eff ≈ 1.12 Ω`, which **would**
trip OCP-01 (needs ≥1.43 Ω to avoid it) — that 40 A / 1.12 Ω figure is **not
itself cited to a source** in that document; it reads as the document's own
estimate.

Both literature data points assembled here (Infineon-derived ~2.2 Ω at 35 kHz,
IJCRT's 2 Ω design assumption at 23 kHz/1.8 kW) sit **above** 1.43 Ω, which if
representative would mean **OCP-01 does not conflict with reaching 1800 W** —
the opposite conclusion from the project's own "typical 40 A" assumption.

**This does not resolve the conflict — it inverts which side carries the
unsupported assumption.** The project's 1.12 Ω figure and this synthesis's 2–2.2
Ω figure are both estimates once you trace them to their root: one is an
uncited "typical," the other is a frequency-extrapolated measurement plus an
independent design assumption. Neither is a citation to a measured `R_eff` at
this project's actual frequency, pan, and coil geometry. **The honest statement
is: literature leans toward "no conflict," but not with enough rigor to close
the question — a bench measurement of the actual coil and a representative pan
set is still required**, and it is the same measurement the coil specification
is already blocked on.

## What should change in `TANK_COIL_SPECIFICATION.md` and `pan_load.sub` — described, not implemented

Per the task's constraint, nothing under `elec/`, `pcb/`, or `simulation/models/`
was touched. If a bench measurement is not available yet and the team wants to
move forward provisionally on literature alone, the changes would be:

1. **`pan_load.sub` (`PANLOAD_TRANSFORMER`, used by the sweep harness):** the
   defect identified in `TANK_COIL_SPECIFICATION.md` is `L2` (pan secondary
   inductance) defaulting to `1 µH`, which drives the reflected-R formula
   `(ωM)²·R_pan/(R_pan²+(ωL2)²)` down to ~0.1 Ω regardless of `R_pan`. Literature
   here doesn't give a value for `L2` directly, but the loaded/unloaded `L1`
   ratio (~0.40, Infineon) can be used to *back out* an implied `L2` and `k`
   pair, because `L_loaded = L1(1 − k²)` is the standard reflected-inductance
   relation this same file already uses in `PANLOAD_SIMPLE`. That inversion —
   not a fabricated `L2` — is the right next step, and it is exactly the
   calibration `TANK_COIL_SPECIFICATION.md` already called for.
2. **`R_PAN` presets:** would move from the current unsourced `8 Ω` (cast iron)
   / `25 Ω` (stainless) toward a value consistent with `R_eff ≈ 2 Ω` reflected
   (not `R_pan` — these are different quantities in the model's own T-topology;
   the model conflates "pan resistance" and "reflected resistance" in its
   comments, which is worth fixing in the same pass).
3. **`TANK_COIL_SPECIFICATION.md`:** could add a "literature bracket" section
   stating R_eff ≈ 2 Ω is a plausible planning number (with this document's
   caveats attached), while keeping the coil `L` **withheld** exactly as it is
   now — the falsifier here doesn't fire cleanly enough to lift that
   withholding, only to narrow the search space for the eventual bench
   measurement.

**None of this should be implemented without a bench measurement.** The
strongest finding in this whole search is the Infineon loaded/unloaded L ratio,
and even that was taken at 90–150 kHz on a coil/pot pair with unstated exact
diameter and gap — not this project's coil.

## UNVERIFIED — attempted, blocked, or abstract-only

| Source | Attempt | Result |
|---|---|---|
| Hsieh, Kuo, Chang, *"Study of half-bridge series-resonant induction cooker powered by line rectified DC with less filtering,"* IET Power Electronics 16, 1929–1942 (2023), doi 10.1049/pel2.12503 | WebFetch on ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/pel2.12503 | **HTTP 402 Payment Required — paywalled**, confirming the project's existing note that this source is inaccessible. A WebSearch snippet (not a direct read) states the paper's equivalent circuit uses `Req = Rp + Rs` with "Rp is very small, in the order of mΩ" — this is a search-engine paraphrase, not a quoted sentence from the paper, and is **not used** as evidence above |
| "Induction Coil Design Considerations for High-Frequency Domestic Cooktops," *Applied Sciences* 14(17):7996 (MDPI, 2024), doi 10.3390/app14177996 | WebFetch on doi.org (redirected to mdpi.com), and directly on mdpi.com and mdpi.com/.../pdf | **HTTP 403 Forbidden** on every attempt, including a plain `curl` from the sandbox (also 403) — MDPI is blocking automated fetches outright |
| "A Mutual-Inductance-Based Impedance Model of Induction Cooker for Efficiency Improvement," ResearchGate pub 337786272 | WebFetch | **HTTP 403 Forbidden** |
| "Multidisciplinary Review of Induction Stove Technology," *Sustainability* 12(10):206 (MDPI) | WebFetch | **HTTP 403 Forbidden** |
| "Performance evaluation of pan position methods in domestic induction cooktops," Springer, doi 10.1007/s00202-023-01837-z | WebFetch, redirected to Springer's IDP login wall | Not fetched — paywalled |
| ST AN4713, "Induction Cooking: IGBTs in Resonant Converters," st.com | WebFetch, three attempts | **Timed out (60 s) every time** — likely too large for the fetch tool; content not retrieved. Possible tank-current/Q data in this document remains unverified |
| ST AN2383 ("Kochfeld.pdf" mirror, mikrocontroller.net) | WebFetch | **HTTP 403 Forbidden** |
| CN113647196A (air-gap-adjusting induction cooker patent) | WebFetch, full read | Retrieved successfully but contains **no numeric k/gap/R values** — qualitative only ("closer gap → higher coupling"), despite a search snippet suggesting a 5.98% error figure existed somewhere in this patent family; that number was not found in the fetched text and is **not used** |
| Infineon AN235020 Fig. 6 scope capture (I_tank at full power) | Read directly from the fetched PDF | OCR of the oscilloscope screenshot was present but not confidently parseable into a trustworthy per-channel current reading — **not used** as a number, flagged rather than guessed |

## Bottom line for the caller

- **Usable values exist, but only two, and both need a frequency/assumption
  caveat attached**: Infineon's measured loaded/unloaded L ratio (≈0.40, most
  trustworthy number in this search) and an R_eff cluster around 2–2.2 Ω from
  one measured-and-scaled source plus one independently-assumed design source.
- **Range and spread:** 2.0–4.5 Ω across full-coil-scale sources (~2.25×, inside
  one order of magnitude); 0.055–4.5 Ω if the small-coupon APHO2025 data is
  pooled in without the geometric caveat (~82×, fires the stated falsifier).
  I judge the narrower framing correct and flag that judgment explicitly.
- **Recommended value:** R_eff ≈ 2 Ω as a *planning* number for a ferromagnetic
  pan near 35 kHz — not a specification-grade value.
- **OCP-01 vs. 1800 W:** literature leans toward **no conflict** (R_eff above
  the 1.43 Ω threshold), inverting the project's own "typical 1.12 Ω" assumption
  — but neither figure is a citation to a measurement at this project's actual
  frequency/coil/pan, so the conflict question is **not closed**.
- **What still needs a bench measurement:** `k` (no source found at all),
  `R_eff` at the project's actual 35 kHz/coil/pan combination (only bracketed,
  not measured), and confirmation that the √f scaling used to bridge 90–150 kHz
  down to 35 kHz is valid for this geometry.
