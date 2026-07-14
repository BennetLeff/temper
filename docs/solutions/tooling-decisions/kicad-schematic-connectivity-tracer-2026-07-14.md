---
title: A union-find connectivity tracer catches KiCad schematic shorts and gaps that visual inspection misses
date: "2026-07-14"
category: tooling-decisions
module: pcb-schematic-capture
problem_type: tooling_decision
component: tooling
severity: critical
applies_when:
  - "Hand-editing raw .kicad_sch S-expression wire/pin coordinates without KiCad's GUI"
  - "Auditing or repairing schematic wiring that was auto-generated or previously hand-edited"
  - "Adding many new wires to a busy sheet where accidental coordinate collisions are easy to introduce"
tags:
  - kicad
  - schematic
  - wire-tracing
  - union-find
  - self-verification
  - short-circuit-detection
---

# A union-find connectivity tracer catches KiCad schematic shorts and gaps that visual inspection misses

## Context

While repairing `pcb/*.kicad_sch` files for the Temper induction-cooker board, wiring had to be
added and corrected directly in the S-expression text (no visual KiCad session available). KiCad's
`kicad-cli sch export netlist` and `sch erc` confirm a file *parses*, but they do not cheaply
answer "does wire X actually reach pin Y, and does it accidentally also reach pin Z?" — ERC output
is verbose, sheet-scoped, and easy to misread at scale (300+ violations across a multi-sheet
design). Two real bugs were found this way that neither `kicad-cli` nor casual reading of the file
caught:

- `+3.3V` was wired directly to two GPIO pins on an ESP32 (a real short — would have damaged the
  MCU if powered as drawn).
- A gate driver's `RTD_CS` signal was wired to the MCU's `EN` (reset) pin instead of a GPIO.

Both were only found by treating "what net is this pin actually on" as a graph-reachability
question and computing it exactly, rather than eyeballing coordinates.

## Guidance

Build absolute pin positions for every placed symbol instance (`sym_pos + local_pin_offset`,
rotated by the symbol's placement angle — see the companion library-mapping doc for pin extraction
details), collect every `(wire (pts (xy x1 y1) (xy x2 y2)))` segment in the file, and run a
union-find (disjoint-set) over all wire endpoints plus every known pin/label coordinate. Any two
points that end up with the same root are electrically the same net — full stop, this is not a
heuristic.

```python
parent = {}
def find(p):
    parent.setdefault(p, p)
    while parent[p] != p:
        parent[p] = parent[parent[p]]
        p = parent[p]
    return p
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb

for p1, p2 in wires:
    union(p1, p2)

# group every tagged point (pin or hierarchical label) by its net root
nets = {}
for tag, pt in tagged_points.items():
    nets.setdefault(find(pt), []).append(tag)

# any group containing two DIFFERENT intended signals is a short
for root, members in nets.items():
    if len(members) > 1:
        print(members)   # inspect — is this the net you meant?
```

Use it twice per edit, not once:

1. **Before writing new wires**: generate the *proposed* wire set in isolation (not yet inserted
   into the file) and run the same union-find over just those new segments plus the pin/label
   points they're meant to join. Assert every intended group is fully connected AND that no two
   different intended groups share a root. This catches generator bugs — e.g. a leftover duplicate
   entry that pulls two different rails into the same list — before they ever touch the real file.
2. **After inserting into the file**: re-run the tracer against the saved file's actual wire text
   (not the in-memory generator state) and confirm the same invariants hold. This step exists
   because the insertion step itself can introduce bugs the pre-check can't see (arithmetic typos
   in a coordinate, a UUID collision, a copy-paste offset error).

When routing many new signals into a busy area (e.g. 12+ power-rail connections into one region),
give every signal its own **unique routing lane** — a distinct x (or y) coordinate for its
approach/exit segment that no other signal in the same batch ever reuses. KiCad connectivity is
determined by exact coincident points, not visual crossing, so two wires can cross on screen
without connecting — but two *collinear overlapping* segments on the same coordinate line **are**
electrically joined. A shared hub point is fine and intentional for signals that are supposed to
be the same net (e.g. all GND connections fanning into one hub); the risk is only when two signals
that should stay separate are accidentally routed through the same intermediate coordinate.

## Why This Matters

`kicad-cli sch erc` on a multi-sheet hierarchical design produces hundreds of violations, many of
them false-positive noise from checking each sheet in isolation (a signal declared correctly at
the root level will still show as "dangling" when ERC checks the child sheet alone). It is
practically impossible to eyeball-verify that a hand-written 60-wire batch has no accidental short
among it. The union-find check is O(n) and gives a yes/no answer with the exact offending points
listed — it converts "I re-read the coordinates and they look right" into a verified fact.

This also caught two bugs introduced by the fix process itself, not just pre-existing bugs in the
file: a script that generated a wire batch had one entry appended to the wrong rail group (an edit
that added a fix without removing the original wrong line), and a coordinate had a stray `+10.16`
offset copy-pasted from a neighboring pin's formula. Both were caught by the pre-insertion
self-check before they reached the file, at zero cost beyond running the same function twice.

## When to Apply

- Any time wire coordinates in a `.kicad_sch` file are being written or edited without a live
  KiCad session to visually confirm ratsnest/DRC feedback.
- Before trusting `kicad-cli sch export netlist`'s "exit 0" as proof of correct connectivity — it
  only proves the file parses, not that the intended nets are right.
- When auditing a schematic of unknown provenance (auto-generated, inherited from another
  engineer, or recovered from a broken state) for correctness before further edits.

## Examples

Real finding from this session (`pcb/mcu.kicad_sch`, before fix):

```
Label '+3.3V'     -> pins: ['IO5', 'IO12']     # SHORT: power rail on two GPIOs
Label 'SPI_MISO'  -> pins: ['IO5', 'IO12']     # same net as +3.3V above!
Label 'RTD_CS'    -> pins: ['EN']              # wired to the chip's reset pin, not a GPIO
```

After rewriting with unique per-signal lanes and re-tracing the saved file:

```
+3.3V     -> pins: ['3V3']
SPI_MISO  -> pins: ['IO12']
RTD_CS    -> pins: ['IO10']
```

Every signal maps to exactly one pin, and no two different labels share a root.

## Related
- `docs/solutions/tooling-decisions/kicad-embedded-symbols-lose-pin-semantics-2026-07-14.md` — how
  to get correct absolute pin *positions* to feed into this tracer when the schematic's own
  embedded symbol copy has lost semantic pin names.
- `docs/solutions/tooling-decisions/generated-safety-netlist-to-pcb-parity-gate-2026-07-13.md` —
  a related but distinct gate: that doc verifies the generated netlist matches the PCB at the
  component-inventory level; this doc verifies wire-level connectivity within a schematic sheet.
