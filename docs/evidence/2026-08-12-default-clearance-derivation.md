<!-- provenance: commit=106d6ce746af0eabc08b02ba110b4742fecc9738 dirty=UNKNOWN -->

# `Default`'s 0.2mm clearance is KiCad's own un-derived stock default, not a cited fab or safety figure -- and a separate, unplanned discovery shows it is currently the DE FACTO clearance floor for most of the board, safety-relevant crossings included, because of a rule-ordering defect in the DRC generator.

**Verdict up front.** `Default`'s 0.2mm clearance is **an arbitrary conservative default**, not a derived figure. It is KiCad's own built-in stock netclass value, copied unexamined into every one of this repo's four independent netclass surfaces at each surface's founding commit, and it is the one entry in every one of those files that carries no `because`/citation field -- every safety-relevant sibling class (HighVoltage, ACMains, HighVoltageIsolated) does. No safety-relevant net currently falls through to `Default` **by kicad_pro assignment** (verified live against `scripts/check_hv_netclass_coverage.py`: 0 HV-domain and 0 SELV-domain coverage violations). But a separate, unplanned finding, measured directly against the real board, shows `Default`'s 0.2mm bar is **currently the operative clearance floor for the large majority of copper-to-copper pairs on this board regardless of net class** -- including HV-to-SELV crossings that are correctly assigned to `HighVoltage`/`ACMains`/`HighVoltageIsolated` in `kicad_pro` -- because `scripts/generate_kicad_dru.py` places its type-based catch-all rule ("Default routing," 0.2mm) **last** in the generated `.kicad_dru`, and KiCad's custom-rule engine resolves a given constraint type to the **last matching rule in file order**, not the most specific one. Measured directly: moving that one rule from last to first in an otherwise byte-identical `.kicad_dru`, against the identical, unmodified board, moves the `clearance` violation count from **402 to ~505** and reassigns the majority of them from the 0.2mm catch-all to the correctly-cited 2.0-8.0mm HV/ACMains/Isolated rules. **This is not something this task was asked to fix and nothing in the repo was modified to establish it** -- it is reported here because it directly bears on "does a safety-relevant net fall through to `Default`": functionally, today, most of them do, for clearance purposes, regardless of their correct `kicad_pro` assignment.

Re-deriving `Default`'s figure downward (e.g. to 0.15mm) would clear **~42 of the board's 402 measured clearance violations (≈10%)** -- real, but a small fraction of the completion-loss problem four prior efforts already fought over. The repo names **no confirmed, fabricator-verified process-capability number** to re-derive it against in the first place; the candidate figures on file (0.15mm, 0.127mm, 0.152mm) are all independently and explicitly disclosed elsewhere in the repo as unverified.

---

## 1. Where 0.2mm came from

### 1.1 Four independent surfaces, one un-derived number, traced to origin

| Surface | Value | `because`/citation? | Origin commit |
|---|---|---|---|
| `pcb/temper.kicad_pro` `net_settings.classes[name="Default"].clearance` | 0.2 | No (only a later-added functional description, "General signals: SPI, I2C, GPIO...") | `651927a8e` "syncing dec 15" -- the repo's own bulk-import genesis for this file |
| `docs/specs/NET_CLASS_SPECIFICATION.md` §3.1 | "Clearance: 0.2mm (8 mil)" | No | Same bulk-import commit (`192c5f992`/`651927a8e`, both "sync"/"syncing dec 15") |
| `elec/src/constraints.ato` `module Default` | `clearance = 0.2mm` | No | Present from this file's own genesis; every HV/ACMains/HighVoltageIsolated sibling module in the same file sits under a `# Per IEC 60335-1 and IPC-2221B` heading (`elec/src/constraints.ato:76-78`) -- `Default` (`:69-73`) does not |
| `packages/temper-placer/configs/netclass_rules.yaml` `default_clearance_mm` | 0.2 | No | `0638554f3` (#122, 2026-07-07) -- the file's founding commit. Every other class in this file (`ACMains`, `HighVoltage`, `HighVoltageTank`, `HighVoltageIsolated`) carries a `because:` string citing an IEC 60335-1 table; `default_clearance_mm:9` carries none, and no `classes.Default` entry exists in this file at all |

`git log -S` on the constant across all four files turns up no commit that ever explains or derives it -- it is present, unexplained, at each file's first appearance and never touched again except by unrelated bulk syncs.

### 1.2 The one place that DOES say what it is

`docs/brainstorms/2026-07-06-netclass-aware-clearance-ssot-requirements.md:16` -- written by the same author, at the moment the whole netclass SSOT system (of which `netclass_rules.yaml` is the current result) was first scoped -- states the origin plainly:

> "kicad-cli DRC therefore runs at KiCad's default **~0.2mm clearance**, not at the 6mm ACMains-to-signal rule the board *should* have."

Line 40 of the same document, laying out the two-tier design that became `netclass_rules.yaml`, proposes routine (non-safety) pairs "at 0.2mm **or matching the manufacturer default**" -- written as an open, never-resolved alternative, not a decision. Line 171 explicitly punts the manufacturer-capability question ("JLCPCB 6mil / 0.15mm minimums for the common order") to a later planning step that never happened for the clearance axis (only for track-width/via sizing, and even that was left a "user call").

**Conclusion for this section:** 0.2mm is KiCad's own stock software default for its built-in `Default` netclass. It was recognized as exactly that by this repo's own design documents at the moment the SSOT was built, carried forward into four files by simple duplication rather than derivation, and never independently re-derived against either a safety standard or this board's real fabrication process.

### 1.3 A fifth surface: hardcoded, not even wired to the YAML "SSOT"

`scripts/generate_kicad_dru.py:1287-1293` -- RULE 10, the rule the ~500-violation number in this task's brief actually fires against (`condition "A.Type == 'Track' || B.Type == 'Track'"`, matching the brief's citation exactly) -- emits `(constraint clearance (min 0.2mm))` as a **hardcoded literal string**, not a read of `netclass_rules.yaml`'s `default_clearance_mm`. That YAML constant *is* live-consumed elsewhere (`packages/temper-placer/src/temper_placer/router_v6/{stage0_data.py:99,183-184; _astar_nlayer.py:501; layer_capacity.py:128; net_batching.py:685-765; escape_via_generator.py:85; _corridor_backbone.py:195-213}`, `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py:311-332` for CP-SAT's courtyard-clearance term) -- it genuinely drives placement and A* routing. But the number that actually gates DRC pass/fail is a second, independent copy that happens to currently agree with it by manual synchronization, not by code. `netclass_rules.yaml`'s own header claims it is "Single source of truth for per-netclass-pair clearance values" (`packages/temper-placer/configs/netclass_rules.yaml:4`) -- for `Default`'s clearance specifically, that claim is false: there are five copies, none deriving from any other.

---

## 2. Does a safety-relevant net currently fall through to `Default`?

### 2.1 By `kicad_pro` assignment: no, verified live

The task's own framing flags the precedent: PRs #1083 (`42c73e21f`, `PWR_RTN`) and #1087 (`cfc8534af`, 20 SELV nets including `gnd`) found and fixed exactly this failure mode, and both are already merged into `origin/main` (`git merge-base --is-ancestor` confirms both are ancestors of this session's `HEAD`). Re-running the gate live, on this session's actual checkout, not trusting the prior write-up:

```
$ .venv/bin/python scripts/check_hv_netclass_coverage.py
=== PROPERTY 3 (BLOCKING): HV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments (99 assignment(s) on file) ===
  off-board HV-domain nets: 0
  unassigned in kicad_pro: 0
  wrong-safety-category assignments: 0

=== PROPERTY 4 (BLOCKING): SELV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments ===
  off-board SELV-domain nets: 0
  SELV-domain nets unassigned in kicad_pro: 0
  SELV wrong-safety-category assignments: 0

HV netclass coverage gate passed
```

`PWR_RTN` (the HV-domain net the task brief names) resolves to `HighVoltage` (`pcb/temper.kicad_pro:443`); `gnd` (the board's largest net, 86 pads) resolves to `Power`, not `Default` (`pcb/temper.kicad_pro`, `netclass_assignments["gnd"]`). Every one of the 21 nets #1083/#1087 fixed is now correctly categorized. **By this axis, the crux check the task brief poses comes back clean.**

### 2.2 By actual DRC enforcement: functionally, yes -- an unplanned finding

Cross-referencing the real board's 402 measured `clearance` violations (method in §4) against `kicad_pro`'s real assignments shows something the assignment-coverage check cannot see: 75 of the 402 are between a `Default`-class net and a `HighVoltage`-class net, 5 between `Default` and `ACMains`, and 5+4 between `Default` and `HighVoltageIsolated` -- and **332 of the 402, including all of the above, are governed by RULE 10 ("Default routing," 0.2mm)**, not by the correctly-cited "HV to LV" (2.0mm/8.0mm creepage, `scripts/generate_kicad_dru.py:680-691`), "AC Mains to LV" (6.0mm, `:571-579`), or "HighVoltageIsolated to LV" (6.0mm, `:927-936`) rules those class pairs are supposed to hit.

This traces to a genuine defect, verified by direct experiment (not inferred from documentation):

**Experiment.** Two scratch copies of the real board, byte-identical `.kicad_dru` **rule content** (same 31 rules, same 449 lines), differing only in whether the "Default routing" rule block sits **last** (as `generate_kicad_dru.py` emits it today) or is moved to sit **first**, before every class-specific rule:

| DRU variant | `clearance` errors | Governed by "HV to LV" | Governed by "HighVoltageIsolated to LV" | Governed by "Default routing" (0.2mm) |
|---|---:|---:|---:|---:|
| **As generated today** (Default routing last) | **402** | 21 | 4 | 332 |
| Default routing moved first | **~505** (499-505 across runs) | 249 | 73 | 175 |

Nothing about the board changed between these two runs -- same `pcb/temper.kicad_pcb`, same `pcb/temper.kicad_pro`, same 31 DRU rules, only their order. Moving the catch-all rule earlier lets the specific, safety-cited rules win instead, and **the true violation count for HV/ACMains/HighVoltageIsolated-to-LV crossings jumps roughly 7x (44 -> 326)**, while `creepage` (a separate constraint type, unaffected by clearance-rule ordering) stays exactly at 200 in both runs -- confirming the effect is specific to which *clearance* rule is selected, not a broader measurement artifact.

This is consistent with KiCad's documented custom-rule semantics: for a given constraint type, the **last matching rule in file order** wins, not the most specific. `generate_kicad_dru.py` places RULE 10 last, deliberately, as a catch-all for tracks with no more specific rule (`scripts/check_hv_netclass_coverage.py:86-89` documents exactly this intent: "`Default`... already covered by `generate_kicad_dru.py`'s type-based 'Default routing' catch-all rule... working exactly as intended"). That reasoning holds for nets that are genuinely unclassed. It does **not** hold under KiCad's real precedence rule for nets that already have a specific, correctly-assigned, safety-cited rule earlier in the file -- because RULE 10's condition (`A.Type == 'Track' || B.Type == 'Track'`) matches essentially every copper-to-copper pair on the board, and being last, it silently supersedes those specific rules wherever both conditions are satisfied, which is nearly always.

**Practical consequence:** as currently generated and currently shipped, `Default`'s 0.2mm figure is not a bar that only governs SELV-to-SELV copper. It is, today, the enforced clearance floor between `HighVoltage`/`ACMains`/`HighVoltageIsolated` copper and everything else too, for any pair spaced between 0.2mm and its true 2.0-8.0mm requirement -- those pairs pass DRC silently today and would only surface as violations if RULE 10's position in the file were corrected. No fix is proposed or applied here (out of this task's scope, and `pcb/temper.kicad_pcb` was never touched); this is reported strictly as a measured fact bearing directly on the task's own crux question.

---

## 3. What the repo records about the intended fabrication process

`docs/PCB_DFM_GUIDELINES.md` (all 82 lines read in full) specifies SMT component-body/pad spacing (§1.1, 0.5mm/0.3mm -- footprint keepout, not copper trace/space), fiducial geometry (§2), test-point pitch (§3), and THT hole sizing/annular ring (§4, "0.5mm minimum for high-current paths"). **It specifies no copper trace width or trace-to-trace spacing minimum anywhere** -- confirmed by reading the complete document, not a keyword search. Its header (`:4`) names a **"Target Process"** of "prototype PCBA (e.g., JLCPCB, PCBWay)" -- illustrative examples, not a committed fabricator.

`docs/specs/PCB_SPECIFICATION.md` §4.1 (`:136-137`) and §12.2 (`:507`) both state "Min Trace/Space: 0.15mm (6 mil)" -- the one figure in the repo that looks like a real process-capability number. But: (a) it comes from the same unauthored bulk-import commit as everything else in §1.1 (`651927a8e`, `git log --follow --diff-filter=A` shows no other origin); (b) §12.1 (`:488-495`) lists **four "Recommended PCB Fabricators"** (JLCPCB, PCBWay, OSH Park, Elecrow) side by side with no single one marked as the board's actual, chosen fab house.

`packages/temper-drc-rs/src/manufacturing.rs:196-234` carries `FabricationEnvelope::jlcpcb_standard()` (min trace/clearance 0.127mm), `::jlcpcb_hdi()` (0.075mm), and `::oshpark()` (0.152mm) -- named, plausible-looking process classes. Every one of their doc comments says, verbatim, **"Not fabricator-verified"**, and the module's own header (`:18-65`) explains these are ported from "a pre-migration Python placer-core implementation for parity, not independently confirmed against a real PCB fabricator's capability sheet."

Two independent, dedicated planning documents -- `docs/plans/2026-08-07-002-feat-wasm-tier-phase2-4-plan.md:555,568,572,579,991` and `docs/plans/2026-08-11-001-feat-wasm-tier-phase2-plan.md:100,212,273,331-345,485,523` -- each re-pose the same open maintainer question and each independently record the same finding in nearly the same words:

> "No file in the repository names this board's actual PCB fabricator or that fabricator's stated process capabilities."

**Conclusion for this section:** the gap is real, and the repo already knows it. There is no confirmed, fabricator-verified trace/space capability number on file to re-derive `Default`'s clearance against. The 0.15mm figure in `PCB_SPECIFICATION.md` and the 0.127-0.152mm range in the `FabPreset`/`FabricationEnvelope` constants are mutually corroborating in the right ballpark (standard 4-layer prototype houses), but every one of them is independently and explicitly disclosed elsewhere in this same repo as unverified. Per this task's instruction, no fabricator-verified figure is manufactured here to fill that gap.

---

## 4. Quantification: how many violations would a corrected figure clear?

### 4.1 Method

`pcb/temper.kicad_pcb` and its real project context (`pcb/temper.kicad_pro`, `pcb/fp-lib-table`, `pcb/libs/`) copied read-only into a scratch directory; `.kicad_dru` regenerated fresh via `generate_kicad_dru.py`'s `generate_dru()` (imported directly, not via its `main()`, so nothing under `pcb/` was ever written); DRC run via `temper_placer.validation._drc_api.run_drc` (single-thread-pinned, `--all-track-errors`, matching this repo's own deterministic-measurement protocol). `clearance` error count: **402, identical across 5 repeated runs** (no sampling variance for this category, consistent with this repo's own prior findings that `clearance` is fully deterministic on this board once `--all-track-errors` is set).

kicad-cli's JSON report embeds the operative rule name and the measured **actual** spacing in every violation's `description` (e.g. `"Clearance violation (rule 'Default routing' clearance 0.2000 mm; actual 0.1226 mm)"`) -- re-grading at an alternative threshold means comparing the recorded `actual` figure against the candidate bar, with **no re-routing and no board mutation**, exactly as instructed.

### 4.2 Results

Of the 402 `clearance` violations: **110 are between two genuinely `Default`-class nets** (confirmed via `kicad_pro`'s real `netclass_assignments`, not guessed), governed by RULE 10 (`n=109`) or the implicit board-level same-netclass clearance (`n=1`, same 0.2mm value either mechanism). Re-grading their real `actual` measurements against candidate figures:

| Candidate figure | Source | Default-Default violations that clear | Remaining |
|---|---|---:|---:|
| 0.10mm | (no repo citation -- shown for range) | 80/110 | 30 |
| 0.127mm | `FabPreset::jlcpcb_standard` (unverified) | 50/110 | 60 |
| 0.15mm | `PCB_SPECIFICATION.md` §4.1/12.2 (unverified fab tie) | 42/110 | 68 |
| 0.152mm | `FabPreset::oshpark` (unverified) | 11/110 | 99 |

Median actual spacing among the 110 is **0.1226mm** -- below every candidate figure -- so most of these 110 need re-routing regardless of where `Default`'s bar is set.

**Net effect: lowering `Default` to 0.15mm would clear ~42 of the board's 402 measured `clearance` violations (≈10%).** This is a real but modest fraction of the "clearance ≈ 500" problem the task's context describes four independent efforts failing to move. It does not, by itself, change the completion picture PR #1106 already established.

### 4.3 What remains, and whether any of it is safety-relevant

The 68 (at 0.15mm) or 60 (at 0.127mm) remaining Default-Default violations are, by definition, SELV-SELV pairs (§2.1 confirms `Default` currently carries no misassigned safety-relevant nets) -- **none are safety-relevant**. The 292 non-Default-Default clearance violations are untouched by any change to `Default`'s figure. Separately, and much larger: §2.2's rule-ordering finding means the true count of under-separated HV/ACMains/HighVoltageIsolated-to-LV pairs is **not** the 44 currently reported as such, but closer to the ~326 that surface once RULE 10 stops shadowing the specific rules -- and every one of those **is** safety-relevant. Re-deriving `Default`'s number does nothing for that population; only reordering the DRU generator would.

---

## 5. Recommendation

**Do not change the value** (per this task's instruction; nothing was changed). If it is revisited in a future, reviewed decision:

- 0.2mm is an arbitrary, un-derived default (KiCad's own stock value), not a safety or cited-fab figure -- re-deriving it downward would be a legitimate correction in principle, not a loosening of a real safety margin, **as long as** the DRU ordering defect in §2.2 is fixed first or in the same change (otherwise "correcting" `Default` corrects a number that is currently masking, not just governing, safety-relevant crossings, and the two changes should not be evaluated independently).
- The repo names no fabricator-verified capability number to re-derive it against. Any correction should either get a real capability sheet from whichever house actually fabricates this board, or explicitly adopt one of the existing unverified candidates (0.15mm / `PCB_SPECIFICATION.md`, or `FabPreset::jlcpcb_standard`'s 0.127mm) with the same "not fabricator-verified, findings are bounds on relevance" caveat the wasm-tier plans already use for the identical gap.
- Even the best case (0.15mm) clears only ~10% of the board's clearance violations -- this does not substitute for "more board area, a coarser DRC model, or accepted completion loss," matching PR #1106's own conclusion.
- **Flag `scripts/generate_kicad_dru.py`'s RULE 10 ordering as a separate, higher-priority follow-up.** It is a bigger and more safety-relevant gap than `Default`'s own value: it currently makes 0.2mm the de facto clearance requirement for most HV-domain-to-SELV crossings on this board, silently substituting for their correctly-assigned 2.0-8.0mm rules, and this task's `-S`-log/citation trail found no prior recognition of it in the repo's history or its test suite (`scripts/tests/test_generate_kicad_dru.py` has no coverage of rule precedence/ordering).
