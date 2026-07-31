<!-- provenance: commit=df84a9d0456963061ca99a1b8d9d7c1d7618577b dirty=false -->

# Is a sealed/partitioned PCB compartment thermally viable? A steady-state bound

**Base commit:** `df84a9d0` (`origin/main`), branch
`analysis/pcb-compartment-thermal-bound`, isolated worktree. `dirty=false`:
no design file, footprint, board file, constant, or gate changes were made;
this document is the only change.

**Scope.** `docs/ENVIRONMENTAL_SPEC.md` and the PD3 determination
(`docs/evidence/2026-07-30-pollution-degree-determination.md`) establish
that PD3 (12.6mm reinforced creepage) governs today because the IEC
60335-2-6 cl. 29.2 enclosure exception is not earned: the PCB sits
standoff-mounted in the same forced-air-ventilated cavity as the coil and
heatsink duct. PD2 (8.0mm) stays available *if* a future revision
documents a genuine sealed/partitioned PCB compartment. **This document
answers only the thermal half of that prerequisite: if the PCB compartment
were walled off from the forced-air duct, would it overheat?** It does not
decide pollution degree, does not touch a design file, and does not
propose reopening the air path — per the task brief.

**Labels used throughout:** **[repo]** = a figure taken directly from a
cited repo document. **[assumed]** = a value this document supplies because
no repo document gives one, explicitly flagged. **[derived]** = arithmetic
on the above, shown in full.

---

## Verdict, up front

**Marginal — viable for normal-to-warm kitchen ambient (chassis air up to
~50–55°C), not comfortably viable at the repo's own "worst case" 55–70°C
ambient band without specific added mitigation.** The compartment's own
convective+radiative temperature rise is modest (roughly 8–20°C under a
wide assumption sweep) and by itself would not be disqualifying. What
changes the picture is that two die-level parts — the LMR51430 buck and,
under a plausible θJA assumption, the UCC21550 gate driver — are *already*
reported in this repo as running at or near their absolute maximum
junction temperature at 70°C ambient **with airflow**. Removing airflow and
adding compartment self-heating on top pushes both past zero margin in a
sizeable fraction of the plausible assumption space, at exactly the ambient
band the repo already calls out as a live operating condition ("extended
cooking," "hot location, poor ventilation"). The electrolytic bus
capacitors, which the brief expected to bind, do **not** bind first under
these numbers — they stay under their 105°C endurance rating in nearly
every scenario computed except the most extreme compound tail. That
reordering (LMR51430/gate-driver bind before capacitors) is itself a
finding worth flagging, not an assumption to correct toward the expected
answer.

---

## 1. Compartment temperature-rise bound

### 1.1 Geometry — stated explicitly, because nothing in the repo gives a compartment volume

No document in this repo describes a PCB compartment, partition, or
cavity — this had to be assembled from adjacent facts:

- **Board size:** `pcb/temper.kicad_pcb`'s only `Edge.Cuts` polygon (line
  8268) runs `(20,20)–(172,20)–(172,254)–(20,254)`, i.e. an **actual board
  of 152mm × 234mm [repo, measured directly from the board file]**. This
  contradicts `docs/specs/PCB_SPECIFICATION.md`'s stated 100mm × 150mm —
  that spec doc is stale relative to the real layout. This analysis uses
  the real 152×234mm board, not the spec figure, and flags the
  discrepancy as an open item (§5).
- **Stack height:** `docs/specs/PCB_SPECIFICATION.md` §2.2/§2.4 gives an
  8mm minimum standoff **[repo]** and a 25mm top general-component
  clearance zone (40mm in the IGBT/heatsink area specifically) **[repo]**.
  I use 33mm (8+25) as the compact case, reasoning that a partition would
  most naturally wall off the "general" electronics zone and let the
  IGBT/heatsink zone (which must stay in the duct) poke through the
  partition wall rather than be enclosed by it.
- **Chassis:** `docs/specs/REQUIREMENTS.md` gives the RCA 12A3 as
  ~230mm W × 180mm D × 120mm H, but self-flags this **"approximate, needs
  verification"** **[repo, low-confidence]**. Note this is in tension with
  the real 234mm board length, which is *longer* than the chassis's stated
  230mm width — one of these two repo figures is wrong; this document
  does not resolve which, and treats it as a residual (§5).

**Two bounding envelopes, both explicitly [assumed] beyond the board
footprint:**

| Case | L × W × H | Rationale |
|---|---|---|
| **Compact** | 152 × 234 × 33mm | Board footprint + PCB_SPECIFICATION's own standoff/clearance zone, no added wall margin. Surface area **A = 966 cm²**, volume 1.17 L. |
| **Generous** | 172 × 254 × 50mm | +20mm each in-plane for partition wall/mounting flange, +17mm height to allow the compartment to also cover part of the IGBT-zone clearance. Surface area **A = 1300 cm²**, volume 2.18 L. |

Compact is the more conservative (smaller-area, higher-ΔT) case and is
used as the headline; generous is reported as the favorable bound.

### 1.2 Heat load

`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §1 gives PCB-resident dissipation
as **9.65W [repo]**: buck 1.0, LDO 0.65, gate drivers 1.5, ESP32 0.5, EMI
filter 2.0, capacitor ESR 4.0. §2 below revises this upward for IGBT lead
conduction; both **Q = 9.65W** (repo baseline) and **Q = 12.0W** (with the
§2 conservative addition) are carried through the thermal-rise calculation.

### 1.3 Method — natural convection + radiation, derived not asserted

Energy balance at steady state for a box at surface temperature
`Ts = Ta + ΔT` losing heat `Q` to surrounding air at `Ta`:

```
Q = h·A·ΔT + ε·σ·A·(Ts⁴ − Ta⁴)
```

- `h = 1.42·(ΔT/Lc)^0.25` W/m²K — the standard simplified free-convection
  correlation for an isothermal plate/enclosure in still air (electronics-
  cooling engineering approximation; **[assumed/external]**, not a repo
  figure, valid for laminar natural convection, ΔT and Lc in this problem's
  range). `Lc` = the box's longer in-plane dimension (0.234m compact,
  0.254m generous). This is a single lumped coefficient applied to the
  whole box — it does not separately distinguish top/bottom/side-face
  orientation (each has a somewhat different coefficient in reality); the
  ε and geometry sweep below is meant to cover that additional ±30–40%
  uncertainty qualitatively rather than modeling each face.
- `ε` (emissivity of the compartment's outer surface): swept **0.2
  (bare/oxidized aluminum, unfavorable) to 0.9 (painted/matte surface,
  favorable)**, midpoint 0.5 — **[assumed]**, since no document specifies
  the chassis wall finish for a hypothetical PCB partition.
- `σ = 5.670374×10⁻⁸ W/m²K⁴` (Stefan-Boltzmann constant).
- Solved by fixed-point iteration to convergence (Python, shown in full
  below is the resulting table; the iteration itself is standard Newton-
  style scaling of ΔT by Q/Q_current until convergence to <0.01°C).

This gives the **partition wall's own outer-surface temperature rise**
above the surrounding chassis-cavity air. It does *not* yet include the
extra rise from the enclosed air/components to the inner wall surface
(covered in §1.5).

### 1.4 Results — compact geometry, the conservative case

| Q (W) | Ta chassis (°C) | ε=0.2 (unfavorable) | ε=0.5 (mid) | ε=0.9 (favorable) |
|---|---|---|---|---|
| 9.65 | 40 (normal) | ΔT 17.5 → Ts 57.5 | ΔT 13.2 → Ts 53.1 | ΔT 9.8 → Ts 49.8 |
| 9.65 | 55 (warm kitchen) | ΔT 17.0 → Ts 72.0 | ΔT 12.4 → Ts 67.4 | ΔT 9.0 → Ts 64.0 |
| 9.65 | 70 (worst case, repo's term) | ΔT 16.4 → Ts 86.4 | ΔT 11.6 → Ts 81.6 | ΔT 8.3 → Ts 78.3 |
| 9.65 | 85 (design limit) | ΔT 15.9 → Ts 100.9 | ΔT 10.9 → Ts 95.9 | ΔT 7.6 → Ts 92.6 |
| 12.0 | 40 | ΔT 21.0 → Ts 61.0 | ΔT 15.9 → Ts 55.9 | ΔT 11.9 → Ts 51.9 |
| 12.0 | 55 | ΔT 20.4 → Ts 75.4 | ΔT 15.0 → Ts 70.0 | ΔT 11.0 → Ts 66.0 |
| 12.0 | 70 | ΔT 19.7 → Ts 89.7 | ΔT 14.1 → Ts 84.1 | ΔT 10.1 → Ts 80.1 |
| 12.0 | 85 | ΔT 19.1 → Ts 104.0 | ΔT 13.2 → Ts 98.2 | ΔT 9.3 → Ts 94.3 |

Generous geometry (30% more surface area) runs consistently **20–40%
cooler in ΔT** than compact at the same Q/ε/Ta — e.g. Q=9.65W, Ta=70°C,
ε=0.5: ΔT 9.0°C (Ts 79.0°C) vs compact's 11.6°C. Full sweep omitted here
for space; the compact numbers above are the conservative headline.

**Headline bound: the partition wall itself runs 8–21°C above the
surrounding chassis-cavity air, central estimate ~12–16°C, across the full
assumption sweep (Q 9.65–12W, ε 0.2–0.9, compact geometry).** This by
itself is a modest, plausible-sounding rise — it is not what makes the
verdict "marginal" (see §3).

### 1.5 Internal film — the one place this bound is admittedly soft

The table above is the *outer wall* temperature; components sit inside
the sealed volume and see an additional, smaller rise from natural
convection/radiation off their own surfaces to the inner wall. This
document does **not** build a second independent nonlinear film model for
that step — doing so would just stack one more unverifiable coefficient on
top of the first, which is exactly the false-precision problem the task
brief warns against. Instead: **an explicit +30% multiplier on the wall ΔT
[assumed]**, bracketed 0% (no internal resistance — components touch the
wall) to +50% (poor internal circulation, fully sealed box with no forced
mixing), is used everywhere a *component* (not the wall itself) is being
checked against a rating in §3. This is engineering judgment sized from
typical enclosed small-instrument-box practice, not a repo figure and not
a independently-derived number — flagged plainly as the weakest link in
the chain, consistent with §5.

---

## 2. IGBT-to-PCB lead conduction — the load-bearing unknown

**Question:** of the IGBTs' 36W **[repo, SYSTEM_THERMAL_BUDGET.md §1]**,
how much conducts into the PCB through the leads/solder joints rather than
out through the heatsink tab? If material, the 9.65W PCB-resident figure
undercounts the sealed compartment's real load.

### 2.1 The two parallel paths

The IGBT die's heat has two exits from the package: (a) the mounting
tab → TIM → heatsink → ambient, and (b) the leadframe fingers (the same
copper flag the tab is stamped from, narrowing into leads) → solder
joints → PCB copper → compartment → ambient. These are parallel thermal
paths from a common node (the die/tab); heat splits inversely with
resistance.

**Path (a), tab→heatsink→ambient — [repo] figures:**
- `Rth_jc = 0.50°C/W` (SYSTEM_THERMAL_BUDGET.md §3.1)
- TIM: Bergquist Sil-Pad 400, 0.009", TO-247 die-cut (`docs/hardware/BOM.md`
  line 508) — no explicit Rth given in-repo for this specific pad, but
  SYSTEM_THERMAL_BUDGET's `Rth_cs = 0.20°C/W` is consistent with a Sil-Pad
  400 at this thickness and area (external cross-check, not independently
  re-derived here).
- `Rth_sa`: the BOM's actual selected heatsink, Wakefield-Vette 392-120AB,
  gives **0.5°C/W natural / 0.2°C/W forced** (`docs/hardware/BOM.md` line
  506) — using the forced-air figure since the heatsink stays in the duct
  regardless of what happens to the PCB compartment.
- **Total, path (a): Rth_jc + Rth_cs + Rth_sa ≈ 0.5 + 0.2 + 0.2 = 0.90°C/W**
  (per device; using the natural-convection 0.5 instead of forced gives
  1.20°C/W — bracket 0.9–1.2°C/W).

**Path (b), leads→PCB — entirely [assumed], no datasheet lead geometry
exists in this repo (confirmed absent by direct search of docs/, elec/,
pcb/):**
- Cross-section: 1.2mm × 0.5mm ≈ 0.6mm² (typical TO-247 leadframe finger
  dimension, external reference, not measured).
- Length, package edge to PCB pad, vertical-mount bend: 8mm (external
  reference).
- Conductivity: copper-alloy leadframe, k = 150–380 W/m·K (150 for a
  lower-conductivity alloy, 380 for near-pure copper) — swept as a range
  rather than a point value.
- Two leads (collector, emitter) are electrically/thermally coupled near
  the die pad and carry the bulk of the current; the gate lead is ignored
  (negligible current, negligible thermal coupling).
- **R_lead (single) = L/(k·A) = 0.008 / (k · 0.6e-6):** 35°C/W at k=380,
  67°C/W at k=200, 89°C/W at k=150.
- **Two leads in parallel:** 18–45°C/W, using the 150–380 W/m·K bracket.
- Solder-joint and PCB in-plane spreading resistance are **neglected**
  (both would only add resistance, i.e. only *reduce* the leak fraction) —
  this makes the estimate a conservative (upper-bound) leak, appropriate
  for a safety-relevant bound.

### 2.2 Split

Current-divider on two parallel resistances from a common node:
`Q_leak = Q_total · R_tab / (R_tab + R_lead)`

Using `R_tab = 0.90–1.20°C/W` and `R_lead = 18–45°C/W`:

`Q_leak/Q_total = 0.90/(0.90+45) = 2.0%` (favorable bound) to
`1.20/(1.20+18) = 6.3%` (unfavorable bound)

Applied to the repo's 36W IGBT total: **Q_leak ≈ 0.7–2.3W**, conducted
into the PCB via the leads across both devices combined.

### 2.3 Verdict on this question

**This does not invalidate the 9.65W figure, but it is not negligible
either — it should be treated as an additional ~1–2.5W, revising the
PCB-resident sealed-compartment design load to roughly 10.5–12W rather
than 9.65W.** §1 and §3 carry both the repo's 9.65W baseline and a 12.0W
conservative case for exactly this reason. **What this calculation cannot
settle:** whether the IGBT's mounting tab is the same electrical/thermal
node as one of its three leads (as assumed here, typical for many discrete
power devices, with the collector) — if it is instead a genuinely isolated
die pad with only bond-wire coupling to all three leads, the true leak is
lower than this bound, not higher, because bond wires are a far higher-
resistance path than a continuous leadframe finger. The direction of this
uncertainty favors safety (this bound over-, not under-, estimates the
leak) but the manufacturer's outline drawing (not in this repo) would be
needed to pin it down rather than bound it.

---

## 3. Per-component margin check

Local temperature bound for each component = compact-geometry wall ΔT
(§1.4) × internal-film factor (§1.5, 1.0–1.3–1.5) added to chassis ambient
`Ta`. Both Q=9.65W (repo baseline) and Q=12.0W (with §2's lead-conduction
addition) are carried. All entries below use **ε=0.5 (mid)**; ε=0.2/0.9
brackets are noted where they change the verdict.

### 3.1 LMR51430 buck (binds first)

`docs/hardware/LMR51430_THERMAL_ANALYSIS.md` **[repo]**: P=1.0W,
RθJA = 80°C/W bare / 60–65°C/W with the recommended copper-pour mitigation,
TJ(max) = 150°C. **This repo's own doc already calls the bare-layout case
"NOT ACCEPTABLE" and the with-pour case "AT LIMIT" at TA=70°C with
airflow** (TJ=130°C, 20°C margin quoted, but that 70°C figure was assumed
as the component's local ambient directly — it did not itself add a
sealed-compartment rise on top).

| Scenario | Compact wall ΔT ×1.3, Ta=70°C, ε=0.5 | Local ambient | Tj (60–65°C/W pour) | Tj (80°C/W bare) | Margin to 150°C |
|---|---|---|---|---|---|
| Q=9.65W | 15.1°C | 85.1°C | **147.6°C** | 165.1°C | **+2.4°C (pour) / −15.1°C (bare)** |
| Q=12.0W | 18.3°C | 88.3°C | **150.8°C** | 170.3°C | **−0.8°C (pour) / −20.3°C (bare)** |

At ε=0.2 (unfavorable finish) these numbers get 4–5°C worse; at ε=0.9
(favorable) they get 4–5°C better (margin recovers to +7 to +10°C at
Q=9.65W). **Whether this part has positive or negative margin at the
repo's own "worst case" ambient is genuinely assumption-dependent** — it
is not comfortably positive under central assumptions, and it is verified
that the recommended copper-pour mitigation (not confirmed as actually
laid out on the real board — this was not independently checked against
`pcb/temper.kicad_pcb` copper zones) is doing all the work of keeping this
part in range at all.

### 3.2 UCC21550 gate driver (binds comparably)

`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §3.4 **[repo]**: P=1.5W total
(single dual-channel IC), Tj(max)=150°C, "expected Tj <100°C (good
airflow)" — no θJA given anywhere in this repo (confirmed absent by
search). Using a **[assumed]** SOIC-14/16W-package JEDEC still-air θJA of
45–70°C/W (45 representing benefit from the via/copper-spreading treatment
SYSTEM_THERMAL_BUDGET §7.2 already calls for; 70 representing the bare
package):

- Q=9.65W, Ta=70°C, ε=0.5, ×1.3 internal factor → local ambient 85.1°C.
  `Tj = 85.1 + 1.5×45 = 152.6°C` (45°C/W case, **−2.6°C margin**) to
  `85.1 + 1.5×70 = 190.1°C` (70°C/W case, **−40°C margin**).

This is the widest-uncertainty entry in the table (θJA is entirely
assumed, not sourced), but even the favorable end of the assumed range
lands at essentially zero margin at the repo's own worst-case-continuous
ambient. **This is a genuine gap: the repo does not carry the data needed
to check this part's sealed-compartment margin with confidence**, and it
should not be read as comfortably passing just because the repo's existing
"<100°C good airflow" claim sounds fine — that claim explicitly depends on
airflow this analysis removes.

### 3.3 XC6220 LDO

`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §8.2 **[repo, reverse-derived]**:
the repo's own Tj-vs-Ta table (25→80°C, 40→100°C, 55→115°C, 70→130°C)
implies a consistent ΔT≈55–60°C at P=0.65W, i.e. an implied
**Rθja ≈ 88–92°C/W [derived]**. Applying that against the §1 local-ambient
bound (85.1°C at Q=9.65W/Ta=70°C/ε=0.5/×1.3): `Tj = 85.1 + 0.65×90 ≈
143.6°C`, against a 150°C max → **+6.4°C margin**. Positive but thin; at
Ta=85°C (design limit) this goes negative. Less severe than the buck or
gate driver, but not a large-margin part either.

### 3.4 Electrolytic bus capacitors (does not bind, contrary to expectation)

`docs/hardware/BOM.md` **[repo]**: EKMQ251VSN182MA50S, 1800µF/250V/105°C,
35mm snap-in can, ×4 (2 in parallel per bus half). Life rating (from
`docs/hardware/BUS_CAPACITANCE_DERIVATION.md`, cross-checked): **2000h at
105°C, rated conditions [repo]**. Using the standard Arrhenius
10-degree-doubling rule the task brief itself specifies:

`L(T) = 2000h · 2^((105−T)/10)`

Using the §1 wall-ΔT bound directly (not the ×1.3 hotspot factor — these
are large, low-power-density cans, closer to the ambient air temperature
than a die-attached IC; using the plain wall figure, not the component
hotspot bracket, is the appropriate proxy here and is *itself* a modelling
choice, flagged):

| Scenario | Local cap temp | vs. 105°C rating | Implied life |
|---|---|---|---|
| Q=9.65W, Ta=70°C, ε=0.5 | 81.6°C | **−23.4°C under rating** | ~9,900h (≈5× rated) |
| Q=12.0W, Ta=70°C, ε=0.2 (compound worst case) | 89.7°C | **−15.3°C under rating** | ~5,300h (≈2.6× rated) |
| Q=12.0W, Ta=85°C, ε=0.2, ×1.3 hotspot (extreme tail, all unfavorable assumptions stacked) | 104.0°C | **−1°C under rating** | ~1,860h (≈rated) |

**The capacitors do not bind in the realistic operating range.** They only
approach their rated condition in the compound-worst-case tail (85°C
chassis ambient — which SYSTEM_THERMAL_BUDGET itself calls the "design
limit... emergency shutdown" condition, not continuous operation — stacked
with the least favorable emissivity, geometry, and lead-conduction
assumptions simultaneously). This contradicts the task brief's framing
that capacitors are "usually the binding constraint" — that expectation
does not hold once the actual (larger, 152×234mm) board geometry and its
correspondingly larger compartment surface area are used; it may have held
under the stale 100×150mm board figure, which gives a compartment about
1/6th the surface area and correspondingly higher ΔT (see §1.1, §5).

### 3.5 ESP32-S3

Module rated -40 to +85°C ambient (`docs/hardware/COMPONENT_COMPATIBILITY_
VERIFICATION.md` **[repo]**), P=0.5W. Using the plain wall-ΔT (not ×1.3 —
same reasoning as §3.4, a low-power, board-spread part): Q=9.65W, Ta=70°C,
ε=0.5 → 81.6°C, **3.4°C margin** to the 85°C module rating. At ε=0.2:
86.4°C, **−1.4°C**, i.e. over rating. Marginal in the same band as the
other parts.

### 3.6 Binding-constraint summary

| Component | Central-case margin at Ta=70°C, Q=9.65-12W, ε=0.5 | Binds? |
|---|---|---|
| **LMR51430 (w/ copper pour)** | **+2.4°C to −0.8°C** | **Yes — first, or tied for first** |
| **UCC21550 gate driver** | **+... to −38°C (θJA-dependent, unresolved)** | **Yes — possibly worst, but underspecified** |
| XC6220 LDO | +6.4°C | Thin but positive |
| ESP32-S3 | +3.4°C to −1.4°C (ε-dependent) | Marginal |
| Electrolytic bus caps | +23.4°C (life, not Tmax) | No — comfortable except extreme tail |

---

## 4. Viability verdict

**Marginal.** Not "viable" outright, not "not viable" outright.

- **At normal/typical kitchen ambient (chassis air ≤ ~50–55°C,
  `docs/ENVIRONMENTAL_SPEC.md`'s rated 25–40°C plus SYSTEM_THERMAL_BUDGET's
  "warm kitchen" 40–55°C band):** every component in §3 clears its rating
  with real margin (LMR51430 with pour: >10°C; ESP32, LDO: comfortable;
  caps: not a concern). **Viable** in this band.
- **At the repo's own "worst case" 55–70°C ambient band (called out as a
  live, if extended/limited-duration, operating condition — not an
  emergency state):** LMR51430 and, on an admittedly under-sourced θJA
  assumption, the UCC21550 gate driver have **zero to slightly negative
  margin** under central assumptions, and clearly negative margin under
  the unfavorable (bare LMR51430 layout, ε=0.2, θJA=70°C/W) end of the
  sweep. **Not comfortably viable here without the mitigations below.**
- **At the 85°C "design limit" band:** multiple parts exceed rating in
  most scenarios — but SYSTEM_THERMAL_BUDGET itself already treats 85°C as
  an emergency-shutdown condition today, forced-air-cooled or not, so this
  is not a new failure introduced by sealing.

### What would decide it (if pursued)

1. **Confirm whether the LMR51430's copper-pour mitigation is actually
   laid out on the real board** (not independently checked here against
   `pcb/temper.kicad_pcb`'s copper zones) — this alone is the difference
   between +2.4°C and −15°C of margin at the central case.
2. **Source a real UCC21550 θJA** (TI datasheet, package DWK) instead of
   the assumed 45–70°C/W range — this is the single highest-leverage
   unknown in the whole analysis given how wide that assumed range is.
3. **Resolve the board-size/chassis-size discrepancy** (§5) — it changes
   the compartment surface area, and hence every ΔT in this document, by
   roughly a factor of 6 depending on which figure is trusted.

### Mitigations that do not reopen the forced-air path

- **Conduction to chassis metal**, not air: a thermal pad or direct
  metal standoff from the LMR51430's/gate driver's ground copper to the
  (presumably metal) RCA 12A3 chassis wall would bypass the compartment's
  air-film resistance entirely for those two parts specifically — this is
  likely the single most effective, lowest-risk mitigation given §3.1/3.2
  identify these two as the binding parts.
- **Spreading copper**: enlarging the LMR51430's and UCC21550's copper
  pour/plane area (SYSTEM_THERMAL_BUDGET §7.3 already specifies minimums;
  going beyond them, especially tying into a larger board-edge pour with
  more thermal vias, directly lowers each part's effective θJA).
- **Relocating the hottest parts** toward the compartment's larger
  external surfaces (nearer a chassis wall/vent-adjacent panel) rather
  than centrally, to shorten the internal-film path in §1.5.
- **High-emissivity finish** on the partition's interior/exterior
  surfaces (e.g. matte black or textured paint rather than bare/anodized
  aluminum) — the ε=0.2→0.9 sweep in §1.4 is worth 4–8°C by itself, free
  of any component-level change.
- Explicitly **not proposed**: any vent, gap, or airflow path between the
  compartment and the duct — that would reopen the exact exposure the
  compartment exists to close, and is out of scope per the task brief.

---

## 5. What this calculation cannot settle

- **Real internal airflow pattern.** §1.5's ×1.0–1.5 internal-film
  multiplier is engineering judgment, not measurement — a sealed box's
  actual internal convective pattern (natural circulation cells, whether
  the IGBT-adjacent zone locally recirculates hotter air onto the LMR51430
  if they are placed close together, per the LMR51430 doc's own >50mm
  keep-out recommendation) is empirical. This is the single largest
  unquantified uncertainty in the chain.
- **Whether a physical partition actually excludes pollution in service.**
  This document assumes the *thermal* prerequisite question in isolation;
  whether any given partition design would also satisfy the IEC 60335-2-6
  cl. 29.2 enclosure exception (sealing quality, ingress at cable
  penetrations, long-term gasket integrity) is a mechanical/regulatory
  question this calculation does not touch and was explicitly told not to
  decide.
- **Real hot spots.** The lumped, single-surface-temperature model in §1
  cannot resolve local component-to-component gradients (e.g. whether the
  LMR51430 sees materially different air than the ESP32 8cm away) — only
  a CFD study or physical prototype with thermocouples would.
- **The IGBT lead/tab electrical topology** (§2.3) — whether the tab
  shares a leadframe node with a lead, as assumed, or is a fully isolated
  die pad — is a manufacturer-outline-drawing fact not available in this
  repo, and materially changes the size (though not the direction) of the
  §2 conduction estimate.
- **Whether the copper-pour recommendation for the LMR51430 is actually
  implemented on the real board.** Not checked here; directly gates §3.1's
  verdict.
- **A real UCC21550 θJA.** Assumed, not sourced, and the single widest
  range in this document (45–70°C/W, a >4× spread in the resulting ΔT
  contribution).
- **Actual chassis wall material/finish and true internal dimensions.**
  Both swept as explicit ranges (§1.1, §1.4) rather than pinned down,
  because no repo document gives them for a hypothetical partition that
  does not exist yet.

Nothing above was guessed silently — every number in §1–§4 traces to either
a cited repo figure or an explicitly labeled `[assumed]` value with its
range stated. Where the assumption range is wide enough to flip the
verdict (LMR51430 copper-pour status, UCC21550 θJA), that is called out
rather than resolved by picking the convenient end.
