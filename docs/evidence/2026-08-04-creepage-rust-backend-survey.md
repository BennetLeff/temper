<!-- provenance: commit=adcc3e53f20b4a24d189e842864bdffb184ea640 dirty=false (branch feat/creepage-rust-backend, based on origin/main at adcc3e53f; measurements taken from the tree exactly as committed at that SHA) -->

# Creepage cannot be moved to the Rust backend today: `CreepageCheck` and the DRU `creepage` constraint are two different checks, and the Rust board model cannot express the one that matters

**Date:** 2026-08-04
**Scope:** SURVEY / DOC-ONLY. No `src/`, no `pcb/`, no `power_pcb_dataset/`
change. No Rust code was written. `pcb/temper.kicad_dru` was regenerated
(it is gitignored, generated output) in order to measure.
**Verdict:** **Do not port.** The task as scoped ("move the creepage DRC
check from kicad-cli to `temper-drc-rs`") rests on a premise that does not
hold: `temper-drc-rs`'s `CreepageCheck` is not a creepage implementation,
and `temper-drc-rs`'s `BoardState` cannot represent the geometry the real
check consumes. Set-comparison equivalence — the correctness bar the task
sets — is **not definable** between the two, because their violations are
not the same kind of object.

---

## TL;DR

1. **They are not the same check.** The Rust rule scores *one component at a
   time* on its package bounding box. The DRU constraint measures a
   *surface path between two copper items*. Different inputs, different
   violation identity, different threshold, different physics.
2. **84% of the real check's violations are invisible to the Rust board
   model.** 156 of 186 creepage violations involve at least one **pad**.
   `BoardState` has no pad type at all.
3. **`temper-drc-rs` cannot read the board being measured.** It is fed a
   Python dict of the *placer's* model via `build_board_state`; there is no
   `.kicad_pcb` parser in the crate. The ceiling category is measured on the
   *fabrication* board.
4. **The threshold is an open owner decision (PD2 8.0mm vs PD3 12.6mm).**
   Freezing 8.0mm into a new safety implementation now would harden a figure
   that this repo's own most recent evidence argues is not earned.
5. The determinism problem is **real and reproduced here** (12 distinct
   violation sets from 12 samples). It is simply not fixable by this port.

---

## 1. Measurement setup (so the numbers below are checkable)

- **Platform:** macOS 15.5 / Darwin 25.5.0, arm64. **`kicad-cli 10.0.4`.**
  Per `drc_ceiling.json`'s documented version-band delta, none of these
  numbers may be compared against CI's Linux / 10.0.5 figures.
- **Board:** `pcb/temper.kicad_pcb`,
  `sha256 51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af`
  — this is **byte-identical to the hash recorded in
  `power_pcb_dataset/drc_ceiling.json`'s `provenance.inputs`**, so this is
  the same artifact the ceiling was measured against.
- **Rules:** `pcb/temper.kicad_dru` regenerated from
  `scripts/generate_kicad_dru.py`, co-located with the board and
  `pcb/temper.kicad_pro`, `sha256 8994d215bc61eb36…`. **Custom rules
  verified to have fired**: the `creepage` category does not exist in
  stock KiCad DRC output — it is produced *only* by our
  `(constraint creepage …)` rules, and 186 of them were reported. This is
  the trap recorded in the task brief (measuring a board outside `pcb/`
  silently drops every custom rule); it did not occur here.
- **Invocation:** the exact argv `temper_placer.validation._drc_api.run_drc`
  builds — `kicad-cli pcb drc --all-track-errors --format json --output … <pcb>`
  (read from `_drc_api.py:337-352`). `run_drc` itself could not be imported
  (see §7), so the argv was replicated, not called.

Whole-board result, for orientation (12 categories omitted):

| category | measured |
|---|---|
| `clearance` | 378 |
| `creepage` | **186** |
| `shorting_items` | 199 |

These reproduce `drc_ceiling.json`'s recorded observations, which is
independent confirmation the harness measures the same thing the ceiling
was measured with.

---

## 2. The survey verdict: two different checks under one name

### 2.1 What `temper-drc-rs`'s `CreepageCheck` actually computes

`packages/temper-drc-rs/src/rules/safety/creepage.rs` (103 lines), registered
at `rules/mod.rs:237` as `CreepageCheck::new(6.0)`:

```rust
let package_width = comp.width.max(comp.height);
if package_width < self.min_iso_width_mm { /* violation */ }
```

For each component classified as an isolation device (by
`NetClassRules.safety_category == "iso"`, else a substring match against
eight keywords), it compares **the larger side of that component's bounding
box** against a scalar. That is:

- **Unary.** One component per violation. No pair, no distance between two
  things.
- **Not a distance measurement.** `comp.width`/`comp.height` are the
  footprint's bounding-box extents. A package's outline width is not its
  creepage distance across the barrier — pin-to-pin surface path is what
  IEC 60664-1 measures, and it is a property of the pad geometry and any
  package slot, not of the body outline.
- **Threshold 6.0mm, uncited.** The default originates at
  `packages/temper-placer/src/temper_placer/validation/drc_result.py:662`
  (`min_iso_width_mm: float = 6.0`) with **no derivation, no standard
  citation, and no evidence-doc reference anywhere in the tree**. It
  matches neither SSOT figure (PD2 8.0mm, PD3 12.6mm). It does coincide with
  the *clearance* figure in DRU RULE 2 ("AC Mains to LV",
  `(constraint clearance (min 6.0mm))`), which is a plausible but
  unverifiable explanation of where it came from. The surrounding
  docstring claims "per IEC 60335" — that claim is unsupported by anything
  I could find.
- Its stated source file, `packages/temper-drc/src/temper_drc/checks/safety/creepage.py`,
  **no longer exists in the tree**, so the port's own oracle is gone.

### 2.2 What the DRU `creepage` constraint computes

`scripts/generate_kicad_dru.py` emits three
`(constraint creepage (min 8.0mm))` rules (`HV_CREEPAGE_ENFORCED_MM =
HV_CREEPAGE_PD2_MM = 8.0`). KiCad 10.0.4 implements these in
`drc_test_provider_creepage.cpp` via `CREEPAGE_GRAPH` — a real surface-path
graph solver. The generator's own header records the experiment proving
this is not a relabeled clearance check: inserting a board slot between two
pads at a fixed 5.0mm straight-line gap moved the reported creepage from
**5.0000mm to 41.0526mm**.

Measured composition of the 186 violations on this board:

| item pair | count |
|---|---|
| pad ↔ track | 101 |
| pad ↔ pad | 47 |
| track ↔ track | 15 |
| track ↔ via | 15 |
| pad ↔ via | 8 |

- **Binary.** Every violation names exactly two copper items, each with a
  UUID and a position.
- Carries a **measured distance** (`actual 4.2800 mm`), spanning
  0.000–7.985mm against the 8.0mm bar.
- Fires from two rules: `HV to LV` (155) and `HighVoltageIsolated to LV`
  (31). The `AC Mains to LV` rule produced none.
- Involves **27 distinct footprints** (top: R30, L1, RV1, U1, K3, C1, U3, C27).

### 2.3 Side by side

| | `temper-drc-rs` `CreepageCheck` | DRU `creepage` constraint |
|---|---|---|
| violation identity | one component (refdes) | two copper items (UUID pair) |
| input geometry | component bounding box | pads, tracks, vias, board edge |
| computation | `max(w,h) < T` | surface path graph solve |
| threshold | 6.0mm, uncited | 8.0mm, `HV_CREEPAGE_PD2_MM` |
| scoping | components with `safety_category == "iso"` | net-class pair conditions |
| routes around obstacles | no | **yes** (5.0 → 41.05mm slot proof) |
| population on this board | isolation components only | 27 footprints, 186 pairs |

**These are two different checks that share a name.** The correctness bar
the task sets — "compare the Rust violation SET against kicad-cli's
creepage SET, classify every difference" — cannot be applied, because there
is no shared notion of what a violation *is*. A refdes cannot be matched to
a UUID pair. Any mapping I invented to make the sets comparable would be
manufactured equivalence, which the task explicitly forbids.

---

## 3. Why a faithful port is a much larger job than the ticket implies

The blocker is the **data model**, not the algorithm.

`packages/temper-drc-rs/src/board.rs`, `BoardState`:

```rust
pub struct BoardState {
    pub width_mm: f64, pub height_mm: f64, pub margin_mm: f64,
    pub electrical_components: Vec<Component>,
    pub mechanical_components: Vec<Component>,
    pub nets: Vec<Net>,
    pub net_class_rules: HashMap<NetClassName, NetClassRules>,
    pub traces: Vec<TraceSegment>, pub vias: Vec<Via>, pub zones: Vec<CopperZone>,
}
```

1. **There is no pad type.** Grepping `board.rs` for "pad" returns two hits,
   both `Via::pad` (an annular ring *diameter*). Pads are the dominant
   participant in the real check: **156 / 186 violations (84%) involve at
   least one pad**. At most 30/186 (16%) — the track↔track and track↔via
   pairs — involve only geometry `BoardState` currently holds.
2. **There is no board outline.** `board.rs` has zero hits for
   `outline`/`cutout`/`slot`/`Edge.Cuts`. The board is a
   `width_mm × height_mm` rectangle. Creepage paths route *around* board
   edges and through slots — that is the entire difference between creepage
   and clearance, and it is precisely the mechanism the generator's own
   5.0 → 41.05mm experiment demonstrates. A solver that cannot see slots is
   not an approximation of this check; it is a clearance check.
3. **The crate cannot read the artifact being measured.** `BoardState` is
   constructed by `board_py_bridge.rs::build_board_state(board_dict)` from a
   Python dict of the placer's model. There is **no `.kicad_pcb` parser in
   `temper-drc-rs`** (the crate's only mention of `kicad_pcb` is a comment
   in `router_clearance.rs`). The ceiling category is measured on
   `pcb/temper.kicad_pcb`, the fab board. Sourcing the category from Rust
   requires the Rust engine to consume the fab board, which it currently
   cannot do at all.

A faithful port therefore requires, at minimum: a pad model (shape, size,
position, rotation, layer set, net); a board-outline model with cutouts and
slots; a `.kicad_pcb` loader feeding both; and a surface-path graph solver
with same-layer / opposite-layer / over-the-edge traversal semantics. That
is a new subsystem, not a rule port — and each piece is on the safety path.

---

## 4. The determinism problem is real, and reproduced here

12 samples, byte-identical board and DRU, same host, back to back:

| creepage count | samples |
|---|---|
| 185 | 1 |
| 186 | 5 |
| 187 | 6 |

**Distinct violation sets: 12 out of 12 samples.** Every single run produced
a different set. This reproduces PR #722's finding (120 pinned samples →
120 distinct sets) and the `185/186/187` range recorded in
`drc_ceiling.json`. Root cause is unchanged and upstream: KiCad's creepage
provider dedupes through `std::set<std::pair<const BOARD_ITEM*, const
BOARD_ITEM*>>`, ordered by raw pointer value
([kicad#20048](https://gitlab.com/kicad/code/kicad/-/issues/20048)).

For contrast, in the same 12 unpinned samples `clearance` (378),
`shorting_items` (199), `solder_mask_bridge` (154) and `hole_clearance`
(105) were each stable. (12 samples is far too few to claim `clearance` is
deterministic unpinned — PR #722 found it wobbles 377/378 over 120. It is
recorded only to show creepage's instability is not an artifact of this
harness measuring everything badly.)

**So the motivating problem is genuine.** The verdict is not "there is no
problem"; it is "this port does not solve it, and cannot be made to solve it
at the scope stated."

---

## 5. Physics constants: coherent, but with one open owner decision

Per R24 the physics was read, not re-derived. The evidence docs are
**mutually consistent**; the apparent 8.0 vs 10.0 conflict is a *resolved*
supersession, not a live contradiction:

- `2026-07-30-creepage-requirement-reconciliation.md` (PR #442) derived
  **10.0mm** reinforced by treating 400V as falling *between* Table 17 rows.
- `2026-07-30-pd2-creepage-row-determination.md` supersedes it from primary
  text (IS 302-1:2008, pages rendered and read visually): row iv is the
  literal range **">250V and ≤400V"**, so 400V sits *inside* it. PR #442's
  10.0mm was an off-by-one-row error. **PD2 reinforced = 8.0mm.**
- `generate_kicad_dru.py` emits 8.0mm, consistent with that determination
  and with `isolation_constants.MIN_BARRIER_WIDTH_MM = 8.0`.

**The genuinely open item — flagged, not resolved here:**
`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` (dated 2026-08-02)
finds the design is **forced-air-vented, not sealed** — "the board outline
is a plain rectangle with zero vent/compartment provisions", the gasketed
compartment exists only as a prescriptive release requirement — and
explicitly states **"Owner decision requested: which reinforced-creepage bar
governs the board — PD2/8.0mm … or PD3/12.6mm."**
`docs/ENVIRONMENTAL_SPEC.md:45` records PD2 as "conditional", with PD3
"mandatory if that compartment is not implemented and verified."

This is a disclosed open decision, so I am not picking a winner. It is,
independently, a strong reason not to port right now: a new Rust safety
implementation would harden 8.0mm at exactly the moment the operative bar is
under review, and a move to 12.6mm would change both the threshold and the
violation population substantially.

---

## 6. `drc_ceiling.json`: the exact block I am NOT changing

Per the hard rule, this file is untouched. Had the port gone ahead, this is
the block that would have needed owner action:

```json
{
  "board_id": "temper",
  "category_source": "kicad-cli",
  "violations_by_type": { "creepage": 188, … },
  "error_ceiling": 1267
}
```

Three things the owner should know:

1. **`category_source` is a single board-level string, not a per-category
   map.** The task brief describes it as existing "precisely so a category
   can be sourced elsewhere", but as written it cannot express "creepage
   from Rust, everything else from kicad-cli". Sourcing one category
   elsewhere requires a **schema change** to `drc_ceiling.json` plus a
   matching change in `scripts/drc_ratchet.py`'s reader — not a value edit.
   This is a real gap worth recording regardless of this port's fate.
2. **`violations_by_type.creepage: 188` and `error_ceiling: 1267` would both
   move**, by an amount nobody can predict, because switching the source
   changes what is being counted (component-scored vs pair-scored). That is
   an owner decision requiring a `Ceiling-Approval:` trailer if it is a
   raise. I am not authorised to write one and have not.
3. Unrelated to this port, PR #722's measured decreases
   (`clearance` 379→378, `shorting_items` 201→199, `error_ceiling` 1264) are
   still pending and independently confirmed by this session's numbers.

---

## 7. What I could not verify

- **The Rust `CreepageCheck` was never executed.** Its §2.1 behaviour is
  read from source, not observed. Running it needs `BoardState`, which needs
  the placer's Python model, which needs the `temper_design_bundle_python`
  pyo3 extension — and the installed build in `/Users/bennet/Desktop/temper/.venv`
  is **stale** (`AttributeError: module 'temper_design_bundle_python' has no
  attribute 'ViaTemplate'`). This is the same blocker PR #722 hit. Rebuilding
  is a multi-GB release build and the disk constraint (~12 GiB free, another
  agent building) forbade it. **I therefore do not know how many violations
  the Rust rule reports on this board.** It does not change the verdict —
  §2.1's semantic gap and §3's missing pad/outline model are both structural,
  read directly from source — but it is a real gap.
- For the same reason `run_drc` was **not** imported; its exact argv was
  replicated from source. Any behaviour `run_drc` adds beyond that argv
  (it adds none on `origin/main`; PR #722's `KICAD_CONFIG_HOME` pinning is
  not merged) is not covered.
- **`pcb/temper.kicad_dru` was generated with `TEMPER_NET_CLASSES` imported
  from the main checkout** (`/Users/bennet/Desktop/temper`, a different
  branch), because this worktree's `temper_placer` cannot import against the
  stale extension. I diffed the two `design_rules.py` files and confirmed the
  constant-table region differs only by blank lines — but this is a
  cross-tree import and is disclosed as such.
- **No CI evidence.** All figures are local macOS / 10.0.4. Creepage has a
  documented version-band delta; do not compare these to Linux / 10.0.5.
- **12 samples, not 120.** Sufficient to reproduce the instability (12/12
  distinct sets is already unambiguous) but not to characterise the
  distribution. PR #722's 120-sample figures remain the reference.
- **No R1 gates, no mutation corpus, no anti-vacuity demonstration** — these
  presuppose an implementation to test. Nothing was implemented, so there is
  nothing to mutate. Reporting a mutation score here would be fabricating
  evidence for code that does not exist.

---

## 8. Recommendation

**Do not pursue "move creepage to `temper-drc-rs`" as scoped.** If the goal
is a deterministic, ratchetable creepage number, the honest options are:

1. **Fix the ceiling's tolerance of the wobble, not its source.** Record
   creepage as a set-digest-unstable category with an explicit upstream-bug
   reference, and ratchet the other 12 categories to zero. This is the
   cheapest path and it is honest about the instrument.
2. **Build the missing subsystem deliberately**, scoped as what it is: a pad
   + board-outline model, a `.kicad_pcb` loader, and a surface-path solver,
   each with its own R1 gates. This is a multi-PR program on the safety
   path, and should not start until §5's PD2/PD3 decision is settled.
3. **Push upstream.** kicad#20048 is a small fix (order the dedup set by a
   stable key — UUID — rather than pointer value). A patch there fixes the
   measurement for everyone and costs far less than reimplementing the solver.

Whatever is chosen, the **6.0mm uncited threshold** in
`drc_result.py:662` / `CreepageCheck::new(6.0)` should be treated as a
separate defect and resolved on its own: it is on the safety path, it
matches no SSOT figure, and its cited source file no longer exists.
