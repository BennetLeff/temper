---
title: "Net-41 pre-route feasibility witness evidence"
date: "2026-09-02"
category: pcb-design
scope: bounded-scratch-only
---

# Net-41 pre-route feasibility witness evidence

This directory records the first Rust-owned feasibility run for the immutable
2,880-candidate Net-41 corridor declaration. It closes the model ambiguity
that made the 2026-09-01 exhaustive campaign hard to interpret, then stops at
one deterministic pre-route witness. It does not invoke or evaluate the
router.

## Result

The run completed with terminal `witness-rejected`:

- 2,880 declaration-bound candidates screened;
- one witness materialized, candidate
  `NET41-CORRIDOR-38802d1da8d11c8ae8a342a5c010c8a8603b78e676fa0604353fa0c321afca77`,
  declaration ordinal 2,244;
- zero candidates routed;
- all affected references had complete body, position, usable domain, and
  240-pad SELV-denominator inputs;
- all three required preflight instruments were trusted;
- all witness instruments were trusted and bound to scratch-board SHA-256
  `10af11c950e3e39b24cb540747c7ad3e540507575d545310794a801631b99c76`;
- Rust reported four new/worsened safety identities and nine new hard DRC
  identities, with zero indeterminate hard comparisons and zero new scoped
  silkscreen findings.

The safety findings are four functional LV_CONTROL-to-LV_CONTROL creepage
relationships involving `R54`, `R66`, `SW1`, and `U22`. The hard DRC findings
are six clearance/hole-clearance observations, one 12.2478 mm HV-to-LV
creepage observation, and two J1 pad-to-track shorts. The full canonical
identities and multiplicities are in `feasibility-receipt.json`; counts are
only summaries.

This is not a family-negative or exhausted result. Rust classifies each
witness finding as unresolved with respect to placement and route shape, so a
single rejected witness cannot prove that all 2,880 candidates fail. It does
prove that the family is not ready for routing under its current ranking and
construction: the deterministic first survivor is not pre-route clean.

## Model and instrument corrections exercised by the run

J1's body is evaluated through the approved standalone footprint supplement,
content-bound by SHA-256
`050fe934d6208d5bd0e8d73da760c525c11185ac838b9c44b09b9cdf20f86a76`.
The supplement supplies body geometry only; it does not synthesize pads,
courtyards, or a board edit.

The domain manifest is intentionally a partial net classifier. The preflight
therefore follows the existing safety loader's contract: an affected
component is usable when it has one unambiguous explicitly classified domain,
even when other physical pads sit on intentionally unclassified internal
nets. Requiring every pad net to appear in the manifest produced a false
`model-incomplete` result for `R45`, `R58`, `R66`, `SW1`, and `U22` during an
earlier diagnostic run. The corrected predicate accepts their explicit
`gnd`/`+3V3`/fault-line membership, rejects absent or mixed domain membership,
and independently preserves the exact 240-pad SELV denominator.

The live run also exercised the v3 DRC comparison boundary. Three semantic
baseline samples and three witness samples agreed. KiCad's globally saturated
`W:silk_overlap` category was handled through complete scoped evidence rather
than treated as an exact global set. Exact new, removed, worsened, and
indeterminate identity multisets remain available in the manifest's compact
instrument index.

## Authority and scope

The production board and DRC ceiling remained byte-identical:

- `pcb/temper.kicad_pcb`: content SHA-256
  `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9`;
- `power_pcb_dataset/drc_ceiling.json`: content SHA-256
  `c6b2198e62ca5b15878884b1e2822a8b3bbd7372ace8f6198aeccffe83189fb2`.

The manifest binds the immutable declaration, generated-input identities,
model rows, J1 model source, preflight receipts, exact witness instruction,
scratch subject, typed findings, and terminal receipt. A same-worktree replay
against the retained checkpoint re-ran the Rust prepare and finalize lifecycle
and passed as `witness-rejected` with receipt SHA-256
`431bbb5fb10da7e1623b95f9455a497df40f1b6e4e1e746ec81477325fac446c`.

Nothing here approves fabrication, relaxes a safety or DRC gate, modifies the
production PCB, changes the DRC ceiling, or makes a claim about router
capability.

## Next engineering unit

Build a declaration-bound pre-route finding matrix over the 240 unique
placement bases, not another routed campaign. Use the exact v3 identities to
separate invariant intersections from placement-dependent fringes, then move
proved constraints into the Rust candidate generator/ranking. The immediate
targets are J1 track avoidance, the `R66`/`SW1`/`U22` local clearance cluster,
and the `R54` functional-creepage relationships. Produce a pre-route-clean
witness before reopening any routing budget.
