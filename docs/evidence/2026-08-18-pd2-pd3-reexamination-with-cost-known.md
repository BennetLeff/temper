<!-- provenance: commit=ce278aa09354c5f46aaebcb127780c4b16962808 dirty=false (own worktree
     .claude/worktrees/pd2-pd3-reexam, branch analysis/pd2-pd3-cost-reexamination, cut fresh
     from origin/main @ ce278aa09). pcb/temper.kicad_pcb sha256=
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified before and
     after; the board file was NEVER opened for writing. pcb/temper.kicad_dru regenerated
     in-worktree from the unmodified scripts/generate_kicad_dru.py (gitignored and generated;
     creepage reads 0 without it) -- git check-ignore confirmed before and after.
     Environment: make venv-isolate + make extensions (both exit 0). temper_geometry initially
     failed to import despite check_stale_extensions.py reporting fresh -- the known
     PyInit_temper_geometry symbol failure; resolved by cargo clean -p temper-geometry plus a
     rebuild against a private CARGO_TARGET_DIR under /tmp (the shared target-shared/ dir was
     under concurrent write by another agent and kept returning a stale artifact in 0.04s).
     Every distance below was computed with the canonical kernels named in the task brief --
     temper_placer.core.pad_geometry.pad_pair_distance (temper-geometry Rust) and
     temper_placer.core.pin_geometry.pin_world_position -- via a throwaway harness under the
     session scratchpad, never committed. scripts/measure_cross_domain_creepage.py was NOT
     used (known-broken rotation convention and violation-list filter; another agent owns it).
     NO clearance, creepage, copper-weight, DRU, or ratchet threshold was changed by this
     document: MIN_BARRIER_WIDTH_MM is 12.6 at line 47 and HV_CREEPAGE_ENFORCED_MM is
     HV_CREEPAGE_PD3_MM at line 152, both untouched. No pinned _*_py_oracle.py was touched.
     No test was skipped, xfailed, or relaxed. git stash was never invoked. -->
---
module: safety
tags: [creepage, pollution-degree, pd2, pd3, iec-60335, isolation, analysis-only]
problem_type: standards-determination
---

# PD3 stands. The new cost data does not touch the classification — but it does refute one of the 2026-08-15 decision's two supporting grounds, and it relocates the critical path onto a free external answer nobody has chased.

**Decision, up front: PD3/12.6 mm remains correct and I changed nothing.** The
classification question and the cost question are separate, and the newly-measured
cost bears on neither the standard's condition nor the board's construction. What the
cost data *does* do is expose that the 2026-08-15 decision rested on two grounds, one
of which does not survive scrutiny, and that the PD3 remediation is currently blocked
on a certification-lab question that has been drafted, never sent, and is free.

Three of the task brief's premises did not reproduce and should not be planned against
(§5). Two of them materially understate what PD3 costs; one materially overstates it.

---

## 1. What the 2026-08-15 decision measured, and what it assumed

`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md` is sound on its central
claim and I am not overturning it. But the task asks precisely what it measured versus
assumed, so:

**The enclosure geometry was neither measured nor assumed — it was read out of the
committed design documents, and there is no physical enclosure to measure.** Its §2.1
cites `docs/COIL_BRACKET_DESIGN.md` §4 and `docs/CHASSIS_AIRFLOW_DESIGN.md` §3.3 for
"forced-air vented with no cover/gasket/partition", and verifies absence three ways
against real repo state: no `docs/specs/pd2_compartment_evidence.yaml`,
`check_pd2_compartment_evidence.py` exit 3, `check_isolation_keepout.py` exit 3. All
three are direct reads of committed state, correctly done. **Re-verified this session
on the current board** (`ce278aa09`, board `26981fea…`):

- `Edge.Cuts` carries exactly one element, a plain rectangle
  `(xy 8 20) (xy 172 20) (xy 172 254) (xy 8 254)` — it is the only `gr_*` element in
  the file. Zero internal cutouts.
- `np_thru_hole` count = **4**; `drill oval` count = **0**. All four NPTH pads are
  K1's relay mounting holes. **No milled slot exists anywhere on the board.**
- `check_isolation_keepout.py`, run live: `MAINS_SELV_ISOLATION_BARRIER` not found;
  1 violation; FAILED.

**It did consider the sealed compartment and rejected it — on two grounds, not one.**
Ground (a): unbuilt. That is a correct, verified read of repo state and it is
sufficient on its own to make PD3 govern *today*. Ground (b): "thermally
counterproductive" (§2.2, and the headline). **Ground (b) does not survive scrutiny.**

---

## 2. Ground (b) — "thermally counterproductive" is not established, and the repo cannot currently establish it

The task's question 3 asked whether the sealed-compartment prerequisite is thermally
viable and instructed me to say so plainly if the thermal model cannot answer. **It
cannot.**

### 2.1 `packages/temper-thermal` cannot model this case at all

Four independent structural reasons, each verified in source:

1. **No enclosure exists in the model.** The domain is a 2-D board plane
   (`fdm.rs` / `thermal_scorer.rs` / `heat_removal.rs`, 5-point stencil, Dirichlet
   heatsink face, Neumann or Robin edges) plus a 1-D resistance ladder
   (`junction_temp.rs:73`, `Ts = Ta + P·Rha`). There is no compartment wall, no
   enclosed-air node, no wall-to-outside-ambient resistance. `ambient_C` is applied
   directly at the board edges. The compartment's entire ΔT — the whole subject of the
   question — has nowhere to live.
2. **No radiation.** Grepping `packages/temper-thermal/src/` and
   `temper_placer/physics/` for `emissiv|stefan|boltzmann|radiat|5.67|rayleigh|nusselt|grashof|prandtl|buoyan`
   returns zero hits. Radiation supplied roughly 30–50 % of the heat removal in the
   2026-07-30 balance at ε = 0.9.
3. **`h` is a fixed constant, not ΔT-dependent.**
   `CONVECTION_COEFFICIENT_H_W_PER_M2K = 10.0`
   (`temper_placer/validation/thermal_scorer.py:93`) and `H_CONV_BACKGROUND = 10.0`
   (`heat_removal.rs:57`). Free-convection-flavoured, but a constant, applied to the
   board — not the `h = 1.42·(ΔT/Lc)^0.25` closure an enclosure balance needs.
4. **Airflow is not a modelled parameter.** Forced vs natural enters this codebase only
   as `HS1_RHA_KW = 0.45`, documented in `thermal_constants.rs:74-76` as **forced
   convection (fan)**. There is no natural-convection alternative constant, and
   `parameter_bounds.rs:208` uses `"wind_speed"` as its canonical *unclassifiable*
   input.

It also has no thermal data for any part that would sit inside the compartment:
`thermal_constants.rs:146-198` knows only `IKW40N120H3`/TO-247 and TO-220; everything
else falls through to `PLACEHOLDER_RJC_RCH_RHA = (0.6, 0.25, 1.0)`. Worse, and
directly relevant here, `thermal_constants.rs:179` maps refdes **`U6` to the IGBT
stackup** — but on this board `U6` is `lib:SOIC16W_Isolated`, the UCC21550 gate driver
(`pcb/temper.kicad_pcb:7967-7972`; the TO-247 IGBTs are U4/U5). Asked for the gate
driver's temperature, the tooling would hand back a fan-cooled heatsink resistance of
0.45 K/W for a part that is not on a heatsink. **Recorded, not fixed — it is another
agent's surface.**

### 2.2 The only in-repo answer is a hand calculation that is not reproducible

`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md` §1.3 solves
`Q = h·A·ΔT + ε·σ·A·(Ts⁴ − Ta⁴)` by fixed-point iteration "(Python, shown in full
below…)". **That script was never committed.** Its §1.4 table cannot be reproduced
from any committed artifact.

Its assumption chain, using the document's own labels: assumed `h` correlation
("*not a repo figure*") → assumed enclosure envelope (152×234×33 mm) → assumed
emissivity (0.2–0.9, midpoint 0.5, "*no document specifies the chassis wall finish*")
→ an assumed **×1.3 internal-film multiplier** the document itself calls "*the weakest
link in the chain*" → an assumed θJA for the part that produces the worst number →
a power budget whose six line items carry no derivation.

### 2.3 Three specific defects in the number the 2026-08-15 decision inherited

1. **The UCC21550 θJA is in the repo, and it is worse than the assumed range.** The
   2026-07-30 doc §3.2 and §5 say "*no θJA given anywhere in this repo (confirmed
   absent by search)*" and rank it "*the single highest-leverage unknown*", then sweeps
   45–70 °C/W. `components/UCC21550/datasheet.pdf` (TI SLUSE89C Rev C, Aug 2024) §5.4
   gives **RθJA = 74.1 °C/W for the DWK 14-pin package** — which is the package on this
   board (`pcb/temper.kicad_pcb:7970`) — with TJ max 150 °C. So every UCC21550 figure
   in that analysis is optimistic. **This cuts against the compartment, not for it, and
   I state it plainly for that reason.**
2. **But the binding unknown has moved, and it is now unresolved in a direction nobody
   has flagged.** Two in-repo figures for the same dissipation:
   `SYSTEM_THERMAL_BUDGET.md` §3.4 says **1.5 W**;
   `components/UCC21550/UCC21550_Documentation.md:1630-1637` works an example at
   VDD 15 V / QG 200 nC / 50 kHz giving **0.45 W**. At the 2026-07-30 doc's own
   compartment local ambient of 85.1 °C and the datasheet 74.1 °C/W, that 3.3×
   disagreement is a **78 °C swing in Tj** (118.4 °C, +31.6 margin — versus 196.3 °C,
   −46 margin). *That arithmetic is mine, on cited inputs, and it is offered as a
   sensitivity, not a result.* Sourcing θJA did not settle this part; resolving the
   gate-driver dissipation would.
3. **The 70 °C headline is not the repo's ambient standard.** "55–70 °C" appears only
   in `docs/hardware/SYSTEM_THERMAL_BUDGET.md:52`, not in the normative
   `docs/ENVIRONMENTAL_SPEC.md` (10/25/40 °C rated, derate to 0 % at 60 °C). The
   committed tooling value is `DEFAULT_AMBIENT_C = 60.0` (`thermal_constants.rs:50`),
   set by a deliberate decision on **2026-08-15 — the same day as the PD2/PD3
   decision**, in `docs/evidence/2026-08-15-thermal-threshold-decision.md`. The
   2026-07-30 bound never ran the 60 °C case. Neither document cites the other.

### 2.4 Verdict on question 3

**UNANSWERABLE with current repo tooling.** Not "the compartment is fine" — I am
explicitly not claiming that, and finding #1 above points the other way. The correct
state is: *the sealed compartment's thermal viability is an open question with a
documented, honest range, and the 2026-08-15 decision cited it as a settled negative.*
Three repo-tractable steps would close it, none requiring CFD or new tooling:
(i) resolve the UCC21550's real dissipation (1.5 W vs 0.45 W); (ii) re-run the
2026-07-30 balance at the committed 60 °C ambient with θJA = 74.1 °C/W, and commit the
script this time; (iii) confirm the LMR51430 copper pour is actually laid out — the
2026-07-30 doc's own §4 item 1, still open, and worth +2.4 °C versus −15 °C of margin
on its own. (U3's `Value` property on the board is `"?"`, so the board does not even
carry that part's identity.)

---

## 3. The IEC basis, verbatim

### 3.1 What decides PD2 vs PD3

**IEC 60335-2-6 cl. 29.2 Addition**, the particular standard for cooking appliances.
CITED-PRIMARY, recovered in `docs/evidence/2026-07-30-pollution-degree-determination.md:83-85`
from IS 302-2-6:2009, the BIS identical adoption, fetched from
`https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf`:

> "29.2 Addition — The microenvironment is pollution degree 3 unless the insulation is
> enclosed or located so that it is unlikely to be exposed to pollution during normal
> use of the appliance."

And the Part 1 baseline it replaces, **IEC 60335-1 cl. 29.2**, same document lines
68-73, from IS 302-1:2008:

> "Appliances shall be constructed so that creepage distances are not less than those
> appropriate for the working voltage, taking into account the material group and the
> pollution degree… Pollution degree 2 applies unless: a) precautions have been taken
> to protect the insulation, in which case pollution degree 1 applies; and b) the
> insulation is subjected to conductive pollution, in which case pollution degree 3
> applies."

**The physical property that decides it is therefore whether the insulation is
"enclosed **or** located so that it is unlikely to be exposed to pollution during
normal use."** Two points worth recording, neither of which changes today's answer:

- The clause is **disjunctive**. The five release conditions in
  `docs/ENVIRONMENTAL_SPEC.md` §3.1 are the owner's chosen *sufficient* implementation
  of the first limb (a gasketed compartment). The clause also admits a "located so
  that" argument, which nobody in this repo has ever explored. It does not help today:
  `docs/COIL_BRACKET_DESIGN.md` §4 specifies an open-frame bracket with large
  triangular cutouts routing bottom-intake unfiltered kitchen air through the coil and
  on to the IGBT heatsink, across the cavity the PCB occupies, and
  `docs/ENVIRONMENTAL_SPEC.md` §3 declares IP20. That fails both limbs. But it is the
  one degree of freedom in the clause that has never been costed.
- `docs/ENVIRONMENTAL_SPEC.md` §3 still describes PD2 as the "*Owner-selected
  production architecture*" with "*PD3 remains mandatory if that compartment is not
  implemented and verified.*" That wording is consistent with enforcing PD3 today —
  the spec itself directs it.

### 3.2 The figures

**IEC 60335-1 Table 17** ("Minimum Creepage Distances for Basic Insulation", cl.
29.2.1–29.2.3), material group IIIa/IIIb, row iv (>250 V, ≤400 V) — as transcribed in
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:204-210` from IS 302-1:2008:

| | PD2 basic | PD2 reinforced | PD3 basic | **PD3 reinforced** |
|---|---:|---:|---:|---:|
| >250 V, ≤400 V | 4.0 | 8.0 | 6.3 | **12.6** |

Reinforced is doubled per **cl. 29.2.3**, verbatim
(`docs/evidence/2026-08-12-hv-hv-creepage-determination.md:152-154`):

> "**29.2.3** Creepage distances of reinforced insulation shall be at least double
> those specified for basic insulation in Table 17."

**Table 18** ("Minimum Creepage Distances for Functional Insulation", cl. 29.2.4 and
L-2) is transcribed in full at `2026-08-12-hv-hv-creepage-determination.md:188-207`
and governs the tank node only: at >500–800 V, IIIa/IIIb, **6.3 mm PD2 / 10.0 mm PD3**
— identical to Table 17, because the functional-insulation concession exists only
below 500 V and the tank measures 570.5 Vrms, 14 % above that cliff.

Per the task's own note: **Table 8 is Maximum Winding Temperature and is not a creepage
table.** It plays no part in this determination and I did not use it.

**IEC 60664-1 Annex L does not exist.** The Annex L in play is **IEC 60335-1's** —
"Guidance for the measurement of clearances and creepage distances", pp. 170–172. Only
its title and the captions of Figures L.1–L.3 are recovered; its body text is
**NOT OBTAINABLE**, with an exhaustive negative recorded in
`docs/evidence/2026-08-13-annex-l-and-ekmq-pulse-current-acquisition.md` §1 (archive.org
advancedsearch enumerating 32 `60335-1` items — only the 2008 Part 1 edition; BS EN /
AS-NZS / SANS adoptions behind paid vendors; ANSI CMV preview HTTP 403; BSI preview
HTTP 403; two free IEC preview PDFs both truncated at ≤ p. 13). **IEC 60664-4 is
likewise not obtainable** — only its public scope paragraph
(`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md` §2.5). "Not
obtainable" remains the correct answer for both and I did not reconstruct either.

---

## 4. The cost, independently re-measured

All figures below computed this session with `pad_pair_distance` +
`pin_world_position` against board `26981fea…`, exact copper-edge distance, 4 decimals.
They reproduce the task brief and `docs/evidence/2026-08-18-isolation-part-binding-pad-pairs.md`
exactly.

| part | footprint | pos / rot | binding pair(s) | **min** | **max (package best case)** | vs 12.6 |
|---|---|---|---|---:|---:|---|
| **C6** | `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` | (58.99, 186.51) 270° | 1/2 `PWR_RTN`↔`gnd` | **8.0000** | 8.0000 | −4.6000 |
| **K1** | `temper:Relay_SPST_Omron-G4A-E` | (82.0, 203.625) 0° | *none on copper* | n/a | n/a | n/a |
| **T1** | `temper:CST3015` | (45.26, 128.91) 90° | 1/4, 2/3 (tie) | **9.1000** | **12.4933** (1/3, 2/4) | −3.5000 / **−0.1067 at best** |
| **T2** | `temper:CST3015` | (92.0, 280.05) 0° | 1/4, 2/3 (tie) | **9.1000** | **12.4933** | same — **but off-board** |
| **U6** | `lib:SOIC16W_Isolated` (UCC21550BDWK) | (77.91, 122.43) 90° | 8/9 + 5 tied | **8.1000** | **11.7145** (9/1, 16/8) | −4.5000 / **−0.8855 at best** |

**The 8.0000 mm exactness is not coincidence, and the brief is right about that.**
C6's is arithmetic on the land: 2.0 mm circular THT pads on a 10.00 mm pitch →
10.00 − 2.00 = 8.0000. K1's 8.0000 (A1↔13, A2↔14) is the real relay's coil-to-Faston
terminal geometry. Two independent parts landing exactly on the PD2 bar is strong
evidence the BOM was selected against 8.0 mm.

**The permutation-invariance argument is correct.** For T1/T2 both primary pads are HV
and both secondary pads are SELV; for U6 all of pads 1–8 are SELV-side and 9/10/11/14/15/16
are HV-side (confirmed against `elec/domain_manifest.yaml`'s declared `groups`). The
HV↔SELV pair set is the full cross product of two function-fixed groups, and `min` over
a cross product is invariant under permutation within either factor. No pin reassignment
moves it.

**Two corrections to how these should be read:**

- **K1 has no HV↔SELV copper pad pair at all.** Read directly from the board: pads
  `13`/`14` are `(pad "13" smd rect … (layers "F.Fab"))` — F.Fab only, no `*.Cu`, no
  `*.Mask`, no `*.Paste`. This is deliberate (the G4A-1A-E's contacts are #250 Faston
  tabs with zero PCB land; representing them as F.Cu previously manufactured a
  fictitious land that shorted two mains nets,
  `docs/evidence/2026-07-29-intra-component-shorts-root-cause.md`). K1's 8.0000 mm is a
  geometric coil-to-tab distance between a copper pad and a *silkscreen-layer marker* —
  a real physical distance in the real relay, but **not a PCB creepage path**. Also
  measured: pads 13/14 are **0.0000 mm** apart (6.35 mm rects on a 6.35 mm pitch, they
  abut exactly), harmless today only because neither carries copper. The open question
  the footprint's own `descr` raises — how `power_in.ntc-no`/`w1_2` physically reach
  the tabs — is where K1's barrier actually lives, and it is unresolved.
- **T2 is not on the board.** It sits at (92.0, 280.05); the outline's y range is
  [20, 254]. Its binding pair is a footprint-level fact, not a board-level violation.

---

## 5. Three of the brief's premises did not reproduce

Stated plainly because two of them understate the cost and one overstates it, and
because planning against unreproduced figures is the failure mode this project has
already been burned by.

### 5.1 "U6 and T1/T2 have no compliant replacement in-repo" — true for drop-in swaps, **false for mechanisms**

The repo already carries researched, orderable, >12.6 mm mechanisms for both.
`docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` §0 and §3.2:

> "| U7 | **Discrete: certified digital isolator (logic only) + local secondary-side
> driver IC, one stage per switch** | **>14.5 mm** (TI ISO7741-Q1/ISO7740-Q1, DWW-16
> package) | **Yes** — `ISO7741FQDWWRQ1`, DigiKey Active, 6,968 units, $5.09 |
> **PASS — this is the recommendation** |"

with the mechanism explained: IC package creepage plateaus at 7–8.5 mm across every
function because the limit is the moulded lead-frame pitch, not the die; TI's
automotive **DWW ("extra-wide SOIC")** package — body 10.30 × 14.0 mm versus DW-16's
10.30 × 7.50 mm — is the same die deliberately re-packaged past that ceiling.

**One caveat I must state, and it is not small: >14.5 mm is the datasheet's *external
package* CLR/CPG, not a measured pad-edge-to-pad-edge distance on a real land
pattern.** Nobody in this repo has ever run `pad_pair_distance` on a DWW-16 land. That
matters here precisely because of this repo's own precedent
(`docs/evidence/2026-08-13-cst3015-reinforced-isolation-capability.md` §2.2, quoting
the 2026-07-29 relay determination): a component certificate governs the component's
internal construction and *cannot* stand in for the PCB pad-to-pad path, "*because that
path is physically outside the relay*". The same logic applies to a datasheet creepage
figure. **Drawing the DWW-16 land pattern and measuring it is a cheap, concrete,
one-session task and it should be done before anyone banks the claimed 1.9 mm margin.**

For T1/T2, `docs/evidence/2026-08-13-cst3015-reinforced-isolation-capability.md` §3.1
establishes there is no better *drop-in* part at 1:100 / ≥50 A from any manufacturer —
CST3015 already appears to be best-in-class on this axis — but names the mechanism that
escapes it: an **aperture/donut-primary CT** (Talema ASM, ICE Components CT07/08/10),
where the mains conductor threads the core's bore instead of landing on a PCB primary
pad, which "*genuinely decouples PCB creepage from a fixed component figure*". The
electrical consequence is already worked: a burden change **4.99 Ω → 49.85 Ω** preserves
the 50 A trip point at 1:1000. The open item there is **certification**, not geometry —
the specific parts checked lack third-party reinforced-insulation approval.

**So PD3 is not structurally unreachable. It is reachable via architecture changes
rather than part swaps** — which is more expensive than the brief's framing in effort,
and far less final than "no compliant replacement exists".

### 5.2 "Either C6 moves 52.41 mm or K1 moves 111 mm" — not found in the repo, and the repo says the opposite for C6

I could not locate this joint-frontier result anywhere: grepped `docs/` and every
commit reachable since 2026-08-16. What is in the repo,
`docs/evidence/2026-08-13-pd3-land-k1-c6.md` §4, is the opposite for C6:

> "**C6 alone: clean.** The C6-only candidate reproduces the baseline's DRC category
> counts **exactly**, across all 20 reported categories … zero new violations of any
> kind, confirmed reproducible."

— for the B81123C1562M000 on `C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4`, measured
**20.1000 mm**, +7.5 mm over 12.6.

And K1's failure there has a specific, named cause that is not a relocation distance:

> "The root cause: the incumbent Omron footprint's contact pins (`13`/`14`) are Faston
> tabs on `F.Fab` only — **zero real PCB copper** … Nearby traces were routed through
> what has always been, on the real board, copper-free space at that footprint.
> `RT33K012` is a conventional THT relay with real copper at the equivalent physical
> location, so it collides with exactly that routing regardless of orientation."

Five new `shorting_items` against `rtd_pan.high_window-out` and `safety.fault_or-b2`,
plus one courtyard overlap with C27. That is a **reroute of two nets** on a board where
88 of 139 multi-pad nets carry zero copper — not a 111 mm relocation. Note that
document measured board `b7d865b7`, so both results warrant re-measurement on
`26981fea`; the *mechanism* of K1's block is a board fact that has not changed.

Separately, the brief's related point stands and is real: the RT33K012 swap does move
**15 A of mains current** off external Faston spades onto PCB pads, and that needs
ampacity and thermal sign-off. That is a genuine new cost the K1 swap carries and it is
not recorded as a blocker anywhere I found.

### 5.3 "39 of 59 pads" and "5 of 8 isolators cannot straddle the corridor" — neither reproduced

The five parts carry **32** pads in total (C6 2, K1 8 including the four unnetted NPTH,
T1 4, T2 4, U6 14). Summing all eight declared isolators' declared group pads in
`elec/domain_manifest.yaml` gives **42**. Neither is 59.

`scripts/check_isolation_keepout.py`, run live this session on this board, reports
exactly **one** violation — `MAINS_SELV_ISOLATION_BARRIER` does not exist, so the
straddle analysis never executes:

```
Copper layers: 4. Footprints examined: 168. Pads examined: 527 (HV=109, SELV=237).
Barrier zone NOT FOUND (name='MAINS_SELV_ISOLATION_BARRIER').
Required minimum barrier width: 12.6mm (REINFORCED creepage).
=== VIOLATIONS: 1 ===
FAILED -- 1 violation(s)
```

Whatever produced "5 of 8", it was not this gate on this board. **I am not asserting
those two figures are wrong — only that they are unreproduced here and should be
re-derived before use.**

---

## 6. The slot avenue — rejected because the text is unobtainable, not because the geometry fails

This is the task's question 4 and it has a sharp answer.

### 6.1 The groove mechanism itself IS recovered primary text

From IS 15382 (Part 1):2003, the identical Indian adoption of **IEC 60664-1:2002**,
`https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf`, live-refetched and
`pdftotext`-extracted, pp. 42–43 — quoted at
`docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md:96-116`:

> "The dimension X, specified in the following examples, has a minimum value depending
> on the pollution degree as follows:
> | Pollution degree | Dimension X minimum value |
> | 1 | 0,25 mm |
> | 2 | 1,0 mm |
> | 3 | 1,5 mm |
> If the associated clearance is less than 3 mm, the minimum dimension X may be reduced
> to one third of this clearance."

> "**Example 2** — Condition: Path under consideration includes a parallel-sided groove
> of any depth and equal to or more than X mm. Rule: Clearance is the 'line of sight'
> distance. **Creepage path follows the contour of the groove.**"

Note the board is PD3, so **X = 1.5 mm** governs. Every slot the repo designed
(3.4–8.0 mm wide) clears it by 2.4×–5.3×, and clears JLCPCB's 1.0 mm minimum
non-plated slot width by 3.6×–7.3×. `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md:116-135`
states it outright: "*the groove-width/contour-following mechanism is recovered primary
text (no Annex L needed).*"

### 6.2 What is NOT recovered is the closed end — and by topology, a mid-board part always has one

Not recovered in any edition, from any source: anything about a groove with a **closed
end** that a creepage path must detour around, or a through-cut with no floor. The
finding is stated identically in four documents:

> "All 11 worked examples, in every edition checked, are 2D cross-sections of a groove,
> rib, joint, or screw head that is implicitly infinite/edge-to-edge in the third
> dimension — none has a rounded or squared end that a creepage path would need to
> detour around." (`docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md:141-148`)

corroborated by an independent third source (Suo et al. 2017, Atlantis Press AER v.105),
which works the same 11 examples and pictures no island either. The in-repo derivation
("path detours around the nearest closed end") is explicitly labelled **DERIVED, not
cited**.

The closed end is unavoidable: by a Jordan-curve argument on this simple-rectangle
outline, a single connected cut with both endpoints on the outline disconnects the
board. Edge-reaching therefore buys nothing numerically — it "*changes which pair
governs, not what number governs*".

### 6.3 The geometry succeeds

Measured, worst case at ±0.2 mm/edge fab tolerance:

| ref | intrinsic | slot | nominal / **worst case** | margin over 12.6 |
|---|---:|---|---|---:|
| **T1** | 9.100 | island 28.0 × 4.0 mm (112 mm²) | 13.2655 / **12.8296** | **+0.230** |
| **T1** | — | island 28.0 × 3.4 mm | 13.045 / **12.634** | +0.034 |
| **T1** | — | island 28.0 × 3.0 mm | — / 12.514 | **FAILS** |
| **U6** | 8.100 | island 7.30 × 17.00 mm (124.1 mm²) | 14.85 / **14.11** | **+1.51** |
| **T2** | 9.100 | transfers identically if placed | identical | identical |

These were reproduced by an independent `shapely`+`networkx` visibility-graph run that
first matched the published figures to 4 decimals before extending.

### 6.4 The precise reason it was not adopted — verbatim

`docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md:89-95`:

> "**Consequence, stated plainly: the slots do NOT clear any of the 7 without the
> cert-lab answer.** The 12.830mm (T1) / 14.11mm (U6) figures are computed *under the
> closed-end credit* — the exact thing cert-lab Question A asks. Without that credit
> (e.g. if the lab reads the path as running under the component's moulded body and
> disregards the slot), the governing figure reverts to the intrinsic 9.100mm /
> 8.100mm and all 7 still fail. This is not a margin nuance: the entire slot benefit
> (9.1→13.27mm, +4.17mm) IS the contested credit. There is no partial-credit floor
> above 12.6mm that survives a 'no credit' lab answer."

**Verdict: (b) — standards text unobtainable, so the credit is uncertifiable.** Not
(a) geometry. There is a real but explicitly subordinate structural gap (T1's
solder-joint thermal-cycling fatigue under a 23×30 mm CT body; U6's arm warpage during
reflow; the repo has zero FEA capability), which the edge-slot document itself calls
"*a real cost a human should weigh, **not a reason by itself to reject***".

### 6.5 What would settle it, and the outstanding question

**The document: IEC 60335-1 Annex L body text, pp. 170–172.** Secondarily, IEC 60664-1
Ed. 3.0:2020 / 3.1:2025 **cl. 6.8 body text plus Table 1 "Dimensioning of grooves"
(p. 46)** — recovered as a caption and page number only, never read.

A sendable certification-lab question already exists at
`docs/cert-lab-inquiry-final-2026-08-16.md` §4:

> "For a fully-through, full-board-thickness, non-plated PCB slot that terminates
> *inside* the board on at least one end (both walls solid FR4 at that end — not
> reaching the board's true outline), entirely underneath a surface-mount component's
> own body but clear of all pads: is the governing creepage path from a pad on one side
> of the slot to a pad on the other (a) the straight-line distance ignoring the slot;
> (b) a path that detours around the slot's nearest closed end and stays on the
> accessible top surface; or (c) something else…"

with the correct premise-narrowing: "*We do not need you to confirm that a wide groove
earns contour credit — that is cited text.*"

**Status in `docs/HANDOFF-2026-08-17.md:401`: "External — needs the lab's response." No
response is recorded anywhere in the repo, and I found no evidence it was ever sent.**

### 6.6 Two corrections to the slot record

- **The T1 edge-reaching arm figure is stale.** Every slot document measured against an
  outline whose left edge was `x = 20`. The committed outline's left edge is now
  **`x = 8`** (read directly, line 8232ff — the PR #1279 left-column enlargement). T1's
  edge-reaching south arm would need ≈**29.96 mm**, not 17.96 mm. The **island**
  variants — which are the ones that matter, since edge-reaching buys nothing — are
  unaffected.
- **`scripts/measure_cross_domain_creepage.py`'s docstring asserts a slot verdict it
  cannot support.** "*A surface creepage path that runs under a component's own moulded
  body cannot be lengthened by a routed slot*" — traced by `git log -p --all` to the
  script's first commit (`8302756d3`, 2026-07-29), **uncited**, and contradicted by a
  one-day-older determination (`docs/evidence/2026-07-28-conformal-coating-pd1.md:356-358`:
  "*a slot is a board feature and reaches under the body; a coating is a surface film
  and does not*"). This is the same script the task brief flags as having a broken
  rotation convention and a wrong violation-list filter. **Nobody should read a slot
  verdict out of it.** Recorded, not fixed — another agent owns that file.

---

## 7. The decision

**PD3 stands. `MIN_BARRIER_WIDTH_MM` stays at 12.6, `HV_CREEPAGE_ENFORCED_MM` stays at
`HV_CREEPAGE_PD3_MM`, and I changed nothing.**

The classification question is settled by the standard's own condition applied to the
board's own construction, and the cost of compliance is not an input to it. On
2026-08-18 the as-built board is forced-air vented across the PCB cavity by design,
with no cover, gasket, partition, compartment evidence file, or isolation-barrier
keepout zone — every one of those re-verified this session. **PD3 governs, and 12.6 mm
reinforced / 10.0 mm tank functional are the figures.**

What the cost data changes is not the answer but the plan. Three amendments:

**A. Amend the 2026-08-15 record's ground (b).** "Thermally counterproductive" should
read "thermally unresolved". It is not established, the repo cannot currently establish
it, and §2.3's three defects — the θJA that was in the repo all along at a value worse
than the assumed range, the 78 °C swing now riding on an unresolved 1.5 W vs 0.45 W
disagreement, and the 70 °C headline superseded by the committed 60 °C standard on the
same day — mean the number the decision leaned on is not one anyone should lean on.
Ground (a) — the compartment is unbuilt — is untouched and remains sufficient on its
own. **This changes no enforced value. It changes what the evidence trail claims.**

**B. Send the certification-lab question.** It is drafted, correct, premise-narrowed,
and free. It is also the single highest-leverage open item in the whole PD3 programme:
a "credit at the closed end" answer resolves T1 and U6 with island slots at
+0.230 mm and +1.51 mm worst-case margin, and a "no credit" answer forecloses the
cheapest path definitively and lets the expensive one start. Four days outstanding with
no evidence of transmission is the actual critical path, and nothing downstream should
be planned until it is either answered or declared unanswerable.

**C. Plan PD3's cost in four tiers, not two.**

| tier | scope | status |
|---|---|---|
| **Researched, parts exist, not on the board** | K1 → RT33K012 (**17.8000 mm**), C6 → B81123C1562M000 (**20.1000 mm**); both already in `elec/src/modules.ato` | K1 blocked on rerouting `safety.fault_or-b2` / `rtd_pan.high_window-out` + **15 A ampacity/thermal sign-off** on the new PCB pads. C6 measured placement-clean on `b7d865b7`; re-measure on `26981fea`. |
| **Blocked on a free external answer** | T1 + U6 island slots (12.83 / 14.11 mm worst case) | Cert-lab Question A. Cheapest path if it lands. |
| **Expensive, real, needs one measurement first** | U6 → `ISO7741FQDWWRQ1` DWW-16 architecture change (discrete digital isolator + local secondary-side driver, one per switch); T1/T2 → aperture-primary CT with burden 4.99 Ω → 49.85 Ω | **Do the DWW-16 pad-to-pad measurement before committing** — the >14.5 mm is a datasheet external figure, never verified on a land pattern in this repo. Aperture CTs need a reinforced-insulation-certified part. |
| **Ordinary debt, independent of all the above** | ~267 non-isolator HV↔LV spacing violations; 5 of 14 flagged pairs (C22×R26, C6×U1) confirmed to need physical redesign | Real routing/placement work on a board 88/139 nets unrouted. Must target 12.6 mm. |

**And if the owner ever wants PD2 back, this is what would make it true** — stated
because the task asked, not as advocacy, and explicitly *not* as an assertion that PD2
is defensible today (it is not):

1. All five conditions in `docs/ENVIRONMENTAL_SPEC.md` §3.1, recorded in
   `docs/specs/pd2_compartment_evidence.yaml` per the schema in
   `docs/evidence/2026-08-11-pd2-decision-record.md` §4.1 — with real part references
   and non-zero dimensions for the cover and gasket, and
   `airflow_routing.duct_crosses_pcb_cavity: false` citing a committed, revised duct
   geometry document.
2. **The one field that makes it non-vacuous:** `partition.keepout_zone_name` must name
   a rule area that actually exists in `pcb/temper.kicad_pcb` as a `(name "…")` — i.e.
   `MAINS_SELV_ISOLATION_BARRIER` must be a real 12.6 mm-wide zone across all four
   copper layers. Today `check_isolation_keepout.py` finds nothing.
3. `check_pd2_compartment_evidence.py` passing on evidence rather than by
   `NOT_APPLICABLE`, with Gate 4 blocking (which it already is).
4. **A thermal validation that does not currently exist**, because
   `packages/temper-thermal` cannot produce it (§2.1) — minimally §2.4's three steps,
   with the iteration script committed this time.

**Naming the prerequisite is not asserting PD2 is met.** It is not met, it is not close,
and until items 1–4 are real artifacts the classification is PD3 and the figure is
12.6 mm.

---

## 8. What this document does not claim

- It does not claim the board is PD3-compliant. It is not.
- It does not claim the sealed compartment is thermally viable — only that the repo's
  negative finding is unvalidatable, and that the one new datasheet fact found (θJA
  74.1 °C/W vs an assumed 45–70) points the *unfavourable* way.
- It does not settle the closed-end slot-credit question, IEC 60664-4, or the clause
  29.2.4 / clause 19 short-circuit-test exemption. All three carry forward unchanged and
  could only raise, never lower, the requirement.
- It does not invent or reconstruct any standards value. IEC 60335-1 Annex L and
  IEC 60664-4 remain **NOT OBTAINABLE**.
- It changes no threshold, no ceiling, no test, and no board file.

## Files

- This document.
- `pcb/temper.kicad_pcb` sha256 `26981fea…` — verified identical before and after; never
  opened for writing.
- Measurement harness: throwaway, session scratchpad, not committed (repo convention for
  one-off measurement).
