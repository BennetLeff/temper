# D27 coverage and exclusions

Base: `212c497f9e762f87ed59ba38842dfaeedc7aa538`. The machine-readable [coverage index](coverage-index.json) enumerates every nonblank DECISIONS / STATUS / FINDINGS line and the overlap IDs that cite it. All substantive decision entries, question rows, work rows other than D27 itself, F1–F8, M1–M10, S1–S13 and outside-input rows have mappings. Repeated statements map to the same subject instead of artificially increasing the count. [Inventory receipt](inventory-check.json).

The only nonmapped lines are table headings, STATUS:3–6 navigation/date, STATUS:61 introduction, STATUS:90 this assignment's own “brief written” progress, FINDINGS:3–9 navigation/status definitions, and their headings. None is an additional design choice. Dates in the introductions do not override the later dated entries. Read the actual rows rather than trusting the header's last-updated date. [coverage-index.json](coverage-index.json).

## Packet coverage

| Source packet | Overlap rows | Review boundary |
|---|---|---|
| DECISIONS D1–D6 and native revisions | R01–R07, R12–R15, R59–R67 | Every dated/ID entry is line-mapped, including source parts, native18 approval and native19 R5 integration. |
| Cooling and manufacturing | R01–R14, R43–R45, R58, R64–R68 | Contact/insulator geometry, thermal/flow requirements, supply, PE, enclosure and physical-release holds. |
| EMI intake and round2 D22 | R40–R46 | Original periodic margins versus later startup/load-law/installed-coupling limits. No new RF simulation. |
| Conditional power, round2 D17, round3 control-energy, round4 joined model, round5 model/protection | R16–R20, R47–R52, R56–R60, R73–R74 | Reference planes, gate-off versus stored energy, accessory topology/parts, initialization and abort limits. |
| Round3 packaging/inlet/integration and round4 catch | R40, R47–R51, R61, R66–R67 | Outside filter-volume hardware and later PC125/catch revisions; no approval of historical resistor or fuse selection. Latest round5 sources supersede their own round3 detail where stated. |
| Round4 supervisor/firmware, round5 target/boards | R21–R39, R66, R69, R74–R76 | Separate STM32/ESP32 roles, pin/control policy, actual failed-init source inspection, sensing and capture gaps. |
| Round4 fields and round17 matrix/methods | R14, R53–R57, R70–R73, R78 | Both-leg availability, distinct reference geometries, signed pairs, bulk limits, source identity and incomplete solves. |
| Hardware summaries changed in #1647 | R12–R15, R37, R52, R58–R68, R72, R77 | POWER-SECTION, COIL-MC, LOSS-REFACTOR plus their Rust/output pairs. Comparative model outputs remain conditional; no heavy build or numerical replay. |

The file census covers every tracked file in `prototype-closure/` and `docs/hardware/power-section-120v/` (770 at this base). This is a *semantic overlap inventory*: generated symbols, routes, sensor ladders, data logs and archive members are supporting artifacts of their packet, not 770 independent owner decisions. The study does not independently inspect all electrical pins, solve FEM, or requalify device models. Source facts are traced through the cited primary narratives/code and committed receipts. [source-census.json](source-census.json), [citation-audit.json](citation-audit.json).

The hardware-summary changed-path list was checked with `git diff 966dbf849e0d8f770d01f428cdc031d038c8b309^1 966dbf849e0d8f770d01f428cdc031d038c8b309 --name-only -- docs/hardware/power-section-120v`: COIL-MC.md, LOSS-REFACTOR.md, POWER-SECTION.md, coil_mc.rs, coil-mc-output.txt, power_section.rs and power-section-output.txt. The three narratives explicitly label comparison/screening limits; rows R52/R58/R68 carry that qualification rather than treating the output files as independent operating approval.

## D20 requirements crosswalk

D20 is supporting detail for the controller entries, not a third independent decision authority. Requirement numbers below refer to `out-D20/CONTROLLER-REQUIREMENTS.md`; exact source lines are in the row citation audit.

| D20 requirements | Overlap rows |
|---|---|
| R01–R04, R15–R18 (power, returns, harness) | R36, R76 |
| R05–R08, R21 (four PWM outputs) | R22, R23, R28 |
| R09–R10, R30–R34 (PERMIT, BUS_FAULT, dynamic chain) | R29, R35, R49, R52, R74 |
| R11–R12, R35–R48 (native bus sensing) | R31–R35, R75 |
| R13–R14, R49–R52 (tank CT) | R25, R37–R38 |
| R19–R20 (reset/partial power, grounding) | R27–R29, R45, R76 |
| R22–R29 (operating/timing/update/capture policy) | R16, R20–R26, R39, R69, R73 |
| R53–R54 (other safety interfaces and release identity) | R39, R58, R65–R67, R76 |

ONE-SIDED rows preserve obligations that are not implemented in the cited prototype contract; a related ADC or supervisor cannot close them by name similarity. CONTRADICTS is reserved for two incompatible stated choices or a source implementation that misses an explicit current requirement. Historical diagnostic values and deliberately inhibited test settings are not falsely classified as deployed contradictions. See README C1/C2 and rows R21/R31–R35.
