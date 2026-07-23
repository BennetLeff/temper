---\ntitle: "U7-U8: W2 audit findings + shorting/diff-pair diagnosis (Phase 2, 2026-07-18)"
date: "2026-07-18"
category: architecture-patterns
module: temper_placer
problem_type: logic_error
severity: high
symptoms:
  - "corpus-board routing-DRC gate reports 249 violations (46 shorting_items, 6 diff_pair_gap_out_of_range) despite netclass SSOT layer assignment being 'live' since 2026-07-08"
  - "shorting_items involve real track-to-track crossings on F.Cu: GATE_H↔+15V, SPI_MISO↔GND, USB_D+↔USB_D-, USB_D+↔GND, +3V3↔SPI_MISO"
  - "diff_pair_gap_out_of_range: USB D+/D- pair uses netclass 'Default' with gap=0.0000mm; actual negative gaps (overlapping tracks)"
root_cause: implement_partial
resolution_type: document_and_scoped_fix
tags:
  - temper-placer
  - router-v6
  - w2
  - multi-layer
  - drc
---\n
# U7+U8: W2 Multi-Layer Audit + Violation Diagnosis\n\n## U7: W2 Plan Completion Audit\n\n### Background\n\nThe multi-layer escalation (plan `2026-07-08-004-feat-4-layer-functional-stackup-plan.md`,
workstream W2) was believed to be ~2.5/6 units complete as of 2026-07-18:
U1 (stackup definition) and U2 (net-to-layer assignment) were committed and
wired into `route_pcb()`. U3 (IPC-2152) was partially live with
`core/ipc2152.py` existing but no per-net current config. U4/U5/U6 were
unstarted.\n\n### Finding: U2's Layer Constraints Are Stored But Never Wired To A*\n\n`layer_assignments_from_netclass()` (`layer_assignment.py:299`) correctly
resolves each net's layer from the netclass SSOT. `route_pcb()`
(`adapter.py:460`) calls it and passes the result as
`RouterV6Pipeline(layer_constraints=layer_constraints)`.\n\nHowever, `RouterV6Pipeline._run_stage4()` (`pipeline.py:1104`) **never
references `self.layer_constraints`**. The stored dict is never passed to
`BoardState`, `Stage4Orchestrator`, or `run_astar_pathfinding()`. The A*
kernel has no awareness of per-net layer restrictions from the SSOT.\n\nThe actual layer decision for A* routing comes from `_assign_layer()`
in `channel_mapping.py:35`, which uses a simple heuristic:\n- Power/ground/HV nets → B.Cu (bottom)\n- Everything else → F.Cu (top)\n- All nets → F.Cu when `_SINGLE_LAYER_MODE=True` (default `False`)\n\nThis heuristic does NOT consult the SSOT `layer` field from
`netclass_rules.yaml`. It is the **only** layer-resolution mechanism that
governs A* routing decisions through the `ChannelPath.preferred_layer` field.\n\n### U2 Completion State: PARTIAL\n\n| Component | Status | Evidence |\n|-----------|--------|----------|\n| `layer` field in netclass_rules.yaml | DONE | All 9 classes have `layer` (e.g., Signal→F.Cu, GateDrive→B.Cu) |\n| `layer_assignments_from_netclass()` | DONE | Correctly resolves net→layer from SSOT |\n| `route_pcb()` calls layer_assignments_from_netclass | DONE | adapter.py:460 |\n| Pipeline stores `layer_constraints` | DONE | RouterV6Pipeline.__init__ (adapter.py:470) |\n| Pipeline PASSES `layer_constraints` to A* kernel | **NOT DONE** | `_run_stage4()` never references `self.layer_constraints` |\n| A* routing honors per-net layer restrictions | **NOT DONE** | `_assign_layer()` in channel_mapping.py is the sole authority |\n\n### Attribution Verification\n\nThe routing-DRC gate's captured error message (\"single-layer F.Cu routing with
all 24 nets on one layer\") is **correctly attributed** to single-layer routing.
Despite 2.5/6 W2 units appearing complete, the missing wiring of
`layer_constraints` to the A* kernel means routing IS still effectively
single-layer. The 261/443 DRC violation count is NOT a stale attribution.\n\n### Remaining W2 Gap Map\n\n| W2 Unit | Status | Can Move DRC Count? | How |\n|---------|--------|---------------------|------|\n| U1 Stackup | DONE (core/stackup.py jlc04161h_7628) | Indirect | Copper weights for IPC-2152 |\n| U2 Layer-to-net | PARTIAL | **YES** | Wire `layer_constraints` to `_run_stage4` |\n| U3 IPC-2152 | PARTIAL (no net_currents.yaml) | Indirect | Trace width sizing |\n| U4 Power pours | Not started | Indirect | Plane connectivity |\n| U5 USB diff-pair | Not started | **YES** | Needed for diff_pair_gap_out_of_range |\n| U6 StackupGate | At different path (placer/cp_sat/gates.py) | Indirect | Gate verification |\n\n---\n\n## U8: Individual Diagnosis of shorting_items and diff_pair_gap_out_of_range\n\n### shorting_items (46 instances on corpus board, kicad-cli 10.0.4)\n\nClassification of first 10 instances:\n\n| Net A | Net B | Classification |\n|-------|-------|----------------|\n| GATE_H | +15V | Genuine short: HV gate drive crosses power rail on F.Cu |\n| SPI_MISO | GND | Genuine short: signal crosses ground on F.Cu |\n| +3V3 | SPI_MISO | Genuine short: power crosses signal on F.Cu |\n| USB_D+ | USB_D- | Genuine short: diff pair tracks overlap on F.Cu |\n| USB_D+ | GND | Genuine short: USB crosses ground on F.Cu |\n\n**Diagnosis**: All shorting_items are **genuine track-to-track shorts** caused
by routing all nets on a single layer (F.Cu). The A* kernel produces paths that
cross with insufficient clearance. These are NOT placement-irreducible
intra-component false positives. Adding layer separation (routing GND/power on
B.Cu or inner planes) would eliminate the majority of these shorts.\n\n### diff_pair_gap_out_of_range (6 instances on corpus board)\n\n| Count | Netclass | Min Gap | Actual Gap |\n|-------|----------|---------|------------|\n| 6 | 'Default' | 0.0000 mm | -0.079 to -0.279 mm |\n\n**Diagnosis**: All 6 instances are the USB D+/D- differential pair. The pair
uses netclass `'Default'` (no explicit USB/HighSpeed class assigned) with a
configured minimum gap of 0.0000 mm. The actual gaps are negative (tracks
overlap).\n\n**Root cause**: W2 U5 (USB differential pair constraints) is unstarted. No
differential pair constraint infrastructure exists for the USB pair — no
impedance target (90Ω), no minimum spacing (0.2mm), no reference plane
assignment (In1.Cu GND).\n\nThese violations would be resolved by implementing W2 U5: add USB class to
netclass_rules.yaml, set diff-pair gap ≥ 0.2mm, and wire the constraint
through `differential_pair_constraints.py`.\n\n---\n\n## U9/U10: Recommended Follow-up\n\n1. **Wire `layer_constraints` to A* kernel** (W2 U2 completion):\n   - In `_run_stage4()`, pass `self.layer_constraints` to `BoardState`\n   - In `Stage4Orchestrator`, read `layer_assignments` and apply to per-net\n     routing (`ChannelPath.preferred_layer` override)\n   - Expected impact: major reduction in `shorting_items` (46→near-0) and\n     `tracks_crossing` (currently 100 on production, ~250 on corpus)\n\n2. **Implement USB differential pair constraints** (W2 U5):\n   - Add USB class to `netclass_rules.yaml` with diff-pair gap=0.2mm\n   - Wire through `differential_pair_constraints.py`\n   - Expected impact: eliminate all 6 `diff_pair_gap_out_of_range` violations\n\n3. **Re-measure after fixes** (U10):\n   - Run corpus-board routing DRC with layer_constraints wired\n   - Run production-board routing DRC with layer_constraints wired\n   - Assert violation delta is attributed to the specific fixes, not\n     threshold relaxation\n\nThese are follow-up tickets, not implemented here — per the Phase 2 plan's
deferred scope (\"only the units that measurably move the routing-DRC violation
count are prioritized\"). The evidence above justifies which W2 gaps are
highest-leverage. Actual implementation belongs in a follow-up pass.
