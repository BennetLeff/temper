---
title: "A rename fixes the name and orphans every key derived from it — the +340V_BUS net's second failure"
date: "2026-07-28"
category: best-practices
module: temper_placer
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a net, signal, or identifier is renamed anywhere in the design source, and the same string appears as a dict key, wildcard pattern, or lookup table entry in a different file"
  - "reviewing a rename commit that touches only the declaration site, not every place the old name was used as a machine-readable key"
  - "a netclass, classifier, or rule-generator table is keyed by name string rather than resolved against the live netlist"
  - "auditing a lookup table for stale entries and tempted to treat every 'name absent from the netlist' row as the same kind of problem"
tags:
  - rename-drift
  - orphaned-classification
  - netclass-assignment
  - stale-key-audit
  - fail-open
  - net-naming
---

# A rename fixes the name and orphans every key derived from it

## Context

`elec/src/main.ato`'s `+340V_BUS` net was renamed to `+170V_BUS` earlier on
2026-07-26 as part of the voltage-doubler correction documented in
`docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`:
the topology is ±170V about a grounded midpoint (340V differential), and the
old name described the differential while reading as a rail voltage — a
misreading that had already caused OVP-01 to be re-tuned as a permanent
fail-open, because the net's *name* was trusted over its actual topology.

**The rename fixed the name and broke a second, independent thing: every
machine-readable key derived from the old string.** Commit `688c15bb`
found `TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py:421`) still
classified `"+340V_BUS": "HighVoltage"` — a key with **0 occurrences** in
`elec/build/default.net` — while the real rail, `+170V_BUS`, carried **12
pads** in `pcb/temper.kicad_pcb` and resolved to **no netclass at all**.
Every generated DRC rule conditioned on `NetClass == 'HighVoltage'` was
therefore inert for the board's main high-voltage bus, silently, for as long
as the classification table lagged the rename.

**The same rename orphaned a second, independent lookup, in a different
file, discovered separately the same day.**
`docs/evidence/2026-07-28-drc-courtyard-condition-fix.md` §3b found that the
DRC rule generator's own `netclass_assignments` table still references the
retired names `DC_BUS+`/`SWITCH_NODE`, and its `netclass_patterns` wildcard
`DC_BUS*` does not match either `+170V_BUS` or `SW_NODE` — so the two TO-247
IGBTs (`U5`, `U6`) that Rule 5/7's own comment names as the reason those
rules exist are *also* unclassified into `HighVoltage` today, for the exact
same rename, resolved in the exact same "did the string change propagate to
every place that keys on it" sense, in a codebase location that has nothing
to do with `design_rules.py`. One rename, two independent orphaned keys,
found by two different sessions auditing two different files.

**The audit that found the fix also drew a distinction worth keeping
separate: "stale" is not "broken."** Auditing all 38 entries in
`TEMPER_NET_ASSIGNMENTS`, 11 name nets absent from the compiled netlist. Ten
of those eleven are harmless legacy aliases whose live counterparts are
already assigned separately under a different-cased or differently-suffixed
name — `AC_L` beside `ac_l`, `GATE_H` beside `GATE_HS`, `PWM_L` beside
`PWM_LS` — kept deliberately, the same way the fix itself kept the old
`"+340V_BUS"` key rather than deleting it, so historical boards that still
use the old name keep resolving. **`"+340V_BUS"` was the only one of the
eleven whose live counterpart was *missing* from the table entirely** — no
`+170V_BUS` key existed anywhere before this fix. That is why this was one
real defect, not eleven: ten rows answer "is this name still used," one row
answers "does the net this name used to point at still have a
classification under any name," and only the second question was unanswered.

## The pattern

**A rename is two edits, not one: the declaration, and every derived key.**
Fixing the name at its declaration site (`main.ato`'s `override_net_name`)
is necessary and was done correctly on 2026-07-26. It is not sufficient,
because every other file that keys off the *string* — a Python dict, a YAML
wildcard, a generated rule's condition — has no mechanism connecting it to
the declaration. The rename is invisible to those files until something
re-derives the mapping and notices the string it expects no longer appears
anywhere real.

This is a sharper, structural cousin of `net-name-is-a-claim-not-an-authority`:
that lesson was about a *human* trusting a name over a topology. This one is
about a *machine-readable table* trusting a name over a live netlist, and the
failure mode is identical in shape (silent, plausible-looking, no crash) even
though the reader is code instead of a person. The rename didn't reintroduce
the first bug — it introduced a new one, in a place the first fix never
touched, because nothing enumerates "every place this string is a key" when
a rename lands.

**Not every stale-looking row in the same table is the same finding.** An
audit that stops at "11 of 38 entries name absent nets" and reports that
number as the defect count overstates the problem by 10x. The discriminating
question is not "is the name in the netlist" but "does the *net this name
used to mean* have a live classification under some name" — ten rows pass
that test via an already-assigned alias; one did not.

## Guidance

1. **When renaming a net, signal, or any identifier used as a lookup key,
   grep for the old string across every classification table, wildcard
   pattern, and generated-rule config in the repo — not just the
   declaration site.** `design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` and the
   DRC generator's `netclass_assignments`/`netclass_patterns` are two
   independent tables that both key off net name strings; a rename that
   touches one and not the other leaves the second silently broken with no
   error anywhere.
2. **A classification table keyed by string name is a standing liability
   independent of any one rename** — prefer resolving classification against
   the live netlist (net exists → has copper → gets a class) over a
   maintained name→class dict that can drift out of sync with every rename,
   split, or merge the net ever undergoes.
3. **When auditing a lookup table for staleness, distinguish "the name is
   gone" from "the net is unclassified."** A dead alias with a live
   counterpart assigned separately is harmless noise; a name whose live
   counterpart has *no* assignment anywhere is the actual defect. Counting
   both the same way inflates the finding by an order of magnitude and
   buries the one row that matters among ten that don't.
4. **Keep the retired key rather than deleting it, but add the new one.**
   The fix here did not remove `"+340V_BUS"` — an old board revision or a
   stale netlist snapshot might still use it — it added `"+170V_BUS"`
   alongside it, following the same alias convention the other ten harmless
   entries already established. A rename fix that only adds forward
   compatibility, never dropping backward compatibility, is strictly safer.
5. **Treat a rename to a net that any safety-relevant netclass depends on as
   a two-file change minimum**, and verify both files against the compiled
   netlist afterward (`grep -c` the old and new name in
   `elec/build/default.net`, confirm the new name resolves to a real
   netclass), not just against each other.

## Why This Matters

The main HV bus went from "misnamed in a way that fooled a human into a
fail-open OVP" to "correctly named, and invisible to every DRC rule that
exists to protect exactly this bus" — in the same net, across two
consecutive fixes, by two different mechanisms. Neither failure was caused
by carelessness in the fix that preceded it: the OVP fix correctly traced
the topology and renamed the net; the netclass fix correctly found the
orphaned key. Each fix was locally correct and left the net one classification
step away from being fully protected again, because a rename's blast radius
— every derived key, in every file, machine-readable or not — is not
visible from the declaration site alone. The 11-of-38 audit distinction
matters for the same reason: a team that reports "11 stale entries" without
separating aliases from orphans either burns time re-verifying ten harmless
rows or, worse, misses that exactly one of them was the entire defect.

## When to Apply

- Before merging any net/signal rename, grep every classification table,
  netclass config, and generated-rule file for the old string — not just
  the file where the rename was made.
- When auditing a name→classification table for drift, sort findings into
  "dead alias with a live counterpart already assigned" versus "net with no
  live classification anywhere," and report the counts separately.
- When two independent sessions find the same net's classification broken
  in two different files on the same day, treat it as one root cause (the
  rename) with two blast-radius sites, not two unrelated defects.
- Before trusting any DRC/gate rule conditioned on `NetClass == 'X'`, verify
  the net it's meant to protect actually resolves to that class today, not
  just that the rule's condition parses.

## Examples

```python
# packages/temper-placer/src/temper_placer/core/design_rules.py:421-445
TEMPER_NET_ASSIGNMENTS = {
    ...
    # HighVoltage - DC bus
    #
    # FIXED 2026-07-28: "+340V_BUS" was the ONLY HighVoltage entry with no
    # live counterpart in the netlist, and the rail it named carries 12 pads
    # on the board under its current name (+170V_BUS). The net was renamed
    # +340V_BUS -> +170V_BUS on 2026-07-26; the rename fixed the name and
    # orphaned this classification, so the main HV rail belonged to NO
    # netclass and every generated DRC rule conditioned on
    # NetClass == 'HighVoltage' was inert for it.
    "+170V_BUS": "HighVoltage",   # <- added; this is the fix
    "+340V_BUS": "HighVoltage",   # <- kept deliberately, like AC_L/GATE_H below
    "DC_BUS_RTN": "HighVoltage",
    ...
}
```

```
# The same rename, orphaning a second, independent key, found the same day:
# docs/evidence/2026-07-28-drc-courtyard-condition-fix.md §3b
netclass_assignments: {..., "DC_BUS+": "HighVoltage", "SWITCH_NODE": ...}  # retired names
netclass_patterns:    {"DC_BUS*": "HighVoltage"}   # does not match +170V_BUS or SW_NODE
board's real nets:    +170V_BUS, SW_NODE             # neither resolves to HighVoltage
```

```
# Audit discipline: "stale" vs "broken" are different claims
11 of 38 TEMPER_NET_ASSIGNMENTS entries name nets absent from default.net:
  10 -- dead alias, live counterpart already assigned (AC_L / ac_l, ...)  -- harmless
   1 -- "+340V_BUS", live counterpart (+170V_BUS) had NO assignment anywhere -- the defect
```

## Related

- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  — the first failure of this same net: a human trusting `+340V_BUS`'s name
  over its actual (half-bus) topology to re-tune OVP-01 into a fail-open. See
  that doc's 2026-07-28 update for this second failure's summary.
- `docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md`
  — the sibling discipline for the general shape of a net-name-keyed
  classifier drifting from its own source of truth.
- `docs/solutions/best-practices/a-rule-that-matches-nothing-reads-as-coverage-2026-07-28.md`
  — the same day's independent finding that, even where a net *is*
  correctly classified, the rule condition meant to consume that
  classification can itself silently fail to bind.
- `packages/temper-placer/src/temper_placer/core/design_rules.py:421-445` —
  the fixed table, with the full clause chain in the surrounding comment.
- `docs/evidence/2026-07-28-drc-courtyard-condition-fix.md` §3b — the
  independent, same-day discovery of the second orphaned key in the DRC
  rule generator's own netclass tables.
- Commit `688c15bb` — the fix, its audit of all 38 `TEMPER_NET_ASSIGNMENTS`
  entries, and the stale-vs-broken accounting.
