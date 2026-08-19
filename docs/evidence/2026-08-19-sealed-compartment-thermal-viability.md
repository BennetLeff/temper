<!-- provenance: base commit=f5488973e (origin/main), branch
     analysis/sealed-compartment-thermal, fresh worktree cut from origin/main.
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after; the board file was never opened for writing.
     NO clearance, creepage, copper-weight, DRU or ratchet threshold was changed.
     MIN_BARRIER_WIDTH_MM is 12.6 and remains 12.6. No _*_py_oracle.py was
     touched. No test was skipped, xfailed or relaxed. git stash never invoked.
     Only two files are added: this document and its companion script. -->
---
module: thermal
tags: [thermal, enclosure, pollution-degree, pd2, pd3, gate-driver, analysis-only]
problem_type: engineering-analysis
---

# The sealed PCB compartment is thermally viable, and the two parts that made it look marginal were both mis-specified — one by 12x, one by 5x. The verdict rests on the datasheets, not on the enclosure model.

**Verdict: VIABLE at the committed 60 °C ambient, with the binding part
carrying +42 °C of junction margin under every unfavourable assumption in the
2026-07-30 sweep stacked simultaneously.** The result does *not* depend on
resolving the enclosure model's soft assumptions, because the corrected part
dissipations are 3-7x below the level at which any of them would matter (§5).

**This does not reclassify anything.** PD3/12.6 mm remains enforced and
`MIN_BARRIER_WIDTH_MM` is untouched. Ground (a) of the 2026-08-15 decision —
the compartment is unbuilt — is unaffected by this document and remains
sufficient on its own for PD3 to govern today. What changes is ground (b):
**"thermally counterproductive" is now positively refuted, not merely
unestablished.** The 2026-08-18 re-examination
(`analysis/pd2-pd3-cost-reexamination`) correctly found ground (b) unproven;
this document closes the three steps it named as sufficient to settle it.

---

## 1. Summary of what moved

| Quantity | Value the 2026-07-30 bound used | Value from primary sources | Factor |
|---|---|---|---|
| UCC21550 dissipation | 1.5 W [`SYSTEM_THERMAL_BUDGET.md` §3.4] | **0.121 W** (TI SLUSE89C §8.2.2.5) | **12.4x lower** |
| UCC21550 θJA | 45–70 °C/W [assumed] | **74.1 °C/W** (SLUSE89C §5.4, DWK) | 1.06–1.65x higher |
| LMR51430 dissipation | 1.0 W [`LMR51430_THERMAL_ANALYSIS.md`] | **0.15–0.22 W** (as-built operating point) | **~5x lower** |
| LMR51430 θJA | 80 °C/W [2-layer note] | **107.8 °C/W** (SLUSF4A §7.4, JEDEC) | 1.35x higher |
| XC6220 LDO, 0.65 W | in the budget | **part is not in the design** | removed |
| Ambient | 70 °C [superseded band] | **60 °C** (`thermal_constants.rs:50`) | −10 °C |

**Both θJA corrections cut against the compartment. Both dissipation
corrections cut for it, and they are much larger.** That asymmetry is the
whole result, and it is why the verdict is robust rather than marginal.

Everything below is reproducible by running the committed companion script:

```
python3 docs/evidence/2026-08-19-sealed-compartment-thermal.py
```

This is the artifact the 2026-07-30 bound §1.3 said was "shown in full below"
and never committed. It reads no repo state; all inputs are literals, each
labelled `[repo]` (cited to a committed file) or `[assumed]`.

---

## 2. The 1.5 W vs 0.45 W disagreement — resolved, and both figures are wrong

Neither in-repo figure is the correct one. **The answer is 0.121 W**, and the
method is the manufacturer's own.

### 2.1 Where 1.5 W came from, and why it cannot be right

`docs/hardware/SYSTEM_THERMAL_BUDGET.md:129-130` (dated 2025-12-14) carries
two adjacent rows: "Gate charge current | ~300 mA average" and "Power
dissipation | ~1.5 W total (both channels)". The same 300 mA appears in
`docs/hardware/COMPONENT_COMPATIBILITY_VERIFICATION.md:62` as "Gate driver
switching | 300 mA | Average, VDD side" and in
`docs/hardware/LMR51430_THERMAL_ANALYSIS.md:73` as a *rail load* line item.
1.5 W = 300 mA x 5 V. **It is a supply-rail current budget re-used as a
package dissipation figure**, and the current itself is wrong:

> Average gate-drive supply current = 2 x QG x fSW = 2 x 185 nC x 50 kHz
> = **18.5 mA**, plus ~5 mA quiescent = **~23.5 mA** — not 300 mA.

Two independent refutations, neither requiring my arithmetic to be trusted:

1. **1.5 W exceeds the part's absolute maximum.** SLUSE89C §5.5 gives
   `PD` (maximum power dissipation, both sides) = **950 mW**, with
   `PDA`/`PDB` = 450 mW each driver side and `PDI` = 50 mW transmitter side.
   A steady-state dissipation of 1.5 W is 58 % above the absolute-maximum
   rating; it is not an operating point, it is a destroyed part.
2. **It contradicts the repo's own IGBT datasheet recovery.**
   `components/IKW40N120H3/IKW40N120H3_Documentation.md:151` already computes
   "Pgate = QG x VGE x fsw ~= 185 nC x 15 V x 50 kHz ~= 0.14 W (negligible)"
   — and that is the *whole gate loop* for one device, most of which is
   dissipated outside the driver package.

### 2.2 Why 0.45 W is also wrong — it ignores the external gate resistor

`components/UCC21550/UCC21550_Documentation.md:1620-1640` works
`P_GATE = 2 x VDD x QG x fSW = 300 mW` and adds ~150 mW quiescent for
450 mW. That treats **all** gate-loop loss as landing in the driver. The
datasheet is explicit that it does not (SLUSE89C §8.2.2.5):

> "PGDO will be equal to PGSW if the external gate driver resistances are
> zero, and all the gate driver loss is dissipated inside the UCC21550. If
> there are external turn-on and turn-off resistances, the total loss will be
> distributed between the gate driver pull-up/down resistances and external
> gate resistances."

### 2.3 The correct calculation (TI SLUSE89C §8.2.2.5, eq. 11–17)

Inputs, all `[repo]`:

| Symbol | Value | Source |
|---|---|---|
| VDD | 15 V | `elec/src/modules.ato` GateDriveHS: boot cap charges to full VDD (15 V); 5.1 V zener sets VSSA = emitter − 5.1 V, so rail-to-rail swing is 15 V. TI eq. 12 note: for a split rail, VDD = positive rail − negative rail. |
| QG | 185 nC | `components/IKW40N120H3/IKW40N120H3_Documentation.md:73` (at VCC = 960 V, IC = 40 A) |
| fSW | 50 kHz | `docs/hardware/RESONANT_TANK_DESIGN.md:20` (38–50 kHz), upper bound |
| RON | 2.2 Ω | `elec/src/modules.ato:160` (GateDriveHS `rg_on`) and `:218` (GateDriveLS `rg_on`) |
| ROFF | none | **No separate turn-off resistor or diode bypass exists in either module** — turn-off returns through the same 2.2 Ω. TI's worked example used ROFF = 0; this board's lack of a bypass keeps *more* loss out of the driver. |
| ROH / ROL / RNMOS | 5 Ω / 0.55 Ω / 1.47 Ω | SLUSE89C §5.8 and eq. 5/6 |
| VCCI | 3.3 V | `elec/src/modules.ato` — `c_vcci1` ties to `power_3v3.vcc`; §252 comment "VCCI is the 3.0–5.5 V control-side supply" |
| IVCC / IVDDx | 4.8 / 2.5 mA **max** | SLUSE89C §5.8 (datasheet maxima, not typicals) |

```
PGSW = 2 x VDD x QG x fSW                    = 277.5 mW   (eq. 12, whole gate loop)
PGDQ = VCCI.IVCCI + VDDA.IDDA + VDDB.IDDB    =  90.8 mW   (eq. 11)
PGDO = (PGSW/2) x (frac_up + frac_down)      =  30.2 mW   (eq. 14)
PGD  = PGDQ + PGDO                           = 121.1 mW   (eq. 17)
```

**The board's Rg = 2.2 Ω is the same value as TI's own worked example**, so
the loss split is not an extrapolation.

**Sensitivity to the one unknown.** The IGBT's internal gate resistance
`RGFET_int` is not in this repo. TI's example uses 4.6 Ω. Bracketing it:

| RGFET_int | PGDO | **PGD** |
|---|---|---|
| 4.6 Ω (TI worked value) | 30.2 mW | **121.1 mW** |
| **0 Ω (worst case, no internal RG)** | 75.0 mW | **165.8 mW** |
| 0 Ω *and* RON = 0 (physically impossible — the 2.2 Ω is a fitted part) | 277.5 mW | 368.3 mW |

**Even the impossible ceiling is below the 0.45 W in-repo figure, and 4x
below the 1.5 W one.** This unknown cannot flip anything.

**Two further conservatisms, both stated so they are not mistaken for
precision:** QG = 185 nC is specified at VCC = 960 V, whereas this board's DC
bus is 170 V (`SYSTEM_THERMAL_BUDGET.md` §2.1) — Miller charge scales with
VCE, so the real QG is materially lower. And datasheet *maximum* quiescent
currents were used throughout. Both push the true figure below 121 mW.

---

## 3. The correct θJA figures — checked, not inherited

| Part | Refdes | θJA | Source |
|---|---|---|---|
| UCC21550BDWK | U6 | **74.1 °C/W** | SLUSE89C §5.4, DWK 14-pin. TJ max 150 °C (§5.3). |
| LMR51430XDDC | U3 | **107.8 °C/W** | SLUSF4A §7.4, DDC SOT-23-6, 4-layer JEDEC. |
| XC6220 LDO | — | **n/a — not in the design** | `elec/src/modules.ato:46` "Removed: LDO3V3 replaced by BuckConverter3V3 (plan 005)"; also `:1424`, `:1539`. |

Refdes identities verified directly against the board file (read-only):
`pcb/temper.kicad_pcb:7967-7972` — U6, footprint `lib:SOIC16W_Isolated`,
sheetpath `hb.gate_hs.driver`, whose descr names "TI UCC21550BDWK, 14-pin DWK
package (SLUSE89C, Aug 2024)". `pcb/temper.kicad_pcb:7832-7835` — U3,
footprint `Package_TO_SOT_SMD:SOT-23-6`, sheetpath `power_mgmt.buck_3v3.buck`.
**Both carry `(property "Value" "?")`** — the board does not encode either
part's identity, which is why refdes-keyed thermal tables have drifted.

Notes that matter:

- **The LMR51430 θJA correction is against the compartment and is adopted
  anyway.** `LMR51430_THERMAL_ANALYSIS.md:31` uses 80 °C/W citing the
  datasheet's "2-layer PCB" note. This board is **6-layer**
  (`pcb/temper.kicad_pcb:8-14`: F.Cu, In1–In4.Cu, B.Cu). TI states plainly
  that the JEDEC number "cannot be used for design purposes"; 107.8 °C/W is
  used here as the conservative bracket rather than the more favourable 80.
- **`temper-thermal`'s U6 mapping is non-conservative by ~77x.**
  `packages/temper-thermal/src/thermal_constants.rs:179-181` maps
  `"Q1" | "Q2" | "U4" | "U5" | "U6"` to the IKW40N120H3 TO-247 stackup,
  resolving to (Rjc, Rch, Rha) = (0.31, 0.20, 0.45) = **0.96 K/W total** —
  a fan-cooled heatsink resistance — for a SOIC-14 gate driver whose real
  θJA is 74.1 °C/W. The `Q1`/`Q2` entries carry the same class of error
  (the comment at `:172-174` concedes "the SOT-23 parts that hold those
  designators on the current board are not the power devices"). **Recorded,
  not fixed** — the mapping is pinned by
  `refdes_lookup_matches_python_table` at `:295-314` and is another agent's
  surface. No figure in this document comes from that table.

---

## 4. The as-built dissipation budget

`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §1 is dated 2025-12-14 and its
PCB-resident line items no longer describe this design.

| Line item | Budget (2025-12-14) | As-built | Basis |
|---|---|---|---|
| Gate drivers | 1.5 W | **0.12 W** | §2.3 |
| LMR51430 buck | 1.0 W | **0.15–0.22 W** | §4.1 |
| XC6220 LDO | 0.65 W | **0 W** | part removed from design |
| ESP32-S3 | 0.5 W | 0.5 W | unchanged |
| EMI filter | 2.0 W | 2.0 W | **not re-derived — see §7** |
| Capacitor ESR | 4.0 W | 4.0 W | **not re-derived — see §7** |
| AuxSupply flyback | *absent* | **~0.7–1.0 W [estimated]** | added by plan 005; not in the budget |
| IGBT lead conduction | *absent* | 0.7–2.3 W | 2026-07-30 bound §2.2 |

**The total is roughly unchanged (~9–11 W) while the composition is
substantially different.** The reductions on the two IC line items are
approximately offset by the newly-added isolated flyback and the IGBT lead
leak. **This document therefore keeps the 2026-07-30 bound's Q = 9.65 W and
Q = 12.0 W cases unaltered**, so the enclosure ΔT table is directly
comparable to the prior analysis and no credit is taken for the reduction.

### 4.1 The buck's real operating point

`docs/hardware/LMR51430_THERMAL_ANALYSIS.md:66-90` derives 1.0 W from
**VOUT = 5.0 V, IOUT = 1.2 A (6.0 W out)**. That is not this board:

- `elec/src/modules.ato` `BuckConverter3V3` sets `power_out.voltage = 3.3V` (`:1440`)
  and uses "TI Table 9-1 (Vout=3.3V, fsw=500kHz)".
- The 3.3 V rail load is **254 mA**
  (`docs/hardware/COMPONENT_COMPATIBILITY_VERIFICATION.md:56-65`: ESP32-S3
  150 + MAX31865 2 + ADUM1250 2 + misc 100 mA); 380 mA is carried as the
  conservative figure from the same table.
- **Pout = 3.3 V x 0.254 A = 0.84 W**, versus the 6.0 W the analysis assumed.

Total *system* loss (IC + inductor + output caps) by efficiency:

| IOUT | η | System loss |
|---|---|---|
| 254 mA | 0.85 | 148 mW |
| 380 mA | 0.85 | 221 mW |
| 380 mA | 0.75 (pessimistic) | 418 mW |

Conduction loss alone, from `RDSON(HS)` = 0.12 Ω / `RDSON(LS)` = 0.07 Ω
(SLUSF4A §7.5) at D = 3.3/15 with a 1.5x hot-Rdson factor, is 8–18 mW —
consistent with the efficiency figures. **0.20 W is used as the IC figure;
§5 shows the verdict survives even if the entire 418 mW pessimistic system
loss were attributed to the IC alone.**

---

## 5. The verdict at the committed 60 °C ambient

Ambient is 60 °C: `packages/temper-thermal/src/thermal_constants.rs:50`
`DEFAULT_AMBIENT_C = 60.0`, set by
`docs/evidence/2026-08-15-thermal-threshold-decision.md` §6.4, matching
`docs/ENVIRONMENTAL_SPEC.md` §1.1's zero-power derating point. **The
2026-07-30 bound's 70 °C headline was superseded the same day it was
inherited and appears only in `SYSTEM_THERMAL_BUDGET.md:52`.**

### 5.1 Compartment wall rise at 60 °C

Same closure as the 2026-07-30 bound (`Q = h·A·ΔT + εσA(Ts⁴ − Ta⁴)`,
`h = 1.42·(ΔT/Lc)^0.25`), now committed and re-run at 60 °C:

| Geometry | Q | ε=0.2 | ε=0.5 | ε=0.9 |
|---|---|---|---|---|
| Compact (152x234x33 mm, A = 966 cm²) | 9.65 W | 16.8 °C | 12.1 °C | 8.8 °C |
| Compact | 12.0 W | 20.2 °C | 14.7 °C | 10.7 °C |
| Generous (172x254x50 mm, A = 1300 cm²) | 9.65 W | 13.3 °C | 9.4 °C | 6.7 °C |
| Generous | 12.0 W | 15.9 °C | 11.4 °C | 8.2 °C |

Applying the bound's own ×1.3 internal-film factor `[assumed]`:

- Central (compact, Q = 9.65 W, ε = 0.5): **local ambient 75.8 °C**
- **Worst (compact, Q = 12.0 W, ε = 0.2): local ambient 86.2 °C** — every
  unfavourable assumption stacked simultaneously.

### 5.2 Junction margins, evaluated at the *worst* local ambient (86.2 °C)

| Part | P | θJA | Tj | Margin to 150 °C |
|---|---|---|---|---|
| **UCC21550** (as-built) | 0.121 W | 74.1 | **95.2 °C** | **+54.8 °C** |
| UCC21550 (RGFET_int = 0) | 0.166 W | 74.1 | 98.5 °C | +51.5 °C |
| *UCC21550 (stale 1.5 W)* | *1.5 W* | *74.1* | *197.4 °C* | *−47.4 °C* |
| **LMR51430** (as-built) | 0.20 W | 107.8 | **107.8 °C** | **+42.2 °C** |
| *LMR51430 (stale 1.0 W / 80 °C/W)* | *1.0 W* | *80.0* | *166.2 °C* | *−16.2 °C* |

The central case is a further 10.4 °C cooler.

### 5.3 Why this verdict does not rest on the enclosure model

The honest weakness of the 2026-07-30 bound was that its answer sat inside
its own assumption spread. This one does not. Inverting the question — **at
what dissipation would each part reach Tj(max) = 150 °C at the worst local
ambient?**

| Part | Breakeven P | As-built P | Headroom |
|---|---|---|---|
| UCC21550 | **861 mW** | 121 mW | **7.1x** |
| LMR51430 | **592 mW** | 200 mW | **3.0x** |

The LMR51430's breakeven (592 mW) exceeds the **entire pessimistic system
loss** of its own converter stage (418 mW at η = 0.75) — so the part passes
even under the physically impossible assumption that the inductor and output
capacitors dissipate nothing and every watt lands in the SOT-23-6.
The UCC21550's breakeven (861 mW) is below its own datasheet `PD` maximum
of 950 mW, meaning **the part's absolute-maximum dissipation rating is a
tighter constraint than the sealed compartment is.**

The remaining soft assumptions — the `h` correlation, emissivity, the ×1.3
internal-film factor, the compartment envelope — would each have to be wrong
by a factor of 3 or more, *in the same direction*, to threaten either part.
The full ε = 0.2→0.9 sweep spans 9.5 °C of local ambient; closing 42 °C of
margin requires far more than the model's total spread.

### 5.4 The other compartment residents

Unchanged from the 2026-07-30 bound §3.4/§3.5 and re-checked at 60 °C, where
every figure improves by ~10 °C:

- **Electrolytic bus capacitors** (105 °C, 2000 h): worst case 60 + 20.2 =
  80.2 °C, 24.8 °C under rating — comfortable. They do not bind.
- **ESP32-S3** (85 °C module rating): worst case 80.2 °C, **+4.8 °C**. At
  the central case, 72.1 °C (+12.9 °C). **This is now the thinnest margin in
  the compartment** — the 60 °C ambient rescues it (at 70 °C it was
  negative), but it is a module *ambient* rating with no θJA to spend, and it
  is the part to watch, not the ICs. See §7.
- **XC6220 LDO**: not in the design; its +6.4 °C entry is void.

---

## 6. Can `temper-thermal` be extended to answer this? — No, and it should not be

**Structurally unable, and the honest path is not to extend it.** Verified in
source (survey of `packages/temper-thermal` + `temper_placer/physics`):

1. **No enclosure node can exist.** Both assemblers are 5-point stencils on a
   2-D board plane dimensioned `n = height_cells * width_cells`
   (`fdm.rs:66`, `thermal_scorer.rs:291`), solved by one direct sparse LU
   (`solve.rs:31-76`). Ambient is a scalar Dirichlet reservoir at every
   boundary term (`fdm.rs:96,110,124,138,147`;
   `thermal_scorer.rs:323,337,351,365,373,381`). **The model cannot represent
   internal air rising above `ambient_C` — which is the entire question.**
   Adding an `n+1`-th unknown changes the returned `n` contract of two Rust
   assemblers, two Python `shape=(n,n)` computations, the solution reshape,
   and every verbatim differential oracle pinning them.
2. **`h` is a constant, and the solver is linear by construction.**
   `CONVECTION_COEFFICIENT_H_W_PER_M2K = 10.0`
   (`validation/thermal_scorer.py:93`) and `H_CONV_BACKGROUND = 10.0`
   (`heat_removal.rs:57`). A ΔT-dependent `h` makes `A = A(T)`, requiring an
   outer Picard/Newton loop that was deliberately *removed* — the iteration
   fields at `validation/thermal_scorer.py:172-174` are marked "unused in
   convective model" and `_convective_fdm_solve` returns `(T_grid, 0, 0.0)`.
3. **No radiation anywhere.** Zero hits for
   `emissiv|stefan|boltzmann|5.67|rayleigh|nusselt|grashof|prandtl|buoyan` in
   any `.rs` or `.py`. `validation/thermal_scorer.py:105` states the
   assumption outright: "Conduction-only in-plane (no internal convection or
   radiation)". Radiation carried 30–50 % of the heat removal at ε = 0.9.
4. **Every power device's Rha assumes a fan.** `HS1_RHA_KW = 0.45`
   (`thermal_constants.rs:76`) is documented as "forced convection (fan)",
   and there is no natural-convection alternative constant.

**Why extending it is the wrong path even so.** Changing `h` from a constant
collides with a live falsifiability contract: `STRUCTURAL_INDEPENDENCE_AXIS`
(`validation/thermal_scorer.py:124-133`) *defines* the U5/U7 independence
claim as the `h=0` vs `h=10` difference, with
`FALSIFIABILITY_THRESHOLD_C = 1.0`. The comment at `:91-92` is explicit:
"This is a FIXED value, never tuned to pass a test. Changing it would require
a commensurate update to the falsifiability threshold." **Rebuilding a
placement scorer into an enclosure simulator to answer a one-off mechanical
question would damage a gate that currently works, to reproduce arithmetic
that fits on one page.** The committed 235-line script is the proportionate
artifact.

The one genuinely cheap extension, recorded for whoever wants it: a
**frozen-`h_rad` radiation term** (`εσ` linearized at an assumed surface
temperature) slots into the existing `diag +=` / `b[idx] +=` pattern at
`thermal_scorer.rs:370-374` as a ~5-line change plus one new constant. It
still would not model an enclosure.

---

## 7. What this document does not settle

Stated plainly, because the margins above are large enough that these are
open items rather than threats to the verdict:

1. **The EMI filter (2.0 W) and capacitor ESR (4.0 W) were not re-derived.**
   They are now ~70 % of the compartment's heat load and they carry the same
   2025-12-14 provenance as the two figures this document found to be wrong
   by 12x and 5x. **They are the largest remaining unverified inputs.** They
   were left at their budget values because that is the conservative
   direction for compartment ΔT — but nobody should cite them as measured.
2. **The AuxSupply flyback dissipation (~0.7–1.0 W) is `[estimated]`**, not
   derived. It is a real load that no committed budget includes.
3. **The ESP32-S3 is now the thinnest margin** (+4.8 °C worst case) and it is
   an 85 °C *module ambient* rating — there is no θJA to trade against it,
   and it responds only to compartment ΔT. If any of §7.1's figures is
   revised *upward*, this is the part that binds first, not the ICs.
4. **`RGFET_int` for the IKW40N120H3 is not in this repo.** Bracketed in
   §2.3; cannot flip the verdict.
5. **The enclosure model is unchanged and still unvalidated.** The `h`
   correlation, ε, the ×1.3 internal-film factor and the envelope are the
   same `[assumed]` values as 2026-07-30. §5.3 is the argument that the
   verdict no longer depends on them — not a claim that they were validated.
6. **The board/chassis dimension conflict is unresolved** (2026-07-30 §5): a
   234 mm board in a stated 230 mm chassis. Both envelopes here are
   `[assumed]`.
7. **Sealing quality, gasket integrity and ingress at cable penetrations are
   mechanical/regulatory questions** this document does not touch. Thermal
   viability is one half of the PD2 prerequisite; **the compartment is still
   unbuilt, and PD3 still governs.**
8. **No physical measurement exists.** This is a hand calculation, as its
   predecessor was. What is different: it is committed and re-runnable, it
   uses the committed 60 °C ambient, its θJA figures are datasheet values,
   and its conclusion survives its own assumption sweep by 3–7x.

---

## 8. Recommended follow-ups (none performed here)

- Correct `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §1/§3.4: gate drivers
  1.5 W → 0.12 W with the SLUSE89C §8.2.2.5 citation; strike the "~300 mA
  average" row; remove the XC6220 line; add the AuxSupply flyback.
- Re-point `docs/hardware/LMR51430_THERMAL_ANALYSIS.md` to the as-built
  3.3 V / 254 mA operating point; its 5.0 V / 1.2 A premise is stale.
- Fix `thermal_constants.rs:179-181` — `U6` (and `Q1`/`Q2`) must not resolve
  to a fan-cooled TO-247 stackup. Owned elsewhere; flagged again here with a
  measured magnitude (0.96 K/W vs a real 74.1 °C/W).
- Give U3 and U6 real `Value` properties; `"?"` on both is the root cause of
  the refdes drift in §3.
