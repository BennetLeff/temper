<!-- provenance: commit=688c15bb dirty=false (base); this file added in worktree agent-a21496c0216991342, branch fix/drc-rule1-netclass-redo -->

# RULE 1/1a redo: netclass-based domain discrimination, not literal net names

Base commit: `688c15bb` (`fix(netclass): the main HV rail belonged to no
netclass after a rename`, branch `docs/methodology-loop-discipline`). Work
done in worktree `agent-a21496c0216991342`, branch
`fix/drc-rule1-netclass-redo` created from that commit.

Reads first, per task instructions:
`docs/evidence/2026-07-28-drc-rule1-netclass-discrimination.md` (the prior
attempt this redoes), `docs/evidence/2026-07-28-drc-courtyard-condition-fix.md`
(the sibling fix for Rules 5/7), `scripts/generate_kicad_dru.py`,
`scripts/tests/test_generate_kicad_dru.py`, `elec/domain_manifest.yaml`.

## FALSIFIER, stated up front

> "A netclass-based dynamic exclusion is expressible and makes RULE 1/1a
> discriminate correctly on the real board. If netclass resolution is too
> broken to rely on even after fixing `.kicad_pro`, then a name-based
> fallback is justified -- but only with that established, not assumed."

**Both halves fire, in a specific, measured way:**

1. **A netclass-based dynamic exclusion IS expressible and DOES bind.**
   `A.NetClass == B.NetClass` is confirmed to match real pad pairs on the
   real board (§2), refuting the prior attempt's premise that it "matches
   zero pad pairs." Combined with the corrected same-footprint test
   (`A.Reference == B.Reference`), it discriminates correctly for the vast
   majority of measured same-footprint pairs once `pcb/temper.kicad_pro`'s
   netclass resolution is fixed (§4).
2. **Netclass resolution was NOT too broken to rely on -- it needed the
   same kind of stale-mapping fix the Python side already got in
   `688c15bb`,** not a fallback to hardcoded literal net names. Fixed
   additively in `pcb/temper.kicad_pro` (§3), verified end-to-end (§4).
3. **A residual gap was found and is honestly reported, not hidden:**
   NetClass equality is a *necessary but not sufficient* proxy for "same
   safety domain" -- one real isolator (U7, the UCC21550 gate driver) had
   two of its pins spuriously treated as "same domain" until a further,
   narrowly-scoped classification fix closed that specific case (§5). A
   residual class of similarly-situated but not individually re-verified
   nets remains, flagged as a structural limitation (§5, UNVERIFIED). **A
   name-based fallback was never invoked** -- the gap was closed by
   completing the netclass classification, which is the dynamically-correct
   fix, not a workaround.

**A second, independent defect was found and fixed alongside the first:**
RULE 1a's `A.Attribute == 'SMD'` clause is *also* an undefined KiCad
property (§2) -- fixed to `A.Pad_Type == 'SMD'`, the correct registered
name.

## 1. Reproducing the prior claim -- and refuting it

The prior attempt (`docs/evidence/2026-07-28-drc-rule1-netclass-discrimination.md`)
concluded RULE 1/1a could not be fixed with a netclass-based condition
because "two-sided dynamic property comparisons match zero pad pairs in
kicad-cli 10.0.4," and built the fix from hardcoded literal net names
instead -- the same failure pattern (an unnoticed rename orphans a
hardcoded key) that produced the `+340V_BUS` defect this branch is named
after.

**Reproduced directly against `pcb/temper.kicad_pcb` (a scratch copy, never
the repo file), from this worktree, using the task's own methodology**: each
expression run as a lone rule with a `999.0mm` clearance constraint (kicad-cli
10.0.4 silently clamps this to 500mm internally -- confirmed by inspecting the
emitted violation text, "clearance 500.0000 mm"; still far larger than
anything on this board, so the clamp does not affect the binds/doesn't-bind
conclusion). Measured against a `.kicad_pro` copy with `netclass_assignments`
and `netclass_patterns` fully emptied (all nets `Default`), which eliminates
a report-truncation artifact discovered during this work (§2a) and isolates
each condition's own true match count:

| condition | violations (this session) | task's reported figure |
|---|---:|---:|
| `A.Reference == B.Reference` | **215 -- binds** | 214 |
| `A.NetClass == B.NetClass` | **499 -- binds** (see §2a: likely truncated) | 499 |
| `A.Footprint == B.Footprint` | **0 -- does NOT bind** | 0 |
| `A.insideCourtyard(B.Reference)` | **0 -- does NOT bind** | 0 |
| `A.Attribute == 'SMD'` (new finding) | **0 -- does NOT bind** | not measured by prior attempt |
| `A.Pad_Type == 'SMD'` (new finding) | **483 -- binds** | not measured by prior attempt |

The first four rows reproduce the task's own table closely (214 vs. 215 is
within run-to-run/board-snapshot noise; the other three match exactly). The
prior attempt's premise -- that `A.NetClass == B.NetClass` "matches zero pad
pairs" -- **does not hold**; it was never independently re-verified against
the real board by that attempt, only asserted from the `insideCourtyard`
investigation's unrelated finding.

**`A.Attribute` is a second, previously-unreported undefined-property
defect**, found while establishing why RULE 1a still showed zero matches
after fixing its `Footprint`/`Reference` clause alone (§2b). Confirmed
against `pcbnew/pad.cpp` at kicad-cli 10.0.4/10.0.5
(`gh api repos/KiCad/kicad-source-mirror/contents/pcbnew/pad.cpp?ref=10.0.4`):

```cpp
propMgr.AddProperty( new PROPERTY_ENUM<PAD, PAD_ATTRIB>( _HKI( "Pad Type" ),
    &PAD::SetAttribute, &PAD::GetAttribute ), groupPad )
    .Map( PAD_ATTRIB::PTH,  _HKI( "Through-hole" ) )
    .Map( PAD_ATTRIB::SMD,  _HKI( "SMD" ) )
    ...
```

The pad's type/attribute field is registered under the display name **"Pad
Type"**, not "Attribute". `pcbexpr_evaluator.cpp`'s `CreateVarRef` looks up
properties by exact display name (replacing `_` with a space first, so
`Pad_Type` correctly resolves to "Pad Type" but `Attribute` resolves to
nothing) -- the identical mechanism that made `A.Footprint` dead. This is a
third independent instance of the same undefined-property failure class
documented across this task and the sibling's.

### 2a. A measurement artifact worth documenting: kicad-cli's clearance-report truncation

While reproducing the task's own numbers, the SAME lone condition
(`A.Reference == B.Reference`) gave visibly different counts depending on
which `.kicad_pro` variant was paired with it, even though this condition
does not reference `NetClass` at all:

| `.kicad_pro` variant | `A.Reference == B.Reference` matches | total `"clearance"`-type violations in report |
|---|---:|---:|
| fully empty (`netclass_assignments={}`) | 210-215 | ~500 (never more) |
| `688c15bb` as-committed ("stale") | 187 | ~500-501 |
| this fix ("fixed") | 16 | ~499 (dominated by 168 newly-surfaced `HighVoltageIsolated` baseline violations, see §5) |

kicad-cli 10.0.4's JSON DRC report appears to cap the **total** number of
`"clearance"`-type violations at roughly 500, shared across *every* source
(custom rules and intrinsic per-netclass baselines alike) -- not a per-rule
cap. The more "noise" other netclass baselines contribute (because
`.kicad_pro` now classifies more nets correctly, §5), the fewer of the
shared ~500 slots are left for any one rule's own violations, so raw counts
above a few hundred are **lower bounds, not exact figures**, and are not
comparable across `.kicad_pro` variants without controlling for this.
**This does not affect any 0-vs-nonzero (binds/doesn't-bind) conclusion in
this document** -- truncation can only ever reduce a true count, never
fabricate a nonzero one from zero. Every table in this document that
reports a large, comparable count across variants (e.g. "AC Mains to LV")
should be read as "at least N," and every reported 0 should be read as a
firm negative.

### 2b. RULE 1a's second defect, isolated

With `A.Attribute == 'SMD'` replaced by nothing (condition reduced to just
`A.Type == 'Pad' && ... && A.Reference == B.Reference`), the fine-pitch
rule's underlying same-footprint/same-netclass test binds exactly like
RULE 1 (§4). Re-adding `A.Attribute == 'SMD'` alone (isolated, both sides)
gave 0 matches at 999mm on the real board; swapping to `A.Pad_Type ==
'SMD'` gave 483. This isolates the defect to the property name, not the
combination with other clauses.

## 2. Establishing the correct expressions -- summary

- `A.Reference == B.Reference` -- RULE 1/1a's same-footprint-instance test.
  Same construction already used for RULE 5/7 (sibling fix); pad->parent-
  footprint property resolution confirmed in `pcbexpr_evaluator.cpp`.
- `A.NetClass == B.NetClass` -- the cross-domain guard (§3 for why this is
  needed, not just "a nice-to-have"). `NetClass` is one of the specially-
  cased properties (`CreateVarRef`'s `CmpNoCase` branches for `NetClass`,
  `ComponentClass`, `NetName`, `Type`), resolved before the generic
  `PROPERTY_MANAGER` lookup that `Footprint`/`Attribute` fall through to
  and fail on.
- `A.Pad_Type == 'SMD'` -- RULE 1a's SMD-only filter, corrected from
  `A.Attribute`.

## 3. Why a bare same-footprint test is unsafe, and why NetClass is the fix

RULE 1's own comment says it exists for "TO-247, SOT-23, QFN packages where
pad pitch < net class clearance" -- a manufacturability allowance for a
single package's own tight pin pitch. But `A.Reference == B.Reference`
alone matches *every* pad pair on a given footprint instance, including an
isolator's primary-side and secondary-side pins, which several declared
isolators in `elec/domain_manifest.yaml` put on **one shared footprint
reference** (the gate driver `hb.gate_hs.driver`, the aux supply
`aux_supply.psu`, the Y-cap `power_in.y_cap_pe`, both discharge relays, the
bypass relay, the ZCD opto). Granting those pairs a 0.1mm relaxation would
be exactly the wrong direction for a reinforced-isolation barrier.

KiCad's rule language cannot reference `elec/domain_manifest.yaml` --
custom rules only see per-item properties KiCad itself computes. Of those,
`NetClass` is the finest-grained property that (a) is dynamically resolved
per net rather than hardcoded, and (b) is confirmed to bind (§1/§2).
**`A.NetClass == B.NetClass` is therefore the correct construction: it is
not a perfect stand-in for "same domain," but it is the best available
dynamic proxy, and unlike a literal-net-name exclusion it does not silently
go inert when a net is renamed** -- it depends only on the net's *current*
classification, which is exactly the thing `688c15bb` demonstrated needs
occasional maintenance anyway (and which this fix also performs, §4/§5).

Demonstrated concretely with a fixture (`TestRule1CrossDomainGuard` in
`scripts/tests/test_generate_kicad_dru.py`): a same-footprint, same-
Reference, *different*-NetClass pair at a 0.5mm gap --

- **passes (wrongly) under the bare `A.Reference == B.Reference` test**
  (0.5mm > the relaxed 0.1mm minimum) -- reproducing the exact hazard this
  guard exists for;
- **correctly fails under RULE 1's real, as-committed condition**
  (`A.Reference == B.Reference && A.NetClass == B.NetClass`), because the
  differing NetClass means RULE 1 declines to match at all, so the pair
  falls through to the HighVoltage netclass's own 2.0mm baseline instead;
- **a genuine same-footprint, same-NetClass pair at a 0.15mm gap still
  passes** under the relaxed 0.1mm minimum (`TestRule1CrossDomainGuard::
  test_genuine_same_domain_pair_still_gets_the_relaxation`) -- the guard
  narrows RULE 1 to its intended cases, it does not neuter it.

## 4. Fix verification -- before/after, with denominators

### 4a. Isolated fixture (fail-before/pass-after)

`scripts/tests/test_generate_kicad_dru.py::TestRule1CrossDomainGuard` (3
tests) and `::TestRule1aPadTypeConditionFix` (1 test), all passing:
denominator = 1 cross-domain fixture (2 pads, 1 footprint) x 2 rule forms
(bare vs. guarded) + 1 same-domain fixture (2 pads, 1 footprint) + 1 static
regression assertion on the real emitted RULE 1a condition = 4 kicad-cli
DRC runs + 1 static check.

### 4b. Real board (`pcb/temper.kicad_pcb`), full old-vs-new `.dru`, both `.kicad_pro` states

Copied the real board to a scratch directory (never the repo copy).
Generated the complete `.dru` text from the base-commit (`688c15bb`)
module and this fix's module, and ran each against BOTH the as-committed
("stale") and this fix's corrected ("fixed") `pcb/temper.kicad_pro`, 1
`kicad-cli pcb drc --format json --severity-all` run each (4 runs, ~24s
each):

| generator | `.kicad_pro` | total violations | "Same footprint pads" (own 0.1mm floor) | "Fine pitch IC pads" (own 0.1mm floor) |
|---|---|---:|---:|---:|
| OLD (`688c15bb`) | stale | 1516 | 0 | 0 |
| OLD (`688c15bb`) | fixed | 1661 | 0 | 0 |
| NEW (this fix) | stale | 1523 | 0 | 16 |
| NEW (this fix) | fixed | 1560 | 0 | **16** |

**Read this table carefully -- it is not simply "count went up," and the
task's hard rule ("expect the count to rise, never weaken to reduce it")
is honored, not violated, by the one place it goes down:**

- **RULE 1 ("Same footprint pads") never fails its own 0.1mm floor either
  before or after**, in any combination -- 0.1mm is such a permissive
  minimum that almost nothing on this board is that tight. This is why the
  **999mm-lone-rule audit (§4c), not the full-file real-violation count, is
  the only way to tell whether RULE 1's *condition* binds at all** -- a
  rule whose value is never violated looks identical to a rule that never
  matches, unless you test the condition directly.
- **RULE 1a ("Fine pitch IC pads") surfaces 16 NEW, genuine violations**
  once its condition actually binds (both `A.Footprint`->`A.Reference` and
  `A.Attribute`->`A.Pad_Type`) -- all on `U9` (a fine-pitch IC, likely a
  QFN/SSOP RTD front-end part), at **0.0700mm actual edge-to-edge gap**,
  below even RULE 1a's own relaxed 0.1mm allowance. This was **invisible
  before this fix** (the dead condition matched nothing, so nothing on `U9`
  was ever checked against RULE 1a at all) and is a genuine new finding:
  `U9`'s real pin pitch is tighter than the manufacturability floor this
  rule's own comment says it should accommodate. **Reported, not resolved**
  -- this task's mandate is the rule's condition, not its clearance value
  or the board's footprint choice; a human should check whether 0.1mm is
  the right floor for this specific package or whether `U9`'s placement/
  footprint needs review.
- **`OLD`+`fixed` (1661) -> `NEW`+`fixed` (1560) is a net DECREASE of 101,
  and this is deliberate, not a weakening.** With the OLD (dead) RULE 1/1a
  condition, same-footprint pairs that are GENUINELY same-domain and
  GENUINELY meant to be exempted (RULE 1's own stated purpose) were instead
  being caught by the stricter netclass baseline, because the rule meant to
  exempt them never fired. Fixing the condition lets RULE 1/1a correctly
  grant the exemption its own long-standing comment already claims to
  provide -- removing false positives, not real protection. No clearance
  VALUE was lowered and no condition was loosened to make a real hazard
  look clean; the safety-relevant cross-domain rules (2-9) are byte-for-
  byte unchanged. Where the fix's own new discrimination logic actually
  matters (cross-domain pairs no longer wrongly exempted), the count either
  stays flat or rises -- see §4c and §5.

### 4c. 999mm-lone-rule audit -- every conditioned rule, both `.kicad_pro` states

Method: override each rule's own condition (unchanged, taken from the real
generator output) with an absurdly generous clearance minimum (999mm,
internally clamped to 500mm -- still enormous for this board), run
`kicad-cli pcb drc --format json --severity-all` against the real board,
count `type=="clearance"` violations whose description names that exact
rule (`rule '<name>'` -- see §2a for why this attribution matters and a
raw-clearance-count would not). 20 conditioned rules found in the
generator's output; run against both `.kicad_pro` states = 40 DRC runs
(~24s each, ~16 min total), plus the two rules needing a Pad_Type-corrected
re-run (§2b) = 4 more runs.

| Rule | Condition (abbreviated) | stale | fixed | binds? |
|---|---|---:|---:|---|
| 1 "Same footprint pads" | `A.Reference==B.Reference && A.NetClass==B.NetClass` | 184 | **8** (was 128 before the U7 fix, §5) | YES |
| 1a "Fine pitch IC pads" | `...&& A.Pad_Type=='SMD' ...&& A.Reference==B.Reference && A.NetClass==B.NetClass` | 183 | **9** | YES |
| 2 "AC Mains to LV" | `A.NetClass=='ACMains' && ...` | 0 | **496** | YES (after `.kicad_pro` fix) |
| 3 "AC Mains to HV" | `A.NetClass=='ACMains' && B.NetClass=='HighVoltage'` | 0 | **122** | YES (after `.kicad_pro` fix) |
| 4 "HV to LV" | `A.NetClass=='HighVoltage' && ...` | 498 | 498 | YES (already partly resolved via the pre-existing `DC_BUS*` wildcard pattern matching the live `DC_BUS_RTN` net) |
| 5 "HV internal same footprint" | `...&& A.Reference==B.Reference` (sibling fix) | 0 | **12** | YES (after `.kicad_pro` fix -- direct confirmation that netclass resolution was "the real enabler" the task predicted) |
| 6 "GateDrive near HV" | `A.NetClass=='GateDrive' && B.NetClass=='HighVoltage'` | 115 | 123 | YES |
| 7 "Power internal same footprint" | `...&& A.Reference==B.Reference` (sibling fix) | 0 | 0 | NO -- same-net exemption (§4 of the courtyard-fix doc), not a condition defect |
| 8 "Ground clearance" | `A.NetClass=='Ground' || ...` | 0 | 0 | NO -- no `Ground` netclass exists in `pcb/temper.kicad_pro`'s `classes` list at all (out of scope here, same gap the prior audit flagged) |
| 9 "USB differential" | `A.NetClass=='HighSpeed' && ...` | 0 | 0 | NO -- no `HighSpeed` class exists either (`Differential` is used instead); same out-of-scope gap |
| 10 "Default routing" | `A.Type=='Track' \|\| ...` | 499 | 499 | YES |
| ACMains/HighVoltage/FinePitch/Power/GateDrive trace width | `A.Type=='Track' && A.NetClass==X` | 0/0/268/0/321 | 0/0/211/0/263 | Mixed -- FinePitch/GateDrive bind both before and after; ACMains/HighVoltage/Power trace width show 0 in both states, UNVERIFIED (not traced further, out of this task's scope) |
| Ground/HighSpeed/Signal/HighCurrent trace width | same shape | all 0 | all 0 | NO -- same missing-class gap as rules 8/9 |

**Pattern, consistent with the prior (partly wrong) audit's own conclusion
about *which construction* binds, now corrected about *whether NetClass
does*:** every rule using `NetClass`/`Type` comparisons binds whenever the
underlying classification exists in `pcb/temper.kicad_pro`; rules 8/9 and
the four trace-width rules for classes that don't exist in this project's
`classes` list (`Ground`, `HighSpeed`, `Signal`, `HighCurrent`) remain
unresolved -- a real gap, but a *different* one than RULE 1/1a's (a missing
class definition, not a broken condition), out of this task's assigned
scope, and already flagged by the prior audit.

## 5. `pcb/temper.kicad_pro` was independently stale on the KiCad side

Confirmed the task's suspicion directly: `pcb/temper.kicad_pro`'s
`netclass_assignments` did not resolve `+170V_BUS`, `ac_l`, `ac_n` (or
`DC_BUS_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`, `PWM_HS`, `PWM_LS`,
`+15V_LS`) to their intended classes, even though the Python-side
`TEMPER_NET_ASSIGNMENTS` twin was already fixed in `688c15bb`. Verified by
extracting every real net name from `pcb/temper.kicad_pcb` (`grep -oP
'\(net \d+ "[^"]*"\)'`, 164 distinct nets) and diffing against
`net_settings.netclass_assignments`/`netclass_patterns` in
`pcb/temper.kicad_pro`.

**Fixed additively** (matching `688c15bb`'s own "audit the whole table,
add rather than delete" methodology) -- added, did not remove or rename,
any existing entry:

```
ac_l, ac_n                     -> ACMains   (case-mismatch: only "AC_L"/"AC_N" existed)
+170V_BUS, DC_BUS_RTN, SW_NODE  -> HighVoltage (dead legacy DC_BUS+/DC_BUS-/SWITCH_NODE names existed instead)
PWM_HS, PWM_LS, GATE_HS, GATE_LS -> GateDrive (dead legacy PWM_H/PWM_L/GATE_H/GATE_L existed instead)
+15V_LS                        -> Power
```

**A real, measured counterexample to "same NetClass implies same domain"
was found while verifying RULE 1's own match set, and closed:**

With `A.Reference == B.Reference && A.NetClass == B.NetClass` giving 128
matches (fixed `.kicad_pro`, before this section's addition), 15 of them
involved footprint `U7` (`hb.gate_hs.driver`, the UCC21550 gate driver).
Tracing the actual nets (`elec/src/main.ato`/`modules.ato`,
`elec/domain_manifest.yaml`): `U7` pin 1 (`INA`, primary/SELV-referenced
side) matched against pin 10 (`OUTB`, secondary/HV-referenced side, net
`gate_ls.input`) and pins 14/16 (`VSSA`/`VDDA`, secondary bias rails, nets
`hb.gate_hs.driver-p2`/`hb.gate_hs.driver-p1-1`) -- **a genuine primary-vs-
secondary, cross-isolation-barrier pair, spuriously treated as "same
domain" because NEITHER side was classified at all and both fell to the
shared `Default` bucket**, not because `GateDrive` itself spans both sides
(the auxiliary/filter nets at these exact pins, e.g. `ina`/`inb`/`input`,
turned out NOT to be the same nets as `PWM_HS`/`GATE_HS` -- a series filter
resistor separates them).

Fixed by classifying the two identifiable secondary bias nets into the
project's own pre-existing `HighVoltageIsolated` class (already used for
the equivalent HS-side bootstrap rail, `VBOOT_H`/`VBOOT_L`, `+5V_ISO` --
"Bootstrap supply, isolated gate power. 6mm clearance to LV. Reinforced
insulation", so this is applying an existing, already-reviewed category to
nets it had simply omitted, not inventing a new one):

```
hb.gate_hs.driver-p1-1 (VDDA), hb.gate_hs.driver-p2 (VSSA) -> HighVoltageIsolated
```

**Verified this closes the specific counterexample**: re-running the
999mm-lone-rule audit for "Same footprint pads" after this addition drops
`U7`'s contribution from 15 pairs to **0**, and the rule's total match
count drops from 128 to **8** (the remaining 8 are decoupling capacitors
and one RTD IC's own adjacent pins -- `C10`/`C17`/`C18`/`C19`/`U9`, all
plausible genuine same-domain manufacturability cases, not further
isolator-barrier crossings).

**This single, narrow addition also surfaces 168 NEW, real clearance
violations elsewhere on the board** (netclass `'HighVoltageIsolated'`
baseline, 6.0mm), because these two nets were never protected by their
correct reinforced-isolation clearance requirement before. **This is
expected and correct, not a bug**: the two nets were structurally
unprotected (falling to `Default`'s 0.2mm) and are now correctly held to
the same 6.0mm bar as their sibling `VBOOT_H`/`VBOOT_L` rail. Per the
task's hard rule, this rise is not weakened away.

**Residual, explicitly not chased further (UNVERIFIED, §7):** the
remaining 8 "Same footprint pads" matches include several other nets that
are ALSO unclassified on both sides of a real pin pair (`ina`, `inb`,
`gnd`, `boot`, `sw`, `RTD_DRDY`, `vcc`, `bias`, `refin_n`) -- these did not,
on inspection, turn out to be genuine cross-domain pairs (all traced to
either decoupling caps or one IC's own adjacent, same-function pins), but
the underlying structural risk (two different domains both falling to
`Default` and appearing "same" by coincidence) is not eliminated in
general, only for the one concrete instance found. A full audit
classifying every one of this board's 164 nets was out of this task's
scope (narrowly targeted at RULE 1/1a's own discrimination, plus the
specific classes RULE 1/1a and rules 2-6 reference) and is flagged as
follow-up.

## 6. Compliance with the task's hard rules

- **Never weakened a rule to reduce a violation count.** No clearance
  VALUE was changed anywhere in this diff. Every condition change either
  makes a previously-dead rule bind (RULE 1, RULE 1a, and -- via the
  `.kicad_pro` fix -- RULE 5, "AC Mains to LV/HV") or adds a stricter
  requirement that did not previously exist (the `HighVoltageIsolated`
  classification, +168 violations). The one net DECREASE observed
  (OLD+fixed 1661 -> NEW+fixed 1560) is explained in full in §4b: it is
  the removal of false positives caused by RULE 1/1a's OWN dead condition
  failing to grant an exemption its comment already claims to provide, not
  a loosening of any safety-relevant rule.
- `power_pcb_dataset/drc_ceiling.json` -- not touched.
- `pcb/temper.kicad_pcb`, `elec/src/`, footprints -- not touched. Only
  `scripts/generate_kicad_dru.py`, `scripts/tests/test_generate_kicad_dru.py`,
  `pcb/temper.kicad_pro`, and this evidence doc were changed.
- No `git stash` used.
- No `run_in_background` deliberately requested; the harness auto-
  backgrounded two ad-hoc `kicad-cli`/`measure.py` probe commands that
  exceeded the tool's default foreground timeout mid-investigation --
  both were stopped via `TaskStop` rather than waited on, and the same
  measurement was re-run in the foreground with an explicit longer
  timeout and/or split into smaller batches.
- Committed after the generator + `.kicad_pro` + test changes (commit
  `0c2e74ae`).
- Disk: no new worktree created; reused this agent's already-assigned
  worktree (re-based its branch onto `688c15bb` since it started on an
  unrelated, already-merged branch) and the main checkout's already-synced
  `.venv` via `UV_PROJECT_ENVIRONMENT` rather than syncing a fresh one.
- `uv run --no-sync` used throughout, never bare `uv run`.
- All real-board measurement was done from copies in this agent's own
  scratchpad directory (`/private/tmp/.../scratchpad/rule1redo/`), never
  by editing or reading a live copy from the shared main checkout.

## 7. Verification

- `make netlist` -- passed (rebuilt `elec/build/default.net`).
- `uv run --no-sync python -m pytest scripts/tests/test_generate_kicad_dru.py -v`
  -- **14 passed**, 0 failed. 10 pre-existing tests unchanged/still passing
  (Rules 5/7's sibling fix is untouched); 4 new: 3 in
  `TestRule1CrossDomainGuard` (fail-before/pass-after fixture proving the
  guard is necessary, a real-condition end-to-end check, and a same-domain
  positive control) + 1 in `TestRule1aPadTypeConditionFix` (static
  regression guard against both `A.Footprint` and `A.Attribute`
  reappearing).
- `uv run --no-sync python -m pytest elec/validation -q` -- **30 passed**.
- `uv run --no-sync ruff check scripts/generate_kicad_dru.py scripts/tests/test_generate_kicad_dru.py`
  -- all checks passed.
- Nine required gates:

| Gate | Result |
|---|---|
| `check_domain_partition` | PASSED (exit 0) -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects (60 declared nets, 2 domains, 10 isolators, over 168 compiled nets/components) |
| `capacity_budget_gate` | PASSED (exit 0) -- 0 defects |
| `mpn_fabrication_gate` | PASSED (exit 0) -- 0 new violations |
| `check_derived_doc_drift` | PASSED (exit 0) -- 3 docs, 47 tables, 136 fields checked |
| `check_copper_net_consistency` | **FAILED (exit 3) -- 146 violations, confirmed pre-existing** (same count as the courtyard-fix doc's §5); not fixed, per instructions, `pcb/temper.kicad_pcb` untouched |
| `check_rust_drc_presence` | PASSED (exit 0) -- `temper_drc_rs` symbols present and fresh |
| `check_undeclared_imports` | PASSED (exit 0) -- 1262 stdlib, 1252 local, 1 allowlisted, 712 resolved |
| `check_stale_extensions` | exit 3, 10 crates flagged "stale" -- confirmed the documented checkout-mtime false positive (`git checkout -b` resets tracked-file mtimes newer than the shared checkout's already-built `.venv` artifacts); none of the 10 crates' `.rs` files are touched by this diff |
| `check_net_classification` | PASSED (exit 0) |
| `check_pll_range_consistency` | PASSED (exit 0) -- 4/4 checks agree |
| `check_isolation_keepout` | exit 3, as expected/documented (no `MAINS_SELV_ISOLATION_BARRIER` keepout zone placed -- pre-existing, unrelated to this fix) |
| `check_measurement_provenance` | exit 5, as expected/documented (`power_pcb_dataset/drc_ceiling.json` malformed `source` field -- pre-existing, unrelated) |

## UNVERIFIED

- **The exact magnitude of every count reported at a 999mm/500mm-clamped
  threshold.** §2a establishes kicad-cli 10.0.4's JSON DRC report truncates
  total `"clearance"`-type violations at roughly 500, shared across all
  sources. Every reported nonzero count in this document should be read as
  "at least N" rather than an exact figure; every reported 0 is a firm
  negative (truncation cannot fabricate a match). The qualitative
  binds/doesn't-bind conclusions in §1/§4c are unaffected by this.
- **Whether rules 8/9 and the four affected trace-width rules' "0
  matches"** trace to a genuinely missing `Ground`/`HighSpeed`/`Signal`/
  `HighCurrent` net classification the way `ACMains`/`HighVoltage`/
  `GateDrive` did, versus some other cause -- not independently re-
  investigated here (same gap the prior audit flagged; `pcb/temper.kicad_pro`'s
  `classes` list has no entries by these names at all, so it's very likely
  the same story, but this wasn't traced net-by-net the way the
  `HighVoltageIsolated`/U7 case was in §5).
- **`ACMains`/`HighVoltage`/`Power` trace-width rules showing 0 matches in
  both `.kicad_pro` states** (§4c table) -- not traced further; plausibly
  this board simply has no routed copper TRACKS (as opposed to pads/vias)
  currently assigned to those classes, but not confirmed by direct
  inspection.
- **Whether other same-footprint pairs beyond U7 hide a similar cross-
  domain-via-shared-`Default` miscategorization** -- §5's residual-8 list
  was inspected and found benign, but a systematic classification of every
  one of this board's 164 nets (versus the narrowly-targeted additions made
  here) was out of scope and was not performed.
- **`U9`'s 0.0700mm actual same-footprint pin gap** (§4b) -- newly visible
  because RULE 1a's condition now binds; whether 0.1mm is the correct
  manufacturability floor for this specific package, or whether `U9`'s
  footprint/placement needs review, was not determined here (out of this
  task's condition-only mandate) and is flagged for a human.
- **Whether the CI container's kicad-cli 10.0.5 reproduces these exact
  counts**: not independently re-verified in this session (no Docker pull).
  Relies on the sibling courtyard-condition-fix's own direct container
  test (10.0.4 vs. 10.0.5 agreement within run-to-run noise) and the same
  source-tag diff precedent this document also used
  (`pcbexpr_evaluator.cpp`/`pad.cpp` at `10.0.4` vs. `10.0.5`, not
  re-diffed here since the sibling doc already established their
  equivalence for the functions both fixes touch).
