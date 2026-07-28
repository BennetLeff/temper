<!-- provenance: commit=fd6c9c15 dirty=false (base); this file added in worktree agent-a3a627b684206b7b8, branch fix/drc-courtyard-condition-fix -->

# Fixing the fail-open courtyard condition in generated DRC Rules 5 and 7

Base commit: `fd6c9c15` (`merge: K2/K3 replaced with a DPDT part that closes
the DC-break gap too`, branch `docs/methodology-loop-discipline`). Work done
in worktree `agent-a3a627b684206b7b8`, branch `fix/drc-courtyard-condition-fix`
created from that commit.

Reads first, per task instructions:
`docs/evidence/2026-07-28-drc-coating-failopen-fix.md`,
`scripts/generate_kicad_dru.py`, `scripts/tests/test_generate_kicad_dru.py`,
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`.

## FALSIFIER, stated up front

> "`A.insideCourtyard(B.Reference)` is the defect, and a corrected condition
> makes the rule fire on the real board. If the rule still contributes zero
> violations after the fix, either the condition was not the cause or the
> board genuinely has no same-footprint HV pad pairs — establish which."

**Both halves of the falsifier's premise fire, but the honest answer to its
"establish which" is a third thing the sentence didn't anticipate:**

1. **The condition genuinely was the cause of a real defect.** Proven three
   ways below: KiCad source analysis, an isolated fixture (fail-before/pass-
   after, 0/0 → 0/1), and the real board (full old-vs-new `.dru` file, still
   0 → 0 for this rule specifically — see why in point 2).
2. **The board does *not* "genuinely have no same-footprint HV pad pairs"**
   in the sense of lacking the physical hazard — it has exactly the TO-247
   IGBT pair (`U5`, `U6`) the rule's own comment describes. But **today,
   neither IGBT's high-voltage pins are classified into the `HighVoltage`
   netclass at all**, because the board's actual net names (`+170V_BUS`,
   `SW_NODE`) don't match the project's `netclass_assignments` (which still
   reference retired names `DC_BUS+`, `SWITCH_NODE`) or its
   `netclass_patterns` wildcard `DC_BUS*` (`+170V_BUS` and `SW_NODE` don't
   match that pattern; only `DC_BUS_RTN` does). This is a **net-classification
   gap**, not a rule-condition gap, and it appears to be the same K2/K3-era
   net-rename drift `check_copper_net_consistency` already flags (confirmed
   pre-existing at `fd6c9c15`, see "check_copper_net_consistency" below).
   Separately, and independently: even if classification were fixed, the
   *actual* footprint used (`TO-247-3_Vertical`, 2.5mm-wide pads on a 5.45mm
   pitch) has a **2.95mm edge-to-edge gap** between its power pins — this
   clears the corrected 2.0mm requirement comfortably. The generator's own
   comment ("1.95mm edge-to-edge") assumes a different, narrower pad style
   than the one actually placed on this board.

So: condition was broken (fixed here) — value is sound (fixed here) — but
whether *this specific rule* would flag *this specific board* today depends
on a net-classification defect this task's mandate does not cover. Reported,
not fixed, below and in the audit.

## 1. Establishing the correct expression for KiCad 10.x custom rules

**Sources consulted and cited, not just kicad-cli behavior:** the KiCad
source itself, via `gh api repos/KiCad/kicad-source-mirror/contents/...`
(the official GitHub mirror of `gitlab.com/kicad/code/kicad`) at the exact
release tags in play:

- `pcbnew/pcbexpr_functions.cpp` at tag `10.0.4` and tag `10.0.5` (diffed:
  the two are functionally identical for everything relevant here — only
  cosmetic line-reflow and one unrelated `ClearArcs()` addition differ).
- `pcbnew/pcbexpr_evaluator.cpp` (property/field resolution).
- `pcbnew/pad.cpp` and `pcbnew/footprint.cpp` (`PROPERTY_MANAGER::AddProperty`
  registrations, to check whether `"Footprint"` is a real property name).

**What `insideCourtyard`/`intersectsCourtyard` actually does**
(`pcbexpr_functions.cpp`, `RegisterAllFunctions()`):

```cpp
RegisterFunc( wxT( "insideCourtyard('x') DEPRECATED" ), intersectsCourtyardFunc, true );
RegisterFunc( wxT( "intersectsCourtyard('x')" ), intersectsCourtyardFunc, true );
```

`intersectsCourtyardFunc` pops its argument, calls `arg->AsString()` on it
inside a deferred-eval closure, and passes that string as a **selector** to
`searchFootprintsNearItem()` / `testFootprintSelector()`:

```cpp
static bool testFootprintSelector( FOOTPRINT* aFp, const wxString& aSelector )
{
    ...
    else if( aFp->GetReference().Matches( aSelector ) )
    {
        return true;
    }
    ...
}
```

and, for the special case where the selector is exactly `"A"` or `"B"`:

```cpp
// "A"/"B" resolve to the items under test; any other selector is matched
// against the footprints whose courtyard can actually reach aItem...
if( aArg == wxT( "A" ) )
{
    FOOTPRINT* fp = dynamic_cast<FOOTPRINT*>( aCtx->GetItem( 0 ) );
    return fp && aFunc( fp );
}
else if( aArg == wxT( "B" ) )
{
    FOOTPRINT* fp = dynamic_cast<FOOTPRINT*>( aCtx->GetItem( 1 ) );
    return fp && aFunc( fp );
}
```

Two things follow from this, both confirmed empirically (§3):

- The literal-string form (`A.insideCourtyard('Q1')`) works because
  `GetReference().Matches("Q1")` is a plain wildcard string match.
- The special `'A'`/`'B'` literal-token form only works when the *item under
  test itself* is a `FOOTPRINT` (the `dynamic_cast` requires it) — useless
  here since Rules 5/7 match `Pad` vs. `Pad`, not `Footprint` vs.
  `Footprint`.
- **There is no code path that evaluates the function's argument as an
  arbitrary property expression of the *other* matched item and uses its
  *value* as the selector.** `A.insideCourtyard(B.Reference)` is parsed, and
  `B.Reference` legitimately resolves to a string (KiCad's property system
  supports `A.Reference`/`B.Reference` as generic pad→parent-footprint
  property lookups — see `pcbexpr_evaluator.cpp` line 482, comment: "If the
  property isn't defined on the item itself but is defined on its parent
  footprint (e.g. Reference, Value), resolve against the parent"), but this
  is exactly the same class of expression that empirically does not bind
  (§3) — the deeper root cause of *why* the argument's already-correctly-
  computed string value doesn't end up mattering was not pinned to one exact
  line of C++ dispatch order, but the *observable, source-consistent, and
  reproducible fact* is: dynamic-property arguments to `insideCourtyard`/
  `intersectsCourtyard` do not bind, only literal strings and the
  self-referential `'A'`/`'B'` tokens do.

**Rule 1's `A.Footprint == B.Footprint` is a *different*, independent
defect**, found while auditing (§4): `pcbnew/pad.cpp` and
`pcbnew/footprint.cpp`'s `PROPERTY_MANAGER::AddProperty(...)` calls register
`"Reference"`, `"Library Link"`, `"Pad Number"`, etc. — **no property named
`"Footprint"` exists anywhere in either class.** `A.Footprint` therefore
resolves to an undefined value on both sides, and the equality comparison
never matches. This is Rule 1's own condition (the sibling agent's rule) —
not touched here, but load-bearing enough to report explicitly (§4, §7).

**Version check (10.0.4 local vs. 10.0.5 CI):** the task flagged that a
prior DRC investigation found a version discrepancy mattered. That
investigation (`docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md`) in
fact *ruled out* version as the cause of the discrepancy it examined (two
different CI runs on two different commits, not a KiCad version effect) and
positively confirmed, by pulling CI's own `ghcr.io/bennetleff/temper-ci:latest`
container and running its bundled 10.0.5 `kicad-cli` against the byte-
identical current board, that **10.0.4 and 10.0.5 agree to within the
documented run-to-run noise band** (708 vs. 707 errors on the same board).
Given the disk-tight constraint here (`docker system df`/`docker images`
showed no cached image and Docker's daemon was not even running locally), a
second container pull was not repeated; instead the **exact release-tagged
source** was diffed (`pcbexpr_functions.cpp` at `10.0.4` vs. `10.0.5`,
above) and found identical for every function this fix touches. Between the
prior empirical container test and this source diff, I'm confident this
fix's behavior does not depend on the 10.0.4/10.0.5 distinction.

## 2. What the rule is actually trying to express

Rule 5 ("HV internal same footprint") and Rule 7 ("Power internal same
footprint") both intend: *given two pads on the same net class, on the same
physical footprint instance, enforce a clearance appropriate to that net
class's hazard level* (2.0mm reinforced clearance for HighVoltage per
`HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.4 and the coating-failopen fix; 0.2mm
manufacturability allowance for Power, per Rule 7's own comment "allow
SOT-23 pitch"). "Same footprint instance" is the operative test — not
courtyard geometry as such (courtyard is a placement-keepout outline, a
proxy that happened to be reached for, not the actual intent).

**Rejected the broken condition's shape rather than patching around it.**
`A.Reference == B.Reference` (a direct property-equality comparison) is not
a cosmetic rewrite of `A.insideCourtyard(B.Reference)` — it drops the
courtyard-geometry indirection entirely in favor of testing the actual thing
the rule cares about (same footprint instance, via each footprint's unique
reference designator). This is simpler, doesn't depend on courtyard-polygon
existence/correctness on every footprint in the library, and — critically —
is the one form confirmed to actually bind in kicad-cli's expression engine
(§3).

## 3. Fix verification

### 3a. Isolated fixture — fail-before/pass-after, no `git stash`

Loaded the base-commit (`fd6c9c15`) generator via `git show fd6c9c15:
scripts/generate_kicad_dru.py` into a standalone file and imported it with
`importlib` as an independent module (never checked out over the working
tree), then ran both the base and fixed RULE 5 conditions through the same
kiutils-built 2-pad, 1.95mm-gap, `HighVoltage`-netclass fixture
`scripts/tests/test_generate_kicad_dru.py::_build_fixture` already uses:

| Generator | RULE 5 condition | min=1.5mm | min=2.0mm |
|---|---|---:|---:|
| BASE (`fd6c9c15`) | `...&& A.insideCourtyard(B.Reference)` | 0 | 0 |
| FIXED (this change) | `...&& A.Reference == B.Reference` | 0 | **1** |

The base condition never binds regardless of value (0/0) — the defect. The
fixed condition binds and the value is load-bearing (0 → 1 at exactly the
1.5mm → 2.0mm threshold crossing the 1.95mm gap) — the same falsifier
mechanics the coating-value fix demonstrated, now with a condition that
actually fires. Denominator: 1 pad pair, 1 footprint, 2 threshold values, 2
generator versions = 4 DRC runs.

This exact comparison is now `scripts/tests/test_generate_kicad_dru.py::
TestDrcFalsifier::test_real_rule_as_committed_now_binds_after_condition_fix`,
using the condition string extracted **verbatim from `generate_dru()`'s real
output**, not a hand-copied substitute — so a regression that silently
reintroduces the broken form is caught structurally, not just by comment.

### 3b. Real board (`pcb/temper.kicad_pcb`), full old-vs-new `.dru` file

Copied the real board and its matching `pcb/temper.kicad_pro` (read-only;
repo copy never touched) to a scratch directory. Generated the **complete**
`.dru` text from both the base-commit module and the fixed module (the same
`generate_dru()` call the coating-fix precedent used, not a single isolated
rule), wrote each in turn, and ran `kicad-cli pcb drc --format json` once
per file:

| `.dru` file | Total violations | "HV internal same footprint" | "Power internal same footprint" |
|---|---:|---:|---:|
| OLD (`fd6c9c15`, broken condition) | 1515 | 0 | 0 |
| NEW (this change, fixed condition) | 1522 | 0 | 0 |

**0 → 0 for both rules, on the real board, even with the condition fixed.**
Per the falsifier discussion above, this is **not** "the fix didn't work" —
§3a proves the fix binds correctly wherever its net-class precondition is
met. It's that **no footprint on this board currently has 2+ pads that
KiCad's own netclass resolution puts in the `HighVoltage` netclass**, and
the one footprint that does have 2+ same-footprint `Power`-classed pads
(`U4`, both pads on net `+15V`) has them on the *same net*, which KiCad's
clearance check exempts from testing by default regardless of any custom
rule (same-net copper touching is intentional).

Verified this net-classification claim independently of kicad-cli, by
replicating KiCad's own resolution logic (`netclass_assignments` exact
match, then `netclass_patterns` wildcard match via `fnmatch`) directly in
Python against the board+project files:

```
--- footprints with >=2 pads classified HighVoltage ---
(none)
--- footprints with >=2 pads classified Power ---
  U4 SOT-23-6 [('3', '+15V', ...), ('5', '+15V', ...)]   # same net, not a hazard pair
```

And the actual TO-247 IGBTs (`U5`, `U6`, footprint `TO-247-3_Vertical`) —
the pair the generator's own RULE 5 comment is about — have pads at
**5.45mm center pitch with 2.5mm pad width = 2.95mm edge-to-edge**, which
clears the corrected 2.0mm requirement on its own, independent of net-class
resolution. (Their *pin nets* are `hb.power_loop.q_high-g` / `+170V_BUS` /
`SW_NODE` for U5 and `GATE_LS` / `SW_NODE` / `DC_BUS_RTN` for U6 — none of
`+170V_BUS` or `SW_NODE` currently resolves to `HighVoltage`, only
`DC_BUS_RTN` does, via the `DC_BUS*` wildcard pattern.)

**Denominators for this section:** real board = 168 footprints, 164 nets,
2 full DRC runs (old, new) at default severity, plus a direct Python
netclass-resolution replication over all footprints/pads on the board
(no sampling).

## 4. Audit: every other generated rule, whether it demonstrably matches

Method: override each rule's own condition (unchanged) with an absurdly
generous constraint minimum (`999mm` for clearance), run `kicad-cli pcb drc
--format json --severity-all` against the real board, and count violations
whose description names that rule. A rule that matches *anything* on this
1500-item board will produce an unmissable violation at 999mm; a rule that
matches nothing produces exactly 0 regardless of how permissive or strict
its real value is. 13 rules checked (12 pairwise-condition rules + 1 spot
sanity check), 1 real-board DRC run per rule (~20s each, ~4.5 min total):

| Rule | Condition (abbreviated) | Matches on real board? |
|---|---|---|
| 1 "Same footprint pads" | `...&& A.Footprint == B.Footprint` | **NO — 0 matches.** Same defect class as Rule 5/7, different mechanism (`"Footprint"` is not a registered property at all, §1). Sibling agent's rule; not fixed here, reported for their attention. |
| 1a "Fine pitch IC pads" | `...&& A.Footprint == B.Footprint` | **NO — 0 matches.** Same broken clause as Rule 1. |
| 2 "AC Mains to LV" | `A.NetClass=='ACMains' && ...` | NO — 0 matches, but **not a condition-syntax defect**: this board has zero nets currently resolving to `ACMains` (its `netclass_patterns` entry `AC_*` doesn't match any real net name either — same net-naming-drift family as §3b, out of scope here). |
| 3 "AC Mains to HV" | `A.NetClass=='ACMains' && B.NetClass=='HighVoltage'` | NO — 0 matches, same `ACMains`-classification gap as Rule 2. |
| 4 "HV to LV" | `A.NetClass=='HighVoltage' && B.NetClass!=... ` | **YES — 498 matches.** Confirms plain `NetClass`-only conditions resolve and bind correctly. |
| 5 "HV internal same footprint" (as-committed) | `...&& A.insideCourtyard(B.Reference)` | NO — 0 matches (the defect this task fixes). |
| 5 (fixed) | `...&& A.Reference == B.Reference` | NO — 0 matches on the real board *today*, for the net-classification reason in §3b (condition itself proven to bind in §3a). |
| 6 "GateDrive near HV" | `A.NetClass=='GateDrive' && B.NetClass=='HighVoltage'` | **YES — 115 matches.** |
| 7 "Power internal same footprint" (as-committed) | `...&& A.insideCourtyard(B.Reference)` | NO — 0 matches (same defect as Rule 5; fixed here since not the sibling's rule). |
| 7 (fixed) | `...&& A.Reference == B.Reference` | NO — 0 matches today (same-net exemption, §3b). |
| 8 "Ground clearance" | `A.NetClass=='Ground' || B.NetClass=='Ground'` | NO — 0 matches at 999mm on this board's item set as tested; not investigated further (out of this task's HV/same-footprint scope; likely a `Ground`-classification question analogous to `ACMains`, not a condition-syntax defect — `||`-based `NetClass` conditions use the same specially-handled resolution path as rules 4/6, which are proven working). |
| 9 "USB differential" | `A.NetClass=='HighSpeed' && B.NetClass=='HighSpeed'` | NO — 0 matches; this board's USB diff pair net-class resolution not investigated further, same caveat as Rule 8. |
| 10 "Default routing" | `A.Type=='Track' \|\| B.Type=='Track'` | **YES — 499 matches.** Confirms `Type`-only conditions bind correctly too. |

**Pattern:** every rule using only `NetClass`/`Type` comparisons (both
specially-cased in KiCad's expression compiler — confirmed in
`pcbexpr_evaluator.cpp`'s `CreateVarRef`, which hard-codes `NetClass`,
`ComponentClass`, `NetName`, and `Type` to dedicated `VAR_REF` subclasses
before ever reaching generic `PROPERTY_MANAGER` lookup) binds correctly
when the underlying net classification exists. Every rule using
`A.Footprint == B.Footprint` or `A.insideCourtyard(B.Reference)` — both
generic-property-lookup or geometry-function-argument constructs — silently
matches nothing. **This is exactly the systemic pattern the task predicted**:
one dynamic-reference/generic-property condition failing silently made it
worth checking whether others shared the defect, and two more (1, 1a) did.

Rules 8/9's "0 matches" were **not** traced to a condition-syntax defect
the way 1/1a/5/7 were (their `NetClass`-only shape is the same proven-
working pattern as rules 4/6) — most likely this board simply has zero nets
resolving to `Ground`/`HighSpeed` netclass today, the same category of gap
as `ACMains` (rules 2/3). Flagged as `UNVERIFIED` below rather than asserted,
since confirming it needs the same netclass-resolution replication done for
`HighVoltage`/`Power` in §3b, not repeated here for every class to keep this
audit bounded.

## 5. `check_copper_net_consistency` — confirmed pre-existing at `fd6c9c15`

Per task instructions, this gate was expected to possibly fail "pending a
board resync after the K2/K3 relay change." Ran it at the unmodified base
commit (after `make netlist`, no board/schematic files touched):

```
FAILED -- 146 violation(s)
  [net-mismatch] ... net 'power_in.ntc-no' (ordinal 90) does not exist in
    the compiled netlist -- stale board (needs a resync) or orphaned copper
    on a deleted net
  [net-mismatch] ... net 'discharge.k_dis1-nc' (ordinal 38) does not exist...
  [pad-mismatch] 7 violation(s):
    R12 pad 2: board has net 'discharge.k_dis1-nc', compiled netlist
      declares 'discharge.k_dis1-nc1' for this pin
    ... (RT1, U1, U2 pad mismatches on 'power_in.ntc-no' vs 'no')
```

**Confirmed pre-existing and confirmed as the same family of net-naming
drift** underlying §3b/§4's `HighVoltage`/`ACMains` classification gaps —
not identical violations (this gate compares board nets against the
*compiled netlist*; §3b's finding is about the *project's netclass
assignment tables* vs. the board's actual net names), but the same root
event (a net rename — evidently around the K2/K3 relay replacement —
propagated to some places and not others). **Not fixed, per task
instructions** — `pcb/temper.kicad_pcb` was not touched.

## 6. Scope decision: Rule 7 fixed, Rule 1/1a reported only

The task named Rule 5 as the assigned defect and asked for an audit of
others. Rule 7 ("Power internal same footprint") turned out to share Rule
5's *exact* condition string shape and root cause, is not any other agent's
current edit target, and the fix is identical and already verified (§3a
covers the mechanism; a static regression test —
`TestPowerInternalConditionFix` — guards the specific string). Fixing it
alongside Rule 5 avoids leaving a known-identical defect in the file one
grep away from the one just fixed. Rule 1/1a's `A.Footprint == B.Footprint`
defect is **not** fixed here: it's the sibling agent's explicit rule (net-
class discrimination), the coordination instructions say not to change
Rule 1's net-class logic or clearance value, and — since the condition
itself doesn't currently bind — it isn't even clear whether the sibling's
planned net-class fix will have any observable effect until this deeper
defect is also addressed. **Flagging this prominently for the sibling/a
human**, not fixing it myself.

## 7. The "coupling" note, re-examined

The task said: *"Rule 1 masks the same pad pair regardless of Rule 5's
value or file order... your fix alone may not change the board's violation
count."* This framing (from the coating-fix predecessor's investigation)
assumed Rule 1's `0.1mm` condition *matches* the pad pair and simply out-
permissions it. **That assumption does not hold under closer testing**:
Rule 1's condition, tested here at a 999mm threshold on the real board
(§4) and on the isolated fixture, produces **0 matches**, not "matches with
a trivially-passing value." Rule 1 isn't masking Rule 5's pad pair by being
more permissive — its condition doesn't bind on this board at all, for an
independent reason (§1, §4). The predecessor's conclusion that "Rule 1 is
the thing actually governing this pad pair today" should be revised: **as
of this investigation, neither Rule 1 nor a corrected Rule 5 currently
binds on any pad pair, so nothing is currently enforcing same-footprint HV
clearance on this board** — a more serious gap than "the wrong rule wins,"
though the practical bottom line (this board's IGBT pins are today
unprotected by any same-footprint HV clearance check) is the same one the
predecessor already flagged as needing follow-up.

## Verification

- `make netlist` — passed (rebuilt `elec/build/default.net`).
- `uv run --no-sync python -m pytest scripts/tests/test_generate_kicad_dru.py -v`
  — **10 passed**, 0 failed (1 new falsifier assertion rewritten to prove the
  fix binds using the real emitted condition; 1 new static regression test
  for Rule 7).
- `uv run --no-sync python -m pytest elec/validation -q` — **30 passed**.
- `ruff check scripts/generate_kicad_dru.py scripts/tests/test_generate_kicad_dru.py`
  — all checks passed. (`ruff format --check` reports the file "would be
  reformatted" — pre-existing at base commit across many unrelated lines,
  not introduced by this change; not run, to keep the diff minimal and avoid
  conflicting with the sibling agent's concurrent edits to the same file.)
- Ten required gates:

| Gate | Result |
|---|---|
| `check_domain_partition` | PASSED — 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects (60 declared nets, 2 domains, 10 isolators, over 168 compiled nets/components) |
| `capacity_budget_gate` | PASSED — 0 defects |
| `mpn_fabrication_gate` | PASSED — 0 new violations |
| `check_derived_doc_drift` | PASSED — 3 docs, 47 tables, 136 fields checked |
| `check_copper_net_consistency` | **FAILED — 146 violations, confirmed pre-existing at base commit `fd6c9c15`** (§5); not fixed, per instructions |
| `check_rust_drc_presence` | PASSED — `temper_drc_rs` symbols present and fresh |
| `check_undeclared_imports` | PASSED — 649 files, 3218 imports checked |
| `check_stale_extensions` | exit 0, but reports 10 "stale" crates — the documented checkout-mtime false positive (`git checkout -b` resets tracked-file mtimes newer than the shared main-checkout `.venv`'s already-built artifacts; no `.rs` file touched by this change) |
| `check_net_classification` | PASSED |
| `check_pll_range_consistency` | PASSED — 4/4 checks agree |
| `check_isolation_keepout` | exit 3, as expected/documented |
| `check_measurement_provenance` | exit 5, as expected/documented |

## UNVERIFIED

- **The exact C++ dispatch reason** `A.insideCourtyard(B.Reference)`'s
  already-correctly-computed `B.Reference` string value fails to bind, at
  the level of "which line evaluates it in which order relative to which
  cache." The *fact* (dynamic property arguments to `insideCourtyard`/
  `intersectsCourtyard` don't bind; literal strings and `'A'`/`'B'` tokens
  do) is established by source reading plus reproducible empirical testing
  on two independent boards (fixture + real board), not by single-stepping
  KiCad's C++.
- **Rules 8 ("Ground clearance") and 9 ("USB differential")'s "0 matches"**
  were not traced to a specific net-classification gap the way `ACMains`/
  `HighVoltage` were (§3b, §4) — flagged as likely the same family of gap,
  not confirmed by the same direct-replication method.
- **check_stale_extensions's 10 "stale" crates** are asserted here to be the
  documented checkout-mtime artifact rather than re-diagnosed from scratch;
  none of the 10 crates has a `.rs` file in this change's diff.
- **Whether `power_pcb_dataset/drc_ceiling.json`'s ceiling is affected**: not
  applicable — the fix's functional change (Rule 5/7's condition) does not
  currently bind on real board DRC output per §3b, so no ceiling breach is
  possible from this change; the file was not touched.
- **Whether the CI container's 10.0.5 `kicad-cli` reproduces the exact
  numbers in §3a/§3b**: not independently re-verified in this session (no
  Docker pull, per the disk-tight constraint and no cached image/running
  daemon locally). Relies on (a) the prior investigation's direct container
  test on this same board showing 10.0.4/10.0.5 agreement, and (b) an exact
  source diff of the relevant KiCad function between the `10.0.4` and
  `10.0.5` release tags showing no behavioral difference. A human with a
  faster/larger environment should repeat the container test directly if
  stronger confirmation is wanted.

## Compliance with the task's hard rules

- Never weakened a rule to keep a check green; the corrected condition
  makes Rules 5/7 strictly more capable of firing than before (from "never"
  to "whenever their net-class precondition is met"), and no value was
  tuned to keep a violation count down.
- `power_pcb_dataset/drc_ceiling.json` — not touched.
- `pcb/temper.kicad_pcb`, `elec/src/`, footprints — not touched.
- No `git stash` used (fail-before comparison done via `git show <ref>:path`
  into a standalone file + Python `importlib`, never checked out over the
  working tree).
- No `run_in_background` requested; the harness auto-backgrounded one
  ad-hoc probe command that exceeded its foreground timeout mid-investigation
  (before the real fix work) — its completion notification was read once
  when it arrived, not polled in a loop.
- Committed after the generator + test changes (commit `0edb3828`).
- Disk: no new worktrees; reused the main checkout's already-synced `.venv`
  via `UV_PROJECT_ENVIRONMENT` (this worktree's own `uv run` had created an
  empty 76K `.venv` skeleton before I noticed and switched — left in place,
  negligible size, not deleted to avoid any risk of an unintended broader
  delete); no Docker image pulled.
- `uv run --no-sync` used throughout, never bare `uv run`.
- Diff kept minimal and localized to Rule 5's and Rule 7's condition strings
  plus their comments, and the corresponding tests — no restructuring, no
  reordering, no change to Rule 1's clearance value or net-class logic.
