---
title: "Net-41 corridor execution and admission evidence"
date: "2026-09-01"
category: pcb-design
scope: bounded-scratch-only
---

# Net-41 corridor execution and admission evidence

This directory executes the immutable 2,880-candidate Net-41 In3.Cu dogleg declaration in `docs/evidence/net41-route-layer-corridor-20260831`. Rust owns candidate identity, exact coverage, veto ordering, terminal classification, and selection. `run_campaign.py` only stages complete KiCad projects and transports instrument evidence.

The run verifies fresh pyo3 extensions and the live asymmetric pcbnew rotation oracle before crediting geometry measurements. It also regenerates the KiCad rules and repeats normalized baseline DRC three times before screening or candidate materialization. Only a fully trusted preflight may enter the exact 2,880-row prefilter and live materialize/admit/route path.

The unchanged baseline DRC reproducibly reports `W:silk_overlap` at KiCad's known 199-item reporting cap. The three runs also returned multiple normalized `creepage` violation sets despite agreeing on the count. A capped set remains a saturated floor, and a stable count with changing members is not repeatable evidence. Requirement R8 therefore forces `instrument-error` before screening, materialization, hard-veto admission, or routing. The receipt reports the exact 2,880 declared-candidate denominator but correctly credits zero measured, materialized, routed, or admitted candidates; it does not turn the inherited instrument defects into candidate failures.

`baseline-drc-preflight.json` records the three normalized runs and the cap diagnosis. If the cap and set instability clear in a future tool or baseline, the same driver enters its now-tested live path: Rust emits each exact materialization instruction, every prefilter survivor is staged with the complete named pre-route instrument set, the Rust-returned eligible prefix is routed through the public target-net path, and full post-route admission stops at the first admitted board or the declared 12-route limit.

The terminal receipt is serialized by Rust. The runner content-hashes every instrument payload, while Rust validates each receipt's required name, declared subject hash, and receipt-hash shape; the compact candidate manifest links back to the terminal receipt hash. The runner's `--replay` mode regenerates and byte-compares the baseline, candidate manifest, and terminal receipt, and passed during branch validation.

The result is scratch-only. `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` remain byte-identical, and no result in this directory claims qualified standards approval, fabrication release, board-wide barrier closure, or production-promotion authority.

Replay with:

```bash
uv run --no-sync python docs/evidence/net41-corridor-execution-20260901/run_campaign.py --replay
```
