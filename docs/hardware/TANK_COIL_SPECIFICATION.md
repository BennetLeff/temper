# Tank Coil — Specification and Incoming Acceptance Test

**Status:** ISSUED 2026-07-29. Supersedes the 2026-07-26 attempt, which
withheld a value; that attempt and why it failed are preserved in §7.
Acceptance threshold corrected 2026-07-29 (later the same day) to also
worst-case the tank capacitor's own tolerance -- see the note at §2 and
`docs/evidence/2026-07-29-pll-floor-cap-tolerance.md`.

**What this document is.** A coil specification a magnetics house can quote
against, plus the incoming test that decides whether a delivered coil is
usable. It is deliberately **not a part number**: no orderable coil in this
class publishes an inductance (§6), so the deliverable is the spec and the
test, not a purchase order line.

**Where it is enforced.** `elec/src/modules.ato`'s `ResonantTank.inductor_conn`
declares `88uH +/- 10%`; `elec/src/main.ato`'s `l_tank_assumed` mirrors it;
`scripts/check_pll_range_consistency.py` check 7 fails the build if the two
disagree, and check 5 derives the PLL frequency floor from it. Check 8
derives the acceptance threshold below (§2) from that same floor and fails
the build if this document's stated number ever drifts from it.

---

## 1. Specification — as a supplier would receive it

**Part:** Resonant tank coil, flat spiral, ferrite-backed, for a 1800 W
domestic induction hob operating at 42–50 kHz.

| # | Parameter | Requirement | How it is verified |
|---|---|---|---|
| 1 | **Inductance, unloaded** | **88 µH ±10 %** (79.2 – 96.8 µH) | LCR bridge, **40 kHz**, coil free in air, no vessel, ≥100 mm from any ferrous surface |
| 2 | **Measurement frequency** | **40 kHz**, and inductance shall be **flat within ±3 % over 20–50 kHz** | Sweep 20/30/40/50 kHz on the same bridge |
| 3 | **Loaded inductance — the binding criterion** | **L_loaded ≥ 53.00 µH** at 40 kHz with the reference pan of §2 (target 59.8 µH) | §2 |
| 3b | **Loaded/unloaded ratio — coupling screen** | **L_loaded ≥ 0.60 × L_unloaded** at 40 kHz, same measurement | §2 |
| 4 | **DC resistance** | **≤ 0.12 Ω** (target 0.10 Ω) | 4-wire DC milliohmmeter at 25 °C |
| 5 | **AC resistance, unloaded** | **≤ 0.40 Ω at 40 kHz** | Same LCR sweep as #1, series-R reading |
| 6 | **Continuous current** | **25 A rms at 40 kHz**, ΔT ≤ 60 K in still air at 40 °C ambient | Thermal soak, §3 |
| 7 | **Peak current, non-repetitive** | ≥ 40 A peak without saturation or measurable L shift | L measured before/after a 40 A pulse |
| 8 | **Conductor** | Litz, stranded for 40 kHz (skin depth in Cu at 40 kHz ≈ 0.33 mm, so individual strands ≤ 0.2 mm / ≥ AWG 32) | Declared by supplier + strand count on the CoC |
| 9 | **Outer diameter** | ≤ 200 mm (mechanical ceiling, `docs/COIL_BRACKET_DESIGN.md`) | Calipers |
| 10 | **Terminations** | Two leads, tinned, for 2.5 mm through-hole pads (`LitzPad_15A`), ≥ 150 mm free length | Visual |
| 11 | **Temperature class** | Insulation and former rated ≥ 180 °C continuous | Datasheet / CoC |
| 12 | **Ferrite backing** | Radial bars or a plate, sufficient that #3 is met | Implied by #3, not specified separately |

**Certificate of conformance shall report, per unit:** L_unloaded @ 40 kHz,
L_loaded @ 40 kHz with the supplier's own ferromagnetic reference pan,
their ratio, R_dc, and R_ac @ 40 kHz.

### Why 88 µH, in one line

Because at the committed 300 nF nominal tank capacitance it puts the
**loaded** resonance at 37.56 kHz, and the whole frequency plan
(`f_switching` = 47 kHz at ratio 1.25, `PLL_MIN_FREQ_HZ` = 43 kHz) is built
on that. The provenance of the number itself is §5.

---

## 2. THE ACCEPTANCE TEST — measure `L_loaded`

**This is the deliverable.** Requirements #3 and #3b are the only
parameters on the list that decide whether the converter works, and **no
vendor in this class states either**, so they have to be measured on
receipt.

### Why a loaded measurement and not an inductance check

Only the **loaded** inductance resonates with the tank capacitor. A coil
with a perfect 88.0 µH unloaded reading and weak pan coupling is a
**failed** coil: it resonates too high, and `f_switching` = 47 kHz lands
too close above resonance, in the 3–7 kW / OCP-tripping band. Conversely a
coil 10 % low on unloaded inductance with strong coupling is fine.
Unloaded inductance alone is not an acceptance criterion; the product is.

Full argument: `docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`.

### Why the criterion is absolute, not only a ratio

**The ratio test alone is not sufficient, and this is worth showing.**
`L_loaded ≥ 0.60 × L_unloaded` is the acceptance criterion
`docs/evidence/2026-07-28-coil-selection-research.md` §5.1 recommends. Run
against a coil that is simultaneously at the **bottom** of requirement #1:

```
L_unloaded = 79.2 µH  (−10 %, in spec)
ratio      = 0.60     (passes the ratio screen)
L_loaded   = 47.52 µH
f_res      = 42 152 Hz  (at nominal 300 nF C)
required PLL floor = 1.05 × 42 152 = 44 260 Hz
PLL_MIN_FREQ_HZ    = 43 000 Hz          ← BELOW resonance
```

That coil passes both #1 and a bare 0.60 ratio screen and still puts a
hard-switching regime inside the firmware's declared legal frequency
range — the exact defect `docs/evidence/2026-07-29-pll-floor-above-resonance.md`
was written to close. The two screens are individually satisfiable and
jointly insufficient because they multiply.

The criterion that is neither is **absolute loaded inductance**, and it
falls straight out of the committed constants -- now worst-casing BOTH
tank components, not just the coil (corrected 2026-07-29, same day as
issue, see the note below the table):

```
PLL_MIN_FREQ_HZ / ZVS_MARGIN_MIN = 43 000 / 1.05 = 40 952.4 Hz
                                                   (highest loaded
                                                    resonance the floor
                                                    still guards)
C_worst = c_tank_total × (1 − c_tank_tolerance) = 300 nF × 0.95 = 285 nF
L_loaded_min = 1 / ((2π × 40 952.4 Hz)² × 285 nF) = 53.00 µH
```

`c_tank_tolerance = 0.05` is decoded from `c_tank1`/`c_tank2`'s MPN,
`FKP1T031507G00JSSD` (WIMA FKP 1), against WIMA's own ordering table:
the trailing `00JSSD` reads as `00` (2-pin) + `J` (**5 % tolerance**) +
`S` (bulk) + `SD` (6-2 mm pin length) -- confirmed against both the
Mouser-hosted (rev 01.19) and current WIMA-hosted (rev 03.26) FKP 1
datasheets, which both list this exact part on their 1600 VDC / 0.15 µF
row as `FKP1T031507G______` and both give the tolerance-letter table
20 %=M, 10 %=K, 5 %=J. (The `G` earlier in the base code is NOT the
tolerance letter -- it is part of the fixed size-variant code, confirmed
by the datasheet printing that row's base code as `FKP1T031507G______`,
i.e. the six trailing underscores -- not the `G` -- are the completion
box.) `docs/hardware/BOM.md` §1.4 independently decoded the same MPN's
tolerance character the same way.

**`L_loaded ≥ 53.00 µH` is requirement #3.** Requirement #3b is retained
as a coupling-quality screen — a coil that reaches 53.00 µH only because
its unloaded inductance is at the top of tolerance has poor coupling and
will behave differently on a different pan — but #3 is the one that binds.
This value is **machine-derived**: `scripts/check_pll_range_consistency.py`
check 8 computes it from `PLL_MIN_FREQ_HZ`, `ZVS_MARGIN_MIN`,
`c_tank_total` and `c_tank_tolerance` and fails the build if the number
above ever drifts from what the gate derives -- do not hand-edit it
without re-running that gate.

For reference, where the thresholds sit (rows other than the acceptance
floor use **nominal** 300 nF C, for illustration of a real coil's own
resonance; the acceptance floor row is the one worst-cased against BOTH
tank components, since that is the number that must guard every unit):

| L_loaded | f_res,loaded | f_sw/f_res at 47 kHz | Verdict |
|---|---|---|---|
| 65.8 µH (+10 % L, nominal ratio) | 35.8 kHz | 1.31 | Top of the design band |
| **59.84 µH** (nominal) | **37.56 kHz** | **1.25** | **Target** |
| 53.86 µH (−10 % L, nominal ratio) | 39.60 kHz | 1.19 | Bottom of the design band; derived floor 41 575 Hz at nominal C, 42 655 Hz at worst-case C |
| **53.00 µH** | **40.95 kHz** | **1.148** | **ACCEPTANCE FLOOR** — derived floor = 43 000 Hz exactly (worst-case 285 nF C) |
| 47.52 µH (−10 % L, ratio 0.60) | 42.15 kHz | 1.115 | **REJECT** — resonance above PLL_MIN_FREQ_HZ |
| 42.14 µH | 44.76 kHz | **1.05** | ZVS cliff at the committed f_switching |

### Procedure

**Equipment:** LCR meter capable of 40 kHz with ≥ 1 % accuracy at 50 µH
(e.g. a 4-wire bench bridge); reference pan per below; a non-ferrous
spacer of the production coil-to-pan gap.

**Reference pan** — fix this once and keep the same physical pan for all
incoming inspection; the number is only reproducible against a fixed
workpiece:

- Flat-bottomed **ferromagnetic** vessel (cast iron or magnetic stainless;
  verify with a magnet), **180 – 220 mm** base diameter, base thickness
  ≥ 3 mm, flat to within 0.5 mm.
- Record its make/model in the incoming-inspection record. A different pan
  gives a different ratio and the 0.60 threshold does not transfer.

**Steps**

1. Coil free in air, ≥ 100 mm from any ferrous object and off any metal
   bench. Measure **L_unloaded at 40 kHz**, 1 V drive or less. Record.
2. Confirm requirement #1: L_unloaded within 79.2 – 96.8 µH. If it fails
   here, stop — reject.
3. Place the coil in its production bracket, or on the same spacer stack,
   so the **coil-to-pan-base gap equals the production gap** (currently
   set by `docs/COIL_BRACKET_DESIGN.md`; record the value used).
4. Centre the reference pan on the coil, empty and at room temperature.
5. Measure **L_loaded at 40 kHz**, same drive level. Record.
6. **ACCEPT if `L_loaded ≥ 53.00 µH`. Reject otherwise.** Target 59.8 µH;
   the design band is 53.9 – 65.8 µH.
7. Compute `ratio = L_loaded / L_unloaded` and record it. **`ratio ≥ 0.60`
   is a secondary screen.** A part that passes step 6 but fails here has
   weak coupling masked by high unloaded inductance and will not repeat on
   a different pan — escalate rather than accept.

No waiver on step 6 without re-deriving `l_pan_loaded_ratio`,
`f_switching` and `PLL_MIN_FREQ_HZ`, and re-running
`scripts/check_pll_range_consistency.py`.

### Where the ratio threshold sits

| | Value | Source |
|---|---|---|
| Ratio the design is specified at | **0.68** | Infineon EVAL-IHW25N140R5L Fig. 16, 40 kHz (§5) |
| Ratio at 30 kHz / 50 kHz, same chart | 0.71 / 0.66 | same |
| Secondary screen | **0.60** | this document |
| Minimum ratio at **nominal** 88 µH that still meets `L_loaded ≥ 53.00 µH` | **0.602** | derived above |
| Minimum ratio at **−10 %** (79.2 µH) that still meets it | **0.669** | derived above |
| Ratio at which `f_sw` = 47 kHz reaches the 1.05 ZVS cliff, at 88 µH | **0.479** | `L_loaded = 42.14 µH` |

The near-exact agreement between the 0.60 screen and the 0.602 required at
nominal L is a **coincidence**, not a design: it is why the ratio screen
looks adequate at first glance and is not.

---

## 3. Thermal soak (requirement #6)

Not a go/no-go for first articles, but it must be run before the coil is
released for production.

At the 1800 W operating point the tank carries **20.7 A rms** by this
repo's ngspice harness and **22.5 A rms** by an independent first-harmonic
solve. With R_ac ≈ 0.34–0.40 Ω at 40 kHz, the coil dissipates **≈150–200 W
in its own copper** — comparable to a soldering iron, inside a sealed
appliance, under a hot pan.

Drive the coil at 25 A rms / 40 kHz with the reference pan present, in
40 °C still air, until temperature is stable (≥ 30 min). Record the
hottest point on the winding. **ΔT ≤ 60 K** (i.e. ≤ 100 °C absolute, well
inside the 180 °C insulation class, leaving margin for the pan's own
radiated heat which this bench test does not reproduce).

**UNVERIFIED:** no thermal design for this dissipation exists yet. This
test may fail, and the remedy would be more copper, more strands, or
forced air — all of which change L and send the part back through §2.

---

## 4. What this specification does to the rest of the design

| Quantity | Value | Moved by this spec? |
|---|---|---|
| `C_TANK` (`c_tank1` + `c_tank2`) | 300 nF | No |
| `f_switching` | 47 kHz | No |
| `PLL_MIN_FREQ_HZ` / `PLL_MAX_FREQ_HZ` | 42 / 50 kHz | No |
| `l_tank_assumed` | 150 µH → **88 µH** | Yes |
| `l_pan_loaded_ratio` | 0.399 → **0.68** | Yes, as a matched pair |
| **`L_loaded`** | 59.85 → **59.84 µH** | **−0.02 %** |
| `f_res,loaded` (nominal) | 37 560 → **37 563 Hz** | **+0.008 %** |
| Derived PLL floor (gate check 5) | 41 571 → **41 575 Hz** | **+3.5 Hz** |
| `f_resonant_nominal` (UNLOADED) | 25 kHz → **31 kHz** | Yes — it is now derivable |

The arithmetic, in full:

```
150 µH × 0.399 = 59.850 µH  →  f_res = 1/(2π√(59.850µH × 300nF)) = 37 560.2 Hz
 88 µH × 0.68  = 59.840 µH  →  f_res = 1/(2π√(59.840µH × 300nF)) = 37 563.3 Hz
```

The two factors are 1.7× apart in opposite directions and their product
agrees to 0.02 %. **Neither may be changed without the other.**

---

## 5. Provenance of 88 µH and 0.68

Both are read off **one chart**: Figure 16 of the **Infineon
EVAL-IHW25N140R5L user guide, rev 1.0, 2023-08-04**
(`https://docs.rs-online.com/e357/A700000012089135.pdf`), which plots the
inductance and resistance of the 2 kW cooking coil shipped with that kit,
with and without a vessel, over **0–50 kHz**.

| Reading | Value |
|---|---|
| L, no vessel | ≈ 90 µH at DC, **≈ 87 µH flat 15–50 kHz** |
| L, with vessel, at 40 kHz | **≈ 60 µH** |
| Ratio at 40 kHz | **0.68** (0.71 at 30 kHz, 0.66 at 50 kHz) |
| R, no vessel | 0.10 Ω at DC, **≈ 0.34 Ω at 40 kHz** |
| R, with vessel, at 40 kHz | ≈ 3.25 Ω |

**What makes this source usable where others were not:** it is a cooktop
coil of the right power class **characterised in this design's own
frequency band**. The 47–50 µH figure this project previously treated as
"what real coils measure" came from a 90–150 kHz characterisation
(Infineon AN235020) plus a **20 W Qi wireless-charging receiver coil**
(Würth 760308101303, Ø26.3 mm, 1.5 A) plus a bench coil validated against
that Qi part. See `docs/evidence/2026-07-28-coil-selection-research.md`
§2.4.

**What is UNVERIFIED about it, stated plainly:**

- It is a **chart reading** (±5 % on the read) of a coil with **no
  published part number, dimensions, turn count, litz spec, current
  rating or temperature rating**. Infineon characterised it; nobody
  specified it.
- The 0.68 was measured on **Infineon's unnamed cookware**, not on this
  project's pan set. It is the single number this specification most
  depends on — hence §2 existing at all.
- Part-to-part spread for any coil wound to this spec is **unknown**. The
  ±10 % in requirement #1 is a specification we impose, not a measured
  distribution.

---

## 6. Sourcing — why there is no part number here

Searched 2026-07-28 (`docs/evidence/2026-07-28-coil-selection-research.md`
§2), with the primary sources fetched rather than searched:

| Channel | Finding |
|---|---|
| **Infineon EVAL-IHW25N140R5L** (`EVALIHW25N140R5LTOBO1`, DigiKey `448-EVALIHW25N140R5LTOBO1-ND`) | The only 2 kW cooking coil found with manufacturer-published L and R across 20–50 kHz. Ships **as a kit item**; the coil has no MPN of its own and Infineon does not say whether it is sold separately. 1 in stock, 99-week lead time at time of fetch. **Buy one to measure against**, ~€122. |
| **Infineon EVAL_2KW_SiC_IH** (AN235020) | Real cooktop coil, ~48 µH — but characterised **only at 90–150 kHz**, for a 100–140 kHz inverter. Not this design's band, and unrescuable at this design's frequency by any capacitor (research §4.3). |
| **OEM appliance spares**, e.g. Electrolux/Simpson `4055092979` (180 mm, A$98, in stock) | Real, cheap, orderable, and **electrically unspecified**. Buy and measure; cannot design against. |
| **Würth 760308101303** | **Not a candidate.** Qi wireless-power receiver coil, Ø26.3 mm, 1.5 A, 20 W. |
| **Custom-wind (AliExpress/Alibaba/Zhongshan/Guangzhou, MOQ 100–500)** | Hundreds of "2000 W induction coil" listings, **none publishing an inductance**. This is the eventual production route, and it means specifying to a winder and measuring what arrives — which is what §1 and §2 are for. |

**No MPN is asserted in this document, in `elec/src`, or in the BOM.**
`inductor_conn.mpn` remains `"CUSTOM_LITZ_COIL"`.

---

## 7. The 2026-07-26 attempt, and why it withheld a value

Preserved because the reason it failed is still true of the simulation
model, and anyone re-running that harness will hit it again.

`simulation/harness/run_tank_coil_sweep.py` swept L against delivered
power. Every ZVS-holding point reported 1305 W maximum at L = 70 µH and
**109.5 A of tank current** — an effective series resistance of 0.109 Ω
and an implied tank **Q of 143**, against ~14 for a real hob. The pan
model absorbs roughly 10× too little, so the **power axis of that sweep is
not usable**, and "1800 W is unreachable at every L" was an artefact.

What survived from it, and is still load-bearing:

1. **ZVS is a threshold, not a gradient**: it holds for
   `f_sw ≥ ~1.02 × f_res,loaded` and collapses below. Design margin is
   **1.05**, which is the constant `ZVS_MARGIN_MIN` in
   `scripts/check_pll_range_consistency.py`.
2. **Whatever value is chosen must be written down.** That was named as
   "the actual defect". It is now written down, in two files, with a gate
   between them.

The 2026-07-26 document also asked whether full-power tank current clears
OCP-01's 50.1 A peak trip. It does, but see §8.

---

## 8. Open items this specification does NOT close

0. **CLOSED 2026-07-29 (partially) — the acceptance minimum is now
   machine-derived and cross-checked, but the coupling ratio is still
   NOT.** As originally written, this item flagged two separate gaps: (a)
   the acceptance threshold in §2/§1 was hand-derived once and nothing
   kept it in sync with the gate, and (b) the gate treats
   `l_pan_loaded_ratio` as exact, with no declared tolerance on it. (a) is
   now closed: `scripts/check_pll_range_consistency.py` check 8 computes
   `L_loaded ≥ 53.00 µH` itself (from `PLL_MIN_FREQ_HZ`, `ZVS_MARGIN_MIN`,
   `c_tank_total` and the newly-declared `c_tank_tolerance`) and fails the
   build if the number stated above ever disagrees — the threshold now
   moves automatically whenever L, C, either tolerance, or
   `PLL_MIN_FREQ_HZ` moves, rather than living only in this document's
   prose. (b) remains open: there is still no declared tolerance on
   `l_pan_loaded_ratio`, so the §2 arithmetic — that an in-tolerance coil
   with a merely-adequate ratio can resonate above `PLL_MIN_FREQ_HZ` — is
   enforced by this document and by incoming inspection, **not by CI**.
   Closing that would mean declaring a ratio tolerance in `main.ato` and
   widening check 5's worst-case derivation to use it; not done here
   rather than done with an invented number.
1. **Two declared ratings are exceeded by the tank current at 1800 W, and
   both were exceeded before this change.** `LitzPad_15A` declares
   `current_rating = 15A` (`elec/src/footprints.ato`) and
   `Top.i_peak_max` / `HighVoltageConstraints.i_max` are 25 A, while the
   1800 W tank current is **20.7–22.5 A rms / 28.7–31.9 A peak**. The
   coil's own `current_rating` is declared at 25 A rms on a thermal
   basis. Nothing here raises a rating to fit — that requires a
   pad/geometry and IGBT-SOA argument, not an edit.
2. **The pan-coupling model in `simulation/harness/run_zvs_sweep.py`**
   still uses `K = 0.79`, solved against the 90–150 kHz measurement. It
   now disagrees with `main.ato`'s in-band 0.68. Re-solving it would
   restate every committed ZVS and OCP number and is deliberately not
   done on the strength of a chart reading.
3. **No bench measurement of this project's own coil and pan exists.**
   That single measurement would replace §5's chart readings and §2's
   threshold with real numbers, and is the highest-leverage physical
   experiment this project has.
4. **Thermal design for ~150–200 W of coil copper loss** does not exist
   (§3).

All simulation models remain `calibrated: false`; the IGBT model is
behavioural with fixed capacitances.
