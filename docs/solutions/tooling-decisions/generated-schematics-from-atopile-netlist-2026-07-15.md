---
title: "Auto-Generated KiCad Schematics from Atopile Netlist"
module: tooling
date: "2026-07-15"
problem_type: tooling_decision
component: tooling
severity: critical
applies_when:
  - "A single-source-of-truth netlist exists and hand-drawn schematics have accumulated safety-critical errors"
  - "Symbol availability is a bottleneck for new component additions"
  - "A project needs CI-verifiable schematic correctness with deterministic output"
symptoms:
  - "120+ unconnected pins in hand-drawn schematic"
  - "215 ERC violations across hierarchical sheets"
  - "Backward IGBT symbols with reversed pin assignments"
  - "Hand-repair sessions produce incorrect intermediate schematics"
root_cause: missing_tooling
resolution_type: tooling_addition
tags:
  - schematics
  - kicad
  - atopile
  - netlist
  - code-generation
  - deterministic
  - safety
  - electrical
---

# Auto-Generated KiCad Schematics from Atopile Netlist

## Context

The Temper project maintained two parallel descriptions of its circuit: `elec/src/*.ato` (atopile source) and `pcb/*.kicad_sch` (hand-drawn KiCad schematics). The atopile build produced a verified netlist (`elec/build/default.net`, 100 components, 135 nets, zero unconnected pins), but no pipeline step translated it into KiCad schematics. As a result, schematics were hand-transcribed and fell out of sync -- accumulating 120 unconnected pins, 215 ERC violations, and safety-critical layout bugs (backwards IGBTs, swapped comparator inputs, backwards mains rectifier diodes). Every review cycle required cross-referencing two independently maintained descriptions of the same circuit.

The root cause is documented in `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`. This document records the decision to close that gap by making schematics **derived output** from the atopile netlist.

## Guidance

**Treat schematics as derived output from the atopile netlist, not as a parallel artifact to be maintained by hand.**

### 1. Synthesize all symbols as box rectangles

Synthesize ALL symbols as simple rectangular boxes from netlist `libpart` pin counts. Even when a component has a local `.kicad_sym` file, use a synthesized box.

Why:
- Schematics are not a review artifact (design review happens in `.ato`). They exist only for netlist export to PCB sync.
- Box symbols are total over any new component -- no manual symbol-harvesting step is ever needed.
- Eliminates the symbol-mapping problem entirely: no MPN-to-symbol lookup, no library path resolution, no pin-name-to-number translation.

If readable schematics are needed later for manufacturing review, add harvested symbols as a cosmetic pass. Cosmetics must not gate pipeline correctness.

```python
# Symbol structure: rectangle body in _0_1, pins in _1_1
# Pin placement: bottom-to-top on both left and right sides
left_count = (pin_count + 1) // 2
for i in range(left_count):
    y = -(left_count - 1) * 5.08 / 2 + i * 5.08
    # pin at (-half_w - pin_length, y) for left side
for i in range(right_count):
    y = -(right_count - 1) * 5.08 / 2 + i * 5.08
    # pin at (+half_w + pin_length, y) for right side
```

### 2. Use pure label-per-pin connectivity (zero wires)

Every pin gets a net label at its endpoint. No wire segments. Hierarchical labels for inter-sheet nets. This eliminates the wire-geometry bug class that caused every historical safety bug.

```python
# Intra-sheet net: plain label
if net_name not in inter_sheet_nets:
    emit(label(net_name, pin_x, pin_y))

# Inter-sheet net: hierarchical label
else:
    emit(hierarchical_label(net_name, pin_x, pin_y))
```

### 3. The KiCad pin-numbering gotcha (bottom-to-top)

KiCad numbers pins **bottom-to-top** on each side of a symbol regardless of the `(number "N")` attribute. A label placed at the connection point for what the source says is "pin 1" will land on KiCad's notion of "pin 2" (and vice versa) if you assume top-to-bottom ordering. Both left and right side pins are affected.

**Fix**: Reverse the Y-index in label placement on both sides to pre-compensate:

```python
def pin_position(libpart, pin_num, symbol_x, symbol_y):
    pin_idx = index_of_pin(libpart, pin_num)
    left_count = (total_pins + 1) // 2
    right_count = total_pins - left_count

    if pin_idx < left_count:
        x = symbol_x - half_w - pin_length
        reversed_idx = left_count - 1 - pin_idx  # <-- compensate
        y = symbol_y - (left_count - 1) * 5.08 / 2 + reversed_idx * 5.08
    else:
        local_idx = pin_idx - left_count
        reversed_idx = right_count - 1 - local_idx  # <-- compensate
        x = symbol_x + half_w + pin_length
        y = symbol_y - (right_count - 1) * 5.08 / 2 + reversed_idx * 5.08

    return (x, y)
```

Without this compensation, the oracle will fail because net labels land on the wrong pins.

### 4. Build a connectivity-partition oracle

After generating, run `kicad-cli sch export netlist` and compare the connectivity partition against the source netlist. Compare `(ref, pin)` groups ignoring net names -- same set of pins per net = same connectivity.

```python
def oracle_verify(source_netlist, generated_sch_dir):
    # Export netlist from generated schematics via kicad-cli
    export_netlist(generated_sch_dir)

    # Build (ref, pin) -> net_name maps
    source = build_partition(source_netlist)     # {("U1","1"): "gnd", ...}
    gen    = build_partition(exported_netlist)    # {("U1","1"): "gnd", ...}

    # Compare groups, not names
    src_groups = {frozenset(pins) for pins in source.values()}
    gen_groups = {frozenset(pins) for pins in gen.values()}
    return src_groups == gen_groups
```

### 5. Deterministic UUIDs and grid layout

Derive stable UUIDs from atopile tstamps via SHA-256. Same input produces byte-identical output, making `git diff` meaningful and enabling CI regen-and-diff.

```python
def stable_uuid(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
```

Grid spacing must avoid pin coordinate collisions. With symbols 25.4mm wide plus 2.54mm pins, adjacent columns need >30.48mm spacing. A 40mm horizontal grid with 30mm vertical row spacing provides comfortable clearance.

### 6. No-connect markers

Pins not connected to any multi-node net (single-node nets or unlisted pads) get explicit `no_connect` markers. This keeps ERC output actionable rather than buried in noise.

## Why This Matters

- **Eliminates a whole class of safety bugs.** Hand-transcription from `.ato` to `.kicad_sch` produced the majority of production escapes in the Temper project. Generated schematics make the netlist the single source of truth.
- **Zero symbol-mapping drift.** Box symbols are universal; no component addition ever requires finding or drawing a KiCad symbol.
- **Wire-geometry bugs are impossible.** Label-per-pin with no wires means there is no geometry to get wrong.
- **The oracle makes correctness checkable, not aspirational.** CI can assert that generated schematics faithfully represent the netlist.
- **Deterministic output makes `git diff` meaningful.** Regenerating after a netlist change shows exactly what changed structurally.

## When to Apply

- Any project where KiCad schematics and an atopile (or equivalent) netlist coexist, and the netlist is the SSOT for connectivity
- Projects where symbol availability is a bottleneck
- Safety-critical or high-pin-count designs where manual transcription error is unacceptable
- **NOT** when schematics are authored interactively in KiCad's schematic editor as the primary design artifact

## Examples

### Before: Hand-Drawn Schematics (Anti-Pattern)

```
.ato source  --(human reads)-->  hand-drawn .kicad_sch
                                      |
                              120 unconnected pins
                              215 ERC violations
                              backward IGBTs
```

Every `.ato` change requires a human to replicate it in KiCad. Schematics drift silently.

### After: Generated Schematics (Pattern)

```
.ato source  -->  atopile netlist  -->  gen_schematics.py  -->  .kicad_sch
                                              |
                                         oracle verifies
                                         (ref, pin) groups
                                         match source netlist
                                              |
                                         ORACLE PASS: 346 pins,
                                         73 nets isomorphic
```

`.ato` change -> rebuild -> schematics update automatically. Oracle verifies correctness. No human touches KiCad's schematic editor.

### Project Results (Temper, 2026-07-15)

```
100 components, 135 nets, 31 unique libparts
6 generated sub-sheets + 1 root sheet
346 pin assignments across 73 multi-node nets
21 inter-sheet nets connected via hierarchical labels
38 pins marked no_connect
Deterministic: same input -> byte-identical output
```

## Related

- `scripts/gen_schematics.py` -- the implementation (~1000 lines)
- `scripts/real_board_inventory.py` -- reused `_sexp()` parser pattern
- `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md` -- root cause document this closes
- `docs/solutions/tooling-decisions/kicad-schematic-connectivity-tracer-2026-07-14.md` -- union-find verification primitive
- `docs/solutions/tooling-decisions/kicad-embedded-symbols-lose-pin-semantics-2026-07-14.md` -- pin-to-function recovery for embedded symbols
- `docs/solutions/architecture-patterns/x-macro-ssot-firmware.md` -- parallel codegen + CI drift-check pattern in firmware
- `docs/solutions/tooling-decisions/generated-safety-netlist-to-pcb-parity-gate-2026-07-13.md` -- downstream parity gate
