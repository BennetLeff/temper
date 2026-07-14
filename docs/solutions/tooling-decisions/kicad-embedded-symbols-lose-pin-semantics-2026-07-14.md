---
title: "For flattened/embedded KiCad symbols with numeric-only pin names, the installed KiCad library (not a web-fetched datasheet) is the fastest reliable source of the real pin-to-function map"
date: "2026-07-14"
category: tooling-decisions
module: pcb-schematic-capture
problem_type: tooling_decision
component: tooling
severity: high
applies_when:
  - "A schematic's embedded lib_symbols block shows a multi-gate IC (logic gates, op-amps) with pins named only by number ('1', '2', '3') instead of semantic names ('1A', '1B', '1Y')"
  - "Wiring or auditing a multi-gate/multi-unit IC where it matters which physical pin belongs to which internal gate"
  - "WebFetch/WebSearch attempts to pull a datasheet pinout table keep returning summaries that say the pin diagram 'is not included in the text shown here'"
tags:
  - kicad
  - symbol-library
  - datasheet-verification
  - pin-mapping
  - 74xx
  - offline-first
---

# For flattened/embedded KiCad symbols with numeric-only pin names, the installed KiCad library (not a web-fetched datasheet) is the fastest reliable source of the real pin-to-function map

## Context

A schematic's fault-detection logic (a triple 3-input OR gate + quad NAND SR latch) needed exact
physical-pin-to-gate wiring to correctly implement a safety shutdown circuit. The schematic's own
embedded `lib_symbols` copy had been flattened into a single unit with pins literally named `"1"`,
`"2"`, `"3"` … — no `1A`/`1B`/`1Y` semantic labels, and no per-gate unit grouping. Several
WebFetch attempts against TI datasheet URLs and datasheet-aggregator sites (alldatasheet,
chipfind, radiolocman) all failed to surface the actual pin table — the tool summarizes page text
and pin diagrams are typically embedded as images inside the PDF, which don't convert to readable
text.

## Guidance

Before spending further budget on web fetches for a well-known part's pinout, check whether the
part is in a KiCad library already installed on the machine (true for anything routed through a
standard `lib_id` like `"74xx:74HC4075"` or `"Comparator:TLV3201"` — the *official* version of
that library, not the schematic's embedded/flattened copy, usually still exists on disk):

```bash
find / -iname "<library-name>.kicad_sym" 2>/dev/null | grep -v Trash
```

Official KiCad libraries represent multi-gate ICs as proper **multi-unit symbols** — one KiCad
"unit" per physical gate, each with its own pin numbers pulled directly from the datasheet. Parse
the target part's block and extract per-unit pin numbers:

```python
# after finding the symbol's start (string-aware paren-depth scan to get the full block):
for unit in re.finditer(r'\(symbol "(PARTNAME_\d+_\d+)"', block):
    ...  # each _N_1 unit is one physical gate; its (pin ...) entries list real pin numbers
```

If the exact part isn't in the library under its own name, check for a KiCad `(extends "OTHER")`
directive — many modern parts (e.g. `74HC00`) are defined as thin overrides of an older base part
(`74LS00`) that carries the actual pin/unit data. Also check sibling part families for
pin-compatible equivalents (a CMOS `4075` and an HC-family `HC4075` are frequently pin-identical
even under different KiCad library files, e.g. `4xxx.kicad_sym` vs `74xx.kicad_sym`).

**Cross-check the result against any generative/source-of-truth model in the repo, don't just
trust one source.** In this case the repo also had an Atopile component model
(`elec/src/components.ato`) with its own explicit pin assignments for the same parts. Comparing
the KiCad-library-derived mapping against it found: one part (`SN74HC00`) matched exactly, but the
other (`SN74HC4075`) had two gates' pin numbers wrong in the Atopile model relative to the real
datasheet-derived KiCad data. That's a real bug in the generative source, independent of anything
in the schematic — worth flagging as its own follow-up, not silently "fixed" as a side effect of
the schematic wiring task, and not something to have discovered at all without an independent
ground truth to diff against.

## Why This Matters

Guessing a multi-gate IC's pin-to-function mapping for a safety-critical circuit (a fault-latch,
in this case) risks wiring the wrong physical pins together — plausible-looking wiring that is
electrically wrong in a way that would only surface as "the shutdown latch doesn't actually latch"
during bench test, or not at all until a real fault occurs in the field. Repeated web-fetch
failures are a signal to change approach, not to lower the bar and guess from partial/remembered
information. The installed KiCad library is: (a) already on disk, no network dependency; (b)
structured with per-unit pin data instead of image-embedded diagrams; (c) itself sourced from
real datasheets by a large maintainer community, making it a credible independent source to
cross-check a repo's own generative model against.

## When to Apply

- Any time a schematic's embedded symbol copy has lost per-gate/per-unit pin semantics (numeric
  pin names only) and the task requires knowing which physical pin does what.
- Before spending multiple WebFetch/WebSearch round trips trying to extract a pinout table from a
  datasheet-hosting site — try the local KiCad install first; it's usually faster and always more
  reliable for parts already in KiCad's standard libraries.
- When a repo has its own generative/source-of-truth component model (Atopile, a custom netlist
  generator, etc.) — treat that model's pin assignments as a claim to verify, not as automatically
  correct, especially for parts with multiple physically-symmetric-looking gates where an
  off-by-a-few-pins error is easy to introduce and hard to notice.

## Examples

Real vs. repo-model comparison found this session for `SN74HC4075` (triple 3-input OR):

| Gate | Real pinout (KiCad `4xxx.kicad_sym`, CD4075) | Repo's Atopile model (`components.ato`) |
|---|---|---|
| Gate 1 (in A,B,C / out Y) | 1, 2, 8 / 9 | 1, 2, **12** / **13** |
| Gate 2 (in A,B,C / out Y) | 3, 4, 5 / 6 | 3, 4, 5 / 6 (matches) |
| Gate 3 (out Y / in A,B,C) | 10 / 11, 12, 13 | **8** / **9, 10, 11** |

`SN74HC00` (quad 2-input NAND), by contrast, matched exactly between the real datasheet pinout and
the repo's model — confirming the discrepancy above is a genuine, isolated bug in one component
model rather than a systematic misunderstanding of the extraction method.

**Update (2026-07-14, later same day):** the `components.ato` model was corrected to the real
pinout in the table above. It had been left as a documented-but-unfixed bug through the end of the
original session (the schematic wiring correctly used real pin numbers directly, bypassing the
broken model, so nothing was blocked on it) but the source-of-truth model itself stayed wrong
until this follow-up. All downstream wiring in `modules.ato` referred to the component by signal
name (`fault_or.A1`, `fault_or.C1`, etc.), never by raw pin number, so fixing the component
definition required no changes anywhere else in the `.ato` source — the earlier decision to model
by name rather than number is what made this a safe, isolated fix.

## Related
- `docs/solutions/tooling-decisions/kicad-schematic-connectivity-tracer-2026-07-14.md` — how these
  verified absolute pin positions get used to build and self-check new wiring.
- `docs/solutions/workflow-issues/firmware-hardware-pin-map-divergence-2026-07-14.md` — the
  parallel problem of two disagreeing sources of truth, one level up (GPIO assignment rather than
  IC internal pinout).
