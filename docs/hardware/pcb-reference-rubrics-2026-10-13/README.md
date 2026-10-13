# PCB reference rubrics for Temper

These six resource reviews turn the downloaded PCB and electronics references into questions, evidence requirements, design advice, and conditional trade-offs for a later Temper review. They are preparation for evaluating a board; the criteria have not been scored against its copper, assembly, or operating measurements.

The subsequent [stage19b assessment](../pcb-rubric-review-stage19b-2026-10-13/README.md) scores all 179 criteria against a separately verified successor PCB. The stage15b identity below records the original preparation context.

## Hardware identity and scope

The context used for tailoring is the native-21 stage15b full-bridge candidate identified by `hardware/CURRENT.tsv`. The pinned files and guard were read from the primary checkout at `/Users/bennet/Desktop/temper`; they were not present in the research-base commit or the current publication checkout. Run the baseline commands in the checkout that contains that pinned manifest and guard, and use `sources.json` to resolve the recorded context. Publishing the rubric does not publish or update the hardware snapshot. The baseline guard passed on 2026-10-13, checking 69 pinned inputs. Selected PCB SHA-256:

`9a9c43c63f63d383c89b9dc1d4d03a34d4390cfa1c26bbe802d71e169c6ddf94`

The manifest and source snapshot establish the scope of the eventual questions. They do not establish manufacturing readiness, operating margins, compliance, or applicability to a newer producer revision. Re-run the baseline guard and explicitly select the reviewed board before using this package to report findings. If the candidate changes, retain this research but reassess every board-specific application against the successor identity.

The pinned source describes a mains-fed, non-PFC full bridge with a series resonant tank, isolated control and measurements, and separate hot-side return functions. Its nominal coil-dependent values are provisional. Its `OCP_KELVIN_P` reference carries specified auxiliary/protection return current; the eventual reviewer must model that load rather than assume that the word Kelvin implies zero current. Resolve references and nets from the pinned schematic/netlist before attaching any criterion to a component.

Historical half-bridge reports provide methodological lessons only. Their component references, thresholds, coil assumptions, DRC counts, and readiness conclusions are not stage15b findings.

## The six resource reviews

Six GPT-6 Sol subagents produced 179 source-specific criteria. The books received chapter surveys and detailed reading of the areas relevant to Temper, with sampled or deferred specialist material explicitly recorded; this is not a claim that every page and exercise was studied. AN-139 was read across all 23 browser-print pages. The six rubrics contain roughly 31,000 words in total.

The [combined trade-off guide](tradeoffs.md) reconciles advice across the resources. The [criterion index](criterion-index.md) lists all 179 review questions, and [sources.json](sources.json) records source identities and the hardware context used.

| Review | Primary use |
|---|---|
| [Bogatin practical PCB guide (28 criteria)](bogatin-practical.md) | Design workflow, part selection, stackup, placement, routing, fabrication, bring-up |
| [Ott EMC engineering (35 criteria)](ott-emc.md) | Coupling, ground/reference topology, filtering, shields, cables, system EMC |
| [Bogatin signal and power integrity (29 criteria)](bogatin-sipi.md) | Edge rates, interconnects, crosstalk, discontinuities, decoupling and measurement |
| [The Art of Electronics (37 criteria)](art-of-electronics.md) | Component behavior, analog accuracy, power devices, operating limits and faults |
| [Trilogy of Magnetics (29 criteria)](trilogy-magnetics.md) | Magnetics, bias, saturation, losses, filters and application-dependent selection |
| [ADI AN-139 (21 criteria)](an139.md) | Switching-state current loops, placement, adjacent return layers and EMI |

Each review records the actual source copy, its hash, reading coverage, and citation conventions. PDF file page numbers are one-based and may differ substantially from printed page labels. The EPUB uses chapter, section, and internal file identifiers rather than invented page numbers. The Art of Electronics download is a scan and requires OCR; verify equations, ratings and tables against the original page image before acting on them.

## Source reading and extraction limits

The per-resource coverage maps distinguish detailed reading from surveys, samples and deferred topics. They also record selected figure checks. Original page images take precedence over extracted text for equations, units, tables and topology. In Ott, a microampere value is mistranscribed by text extraction as milliamperes. The Art of Electronics scan has a tall foldout containing two printed pages plus duplicated chapter-opening pages, so a single page offset is invalid; the apparent missing printed page 321 is present on the foldout. The AN-139 browser print has blank Figures 7, 9, 12 and 24; its rubric does not infer their unseen contents. These issues qualify the cited local copies, not the authors' engineering guidance.

## How to use the rubrics

For each applicable criterion, record the exact board identity, component/net mapping, operating condition, evidence location, conclusion, reviewer, and follow-up. Start unassessed criteria at U. Documentation of an intended topology is evidence of design intent; measured operation is separate evidence.

| State | Meaning |
|---|---|
| 0 | Evidence demonstrates failure against the applicable requirement |
| 1 | A material concern is identified and needs resolution |
| 2 | The design has a supported rationale but required verification remains |
| 3 | Evidence demonstrates the specified margin over the required conditions |
| U | Information is insufficient to reach a conclusion |
| NA | The criterion is inapplicable, with the reason recorded |

The scores organize follow-up. They are not physical quantities and should not be averaged into a manufacturing, mains-operation, or compliance verdict. A safety-critical unknown or failure remains open even if unrelated criteria are strong. State the target, operating envelope, uncertainty, and acceptance basis before assigning 3; a nominal oscilloscope trace or a DRC pass alone does not establish worst-case margin.

## Evidence to collect before applying the books

1. **Identity and connectivity:** manifest, full PCB hash, schematic/netlist parity, actual part numbers, footprints and assembly configuration.
2. **Operating envelope:** line range and transients, switching modes, actual rise/fall times, dead-time states, startup/shutdown, burst behavior, pan and coil range, ambient/cooling conditions and defined faults.
3. **Physical construction:** manufactured stackup, copper thickness and tolerances, dielectric thickness, board material, thermal interfaces, enclosure, shields, connector and cable geometry.
4. **Component operating behavior:** relevant datasheet revisions, capacitance under bias/temperature, current and pulse limits, switching/drive losses, magnetic bias and AC losses, isolation ratings and actual qualification conditions.
5. **Measurements:** specified instrument, probe/reference connection, bandwidth and uncertainty; waveforms and thermal/EMC results tied to the operating state and assembly.

The source books teach mechanisms and design methods. Current device datasheets, selected manufacturer capabilities and the applicable product requirements supply the numerical acceptance limits.

## Sequence for an eventual board review

### 1. Establish the domains and switching states

Draw the hot and SELV circuits, protective earth/chassis connections, isolated supply returns and cable interfaces. Enumerate conduction and dead-time states for both bridge legs. For each transition, derive which branch currents change rapidly; identify each local DC-link commutation loop, gate loop, tank path and sensing return. Avoid equating a high-RMS-current path with the largest switched-current difference loop.

### 2. Review placement before routing details

Check the physical capacitor-switch-return geometry, gate driver and its local supply loop, current-sense pickup, hot-side protection references, isolation boundaries and thermal attachments. Placement is the strongest lever for loops and coupling; extra routing rules cannot necessarily repair a topology imposed by poor placement.

### 3. Review stackup and copper by function

Check the return/reference for each sensitive or fast route, particularly at a layer transition. Separate safety clearance/creepage questions from signal-return questions. Inspect switched-node copper, nearby structures, cable exits and heat paths together. Evaluate neck-downs and vias for RMS heating and transient inductance; do not approve an entire power net from its widest trace alone.

### 4. Audit the BOM at operating conditions

Review each part's complete role: tolerances, bias, temperature, voltage/current waveform, ripple/pulse stresses, losses, mounting and footprint. Include the selected alternatives in the same audit. A component with the same nominal value or package is not necessarily an electrical or assembly substitute. Historical part tables are educational references, not evidence of current availability.

### 5. Evaluate sensing and fault behavior

Trace the entire signal plus return path and its exposure to magnetic, capacitive and shared-impedance coupling. Build the error and timing budget for threshold decisions. Include power sequencing, unpowered interfaces, disconnects, bias collapse, protection latency and the energy delivered before interruption. Distinguish a protection circuit's intended logic from demonstrated end-to-end fault behavior.

### 6. Close the loop with measurements

Use staged measurements to validate the predicted mechanism. Switching, thermal and EMI outcomes depend on coil/pan, wiring, enclosure, operating mode and cooling. Use the actual representative assembly and characterize the changes between nominal, worst-case and fault conditions. When evidence contradicts a prediction, verify the setup and source identity before changing the design.

## Decision record for a proposed change

Record the criterion and source section, the observed problem, the coupling/current/thermal mechanism, the proposed geometry or component change, at least one practical alternative, the expected benefit, adverse effects, numerical acceptance basis and the test that can falsify the prediction. After testing, retain both the result and its conditions. This turns advice into an accountable design decision rather than a copied rule of thumb.

## Project methods retained from prior work

The project's [measurement convention lesson](../../solutions/best-practices/measurement-convention-must-be-stated-2026-07-28.md) requires explicit quantities: peak versus RMS, surface creepage versus air clearance, copper-edge spacing versus pad pitch, and package rating versus assembly performance. Its historical component examples do not transfer to the current board.

The [coupled resonant tank lesson](../../solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md) reinforces application matching and verifying the quantity that actually governs resonance. Measure the coil-plus-pan system in the operating band; do not substitute a similarly valued low-power wireless-charging part or free-air inductance for that evidence. Historical numeric models are not the current design's acceptance limits.

## Validation

The six local resource hashes were checked, as were the rubric digests, 179 distinct sequential criterion IDs, local document links, code fences and unfinished placeholders. Agents checked cited source sections and selected figures; the parent independently spot-checked Ott PDF p. 716, Trilogy PDF p. 338 and AN-139 PDF p. 3. These are sampled citation checks, not independent verification of every technical statement. The primary-checkout hardware identity guard passed again before publication. No board performance or criterion score was evaluated.

On the original research base `84c5e5b61000d45eec09834cb23e6bba8fa51169`, the import boundary gate passed with five contracts kept and no new violations, and regeneration completed with consistent derived artifacts. Remote main had subsequently retired those legacy gates. The final publication branch is based on remote main and contains only this documentation package; no legacy code from the primary checkout was carried into it.
