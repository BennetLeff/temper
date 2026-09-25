# Operating-matrix campaign consolidation (draft)

**Status: `DRAFT_PENDING_SW_PREFIX_AND_BYPASS`.** This report consolidates the source-bound model evidence and protection requirements. It does not add acceptance claims, widen a criterion, or qualify hardware. The remaining SW-SHORT prefix disposition and BYPASS-NEG complete capture are acceptance-dependent and intentionally unresolved.

## Scope and operating target

The campaign evaluates the authored Temper PFC surrogate over nine normal points and prepared fault graphs. The Breville Control Freak comparison is an approximately **120 V AC, 60 Hz, 1800 W mains-input** benchmark ([power target](power-target-105.md)); it is not an 1800 W DC-output or pan-heating requirement. No PMP10948 efficiency is inherited. The existing 15 A modeled input screen remains unchanged; at 108 V it permits at most 1,620 W at ideal PF, and at 120 V at most 1,800 W at ideal PF.

Normal results are discrete authored-model screens, not interpolation, thermal, SOA, magnetic, fuse, or hardware evidence. The accepted cold 120 V / 190 Ω baseline is [accepted-baseline-11](../accepted-baseline-11/acceptance.json); its 650 ms run uses a three-cycle settled window. The event-aware normal-v1 path accepts source-bound complete samples while preserving the legacy strict checker’s repeated-timestamp rejection; this is a measurement-contract distinction, not a claim that duplicate timestamps are physical behavior. The nine-point acceptance and minimum margins are recorded in [checkpoint 53](operating-envelope-checkpoint-53.md) and [margin review 89](normal-screen-margins-89.md).

| Case | Mains / load | Bus min–max | Input RMS | Drift | Disposition |
|---|---:|---:|---:|---:|---|
| LL01 | 108 V / 359.07 W | 385.676–387.716 V | 3.869 A | 0.1499% | accepted modeled screen |
| LL02 | 108 V / 705.40 W | 381.308–385.189 V | 7.510 A | 0.2726% | accepted modeled screen |
| LL03 | 108 V / 1242.52 W | 375.858–382.392 V | 13.412 A | 0.4156% | accepted modeled screen; limiting current/bus/drift case |
| LL04 | 120 V / 398.20 W | 385.202–387.442 V | 3.844 A | 0.1653% | accepted modeled screen |
| LL05 | 120 V / 783.85 W | 381.212–385.347 V | 7.420 A | 0.2749% | accepted modeled screen |
| LL06 | 120 V / 1383.94 W | 376.244–382.998 V | 13.199 A | 0.3873% | accepted modeled screen |
| LL07 | 132 V / 398.38 W | 385.328–387.507 V | 3.505 A | 0.1563% | accepted modeled screen |
| LL08 | 132 V / 785.86 W | 381.772–385.749 V | 6.699 A | 0.2508% | accepted modeled screen |
| LL09 | 132 V / 1392.35 W | 377.461–384.029 V | 11.890 A | 0.3551% | accepted modeled screen |

Minimum observed model-screen margins are: 1.587946 A to the 15 A screen (LL03), 5.723620 V to the settled-bus lower screen (LL03), 21.379610 V to the bus upper screen (LL01), 0.000844183195 fractional drift to the 0.005 limit (LL03), 112.223171 V to VD 500 V, 62.283860 V to VB 450 V, 260.977460 V to |VDS| 650 V, and 10.017774 V to |VGS| 25 V. Input-grid bounds ±0.001 V are tolerances, not physical headroom.

## Fault dispositions

| Case | Evidence and bounded metrics | Status |
|---|---|---|
| F2-START | [startup acceptance](../faults/startup-compact-analysis-23/acceptance.json): 6,025,180 rows to 89 ms; injection 74.9999995 ms; detector 75.9146064 ms; retained-off 75.9147132 ms; VD peak 167.183 V, VB peak 127.054 V, `|Lboost|` 14.527 A; channel already below 0.1 A 596 ns before detector; 1.244 A passive peak after detector | accepted exact startup modeled screens only; not settled 390 V, fuse, or hardware evidence |
| F2-CREST | [settled acceptance](../faults/settled-reanalysis-40/F2-CREST38/acceptance.json): injection 654.166666 ms; detector 654.227894 ms (61.228 µs); retained-off 106.628 ns later; channel already below 0.1 A 2.819 µs before detector; passive peak 8.879 A; full-trace `|Lboost|` 30.654 A | accepted exact source-bound modeled screens; causal interruption and physical F2 clearing remain unproven |
| F2-ZERO | [settled acceptance](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json): injection 658.333333 ms; detector 659.601272 ms (1.267940 ms); retained-off 106.768 ns later; channel already below 0.1 A 0.788 µs before detector; passive peak 3.715 A; full-trace `|Lboost|` 30.654 A | accepted exact source-bound modeled screens; initial transport/header failure and legacy strict rejection retained; causal interruption and physical F2 clearing remain unproven |
| SW-SHORT | Complete endpoint is unavailable: the saved attempt has 30,686,230 rows and stops before 0.662 s. The active process/session identifier `33018` is not a row count. A separate own-prefix scan reports 30,112,476 selected rows in pending review 117; neither can establish a complete fault envelope or whole-case result | **INDETERMINATE; bounded incomplete attempt, with prefix review pending; no blind rerun implied** |
| DIODE-SHORT | [campaign verdict](../faults/settled-diode-short-64/full-DIODE-SHORT/campaign-verdict-98.json): complete 32,309,024-row trace; injection 654.166666 ms; detector 657.287927 ms, 3.121261 ms after injection, outside unchanged 2 ms window; normal prefix and phase separately accepted | **FAIL** timing window; diagnostic success does not change electrical disposition |
| BOTH-SHORT | [campaign verdict](../faults/settled-both-short-65/full-BOTH-SHORT/campaign-verdict-118.json): complete 32,036,953-row trace to 0.662 s; all-row `Lboost` 435.790782 A > 100 A screen; formal `ProtectionGap` checker was not reached because node screens precede it; same-row diagnostic shows gate/off signals with continuing failed-branch current | **FAIL** unchanged all-row screen; no protection pass or physical current claim |
| BYPASS-NEG | Active process/session identifier `28321` is not a row count. The captured row count is not yet established; complete endpoint, waveform, and validator disposition remain unavailable | **PENDING; no pass can be inferred from a clean transport run** |

## Protection graph and functional interpretation

The frozen graph keeps F2 as the VD-to-VB path and models F2 opening as an ideal scripted state change. With F2 closed, the diode-short/both-short graph permits stored-bank energy through `Cbank → F2 → VD → shorted diode terminal → MOS/channel path → node 0`; the VD local capacitor is a separate reservoir. Source-fed `Lboost → switch node` current is distinct from this bank-discharge path. Voltage detectors observe VD/VB conditions and do not directly allocate current among F2, diode, body, MOS, or local-capacitor paths. Source-return ISENSE is therefore not a complete stored-energy measurement.

Protection functions that remain requirements rather than proven implementation are: a gate-independent and F2-independent interrupting path for a failed MOS channel; defined clearing time and interrupted energy; safe failure and restart interlock; F2 isolation across startup, charged, discharged, and residual-energy states; detector coverage of each fault mode; qualification of the assumed negative ISENSE clamp; and requalification of the graph if a reference D2 inrush bypass is adopted. The reference D2 path can bypass the boost inductor and MOS-controlled conversion path, so existing fault evidence cannot transfer to that changed graph.

The checker’s VD 500 V, VB 450 V, switch-node 650 V, gate 25 V, `|Lboost|` 100 A, gate-off, channel-off, and passive-report values are frozen **model screens**, not component ratings or hardware qualification. The diode diagnostic’s sampled -326.5 kA branch extreme and BOTH-SHORT’s 22.147 kA first off-state branch are idealized model observations with unproven mechanisms and no physical die/SOA meaning.

## Controller, clamp, magnetic, and reference bounds

The selected clamp remains an assumed model with unresolved low-current forward-voltage, leakage, temperature, and lot bounds. The clamp audit records TI’s -0.438 to -1.1 V functional window and the selected BAV23C’s missing guaranteed low-current VF-versus-temperature/lot envelope; its fixture limits are engineering screens, not vendor limits ([clamp evidence gap](clamp-evidence-gap-review-49.md)). The campaign inductor is a fixed 180 µH / 20 mΩ model. The retained Würth package is a separate linear RLC vendor asset, not adopted into the campaign, and omits nonlinear DC-bias, saturation, temperature, and thermal behavior ([vendor-model review](inductor-manufacturer-audit-72/vendor-model-review-73.md)); the datasheet’s 180 µH ±20%, 20 mΩ maximum DCR, 24.5 A thermal rating, and 43 A typical saturation criterion are not encoded as guarantees.

The local UCC28180 surrogate and protection path are behavioral. TI’s encrypted TINA transient and PSpice average assets are available but not open ngspice transient models; no vendor correlation has been performed ([vendor-model availability](ucc28180-vendor-model-availability.md)). [Reference deviations 107](ucc28180-reference-deviations-107.md) records EVM and TIDA-00779 Rev D differences in current sensing, feedback/follower, compensation, frequency, bias, gate driver, magnetics, and D2 inrush connectivity. Those references are comparison evidence, not automatic component qualification or an adoption decision.

## Hardware questions and pending work

Later hardware evidence must measure synchronized line/bridge/inductor/shunt current, VD/VB, VDS/VGS, gate-enable, ARM/PERMIT/fault, controller state, rails, temperatures, probe settings, calibration, and raw traces. It must separately establish source-current interruption, stored-energy handling, clearing time, device survival, restart behavior, clamp behavior, magnetic loss/saturation, capacitor ripple, and any D2 inrush path. The hardware document is an observation/comparison specification, not an energization authorization.

Acceptance-dependent sections intentionally remain open: SW-SHORT prefix review and its missing endpoint, BYPASS-NEG complete capture and waveform/validator disposition, final reproducibility/index closure, and full goal-audit signoff. This draft therefore supersedes neither the per-case acceptance receipts nor the pending statuses.

## Report references

[Checkpoint 53](operating-envelope-checkpoint-53.md) · [Margins 89](normal-screen-margins-89.md) · [DIODE verdict 98](../faults/settled-diode-short-64/full-DIODE-SHORT/campaign-verdict-98.json) · [DIODE stress review 103](../faults/coincident-stress-observability-99/parent-result-review-103.md) · [Power target 105](power-target-105.md) · [Reference deviations 107](ucc28180-reference-deviations-107.md) · [Reference review 111](reference-parent-review-111.json) · [Completion correction 115](completion-audit-correction-115.md) · [Protection requirements 116](protection-requirements-116.md) · [BOTH verdict 118](../faults/settled-both-short-65/full-BOTH-SHORT/campaign-verdict-118.json) · [BOTH stress review 120](../faults/coincident-stress-observability-99/parent-both-result-review-120.md) · [Requirements index 122](requirements-index-parent-review-122.json).
