---
title: "Net-41 corridor execution and admission evidence"
date: "2026-09-01"
category: pcb-design
scope: bounded-scratch-only
---

# Net-41 corridor execution and admission evidence

This directory executes the immutable 2,880-candidate Net-41 In3.Cu dogleg declaration in `docs/evidence/net41-route-layer-corridor-20260831`. Rust owns candidate identity, exact coverage, veto ordering, terminal classification, and selection. `run_campaign.py` only stages complete KiCad projects and transports instrument evidence.

The run verifies fresh pyo3 extensions and the live asymmetric pcbnew rotation oracle before crediting geometry measurements. It also regenerates the KiCad rules and repeats normalized baseline DRC three times before screening or candidate materialization. Only a fully trusted preflight may enter the exact 2,880-row prefilter and live materialize/admit/route path.

The unchanged baseline DRC reproducibly reports `W:silk_overlap` at KiCad's known 199-item reporting cap. The three runs also return provider-selected raw `creepage` and `unconnected_items` records whose engineering multisets agree. A capped set remains a saturated floor, and a stable count with changing raw members is not exact whole-board evidence. The current instrument therefore retains the raw fringe, compares only the production-proved provider-equivalent categories semantically, and resolves the candidate-changeable silk cone through an exhaustive Rust-validated scoped receipt. `baseline-drc-preflight.json` records the three raw and semantic envelopes, the saturated global floor, and the complete 1,148-pair scoped ledger.

The live replay reached an honest terminal result: all 2,880 declared candidates survived the immutable geometric prefilter, were materialized, and received conclusive pre-route measurements; none survived pre-route admission, so routing was neither necessary nor credited. Every candidate was connected, route-geometry-valid, current-capacity-valid, mutation-scope-valid, and had agreeing DRC semantic repeats. All 2,880 carried `J1:missing-geometry`, which is a model-completeness finding rather than proof that J1 lies outside the board, and worsened one safety signature. Netlist reconciliation was not evaluated because it is post-route-only; the legacy `netlist_reconciled: false` field records that unevaluated stage and did not contribute a pre-route veto. All candidates had zero worsened hard DRC observations and zero new scoped-silk findings. The Rust terminal status is `exhausted` under the historical campaign-v1 contract, with zero admitted and zero untested eligible candidates.

The terminal receipt is serialized by Rust. The runner content-hashes every instrument payload, while Rust validates each receipt's required name, declared subject hash, and receipt-hash shape; the compact candidate manifest links back to the terminal receipt hash. The runner's `--replay` mode reruns and byte-compares the baseline, candidate manifest, and terminal receipt when exact provider bytes are expected. For interruption recovery under provider-only raw churn, use the v4 semantic checkpoints instead; they remeasure only work whose engineering identity or instrument context changed.

The result is scratch-only. `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` remain byte-identical, and no result in this directory claims qualified standards approval, fabrication release, board-wide barrier closure, or production-promotion authority.

Replay with:

```bash
uv run --no-sync python docs/evidence/net41-corridor-execution-20260901/run_campaign.py --replay
```
