<!-- provenance: commit=11b344c65953c499384445661fc3df5065e06c5a dirty=false (HEAD at every post-fix measurement below, worktree clean; the pre-fix column was measured with scripts/generate_kicad_dru.py checked out from origin/main commit=812719e2aa8fc5be69448a1334e808b607a43970, same clean worktree). Branch fix/dru-rule-precedence, worktree /home/bennet/Desktop/temper-dru-precedence. pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 and pcb/temper.kicad_pro sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac -- NEITHER FILE WAS EVER WRITTEN by this task (`git status --porcelain` clean for pcb/** throughout; the only tracked files this branch changes are scripts/generate_kicad_dru.py, scripts/tests/test_generate_kicad_dru.py and this document). Every DRC measurement below ran against read-only scratch copies of the real board outside the repo, under this session's scratchpad, each carrying the real pcb/temper.kicad_pro, pcb/fp-lib-table and pcb/libs/ plus a .kicad_dru generated into the scratch directory. kicad-cli 10.0.5 (`kicad-cli version`), invoked exactly as temper_placer.validation._drc_api.run_drc does: --all-track-errors, single-thread-pinned KICAD_CONFIG_HOME. power_pcb_dataset/drc_ceiling.json is NOT touched by this task -- see sec 8. No subagents were dispatched. -->

# KiCad enforces the LAST matching rule, not the most specific one — so this board's mains-to-SELV clearance bars have been disabled by a catch-all for as long as they have existed, and correcting it exposes ~1,291 real HV-to-SELV clearance violations. Along the way: `clearance` 499 and `shorting_items`/`track_width` 199 are kicad-cli **reporting caps**, not counts.

**Verdict up front.**

1. **The precedence claim is true, and now proven two ways.** KiCad's own documentation says rules are evaluated in reverse file order and the first match found wins; measured against this repo's board, a 0.001mm catch-all clearance rule appended **last** drops `clearance` from 402 to 71, while the byte-identical rule placed **first** leaves it at 402 (sec 1).
2. **Fix: rules are now emitted weakest-first, so last-matching-wins is numerically identical to strictest-wins** — rule bodies byte-identical, only their order changes — plus a fail-closed guard that re-derives the winner for every rule pair over a finite world model and refuses to emit a file where any rule can still be overridden by a weaker one (sec 3).
3. **Four instances of the defect existed, not one** (sec 2). `Default routing` (0.2mm) over ten safety rules; `Ground clearance` (0.15mm) over four HV-to-LV rules (latent — the class it names does not exist on this board); `GateDriveSELV near HV` (0.5mm) over `HV to LV` (2.0mm), which is a **SELV-side** class downgrading a reinforced barrier; and `HighVoltageIsolated same side` (2.0mm) over `AC Mains to LV` (6.0mm).
4. **The safety finding: 1,291 distinct HV/mains-to-SELV clearance violations exist on the committed board; 44 are reported today** (sec 5-6). Full net/component/gap breakdown, measured, in sec 6 and `docs/evidence/2026-08-12-dru-rule-precedence-violations.csv`.
5. **The reframing: `clearance` saturates at 499 and `track_width`/`shorting_items`/`silk_overlap` at 199 — these are KiCad GUI truncation constants (`#define EXTENDED_ERROR_LIMIT 499`, `#define ERROR_LIMIT 199`) that kicad-cli inherits** (sec 4). Proven by a DRU requiring 20mm between every copper pair on the board still reporting exactly 499. This is a complete mechanical explanation for the "clearance ≈ 500, immune to every lever" invariant that four investigations chased — and it is **not** the "uniform 0.2mm ⇒ density-only" mechanism the hypothesis proposed (sec 7).
6. **The fix does not newly break a required gate — the gate is already red on `origin/main`** (clearance 402 > ceiling 386, creepage 199 > 186). It does widen the failure. Recommended staging and a warning for whoever re-derives the ceiling: **do not ratchet a saturated number** (sec 8).

---

## 1. The precedence semantics, verified rather than assumed

### 1.1 Documentation

KiCad's documentation source (`kicad-doc`, `src/pcbnew/pcbnew_advanced.adoc`, "Custom Design Rules"), fetched live:

> "Rules are evaluated in reverse order, meaning the last rule in the file is checked first. Once a matching rule is found for a given set objects being tested, no further rules will be checked."

> "The order of the two objects is not important because the design rule checker will test both possible orderings."

Both statements matter. The first is last-matching-rule-wins. The second means a condition of the form `A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage'` matches a pair with the HV item on either side — so the shadowing analysis in sec 2 must consider both orderings, and it does.

### 1.2 Falsification against the real board

Documentation is not enough — a repo document asserting a standards behaviour that did not hold has bitten this project before. Two DRC runs on read-only scratch copies of the unmodified `pcb/temper.kicad_pcb`, with a probe rule whose body is byte-identical in both and whose only difference is position:

```
(rule "ZZ precedence probe"
   (condition "A.Type == 'Track' || B.Type == 'Track'")
   (constraint clearance (min 0.001mm))
)
```

| DRU variant (32 rules, identical bodies) | `clearance` | `creepage` |
|---|---:|---:|
| generated file, unmodified | 402 | 200 |
| probe appended **last** | **71** | 200 |
| probe inserted **first** (immediately after `(version 1)`) | **402** | 199 |

A 0.001mm rule placed last wins over every rule above it, collapsing `clearance` to the 71 pairs the probe's condition does not match (pad-to-pad, pad-to-via, zone). The same rule placed first is invisible. **Last-matching-rule-wins is confirmed; first-matching-wins and most-specific-wins are both falsified.**

The same falsifier is now a permanent test (`scripts/tests/test_generate_kicad_dru.py::TestRulePrecedenceIsLastMatchingWins`), running real kicad-cli on the existing isolated two-pad fixture: an identical 3.0mm clearance figure **fails** the fixture's 1.95mm gap when emitted last and **passes** it when emitted first with a 0.5mm rule after it.

### 1.3 `track_width` is not a paired constraint

The analysis below treats `clearance`, `creepage`, `hole_clearance` and `hole_to_hole` as pair constraints and `track_width` as unary. Measured justification, not assumption: on the real board `HighVoltage trace width` (3.0mm) fires 127 times even though `Power trace width` (1.0mm) is emitted after it. If KiCad paired and swapped items for `track_width`, the later 1.0mm rule would win on every HighVoltage/Power pair and those 127 could not exist.

---

## 2. Every instance of the defect in the emitted file

Method: `find_shadowing()` (now shipped in `scripts/generate_kicad_dru.py`) parses the emitted rules, compiles each condition into a predicate, and enumerates a finite world model — every ordered pair of net classes drawn from `TEMPER_NET_CLASSES` ∪ every class name any condition mentions ∪ an `__unlisted__` sentinel, crossed with item type (Track/Pad/Via/Zone), pad type, and reference-equality — evaluating each condition in **both** A/B orderings. For each constraint type it identifies the last matching rule (what KiCad enforces) and the strictest matching rule (what the file's own cited figures require), and reports every case where they differ.

Against `origin/main`'s generator, **four rules shadow eleven others**:

| # | Shadowing rule (wins) | Value | Shadowed rule (loses) | Cited value | Live on this board? |
|---|---|---:|---|---:|---|
| 1 | `Default routing` (last in file) | 0.2mm | `AC Mains to LV` | 6.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `AC Mains to HV` | 3.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `HV to LV` | 2.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `HighVoltageTank to LV` | 2.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `HighVoltageIsolated same side` | 2.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `HighVoltageIsolated to LV` | 2.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `HV internal same footprint` | 2.0mm | **yes** |
| 1 | `Default routing` | 0.2mm | `GateDriveHV near HV` | 0.5mm | **yes** |
| 1 | `Default routing` | 0.2mm | `GateDriveHV to ACMains` | 0.5mm | **yes** |
| 1 | `Default routing` | 0.2mm | `GateDriveHV to HighVoltageIsolated` | 0.5mm | **yes** |
| 2 | `Ground clearance` | 0.15mm | `AC Mains to LV` | 6.0mm | latent |
| 2 | `Ground clearance` | 0.15mm | `HV to LV` | 2.0mm | latent |
| 2 | `Ground clearance` | 0.15mm | `HighVoltageTank to LV` | 2.0mm | latent |
| 2 | `Ground clearance` | 0.15mm | `HighVoltageIsolated to LV` | 2.0mm | latent |
| 3 | `GateDriveSELV near HV` | 0.5mm | `HV to LV` | 2.0mm | **yes** |
| 3 | `GateDriveSELV near HV` | 0.5mm | `HighVoltageTank to LV` | 2.0mm | **yes** |
| 4 | `HighVoltageIsolated same side` | 2.0mm | `AC Mains to LV` | 6.0mm | **yes** |

**Instance 1 — `Default routing`.** The one the task brief names. Its condition `A.Type == 'Track' || B.Type == 'Track'` matches essentially every routed pair on the board, and it is emitted last. On the committed board this is not theoretical: 332 of the 402 reported `clearance` violations are attributed to it, and it is also overriding `pcb/temper.kicad_pro`'s own netclass clearances, not only the DRU rules (sec 5.2).

**Instance 2 — `Ground clearance` (latent).** `A.NetClass == 'Ground' || B.NetClass == 'Ground'` at 0.15mm, emitted after every HV rule. `pcb/temper.kicad_pro` declares eleven net classes and **`Ground` is not one of them** — the ground class on this board is named `GND`. So the rule matches nothing today and its isolated measurement is 0 violations. It is reported here because it is a real, armed instance of the same defect: the moment anyone reconciles that name (and `docs/evidence/2026-08-12-gnd-class-decision.md` and `2026-08-12-nonexistent-gnd-class-mapping.md` are both live work in this area), a 0.15mm rule would take over every HV-to-ground crossing on the board — and `gnd` is the largest net on it. **This document does not rename the class**; that would conflate two causes. It fixes the ordering so that the rename, whenever it happens, is safe.

**Instance 3 — `GateDriveSELV near HV`, and it is a genuine safety downgrade, not a cosmetic one.** `packages/temper-placer/src/temper_placer/core/design_rules.py` gives `GateDriveSELV` `safety_category="LV"`, and `TEMPER_NET_ASSIGNMENTS`'s own comment records why: `GATE_*` are "the secondary-side (HV) gate outputs; `PWM_*` are the primary-side (SELV) MCU PWM inputs", split across U7's reinforced isolation barrier in 2026-07-28's R4. `HV to LV`'s condition deliberately excludes `GateDriveHV` and deliberately does **not** exclude `GateDriveSELV` — i.e. the author intended `HighVoltage` ↔ `GateDriveSELV` to be the 2.0mm/8.0mm reinforced barrier. `GateDriveSELV near HV` (0.5mm) is a leftover of the pre-split single `GateDrive` class — its own generator comment says "Both halves keep the original 0.5mm figure -- this unit changes the class model, not the clearance value" — and, being emitted later, it wins. Under the fix, `HV to LV`'s 2.0mm wins and this rule becomes inert on every pair. **Measured consequence on this board: zero.** In isolation the rule reports 0 clearance violations and `HighVoltage ↔ GateDriveSELV` reports 0 — the four `PWM_*` nets are already ≥2.0mm from HV copper. The correction is free today and closes a hole that a future placement change would have walked straight into. Recommended follow-up (not done here): delete the rule or re-scope it to `GateDriveHV`, since a rule that can never win reads as coverage.

**Instance 4 — `HighVoltageIsolated same side` over `AC Mains to LV`.** `HighVoltageIsolated same side` explicitly enumerates `ACMains` in its B set at 2.0mm; `AC Mains to LV` requires 6.0mm and does not exclude `HighVoltageIsolated`. Two of the file's own conditions disagree, and today the later one wins. The fix resolves it toward 6.0mm, and there is an independent reason to think that is the coherent reading: `AC Mains to LV` **also** carries `(constraint creepage (min 8.0mm))`, `HighVoltageIsolated same side` carries no creepage constraint at all, so 8.0mm reinforced creepage is *already* being enforced on ACMains ↔ HighVoltageIsolated pairs today. A pair required to hold 8.0mm of creepage but only 2.0mm of clearance is not a coherent barrier. Measured consequence: 3 violations (sec 6). **This one is a judgement the board owner should confirm** — it is the only instance where the fix changes an explicitly-enumerated figure rather than restoring one.

**No shadowing exists for `creepage`, `track_width`, `hole_clearance` or `hole_to_hole`.** The creepage rules' conditions are mutually disjoint by construction (`HighVoltageTank functional creepage` at 6.3mm vs the four 8.0mm barrier rules), and this is confirmed by measurement: `creepage` is 198-200 both before and after the fix, identically distributed (sec 5.1).

---

## 3. The fix, and why this one

Two approaches were on the table.

**Rejected — narrow `Default routing`'s condition.** To stop it matching pairs a safety rule governs, its condition would have to enumerate the complement of ten other rules' conditions across an 11-class matrix, inside a quoted string. It has to be hand-edited whenever a class or a rule is added; it silently degrades (a forgotten exclusion is invisible); and it fixes exactly **one** of the four instances, because the other three shadowing rules are not catch-alls and have nothing to narrow.

**Chosen — emit weakest-first, and machine-check it.** Rules that can apply to the same pair of items are emitted in increasing order of their `min` value, which makes KiCad's last-matching-wins *numerically identical* to strictest-matching-wins. This is not a hand-maintained ordering: overlap is computed over the finite world model of sec 2, an edge `weak → strong` is added for every overlapping pair that disagrees on a value, and the emission order is the topological sort of that graph (Kahn, tie-broken by authored order so the output is deterministic). A rule added anywhere in `generate_dru()` is therefore placed **by value**, with nothing for the author to remember.

The task brief asked for a guard that fails when a rule is emitted after the catch-all. The shipped guard is strictly stronger and subsumes it: `find_shadowing()` re-derives, for every constraint type and every modelled item pair, whether the rule KiCad selects is the strictest matching one, and `generate_dru()` raises `RuleShadowingError` rather than returning a file where it is not. The specific regression the brief describes is covered by `test_guard_fires_when_a_catch_all_is_appended_after_the_rules`, which appends a 0.2mm track catch-all to the finished file and asserts the guard names `AC Mains to LV` and `HV to LV` as shadowed.

Three deliberate properties:

- **Fails closed on the unknown.** A condition using syntax the analyser cannot model (e.g. `A.insideCourtyard('Q1')`) raises `UnsupportedConditionError` rather than being skipped. A guard that silently ignores the rules it does not understand is the vacuous-gate pattern this repo already treats as a defect.
- **Fails loudly on the impossible.** If two overlapping rules require opposite orderings under two different constraint types, no emission order can satisfy strictest-wins; `RulePrecedenceCycleError` says so instead of picking one. No such cycle exists today.
- **The authored narrative in the source is untouched.** The `lines.append(...)` blocks in `generate_dru()` stay in the order a human wrote them, with their cross-referencing comments (`"RULE 5a below supplies the correct functional figure"`) intact; only the emitted `.kicad_dru` is reordered, and each rule's comment banner travels with it.

**The change is a pure permutation.** Sorting the lines of the pre-fix and post-fix `.kicad_dru` gives byte-identical multisets, and every one of the 31 rule blocks is byte-identical between them — only their positions differ. Pinned by `test_reordering_is_a_pure_permutation_of_the_emitted_lines`.

---

## 4. `clearance` 499 and `track_width`/`shorting_items` 199 are reporting caps, not counts

This was not something this task went looking for. It surfaced because 161 violations that the pre-fix report contained — including nine `HV internal same footprint` pad pairs whose governing rule and 2.0mm figure are **identical** before and after the fix — vanished from the post-fix report.

**Probe.** A `.kicad_dru` containing one unconditioned rule, `(constraint clearance (min 20mm))`, applied to a 168-footprint board with 2,290 track segments. Every copper pair on the board violates it; the true count is in the tens of thousands.

| DRU | reported `clearance` |
|---|---:|
| generated file (pre-fix) | 402 |
| generated file (post-fix) | **499** |
| generated file + 5.0mm track catch-all appended last | **499** |
| generated file + 20.0mm track catch-all appended last | **499** |
| **one rule, no condition, 20mm, nothing else** | **499** |
| two rules only (`Same footprint pads`, `HV internal same footprint`) | **499** |
| `HighVoltage`↔`Default` alone (one rule) | **499** |
| two HV nets vs `Default` (isolated counts 425 + 423 = 848) | **499** |

**499 is a ceiling on what kicad-cli will print.** Confirmed against KiCad's own source (`pcbnew/drc/drc_engine.cpp`, 10.0 branch), quoted verbatim:

```c
// wxListBox's performance degrades horrifically with very large datasets.  It's not clear
// they're useful to the user anyway.
#define ERROR_LIMIT 199
#define EXTENDED_ERROR_LIMIT 499
```

```c
for( int ii = DRCE_FIRST; ii <= DRCE_LAST; ++ii )
{
    if( m_designSettings->Ignore( ii ) )
        m_errorLimits[ ii ] = 0;
    else if( ii == DRCE_CLEARANCE || ii == DRCE_UNCONNECTED_ITEMS )
        m_errorLimits[ ii ] = EXTENDED_ERROR_LIMIT;
    else
        m_errorLimits[ ii ] = ERROR_LIMIT;
}
```

A GUI list-widget performance workaround, inherited by the headless CLI. Which categories on this board are at their limit **right now, on `origin/main`, before any change in this branch**:

| category | measured (n=120) | limit | status |
|---|---:|---:|---|
| `clearance` | 402 pre-fix / **499** post-fix | 499 | pre-fix real; **post-fix SATURATED** |
| `track_width` | **199** | 199 | **SATURATED** — a 5mm-minimum rule on all 2,290 segments also reports exactly 199 |
| `shorting_items` | **199** | 199 | **SATURATED** |
| `silk_overlap` (warning) | **199** | 199 | **SATURATED** |
| `creepage` | 198-200 | — | **not capped** — a 20mm creepage rule reports 3,311, so the provider does not honour the limit |
| `unconnected_items` | 428 | 499 | real, below cap |
| `solder_mask_bridge` / `silk_over_copper` / `hole_clearance` | 154 / 172 / 105 | 199 | real, below cap |

Three consequences the repo should absorb:

- **`track_width` = 199 and `shorting_items` = 199 in `power_pcb_dataset/drc_ceiling.json` are not counts.** They are lower bounds. Any change to the board that halves the true number of shorts will still read 199, and any ratchet on them is measuring nothing.
- **The `creepage` "chronic scatter" is not this.** `creepage` is genuinely uncapped and its 198-200 spread is real run-to-run variance, exactly as `drc_ceiling.json`'s own `_march` log describes. That distinction matters: the 199-valued categories should be treated as saturated, `creepage` should not.
- **`clearance` = 499 post-fix is a floor on the truth, not the truth.** Sec 5.3 measures the truth by partition.

---

## 5. Re-measurement of the committed board

### 5.1 Full per-category table, n = 120 samples per configuration

240 kicad-cli invocations against read-only scratch copies of the byte-identical committed board (sha256 above), `--all-track-errors`, single-thread-pinned `KICAD_CONFIG_HOME`, via `temper_placer.validation._drc_api`'s own invocation. "pre-fix" = `origin/main`'s generator; "post-fix" = this branch's. The board, the project file and the 31 rule bodies are identical in both columns; only rule order differs.

| severity | category | pre-fix (n=120) | post-fix (n=120) |
|---|---|---:|---:|
| error | **clearance** | **402** | **499** *(at cap)* |
| error | creepage | 198-200 (3 distinct) | 198-200 (3 distinct) |
| error | shorting_items | 199 *(at cap)* | 199 *(at cap)* |
| error | track_width | 199 *(at cap)* | 199 *(at cap)* |
| error | solder_mask_bridge | 154 | 154 |
| error | hole_clearance | 105 | 105 |
| error | courtyards_overlap | 11 | 11 |
| error | copper_edge_clearance | 10 | 10 |
| error | annular_width | 4 | 4 |
| error | drill_out_of_range | 4 | 4 |
| error | via_diameter | 4 | 4 |
| error | hole_to_hole | 3 | 3 |
| error | tracks_crossing | 1 | 1 |
| warning | silk_overlap | 199 *(at cap)* | 199 *(at cap)* |
| warning | silk_over_copper | 172 | 172 |
| warning | track_dangling | 45 | 45 |
| warning | via_dangling | 32 | 32 |
| warning | lib_footprint_mismatch | 23 | 23 |
| warning | lib_footprint_issues | 11 | 11 |
| warning | missing_courtyard | 5 | 5 |
| warning | pth_inside_courtyard | 1 | 1 |
| warning | silk_edge_clearance | 1 | 1 |
| — | **total errors** | 1294-1296 | 1391-1393 |
| — | total warnings | 489 | 489 |
| — | unconnected_items (pad connectivity) | 428 | 428 |

`clearance` is deterministic at 402 across all 120 pre-fix samples and at 499 across all 120 post-fix samples. `creepage` spread (198/199/200, 3 distinct) is identical in both columns and identically distributed by rule — as sec 2 predicts, since no creepage rule was ever shadowed. **Every non-clearance category is unchanged.** The single measured effect of this branch is on `clearance`.

The one figure that is not "pad connectivity" is labelled: `unconnected_items` above is **pad connectivity** as kicad-cli reports it, unchanged at 428.

### 5.2 Which rule each `clearance` violation is charged to

Attribution is taken from kicad-cli's own `description` string, which names the operative rule and both the required and actual figures.

| governing rule | pre-fix | post-fix |
|---|---:|---:|
| `Default routing` (0.2mm catch-all) | **332** | 175 |
| `HV to LV` (2.0mm) | 21 | **251** |
| `HighVoltageIsolated to LV` (2.0mm) | 4 | **47** |
| `AC Mains to LV` (6.0mm) | 5 | **21** |
| `HighVoltageTank to LV` (2.0mm) | 0 | **3** |
| `AC Mains to HV` (3.0mm) | 0 | **1** |
| `HighVoltageIsolated same side` (2.0mm) | 5 | 0 |
| `HV internal same footprint` (2.0mm) | 9 | 0 |
| implicit netclass `Power` (0.5mm) | 18 | 0 |
| implicit netclass `GND` (0.3mm) | 6 | 0 |
| implicit netclass `HighVoltage` (2.0mm) | 1 | 0 |
| implicit netclass `Default` (0.2mm) | 1 | 1 |
| **safety-rule-governed subtotal** | **44** | **323** |

Pre-fix attribution is byte-identical across all 120 runs. Post-fix the total is a fixed 499 but the last few slots shuffle between `HV to LV` and `Default routing` across runs (4 distinct vectors in 120) — which is itself a signature of truncation: the report is cut off mid-stream.

The zeros in the post-fix column are the cap, not an improvement: `HighVoltageIsolated same side`, `HV internal same footprint` and the implicit-netclass violations are all **pad-to-pad** pairs, and KiCad's copper-clearance provider exhausts its 499 budget during the track phase before it reaches them. Measured in isolation (sec 5.3) they are all still there.

**The catch-all was overriding `pcb/temper.kicad_pro`'s netclass clearances too, not only the DRU rules.** With a `.kicad_dru` containing just two rules and no catch-all, kicad-cli charges the board against its project netclasses — `HighVoltageIsolated` 6.0mm, `ACMains` 6.0mm, `HighVoltage` 2.0mm, `GND` 0.3mm, `Power` 0.5mm — and reports 499 (capped), of which 235 cite `netclass 'HighVoltageIsolated' 6.0mm` and 142 cite `netclass 'HighVoltage' 2.0mm`. Pre-fix, only 26 violations in total were charged to any netclass. Every one of the five safety-relevant netclass bars in the project file was being replaced by 0.2mm as well.

### 5.3 The true per-rule counts, measured under the cap

Because 499 truncates, each rule was measured **alone**: a `.kicad_dru` containing a 0.001mm unconditioned floor (which suppresses the implicit netclass clearances) followed by that single rule. The floor's own contribution (1 clearance, 47 creepage) is subtracted. `HV to LV` still saturates alone, so it was partitioned further — by LV-side net class, and for the `Default` class by individual HV-side net name (`A.NetName == '<net>'`), 23 further runs, every partition below the cap and therefore exact.

| rule | true `clearance` | true `creepage` |
|---|---:|---:|
| **`HV to LV`** (2.0mm / 8.0mm) | **1,152** | 145 |
| `Default routing` (0.2mm) | 331 | — |
| `HighVoltageIsolated to LV` (2.0mm / 8.0mm) | 112 | 22 |
| `AC Mains to LV` (6.0mm / 8.0mm) | 23 | 8 |
| `HV internal same footprint` (2.0mm) | 9 | — |
| `HighVoltageIsolated same side` (2.0mm) | 5 | — |
| `HighVoltageTank to LV` (2.0mm / 8.0mm) | 5 | 7 |
| `AC Mains to HV` (3.0mm) | 1 | — |
| `HighVoltageTank functional creepage` (6.3mm) | — | 2 |
| `Same footprint pads`, `Fine pitch IC pads`, `Power internal same footprint`, `Ground clearance`, `USB differential`, `GateDriveHV near HV`, `GateDriveHV to ACMains`, `GateDriveHV to HighVoltageIsolated`, `GateDriveSELV near HV` | 0 each | 0 each |
| **safety-rule-governed total** | **1,307** (1,291 distinct pairs) | 184 |

The `Default routing` row does **not** add to the safety total: measured alone it also fires on pairs that, in the ordered file, a stricter safety rule governs instead. So the true post-fix `clearance` total is bounded — **at least 1,307 and at most 1,638** — with the safety-governed part exact at 1,307. kicad-cli prints 499.

`HV to LV`'s 1,152 decomposes as: `HighVoltage`↔`Default` 994 (of which `discharge.k_dis1-nc` 424 and `zcd` 422), `HighVoltage`↔`Power` 96, `HighVoltage`↔`FinePitch` 35, `HighVoltage`↔`GND` 27, `HighVoltage`↔`GateDriveSELV` **0**, `HighVoltage`↔`Differential` **0**.

---

## 6. The safety finding: what is actually too close to what

**1,291 distinct HV/mains-to-SELV clearance violations exist on the committed board. Forty-four are visible today.** Full per-violation detail — rule, required, actual, shortfall, both nets, both net classes, both item kinds, owning components, board coordinates — is in `docs/evidence/2026-08-12-dru-rule-precedence-violations.csv` (1,291 rows). Summary:

### By net class pair

| count | net class pair | required |
|---:|---|---:|
| 984 | `HighVoltage` ↔ `Default` | 2.0mm |
| 96 | `HighVoltage` ↔ `Power` | 2.0mm |
| 71 | `HighVoltageIsolated` ↔ `Default` | 2.0mm |
| 35 | `HighVoltage` ↔ `FinePitch` | 2.0mm |
| 31 | `HighVoltageIsolated` ↔ `Power` | 2.0mm |
| 27 | `HighVoltage` ↔ `GND` | 2.0mm |
| 16 | `ACMains` ↔ `Default` | 6.0mm |
| 6 | `HighVoltage` ↔ `HighVoltage` (same footprint) | 2.0mm |
| 6 | `HighVoltageIsolated` ↔ `FinePitch` | 2.0mm |
| 4 | `HighVoltage` ↔ `HighVoltageIsolated` | 2.0mm |
| 4 | `HighVoltageIsolated` ↔ `GND` | 2.0mm |
| 3 | `ACMains` ↔ `HighVoltageIsolated` | 6.0mm |
| 2 | `HighVoltageTank` ↔ `Power` | 2.0mm |
| 2 | `HighVoltage`/`FinePitch`/`ACMains` ↔ `HighVoltageTank` | 2.0-6.0mm |
| 1 each | `ACMains` ↔ `HighVoltage`, `ACMains` ↔ `FinePitch`, `HighVoltageIsolated` ↔ `HighVoltageTank` | 3.0-6.0mm |

### By hazardous-side net

| count | class | net |
|---:|---|---|
| 458 | `HighVoltage` | `discharge.k_dis1-nc` |
| 434 | `HighVoltage` | `zcd` |
| 123 | `HighVoltage` | `power_in.ntc-no` |
| 117 | `HighVoltageIsolated` | `hb.gate_hs.driver-p1-1` |
| 42 | `HighVoltage` | `a` |
| 41 | `HighVoltage` | `PWR_RTN` |
| 20 | `ACMains` | `ac_n` |
| 17 | `HighVoltage` | `+170V_BUS` |
| 15 | `HighVoltage` | `DC_BUS_RTN` |
| 9 | `HighVoltage` | `hb.power_loop.q_high-g` |
| 6 | `HighVoltageTank` | `tank.c_tank1-p2` |
| 6 each | `HighVoltage` | `+15V_LS`, `SW_NODE` |
| 3 each | `HighVoltageIsolated` / `HighVoltage` | `hb.gate_hs.driver-p2`, `w1_1` |
| 1-2 each | `HighVoltage` / `ACMains` | `tank-out`, `discharge.k_dis2-nc`, `w1_2`, `ac_l` |

Two nets — the discharge relay's normally-closed contact and the zero-cross-detect line — account for 69% of the finding. Both are mains/bus-referenced and both run long across the board.

### By component

`D2` (23), `C1` (17), `C14` (15), `R77` (9), `U18` (9), `C4` (8), `C3` (7), `U7` (7), `RT1` (7), `R64` (7), `R30` (6), `R8` (6), `R61` (6), `RV1` (5), `U8` (5), `C26` (5), `C7` (4), `U25` (4), `J1` (4), `T1` (4). 1,053 of the 1,291 are track-to-track and name no component at all — these are bare copper crossings, which is why a component histogram undercounts the finding.

### Gap severity

| shortfall (required − actual) | count |
|---|---:|
| 0.0-0.5mm | 268 |
| 0.5-1.0mm | 309 |
| 1.0-1.5mm | 326 |
| 1.5-2.0mm | 381 |
| 2.0mm+ | 7 |

Median shortfall 1.11mm. **All seven shortfalls of 2.0mm or more are `AC Mains to LV`** — the 6.0mm mains barrier — and they are the single most serious entries in the finding:

| shortfall | actual | net (class) ↔ net (class) | at |
|---:|---:|---|---|
| **4.20mm** | **1.80mm** | `ac_l` (ACMains) ↔ `power_in.r_zcd_top1-p2` (Default) | `R6`, (143.81, 59.73) |
| 3.38mm | 2.62mm | `ac_n` (ACMains) ↔ `hb.gate_hs.driver-p1-1` (HighVoltageIsolated) | `C1`, (50.05, 195.25) |
| 3.13mm | 2.87mm | `ac_n` ↔ `hb.gate_hs.driver-p1-1` | `C1`, (51.49, 199.22) |
| 2.10mm | 3.90mm | `ac_n` ↔ `hb.gate_hs.driver-p1-1` | `C1`, (54.95, 195.25) |
| 2.04mm | 3.96mm | `ac_n` ↔ `rtd_pan.high_window-out` (Default) | `C1`, (51.49, 199.22) |
| 2.04mm ×2 | 3.96mm | `ac_n` ↔ `rtd_pan.rail_monitor-outa` (Default) | `C1`, (51.49/47.65, …) |

`ac_l` at 1.80mm from a SELV divider node is the worst mains-to-SELV separation on the board and is under a third of its required figure.

At the other extreme, the tightest absolute gaps are `HV to LV` pairs at **0.6µm** (`power_in.bypass_relay-coil2` ↔ `a`), **1µm** (`discharge.k_dis1-coil2` ↔ `power_in.ntc-no`), 10µm (`discharge.k_dis1-nc` ↔ `ina`) and 15µm (`discharge.k_dis1-nc` ↔ `safety-line-2`) — sub-fabrication-tolerance separations between bus-referenced copper and SELV copper, all bare track-to-track.

### Pair kinds

1,053 track↔track, 104 pad↔track, 75 PTH-pad↔track, 30 track↔via, 16 pad↔pad, 7 pad↔via, 3 PTH-pad↔via, 2 PTH-pad↔PTH-pad, 1 PTH-pad↔pad. **81.6% are track-to-track**: this is overwhelmingly a routing finding, not a footprint-packing one.

**These are real.** They are not a regression introduced by this branch: the board is byte-identical, the rule bodies are byte-identical, and every required figure is the one the generator already cites to IEC 60335-1. The only thing that changed is that KiCad now evaluates them.

---

## 7. Does `clearance` respond to routing or placement once precedence is correct?

The hypothesis under test: *with safety rules overridden, the effective DRC model is a uniform 0.2mm everywhere, so the count depends only on netlist density and not on netclass structure — which would explain an invariant immune to both routing and placement changes.*

**The invariant is confirmed. The proposed mechanism is not the operative one.**

**The hypothesis's premise is only partly true.** Under the pre-fix DRU the model was not uniform 0.2mm: 332 of 402 violations (82.6%) were charged to the 0.2mm catch-all, but 44 were charged to netclass-specific safety rules and 26 to implicit netclass clearances. Post-fix, 323 of 499 reported (and 1,307 of ~1,638 true) violations are decided by netclass structure at 2.0-6.0mm. So the DRC model **is** now netclass-structured, decisively.

**But the observable did not become more responsive — it became less.** The true post-fix count is between 1,307 and 1,638 (sec 5.3), and kicad-cli prints 499. `clearance` is now **pinned at the cap**, so no routing change, no placement change, and no netclass change can move the reported number until the true count falls below 499 — a reduction of at least 62%. That is a complete, mechanical explanation for an invariant immune to every lever, and it is stronger than the density hypothesis: it predicts immunity to *any* intervention, which is exactly what four investigations observed.

It also retro-explains the specific numbers those investigations reported. `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md` records main at 386/392 (below the cap, a real measurement) and the candidate board at **499/505** — the cap, plus the 0-6 overshoot that `--all-track-errors` produces when the limit is checked between items and a whole item's batch is emitted anyway. The candidate board's "499-505, nondeterministic" was never noise; it was saturation.

**Routing lever, measured directly.** A scratch copy of the committed board with all 2,290 track segments and 48 vias stripped (footprints, pads, zones and the project file untouched) — i.e. placement with routing taken to zero:

| board | `clearance`, pre-fix DRU | `clearance`, post-fix DRU |
|---|---:|---:|
| committed (routed) | 402 | 499 *(true 1,307-1,638)* |
| tracks and vias stripped | **48** | **48** |

Two findings. First, **the precedence defect had exactly zero effect on the unrouted board** — 48 identical, rule-for-rule identical (16 netclass `Power`, 10 `HV to LV`, 9 `HV internal same footprint`, 6 netclass `GND`, 5 `HighVoltageIsolated same side`, 1 `AC Mains to LV`, 1 netclass `HighVoltage`) — because `Default routing`'s condition requires a track and there are none. The entire defect lives in routed copper. Second, **routing accounts for 88% of the pre-fix count and 96-97% of the true post-fix count** (48 → 402 → 1,307-1,638). Placement's own contribution to `clearance` is 48 violations, of which 25 are safety-rule-governed. This is consistent with, and sharpens, the prior finding that the clearance problem is a routing-congestion problem rather than a footprint-packing one — and it now has a number for the placement floor.

**What reopens and what does not.** The four closed investigations were not wrong about their levers; they were reading a saturated counter. Re-opening any of them requires a measurement that does not saturate — either the partitioned per-rule protocol used in sec 5.3 (exact, ~25 kicad-cli runs), or a violation count computed outside kicad-cli. Until such a measurement exists, **`clearance` from `kicad-cli` is not a usable optimisation objective for this board**, with or without this fix, and neither is `track_width` or `shorting_items`. That is the most consequential thing in this document after the safety finding itself.

---

## 8. Is this safe to land?

**The required DRC gate is already red on `origin/main`, before this branch.** Measured live, same session, by checking out `origin/main`'s generator and running the gate:

```
$ python scripts/ci_check_drc.py --backend kicad-cli      # origin/main generator
FAIL: temper: DRC FAIL
  aggregate errors 1295 exceeds ceiling 1266 (+29)
    [   ] clearance 402 > 386 (+16)
    [   ] creepage 199 > 186 (+13)

$ python scripts/ci_check_drc.py --backend kicad-cli      # this branch
FAIL: temper: DRC FAIL
  aggregate errors 1391 exceeds ceiling 1266 (+125)
    [   ] clearance 499 > 386 (+113)
    [   ] creepage 198 > 186 (+12)
```

So this branch does not turn a green gate red; it widens an already-failing one, by +97 on `clearance` and by nothing on `creepage`. The noise-headroom guard passes in both cases.

**`power_pcb_dataset/drc_ceiling.json` is deliberately not touched by this branch.** A separate effort is re-deriving it, and a rule-precedence fix landing inside a ceiling change would conflate two causes. Proposed staging:

1. Land this branch (generator fix + guard + tests + this document). The gate stays red, as it already is.
2. The ceiling re-derivation lands next, measuring against the corrected generator.

**A warning for whoever re-derives that ceiling.** Do not record `clearance: 499` (or 505) as a measured count and ratchet on it — 499 is `EXTENDED_ERROR_LIMIT`, and a category sitting on its limit cannot ratchet, cannot regress, and cannot improve. The same applies to the `track_width: 199` and `shorting_items: 199` entries already in the file. A ceiling on a saturated category is a gate that can never fire. Either record them with an explicit `saturated: true` marker and stop treating them as ratchets, or replace the measurement with the partitioned protocol of sec 5.3. This document deliberately proposes and does not implement that change.

**Two determinations for the board owner, neither made here.**

- `HighVoltageIsolated` ↔ `ACMains`: this branch resolves it to `AC Mains to LV`'s 6.0mm (3 violations) rather than `HighVoltageIsolated same side`'s 2.0mm. The 8.0mm reinforced creepage already enforced on those pairs argues for 6.0mm, but the file's two conditions genuinely disagree and someone should say which is intended.
- `GateDriveSELV near HV` is now inert. Its 0.5mm figure was a pre-class-split leftover that had been downgrading a reinforced barrier; deleting it or re-scoping it to `GateDriveHV` is the clean follow-up.

---

## 9. Reproduction

```bash
# The fix and its guard, no DRC required
python -c "import sys; sys.path.insert(0,'scripts'); \
           sys.path.insert(0,'packages/temper-placer/src'); \
           import generate_kicad_dru as g; print(g.find_shadowing(g.generate_dru()))"   # -> []
python -m pytest scripts/tests/test_generate_kicad_dru.py -k Precedence

# Precedence falsifier and the 499 cap, against a scratch copy of the real board
#   1. copy pcb/temper.kicad_pcb + .kicad_pro + fp-lib-table + libs/ to a scratch dir
#   2. write a .kicad_dru there containing only:
#        (version 1)
#        (rule "ZZ everything 20mm"
#           (constraint clearance (min 20mm))
#        )
#   3. kicad-cli pcb drc --all-track-errors --format json -o out.json <scratch>/temper.kicad_pcb
#      -> "clearance": 499, on a board where every copper pair violates
```

Sources for the documentation quotes: KiCad user documentation `kicad-doc`, `src/pcbnew/pcbnew_advanced.adoc` ("Custom Design Rules"); KiCad source `pcbnew/drc/drc_engine.cpp`, 10.0 branch (`ERROR_LIMIT` / `EXTENDED_ERROR_LIMIT`, `DRC_ENGINE::RunTests`).
