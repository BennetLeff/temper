# BYPASS-NEG feedback and local-VD topology review

This is a bounded topology review of the complete BYPASS-NEG capture. It does not modify the circuit, thresholds, or acceptance criteria and does not infer exact dynamic causality from a static graph.

## Source and disposition

The materialized case uses `Rfb1 vb vsense 1meg` and `Rfb2 vsense 0 13k`; the UCC28180 surrogate therefore receives its voltage-feedback signal from **VB**, the bank node. `Clocal=19.8u` is connected from VD to node 0, `Cbank=2240u` from VB to node 0, and F2 is `Sf2 vd f2_path ...` followed by `Vf2sense f2_path vb 0`. At the declared fault, F2 opens VD from the VB bank path. The protection include sets `BYPASS=1`, making `Bfault` force `fault_raw` low regardless of the VD/VB comparator channels.

The parent capture review records a complete 32,287,070-row archive to 0.662 s, raw SHA-256 `75f444f8e422e445c2e5d65f21760af1658f0b14f05dcd088d1c80cd2b87b0a1`, and an unchanged all-row screen failure: `VD=651.1730124191079 V > 500 V`. Adapter diagnostics report no detector rise, no latch-off, and channel current above 0.1 A through the endpoint. Because the all-row screen precedes the formal checker, the bypass-flag rejection was not reached; this is not an acceptance or protection pass.

## Connectivity implication

When F2 is open, VB remains the feedback source while VD and its 19.8 µF local capacitor are separated from VB by the open switch. The controller’s feedback/OVP surrogate can therefore continue to regulate or assess the bank node without directly sensing the isolated VD node. The VD comparator network is present in `protection.inc`, but BYPASS=1 suppresses its contribution to `fault_raw` in this negative-control deck. These are direct netlist/connectivity facts.

The graph supports the concern that local-VD overvoltage or local-capacitor energy can evolve without the VB feedback signal immediately representing it. The capture’s 651.173 V VD screen failure demonstrates an observed model excursion, while the absence of detector/latch transitions is consistent with the explicit bypass. It does **not** prove that feedback disconnection caused the excursion, nor does it establish a physical response time, energy, or component failure mode.

## Requirements for a reference-anchored revision

Any revision that opens F2 or otherwise permits VD/VB separation must define and independently verify:

1. A local-VD protection path that remains active when VB feedback is disconnected, including its detector timing, latch/enable response, and safe restart state.
2. An energy-interruption path for VD local capacitance and source-fed inductor current that does not rely solely on VB regulation or the failed MOS gate command.
3. F2 open-state indication and restart behavior for charged, discharged, and residual VD/VB energy.
4. A negative-control test in which detector bypass is rejected by the validator before any electrical result could be mistaken for a pass.

These are functional requirements, not selected parts or proposed threshold changes. The protection requirements in [116](protection-requirements-116.md) and the reference review in [111](reference-parent-review-111.json) already state the bank/local-energy and graph-change boundaries. A reference D2 inrush bypass would add another rectifier-to-bus path around the inductor/MOS conversion path; existing evidence cannot be transferred to that changed graph without requalification.

## Evidence hashes

The review is bound to the following regular files:

| File | SHA-256 |
|---|---|
| `full-BYPASS-NEG/case.cir` | `c6ea3dca688918137282ed3fd3d0ffa17c2b740d68ab52bab306ee3e8b228180` |
| `full-BYPASS-NEG/protection.inc` | `d9b499bbba3f2636ac926a3c8782943d3144798cfe4faa765ceaf7774628a025` |
| `full-BYPASS-NEG/manifest.json` | `4066ac5bf595b4aaca1b99c79035b5729d20bb217ffe1e5f3a4b6ca6a0003e01` |
| `full-BYPASS-NEG/run-parameters.json` | `01ea97089a40842d1e5ac38dd1f5f53f58cc3e71cea110051be638acba9782e5` |
| `full-BYPASS-NEG/parent-capture-review-130.json` | `a921f3cc6ca1a5532ceac537f91569b9d2174862532f2ee05e321aae23f5a770` |
| `full-BYPASS-NEG/result.json` | `1155dbbaf4d9994404fe8a5ad8f8c122cb8254226856d371cea3a84cacc55692` |
| `full-BYPASS-NEG/adapter-report.txt` | `ab797a28a30ef27ad4a2831dbfdea112e4041082adff80709cb7857323c21af4` |

