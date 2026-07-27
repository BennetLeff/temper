---
title: "A net name is a claim, not an authority — OVP-01 was re-tuned from '+340V_BUS' on a node that never exceeds 170V"
date: "2026-07-26"
category: best-practices
module: pcb-hardware-design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "deriving a trip point, gain, or threshold from a net's declared name or override_net_name rather than tracing its actual topology"
  - "two comments or declarations in the same file disagree about what a node is, and one of them is a net name"
  - "a design change is justified by a value that already has a machine-checked assertion elsewhere in the source"
  - "reviewing a protection-circuit fix and the 'bug' it was fixed against has no reproduction, only a name-based inference"
tags:
  - net-naming
  - override-net-name
  - fail-open
  - assertion-over-prose
  - ovp
  - voltage-doubler
  - half-bus
  - self-contradicting-source
---

# A net name is a claim, not an authority

## Context

`elec/src/main.ato:94-95` declares:

```
signal dc_bus_plus  # +340V
dc_bus_plus.override_net_name = "+340V_BUS"
```

**That node is the +170 V half-bus, not the full 340 V bus.** The same file
contradicts its own name eight lines and 175 lines later:
`main.ato:270` (`aux_supply.power_in.vcc ~ dc_bus_plus`) is commented "Half-bus
input (~170VDC)" one line above the connection.

The truth was already machine-checked, one file over, the whole time.
`elec/src/modules.ato:684-685` connects `c_bus1` between `dc_bus.hv_plus` and
`dc_bus.gnd_ref` — the doubler midpoint, not system ground — and
`modules.ato:649` asserts `c_bus1.voltage_rating >= v_bus_half * 1.25`. A 250 V
part (`EKMQ251VSN182MA50S`) clears `170 × 1.25 = 212.5 V` and would fail
`340 × 1.25 = 425 V`. The assertion has been passing against the *half-bus*
value the entire time; only the net's own name, `+340V_BUS`, claimed
otherwise.

**Consequence:** OVP-01 (`OVPComparator`, `modules.ato:1619` onward) was
re-tuned reasoning from the net name, and the false reasoning is preserved
verbatim in the source at `modules.ato:1669-1677`:

> "Was 12k -> V_ref 1.50V -> trip at 195V. The divider senses the FULL bus
> (modules.ato: ovp.v_bus.line ~ dc_bus.line, and main.ato declares
> dc_bus_plus as +340V_BUS with v_bus_max = 340V), so at the 340V nominal bus
> the sense node sat at 2.615V against a 1.50V reference and the OVP fault
> asserted permanently. The cooker could not have run."

The "fix" changed `r_ref_top` to 1.1 kΩ, giving `V_ref = 2.973V` and a 1/130
divider that trips at **~400 V** (399.8 V, per the source's own comment at
line 1662) on a node that never exceeds **~170 V**. OVP-01 is now fail-open —
it cannot trip under any bus condition this design reaches. The *original*
12 kΩ / 1.50 V value gave a 195 V trip, exactly half of the spec's 390 V
(`FUNCTIONAL_TEST_CRITERIA.md`'s OVP-01 threshold), and was correct for the
half-bus node it actually senses. The bug it was "fixed" against — permanent
fault assertion at 340 V nominal — did not exist, because the bus never
reaches 340 V at that sense point.

This is a distinct failure from
`docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`,
which documents OVP-01's *hysteresis* being lost from a summary table the
same day (no hysteresis resistor at all, in an earlier revision of the same
comparator). Both incidents hit `OVPComparator` on 2026-07-26; neither caused
the other. That one is a lossy summary table causing an omitted feature; this
one is a self-contradicting net name causing a wrong threshold on a
correctly-featured circuit. A single gate accumulated two independent
documentation-shaped defects on the same day, from two different mechanisms.

## Guidance

1. **A net name — including `override_net_name` — is documentation, not a
   source of truth.** It can be wrong, stale, or aspirational in exactly the
   way a comment can, and nothing in the toolchain checks it against the
   node's actual topology. Trace the connection graph before deriving a
   voltage or current from what a signal is called.
2. **When a machine-checked assertion and a net name disagree, the assertion
   wins — but only if someone reads it.** `modules.ato:649`'s
   `c_bus1.voltage_rating >= v_bus_half * 1.25` was correct and passing the
   entire time the OVP fix was being reasoned about 1,000+ lines away, on the
   same half-bus node, using the wrong name for it. **Prefer assertions over
   prose for anything electrically load-bearing** — an assertion is checked
   every build; a comment is checked only when someone happens to read it,
   and a name is read even less critically than a comment because it looks
   like a label, not a claim.
3. **Before re-tuning a protection circuit's threshold, reproduce the failure
   it's being tuned against.** The OVP-01 fix's justification — "the OVP
   fault asserted permanently" at 340 V nominal — was never checked against
   simulation or the bus's actual range; it followed directly and only from
   trusting the net's declared name. State the falsifier
   (`docs/METHODOLOGY.md` §5): *this diagnosis is wrong if the sensed node's
   actual max voltage is not 340V* — a topology trace, not a name lookup,
   answers that in under a minute.
4. **A contradiction between two locations in the same file is a signal to
   stop and resolve it, not to pick whichever supports the change in
   progress.** `main.ato:94-95` and `main.ato:270` disagree about the same
   node 175 lines apart; the OVP-01 fix used the wrong one without ever
   surfacing the disagreement.
5. **This generalizes the physical-envelope rule to naming itself.**
   `docs/solutions/best-practices/physical-envelope-precondition-component-changes-2026-07-26.md`
   establishes that a part's physical/electrical envelope is a precondition
   to check before changing a value. A net's name is not part of that
   envelope and must not be substituted for tracing it — "the node called
   `+340V_BUS`" is not evidence about what voltage the node reaches.

## Why This Matters

OVP-01 is the induction cooker's over-voltage protection gate. A fail-open
protection circuit is worse than an absent one in exactly the way a smoke
detector with a dead battery is worse than no smoke detector: it looks present
on every review that doesn't independently derive the trip voltage, and
nobody escalates its absence because the BOM line, the schematic symbol, and
the fault-tree wiring are all real. The failure was entirely preventable with
information already in the repository — `modules.ato:649`'s assertion had
been asserting the correct physical fact the whole time. The gap was not
missing information; it was that a net's name outranked a passing, adjacent,
machine-checked assertion in the reasoning that produced the fix.

## When to Apply

- Before deriving any threshold, gain, or trip point from what a net or
  signal is *called* — trace its actual connections instead.
- Before trusting `override_net_name` (or any renaming construct) as a
  statement of electrical fact — it is a label applied by whoever wrote it,
  with no build-time check against the node's real voltage or current.
- When two locations in the same source file disagree about what a node is —
  treat this as a stop-and-resolve trigger, not a tie to break by preference.
- When "fixing" a protection circuit whose failure mode was inferred rather
  than reproduced — reproduce it first, from the actual topology.
- When reviewing any protection gate (`OCP-*`, `OVP-*`, `UVL-*`, `THM-*`) —
  check whether its threshold derivation cites a net name, a topology trace,
  or both; a name-only citation is the risk signal.

## Examples

```
# main.ato:94-95                          main.ato:270
signal dc_bus_plus  # +340V               aux_supply.power_in.vcc ~ dc_bus_plus
dc_bus_plus.override_net_name             # Half-bus input (~170VDC)
  = "+340V_BUS"
        ^^^^^^^^ says 340V                        ^^^^^^^^^^^^ says 170V, correctly

# modules.ato:649 -- the machine-checked fact, unaffected by either comment
assert c_bus1.voltage_rating >= v_bus_half * 1.25
# c_bus1 bridges hv_plus <-> gnd_ref (modules.ato:684-685), the doubler
# midpoint -- so v_bus_half IS this node's actual range. 250V clears
# 170*1.25=212.5V. It would fail 340*1.25=425V. This assertion is the
# ground truth the OVP-01 fix should have traced to instead of the name.
```

```
# WRONG: threshold derived from the net's declared name
"dc_bus_plus is +340V_BUS" -> v_bus_max = 340V -> re-tune V_ref for 340V nominal
  -> trip point ~400V on a node that tops out at ~170V -> fail-open, can never fire

# RIGHT: threshold derived from traced topology
c_bus1.plus ~ dc_bus.hv_plus, c_bus1.minus ~ dc_bus.gnd_ref  (doubler midpoint)
  -> this node's range is v_bus_half (170V), confirmed by the passing
     `c_bus1.voltage_rating >= v_bus_half * 1.25` assertion
  -> original 12k/1.50V divider (trip 195V = half of 390V spec) was correct
```

## Related

- `docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`
  — the other independent defect that hit OVP-01 the same day (hysteresis
  dropped from a summary table); read together, they show one gate absorbing
  two unrelated documentation-shaped failures in one session.
- `docs/solutions/best-practices/physical-envelope-precondition-component-changes-2026-07-26.md`
  — the sibling rule this extends: physical/electrical envelopes are
  preconditions to trace, not infer from a name or a familiar topology.
- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — a different OVP-01-adjacent lesson from the same day's work: measurement
  provenance, rather than naming, as the trust boundary.
- `elec/src/main.ato:94-95, 270` — the self-contradicting net declaration and
  comment.
- `elec/src/modules.ato:649, 684-685, 1662-1677` — the passing assertion, the
  actual connection, and the false reasoning preserved verbatim.
