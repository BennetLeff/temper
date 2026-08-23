<!-- provenance: commit=b94f8cc9d4b03411a50680efc14e8c0d0bca1470 dirty=UNKNOWN -->
---
title: "Component.net_class flattening -- root cause, fix, and before/after safety-rule measurement"
date: 2026-08-11
module: temper-placer / temper-drc-rs
tags: [net-classification, safety, drc, kicad-parser]
problem_type: silent-data-flattening
---

# Component.net_class flattening -- root cause, fix, and before/after safety-rule measurement

## Summary

All 169 components on `pcb/temper.kicad_pcb` parsed with `net_class ==
"Signal"`, unconditionally -- a second, distinct flattening from the one
`#1041`/`#1042` fixed (those fixed `Net.net_class`; `Component.net_class` is
a separate field on the same pyclass hierarchy and stayed flat the whole
time). This field is read directly by three Rust safety-DRC kernels
(`packages/temper-drc-rs/src/rules/safety/{creepage,hv_lv_separation,isolation}.rs`,
via `resolve_safety_category(comp, board)` / `is_iso_component(comp,
board)`), so every one of them was evaluating a board where every component
looked electrically identical, on a design whose entire safety case is a
mains<->SELV creepage barrier.

## Where a component's class should come from

A component is not a net -- it has pins on potentially several nets of
different classes. The answer implemented here: **a component's class is
the most safety-severe class among its own pins' resolved net classes**
(HV/AC-severity beats LV/unclassified), expressed through this codebase's
own pre-existing binary `"Signal"` / `"HighVoltage"` idiom -- not a new,
finer-grained label scheme.

This was a deliberate choice against two alternatives:

1. **Preserve the real per-class name on the rollup** (e.g. `"ACMains"`,
   `"GateDriveHV"`, `"HighVoltageIsolated"` instead of collapsing to
   `"HighVoltage"`). Rejected: four *other*, already-shipped production
   consumers of `Component.net_class` --
   `temper_placer/metrics/physics.py:149`,
   `temper_placer/validation/metrics.py:310`,
   `temper_placer/deterministic/stages/_phase_rotation.py:160`, and
   `temper_placer/router_v6/constraints_design_rules.py:613` -- already do a
   literal `net_class == "HighVoltage"` string comparison as their own HV/LV
   proxy. All four were *also* silently vacuous before this fix (every
   component was `"Signal"`), for the identical root cause the task
   description centers on the three DRC kernels. Preserving real class
   names would have fixed the DRC kernels (which resolve safety category via
   SSOT lookup or keyword-substring fallback, either of which tolerates a
   real class name fine) while introducing a *new* silent gap in the four
   consumers that only understand the literal `"HighVoltage"` string. Reusing
   the existing binary label fixes all seven consumers (3 DRC kernels + 4
   pre-existing ones) with one change, not one.
2. **Move classification to the safety kernels themselves (read per-pin/
   per-net data instead of a component-level field).** Rejected as
   out-of-scope/unnecessary: `BoardState`'s `Component` struct in Rust
   already only carries a single `net_class: NetClassName` field with no
   pin/net topology attached (see `packages/temper-drc-rs/src/board.rs`) --
   changing that shape is a materially larger, cross-cutting change to the
   Rust board contract than the task's own framing calls for, and the
   component-level field is a real, useful, coarse concept for placement
   (see `dru_priority`) even if a hypothetical future pin-level check
   wants more. The Python-side rollup already existed
   (`_apply_safety_classifications`, `temper_placer/io/_parse_nets.py`) and
   was correct; it was simply never invoked by default.

## The fix

`_apply_safety_classifications` (existing, unchanged) already computes
exactly this rollup. The defect was that `kicad_parser.parse_kicad_pcb`
only invoked it when a caller explicitly passed `design_rules=` --
`design_rules=None` (the default) meant "skip entirely", and essentially no
real DRC-path caller passed it (two call sites in
`temper_placer/regression/physics_oracle.py` already did, independently
confirming this is the established pattern -- see that file's own
`design_rules = create_temper_design_rules()` lines).

The fix changes the *default*, mirroring the `net_class_mapping` precedent
`#1041` already established (`net_class_mapping=None` defaults to
`TEMPER_NET_ASSIGNMENTS`, not to "off"): `design_rules=None` now defaults to
`create_temper_design_rules()` (this project's own SSOT, built from
`TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` in `core/design_rules.py`),
and `_apply_safety_classifications` always runs. No table is transcribed
into Rust or duplicated anywhere. An explicit empty `DesignRules(net_classes={},
net_class_assignments={}, ...)` is the opt-out, mirroring `net_class_mapping={}`.

This is a one-file Python change
(`packages/temper-placer/src/temper_placer/io/kicad_parser.py`); no Rust
rebuild is required for the fix itself (`_apply_safety_classifications`
mutates the Python `Component.net_class` pyclass attribute directly, and
every downstream Rust DRC consumer reads that same attribute as a plain
string when it marshals the board across the pyo3 boundary).

`drc_oracle_marshal.rs::build_board_dict_py` (the frozen migration-parity
artifact) is not touched and does not need to be: it is not called from any
production `src/` code path (only from the differential test suite and
`drc_ratchet.py`'s *dict*-based external callers, per its own module
docstring), and this fix changes a Python default, not that kernel's
semantics.

## Measurement

Reproduced via the exact board-dict construction
`temper_placer/regression/drc_ratchet.py::DrcRatchet._run_rust_drc` already
uses in production (full `TEMPER_NET_CLASSES` wired as `net_class_rules`,
`hv_clearance_mm` at its default 10.0mm) against `pcb/temper.kicad_pcb`:

| Measurement | Before | After |
|---|---|---|
| `Component.net_class` distribution | `{"Signal": 169}` | `{"Signal": 119, "HighVoltage": 50}` |
| `temper_drc_rs.run_drc(categories=["safety"])` | **0 violations** | **94 violations** (all `SAF_HVL_001`, HV/LV separation) |
| Same engine, `categories=["drc"]` | 117 | 166 (+49, all `DRC_CLR_001` -- HV-to-non-HV component clearance, e.g. `C1 (HighVoltage) to C6 (Signal) = 0.000mm, required 6.000mm`) |
| Same engine, all categories, errors/warnings | 85 errors / 38 warnings | 228 errors / 38 warnings |
| `kicad-cli` DRC ceiling (`power_pcb_dataset/drc_ceiling.json`, `--backend kicad-cli`) | unaffected | unaffected -- reads netclasses from `pcb/temper.kicad_pro` directly, not from this Python path (confirmed: `.github/workflows/regression.yml` invokes `ci_check_drc.py --backend kicad-cli` exclusively; the Rust backend this fix affects is not wired into any CI-checked ceiling) |

No `SAF_CRP_001` (creepage) or isolation-check violations appeared: no
`TEMPER_NET_CLASSES` entry currently declares `safety_category="iso"`, so
that axis is unaffected by this specific board's class table (a distinct,
pre-existing gap, out of scope here).

## This is real, not a measurement artifact

**94 new `SAF_HVL_001` HV/LV-separation violations is the fix revealing
genuine, previously-invisible mains<->SELV proximity findings that flat
classification was hiding, not a regression this fix introduces.** Every
one of them is a real pair of components -- one carrying a pin on a
declared HV/AC-severity net (`+170V_BUS`, `ac_l`/`ac_n`, `SW_NODE`, gate
nets, ...), the other not -- sitting closer than the configured 10.0mm
`hv_clearance_mm` bar. Examples (component refdes, gap, all < 10.00mm
required): `C1<->C6` at 0.00mm, `C25<->R34` at 0.00mm, `C13<->K2` at
0.11mm, `C31<->K2` at 0.59mm. These counts are **not** absorbed into any
ceiling by this change -- `power_pcb_dataset/drc_ceiling.json` is untouched
(out of this task's boundaries, and, per the table above, not affected by
this fix's code path regardless). The board itself is out of scope for this
task (a sibling agent owns `pcb/temper.kicad_pcb` placement); this document
exists so the finding is not lost.

## Regression test

`packages/temper-placer/tests/io/test_component_net_classification.py`.
Verified RED against the pre-fix code (temporarily reverted the two-line
default-resolution change in place, re-ran, confirmed 6 of 8 assertions
fail with the exact "still Signal" failure mode described above, then
restored the fix) and GREEN after.
