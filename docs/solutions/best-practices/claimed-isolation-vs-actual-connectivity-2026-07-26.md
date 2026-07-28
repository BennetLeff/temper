---
title: "Claimed isolation versus actual connectivity — every check validated one representation against itself, none crossed the isolation barrier"
date: "2026-07-26"
category: best-practices
module: pcb-hardware-design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a design claims galvanic isolation, a SELV domain, or a star-point ground join between two power domains"
  - "reviewing whether a docstring's isolation claim ('separated from AC mains potential') matches the actual net graph"
  - "netlist validation, BOM reconciliation, and ERC all pass on a design with an isolation requirement"
  - "a single node is referred to by two different domain-scoped names (power_return vs. gnd) that get tied together somewhere"
tags:
  - isolation-barrier
  - star-point-ground
  - cross-domain-validation
  - selv
  - single-representation-blindness
  - rtd-sensing
  - domain-partition-check
---

# Claimed isolation versus actual connectivity

## Context

`elec/src/main.ato:271` and `:273`:

```
aux_supply.power_in.gnd ~ power_return   # Referenced to doubler midpoint
aux_supply.power_out.gnd ~ gnd           # SELV ground
```

These read as two different nets on two sides of an isolation barrier. They
are the same net: `main.ato:299` joins them —

```
power_return ~ gnd  # Single-star-point ground join near doubler caps
```

— and that node is **AC Neutral** (via the CMC winding: `modules.ato:690-691`,
`ac_n ~ cmc.W2_1` then `cmc.W2_2 ~ dc_bus.gnd_ref`, which is `power_return`'s
source). The isolated auxiliary supply's 4.2 kVAC-rated barrier (IRM-10-15,
`modules.ato:1159`)
is shorted across by a ground join whose own comment calls it a
"single-point star join." The user-touchable RTD food probe rides on this
node while `RTDSensing`'s own docstring
(`elec/src/modules.ato:1330-1339`) claims:

> "the RTD probe and MAX31865 are on the SELV side — galvanically isolated
> from the HV power domain by the auxiliary supply transformer. The
> user-touchable RTD food probe is therefore separated from AC mains
> potential."

The docstring and the net graph disagree about the same three components.

**Invisible to every existing check.** Netlist valid. BOM reconciled against
source at 155 components. ERC passed. The schematic is internally
self-consistent. None of these caught it, and the reason is the same for all
of them: **every check in the project validated one representation against
itself — the netlist against the netlist's own connectivity rules, the BOM
against the source's component list, the schematic against its own
symbol/pin conventions. None of them crossed two representations** (the
declared isolation topology vs. the actual net graph; the docstring's safety
claim vs. the wiring that determines whether it's true).

A star-point join is a legitimate technique for tying multiple ground
references together *within* one electrical domain — it is exactly how you'd
join, say, three different SELV return paths that should share a reference.
Applied *across* a domain a transformer is supposed to isolate, the same
technique is simply a short. The construct that is correct in one context is
a safety defect in the adjacent one, and nothing about its syntax changes
between the two.

## Guidance

1. **A claimed isolation boundary needs a check that crosses it, not just
   checks that each side is internally consistent.** Netlist validity, ERC,
   and BOM reconciliation are all single-representation checks by
   construction — they ask "is this artifact self-consistent," never "does
   this artifact's claim match a different artifact's claim about the same
   physical fact." An isolation claim requires a graph-reachability check:
   trace every net that should be electrically distinct and assert no path
   connects them outside the isolating component itself.
2. **A docstring asserting isolation ("separated from AC mains potential") is
   a testable claim, not a design note.** Where it's testable — as here, by
   graph reachability from the named node to the AC mains net — it should be
   asserted at build time, not left as prose that can silently diverge from
   the wiring it describes. This is the same discipline as
   `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`,
   applied to a safety-boundary claim instead of a threshold derivation.
3. **A star-point ground join is domain-scoped.** Before adding one, name
   which single electrical domain it operates within, and verify every net
   it joins is already inside that domain. If any of the nets being joined
   sits on the far side of an isolation component (transformer, opto,
   isolated gate driver) from the others, the join is not consolidating
   references — it is bridging the isolation.
4. **When two names refer to the same physical node from two different
   domains** (`power_return` on the SELV/aux-supply side, `gnd` on the
   digital/control side, joined by one line), that join is exactly the point
   where a domain-partition check needs to run, because it is exactly where
   a human is most likely to read the two names as evidence of separation
   rather than as two labels for one wire.
5. **Passing single-domain checks are not evidence an isolation claim
   holds.** 155/155 BOM reconciliation, a clean ERC, and a valid netlist are
   all necessary and were all satisfied here; none of them are sufficient,
   because none of them ask the cross-domain question. Do not let a stack of
   passing single-representation checks stand in for the one check that
   would have caught this.

## Where this is being mechanized

A **netlist domain-partition check** is in flight: given a declared set of
electrically-isolated domains (HV, SELV/control, chassis/PE) and the
components that are supposed to isolate them, it should walk the net graph
and fail if any two nodes in different domains are connected by anything
other than a named isolating component. This incident is the motivating case
for that gate — the star-point join at `main.ato:299` is exactly the shape of
violation it is designed to catch, and the RTD docstring's claim is exactly
the kind of prose assertion it would make redundant by making the underlying
fact machine-checked.

**Update, 2026-07-27:** this gate shipped as `scripts/check_domain_partition.py`
and is now the reference example a same-day gate audit measures every other
gate against, specifically because it prints its own coverage ratio
("Checked N declared nets ... over M compiled nets / K components") on every
run, pass or fail, and fails closed on an empty domain declaration rather
than passing vacuously. See
`docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` — the
same audit also found the *other* half of this incident's lesson recurring
one layer over: the separate IEC 60335 clearance/creepage path was, at the
time, still running against a second, hand-maintained 10-net classification
that had drifted from this gate's own 39-net manifest, invisible to
`check_domain_partition.py` itself because it is a different check entirely.

## Why This Matters

This is not a hypothetical safety gap: a 4.2 kVAC-rated barrier is shorted,
and a user-touchable food-contact probe sits on AC Neutral instead of the SELV
reference its own documentation claims. The failure survived a netlist
validity check, a full BOM reconciliation, and ERC — three checks that,
between them, cover most of what a schematic review process typically relies
on to say "the design is sound." All three were legitimately green. The
lesson is not that those checks are bad; it's that none of them was ever
designed to answer the specific question an isolation claim asks, and a
design can accumulate arbitrarily many internally-consistent, individually
correct checks without ever gaining the one check that looks *across* two
of them.

## When to Apply

- Reviewing any design with a claimed galvanic isolation boundary, SELV
  domain, or safety-isolated interface — ask what check, specifically, would
  fail if that boundary were bridged, and confirm it exists and runs.
- Before adding a ground/reference join between two nets that originate on
  different sides of an isolating component.
- When a module's docstring makes a safety claim ("isolated from," "separated
  from," "cannot exceed") — treat it as a specification for a check, not a
  substitute for one.
- After any change that renames or re-routes a reference node — re-verify
  which domain it's actually in, not which domain its name implies.
- When a stack of passing checks (netlist, ERC, BOM) is being used as
  evidence a design is safe — confirm at least one of them actually crosses
  the specific boundary the safety claim depends on.

## Examples

```
# elec/src/main.ato:271, 273, 299
aux_supply.power_in.gnd ~ power_return   # looks HV-side-referenced
aux_supply.power_out.gnd ~ gnd           # looks SELV-side-referenced
...
power_return ~ gnd   # <- this line makes the two identical

# Net graph reality: power_return traces to AC Neutral via the CMC winding.
# gnd is the control/SELV reference the RTD sits on.
# The join above puts the RTD's reference at AC Neutral, contradicting
# RTDSensing's own docstring at modules.ato:1330-1339.
```

```
# The check this incident argues for (sketch)
domains = {
  "HV":  {"ac_l", "ac_n", "dc_bus_plus", "dc_bus_minus", "power_return", ...},
  "SELV": {"gnd", "vcc_3v3", "vcc_15v", "rtd_sense_p", "rtd_sense_n", ...},
}
isolating_components = {"aux_supply": ("HV", "SELV")}  # the ONLY allowed bridge

for net_a, net_b in all_directly_connected_net_pairs():
    if domain_of(net_a) != domain_of(net_b) and not via_isolating_component(net_a, net_b):
        fail(f"{net_a} <-> {net_b} bridges {domain_of(net_a)}/{domain_of(net_b)} "
             f"without an isolating component")
```

## Related

- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  — same class of failure (a naming/documentation claim outranking the actual
  net graph in someone's reasoning), applied to a threshold instead of a
  safety boundary.
- `docs/solutions/best-practices/physical-envelope-precondition-component-changes-2026-07-26.md`
  — a sibling "the arithmetic was right, the physical context was not
  checked" failure, one layer over: envelope survivability rather than
  domain separation.
- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md` —
  the CI-side taxonomy of checks that exist, run, and still can't catch their
  target defect; this incident is the hardware-side instance of the same
  shape, one check (an isolation/domain-partition gate) simply not existing
  yet rather than existing-but-neutered.
- `elec/src/main.ato:271, 273, 299` — the star-point join.
- `elec/src/modules.ato:1330-1339` — the `RTDSensing` docstring's isolation
  claim.
