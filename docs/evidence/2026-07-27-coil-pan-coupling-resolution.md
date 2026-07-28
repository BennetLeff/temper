# Coil-to-pan coupling — resolution attempt

<!-- provenance: commit=d37315eb9b072b08b17d2f16307010c17a9bb241 dirty=false -->

**Date:** 2026-07-27
**Method:** Analytical derivation from committed documents + the standard
reflected-impedance algebra `pan_load.sub` and `RESONANT_TANK_DESIGN.md`
already state, cross-checked numerically against
`docs/hardware/TANK_COIL_SPECIFICATION.md`'s reported sweep output. No
bench hardware, no new simulation runs. `simulation/models/pan_load.sub`
was **read** (required for diagnosis) but **not edited**, per task
constraint.
**Reads first:** `docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md`
(literature), `docs/hardware/TANK_COIL_SPECIFICATION.md` (the Q=143
finding), `docs/COIL_BRACKET_DESIGN.md` (candidate geometry source),
`docs/hardware/RESONANT_TANK_DESIGN.md` (a second, disqualified geometry
source — see §1.2), `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`
(OCP-01 threshold), `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` §7 (the
ripple-budget blocker).

---

## Falsifiers, stated before analysis

**F1 (given by the task):** *"The geometry in `COIL_BRACKET_DESIGN.md` is
specific enough to derive `L` analytically."*
**Result: fires.** See §1. It is not specific enough, and the one other
document that looks specific enough (`RESONANT_TANK_DESIGN.md`) is
disqualified as a citation for reasons given in §1.2.

**F2 (mine, for the `pan_load.sub` diagnosis):** *"If no single parameter
in `PANLOAD_TRANSFORMER` can be shown wrong independent of what the other
two unknowns are set to, the diagnosis is not a diagnosis — it's just
'three things might be off,' and gives the caller nothing actionable."*
**Result: does not fire.** §2 shows a parameter-independent proof that `K`
alone is inconsistent with the one hard external data point (Infineon's
L-ratio), regardless of `L2` or `RPAN`. It does fire for `L2` vs `RPAN`
individually — those two cannot be separated from the literature alone,
which is exactly why the bench spec (§4) includes a multi-frequency step
to split them.

---

## 1. Does geometry let us derive coil `L` analytically?

### 1.1 What `COIL_BRACKET_DESIGN.md` actually commits to

Read in full. It specifies, under REQ-MECH-02:

- Air gap: **3 mm ± 0.5 mm** to the glass cooktop.
- "Coil Size: Supports OD **up to 200 mm**" — a bracket clearance
  *ceiling*, not a built coil dimension.
- Coil height in the stack-up: **5.0 mm** (± the table's tolerances).
- Material: non-magnetic bracket (FR4/fiberglass/slotted aluminum).

It does **not** state: turn count, inner diameter, winding pitch, or Litz
wire gauge/strand count. `elec/src/modules.ato:463-465` confirms nothing
downstream fills this gap either — `inductor_conn` is declared:

```
inductor_conn = new Resistor # Placeholder for Litz interface
inductor_conn.mpn = "CUSTOM_LITZ_COIL"
```

a placeholder resistor with a placeholder MPN, not a real inductor with a
value. `docs/hardware/TANK_COIL_SPECIFICATION.md` (2026-07-26) independently
confirms this: *"`inductor_conn` is an unplaced Litz placeholder... L cannot
be specified from the current model."*

Any planar-spiral inductance formula (Wheeler-type or current-sheet-type)
needs at minimum: outer diameter, inner diameter (or turns + wire
pitch/diameter), and turn count. Two of those three are simply absent from
every committed document. **Falsifier F1 fires: geometry is not specific
enough.**

### 1.2 A second document claims the missing numbers — and is disqualified

`docs/hardware/RESONANT_TANK_DESIGN.md` (dated 2025-12-13, status "Design
Complete, Verified by Simulation") states: **80 µH ± 10%, 20–25 turns,
160–200 mm diameter, Litz wire (100 × 0.1 mm strands)**. This looks like
exactly the missing input — but it is not usable as a citation, for three
reasons:

1. It is **contradicted by a more recent, more careful document**.
   `TANK_COIL_SPECIFICATION.md` (2026-07-26, seven months later) explicitly
   found the coil unplaced in `elec/src/*.ato` and stated the L value
   "cannot be specified from the current model" — directly at odds with
   `RESONANT_TANK_DESIGN.md`'s "Design Complete" status for the same
   parameter.
2. Its pan-material numbers are **not independent evidence** — they are
   verbatim identical to `pan_load.sub`'s own uncited header comments
   (`k = 0.5`, `R_pan = 8 Ω` for cast iron; `k = 0.3`, `R_pan = 25 Ω` for
   stainless). Restating an uncited source's numbers is not corroboration
   of them.
3. **No bench measurement, supplier datasheet, or external citation is
   given anywhere in the document** for the 80 µH / 20–25 turns / 160–200 mm
   figures themselves — they appear as already-decided "Specifications,"
   with no derivation shown.

Per the anti-fabrication instruction to distinguish measured/modeled/
assumed and cite every number: **this document's geometry is treated as
not usable input.** It is flagged here rather than silently ignored,
because its own internal self-consistency (a Q=1.67 calculation, a
plausible-looking BOM) makes it easy to mistake for verified design intent
if not checked against the newer document.

### 1.3 A structural (not formula-dependent) sensitivity check

I attempted to verify a standard planar-spiral inductance formula (the
"modified Wheeler" / current-sheet expression from Mohan, Hershenson, Boyd,
Lee, *"Simple Accurate Expressions for Planar Spiral Inductances,"* IEEE
JSSC, Oct. 1999) to compute a bounding range from the one real number
available (OD ≤ 200 mm). Four fetch attempts failed:

| URL | Result |
|---|---|
| `web.stanford.edu/~boyd/papers/pdf/inductances.pdf` | HTTP 404 |
| `people.eecs.berkeley.edu/~niknejad/ee242/pdf/inductance_mohan.pdf` (→ `rfic.eecs.berkeley.edu/...`) | HTTP 403 after redirect |
| `coil32.net/pcb-coil.html` | HTTP 403 |
| WebSearch | session search budget exhausted (200/200) before this query ran |

I am not willing to quote that formula's exact coefficients (`c1..c4` per
coil shape) from memory without a fetch to check them, given this task's
explicit bar against uncited numbers. **So the coefficient-dependent
version of this exercise is dropped, not fabricated.**

What survives without needing any disputed coefficient: inductance of any
fixed-geometry-family winding scales as **turn count squared**
(`L ∝ N²`), a textbook result independent of which spiral-inductance
formula's constants you use — doubling turns while holding the winding
footprint's shape fixed roughly quadruples `L`. `RESONANT_TANK_DESIGN.md`
(itself disqualified per §1.2, but illustrative of the kind of range a
designer would consider for a 160-200mm coil) suggests something in the
15–30 turn neighborhood is plausible for a coil this size. Over that
range alone, `N²` spans **225 to 900 — a 4× band** — before inner
diameter, pitch, or the OD itself (only upper-bounded, not fixed) are
allowed to vary at all. Adding those back in (COIL_BRACKET_DESIGN.md fixes
none of them) only widens the band further.

**Conclusion for §1:** Falsifier F1 fires. Neither the committed geometry
nor a disqualified secondary document permits an analytical `L` derivation
to anything near the ±10% precision the project's own design documents
assume. This piece of the task reduces to the literature framing already
done in the prior-art document, plus the bench spec in §4.

---

## 2. `pan_load.sub` — which `PANLOAD_TRANSFORMER` parameter is wrong

Confirmed by reading `simulation/harness/run_tank_coil_sweep.py` and
`run_zvs_sweep.py` (read-only, per task constraint): the harness that
produced the Q=143 finding instantiates **`PANLOAD_TRANSFORMER`**
specifically (not `PANLOAD_SIMPLE`), and its four named pan presets
(`run_zvs_sweep.py:121-126`) override only `K` and `RPAN` per material —
**`L2` is never overridden by any preset; it is always the subcircuit
default, 1 µH, for every pan material in every sweep run.**

| Preset | K | RPAN | L2 (always) |
|---|---|---|---|
| cast_iron | 0.5 | 8 Ω | 1 µH |
| stainless | 0.3 | 25 Ω | 1 µH |
| aluminum | 0.15 | 125 Ω | 1 µH |
| no_pan | 0.01 | 8 Ω | 1 µH |

### 2.1 The governing equations (already in this repo's own files)

`pan_load.sub`'s header and `RESONANT_TANK_DESIGN.md` §2.3 both state the
standard shorted-secondary reflected-impedance relation. Writing
`x = ωL2` (Ω) and `M = K√(L1·L2)`, the exact (not small-signal-approximated)
form is:

```
Z_reflected = (ωM)² / (R_PAN + jx)
R_ref        = (ωM)² · R_PAN / (R_PAN² + x²)                 [real part]
L_apparent   = L1 − M²·ω²·L2 / (R_PAN² + x²)                 [reactive part / ω]
```

Substituting `M² = K²·L1·L2` and `x = ωL2` gives the apparent-inductance
ratio purely in terms of `K`, `x`, and `R_PAN` — **`L1` cancels out**:

```
L_apparent / L1 = 1 − K²·x² / (R_PAN² + x²)
```

### 2.2 A parameter-independent floor on the L-ratio (this is the clean result)

As `x → ∞` (the fully-shorted-secondary limit — the same limit
`PANLOAD_SIMPLE`'s own `L_eff = L1·(1−K²)` formula hard-codes, one line
away in the same file), the ratio's reduction term saturates at its
maximum, `K²`. That means, **for any `L2` and any `R_PAN` whatsoever**:

```
L_apparent / L1  ≥  1 − K²          (floor, independent of L2, R_PAN)
```

The prior-art document's single most trustworthy number, Infineon
AN235020's measured loaded/unloaded ratio, is **≈0.40** (measured, 90–150
kHz, full coil + stainless pot — see
`2026-07-27-coil-pan-coupling-prior-art.md`). Requiring the floor to reach
0.40:

```
1 − K² ≤ 0.40   ⟹   K² ≥ 0.60   ⟹   K ≥ 0.775
```

Checked against every `K` value that appears anywhere in this project —
the subcircuit default (0.4), the header's "typical" range (0.2–0.6), and
all four named presets (0.01–0.5):

| K source | K | Floor (1−K²) | Reaches 0.40? |
|---|---|---|---|
| Subcircuit default | 0.40 | 0.84 | No |
| Header "typical" ceiling | 0.60 | 0.64 | No |
| cast_iron preset | 0.50 | 0.75 | No |
| stainless preset | 0.30 | 0.91 | No |
| aluminum preset | 0.15 | 0.9775 | No |
| Required to reach 0.40 | **≥0.775** | ≤0.40 | — |

**Every `K` value used anywhere in this project's model or its comments
falls short of what the one measured L-ratio in the literature requires —
by a wide margin, and this conclusion needs no assumption about `L2` or
`R_PAN` at all.** This is the single most defensible finding in this
document.

**This is also an open tension, not a clean fix**, flagged rather than
papered over: `K ≥ 0.775` is *outside* every coupling-coefficient range
any source in the prior-art search reported for pan/coil systems (max
found anywhere was 0.6, for cast iron). Two readings are both live:
(a) the model's whole `K` range is calibrated too low for this project's
specific flat-coil/flat-pan topology at a tight (3 mm) air gap, or
(b) Infineon's 0.40 ratio — measured on an unstated-diameter stockpot, not
this project's coil/pan pair — does not transfer here. **Not resolved by
literature; this is exactly a bench-measurement question** (§4).

### 2.3 `L2 = 1 µH` independently keeps the model far below even its own achievable ceiling

Plugging the actual default (`K=0.4`, `RPAN=10`, `L2=1u`) into the exact
formula at 35 kHz (`ω = 2π·35000 = 219{,}911` rad/s):

```
M  = 0.4·√(80e-6 × 1e-6)     = 3.578e-6 H
ωM = 219911 × 3.578e-6        = 0.7868 Ω
x  = ωL2 = 219911 × 1e-6      = 0.2199 Ω     (R_PAN=10 is 45× larger)
R_ref = (ωM)²·R_PAN/(R_PAN²+x²) = 0.619×10/100.05  = 0.0619 Ω
L_apparent/L1 = 1 − K²x²/(R_PAN²+x²) = 1 − 0.16×0.0484/100.05 ≈ 0.99992
```

With `L2` this small, `x` is 45× below `R_PAN` even for the *lowest*
`R_PAN` preset (cast iron, 8 Ω) — the model sits deep in the
"barely-loaded" regime where **neither the inductive loading (ratio ≈
0.9999, not even close to the 0.84 that `K=0.4` alone permits) nor the
reflected resistance (0.062 Ω) shows up**, regardless of which `K`/`RPAN`
preset is selected. **`L2` must be raised until `x = ωL2` is comparable to
`R_PAN` (`L2 ≳ R_PAN/ω`) before `K` or `R_PAN` can express themselves in
the model at all** — at `R_PAN=10 Ω`, 35 kHz, that floor is `L2 ≳ 45 µH`,
roughly **45× the current default**.

### 2.4 Numeric cross-check against the reported Q=143 finding

`TANK_COIL_SPECIFICATION.md`'s sweep used the `cast_iron` preset
(`K=0.5`, `RPAN=8`) at `L1=70 µH`, ratio 1.02 (`f_sw ≈ 35.4 kHz`,
`ω ≈ 222{,}400`):

```
M = 0.5·√(70e-6 × 1e-6) = 4.183e-6 H
ωM = 222400 × 4.183e-6  = 0.930 Ω
x  = ωL2 = 0.222 Ω
R_ref = (ωM)²×8/(64+0.049) = 0.865×8/64.05 = 0.108 Ω
Total R (R_ref + R_coil=0.1) ≈ 0.208 Ω
Q  = ωL_apparent/R_total ≈ 222400×70e-6/0.208 ≈ 74.9
```

The doc reports an implied `R = 0.109 Ω` and `Q = 143` at this operating
point — my hand-calc lands at `R ≈ 0.208 Ω`, `Q ≈ 75`: same order of
magnitude and the same qualitative story (severely under-loaded model),
but not an exact reproduction (~2× apart). I did not chase the residual
gap — it is plausibly other loop resistances the full harness circuit
includes beyond `pan_load.sub` alone (IGBT `R_on`, `C_tank` ESR), which I
have not read. **Flagged UNVERIFIED, not asserted.** The order-of-magnitude
match is enough to validate the *direction and scale* of the diagnosis in
§2.2–2.3, not to certify exact numbers.

### 2.5 A corrected, self-consistent example — explicitly not unique

Holding `L1=80 µH` and `RPAN=10 Ω` (the raw subcircuit defaults) fixed,
and solving the two literature constraints simultaneously —
`L_apparent/L1 = 0.40` (Infineon) and `R_ref ≈ 2.2 Ω` (prior-art doc's
35 kHz √f-extrapolated Infineon figure, corroborated within 10% by
IJCRT's independent 2 Ω design assumption at 23 kHz) — for the two
remaining unknowns `K` and `L2`:

```
Ratio eq:  K²x²/(100+x²) = 0.60
Rref eq:   R_ref = K²·L1·x·ω·R_PAN/(R_PAN²+x²) = K²·175.93·x/(100+x²) = 2.2

Substituting K² from the ratio eq into the R_ref eq collapses to:
  R_ref = 0.60 × 175.93 / x = 105.56 / x  =  2.2
  x = 105.56 / 2.2 = 47.98  →  L2 = x/ω = 47.98/219911 ≈ 218 µH
  K² = 0.60×(100+47.98²)/47.98² = 0.626  →  K ≈ 0.791
```

Check: `K²x²/(100+x²) = 0.626×2302/2402 = 0.600` ✓.
`R_ref = 0.626×175.93×47.98/2402 = 2.20 Ω` ✓.

**This is one point in an underdetermined family, not a specified value.**
Three unknowns (`K`, `L2`, `RPAN`), two independent literature-derived
constraints (L-ratio, `R_eff`) — the system cannot be uniquely solved.
Holding `RPAN` at a different value (it is itself an uncited placeholder;
the header offers 5–200 Ω across materials with no citation) yields a
different `(K, L2)` pair that fits the same two constraints equally well.
**This underdetermination is the concrete, mechanical reason a bench
measurement is required and literature-plus-algebra cannot finish the
calibration** — exactly the gap §4's multi-frequency step is designed to
close.

### 2.6 What this means for `pan_load.sub` (described, not implemented)

1. **`K`'s default (0.4) and the file's own documented "typical" ceiling
   (0.6) are both provably too low** to reproduce the one measured L-ratio
   found in the literature, independent of `L2`/`RPAN` (§2.2). Whether the
   fix is "raise K" or "the Infineon ratio doesn't apply to this geometry"
   is not decidable from documents alone — flagged as an open tension, not
   resolved here.
2. **`L2 = 1 µH` is too small by roughly 1–2 orders of magnitude** to let
   any of the model's `K`/`RPAN` combinations express meaningful coupling
   at all — it needs to be large enough that `ωL2` is comparable to
   `RPAN` (§2.3), which for the existing `RPAN` presets (8–125 Ω) at
   35 kHz means `L2` in the tens-to-hundreds of µH, not 1 µH. It is a
   **single, material-independent defect** (never overridden by any
   preset), so it affects every pan-material sweep the same way.
3. **`RPAN`'s per-material values (5–200 Ω) are uncited** and cannot be
   independently checked from the L-ratio constraint alone (§2.5) — they
   need their own measurement, not an inference from Infineon's data.

None of `simulation/models/pan_load.sub` was edited, per the task
constraint against repeating the original error on unvalidated numbers.

---

## 3. OCP-01 vs. 1800 W — verdict, with confidence

Threshold, from `2026-07-26-ocp01-vs-full-power-current.md` (not
re-derived here, only cited): OCP-01 trips at 50.1 A peak / 35.4 A RMS;
reaching 1800 W without tripping requires **`R_eff ≥ 1.43 Ω`**.

| Source | R_eff | Clears 1.43 Ω? | Basis |
|---|---|---|---|
| Project's own "typical 1.8 kW hob" figure | 1.12 Ω | **No** | Uncited estimate in the source doc itself |
| Infineon AN235020, measured & √f-extrapolated to 35 kHz | ≈2.2 Ω | **Yes** (+54%) | Measured 90–150 kHz, extrapolated (unverified scaling law) |
| IJCRT design assumption, 23 kHz/1.8 kW | 2.0 Ω | **Yes** (+40%) | Design assumption, not measured |
| This doc's §2.5 derived example (K≈0.79, L2≈218µH, RPAN=10, L1=80µH) | 2.2 Ω | **Yes** (+54%) | Derived to match the two constraints above — not independent evidence |

**Verdict: the weight of what evidence exists leans toward "no conflict"**
— two semi-independent literature estimates and one internally-consistent
derived example all clear 1.43 Ω by 40–54%, versus one project-internal
estimate (never cited to a source) that does not clear it.

**Confidence: low-to-moderate, not resolved.** Reasons to not treat this
as closed:
- No source measures `R_eff` at this project's actual 35 kHz, on this
  project's actual coil, with this project's actual pan set. Infineon is
  measured at 2.5–4.3× the target frequency; IJCRT is an assumption, not
  a measurement.
- §1 shows this project's coil geometry is unspecified. `R_ref` scales
  with `L1` in the model (§2.1) and with the true coil geometry's mutual
  inductance in reality — there is no guarantee the eventual coil matches
  either literature source's implicit scale.
- The §2.5 "derived" data point is not independent corroboration; it was
  constructed to satisfy the same two literature numbers already counted.

**Plain statement for the caller:** *"Does not conflict" is the
better-supported reading given everything gathered here, at low-to-moderate
confidence — not "resolved."* A single bench measurement of `R_eff` on the
worst-case (lowest-coupling) pan in whatever compliance pan set the
project uses would close this outright (§4).

---

## 4. Bench measurement — executable spec

### 4.1 Equipment

**Falsifier for this section, stated up front:** *this spec fails if a
standard bench LCR meter cannot reach 35 kHz with adequate accuracy.*
**It is a real risk** — many bench LCR meters have fixed test frequencies
(100 Hz/1 kHz/10 kHz/100 kHz) and no 35 kHz point. Check the instrument's
selectable-frequency list before starting.

- **Preferred:** an LCR meter or impedance analyzer with a user-settable
  test frequency covering 25–45 kHz (e.g., swept-sine impedance analyzers,
  or LCR meters with a continuously variable oscillator, not just fixed
  decade points).
- **Fallback if only fixed frequencies are available:** a sine-wave
  generator at the target frequency, a current-sense shunt (non-inductive)
  in series with the coil, and an oscilloscope — compute `|Z| = V_coil/I`
  and phase from the V/I waveforms (Lissajous or cross-correlation), then
  `R = |Z|cos(θ)`, `X = |Z|sin(θ)`, `L = X/ω`. Lower precision than a
  proper impedance analyzer but reaches any frequency a generator can
  produce.

### 4.2 Coil

Use the actual coil intended for production. If it is not yet wound: wind
one to COIL_BRACKET_DESIGN.md's 200 mm OD ceiling, and **record the
turns, inner diameter, and wire spec used** — recording these is itself a
required output, since §1 showed none of them are documented anywhere in
this project today.

### 4.3 Procedure

1. **Coil alone, no pan**, at 35 kHz (± whatever the instrument allows):
   record `L_unloaded`, `R_unloaded`.
2. **For each pan in the test set** (§4.4), centered on the coil at the
   production air gap (3 mm ± 0.5 mm per COIL_BRACKET_DESIGN.md
   REQ-MECH-02): record `L_loaded(f)`, `R_loaded(f)` at 35 kHz.
3. Compute per pan: `ratio = L_loaded/L_unloaded`; `R_eff = R_loaded −
   R_unloaded`.
4. Solve `K = √(1 − ratio)` — valid in the near-shorted-turn limit a real
   conductive pan approximates (§2.2's floor relation, evaluated as an
   equality rather than a bound once `ratio` is actually measured rather
   than assumed).
5. **To split `L2` from `RPAN`** (§2.5 showed one L/R measurement at a
   single frequency cannot do this — it is the concrete underdetermination
   this bench step exists to remove): repeat steps 1–3 at **2–3 additional
   frequencies bracketing 35 kHz** (e.g., 25 kHz, 35 kHz, 45 kHz). `RPAN`
   (real eddy-current loss) varies only weakly with frequency
   (√f, skin-effect); `L2` (the pan's geometric self-inductance as a
   shorted loop) is frequency-independent by construction. Fitting
   `R_ref(f)` and `ratio(f)` jointly across 3+ points to the exact
   formulas in §2.1 (not just algebra at one point) resolves the
   `L2`/`RPAN` split.
6. Repeat steps 1–5 at **2.5 mm and 3.5 mm** air gap (REQ-MECH-02's stated
   ±0.5 mm tolerance) — needed because §2.2 found the `K` this project's
   own literature-anchored ratio implies (≈0.79) is outside every
   `K` range found in any source, and gap sensitivity is the most likely
   physical explanation to check first.

### 4.4 Pan test set (minimum)

- Whatever pan(s) the project's compliance/test criteria already specify
  as the target cookware — **UNVERIFIED: not confirmed in this pass
  whether `FUNCTIONAL_TEST_CRITERIA.md` or another document defines one**;
  check before starting.
- A cast-iron pan and a magnetic (ferritic) stainless pan, bracketing the
  `k = 0.3–0.6` range every source in the prior-art search associated with
  induction-suitable materials.
- At least two diameters per material: one matched to the coil OD and one
  visibly undersized/off-center — `2026-07-26-ocp01-vs-full-power-current.md`
  names undersized/off-center pans as exactly the case that would push
  `R_eff` down and cause nuisance OCP-01 trips.

### 4.5 What the numbers must produce to close each blocked question

**(a) Tank coil `L` spec** (`TANK_COIL_SPECIFICATION.md`): `L_unloaded`,
measured to the instrument's stated accuracy, becomes the specified `L1`
directly. The `L_loaded` values across the pan/gap matrix bound the
achievable `f_sw/f_res` envelope with no further modeling required for
this piece — it is a direct measurement, not an inference.

**(b) OCP-01 vs. 1800 W** (§3 here): compute `R_eff` for the
**lowest-coupling pan actually in the compliance test set**. If
`R_eff < 1.43 Ω` for that pan, OCP-01 conflicts with 1800 W on it, and one
of the four resolutions `2026-07-26-ocp01-vs-full-power-current.md`
already lists (coil redesign for higher `R_eff`, raise the OCP-01 trip,
add RMS-sensing hardware, or lower the 1800 W target) is required. If
`R_eff ≥ 1.43 Ω` for every pan in the compliance set, the conflict is
closed — no further work needed on this question.

**(c) Bus ripple-voltage budget** (`BUS_CAPACITANCE_DERIVATION.md` §7):
plug the measured, frequency-fit `(K, L2, RPAN)` triple into the tank's
`P(V_bus, f_sw)` transfer function and re-evaluate at the 3000 µF
central-case ripple trough that document derives (170 V → ≈143 V, a 16%
sag each line half-cycle). The measurement closes this question if it
confirms `PWR-02`/`EFF-02` (1800 W, >92% efficiency) and the
`f_sw/f_res ≥ 1.05` ZVS margin both hold at the bottom of that sag; it
reopens the ripple-capacitance sizing if they do not.

---

## 5. UNVERIFIED

- Whether Infineon's √f skin-effect scaling (90–150 kHz measured → 35 kHz
  target) is actually valid for this project's geometry — carried over
  from the prior-art document, not independently re-checked here.
- Whether `K ≥ 0.775` (required by §2.2's floor argument to match the
  Infineon L-ratio) is physically plausible for a flat coil/flat pan at a
  3 mm gap, or whether the Infineon ratio (measured on an
  unstated-diameter stockpot) simply doesn't transfer to this project's
  geometry. Genuinely open; not resolved by anything found.
- Whether `RESONANT_TANK_DESIGN.md`'s 20–25 turns / 160–200 mm / 80 µH
  figures have any basis beyond restating `pan_load.sub`'s own assumed
  defaults — not established either way; a citation audit of that
  document is out of scope here.
- The ~2× residual gap between my §2.4 hand-calculated `Q ≈ 75` and
  `TANK_COIL_SPECIFICATION.md`'s reported `Q = 143` at nominally the same
  operating point — plausibly other loop resistances in the fuller
  harness circuit (IGBT `R_on`, `C_tank` ESR) not modeled by
  `pan_load.sub` alone. Not chased further.
- Whether a reference/compliance pan set is defined anywhere in
  `FUNCTIONAL_TEST_CRITERIA.md` or elsewhere — not checked exhaustively in
  this pass; the bench spec (§4.4) flags this as a pre-flight check.
- The `RPAN = 10 Ω` anchor used throughout §2.5's "corrected parameters"
  example is itself an unvalidated placeholder inherited from the file's
  own uncited defaults — the `(K≈0.79, L2≈218µH)` solution is one member
  of an underdetermined family, not a recommendation to adopt those exact
  numbers.
- Exact air-gap and pan diameter used in Infineon AN235020's own
  measurement (photo-inferred stockpot, not explicitly dimensioned in the
  document's text) — carried over from the prior-art document's own
  caveat.
- The four fetch attempts at a published planar-spiral-inductance
  reference (§1.3) all failed (403/404/search-budget-exhausted); the
  `N ∝ N²` structural argument used instead needed no such citation, but
  the coefficient-level version of that exercise was dropped rather than
  attempted from unverified memory.

---

## Bottom line for the caller

- **Geometry does not permit an analytical `L` derivation.** F1 fires:
  `COIL_BRACKET_DESIGN.md` gives only an OD ceiling, air gap, and coil
  height — no turns, inner diameter, or wire spec. A second document that
  claims those numbers (`RESONANT_TANK_DESIGN.md`) is disqualified: it
  contradicts a more recent audit and its pan-material numbers merely
  restate `pan_load.sub`'s own uncited defaults.
- **`pan_load.sub`'s `PANLOAD_TRANSFORMER`: two independent, compounding
  defects, one provable without assumptions.** `K` (default 0.4, file's
  own stated ceiling 0.6) can never reproduce Infineon's measured 0.40
  loaded/unloaded L-ratio, because the ratio's theoretical floor is
  `1−K²` regardless of `L2`/`RPAN` — reaching 0.40 needs `K ≥ 0.775`,
  outside every coupling value this project or the literature search
  names anywhere. Separately, `L2 = 1 µH` (never overridden by any of the
  four pan presets) keeps `ωL2` ~45× below `RPAN`, suppressing essentially
  all coupling effects regardless of `K`; it needs to rise by roughly 1–2
  orders of magnitude. One self-consistent (but not unique) corrected
  triple: `K≈0.79`, `L2≈218 µH`, holding `RPAN=10 Ω` — explicitly one
  point in an underdetermined family, not a specification.
- **OCP-01 vs. 1800 W: literature leans "no conflict," at low-to-moderate
  confidence.** Two literature-derived `R_eff` estimates (≈2.0–2.2 Ω) and
  one internally-consistent derived value clear the 1.43 Ω threshold by
  40–54%; only the project's own uncited "1.12 Ω typical" figure does not.
  Not resolved — no source measures `R_eff` at this project's actual
  frequency/coil/pan.
- **The bench measurement is fully specified in §4**: LCR meter or
  impedance-analyzer fallback, coil geometry recording, a pan/gap test
  matrix, a multi-frequency step specifically to split `L2` from `RPAN`,
  and the exact numeric thresholds (`R_eff` vs. 1.43 Ω; `L_unloaded`
  directly as the spec value) that close each of the three blocked
  questions.
