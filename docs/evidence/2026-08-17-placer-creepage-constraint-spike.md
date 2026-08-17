<!-- provenance: STUB, in progress. commit=775a7a40e (main), board pcb/temper.kicad_pcb sha256 33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962 verified unchanged, not to be modified (analysis only). -->

# Spike: does the CP-SAT placer know about creepage/clearance, and would it have avoided J1/K1? (2026-08-17)

STATUS: IN PROGRESS — this is a survival stub, committed first per handoff §15.
Being filled in by a live investigation of `packages/temper-placer/src/temper_placer/placer/cp_sat/`,
`gates.py`, and `scripts/generate_kicad_dru.py` / `pair_clearance.generated.yaml` /
`pair_creepage.generated.yaml`.

Question: why does the placer produce layouts (e.g. J1 4.0-5.3mm from K1's HV
contact pins, needing 12.6mm PD3 reinforced creepage) that are provably
unroutable under the board's own safety rules, and can it be told not to?

Sections to be completed:
1. What the placer's CP-SAT model actually constrains (traced from model construction, not naming).
2. Whether `IECCreepageGate` is a constraint or a post-hoc verdict.
3. Whether the `pair_clearance.generated.yaml` / `pair_creepage.generated.yaml` SSOT tables are read by the placer.
4. Whether a creepage-aware placer would have avoided J1/K1, or proven the board infeasible.
5. Feasibility/cost assessment (O(n^2) pairs, cross-domain subset, solve-time impact).
6. Recommended design.
7. Minimal prototype (separate commit) reading pair_creepage.generated.yaml against the current placement.
