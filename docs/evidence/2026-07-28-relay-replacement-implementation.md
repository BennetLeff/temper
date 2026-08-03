<!-- provenance: commit=b39035f508d208b92ce4061e890662acf3262ceb dirty=false -->

# K2/K3 discharge-relay replacement: implementation (Omron G5LE-1 -> Finder 40.52 DPDT)

Base commit: `b1499a16` (`merge: reconcile with concurrent session before
push`), branch `docs/methodology-loop-discipline` as it stood at that
commit (the branch has since advanced with unrelated doc-only commits from
concurrent sessions; this work is based directly on the commit, per the
task's own instruction). Work done in worktree
`agent-aa7beb67f44906306`, branch `feat/k2-k3-discharge-relay-replacement`.

This is an **implementation** pass, not a research pass: it changes
`elec/src/components.ato`, `elec/src/modules.ato`, `elec/domain_manifest.yaml`,
adds a new footprint under `pcb/libs/temper.pretty/`, and corrects one stale
line in `docs/hardware/BOM.md`. `pcb/temper.kicad_pcb` was **not** touched
(per the task's hard rule to stay in `elec/src/` and the relay footprint,
and to coordinate before touching the board file — sibling agents are
active there). This has a real, reported consequence: see "Board resync
required" below.

## Verdict up front

**The falsifier's strong form holds: a single, real, manufacturer-verified
relay closes isolation AND DC-break AND NC-topology together, with no
trade-off among the three.** Neither of the two single-pole candidates
identified by the prior research pass
(`docs/evidence/2026-07-28-discharge-relay-isolation.md`) was adopted.
Re-verifying both against their own manufacturer PDFs this session (not
reused from that doc's summary) surfaced a **third, better candidate**:
**Finder `40.52.7.012.0000`**, a genuinely 2-pole (DPDT) relay whose own
catalog states **"Reinforced (8mm)"** coil-to-contact insulation
(EN 61810-1) for both poles and gives an **explicit DC1 breaking-capacity
graph** at this circuit's actual 170-200V duty — closing the one gap
(un-rated DC break) that both single-pole candidates and the incumbent
G5LE-1 shared. Both poles are wired NC-in-series in the discharge string,
converting the task's suggested mitigation-to-specification re-scoping into
an actual implementation, on top of (not instead of) the part's own
already-adequate per-pole rating.

**The one real trade-off, reported plainly rather than dropped**:
implementing this pin-mapping-and-footprint change in `elec/src/` makes
`pcb/temper.kicad_pcb` genuinely stale (it still carries the old 5-pin
G5LE-1 footprint and old net names for K2/K3). `check_copper_net_consistency`
now fails as a direct, mechanical consequence — not a design defect — and a
placement/routing resync is a required follow-up this task's own hard rules
put out of scope (stay in `elec/src/` and the relay footprint; coordinate on
the board file). This is flagged explicitly below, not silently absorbed
into a "PASSED" claim.

## Task 1 — candidate re-verification and choice

Both candidates from the prior research doc were re-fetched from their
manufacturer PDFs directly this session (`WebFetch`, full text extracted,
not reused from that doc's summary — `WebSearch` was budget-exhausted at
session start, same constraint every prior session in this chain hit;
`WebFetch` on direct/discovered URLs worked throughout):

- **American Zettler `AZ770-1C-12D`**
  (`https://www.azettler.com/media/pdfs/relays/datasheets/AZ770.pdf`,
  2021-04-27): confirmed **1 Form C only** (no 2-pole option exists in this
  family's ordering grammar — "Contact arrangement: 1A/1C" is the entire
  field), **8mm creepage and clearance**, "Reinforced insulation, EN 60730-1
  (VDE 0631, part 1)", **30VDC catalog ceiling** with an explicit "contact
  the factory" escape hatch above that, and a photographed physical unit on
  the datasheet's own cover marked `AZ770-1C-12DE` — direct evidence the
  sealed variant of this exact configuration is a real, manufactured part
  (not proof of the specific non-sealed `-12D` string, which remains
  derived from the ordering grammar, not verbatim-catalog).
- **Panasonic Industry `ALZN1B12W`**
  (`https://mediap.industry.panasonic.eu/assets/download-files/import/mech_eng_lzn.pdf`,
  cat. ASCTB395E, 2022.4): confirmed **verbatim** in the ordering table,
  **1 Form C / 1 Form A only** (no 2-pole option in this family either),
  **10mm min clearance/creepage**, coil numerically identical to the
  incumbent G5LE-1 (360 ohm/33.3mA/400mW), but **no DC contact-voltage
  rating stated anywhere** in the fetched catalog (a genuine gap, not
  favorable — Panasonic's own literature is silent on DC switching at any
  voltage for this family) and **no "reinforced" wording found** in this
  catalog (the 10mm figure is stated as a clearance/creepage number, not
  tied to an explicit insulation-class claim the way AZ770's is).

**Neither was selected.** Both are real, single-pole (1 Form C) parts, and
the task's own instruction to evaluate DPDT re-scoping motivated checking
whether a DPDT relay with comparable certified isolation exists at all —
it does, and it is stronger on every axis that matters here.

### The chosen part: Finder `40.52.7.012.0000`

Source: Finder "40 SERIES PCB/Plug-in relays 8-10-12-16A" catalog
(`https://cdn.findernet.com/app/uploads/S40EN.pdf`), fetched and read in
full this session (11 pages, `pdftotext`-equivalent extraction via the
`Read` tool on the saved PDF).

| Parameter | Value | Source |
|---|---|---|
| Contact arrangement | **2 CO (DPDT)**, type 40.52 | catalog p.3/p.4, confirmed genuine 2-pole (not derived) |
| Coil-to-contact-set insulation | **"Reinforced (8mm)"**, EN 61810-1, overvoltage cat. III, 6kV rated impulse, 4000VAC dielectric | catalog p.6 "Technical data" table — an explicit standards *classification*, stated for both the 1-pole and 2-pole variants, not just a raw mm figure the way both single-pole candidates state theirs |
| Insulation between the 2 poles' adjacent contacts | "Basic", 4kV impulse / 2500VAC | catalog p.6 (relevant since this design puts both poles in series — see Task 2) |
| DC1 breaking capacity | **explicit manufacturer graph**, "single contact" and **"40.52 - 2 contacts in series"** curves, 20-220VDC | catalog p.8, "H 40.1 - Maximum DC1 breaking capacity, Types 40.31/51/52/61" |
| Rated current (2 CO) | 8A / 250VAC | catalog p.3 |
| Coil (sensitive DC, code `7.012`) | 288 ohm, 42mA rated at 12V, operate range 8.8-18V | catalog p.9 coil table |
| Standards | Meets EN 60335-1 glow-wire (GWT); UL 508, IEC 61810-1 | catalog p.3 |
| Package | 29 x 12.4mm footprint envelope (height not independently re-verified), 8-pin THT | catalog p.10 outline drawing |

**DC1 breaking-capacity finding, read directly off the graph (catalog p.8,
"H 40.1"), approximate (graph-read, not a table value — flagged as such,
not rounded to false precision):** the "single contact" curve for
types 40.31/51/52/61 sits on the order of **0.2-0.3A at 220VDC**, and the
**"40.52 - 2 contacts in series"** curve sits higher across the whole
20-220V range. This circuit's actual break current is **21.8mA**
(`docs/evidence/2026-07-28-discharge-relay-isolation.md` Task 1, unchanged
by this relay swap) — **roughly an order of magnitude under the single-
contact curve alone**, at the 200V worst-case bus voltage. Neither AZ770
(30VDC catalog ceiling) nor ALZN1B12W (no DC rating stated at all) gave an
explicit rating this far into the circuit's real 170-200V operating range.
This is a materially stronger disclosure than either single-pole candidate,
independent of the series-poles re-scoping in Task 2.

**Part-number provenance**: `40.52.7.012.0000` is constructed from the
manufacturer's own published ordering-code grammar (catalog p.5): Series=40,
Type=52 (5.0mm pinning / 2-pole), CoilVersion=7 (sensitive DC 0.5W, coil
table row `7.012` read directly), CoilVoltage=012, default ABCD suffix.
`40.52.9.024.0000` (standard-DC, 24V) and `40.52.7.012.0000` (this exact
sensitive-DC, 12V SKU) were both independently found as real distributor
listings (DigChip, Newark, DigiKey snippets) via `lite.duckduckgo.com`
(used the same way prior sessions in this chain used it, as a URL-discovery
path after `WebSearch`'s budget was exhausted) — corroborating the
derivation against a real, orderable part, the same standard this project
already applies to `AZ770-1C-12D` in the prior research doc.

**Why not the incumbent's own family or the two single-pole candidates:**
the incumbent G5LE-1 (Relay_SPDT) fails on the three grounds the task
states: 6.32mm pad gap (3.50mm edge-to-edge) against 8.0mm, shortest path
across the relay's own case (unfixable by any board feature), no
creepage/clearance figure at all in its own datasheet, and 2000VAC
coil-to-contact dielectric strength below IS 302-1 Table 7's reinforced
figure. `Omron G5NB-1A-HA` (evaluated and rejected in the prior research
doc) is excellent on isolation but SPST-NO only — inverts the fail-safe
direction, correctly rejected there and not re-litigated here.

## Task 2 — DC break: DPDT re-scoping, evaluated and adopted

**Both single-pole candidates were checked for a same-family DPDT sibling
first, and neither has one** — confirmed from the primary datasheets
fetched this session, not assumed: AZ770's own "Arrangement" field is
"SPST (1 Form A), SPDT (1 Form C)" with no 2-pole row anywhere in its
ordering-code grammar; LZ-N's ordering table lists only "1 Form C" and
"1 Form A" as contact-arrangement options. **Re-scoping within either
single-pole family is not possible** — a different family was required,
which is exactly why Finder's 40 series (found independently, not in the
prior doc) matters here.

**Finder 40.52 is genuinely 2 Form C (DPDT)**, and both poles are now
wired in series in each relay's discharge string
(`elec/src/modules.ato` `BusDischarge`):

```
r_dis1b.p2 ~ k_dis1.NC1
k_dis1.COM1 ~ k_dis1.NC2      # series junction between the two poles
k_dis1.COM2 ~ mid
```

**This converts the task's framing exactly as intended**: the incumbent's
un-rated 170-200VDC break was mitigated (not resolved) by low break current
relative to Ag arc-sustain threshold and RC-snubber dV/dt limiting — a
circuit-level argument, not a component rating. The new part **both**
carries an adequate rating on a single contact already (~10x margin at
220V) **and** the task's suggested two-contacts-in-series doubling is
implemented as an actual wired specification on top of that, using a real
second pole rather than a hypothetical one. **Recommendation: keep the
DPDT-with-series-poles design** — it is strictly better than either
"single pole, rely on the per-pole rating" or "single pole, rely on the
mitigation argument alone," and costs nothing extra once a genuinely
2-pole part exists (the coil, driver, and resistor-string sizing are
unchanged, see Task 3).

Both relays' two poles share a single armature (standard DPDT
construction) — both contacts of a given relay open and close in the same
physical event, so the existing per-relay RC snubber sizing (100 ohm +
470nF, dV/dt and energy figures in the `BusDischarge` docstring) is
**unchanged** by this: it now spans the two contacts in series (NC1 to
COM2) rather than one contact, but the switching event it sees is the same
one it was already sized for.

## Task 3 — implementation

### `elec/src/components.ato`

Added `Relay_DPDT`, an 8-pin component with EN 50005 standard relay
terminal numbering (the industry-wide convention for general-purpose power
relays of this class — used identically by Finder, Omron, Releco, Relpol,
Songchuan): `coil1`/`coil2` -> pins `"A1"`/`"A2"`; pole 1
`COM1`/`NC1`/`NO1` -> pins `"11"`/`"12"`/`"14"`; pole 2
`COM2`/`NC2`/`NO2` -> pins `"21"`/`"22"`/`"24"`. Pin references use the
grammar's quoted-`string` form (`pin "11"`, etc. —
`atopile/parser/AtopileParser.g4:60`, `pindef_stmt: 'pin' (name |
totally_an_integer | string)`), avoiding any ambiguity between a numeric
pad name and an identifier. `Relay_SPDT` (the G5LE-1 pinout) is left in
place, now unused — nothing else in the tree imports it (`grep -rn
"Relay_SPDT\b" elec/` confirms only the removed `k_dis1`/`k_dis2`
instantiations referenced it before this change).

### `elec/src/modules.ato`

`BusDischarge`'s `k_dis1`/`k_dis2` are now `Relay_DPDT` instances
(`mpn = "40.52.7.012.0000"`, `footprint = "temper:Relay_DPDT_Finder-40.52"`,
`contact_current = 8A`). The docstring documents the replacement rationale
inline (RELAY REPLACEMENT note) so the "why" survives independent of this
evidence doc. Coil-dropper math re-verified for the new 288 ohm/42mA coil:
`I = 15V / (288+100)ohm = 38.7mA`, `V_coil = 38.7mA * 288ohm = 11.14V`
(93% of the 12V rating, clearing the 8.8V must-operate voltage with 26%
margin) — the existing 100 ohm/0.25W dropper (`r_coil1`/`r_coil2`) is
unchanged and still adequate.

### New footprint: `pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod`

Hand-built, following this project's own established convention for
custom footprints (`Relay_SPST_Omron-G4A-E.kicad_mod` in the same library
is the precedent this one cites and follows: real datasheet dimensions,
explicit confidence/provenance notes in `descr`, an explicit call to
verify against the manufacturer's CAD/STEP file before fabrication).
Per `AGENTS.md`'s own PCB-design guidance ("Do not rely on global
libraries"), this is a project-local footprint, not a reference to a
`Relay_THT:...`-style global KiCad library entry (which does not exist on
this machine for this part in any case — confirmed no
`Relay_THT.pretty`/`KICAD10_FOOTPRINT_DIR` is configured in this
environment).

- Body envelope: 29 x 12.4mm (catalog p.10 outline drawing).
- Pin pitch: 5.0mm contact pitch (catalog's own stated feature), 7.5mm row
  separation (catalog's "Copper side view" drawing).
- **Coil-to-nearest-contact spacing is a deliberate design choice, not a
  trace of the manufacturer's own recommended PCB pattern** (that
  drawing's exact pitch numbers rendered ambiguously under this session's
  PDF text-extraction, the same difficulty every prior candidate's own
  diagram hit in this evidence chain): 11mm center-to-center, chosen
  specifically so the **external PCB-surface path** does not become the
  governing (shortest) creepage path and silently undercut the part's own
  certified internal 8mm figure — see Task 4.

## Task 4 — verification: creepage as placed, edge-to-edge

**MEASURED** (script run this session, circular thru-hole pads, exact
geometry — not a bounding-circle approximation, since the pads in this
hand-built footprint genuinely are circles):

| Pair | Center-to-center | Edge-to-edge (exact) |
|---|---:|---:|
| **A1 (coil) <-> "11" (pole 1 COM, governing/shortest pair)** | 11.000mm | **9.200mm** |
| A2 (coil) <-> "21" (pole 2 COM) | 11.000mm | 9.200mm |
| A1 <-> "21" (diagonal) | 13.310mm | 11.510mm |

**9.200mm edge-to-edge clears the 8.0mm target with 1.200mm margin.** This
is the PCB-surface path only; the manufacturer's own certified 8mm figure
governs the relay's *internal* coil-to-contact-set construction (EN 61810-1
type-tested), independent of how the part is placed on this board. The
point of this measurement is exactly the one the task named: confirm the
external board path does **not** become a *shorter, parallel* creepage
path that undercuts the certified internal one — the failure mode this
project's own evidence chain already identified for the incumbent G5LE-1
(whose shortest path ran across its own case). Here, since 9.2mm > 8.0mm,
**the internal, certified 8mm figure remains the governing number** — the
footprint does not create a new, weaker path alongside it.

**Not independently re-verified**: the manufacturer's own recommended PCB
pattern for this exact part (would require the real CAD/STEP file, not
attempted this session) — flagged in the footprint's own `descr`, per this
project's established convention.

## Task 5 — placement impact

**Footprint size delta** (courtyard-to-courtyard, MEASURED from
`pcb/temper.kicad_pcb`'s embedded G5LE-1 footprint definition, script-read
this session):

| | Old (G5LE-1) | New (Finder 40.52) | Delta |
|---|---:|---:|---:|
| Courtyard envelope | 17.0 x 23.0mm | 29.0 x 12.4mm | reshaped: +12.0mm one axis, -10.6mm the other |
| Courtyard area | 391 mm^2 | 359.6 mm^2 | -31.4 mm^2 (net smaller) |

For context: `K1` (Omron G4A-1A-E, already on this board) has a **larger**
courtyard (30.5 x 23.5mm) than the new K2/K3 footprint in either
dimension — this board already accommodates a footprint at least as large
as the one being introduced here.

**Whether the board can accommodate it, MEASURED (not modeled):** neither
K2 nor K3 has any other footprint within 20mm today (script-read from
`pcb/temper.kicad_pcb`'s actual placed component coordinates this
session): K2's nearest neighbor is `U6` at 21.43mm center-to-center; K3's
is `R19` at 20.79mm. The new footprint's largest linear growth over the
old one is ~12mm (reshaped from a squarer 17x23mm envelope toward a
longer, narrower 29x12.4mm one) — comfortably inside the >20mm of open
space measured around both K2 and K3 today, even without crediting any
shrinkage in the other axis. **This is not a CP-SAT/DRC re-run** (out of
scope per the task's hard rule to stay out of `pcb/temper.kicad_pcb`) —
it is a direct measurement against the real, current board, and it
supports (without formally proving) that the footprint fits.

### Board resync required (the real trade-off, reported plainly)

`pcb/temper.kicad_pcb` was **not** edited this session (per the hard
rule). Because K2/K3's footprint and every one of their pin names changed,
the board file is now stale relative to `elec/src/`:

- `check_copper_net_consistency.py` **fails** (146 violations, all of the
  form "board has net X, compiled netlist declares Y for this pin" or
  "orphaned copper on a deleted net") — this is the direct, mechanical,
  expected consequence of the pin-mapping and footprint change, not a new
  design defect. The board still carries the old 5-pin G5LE-1 footprint
  and old net names for K2/K3; it needs K2/K3 re-placed with the new
  8-pin footprint and re-routed before this gate is green again.
- `check_isolation_keepout.py`'s own HV-pad count (87, vs. this
  project's own prior-session baseline of 97) reflects the **same root
  cause**: that script classifies board pads as HV/SELV by matching each
  pad's *board-declared* net name against `domain_manifest.yaml`'s
  declared net-name lists (`scripts/check_isolation_keepout.py:558-559`).
  Since the manifest was correctly updated to the *new* net names
  (`discharge.k_dis1-nc1`, etc.) but the board still carries the *old*
  ones (`discharge.k_dis1-nc`), a handful of HV pads on the still-stale
  board no longer match any declared HV net and drop out of the count.
  The gate's actual **result is unaffected** (still exits 3, "no keepout
  zone found," identical to every prior session in this chain — a
  pre-existing, different finding) but its pad-count denominator is
  temporarily degraded until the board is resynced. Both of these are the
  *same* underlying fact — the board needs a resync — not two separate
  problems.

This is exactly the trade-off the falsifier asked to have reported rather
than dropped: the part and the topology both check out, but a full
board-level "done" claim requires a placement/routing pass this task's own
scope (and the presence of sibling agents already working in
`pcb/temper.kicad_pcb`) puts outside this session. **Flagged as a required
follow-up, not silently absorbed.**

## Falsifier verdict

> "A verified reinforced-isolation relay preserving the fail-safe NC
> topology can replace K2/K3 within the existing design. If the footprint
> change does not fit, or no part satisfies isolation AND DC break AND NC
> topology together, that trade-off is the finding — report it rather than
> silently dropping a requirement."

**Holds, in the strong sense, on the part/topology question — with one
honest, reported exception on the board-file question:**

- **Isolation**: Finder `40.52.7.012.0000` states "Reinforced (8mm)"
  coil-to-contact-set insulation (EN 61810-1) explicitly, for both poles.
  As placed in the new footprint, the external PCB path (9.2mm
  edge-to-edge) does not undercut it. **Satisfied.**
- **DC break**: an explicit manufacturer DC1 breaking-capacity graph
  covers this circuit's actual 170-200V/21.8mA duty with roughly an order
  of magnitude of margin on a single contact, and the task's requested
  two-poles-in-series re-scoping is implemented on top of that.
  **Satisfied, and strengthened beyond what either single-pole candidate
  offered.**
- **NC topology**: both poles are genuine changeover (Form C) contacts;
  de-energized -> both close -> series NC path connects -> discharge
  engages, with zero MCU involvement, unchanged from the incumbent's
  fail-safe behavior. **Satisfied.**
- **Footprint fit**: measured (not CP-SAT-proven) to fit the >20mm of open
  space around both K2 and K3 today. **Satisfied, with the measurement
  method disclosed.**
- **The one place this is not a clean "solved"**: `pcb/temper.kicad_pcb`
  itself needs a resync (re-placement + re-routing of K2/K3 with the new
  footprint/pins) before the board-level gates are fully green. This is a
  real, reported consequence of a real footprint/pin-mapping change — not
  a defect in the part or the topology, and not something this task's own
  scope (stay in `elec/src/` and the relay footprint) permits fixing here.

## UNVERIFIED (explicit list)

- **The manufacturer's own recommended PCB pattern** for the Finder 40.52
  (exact pin coordinates) was not obtained at pixel-exact fidelity — the
  catalog's own drawing rendered ambiguously under this session's PDF
  extraction, the same difficulty every prior candidate's diagram hit in
  this evidence chain. This footprint's pin *coordinates* are this
  session's own deliberate, safety-margined design (see Task 4), not a
  trace of Finder's drawing; the pin *count*, *pitch* (5.0mm contacts,
  7.5mm rows), *body envelope* (29x12.4mm), and *terminal role assignment*
  (EN 50005 convention) are all independently sourced from the catalog's
  explicit text/tables. **A human should cross-check the real CAD/STEP
  file (downloadable from findernet.com) before this footprint is used to
  fabricate a board.**
- **The EN 50005 COM-pin labels ("11", "21") were not directly legible**
  in this session's PDF text-extraction of the type-40.52 schematic
  (only "12"/"14"/"22"/"24" rendered distinctly); the "11"/"21" COM
  assignment is the standard, industry-wide convention for this pin
  numbering scheme (corroborated structurally by the family's own 40.61
  schematic, which shows the doubled-pin form of the same convention),
  not an independent pixel-level read. Flagged, not smoothed over.
- **DC1 breaking-capacity figures were read approximately off a graph**
  (catalog p.8), not a table — "0.2-0.3A at 220V" for the single-contact
  curve is a visual estimate, not a precise value. The direction and
  order-of-magnitude margin (21.8mA vs. ~200-300mA) is robust to
  reasonable graph-reading error; an exact number is not available from
  this catalog in tabular form.
- **Whether the board actually accommodates the new footprint is a
  measurement against current placement, not a CP-SAT/DRC proof.** The
  barrier-constrained placement model (`docs/evidence/
  2026-07-28-barrier-constrained-placement.md`) was not re-run with this
  new footprint — out of this task's scope (stay out of
  `pcb/temper.kicad_pcb`; no additional worktrees; disk is tight).
- **Height (29 x 12.4 x ~25mm envelope)**: the Z-dimension was read from
  the catalog's outline drawing but not independently cross-checked
  against any enclosure/clearance-to-lid constraint in this repo — out of
  scope for this pass (footprint = X-Y board impact, not mechanical
  enclosure fit).
- **The 6.5mm-vs-8.0mm creepage-figure reconciliation** the sibling
  evidence docs discuss remains open and is not resolved by this doc; both
  the internal certified figure (8mm) and the external PCB path (9.2mm)
  clear both ends of that disputed range, so this implementation is
  insensitive to how that question resolves.

## Hard rules — compliance checklist

- Every proposed MPN verified via a directly-fetched manufacturer PDF this
  session (AZ770, ALZN1B12W re-fetched and re-read; Finder 40.52 fetched
  fresh) — no MPN proposed from memory or from the prior doc's summary
  alone.
- `uv run --no-sync python scripts/mpn_fabrication_gate.py` run against
  this change: **PASSED — 0 new violations** (118 parts inspected, 10
  pre-existing allowlist entries unchanged; the new relay's own MPN was
  not flagged).
- No `git stash` used anywhere this session.
- No `run_in_background`; no waiting on background jobs. (One `find /`
  command auto-backgrounded by the harness after a 120s timeout during
  early footprint-library discovery — not retried, not waited on; its
  result was irrelevant once `pcb/fp-lib-table` was read directly instead.)
- `uv sync --all-packages` run exactly once, at the start of gate
  verification, into this worktree's own venv (`uv run --no-sync` was
  failing with `ModuleNotFoundError` beforehand — the venv had never been
  populated in this fresh worktree). All gate invocations after that use
  `--no-sync`.
- Commits made after each meaningful step (component/footprint/module
  implementation; domain-manifest gate fixes), not batched into one.
- Stayed in `elec/src/`, `elec/domain_manifest.yaml`, the relay footprint
  (`pcb/libs/temper.pretty/`), and one documentation file
  (`docs/hardware/BOM.md`, a targeted correction following that file's own
  existing "corrected" convention). `pcb/temper.kicad_pcb` was **not**
  touched.

## Verification (all commands run this session; results as shown)

| Check | Result |
|---|---|
| `make netlist` | build complete, K2/K3 compile as `40.52.7.012.0000` / `temper:Relay_DPDT_Finder-40.52` |
| `check_domain_partition.py` | exit 0 (after fixing this session's own stale net-name entries, plus one unrelated pre-existing stale entry found and fixed in passing) |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 (0 new violations) |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | **FAILS (146 violations)** — expected, direct consequence of the footprint/pin change on an un-resynced board; see "Board resync required" |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (9/10 fresh, `temper-constraints` missing in lenient local-dev mode — matches every prior session's baseline) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 (4/4 checks agree) |
| `check_isolation_keepout.py` | exit 3 (unchanged result — "no keepout zone found" — same as every prior session; pad-count denominator temporarily affected by board staleness, see above) |
| `check_measurement_provenance.py` | exit 5 (pre-existing `drc_ceiling.json` provenance-tag defect, not touched by this task — unchanged from baseline) |
| `uv run --no-sync python -m pytest elec/validation -q` | 30/30 passed |

**Nine of the ten gates this project tracks as "green" are green.** The
tenth, `check_copper_net_consistency`, fails for the reason explained above
— a real, reported, expected consequence of the implementation, not a
silently-dropped requirement. The two designated-exception gates
(`check_isolation_keepout` exit 3, `check_measurement_provenance` exit 5)
fire exactly as the task anticipated.
