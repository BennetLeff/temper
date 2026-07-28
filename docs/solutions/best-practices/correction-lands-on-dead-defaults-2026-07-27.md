---
title: "A correction that lands on dead defaults — verified inert by diffing, not by re-reading the file you edited"
date: "2026-07-27"
category: best-practices
module: simulation
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "correcting a subcircuit/function/class's default parameter values"
  - "a parameter is set at more than one layer (library default, netlist-level .param, per-call override)"
  - "about to claim a fix 'took effect' without diffing the actual downstream artifact before and after"
  - "a fix's ownership boundary stops short of the file that actually consumes the corrected value"
tags:
  - dead-default
  - override-shadowing
  - inert-fix
  - byte-identical-diff
  - pan-load-model
  - verify-by-diffing
---

# A correction that lands on dead defaults — verified inert by diffing, not by re-reading the file you edited

## Context

`simulation/models/pan_load.sub`'s `PANLOAD_TRANSFORMER` subcircuit had its
default `K` (0.4 → 0.79) and `L2` (1 µH → 218 µH) corrected on 2026-07-27,
fixing a provably-impossible coupling assumption (see
`docs/solutions/best-practices/citation-loop-validates-a-model-against-itself-2026-07-27.md`
for the citation-chain half of this incident). **The fix was inert for
both of the project's official simulation harnesses**, and this was
discovered before being claimed, by running both harnesses unmodified
before and after the edit and diffing the parsed result arrays in Python —
not by re-reading the edited file and reasoning that the change should
matter.

Three independent, redundant reasons, each confirmed by reading the
consuming code, not inferred:

1. **The harness's `X_PAN` instantiation line explicitly overrides all five
   `PANLOAD_TRANSFORMER` parameters**: `X_PAN tank_mid2 0
   PANLOAD_TRANSFORMER L1={PAN_L1} L2={PAN_L2} K={PAN_K} RPAN={PAN_RPAN}
   RCOIL={PAN_RCOIL}`. A `.subckt` line's own defaults are only used for
   parameters *omitted* at instantiation — none are omitted here, so
   `pan_load.sub`'s new `K=0.79`/`L2=218u` defaults were never reached by
   this call site regardless of what they were set to.
2. **`PAN_L2` was a separate `.cir`-level `.param PAN_L2 = 1u` statement**,
   fixed in the committed netlist, independent of the subcircuit file. The
   harness scripts never overrode it — `PAN_L2` appeared nowhere in either
   script's override dict.
3. **`run_zvs_sweep.py`'s `PAN_PRESETS` (K/RPAN per material) were literal
   Python constants**, copied from — not read from — `pan_load.sub`'s
   header table. Correcting the subcircuit's own preset subcircuits
   (`PANLOAD_CASTIRON`, `PANLOAD_STAINLESS`) would *also* not have reached
   these harnesses, since neither is ever instantiated by them; only
   `PANLOAD_TRANSFORMER` is, with every parameter pinned as in (1).

**Proof, not assertion:** both official harnesses (`run_zvs_sweep.py`,
`run_tank_coil_sweep.py`) were re-run, unmodified, before and after the
`pan_load.sub` edit. Every parsed result was **byte-identical** — verified
by `==` on the full list of result dicts in Python, not eyeballed. A
supplementary, non-harness deck (built outside the owned directory, never
modifying it) confirmed the corrected model *does* imply a materially
different result (~60% higher loaded resonance, 3–8× more power at the
old operating ratio) — proving the edit was semantically real, just
unreachable through either production call path.

**Follow-up pass, same day, closed the gap:** `PAN_L2` was exposed as a
per-preset override in both harness scripts, `PAN_PRESETS` was corrected
to derive `K`/`L2` from the same Infineon-anchored point rather than the
uncited table, and the `.cir`'s own committed baseline defaults were
updated to match — required because the harness's own
`grid_reproduces_independent_baseline_run` sanity check independently
re-runs the committed `.cir` and asserts it matches the Python-generated
grid point exactly; leaving the two out of sync would have (correctly)
failed that check. Once fixed, the official harness reproduced the
supplementary deck's numbers to 4 significant figures — the fix's real
effect became visible in the evidence-tracked artifact chain for the
first time.

## Guidance

1. **A default is only reachable through the call sites that omit it.**
   Before claiming a default-value correction changes anything, find every
   call site and check whether it *actually* omits that parameter. A
   caller that pins every parameter explicitly is immune to the file's own
   defaults by construction, no matter how wrong those defaults were.
2. **Verify a fix took effect by diffing the actual consumer's output,
   before and after — not by re-reading the file you just edited.**
   Re-reading `pan_load.sub` after the edit would show the correction is
   present and looks right; it would not show that neither harness could
   ever reach it. A before/after diff of the harness's own parsed output
   is the only check that catches a dead default, because the defect is
   entirely in what calls the file, not in the file itself.
3. **A parameter set at more than one layer (subcircuit default, `.param`
   statement, per-call Python constant) needs the fix applied at the layer
   actually read at runtime**, not the layer that is easiest to edit or
   owns the clearest docstring. Identify which layer wins before fixing
   any of them.
4. **When an ownership boundary stops short of the actual consumer, say so
   and flag it as a required follow-up — do not claim the fix landed.**
   The first pass here correctly recognized it could not modify
   `simulation/harness/*` and reported the gap explicitly rather than
   silently declaring victory on the subcircuit-only edit; the follow-up
   pass then closed it.
5. **A byte-identical before/after diff on a change you expected to matter
   is itself a finding, not a null result to shrug off.** It is the
   fastest, cheapest signal that the wiring between the edited file and
   its consumer is broken — chase it before concluding the correction was
   too small to matter.

## Why This Matters

The correction to `pan_load.sub` was not wrong — the arithmetic, the
citation, and the resulting `K`/`L2` values all held up under
independent, external verification (Infineon AN235020). The entire risk
was procedural: a reasonable person, having made a correct edit to the
file that "owns" the pan model, could report the fix as done without ever
learning that two production evidence artifacts (`run_zvs_sweep.py`'s ZVS
margin sweep, `run_tank_coil_sweep.py`'s power sweep) were structurally
incapable of reflecting it. The eventual downstream stakes were real: once
the harness-side gap was closed, the corrected model flipped
`TANK_COIL_SPECIFICATION.md`'s headline conclusion ("1800 W is unreachable
at every L tested") and showed 35 kHz nominal switching loses ZVS entirely
for ferromagnetic pans — neither of which a subcircuit-only fix, however
correct, would ever have surfaced.

## When to Apply

- After correcting any default parameter value in a shared model,
  subcircuit, config schema, or base class — enumerate every call site and
  check which ones actually omit that parameter versus pin it explicitly.
- Before reporting a fix as complete — diff the actual downstream
  artifact (a rendered file, a computed result, a written record) before
  and after, rather than re-reading the edited source for plausibility.
- When a fix's ownership boundary (a directory, a file, a package) stops
  short of the code that consumes the corrected value — flag the gap
  explicitly as a required follow-up rather than treating the edit as done.
- When a parameter exists at multiple layers (library default, netlist
  param, language-level constant copy) — identify which layer the runtime
  actually reads before deciding where the fix belongs.

## Examples

```
# pan_load.sub (edited, correct in isolation):
.subckt PANLOAD_TRANSFORMER A B L1=80u L2=218u K=0.79 RPAN=10 RCOIL=0.1
#                                    ^^^^^^^ ^^^^^^^ corrected 0.4->0.79, 1u->218u

# zvs_margin_sweep.cir (not edited by the first pass):
.param PAN_L2 = 1u                          # <- fixed, independent of the .sub file
X_PAN tank_mid2 0 PANLOAD_TRANSFORMER \
    L1={PAN_L1} L2={PAN_L2} K={PAN_K} RPAN={PAN_RPAN} RCOIL={PAN_RCOIL}
#                    ^^^^^^^^^^^^^^^^ all 5 params pinned -- the .sub file's
#                    own new defaults are never consulted at this call site
```

```python
# The verification that actually caught it -- not re-reading pan_load.sub,
# but diffing the harness's own output:
before = run_zvs_sweep(baseline_code)
after  = run_zvs_sweep(corrected_pan_load_sub)
assert before == after          # TRUE -- byte-identical, the red flag
# -> chased the wiring, found three independent override layers,
#    none of which read the edited file's defaults
```

## Related

- `docs/solutions/best-practices/citation-loop-validates-a-model-against-itself-2026-07-27.md`
  — the other independent defect found in the same file, the same day: the
  table the pre-correction defaults came from had no source at all. Fixing
  the value and fixing its citation chain were two separate necessary steps.
- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — a sibling verification discipline: re-derive independently rather than
  trust a plausible-looking artifact; here the byte-identical diff plays
  the same role as that doc's ancestry check.
- `docs/evidence/2026-07-27-pan-model-correction.md` — the first pass:
  the corrected `K`/`L2` derivation and the byte-identical-diff proof the
  fix was inert for both official harnesses.
- `docs/evidence/2026-07-27-pan-preset-correction.md` — the follow-up pass
  that exposed `PAN_L2` as an override, corrected `PAN_PRESETS`, and
  reproduced the supplementary deck's findings through the official
  harness for the first time.
- `simulation/models/pan_load.sub`, `simulation/harness/nets/zvs_margin_sweep.cir`,
  `simulation/harness/run_zvs_sweep.py` — the three files across which the
  override chain runs.
