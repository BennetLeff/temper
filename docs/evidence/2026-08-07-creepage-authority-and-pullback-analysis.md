<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false -->

# Creepage authority reconciliation and `routing_copper_pullback` +42 determination

**Date:** 2026-08-07
**Task:** Decision-support for two questions surfaced this session: (1) which
of the two disagreeing creepage authorities (netclass-declared flat 6.0mm vs.
the `IEC60335_REQUIREMENTS` domain matrix) is correct, and whether either is
non-conservative; (2) whether the WASM tier's `routing_copper_pullback` +42
(117→165 total violations, `f2596ca3`) is real or a rule gap. This document
makes no safety-rule changes — it is a recommendation for the maintainer.

---

## Finding to lead with (Q1, non-conservative gap)

**`design_rules.py`'s flat `creepage_mm=6.0` for `ACMains`/`HighVoltage`
(and `HighVoltageIsolated`) is 2.0mm short of the IEC 60335-1 requirement
for every REINFORCED-insulation boundary these classes participate in**
(MAINS↔SELV, DC_BUS↔SELV, MAINS↔ISOLATED — the correct figure is 8.0mm per
Table 17 row iv at PD2, derived below). **This is currently not exploitable**:
the default CP-SAT solve path never reads netclass `creepage_mm` at all — it
enforces the always-on `IEC60335_REQUIREMENTS` matrix directly, which already
has the correct 8.0mm figure. The only path that turns the netclass value
into an actual constraint is the PCL constraint compiler, gated behind
`TEMPER_PCL_CONSTRAINTS=1`, which is off by default and not set anywhere in
this repo (`grep -rn TEMPER_PCL_CONSTRAINTS` across `.py`/`.yml`/`.sh`/`.md`
finds no setter, only the one `if os.environ.get(...)` read site and two
planning-doc mentions). So the number is latently wrong, not actively unsafe,
today. It becomes actively unsafe the moment someone flips that flag, or the
moment any future consumer trusts `SAFETY_CONSTANT_AUTHORITY`'s creepage
entries directly instead of the matrix. See §1.4 for the full derivation and
§1.5 for the recommendation.

---

## 1. Which creepage authority is correct (Q1)

### 1.1 The two mechanisms, restated precisely

- **Netclass-declared** (`packages/temper-placer/src/temper_placer/core/design_rules.py:69,83,217`):
  a single scalar per net class — `ACMains.creepage_mm = 6.0`,
  `HighVoltage.creepage_mm = 6.0`, `HighVoltageIsolated.creepage_mm = 6.0` —
  with no notion of *which* domain pair or insulation type it is being
  measured against. It cannot vary by boundary because it is a property of
  one net class, not a pair.
- **`IEC60335_REQUIREMENTS`** (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:259-290`):
  a `(domain_a, domain_b, insulation_type) -> {min_clearance_mm,
  min_creepage_mm, design_value_mm}` matrix, consumed unconditionally by
  `placer/cp_sat/domain_clearance.py` (verified by reading that module: it
  imports `IEC60335_REQUIREMENTS` directly from `clearance.py` and encodes
  `margin = max(min_clearance_mm, min_creepage_mm)` as a `SeparatedConstraint`
  for every domain-crossing component pair — no feature flag gates this
  path).

A flat per-netclass scalar structurally cannot be correct for "the" creepage
requirement, because IEC 60335-1's requirement is a function of working
voltage, pollution degree, material group, and insulation type (basic vs.
reinforced) — exactly the matrix's four axes. The disagreement is not a
measurement error on one side; it's that one side (the netclass scalar) is
the wrong *shape* of data structure to hold this quantity at all.

### 1.2 Board parameters governing the matrix

These were established over multiple prior sessions and are re-confirmed
here, not re-derived from scratch:

- **Mains / DC bus voltage:** 240V RMS mains (340V peak), 300–400V DC bus
  (400V transient) — `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §2.1;
  `design_rules.py`'s own `voltage_v=240.0` (ACMains) / `400.0` (HighVoltage)
  fields agree.
- **Pollution degree:** **PD2**, as a conditional production-architecture
  decision (`docs/evidence/2026-07-30-pd2-enclosure-decision.md`), superseding
  the PD3 default IEC 60335-2-6 cl. 29.2 Addition would otherwise impose
  (`docs/evidence/2026-07-30-pollution-degree-determination.md`). PD2 is
  conditional on a real, verified gasketed PCB compartment
  (`docs/CHASSIS_AIRFLOW_DESIGN.md`, `docs/ASSEMBLY_GUIDE.md`,
  `docs/ENVIRONMENTAL_SPEC.md`) — if that compartment is not built or fails
  inspection, PD3 is the fallback and every reinforced-creepage figure below
  reverts to 12.6mm (basic: 6.3mm). This document does not re-litigate that
  decision; it takes PD2 as given, per the task's own framing ("PD2
  protected-compartment architecture," commit `ee3da42a`).
- **Material Group:** IIIb (FR4, CTI 175–249V) — `HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  §3.2; Table 17's IIIa/IIIb column is a single shared column (the two
  groups are not distinguished in that table), so this is the correct column
  regardless of whether the FR4 in question is IIIa or IIIb specifically.
- **Insulation class per net-pair domain:** determined by what separates the
  two sides electrically. MAINS↔LV_CONTROL and DC_BUS↔LV_CONTROL are
  **REINFORCED** (single-fault protection is insufficient when the LV side is
  user-accessible SELV — a person must be protected by two independent
  insulation systems). MAINS↔PE is **BASIC** (protective earth, not an
  accessible SELV surface). Within-LV_CONTROL is **FUNCTIONAL** (no hazard
  voltage on either side).

### 1.3 Table 17 derivation (creepage), by domain pair

IEC 60335-1 clause 29 (creepage), Table 17 ("Minimum Creepage Distances for
Basic Insulation"), material group IIIa/IIIb, PD2 column — cross-checked
against IS 302-1:2008 §29 (an identical adoption, already cited in
`clearance.py`'s own module comments and independently re-confirmed here
against the standard Renard R10 creepage-distance series IEC 60664-1/60335-1
tables draw from: 1.2/1.5/2.5/4.0/5.0mm at PD2 rows ≤50/≤125/≤250/≤400/≤500V —
these are the standard's own preferred numbers, not board-specific
inventions):

| Working voltage row | PD2 basic (mm) | PD2 reinforced (mm, = 2× basic per cl. 29.2.3) |
|---|---:|---:|
| ≤50V | 1.2 | 2.4 |
| >50–≤125V | 1.5 | 3.0 |
| >125–≤250V | 2.5 | 5.0 |
| **>250–≤400V (row iv)** | **4.0** | **8.0** |
| >400–≤500V | 5.0 | 10.0 |

This board's MAINS (340V pk), DC_BUS (400V pk/transient), and
HighVoltageIsolated/gate-drive-isolated (355V peak-to-earth) boundaries all
fall in row iv (>250, ≤400V — 400 qualifies at the row's own inclusive upper
bound). **Reinforced creepage at row iv, PD2 = 8.0mm; basic = 4.0mm.** This
exactly matches what `IEC60335_REQUIREMENTS` already encodes:

```
(MAINS, LV_CONTROL, BASIC):      min_creepage_mm = 4.0
(MAINS, LV_CONTROL, REINFORCED): min_creepage_mm = 8.0
(DC_BUS, LV_CONTROL, REINFORCED):min_creepage_mm = 8.0
(MAINS, ISOLATED, REINFORCED):   min_creepage_mm = 8.0
```

I independently re-derived these from the standard's row structure rather
than merely re-reading the code comment, and they check out. **The matrix is
correct for these rows given the PD2/IIIb inputs above.**

### 1.4 Table 16 derivation (clearance), and where the netclass scalar comes from

**Correction, 2026-08-14: this section's "overvoltage category III" premise is
wrong and was asserted with no clause citation; it has been carried forward
from the same error in `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (now
corrected — see that document's §3.2 and revision-history v1.4). IEC 60335-1
clause 29.1 states unconditionally: "Appliances are in overvoltage category
II"** (CITED-PRIMARY, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:221-223`).
At this board's 120V rated voltage, OVC II puts the appliance in Table 15
row ii (>50V, ≤150V) → **1500V** rated impulse, not the 2500V this section's
uncorrected OVC III premise used — one full Table 16 step lower. Under the
corrected OVC II reading, clause 29.1.3's "next higher step" reinforced rule
gives Table 16's 2500V-row basic figure (1.5mm) plus clause 29.1's +0.5mm
soldered-construction adder = **2.0mm reinforced clearance**, not 6.0mm — this
is `scripts/generate_kicad_dru.py`'s `HV_INTERNAL_CLEARANCE_MM`, independently
derived there from the same clause and matching the netclass `clearance` field
`design_rules.py` was fixed to on 2026-08-12
(`docs/evidence/2026-08-12-netclass-param-reconciliation.md`). **This
section's original "6.0mm is the correct Table 16 reinforced clearance figure,
just mislabeled as creepage" conclusion (below) is therefore itself
superseded, not merely mislabeled** — 6.0mm was never a correct Table 16
figure for this board's mains/DC-bus boundaries at 120V rated voltage under
either OVC reading available in this repo's primary text. See
`docs/evidence/2026-08-12-hv-clearance-adequacy.md` for the current,
worst-case-voltage-aware clearance derivation, and the certification-lab package
`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md` for
what remains genuinely open. **The rest of this section is retained verbatim
below as the historical record of how the netclass `creepage_mm=6.0` value
originated (a field-name conflation, `cb317451`) — that git-history finding is
independent of the OVC error and still stands; only the "6.0mm itself is a
correct Table 16 figure" framing around it is corrected here.**

IEC 60335-1 Table 16 (clearance, through air) is keyed to **rated impulse
voltage** (via Table 15's overvoltage-category lookup), not pollution degree
or material group. This board's mains/DC-bus boundaries fall under
overvoltage category III at ≤300V mains supply system voltage → 2500V rated
impulse (basic) / the reinforced figure doubles that clearance requirement.
`IEC60335_REQUIREMENTS` gives `min_clearance_mm = 3.0` (basic) / `6.0`
(reinforced) for MAINS↔LV_CONTROL and DC_BUS↔LV_CONTROL — consistent with
Table 16's 400V-row minimums, and **this is where the netclass scalar's
6.0mm actually comes from**: `design_rules.py`'s `clearance=6.0` field
(a *different* field from `creepage_mm`) matches the REINFORCED **clearance**
figure exactly. The commit history and a prior, independent evidence doc
(`docs/evidence/2026-07-28-conformal-coating-pd1.md`, commit `50df12f3`)
already caught this exact confusion in the sibling YAML
(`packages/temper-placer/configs/netclass_rules.yaml`): "one number and one
citation are doing duty as both the clearance and the creepage figure,"
citing Table 16 (clearance) for a value that was then also reused as
`creepage_mm`. `git log -S` on `design_rules.py` confirms
`HighVoltage.creepage_mm` was raised from `2.0` to `6.0` in `cb317451`
("increase HV clearance/creepage to IEC 60335-1 minimums") — i.e. someone
copied the (correct, for reinforced) *clearance* figure into the *creepage*
field at the same time, without re-deriving creepage from Table 17
separately. That is the origin of the disagreement: **the netclass
`creepage_mm=6.0` is not derived from Table 17 at all — it is the Table 16
clearance figure, mislabeled.**

### 1.5 Verdict: is either non-conservative?

| Domain pair | Insulation | Correct clearance | Correct creepage | Netclass `clearance` | Netclass `creepage_mm` |
|---|---|---:|---:|---:|---:|
| MAINS↔PE | Basic | 2.5mm | 4.0mm | 6.0mm (conservative) | 6.0mm (conservative) |
| MAINS↔LV_CONTROL | Reinforced | 6.0mm | **8.0mm** | 6.0mm (exact match) | **6.0mm — 2.0mm short** |
| DC_BUS↔LV_CONTROL | Reinforced | 6.0mm | **8.0mm** | 6.0mm (exact match) | **6.0mm — 2.0mm short** |
| MAINS↔ISOLATED | Reinforced | 6.0mm | **8.0mm** | 6.0mm (exact match) | **6.0mm — 2.0mm short** |

- **The `IEC60335_REQUIREMENTS` matrix is correct** for every row I
  re-derived (§1.3) and is never non-conservative — it is the mechanism
  actually gating the default CP-SAT solve path (`domain_clearance.py`),
  unconditionally.
- **The netclass `clearance` field (6.0mm flat) is conservative or exact**
  everywhere: it matches the REINFORCED clearance minimum exactly on the
  boundaries that need REINFORCED, and over-shoots the BASIC minimum
  elsewhere. Not a safety problem.
- **The netclass `creepage_mm` field (6.0mm flat) is non-conservative by
  2.0mm on every REINFORCED-insulation boundary** (MAINS↔LV_CONTROL,
  DC_BUS↔LV_CONTROL, MAINS↔ISOLATED) — it is a mislabeled copy of the
  clearance figure, not a creepage derivation, and 6.0 < 8.0 required.
  **As established above, this is currently inert** (dead-lettered behind
  `TEMPER_PCL_CONSTRAINTS`, unset everywhere) so it is not producing an
  under-enforced board today — but it is wrong data sitting in the SSOT
  (`SAFETY_CONSTANT_AUTHORITY` explicitly includes `creepage_mm` for
  `ACMains`/`HighVoltage` as of `SAFETY_CONSTANT_AUTHORITY_FIELDS`,
  `design_rules.py:344`) that anyone reading it directly, or any future
  change that turns `TEMPER_PCL_CONSTRAINTS` on by default, would silently
  under-enforce reinforced creepage by 2.0mm.
- I did **not** find a case where the matrix under-requires relative to the
  standard. I did **not** re-verify the BASIC-row / FUNCTIONAL-row figures
  beyond what's already flagged as open in
  `docs/evidence/2026-07-30-pollution-degree-determination.md` (the
  within-LV_CONTROL FUNCTIONAL row, 1.0mm vs. a PD2 table figure of 1.1mm —
  already flagged there as a separate, un-closed follow-up, not this
  document's finding).

### 1.6 Recommendation

1. **`IEC60335_REQUIREMENTS` should be the sole creepage authority.** It is
   already domain-pair-and-insulation-aware (the only shape of data that can
   be correct for this standard), already unconditionally enforced on the
   default solve path, and every row I independently re-derived checks out
   against Table 17.
2. **The netclass `creepage_mm` scalar should not be deleted outright** —
   `bottleneck_geometry.py` and the PCL path read it as a routing-corridor
   sizing hint, and a `getattr(..., 0.0)` fallback with a wrong or absent
   value is worse than a present, conservative one. Instead: **raise it to
   8.0mm** (the maximum reinforced-creepage requirement across every domain
   pair `ACMains`/`HighVoltage`/`HighVoltageIsolated` participate in) so it
   functions correctly as a **conservative floor/hint** rather than a
   second, disagreeing source of truth. This is a one-line-per-class value
   change (`design_rules.py:69,83,217`, and the mirrored `class_pairs`
   entries in `configs/netclass_rules.yaml`) — left to the maintainer per
   this task's constraints (no safety-rule-value edits made here).
3. Fix the `netclass_rules.yaml` `because:` strings while at it (they cite
   "Table 16... at 400V" for a value now serving double duty as clearance
   *and* creepage — already flagged as wrong in `50df12f3` and never
   corrected). The clearance citation is fine; the creepage figure needs its
   own citation to Table 17 row iv once corrected.
4. No urgency beyond the ordinary backlog: the dormant path
   (`TEMPER_PCL_CONSTRAINTS`) is off everywhere today, verified by grep
   across the whole repo, so nothing currently in production is
   under-enforcing creepage because of this scalar.

---

## 2. `routing_copper_pullback` +42 (Q2)

### 2.1 Rule implementation: it reads the authored outline, never the fill

`packages/temper-drc-rs/src/rules/routing/copper_pullback.rs` (`check()`,
lines 43-112) tests `zone.polygon.exterior()` — every vertex of
`board.zones[i].polygon` — against an inset rectangle
`[margin, margin] .. [width-margin, height-margin]`. `CopperZone.polygon`
(`board.rs:431-434`) is populated, for the WASM-tier producer in question
(`tools/wasm/r2_serialize_board.py::_zones_from_parsed`), from
`parsed.zones[i].polygon`, which traces back to
`temper-design-bundle/src/parse_engine.rs::parse_zone` (lines 999-1046).
**`parse_zone` matches only the S-expression head `"polygon"` — the zone's
authored outline. It has no handler for `"filled_polygon"` at all**; that
KiCad node type (written only after "Fill All Zones" + save) is silently
ignored if present. This is a structural fact about the parser, independent
of any specific board file: **the rule can never see filled copper, only the
outline, by construction.**

Confirmed this file has no fill data to begin with: `grep -c
"(filled_polygon" pcb/temper.kicad_pcb` → **0**, and `git log --all -S
filled_polygon -- pcb/temper.kicad_pcb` → **no commit ever added one**. This
board has never been saved from KiCad with zones filled.

### 2.2 What the 42 actually are, geometrically

I reproduced the +42 independently by parsing every `(zone ...)` block's
`(polygon (pts ...))` directly out of `pcb/temper.kicad_pcb` (96 zones total)
and testing each against the same rectangle the rule uses: board outline
`Edge.Cuts` `(xy 20 20)-(xy 172 254)` → 152mm × 234mm, board-local origin
(20,20); `margin_mm = 3.0` (hardcoded in
`r2_serialize_board.py::build_board_dict`, not read from the board's own
`(setup ...)` block, which declares no copper-to-edge-clearance setting at
all — only `pad_to_mask_clearance 0`). Result: **42 zones violate the
3mm-inset rectangle**, matching the commit's reported count exactly. Splitting
those 42 by whether the *outline itself* exceeds the physical board rectangle
(not just the 3mm inset):

| Category | Count | Nets | Shape |
|---|---:|---|---|
| **Outline exceeds the board edge itself** (points beyond 0–152mm / 0–234mm local) | **8** | `ac_l`, `ac_n`, `DC_BUS_RTN`, `SW_NODE` — each on both F.Cu and B.Cu | Simple 4-5-point rectangles (or a lightly-keepout-cut 66-point `ac_l` shape), bounding boxes up to 155.8mm×238.1mm — i.e. drawn *larger than the 152×234mm board itself*, by as much as 31mm past the inset (and past the edge). |
| **Outline entirely inside the board, only violates the 3mm inset** | **34** | mostly `+3V3`, `vcc`, `PWM_HS`, `+15V_LS`, `V_BUS_SENSE`, `PWR_RTN` | Ranges from ~0.5×0.5mm point-like pours (via/thermal-relief islands) up to one 129×98mm `PWM_HS` pour that comes within 0.16mm of the literal board edge. Shortfalls beyond the 3mm margin are small: 0.01mm–2.84mm. |

### 2.3 Direct answer: real vs. rule gap, split by category

**The recorded hypothesis (outline drawn generously, clipped to the board
edge at fill time) explains exactly the first category — 8 of the 42 — and
only those 8.** `ac_l`, `ac_n`, `DC_BUS_RTN`, and `SW_NODE` (each on F.Cu and
B.Cu) are drawn as rectangles that physically extend past the board outline
by up to ~31mm. KiCad's fill engine unconditionally clips filled copper to
the `Edge.Cuts` polygon — copper cannot exist outside the physical board — so
these 8 flags, as reported (magnitude "extends 31mm past the margin"), are
**a rule gap for their exact reported magnitude**: real filled copper cannot
be 31mm outside a 152mm-wide board.

**This does not mean these 8 are clean, though — flag prominently, don't
let the outline-vs-fill explanation read as "safe."** All four nets are
`ACMains`/`HighVoltage`-domain (`ac_l`/`ac_n` → `ACMains`, `DC_BUS_RTN`/
`SW_NODE` → `HighVoltage` per `design_rules.py`'s `TEMPER_NET_ASSIGNMENTS`) —
i.e. these are exactly the mains/HV-bus copper pours this session's Q1 is
about. Clipping to the physical board edge does not pull the fill back to
the 3mm margin — it only stops it *at* the edge (0mm), which is *closer* to
the edge than the reported violation, not farther. I could not determine
whether the true filled copper for these 4 nets actually reaches the literal
edge (their outlines look like deliberate full/near-full-board background
pours, and KiCad zone-priority resolution against the other 92 zones, which I
did not simulate, could carve most of that territory away before it ever
reaches the edge) — **this file has never been saved with fills, so there is
no ground truth to check it against.** Recommend the maintainer open the
board in real KiCad, run "Fill All Zones," and re-measure before treating any
of these 8 as resolved either direction.

**The other 34 are not explained by the outline-vs-fill hypothesis at
all, and I found no other rule-gap explanation for them — treat them as
real** (or at minimum, not dismissible by this hypothesis). Their authored
outlines are entirely inside the 152×234mm board; nothing in their geometry
(irregular vertex counts — 66-point rounded/faceted shapes, small 4-8-point
polygons — none matching the "oversized rectangle" authoring pattern the
first 8 show) suggests they were drawn intentionally larger than intended and
would be clipped down. For a zone whose outline never crosses the board
edge, KiCad's fill is the outline (intersected with other zones' priority
claims and thermal-relief spokes at pads, neither of which changes the outer
boundary against open board area) — so the filled result would plausibly
reproduce the same close-to-edge geometry the outline already shows. Some of
these are trivial (six ~0.5×0.5mm via/thermal-relief points a hair under the
margin — `vcc`, `+3V3`, shortfalls 0.05-2.05mm); one is not trivial
(`PWM_HS`, a 129mm×98mm pour reported 0.16mm from the literal physical
board edge, on a signal-adjacent net class).

### 2.4 Recommendation

1. **Rule gap, fix if the rule should ever assess final copper accurately**:
   `parse_zone` in `temper-design-bundle/src/parse_engine.rs` should parse and
   prefer `(filled_polygon (layer ...) (pts ...))` when present (per-layer,
   since a multi-layer zone has one filled polygon per layer) and fall back
   to the authored `(polygon ...)` only when no fill exists (unfilled board,
   exactly this file's current state) — flagging that fallback explicitly
   (e.g. a stats counter or WARNING) so a report doesn't silently claim it
   measured filled copper when it measured raw outline. This closes the gap
   for the 8 oversized-rectangle zones going forward, on any board that has
   actually been filled.
2. **Do not use that fix to explain away the current 42** — this specific
   board file has zero fill data (§2.1), so no filled-polygon parser change
   would alter today's 165-count; it only prevents the same false-positive
   shape from recurring after re-fill on a future board revision.
3. **Before shipping, get a real KiCad fill of `pcb/temper.kicad_pcb`** and
   re-run `routing_copper_pullback` against it. That is the only way to
   settle the 8 mains/HV-net zones definitively, and it would also validate
   or refute the 34 non-explained violations against real (not just
   plausibly-real) copper. I could not do this in this environment (no
   KiCad zone-fill engine available here) — this is the one open item this
   analysis could not close.
4. The `margin_mm = 3.0` value the WASM producer hardcodes is not sourced
   from the board's own design-rule settings (which declare none) — worth
   the maintainer confirming 3.0mm is actually the intended pullback
   (vs., say, deriving it from the same `IEC60335_REQUIREMENTS`/netclass
   creepage figures Section 1 discusses) rather than an arbitrary test
   constant, independent of the outline-vs-fill question.

---

## Sources consulted

- `packages/temper-placer/src/temper_placer/core/design_rules.py`
- `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py`
- `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py`,
  `_adapter_convert.py`, `stage0_data.py`, `bottleneck_geometry.py` (read-only;
  `router_v6/` not modified per task constraints)
- `packages/temper-placer/configs/netclass_rules.yaml`
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
- `docs/evidence/2026-07-30-pollution-degree-determination.md`,
  `2026-07-30-pd2-enclosure-decision.md`,
  `2026-07-28-conformal-coating-pd1.md`
- `packages/temper-drc-rs/src/rules/routing/copper_pullback.rs`, `board.rs`,
  `board_py_bridge.rs`
- `packages/temper-design-bundle/src/parse_engine.rs`
- `tools/wasm/r2_serialize_board.py`
- `pcb/temper.kicad_pcb` (read-only; not modified per task constraints)
- Commits: `63ca7f3c`, `f2596ca3`, `cb317451`, `50df12f3`
- IEC 60335-1 Table 16/17 clauses 29.1-29.2.4, cross-checked against
  IS 302-1:2008 §29 (identical adoption) and the standard Renard R10
  creepage-distance series
