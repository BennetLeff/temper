---
title: "Isolation values need role-aware authority, not tier-label equality"
date: "2026-08-31"
last_updated: "2026-09-01"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture_pattern
component: isolation-barrier
severity: critical
applies_when:
  - "Several clearance or creepage declarations share an insulation-tier label but serve different engineering roles."
  - "A repository-wide scanner finds numerically different safety values across generated rules, design targets, and production requirements."
  - "A bounded PCB topology campaign must consume the same safety contract as production validation."
tags:
  - isolation-authority
  - reinforced-insulation
  - clearance
  - creepage
  - rust-ssot
  - fail-closed
  - topology-identity
  - standards-review
---

# Isolation values need role-aware authority, not tier-label equality

## Context

Temper's broad declaration scanner grouped three reinforced-clearance values into one family and treated numerical equality as the consistency rule. That made a 2.0 mm generated `HighVoltage` fabrication projection conflict with two 6.0 mm HV-to-LV project/fabrication projections even though those values did not make interchangeable claims.

Blindly changing either side would have been unsafe. Raising the generated value could change routing and DRC behavior without establishing the applicable standard basis; lowering the 6.0 mm project target would silently weaken a conservative design constraint. Treating the mismatch as permanently accepted drift would preserve the ambiguity and allow future declarations to inherit the exception.

The production creepage role has a separate 12.6 mm PD3 requirement. Regional routing experiments had embedded that value as a free literal, so a safety-contract change and a topology campaign could drift independently even if each subsystem's tests stayed green.

The same authority problem appeared one level downstream in the net-41 corridor campaign. Candidate identity, production topology, and the affected SELV denominator all had to be exact and content-addressed before any scratch route could be trusted. The declaration and screening authority are pending in PR #1557 as of 2026-09-01; they are not yet merged authority or a production-board approval.

The execution layer exposed the next boundary: a caller-supplied list of plausible measurements is not admission evidence. Required instruments must be named exactly, their receipts must bind the board bytes each instrument inspected, and an untrusted preflight must terminate before candidate screening receives any measurement or rejection credit. The recorded execution found a capped `W:silk_overlap` result and disagreeing normalized creepage sets across repeated runs, so it correctly produced `instrument-error` with all 2,880 candidates declared and zero measured, materialized, routed, or admitted. The production board and DRC ceiling remained byte-identical.

## Guidance

Keep broad discovery and narrow adjudication separate:

1. Let the scanner continue finding candidate declarations by metric and coarse tier. Broad discovery is useful precisely because it does not need to understand every subsystem.
2. Send only a closed, exact identity set to a typed authority owner. The authority row must name the physical metric, boundary, insulation purpose, environmental basis, engineering role, source, review status, and applicable minimum relationship.
3. Require exact projection coverage. Missing, extra, renamed, duplicated, non-finite, or numerically changed declarations fail; a coincidentally unchanged distinct-value set is not enough.
4. Keep provisional provenance visible. A successful role resolution must still emit `REVIEW REQUIRED` until an attributed qualified standards review replaces the provisional source. Passing the consistency gate is not standards approval.
5. Make downstream topology logic consume the governing roles and their scoped digest from the same Rust authority. Candidate identities then become stale automatically when the board, generated inputs, declaration, or either consumed topology-authority row changes.

The Rust-owned contract lives in `packages/temper-design-bundle/src/safety_value_authority.rs`. It exposes the three live reinforced-clearance projections without changing their values and exposes the 6.0 mm conservative project target plus the 12.6 mm PD3 production creepage role as a scoped topology authority. `scripts/check_creepage_clearance_drift.py` remains the discovery and reporting layer; it cannot manufacture a role mapping or suppress provisional review.

The regional quality oracle consumes those two roles through `packages/temper-quality-oracle/src/regional_feasibility.rs`. Rust also owns the candidate identity and exact candidate-set digest. Each identity binds the declaration, production board, generated inputs, topology authority, predecessor placement, route axes, layer, width, and via geometry. Python is only a transport boundary: it may load evidence, JSON-encode Rust-returned objects for transport, and call the Rust generator and validator, but it must not select predecessor rows, assemble the family, define the canonical candidate serialization, or compute its digest.

Hash the authority envelope, not only its payload. An early implementation hashed the candidate vector but left the neighboring board hash, generated-input hashes, topology authority, and count outside that pin. The corrected `candidate_set_digest` canonicalizes the complete `CorridorDeclaration` with only the digest field itself removed. Admission then independently reconstructs every candidate in Rust from the bound predecessor manifest and declaration, including ordinal, order, J1 position, route points, and content-addressed ID. Recomputing an aggregate digest over a tampered list can no longer bless a self-consistent lie.

Treat same-typed transport arguments as an identity hazard. The topology validator accepts eight bound evidence byte inputs plus a JSON request, so its PyO3 seam is keyword-only and its callers name each evidence role. Similarly, optional injected transports must be supplied as a complete pair or not at all; silently replacing one half with a live extension makes tests exercise a different authority transaction than they claim.

Bind topology as a graph, not a census. The production net-41 predecessor contains 15 In3.Cu segments, one In3.Cu-to-F.Cu blind via, and zero zones, but those plausible counts conceal two connected components and an isolated `C7.1`. The net is topologically open, with a 12 mm pad-center-to-segment-start coordinate gap: `C7.1` is at `(112, 206)` while the first segment begins at `(112, 218)`. The declaration also binds the complete affected SELV denominator—240 pads, 1,798 tracks, 124 vias, and 13 zones—by ordered identity, rather than sampling a convenient local subset.

Do not put geometry-only strings into a set and call the result an object denominator. Two distinct KiCad objects can occupy identical geometry; a `BTreeSet` then silently turns two objects into one. The topology snapshot qualifies traces, vias, and zones by stable board-order occurrence and pads by reference, number, and occurrence before adding geometry.

Do not expose a JSON validation receipt as capability authority. A caller that can submit both the candidate set and the matching receipt can forge both. The safe boundary accepts only raw bound evidence and raw measurements; one Rust transaction derives the candidate set, runs board/design-basis admission, and screens exact coverage. The candidate declaration and validator receipt remain internal values that Python cannot construct or substitute.

Separate partial screening from complete admission. The declared family is the exact Cartesian product `60 × 4 × 4 × 3 = 2,880`. The current Rust quality oracle evaluates the 6.0 mm clearance and 12.6 mm creepage bounds and returns the complete deterministically ranked `clearance_creepage_prefilter_subset`, with role, value, and source attribution on every veto. It must not apply the route budget at this stage: candidates rejected by later connectivity, mechanics, safety-signature, or DRC checks have to be backfilled from the remaining ordered prefilter survivors. A follow-on execution driver must materialize every prefilter survivor, apply those complete vetoes, and only then route the first 12 complete survivors. The current design basis still denies production promotion; selecting a complete scratch survivor does not authorize copying it to the production board.

Bind every terminal instrument receipt to both an exact instrument identity and the SHA-256 of its subject board. The quality oracle defines distinct closed sets for preflight, pre-route, and post-route evidence; missing, extra, duplicate, empty, malformed, or wrong-subject receipts fail admission. The runner hashes each canonical evidence payload; Rust requires a well-formed receipt hash and exact subject identity, but does not receive the payload preimage to recompute that hash. Command timeouts and tool failures become explicit error receipts rather than empty or clean-looking results.

Make preflight ordering part of the Rust terminal authority. `execute_corridor_campaign` validates the declaration and the complete named preflight set against the production-board hash before it calls candidate screening. The first non-trusted preflight result returns `instrument-error` from a zero-credit base receipt. This preserves the distinction between an instrument condition and a candidate condition: a capped, unstable, missing, or wrong-board baseline cannot become a candidate rejection.

Derive materialization and route scope from canonical Rust identities. Rust reconstructs each accepted placement and route instruction from the declaration and predecessor evidence, and rejects any submitted instruction that differs. The narrow S-expression mutation seam verifies target-net identities and preserves a fingerprint of all non-target board content. The public router boundary accepts an explicit target-net scope; empty, duplicate, or unknown target nets fail rather than silently widening the route.

Treat the route limit as an evidentiary budget, not proof of exhaustion. The execution authority routes at most the first 12 complete survivors and consults the Rust terminal decision after each attempt. If eligible rows remain untested, the only honest terminal state is `stopped-indeterminate`; an unresolved higher-ranked route cannot be bypassed to admit a later row.

The board-owning validator in `packages/temper-design-bundle/src/regional_topology.rs` binds the production topology and exact Rust-derived candidate set, so quality scoring does not become a second board parser. Hashes are freshness guards, not semantic validation: the validator also reads the design basis's predecessor authority, fixed-copper fence, current-capacity invariants, necessary bound, authority roles, limitations, and denial flags. Admission assertions such as the 12.9 mm necessary-bound minimum are exact contract values, not caller-selectable lower limits. The validator accepts only bounded scratch screening and routing authority; it rejects fabrication release, qualified safety approval, and production promotion.

## Why This Matters

An insulation tier describes purpose, not provenance or enforcement role. A standards minimum, conservative design target, fabrication rule, and measured production requirement can legitimately differ while still forming one coherent contract. Conversely, two equal numbers can be unsafe if one is attached to the wrong metric, boundary, or environment.

Role-aware authority makes both errors observable. It permits justified differences only for registered identities, rejects unsafe movement by construction, and prevents a search campaign from continuing under stale safety assumptions. Retaining the review-required state also distinguishes repository consistency from appliance-safety approval.

Exact-set integrity closes a second class of false confidence. A differential or screen over 2,879 of 2,880 candidates is incomplete even if every evaluated row passes. Likewise, matching track and via counts does not prove electrical connectivity. Candidate-set digests, graph reconstruction, and exact denominator identities turn those omissions into fail-closed contract violations.

Finally, naming a partial result after what it proves prevents accidental authority escalation. Clearance and creepage are necessary route bounds, but they cannot establish mechanical fit, containment, connectivity, absence of new safety signatures, or DRC compliance. The `clearance_creepage_prefilter_subset` name preserves that distinction for the execution layer.

Terminal receipts close the remaining gap between correct individual checks and a correct campaign verdict. Exact instrument sets prevent omissions, subject hashes prevent cross-board evidence reuse, canonical materialization prevents the transport layer from redefining a candidate, and terminal precedence prevents an attractive later result from hiding an earlier unresolved or failed condition. A deterministic byte replay then proves the recorded terminal artifact was derived from the pinned inputs, not hand-edited after the run.

## When to Apply

- When a consistency gate reports same-tier numerical drift across unlike artifacts.
- Before changing a safety value merely to make a repository-wide equality check green.
- When a generated fabrication rule, design target, and production requirement must coexist.
- Before freezing identities for a placement or routing campaign that depends on clearance or creepage.
- When route-object counts look stable but connectivity or denominator completeness may have changed.
- When a bounded geometric screen feeds a later materialization, DRC, or production-promotion stage.
- When external tools can cap output, disagree across repeated normalized runs, time out, or inspect scratch boards with different content.
- When a fixed candidate denominator is screened completely but only a bounded prefix may consume expensive routing or simulation capacity.

## Examples

A role-aware row should answer questions that a bare number cannot:

```text
metric: clearance
boundary: high_voltage_to_low_voltage
role: conservative_design_target
value: 6.0 mm
applicable minimum: clearance.hv_lv.120v_ovc2.minimum
review status: current-edition review required
```

A topology candidate should bind the scoped authority digest alongside its board and declaration hashes:

```text
candidate identity = digest(
  declaration authority,
  production board,
  generated inputs,
  topology authority,
  complete route strategy,
)
```

For the current net-41 family, the evidence contract is:

```text
candidate set = 60 predecessor placements
              × 4 R14 endpoints
              × 4 corridor centerlines
              × 3 entry portals
              = 2,880 exact identities

prefilter pass != complete hard-veto survivor
```

The execution admission order is:

```text
validate declaration and exact preflight instrument set
  -> instrument-error with zero candidate credit, if any preflight is untrusted
  -> screen all 2,880 declared identities
  -> materialize every ordered prefilter survivor
  -> apply connectivity, mechanical, containment, safety-signature, ampacity, and DRC vetoes
  -> route at most the first 12 complete survivors, stopping at the first admitted row
  -> stopped-indeterminate if eligible rows remain untested
```

The committed execution evidence demonstrates the fail-closed branch rather than a candidate verdict. Its three-run DRC preflight reached a reporting cap and disagreed on normalized creepage sets, so the terminal receipt records zero measured candidates. Byte-for-byte replay passes, while `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` remain unchanged.

Useful mutation tests remove or duplicate one candidate measurement, change one route axis, disconnect a pad while preserving the route census, or omit one SELV object. Each mutation must invalidate the relevant digest or graph contract before ranking or terminal selection.

Do not use an accepted-drift string as a substitute for this model, and do not describe a clean role-resolution result as qualified IEC approval.

## Related

- `docs/solutions/architecture-patterns/dense-creepage-repair-is-neighborhood-topology.md`
- `docs/solutions/architecture-patterns/netclass-clearance-ssot-designrules-consumer-chain-2026-07-07.md`
- `docs/evidence/net41-route-layer-corridor-20260831/README.md`
- `docs/evidence/net41-route-layer-corridor-20260831/declaration.json`
- `docs/evidence/net41-route-layer-corridor-20260831/design-basis.json`
- `docs/evidence/net41-corridor-execution-20260901/README.md`
- `docs/solutions/architecture-patterns/typed-rust-quality-oracle-pipeline-2026-07-01.md`
- `docs/solutions/best-practices/characterize-oracle-noise-floor-2026-07-26.md`
- `docs/solutions/best-practices/ratchet-inputs-must-be-pinned-2026-07-29.md`
