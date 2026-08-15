<!-- provenance: own worktree `temper-tank-coil-copper-mass`, branch `analysis/tank-coil-copper-mass-bound`,
branched from `analysis/tank-fault-interrupting-device` at commit 6ae2d668c (no `origin/analysis/tank-fault-
interrupting-device` ref exists; the local branch is PR #1120's branch per that document's own provenance
comment). `git status --porcelain` clean, `git grep -l "^<<<<<<< "` empty, checked before this document was
written. No file under `elec/src/**` or `pcb/temper.kicad_pcb` was opened for writing at any point in this
session. `ngspice` not invoked; every number below is a hand/script derivation from repo-sourced inputs, not
a SPICE result. This document does not modify the source tree it derives from. -->

# A conservative lower bound on the tank coil's copper mass, derived from its own specification — and what it means for the coil's fault I²t withstand

**Scope.** `docs/evidence/2026-08-13-tank-fault-interrupting-device-specification.md` (this branch's own
prior document) left the tank coil's I²t withstand as the one genuinely open item in its Blocker B: "no
sourced mass, turn count, or manufacturer surge/pulse-current rating... a defensible mass bound genuinely
cannot be built from what is published." That conclusion was reached by looking for a *directly stated*
dimension analogous to CT1's land-pattern spacing — and correctly found none. This document takes a
different approach: it treats the coil's own specification (`docs/hardware/TANK_COIL_SPECIFICATION.md`) as
an **over-determined system** — inductance, DC resistance, and an outer-diameter ceiling are all stated
simultaneously for the same physical winding — and solves that system for the winding geometry a real coil
would need to satisfy all three at once. That is a real, if indirect, geometric constraint the prior
document's search for an explicit dimension did not use.

---

## Verdict, up front

**The tank coil is comfortably clear of its own adiabatic I²t withstand under this fault — not marginal,
not the binding element.** Using a conservative lower bound on copper mass (≈126–165 g, derived below,
narrower and independently cross-validated by two of the coil's own spec numbers at once) and the fault's
own dissipated-energy figures from the prior document (14.7–25.5 J landing in the coil through the fault's
dominant 0.69–1 ms window), the coil's temperature rises by **under 0.6 K**, adiabatically, in the worst
case — against roughly 80–155 K of headroom to its Class H (180 °C) insulation ceiling. Converting that
headroom to an I²t figure gives a withstand of **≈38,500–75,000 A²·s**, against a fault I²t of **147–255
A²·s** — a margin of **≈150–510×** depending on starting temperature and time horizon, even before crediting
the (much larger) mass bound Route A independently produces.

**This bounds the coil only.** The bus capacitors — the other ~29–32% of the fault's energy — are not
addressed here; the prior document's finding that no defensible mass/withstand bound exists for them (a
different physics problem: internal foil/electrolyte heating, not a lumped can mass) stands untouched.
Blocker B is now closed for three of the four loop elements (CT1, PCB copper, tank coil) and remains open
only for the bus capacitors.

---

## 1. What this document inherits, re-verified

| Quantity | Value | Source | Re-verified how |
|---|---|---|---|
| Unloaded inductance | 88 µH (design/nominal; ±10%, i.e. 79.2–96.8 µH) | `docs/hardware/TANK_COIL_SPECIFICATION.md` req #1 | Read directly |
| DC resistance | 0.10 Ω (target; ≤0.12 Ω spec ceiling), measured at 25 °C | Same doc, req #4 | Read directly; matches `elec/src/modules.ato:621` `inductor_conn.dcr = 0.1ohm`, which is the exact value the fault-loop model (§4.1 of the interrupting-device spec) already uses for the coil's `R` |
| Continuous current rating | 25 A rms | Same doc, req #6; `elec/src/modules.ato:620` `inductor_conn.current_rating = 25A` | Read directly |
| Outer-diameter ceiling | ≤ 200 mm | Same doc, req #9, sourced to `docs/COIL_BRACKET_DESIGN.md` | Read `COIL_BRACKET_DESIGN.md` directly: "Coil Size: Supports OD up to 200mm" (§2), same figure in the stack-up cutout diagram (§3.2) |
| Construction | "Flat spiral, ferrite-backed" | Same doc, §1 title line | Read directly — this is the basis for treating the winding as a single-layer planar spiral below, not an assumption of convenience |
| Insulation class | Class H, ≥180 °C continuous | Same doc, req #11 | Read directly; matches the interrupting-device document's independent read of the same line |
| Copper resistivity | 1.68×10⁻⁸ Ω·m (this repo's own standard value, stated without an explicit reference temperature — treated as 20 °C per the usual textbook convention for that figure) | `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` (used identically in three skin-depth/resistance calculations there) | Read directly, `grep`-confirmed as the only resistivity figure this repo uses anywhere |
| Copper density, specific heat | 8960 kg/m³, 385 J/(kg·K) | `docs/evidence/2026-08-13-tank-fault-interrupting-device-specification.md` §3.2 ("standard tabulated material constants... not a datasheet or standards figure being invented") | Reused identically here, for the same reason |
| Fault energy landing in the coil | 14.73 J through t_peak (694 µs); 25.49 J through 1 ms | Same doc, §4.1 per-element energy-breakdown table (installed 3600 µF case) | Read directly; this is `R_coil × I²t_total(t)` at the coil's 100.0 mΩ / 69.93% share of `R_total`, itself independently re-derived in that document's §1.1 |
| Fault I²t (whole loop, for comparison) | 147.32 A²·s at t_peak; 254.94 A²·s at 1 ms | Same doc, §1.1 | Read directly |

**A repo-wide check for a wire/winding current-density design rule turned up nothing**: `grep -rn "A/mm\|current density"` across `docs/` and `elec/` returns only PCB-trace-current-density references (`TRACE_WIDTH_CALCULATIONS.md`, `METHODOLOGY.md`), none for a wound conductor. Route A below therefore imports a **standard external engineering rule of thumb** for that one number, explicitly labeled as such — it is the one input in this document that is not sourced from this repository.

---

## 2. Route A — from DCR and an assumed current-density range

`R = ρL/A`. DCR (0.10 Ω, §1 above) and copper resistivity fix the ratio `L_conductor/A_conductor`, not
either quantity alone (this is exactly the gap the prior document named — DCR alone underdetermines mass).
To close it, Route A borrows a **current-density assumption**, since the spec fixes a continuous current
rating (25 A rms) but not a wire gauge or strand count (task instruction: do not invent the litz
construction — bound it instead).

**Resistivity temperature.** DCR is specified as measured "4-wire DC milliohmmeter at 25 °C" (req #4). Using
`ρ_Cu` at that same 25 °C (not the bare 20 °C textbook reference point, and not an assumed hot operating
temperature) is the physically consistent choice: `R = ρ(T)·L/A` only holds at the temperature the
resistance was actually measured at, so backing out a real conductor length from a measured DCR requires
`ρ` evaluated at that measurement temperature, not at some other one. `ρ_Cu(25°C) = 1.68×10⁻⁸ × (1 +
0.00393×5) = 1.713×10⁻⁸ Ω·m` (0.00393/K is copper's standard temperature coefficient of resistance,
referenced to 20 °C — a material constant, not a repo or datasheet figure). Using a hot operating-temperature
resistivity instead would be self-inconsistent here: it would silently assume DCR stays at 0.10 Ω while hot,
when physically a hot coil's real DCR would itself be higher by roughly the same factor — double-counting
temperature in one direction while ignoring it in the other. 25 °C is used throughout Route A for this
reason, not because it is the more "conservative" pick in isolation.

**Current-density assumption (external, explicitly not from this repo).** A widely used magnetics-design
rule of thumb for continuously-rated copper windings (e.g. as tabulated in general transformer/inductor
design references, commonly expressed as circular-mils-per-amp) spans roughly **300–600 cmil/A**, i.e.
**J ≈ 3.3–6.6 A/mm²**. Per the task's instruction not to invent a single construction, both ends are carried
through:

| cmil/A | J (A/mm²) | Implied `A_cond` at 25 A | `L_cond = DCR·A/ρ` | `mass = ρ_density·A·L_cond` |
|---|---|---|---|---|
| 300 (tighter/better-cooled) | 6.58 | 3.80 mm² | 22.18 m | **755 g** |
| 600 (looser/typical) | 3.29 | 7.60 mm² | 44.37 m | **3021 g** |

Since `mass ∝ A²` (area appears once directly and once again through the DCR-derived length), the ~2×
current-density range produces a ~4× mass range — Route A alone is not tightly constraining. Both figures
are carried forward for the cross-check in §4.

---

## 3. Route B — from geometry, the OD ceiling, and inductance (the tighter, self-consistent bound)

### 3.1 Method

The spec's own numbers over-determine the winding once treated as a physical planar spiral:

- **Inductance target**: `L = 88 µH`, related to turn count `n` and mean diameter `d_avg` by a standard
  flat-spiral inductance formula. Two independent, cross-checked forms are used:
  - the classic **H. A. Wheeler (1928)** flat-spiral formula, `L(µH) = a²n²/(8a + 11c)`, with mean radius
    `a` and radial winding depth `c` in **inches** (the formula's native, empirical unit) — this is the
    long-standing, textbook form for round-wire spiral coils and is used as the primary check here because
    it is unambiguous and does not depend on coefficients specific to any one later paper;
  - a modern **modified-Wheeler planar-spiral form** (`L = K1·μ0·n²·d_avg / (1 + K2·ρ_fill)`, circular
    coefficients `K1≈2.23, K2≈3.45`, `ρ_fill = (d_out−d_in)/(d_out+d_in)`), used as the solving equation
    below because it is algebraically easier to combine with the other constraints, then **cross-validated
    against the classic formula independently** (§3.3).
- **DC resistance**: `DCR = ρ_Cu(25°C)·L_cond/A_cond`, with `L_cond = n·π·d_avg` (total conductor length =
  turns × mean turn circumference).
- **Outer-diameter ceiling**: `d_out ≤ 200 mm` (req #9). Using the ceiling itself — the largest permitted
  OD — is the conservative choice for a *lower* mass bound: a larger `d_avg` needs fewer turns for the same
  `L` (Wheeler's `n²` term), which needs less conductor length and less copper. This matches the task's own
  framing of the ceiling as what "bounds the mean diameter."
- **Close-wound, single-layer construction**: the spec's own language, "flat spiral" (§1 title line of
  `TANK_COIL_SPECIFICATION.md`), is read as a single layer of turns spiraling from an inner diameter `d_in`
  to `d_out`, each turn touching the next (no assumed gap) — i.e. the winding's radial buildup
  `(d_out − d_in)/2 = n·w`, where `w` is the wound conductor bundle's own diameter. This is the standard
  real-world construction for this coil class and is stated here as an assumption, not re-derived from
  anything more primitive.
- **Litz copper fill factor `F`** (assumption, external, explicitly labeled): the fraction of the round
  bundle's cross-sectional area that is actually copper (the rest is individual-strand enamel, interstitial
  air between round strands, and the bundle's outer serving). Real litz cable commonly runs **F ≈ 0.35–0.5**;
  the theoretical maximum for identical round strands in hexagonal close packing, ignoring all insulation, is
  **F ≈ 0.785**. This is the one free parameter in Route B and is swept across its full plausible range below
  rather than fixed at one value.

With `d_out` fixed at the 200 mm ceiling and `F` assumed, the system (Wheeler inductance = 88 µH; DCR =
0.10 Ω; close-wound geometry; bundle area = `F·π(w/2)²`) has exactly as many equations as unknowns
(`n`, `w`, `d_in`) and was solved numerically (Brent's method on the two combined equations; full script
retained in this session's scratch directory, not committed — the numbers below are its output, reproducible
from the equations stated).

### 3.2 Result, swept across the fill-factor range

| `F` (copper fill) | Turns `n` | Bundle OD `w` | `d_avg` | `d_in` | `A_cond` | `L_cond` | **Mass** | DCR check | L check |
|---|---|---|---|---|---|---|---|---|---|
| 0.25 | — | — | — | — | — | — | **infeasible** — no `d_in > 0` solution reaches 88 µH & 0.10 Ω within the 200 mm ceiling | | |
| 0.30 | — | — | — | — | — | — | **infeasible**, same reason | | |
| 0.35 (typical litz) | 23.5 | 2.54 mm | 140.2 mm | 80.5 mm | 1.775 mm² | 10.36 m | **164.8 g** | 0.1000 Ω | 88.00 µH |
| 0.40 | 21.0 | 2.33 mm | 151.2 mm | 102.4 mm | 1.705 mm² | 9.95 m | **152.0 g** | 0.1000 Ω | 88.00 µH |
| 0.45 | 19.7 | 2.17 mm | 157.4 mm | 114.7 mm | 1.664 mm² | 9.71 m | **144.8 g** | 0.1000 Ω | 88.00 µH |
| 0.50 | 18.8 | 2.04 mm | 161.6 mm | 123.3 mm | 1.635 mm² | 9.55 m | **139.8 g** | 0.1000 Ω | 88.00 µH |
| 0.60 (tight winding) | 17.7 | 1.84 mm | 167.4 mm | 134.8 mm | 1.595 mm² | 9.31 m | **133.1 g** | 0.1000 Ω | 88.00 µH |
| 0.70 | 17.0 | 1.69 mm | 171.3 mm | 142.5 mm | 1.568 mm² | 9.15 m | **128.6 g** | 0.1000 Ω | 88.00 µH |
| 0.785 (theoretical max packing) | 16.6 | 1.59 mm | 173.7 mm | 147.4 mm | 1.551 mm² | 9.05 m | **125.8 g** | 0.1000 Ω | 88.00 µH |

**`F = 0.25–0.30` is geometrically infeasible** — there is no single-layer spiral that reaches both 88 µH
and 0.10 Ω within a 200 mm OD at that little copper fill; it would need an inner diameter below zero (i.e.
an OD greater than 200 mm, which the ceiling forbids). This is itself a useful, derived fact: it rules out
the loosest-packed constructions as inconsistent with the coil's own stated numbers, independent of any
current-rating assumption.

**The mass estimate is strikingly insensitive to `F` across the remaining, physically plausible range**:
125.8–164.8 g across `F = 0.35–0.785`, a factor of only 1.3×, despite `F` itself spanning more than 2×. This
is because `n`, `w`, and `A_cond` all move together to keep both the 88 µH and 0.10 Ω constraints satisfied
simultaneously — the self-consistency is doing real constraining work, not just producing a number.

**Conservative floor adopted: 126 g** (rounding `F = 0.785`'s 125.8 g down slightly), reflecting the tightest
physically-defensible packing. **Realistic estimate: ≈145–165 g** (`F ≈ 0.35–0.45`, closer to real litz
cable's typical copper fill once enamel and outer serving are accounted for).

### 3.3 Cross-check against the classic 1928 Wheeler formula

At the `F = 0.35` geometry (`a = 2.760 in` mean radius, `c = 2.353 in` radial depth, `n = 23.52` turns):

```
L = a²n²/(8a + 11c) = (2.760)²×(23.52)² / (8×2.760 + 11×2.353) = 87.88 µH
```

against the 88.00 µH the modified-Wheeler equation was solved to hit exactly — **agreement to 0.14%**. Two
independently-published spiral-inductance formulas, applied to the same solved geometry, agree closely. This
is not proof the *real* coil has this exact geometry (the fill factor is still an assumption), but it shows
the geometric solve is not an artifact of which planar-spiral formula was chosen.

---

## 4. The two routes disagree — what that means, and why it doesn't change the verdict

Route A (naive current-density): **755–3021 g**. Route B (geometry + inductance + OD ceiling, solved
self-consistently): **126–165 g**. These disagree by roughly **5–20×** — a material disagreement, reported
rather than averaged, per the task's instruction.

**What the disagreement implies.** Route A's current-density rule of thumb has nothing to do with this
specific coil's geometry — it is calibrated for windings in general, unconstrained by any particular
inductance target or outer-diameter ceiling. Route B shows that this coil's *own* combination of 88 µH and a
200 mm OD ceiling cannot accommodate a conductor as large as Route A's naive assumption implies: a
3.8–7.6 mm² conductor, close-wound into a single-layer spiral, would need an OD larger than 200 mm to reach
88 µH at all (§3.2's infeasibility result at low `F` is the same effect from a different direction — too
little *copper fraction*, rather than too much *conductor cross-section*, but both fail for the same
underlying reason: there isn't room). **The current-density assumption, taken alone, is not tightly
constrained enough to trust for this coil** — the coil's own stated geometry is a tighter constraint than an
imported rule of thumb, and Route B is the more defensible bound for that reason, not merely because it is
smaller.

**Why this doesn't change the verdict.** The task asks for a *conservative* (lower) mass bound, because
lower mass means lower — safer — I²t withstand. Route B's bound (126–165 g) is *already* the smaller,
more conservative of the two. Route A's much larger mass estimate (755–3021 g), if anything, would only
widen the coil's margin further (§5 shows this explicitly). The two routes disagree sharply on the coil's
*likely actual* copper content, but they agree on the direction that matters for this task: neither comes
close to making the coil the binding element.

---

## 5. Adiabatic temperature rise and I²t withstand

### 5.1 Adiabatic assumption — stated and checked

The lumped model `ΔT = E/(m·c_p)` assumes no heat escapes the copper mass during the event. Copper's thermal
diffusivity is `α = k/(ρ·c_p) = 401/(8960×385) = 1.163×10⁻⁴ m²/s` (`k_Cu = 401 W/(m·K)`, standard tabulated
value). Over the fault's dominant window, the diffusion length `√(αt)` is:

- at `t_peak = 694 µs`: `√(1.163e-4 × 694e-6) = 0.284 mm`
- at `t = 1 ms`: `√(1.163e-4 × 1e-3) = 0.341 mm`

This is **much smaller than the coil's macroscopic dimensions** (turn-to-turn spacing ~1.6–2.5 mm per §3.2,
mean radius ~70–87 mm) — heat generated in the copper has no time to conduct out to the ferrite core, air,
or adjacent turns within the fault's duration, which is exactly the condition the adiabatic (no-loss)
assumption needs. It is **comparable to or larger than an individual litz strand's radius** (≤0.1 mm, spec
req #8: strands ≤0.2 mm diameter) — heat equilibrates within a single strand's cross-section on this
timescale, so a single lumped ΔT per turn is a physically reasonable simplification rather than masking
sharp internal hot spots. Both checks support the adiabatic model here; neither would hold at, say, a 100 ms
timescale, where diffusion length grows to ~3.4 mm and heat would begin escaping to neighboring turns and
the ferrite.

### 5.2 Temperature rise, at the derived mass bounds

Using the coil's own fault-energy figures (§1: 14.73 J through t_peak, 25.49 J through 1 ms) and
`c_p = 385 J/(kg·K)`:

| Mass basis | `m` | ΔT at t_peak (694 µs) | ΔT at 1 ms |
|---|---|---|---|
| Route B conservative floor (`F=0.785`) | 125.8 g | **0.304 K** | **0.526 K** |
| Route B realistic (`F=0.35`) | 164.8 g | 0.232 K | 0.402 K |
| Route A conservative floor (300 cmil/A) | 755.4 g | 0.051 K | 0.088 K |

Even at the **smallest, most conservative** mass bound found (Route B, 126 g), the coil's adiabatic
temperature rise under this fault is **under 0.6 K** — negligible against any starting temperature and the
180 °C Class H ceiling.

### 5.3 I²t withstand, at the conservative mass floor

Converting the available temperature headroom to an I²t figure (`Q = m·c_p·ΔT_avail`, `I²t_withstand =
Q/R`, `R = DCR = 0.10 Ω`, `m = 125.8 g`):

| Starting temperature | ΔT available to 180 °C | `I²t` withstand | Margin vs 147.3 A²·s (t_peak) | Margin vs 254.9 A²·s (1 ms) |
|---|---|---|---|---|
| 25 °C (cold) | 155 K | **≈75,100 A²·s** | 510× | 294× |
| 100 °C (hot — the spec's own §3 worst-case ΔT≤60K-from-40°C operating ceiling) | 80 K | **≈38,700 A²·s** | 263× | 152× |

**Worst case across every combination examined here: ≈150× margin** (hot start, 1 ms horizon, smallest
mass bound). Using Route A's much larger mass estimates instead only widens this further (e.g. at 755 g,
hot start: `Q = 755g×385×80K = 23,254 J`, `I²t_withstand ≈ 232,500 A²·s`, ≈900× margin at 1 ms) — the two
routes disagree on the number but agree on the conclusion.

---

## 6. Caveats inherited from the source document, and why they don't change this result

- **The fault model's I²t figures (147–255 A²·s) assume the coil's inductance stays linear (88 µH) through
  the entire event**, but the coil's own spec only guarantees linearity to 40 A peak — 15–18× below the
  fault's modeled 619–710 A peak (source document §1.2, §2.1). If the coil saturates, the *true* fault
  I²t could exceed the 147–255 A²·s figures used here, in a direction this document cannot quantify (no
  B-H curve exists in this repository). Given the ≈150–510× margin found above, a modest correction for
  saturation would need to be very large — multiple orders of magnitude — to change the qualitative verdict,
  but this document inherits, rather than resolves, that uncertainty: it is a statement about the *fault's*
  severity, not about the coil's copper mass, which is a static winding property independent of how much
  current later flows through it.
- **The pre-existing `i_max` conflict does not affect this bound.** `elec/src/constraints.ato:8` declares
  `HighVoltageConstraints.i_max = 25A` while `elec/src/modules.ato` records a 28.7–31.9 A tank *peak*,
  marked UNRESOLVED. Route B (the primary bound here) uses only `L=88µH`, `DCR=0.10Ω`, and the OD ceiling —
  it never references either current figure. Route A (secondary, discounted per §4) uses only the 25 A
  **rms continuous** rating, not the disputed peak figures. The conflict is orthogonal to both derivations
  and is noted, not resolved, per the task's instruction.
- **The mass bound itself does not depend on the fault at all** — it is derived purely from the coil's
  small-signal design spec (88 µH measured at "1 V drive or less" per §2 of `TANK_COIL_SPECIFICATION.md`,
  25 °C DCR, mechanical OD ceiling). Whatever happens to the coil's inductance during a 600+ A fault does
  not change how much copper is in the winding.

---

## 7. Assumptions, labeled, and what would supersede this document

Every number above is either read directly from the repository (§1) or derived from those numbers by a
stated formula (§§2–5). The following are the assumptions the derivation depends on, none of them sourced
from this repository:

| Assumption | Value/range used | Where it enters | What would replace it |
|---|---|---|---|
| Copper temperature coefficient of resistance | 0.00393 /K | Route A & B resistivity-at-25°C calc | Not needed once a real DCR-vs-temperature curve exists for the actual part |
| Current-density design rule (Route A only) | 300–600 cmil/A (3.3–6.6 A/mm²) | Route A conductor area | A real winder's declared strand count/gauge on the CoC — this entire route becomes unnecessary |
| Wheeler/modified-Wheeler spiral-inductance coefficients | Classic Wheeler (1928) primary; modified-Wheeler (`K1=2.23,K2=3.45`) as the solving form, cross-checked | Route B turn-count solve | A real turn count from the CoC or a bench teardown |
| Close-wound, single-layer, zero-gap winding | Assumed from "flat spiral" (spec §1) | Route B geometry | A real coil's cross-section (photograph, teardown, or CoC drawing) |
| Litz copper fill factor `F` | 0.35–0.785 (swept; 0.25–0.30 shown infeasible) | Route B conductor area | A real strand count + individual strand gauge on the CoC |

**What would supersede this entire document**: exactly what the prior document already named — a real
winder's Certificate of Conformance reporting turn count, strand count, strand gauge, or a directly measured
copper mass. Until one exists, the bound above (≈126–165 g, conservative floor 126 g) is **an engineering
derivation from this coil's own published specification, not a datasheet or vendor figure, and must not be
read as one downstream.**

---

## 8. What this document does not do

- It does not modify `elec/src/**` or `pcb/temper.kicad_pcb`. Verified clean (`git status --porcelain`)
  before this document was written.
- It does not resolve the pre-existing `i_max = 25A` vs 28.7–31.9 A peak conflict (`elec/src/constraints.ato:8`) —
  noted in §6 as orthogonal to this bound, not touched.
- It does not bound the bus capacitors' I²t withstand. That remains open for the reason the source document
  gave: aluminum-electrolytic surge failure is driven by localized internal I²·ESR heating, not bulk can
  mass, so a lumped adiabatic model would not represent the real failure mechanism even with a mass figure
  in hand. Out of scope for this document, which was asked to bound the coil specifically.
- It does not select, name, or recommend a real coil vendor or part. §7 states plainly what would replace
  this derivation, and by whom, without inventing either.
- It does not run `ngspice` (confirmed absent machine-wide, consistent with every prior evidence document in
  this repository).
