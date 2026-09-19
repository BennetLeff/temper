# Passive power-entry milestone

Decision: 2026-09-19, user-directed. Develop the retained GBJ2510-F passive
power-entry section as the next integration baseline. Preserve the active
rectifier experiments; do not make their construction the critical path.

The objective is a protected, thermally defensible section. A routed board,
an explicit qualification plan, or a collection of passing numerical checks
alone does not complete this objective.

## Fixed scope

- Baseline: `../shunt-repair/candidate/section.kicad_pcb`, SHA-256
  `34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9`.
- GBJ2510-F bridge, UCC28180 PFC and STW65N65DM2AG boost switch. Preserve
  the validated geometry where a protection change does not require an ECO.
- Existing 120 VAC nominal, 108–132 VAC design envelope and 15 A RMS limit.
  Full nominal power at low line is not implied. Existing HOT-interface,
  precharge, isolation and surge obligations remain in force.
- Existing 40 °C cooling-inlet target. Sink, fan, duct, interfaces and heat
  budgets must refer to this GBJ assembly, not the superseded GBU assembly.
- No new active-bridge or frequency/device optimization campaign. No generic
  harness expansion. Use existing Rust and native KiCad validation.

## Completion evidence

| Requirement | Required result |
|---|---|
| Circuit identity | Authored source, compiled netlist, native schematic/PCB, purchased parts and reviewed hashes agree |
| Line-fed fault | Applicable interruption capability and clearing behavior, actual prospective fault envelope and explicit consequence for the bridge/copper |
| Internal bank fault | Identified current path for healthy and failed-short switches; demonstrated interruption or a supported containment disposition, with no credit to an out-of-loop shunt/fuse |
| F2 opening, if F2 is selected | First peak, continuing mains input, restart, controller timing and energy handling established together for the exact circuit |
| Installed cooling | Defined assembly and losses/envelope; interfaces and installed airflow support device, solder/PCB and accessible-surface limits, including fan-failure response |
| Construction | Fresh native ERC/DRC/parity and existing Rust checks on saved bytes; no suppressions or inherited result relabeling |
| Qualification | Every physical result required by the protection/cooling argument retained, or the milestone remains incomplete |

The GBJ model's 40 W dissipation and the assembly's other heat allowances are
design inputs, not established worst-case losses. The independent C7 switching
result cannot stand in for the retained STW part. An unknown total stays unknown.

## Work ownership

- `protection/`: Luna assesses and resolves the passive circuit's protection
  choices using retained and published exact-part evidence.
- `cooling/`: Luna defines and evaluates the GBJ cooling assembly and its
  qualification requirements.
- `candidate/`, `source/`, `native/`, `tools/`, `libraries/`: Luna prepares
  isolated source-bound CAD; coordinate protection ECOs before routing.
- Coordinator: integrate, review physical assumptions and actual changes,
  verify, and record the authoritative final status. No worker's PASS by
  itself closes this milestone.

Physical testing, purchasing, fabrication and third-party outreach have not
been performed by this work. Do not convert a missing observation into a
numerical assumption just to finish a row.
