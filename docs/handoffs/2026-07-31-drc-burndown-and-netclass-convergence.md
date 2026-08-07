# DRC Burn-Down and Netclass Convergence

**Date:** 2026-07-31
**Trunk:** `codex/drc-burndown-to-zero` (integration branch for gates, netclass, PD3)
**Open PRs:** #514, #513, #512, #501, #498, #488, #460, #446
**Scope:** large — mains-safety netclass correctness, DRC measurement reproducibility, burn-down programme

**Status:** IN PROGRESS. The ceiling is ratcheted and human-approved at `31850d3e6`, but one omission in that commit leaves the DRC gate red. Fix is identified and staged; see "The one blocker" below.

---

## The one blocker

`power_pcb_dataset/drc_ceiling.json` on the trunk lists **12** categories in `violations_by_type`; there are **13**. `track_width` is missing.

Unlisted categories carry an implicit ceiling of zero, so the gate reads the board's 199 track-width violations as a brand-new category and fails:

```
[NEW] track_width 199 > 0
```

Everything else in `31850d3e6` is correct — `error_ceiling: 1348`, `creepage: 314`, `clearance: 502`, and both scattering categories present in `nondeterministic_error_types`. The commit's own `_march` prose mentions `track_width`; only the data omits it.

**Fix:** add `"track_width": 199` to `violations_by_type`. Verified to produce:

```
PASS: temper: DRC 1343/1348 errors, 680/680 warnings within ceiling
```

This is a correction restoring a category the approved trailer already accounted for, not a new raise — the aggregate does not move and the category sits at its exact measured value. Whether it needs its own `Ceiling-Approval:` trailer is a human call.

**Do not** act on the gate's suggestion to lower `error_ceiling` to 1343. That is the observed *minimum* across 120 samples; locking it in would flake immediately.

---

## What the board actually is

Canonical measurement: 120 samples, `kicad-cli 10.0.4 --all-track-errors`, on the trunk.

```
AGGREGATE   min 1343   max 1347   mode 1344 (43/120)

category                min   max   scatter
  clearance             499   501   VARIES
  creepage              311   313   VARIES   <- newly nondeterministic
  track_width           199   199   stable
  shorting_items        118   118   stable
  hole_clearance        102   102   stable
  solder_mask_bridge     69    69   stable
  copper_edge_clearance  15    15   stable
  courtyards_overlap     14    14   stable
  via_diameter / drill_out_of_range / annular_width   4 each, stable
  tracks_crossing 3, hole_to_hole 1                   stable
```

`creepage` scattering is new. Before this work `nondeterministic_error_types` listed `clearance` alone, which was wrong and would have produced intermittent failures of exactly the kind that got written off as flake earlier.

Creepage triage (`docs/evidence/2026-07-30-creepage-205-triage.md`): of 205 measured pre-fix, **135** were genuine HV/mains-to-SELV crossings and board-routable, **5** were same-package isolation gaps fixable only by part choice, **9** are protective-impedance divider interior nodes and an open policy question, and the remainder were rule artifacts. Fixing the rule defect took 205 to 186 with the genuine buckets byte-identical.

---

## Findings worth not re-deriving

1. **The mains conductors had no netclass in the file KiCad reads.** `pcb/temper.kicad_pro` assigns by glob, and KiCad matches case-sensitively: `AC_*` never matched the board's `ac_l` / `ac_n`, and `+*V` cannot match `+170V_BUS`. Line, neutral, the 170 V bus, `SW_NODE` and `PWR_RTN` all inherited `Default` spacing in the fab-authoritative check while `design_rules.py` had them right all along. Corroborated by `"ACMains"` appearing zero times across ~1900 violations. Now carries 80 explicit `netclass_assignments`.

2. **The router ignored netclass trace-width minimums.** `_determine_trace_width` matched `"GATE"`/`"DRIVE"` as keywords and emitted `power_width * 0.6 = 0.3048 mm` — exactly 12 mil — regardless of the 0.4 mm `GateDriveHV` minimum, and `_run_stage5` never threaded `pcb.design_rules` through. All 39 committed `GATE_LS` segments measure `width 0.3048`. Fixed for future routing; the committed segments remain until a re-route.

3. **Some violations cannot be fixed by layout.** `scripts/generate_kicad_dru.py:682-725` records that the TO-247's 1.95 mm edge-to-edge internal pin gap is below the reinforced-insulation requirement, that this is "a real violation this rule is now expected to report, not a bug in this rule", and that resolving it "needs a BOM/footprint/placement change, none of which this script performs." Zero has a hardware dependency.

4. **PD3 replaced PD2.** `HV_CREEPAGE_ENFORCED_MM` is 12.6 mm on the trunk, 8.0 mm on `main`. Revisiting that determination moves the creepage target.

5. **`_is_plane_required_net` was defined but never called.** On one branch the helper sat correctly implemented at line 103 while the scan loop at line 208 still ran `"+" in zone.netName` — which matches `+3V3` and condemns an entire outer copper layer. Dead code beside the loop it was meant to replace reads exactly like a fix and stops reviewers looking further. **Check call sites, not definitions.**

6. **A byte-identical refactor carried a stale fix backwards.** An AST-scripted extraction with a line-conservation assertion was faithful to its source — and its source predated a fix living on a sibling branch, so it silently reintroduced a hardcoded netclass list that had already been corrected. Byte-identical does not mean current.

7. **PR #474 would have regressed three nets if ported.** All 59 of its `netclass_assignments` exist on the trunk's 80, but `+3V3`, `PWM_H` and `PWM_L` disagree (`FinePitch` vs the trunk's `Power` / `GateDriveSELV`), and `design_rules.py` sides with the trunk in all three. `FinePitch` on the SELV-side gate drives would undo the HV/SELV domain split.

---

## Methods that paid for themselves

**Falsifier-first gates.** `scripts/check_hv_netclass_coverage.py` was required to fail on `main` — naming `+170V_BUS` and `HighVoltageIsolated` specifically — before being accepted. It found a live 170 V rail with no netclass and a declared netclass emitting zero rules, neither of which was on anyone's list, within hours of being written.

**Investigate before admitting.** Three times a number changed under scrutiny: 39 track-width violations were a router code defect rather than board debt; 205 creepage violations included 37 rule artifacts; a creepage figure of 203 turned out to be measured on a stale tree. Baselining any of them first would have frozen a defect as an accepted floor.

**Verify by content, never by commit id.** This work was independently re-implemented under different SHAs at least five times by parallel sessions. Message-matching and ancestry checks both give wrong answers.

---

## Environment traps

- `gh pr checks` renders **cancelled** runs as `fail`, and exits non-zero whenever any check is failing — a non-zero exit is not a measurement error. Confirm a job's real conclusion via `gh api repos/BennetLeff/temper/actions/jobs/<id>`. A small number of reported checks means CI **did not run**, never green.
- A fresh `git worktree`'s own `.venv` lacks workspace deps. Use `PYTHONPATH=$PWD/packages/temper-placer/src /Users/bennet/Desktop/temper/.venv/bin/python`, not `uv run`, or run `make venv-isolate`.
- From inside an agent worktree, `cd /Users/bennet/Desktop/temper` resolves to the **shared checkout**, not the worktree. Reads there silently return the wrong tree.
- zsh ties the lowercase variable `path` to `PATH`; using it as a loop variable destroys the shell's `PATH`.
- **Never `git stash` in this repo.** The stash list is 80+ deep, sessions share the checkout, and a timed-out command between stash and pop nearly lost an hour of work. Use `git worktree add --detach <ref>` for before/after comparisons.
- 472 files under `packages/*/target/` are **tracked**. Assuming they were regenerable build output destroyed 10,612 tracked files once.

---

## Open PRs

| PR | Subject | State |
|---|---|---|
| #514 | Ported closeout evidence + closure verification | open, base is the trunk |
| #446 | HV netclass coverage gate | open, both properties pass on the trunk |
| #460 | Domain-clearance bbox constraint, copper-aware | open, other session |
| #488 | Typed coordinate frames migration plan | open, other session |
| #498 | Handoff actionables and board reconciliation | open, other session |
| #501 | Compound safety closure method | open, other session |
| #512, #513 | Provenance records, generated plan index | open, other session |

Closed after content verification: #382, #421, #440, #447, #449, #465, #467, #473, #474, #477.

---

## Next actions

1. Apply the `track_width` fix and land the ceiling. Everything downstream depends on the gate being green and meaningful.
2. Merge #446 so the HV coverage gate is enforced rather than advisory.
3. Start the burn-down's first campaign per `docs/plans/2026-07-30-001-fix-drc-burndown-to-zero-plan.md` — creepage before clearance, on the argument that clearance's larger count is mostly low-voltage pairs.
4. Resolve the 9 protective-impedance divider nodes, which are a policy question rather than a defect.
5. Decide whether prover coverage should ever gate, or remain reported alongside the count.

---

## Coordination note

The dominant cost was not technical. Five pieces of work were completed twice by parallel sessions — the `_astar_reconstruct` split, HV netclass assignments, creepage rule emission, the zone/pour split, and the `_adapter_convert` split. One PR closed on an unverified "already superseded" assumption stranded 75 commits including the HV-safety fixes that took the rest of the day to recover. Worktrees regenerated faster than they could be reaped, peaking near 56 at roughly 1.8 GB each.

The repository did not need another gate. The sessions needed a claim on in-flight work.
