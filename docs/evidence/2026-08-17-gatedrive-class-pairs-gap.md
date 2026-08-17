<!-- provenance: commit=0a3cfcb55 (branch fix/netclass-classifier-and-creepage-gate,
PR #1322, checked out as agent/netclass-class-pairs-derive), worktree
agent-ad6ce2de93095575d. pcb/temper.kicad_pcb sha256
6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 verified
unchanged before/during/after this task (read-only against the board; never
opened for writing). Venv: `make venv-isolate` in THIS worktree only. All
measurements below are live, run in this worktree's own .venv against the
real committed board, not estimated. -->

# `class_pairs` has zero rows for `GateDriveHV`/`GateDriveSELV` — closing the gap PR #1322 activated

STATUS: in progress, committing incrementally per the working-pattern rule.

Builds on PR #1322 (`fix/netclass-classifier-and-creepage-gate`,
`docs/evidence/2026-08-17-netclass-classifier-manifest-and-ieccreepagegate-liveness.md`).
That PR fixes `netclass_constraints.py` to classify nets from the
`TEMPER_NET_ASSIGNMENTS` SSOT instead of a 4-bucket name-keyword heuristic —
a real fix (J1↔K1 goes from *no constraint* to a constraint) — but it
activates a dormant gap: `netclass_rules.yaml`'s `class_pairs` table has zero
rows for `GateDriveHV`/`GateDriveSELV`, so cross-domain pairs touching either
class fall through to a weaker default
(`max(class_a.clearance, class_b.clearance)`, as low as 0.25mm) instead of
this table's established 6.0mm cross-domain figure.

## 1. Is the `class_pairs` "placer-feasibility model" a deliberate two-tier design?

**Yes — established, in-file, prior to this task.** `netclass_rules.yaml`'s
own header comment (added by PR #1226, "label 6.0mm legacy family UNSOURCED",
responding to the 2026-08-15 safety-citation audit
`docs/evidence/2026-08-15-safety-constant-census.md`) states explicitly, for
every 6.0mm figure in the file:

> "This config is the placer-feasibility model; the fab-authoritative
> enforcement point is `scripts/generate_kicad_dru.py`'s cited figures
> ... Re-sourcing or re-deriving these figures is a separate, attributed
> decision; the value is NOT changed here to avoid silently weakening the
> placer's conservative model."

This is corroborated by a live measurement already on record: PR #1321 wired
the *real* PD3-derived 12.6mm figures into the placer's constraint
generation. It solved (CP-SAT `optimal`, 94.7s, J1/K1 legally placed at
148.9mm) but cost connectivity **63/139 → 50/139** on a full re-solve — the
real safety figures are far more constraining than this feasibility model,
which is presumably *why* the feasibility model exists at a smaller,
deliberately-conservative-but-solvable 6.0mm rather than the true 12.6mm.

**Conclusion: do NOT derive `class_pairs` from `pair_clearance.generated.yaml`
/ `pair_creepage.generated.yaml`.** Those are the fab-authoritative DRU
tables (2.0–12.6mm real figures); `class_pairs` is a separate, intentionally
looser placer-feasibility model, and replacing its values with the DRU
figures would be an uncoordinated safety-value change with a large,
unverified connectivity cost — exactly what the task's hard rule "if any
existing pair's figure changes, stop and report" is guarding against. This
correction supersedes an initial reading of the task brief that suggested
deriving from the SSOT; verified against file evidence before acting, not
by inspection alone.

## 2. Is the missing `GateDriveHV`/`GateDriveSELV` gap itself deliberate?

**No — it is an omission that predates the class split, not a decision.**

`git log --follow` on `netclass_rules.yaml` shows commit `81f3c69a5`
("HighVoltageIsolated closure, GateDrive HV/SELV split, U2 stackup role
(slice 4 of 8)", PR #434, 2026-07-28) did both things in the same commit:

- Added the brand-new `HighVoltageIsolated` class **and its 4 class_pairs
  rows** (`HighVoltageIsolated-Signal/-GND/-Power/-FinePitch`, all 6.0mm),
  with a comment explicitly walking through the convention: "Same 6.0mm
  figure used for every other HV-domain-to-LV class_pair entry in this file
  below, for internal consistency with that convention."
- Split the single `GateDrive` class into `GateDriveHV`/`GateDriveSELV`,
  commit message: "All clearance/width/via values unchanged -- class-model
  change only." **No class_pairs rows were added for either half.**

Checked whether the split *removed* pre-existing `GateDrive` rows:
`git show 81f3c69a5^:.../netclass_rules.yaml`'s `class_pairs` block has
exactly 9 rows (`ACMains-{Signal,GND,Power,FinePitch}`,
`HighVoltage-{Signal,GND,Power,FinePitch}`, `ACMains-HighVoltage`) — **zero
mention of `GateDrive` in any form.** The undifferentiated class never had
class_pairs protection either. So this is not a "split dropped rows" defect;
it's a "class introduced without rows, twice, and only the other class
introduced in the same commit (`HighVoltageIsolated`) got them" oversight.

## 3. The fix: complete the matrix in the SAME feasibility-model terms as every sibling

Added 10 rows to `packages/temper-placer/configs/netclass_rules.yaml`'s
`class_pairs`, all at the SAME 6.0mm figure used by every other HV-domain
class in this table, with the SAME "UNSOURCED legacy... placer-feasibility
model only" disclaimer already established by PR #1226 for every existing
6.0mm row. No new figure invented — this is the file's own repeatedly-used
convention value, applied to the two classes that were skipped:

```
GateDriveHV-FinePitch:              6.0
GateDriveHV-GND:                    6.0
GateDriveHV-Power:                  6.0
GateDriveHV-Signal:                 6.0
GateDriveHV-GateDriveSELV:          6.0
ACMains-GateDriveSELV:              6.0
GateDriveSELV-HighVoltage:          6.0
GateDriveSELV-HighVoltageTank:      6.0
GateDriveSELV-HighVoltageIsolated:  6.0
GateDriveSELV-HighVoltageSignal:    6.0
```

Derivation of this exact set (10 pairs, not more, not fewer), by symmetry
with the file's own established pattern:

- `GateDriveHV` (`safety_category: HV`) gets a row against each of the 4
  standard LV targets every other HV-domain class carries
  (`FinePitch`/`GND`/`Power`/`Signal`), plus `GateDriveSELV` itself
  (`safety_category: LV` — the SELV/primary side of U7's own reinforced
  isolation barrier, per `elec/domain_manifest.yaml`, same barrier
  `GateDriveHV`'s docstring already names).
- `GateDriveSELV` (`safety_category: LV`) symmetrically gets a row FROM
  every HV-domain source that already has an explicit "-to-LV" block in this
  file (`ACMains`, `HighVoltage`, `HighVoltageTank`, `HighVoltageIsolated`,
  `HighVoltageSignal`) — mirroring exactly how `Signal`/`GND`/`Power`/
  `FinePitch` already receive rows from all five of those sources.
- **No** `GateDriveHV-ACMains` / `GateDriveHV-HighVoltage*` row is added:
  this mirrors the file's own existing, explicit choice not to protect
  same-broader-HV-domain sub-class pairs via `class_pairs` at all (there is
  no `HighVoltage-HighVoltageTank` row, no `HighVoltageIsolated-HighVoltage`
  row, etc. either — the block comments say this is deliberate, "the
  same-domain figure is the DRU's business"). `GateDriveHV` and
  `HighVoltage`/`ACMains`/etc. are all HV-domain siblings around the same
  switch node; that separation is the DRU's/same-class NoOverlap2D's
  business, not this table's, exactly like its siblings.
- **No** `HighCurrent`/`HighSpeed` rows added: those two classes have zero
  `class_pairs` rows on *either* side, a separate pre-existing gap not
  scoped to "GateDriveHV/GateDriveSELV have zero rows" (the task's stated
  target). Flagged, not fixed — see §6.

## 4. Verification: whole-board pairwise comparison, old (pre-#1322) vs fixed

Ran a live comparison against the real committed board's real netlist (168
components, `pcb/temper.kicad_pcb`, sha256 unchanged, verified above),
comparing THREE constraint sets produced by
`generate_netclass_separated_constraints`:

- **old-main**: the OLD classifier (`classify_net_type`, the pre-#1322
  4-bucket name-keyword heuristic, reconstructed verbatim from
  `caec25d61:.../netclass_constraints.py`, main's HEAD before #1322) +
  the file's 21 PRE-EXISTING `class_pairs` rows only (the 10 new rows
  explicitly excluded, so this is exactly what main measured before #1322).
- **fixed**: the NEW classifier (`design_rules.get_rules_for_net`, PR
  #1322's fix, unchanged by this work) + the file as it now stands on disk
  (31 rows: 21 pre-existing + 10 new).

Every one of the real board's `C(168,2) = 14028` component pairs was
evaluated; 9,693 got a constraint under old-main, 8,978 under fixed.

**Result: 0 genuine cross-domain regressions.** 2,483 pairs' figure did
change (fixed < old-main for that pair), but **every one** of them is a
same-broader-HV-domain (or same-LV) sub-class correction — verified by
checking each changed pair's NEW resolved classes' `safety_category`
(`AC`/`HV` collapsed to one "HV" bucket, else "LV") and confirming both
sides land in the same bucket. These are the exact same category PR #1322's
own evidence doc already documents for its other 102 non-GateDrive pairs:
"same-HV-domain pairs... accidentally getting the 6.0mm cross-domain figure
under the old [coarse] scheme... now correctly recognized as same-domain."
Zero pairs where one side resolves HV/AC and the other LV decreased below
its old-main value. Script: see `verify_final.py` logic reproduced below.

```
components: 168
old-main pairs: 9693
fixed pairs: 8978
same-broader-domain corrections: 2483
GENUINE cross-domain regressions (MUST BE 0): 0

J1<->K1:
  old-main: None
  fixed: 6.0  classes: Signal / HighVoltage

Gate-drive pairs count in fixed set: 660 total pairs touching GateDriveHV/GateDriveSELV
  of those, at the new 6.0mm figure: 350
```

**J1↔K1 = 6.0mm.** This is the `HighVoltage-Signal` row (a PRE-EXISTING
row, untouched by this change) — J1 resolves `Signal`, K1 resolves
`HighVoltage`, not one of the 10 new GateDrive rows. Matches PR #1322's own
reported figure exactly; not adjusted, not re-derived.

Also verified, against the state BEFORE this fix (PR #1322 as merged, i.e.
"broken"): 314 real component pairs on the board are strengthened by the 10
new rows (0→6.0mm or partial→6.0mm), spanning exactly 7 of the 10 possible
new class-pair *types* (the other 3 —
`GateDriveHV-GND`, `ACMains-GateDriveSELV`, `GateDriveSELV-HighVoltageIsolated`
— complete the matrix for classes not currently paired on this specific
board layout, matching the file's own precedent of completing full
class-pair blocks rather than only the currently-observed subset). **Zero**
pairs were weakened going from broken to fixed. **All** strengthened
class-pair types involve `GateDriveHV` or `GateDriveSELV`, confirming this
is the correct, complete, and sufficient fix for the gap as scoped.

## 5. No existing value was read or changed

The verification script asserts (`assert key not in cp`) before writing
each of the 10 new keys, so the addition cannot silently overwrite an
existing row. `git diff` on `netclass_rules.yaml` (see below) is
purely additive — every pre-existing line, value, and comment is byte-for-byte
unchanged.

## 6. Flagged, not fixed (adjacent gaps, out of this task's scope)

- **`HighCurrent`/`HighSpeed` have zero `class_pairs` rows on either side** —
  a separate, pre-existing gap (not "GateDriveHV/GateDriveSELV have zero
  rows", the task's stated target). If either class is ever resolved as a
  component's representative class against an HV/AC-domain class, it will
  fall to the same weak `max_self` default this task just fixed for
  GateDriveHV/GateDriveSELV. Registered as a candidate for the drift gate
  (§7) rather than fixed here — fixing it requires the same "what LV/HV
  siblings does it need" judgment call this doc made for GateDriveHV/SELV,
  which is a scoped decision this task was not asked to make.
- **`hb-gnd` is HV in `elec/domain_manifest.yaml`/`clearance_check.py`'s
  `_classify_net_class` but GND/LV in `core/design_rules.py`'s
  `TEMPER_NET_ASSIGNMENTS`** (the table `netclass_constraints.py`'s new
  classifier reads) — flagged already by PR #1322 and PR #1300; not
  reclassified here (that is `TEMPER_NET_ASSIGNMENTS`, a widely-shared SSOT
  outside this task's file, and reclassifying a net unilaterally is exactly
  what the hard rules forbid). Registered in the drift gate (§7).

## 7. Registered in `scripts/check_fact_registry_drift.py`

(next: add a fact entry asserting `class_pairs` carries a row for every
{ACMains,HighVoltage,HighVoltageTank,HighVoltageIsolated,HighVoltageSignal,
GateDriveHV,GateDriveSELV} × {FinePitch,GND,Power,Signal} + the
GateDriveHV↔GateDriveSELV / ACMains↔HighVoltage-family completeness this doc
derived, so a future class addition that skips class_pairs rows is a gate
failure, not a silent weakening. Also register the `hb-gnd` two-homes
divergence (§6).)

## Files touched

- `packages/temper-placer/configs/netclass_rules.yaml` — 10 new
  `class_pairs` rows, purely additive.
- `scripts/check_fact_registry_drift.py` — (pending) new fact(s).

## Files read, not touched

- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py`
  (PR #1322's fix, unmodified by this work — the classifier that makes the
  gap live)
- `packages/temper-placer/configs/pair_clearance.generated.yaml`,
  `pair_creepage.generated.yaml` — read to confirm they are the SEPARATE,
  fab-authoritative DRU tables, not the right derivation source for
  `class_pairs` (§1)
- `docs/evidence/2026-08-15-safety-constant-census.md`,
  `docs/evidence/2026-08-17-netclass-classifier-manifest-and-ieccreepagegate-liveness.md`
