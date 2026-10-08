# Standalone RTD unit acceptance

**Model review update, 2026-09-11:** the [model-correctness follow-up](../model-correctness/README.md) replaces the unsupported scalar timing claim with a continuous-range passive-network certificate, independently recomputed in Rust. Its conditional maximum is 0.971460 ms against 2 ms. The [new report](../model-correctness/qualified-input/report.json) passes mathematical qualification while retaining device applicability and brownout timing as INDETERMINATE. The layout/native evidence and historical bundle below are unchanged; this update does not qualify all inherited model assertions or authorize fabrication.

The standalone RTD design/layout milestone is accepted on 2026-09-10.
This follows the user's direction to build each unit separately before cooker
integration. It is not fabrication release, physical qualification, or acceptance
of the integrated cooker.

Accepted board SHA-256:
`d9908e58335fc9e20d9d786af4423ba8844d7ee893a08dc99472a3dd357653cb`.
The [owner receipt](evidence/acceptance-final/receipt.json) binds 90 canonical
files and 102 frozen files. The coordinator independently checked every hash,
replayed the final and earlier-board Rust reports, checked native report contents,
and reviewed the final front and In2 layer renders.
See [independent bundle review](evidence/root-final-bundle-review/receipt.json).

| Required deliverable | Acceptance evidence |
|---|---|
| Circuit, interfaces, error and fault behavior | [Circuit contract](../circuit/rtd_contract.json), executable passive/static/transient models and [independent observation replay](evidence/root-circuit-final-review/receipt.json). Healthy behavior, each of four conductor opens and short transitions are separate cases. Accuracy and timing claims remain bounded models under stated assumptions. Local supply-loss ownership and upstream-loss host inhibit are explicit. |
| Atopile-derived standalone schematic/PCB | `elec/src/rtd_unit.ato:RTDUnit`, retained generation evidence, exact 36-component/119-pad source census and [identity retained after return corrections](evidence/root-return-identity-01/receipt.json). Exact instances, MPNs, pad UUIDs and nets survive the flow. |
| Rust engineering validation | 53 passing tests across the frozen suite; 27 registered checks evaluated on the real unit. Current report has zero failing findings and exactly the deferred timing result below. [Independent final replay and four additional input mutations](evidence/root-final-rust-replay/receipt.json) confirm missing required fault data cannot silently pass, incorrect detection and excessive latency fail, and ground-via removal fails return checks. |
| Agent placement/routing and actual feedback | Explicit native edit records; preserved RTDIN− copper deletion/correction [reproduced independently](evidence/root-open-correction-replay/receipt.json). With the final executable, the earlier board produces 14 return findings and the corrected board produces none. This is an actual source-to-board editing and validation loop. |
| Independent native verification | [Final native receipt](evidence/native-final-02/receipt.json): three KiCad 10.0.4 DRC runs with schematic parity, all-track errors and all severities have zero violations, opens and parity findings; ERC has zero included findings. The ignored-check inventory is retained. All 18 native input hashes match. |
| Reviewable next-owner handoff | [Handoff](HANDOFF.md), exact 36-instance/20-group [BOM](bom/pcb-bom.csv), [dated procurement review](bom/availability-review.md), power/SPI/probe/fault/reference boundaries, [bench outline](BENCH-OUTLINE.md) and [reviewed lessons](LESSONS.md). |

## Exact deferred result

The overall Rust result remains **INDETERMINATE** for
`ERC.RTD.FAULT_CORNERS / local_rtd_avdd_loss`: guaranteed worst-case brownout
timing is unproven. The TPS3890 table gives a nominal response under specified
conditions, not a maximum. Static threshold/NAND ownership is checked separately.
The standalone plan defers actual shutdown timing to characterization and
integration; this specific result is therefore outside layout acceptance.

This is not a generic indeterminate exemption. Missing SENSE+ observations, for
example, produce a separate required-input indeterminate and block unit acceptance.
Any new or different indeterminate, failing check, or changed source/board/suite
identity requires another acceptance review.

The modeled under-100 ms system response includes brownout as well as probe
faults. Characterization must close the allocated response budget or trigger a
redesign before integration acceptance. No powered-high fault is guaranteed
when the upstream supply itself disappears.

## Remaining build and integration obligations

- Physical accuracy, thermal/contact behavior, noise, probe wiring, transient
  response and shutdown measurements remain **NOT RUN**. The bench outline is
  a future procedure, not a completed session.
- Exact comparator availability and the precision RREF's authorized sourcing
  need procurement resolution. The snapshot is dated evidence, not reserved
  stock; it approves no substitution. Recheck the selected shipping channel.
- Fabrication/assembly capability and effective bypass-capacitance conditions
  remain build prerequisites. No order or fabrication was performed.
- Each following electrical unit has its own separate goal. Integration later
  composes their interfaces, validates cross-unit routing and reruns regressions.

The acceptance claim is the completed standalone unit and its working engineering
harness evidence. It makes no claim of a measured cooker or 100–1,000× comparative
validation coverage; those would require their own evidence.
