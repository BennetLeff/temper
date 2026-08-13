# OVP-01 divider mid-chain nodes: single-fault voltage, why they cannot be domain-declared, and the netclass fix applied instead

<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=false (worktree /home/bennet/Desktop/temper-hv4-review, branch agent/hv4-mid-chain-review, base origin/fix/board-schematic-resync) -->

**Date:** 2026-08-13

**Subject:** the four nets PR #1164 left "deliberately unclassified" as genuinely
mid-chain protective-impedance-divider nodes: `safety.ovp.r_div_top1-p2`,
`safety.ovp.r_div_top2-p2`, `safety.ovp.r_adc_top1-p2`,
`safety.ovp.r_adc_top2-p2`. All four currently resolve to the `Default`
netclass (`creepage_mm = 0.0`, `clearance = 0.15mm` — no creepage
enforcement at all), confirmed live in this pass:
`create_temper_design_rules().get_class_for_net(...)` returns `'Default'`
for all four, against a fresh `make netlist` build (digest `8cfd715e60a3…`,
same digest PR #1164 recorded).

## 1. The precedent, and whether it was ever justified

`elec/domain_manifest.yaml`'s comment block for these nodes (currently
lines 346-352, unchanged since it was written) reads:

> The chain's own interior nodes upstream of this one (r_div_top1-p2,
> r_div_top2-p2, sitting at ~57-114V per the same arithmetic) are NOT
> added here — they are genuinely mid-chain, neither HV nor SELV by
> voltage, and remain deliberately unclassified; see
> 2026-07-27-domain-classification-coverage.md.

`git blame`/`git log -S "deliberately unclassified"` trace this to commit
`70503e6dc` (2026-07-27, "fix(safety): close domain-clearance coverage gap,
fail closed on unclassified-near-HV"), whose own cited evidence doc
(`docs/evidence/2026-07-27-domain-classification-coverage.md`, same commit
as its `provenance` stamp) states the actual reasoning:

> Deliberately NOT closed: the divider chains' own purely-interior nodes
> … sit at genuinely intermediate voltage … neither HV nor SELV by
> voltage, and forcing either label would be exactly the naming-convention
> guess the manifest's ground rule forbids. Left unclassified, with the
> fail-closed proximity check (Sec 6) as the safety net for that decision.

**This reasoning does not hold up, and it is worth being precise about
why.** The manifest's "ground rule" it invokes ("never infer domain from
how a net is spelled — never a pattern, prefix, or naming-convention
guess") is about **inferring domain from net-name text**. Voltage is not
text: it is derivable, and the same document derives it (57-114V) two
sentences earlier. Declining to classify a net whose voltage IS known,
on the grounds that assigning it a label would be "a naming-convention
guess," conflates two different questions — "what does this net's name
suggest" (correctly forbidden) and "what domain does this net's
electrical behavior actually belong to" (not attempted here, even though
the arithmetic to answer it was already on the page). That confusion is
real and independent of the finding in Sec 2/3 below.

**However** — and this is the part neither the precedent commit nor PR
#1164 checked — there turns out to be a second, genuine reason these nodes
resist a `domains:` declaration, one that has nothing to do with "naming
guess" reasoning and everything to do with how
`scripts/check_domain_partition.py` models a protective-impedance chain.
That reason is real, was verified empirically in this pass (Sec 3), and is
the actual, defensible justification the existing precedent should have
given but did not.

The 2026-07-26 divider-integrity work itself
(`docs/evidence/2026-07-26-ovp-crossing-resolution.md`, re-verified
2026-07-30) **is** independently substantiated — its arithmetic, resistor
ratings, and the single-fault analysis of the chain's own construction
(does the chain survive one resistor failing, for the FAR-end node's own
touch-current budget) were re-derived and confirmed correct. What neither
that document, the 2026-07-27 coverage doc, nor PR #1164 ever computed is
the question this document answers: **not "is the far end (`comp.INP`,
`adc_v_bus`) safe under a single fault" (already answered: yes) but "what
voltage appears at the chain's own INTERIOR nodes under that same fault."**

## 2. Independent re-derivation: interior-node voltage, normal and single-fault

Topology, read directly from `elec/src/modules.ato:2204-2275` (comparator
divider) and `:2361-2404` (ADC-sense divider) this pass:

```
v_bus.line ~ r_div_top1.p1
r_div_top1.p2 ~ r_div_top2.p1      # net "safety.ovp.r_div_top1-p2"
r_div_top2.p2 ~ r_div_top3.p1      # net "safety.ovp.r_div_top2-p2"
r_div_top3.p2 ~ comp.INP
comp.INP ~ r_div_bot.p1
r_div_bot.p2 ~ power.gnd
```
(ADC-sense divider is the identical topology with `r_adc_top1-3`/`r_adc_bot`/`adc_v_bus`.)

`+170V_BUS` (`dc_bus_plus`) = 170V nominal, the half-bus (`elec/src/main.ato:511-520`,
already independently re-verified in the 2026-07-30 doc).

```python
V = 170.0
def divider(rtop, rbot, faulted_idx=None):
    r = list(rtop)
    if faulted_idx is not None:
        r[faulted_idx] = 0.0          # dead short -- Clause 8.1.4's own fault condition
    total = sum(r) + rbot
    I = V / total
    nodes, v = [], V
    for ri in r:
        v -= I * ri
        nodes.append(v)
    return I, nodes   # nodes = [top1-p2, top2-p2, top3-p2(=far end)]
```

**Comparator divider** (`r_div_top1-3` = 430k each, `r_div_bot` = 16.9k):

| Condition | I | `r_div_top1-p2` | `r_div_top2-p2` | far end (`comp.INP`) |
|---|---:|---:|---:|---:|
| Normal | 130.1µA | **114.1V** | **58.1V** | 2.20V |
| `r_div_top1` shorts | 193.9µA | **170.0V** | 86.6V | 3.28V |
| `r_div_top2` shorts | 193.9µA | 86.6V | 86.6V | 3.28V |
| `r_div_top3` shorts | 193.9µA | 86.6V | 3.3V | 3.28V |

**ADC-sense divider** (`r_adc_top1-3` = 169k each, `r_adc_bot` = 10k):

| Condition | I | `r_adc_top1-p2` | `r_adc_top2-p2` | far end (`adc_v_bus`) |
|---|---:|---:|---:|---:|
| Normal | 328.8µA | **114.4V** | **58.9V** | 3.29V |
| `r_adc_top1` shorts | 488.5µA | **170.0V** | 87.4V | 4.89V |
| `r_adc_top2` shorts | 488.5µA | 87.4V | 87.4V | 4.89V |
| `r_adc_top3` shorts | 488.5µA | 87.4V | 4.9V | 4.89V |

Every normal-condition figure matches PR #1164's own arithmetic exactly
(114.1/58.1V comparator, 114.4/58.9V ADC) — independently re-derived here,
not copied. The single-fault figures are new: **no existing document in
this repository computed them before this pass.**

**Governing single-fault case, per net (worst voltage over all three
top-resistor fault positions):**

| Net | Normal | Worst single-fault | Fault that produces it |
|---|---:|---:|---|
| `safety.ovp.r_div_top1-p2` | 114.1V | **170.0V — exactly `+170V_BUS`** | `r_div_top1` shorts |
| `safety.ovp.r_div_top2-p2` | 58.1V | **86.6V** | `r_div_top1` shorts |
| `safety.ovp.r_adc_top1-p2` | 114.4V | **170.0V — exactly `+170V_BUS`** | `r_adc_top1` shorts |
| `safety.ovp.r_adc_top2-p2` | 58.9V | **87.4V** | `r_adc_top1` shorts |

This is not a marginal excursion. A short of the top-side resistor nearest
the bus makes `r_div_top1-p2` / `r_adc_top1-p2` **galvanically identical to
`+170V_BUS`** — zero ohms away from it, at the exact bus potential, not an
approximation. `r_div_top2-p2` / `r_adc_top2-p2` reach 86.6-87.4V under the
same event — above the SELV ceiling this task cites (60V DC ripple-free /
42.4V AC peak, IEC 60335-1 cl. 27.1 / IEC 61140) by a comfortable margin,
even though their *normal* voltage (58.1-58.9V) sits just under it.

**Why this is the governing case, not an extra, optional analysis:**
IEC 60335-1 Clause 8.1.4's protective-impedance provision — the same clause
the manifest already leans on for both dividers — requires the
current-limiting function to survive "any ONE of the components" failing,
open or short (`docs/evidence/2026-07-30-ovp-crossing-resolution.md` §2,
independently re-confirmed against primary text by
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md`'s recovery of
the adjacent clauses). A top-resistor short is exactly the fault class the
manifest's own existing arithmetic already walks through for the far end's
touch-current budget (the "One top shorted" row of the comparator/ADC
divider tables) — this document applies the identical fault to the
interior nodes' own voltage, a computation the existing arithmetic never
performed because it was only tracking current (a scalar shared by the
whole series string), not the per-node voltage split the fault also moves.

## 3. Why these nodes cannot be added to `domain_manifest.yaml`'s `domains:` lists — verified, not assumed

Having established these four nodes sit above SELV under a foreseeable
single fault, the natural next step (and this task's default expectation)
is to declare the two `-top1-p2` nodes HV outright (170.0V under fault is
indistinguishable from the declared HV rail) and treat the two `-top2-p2`
nodes as a harder call. **This was tried and it breaks
`scripts/check_domain_partition.py`.** Tested directly, not inferred:

```
$ cp elec/domain_manifest.yaml /tmp/domain_manifest_test.yaml
# added all 4 nets under domains: HV: nets:
$ uv run --no-sync python scripts/check_domain_partition.py --manifest /tmp/domain_manifest_test.yaml
...
=== DOMAIN VIOLATIONS: 1 ===
  Domain 'HV' and domain 'SELV' are NOT disjoint (2 independent bridge(s) found):
    [1] 'safety.ovp.r_div_top2-p2' --[safety.ovp.r_div_top3 (R48)]--> 'safety.ovp.comp-inp'
    [2] 'safety.ovp.r_adc_top2-p2' --[safety.ovp.r_adc_top3 (R53)]--> 'V_BUS_SENSE'
FAILED -- 1 domain violation(s), ...
```

**Root cause, read from `scripts/check_domain_partition.py`'s own
`synthesize_chain_head_isolators`:** the gate's chain model treats only the
FIRST member of a declared `protective_impedance_chains` entry as a graph
isolator (deliberately — the docstring records that declaring every chain
member as an isolator "caused false isolator-barrier violations in
practice"). Every node downstream of that first resistor — `top1-p2`,
`top2-p2`, and the already-declared-SELV far end (`comp.INP` /
`V_BUS_SENSE`) alike — is therefore modeled as ONE connected component for
`check_domain_disjointness`'s purposes. That is a *correct* model of a
*true* fact: under normal operation, all four nodes ARE resistively
continuous with the verified-SELV far end, with no isolator between them.
Declaring `top1-p2` or `top2-p2` "HV" in the same `domains:` dictionary
that also declares `comp.INP`/`V_BUS_SENSE` "SELV" asserts that two nets in
the *same* connected component belong to *different* domains — exactly the
contradiction `check_domain_disjointness` exists to catch, and it catches
it correctly here. This is not "more violations to report honestly" in the
sense PR #1164's 7 new HV declarations were (those made 0→7 *new*,
previously-invisible, real violations appear in a *different*, unrelated
gate); this is the gate's core invariant failing against a manifest entry
that would make an internally inconsistent claim about the SAME piece of
topology it already, correctly, certifies as SELV at the far end.

**Consequence:** the topology axis (`domain_manifest.yaml`'s `domains:
HV/SELV`, feeding `check_domain_partition.py` and
`measure_cross_domain_creepage.py`) cannot represent "this node is
galvanically continuous with a verified-SELV endpoint under normal
operation, but rises above SELV under a single top-resistor fault." That
is a real, previously-undocumented gap in what the two-domain model can
express — not a defect in the gate (which correctly protects the far end's
SELV classification), and not a case of "just pick the conservative
label" (the conservative label is exactly what the gate rejects, for the
reason above).

## 4. What this task does instead: an existing, decoupled netclass, not a new value

`elec/domain_manifest.yaml`'s `domains:` dictionary is **not** the only
mechanism that assigns a net a real (non-`Default`) netclass.
`TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`) is a
separate, independently-consulted table — `scripts/check_hv_netclass_coverage.py`'s
own PROPERTIES 1/3/4 all iterate `elec/domain_manifest.yaml`'s HV/SELV
lists and check whether a matching `TEMPER_NET_ASSIGNMENTS`/`kicad_pro`
entry exists; none of them check the reverse direction. A net can
therefore carry a `TEMPER_NET_ASSIGNMENTS` entry with **no**
`domain_manifest.yaml` declaration at all, invisible to (and not flagged
by) `check_domain_partition.py` or `check_hv_netclass_coverage.py`,
confirmed by re-running both gates after the change (Sec 5).

This PR assigns all four nets `"HighVoltage"` in `TEMPER_NET_ASSIGNMENTS`
— **an existing class, reusing its existing `creepage_mm=6.0` /
`clearance=2.0` values**, not a new DRU threshold or a hand-derived
number (both are placed off-limits by this task's hard constraints).
This is deliberately conservative, not precisely tuned: per
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md`'s recovered
IEC 60335-1 Table 18 (functional insulation, material group IIIa/IIIb),
the interior nodes' own true working-voltage bands would call for smaller
figures than `HighVoltage`'s 6.0mm —

| Voltage band | Table 18 PD2 | Table 18 PD3 |
|---|---:|---:|
| >50 and ≤125V (covers `-top2-p2`'s 58.1-87.4V) | 1.4mm | 2.2mm |
| >125 and ≤250V (covers `-top1-p2`'s 114.1-170.0V) | 2.0mm | 3.2mm |

(Whether Table 17 basic insulation — 1.5/2.4mm and 2.5/4.0mm respectively —
or Table 18 functional insulation is the correct table for THIS pairing
[interior divider node vs. an unrelated nearby LV/SELV component, not the
divider's own end-to-end insulation function] is not resolved here; both
are cited so a future reader has the range regardless of which table
applies.) A purpose-built netclass at the correct row is the more
surgically correct fix and is named as a follow-up (Sec 6), not
implemented here — inventing that number is exactly what this task's hard
constraints (`Do NOT edit ... any DRU threshold, or any clearance/creepage
value`) forbid a single pass from doing unilaterally. `HighVoltage`'s
existing 6.0mm is a safe over-provision in the interim, not a claim that
6.0mm is the precisely correct figure.

## 5. Gates re-run after the change

```
$ make netlist                                  # digest 8cfd715e60a3…, unchanged from PR #1164
$ uv run --no-sync python scripts/check_stale_extensions.py     # 10/10 fresh
$ uv run --no-sync python scripts/check_domain_partition.py
Checked 51 declared nets ... PASSED -- 0 domain crossings, 0 isolator-barrier breaches,
  0 protective-impedance chain defects, 0 board-interface contract violations
  # unchanged: this PR does not touch elec/domain_manifest.yaml's domains: dict
$ uv run --no-sync python scripts/check_hv_netclass_coverage.py
  HV netclass coverage gate passed          # unchanged -- these 4 nets carry no
                                             # domain_manifest.yaml HV declaration,
                                             # so PROPERTY 1/3 never iterate them
$ uv run --no-sync python scripts/measure_cross_domain_creepage.py
  HV=89/SELV=223 pads, 19847 pairs, 14 violations   # unchanged -- this tool also
                                                     # reads domain_manifest.yaml's
                                                     # domains: dict directly, which
                                                     # this PR does not touch
```

**Honest delta:** `TEMPER_NET_ASSIGNMENTS` now maps all four nets away
from `Default` for every Python-side (CP-SAT placer, router_v6) clearance
decision. `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` —
the mapping the real `kicad-cli` DRC engine reads — is **not** touched
here (matching PR #1145/#1164's own precedent of leaving that wire-up as
a named follow-up rather than doing it inline); the real board's DRC
creepage enforcement for these four nets is unchanged by this PR alone.
`pcb/temper.kicad_pcb` is untouched; no DRU threshold, clearance value, or
creepage value was created or modified — `HighVoltage`'s existing figures
were reused, not edited.

## 6. Follow-ups named, not fixed here

1. **`pcb/temper.kicad_pro` `netclass_assignments`** for these 4 nets (and
   PR #1164's own 7, and the `PWR_RTN`-shaped gap `check_hv_netclass_coverage.py`
   already tracks) — the actual wiring the real `kicad-cli` DRC engine
   needs. A single follow-up PR doing all of these together is more
   coherent than three separate ones touching the same file.
2. **A purpose-built netclass for protective-impedance mid-chain nodes**,
   sized to the correct IEC 60335-1 Table 17/18 row for their real working
   voltage (Sec 4) instead of borrowing `HighVoltage`'s 6.0mm wholesale —
   mirrors this project's own `HighVoltageTank` precedent (added
   2026-08-12 specifically because one class could not correctly represent
   two working-voltage bands landing in different table rows). Needs a
   certification-engineer or primary-standards-text call on (a) whether
   Table 17 (basic) or Table 18 (functional) governs a mid-chain node's
   spacing to an unrelated nearby SELV/LV component, and (b) confirmation
   that `HighVoltage`'s 2.0mm clearance is not itself under-derived for
   this specific voltage band (out of scope here; not re-examined).
3. **The precedent's stated reasoning** ("forcing either label would be a
   naming-convention guess," Sec 1) should be corrected wherever it is
   repeated — it is not the actual reason these nodes resist
   classification; Sec 3's topology conflict is.
