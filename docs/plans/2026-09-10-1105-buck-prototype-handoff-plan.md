# Buck Rev A prototype — handoff index

Created: 2026-09-10

## Outcome

Produce a build-ready, standalone 15 V to 3.3 V buck prototype: a reviewed board and schematic, an exact purchasing BOM and fabrication package, and an executable bench procedure. This is the next milestone before moving attention to the next subsystem. Hardware performance remains unverified until the physical tests are run.

These are execution plans for another agent. Writing these plans does not itself complete board design, release, assembly, or testing.

## Three assignments

| Assignment | Plan | Completion evidence |
|---|---|---|
| 1. Finish the standalone board | [Board and interfaces](2026-09-10-1105-buck-prototype-board-plan.md) | Matching schematic/PCB, real connectors, probe access, reviewed footprints, native ERC/DRC, frozen source manifest |
| 2. Prepare the build package | [BOM and fabrication release](2026-09-10-1105-buck-prototype-release-plan.md) | Exact BOM, dated DigiKey procurement mapping, verified Gerbers/drills/positions/drawings, hashes and reproducible export command |
| 3. Prepare first power-on | [Bring-up procedure and records](2026-09-10-1105-buck-prototype-bringup-plan.md) | Board-specific runbook, instrument capability checklist, empty results templates, explicit pass/fail/stop criteria |

Use a Luna agent for each assignment if parallel agents are available. The board owner is the only writer of CAD files and component fields. The release owner can research availability and prepare export tooling while the board develops. The bring-up owner can draft measurement procedures at the same time. Final exports and final pinout/probe illustrations wait for the board freeze.

No agent is alone in this checkout. Preserve others' changes, coordinate source corrections through the board owner, and never use `git stash`.

## Workspace and source authority

Start in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`, branch `codex/buck-harness-experiment-plan`. The planning snapshot has HEAD `a75ca538d87d6578917d0cb3a50da7f14ebdc210` and substantial uncommitted work. Read the current files and `git status`; do not reset to HEAD and thereby discard the actual source state. Paths below are relative to that worktree.

The existing Atopile `elec/src/modules.ato::BuckConverter3V3` owns the nine-component electrical core. The new manufacturing project will be `pcb/prototypes/buck-reva/`, named `buck-reva.kicad_sch`, `buck-reva.kicad_pcb`, and `buck-reva.kicad_pro`. Its schematic owns prototype connectors and test points and must explicitly reconcile the core against Atopile. Do not introduce a new code-generation framework for this one prototype.

Use `harness-lab/fixtures/buck-v2/buck-dev-a/witness.kicad_pcb` as the layout reference. Copy required sidecars and resolve them for the new project. Do not use the incomplete start/candidate board or develop against reserved variants. Existing fixture files remain historical benchmark inputs.

Read the current evidence before making new claims:

- `harness-lab/audits/buck-final-20260910/README.md`
- `harness-lab/audits/buck-final-20260910/components/current-buck-bom.md`
- `harness-lab/audits/buck-final-20260910/source-build/README.md`
- `harness-lab/audits/buck-final-20260910/full-scenario-readiness/README.md`
- `harness-lab/engineering/requirements.json`

## Shared interface decisions

| Item | Rev A default |
|---|---|
| Supply | Isolated bench DC, 15 V nominal; operating checks at 13.5, 15, 16.5 V |
| Output | 3.3 V, 0.5 A continuous design budget; 1 A for 10 ms is a test target |
| J1 | Two-pin input: pin 1 VIN, pin 2 GND |
| J2 | Two-pin output: pin 1 3V3, pin 2 GND |
| Connector style | Common 5.08 mm, two-position, vertical through-hole screw terminal; exact DigiKey-listed MPN selected by board owner, ≥3 A and ≥30 V |
| Test access | TP1 VIN, TP2 input GND, TP3 VOUT, TP4 output GND; compact SW access only if it does not enlarge the switching loop |
| Mechanics | 50 × 40 mm, two layers; top-side components; explicit fabrication stackup and finish selected and recorded before freeze |
| Build method | Generic small prototype batch, SMT reflow/hand assembly and hand-soldered terminals; no assembler-specific BOM imposed prematurely |

The fixture's J1/J2/J3 each have two pins on the **same net**. Replace those synthetic terminals in the new project. Do not preserve their pin assignments, copy their terminal-count requirement, or label them as conventional input/output connectors.

## Gates and ownership transfer

1. **Board ready for export:** plan 1 passes connectivity, footprint, physical review and native checks. It writes `pcb/prototypes/buck-reva/verification/board-freeze.md` and `source-manifest.json`, including file hashes and connector/testpoint map.
2. **Build package ready for review/order:** plan 2 exports that exact frozen revision and writes `release/release-checklist.md`. Board changes invalidate its exports and require a new freeze. An order-ready package does not mean an order was placed.
3. **Bench documentation ready:** plan 3 binds its runbook to the same revision. A completed runbook does not mean a powered board passed.
4. **Prototype demonstrated:** after assembly and operator-run testing, actual records identify which operating points passed, failed, or remain untested. This later state is distinct from the build-ready milestone.

Outputs are divided as follows:

- Board owner: CAD, local libraries, `source-manifest.json`, `verification/`, project `README.md`.
- Release owner: `procurement/`, `release/`, `export-release.sh` within the new project.
- Bring-up owner: `docs/hardware/buck-reva/`.

## Scope boundaries that prevent another qualification loop

Capacitor combined derating, hot-inductor behavior, and behavioral-model transient accuracy remain recorded qualification questions. They do not require another vendor/model research cycle before producing this controlled prototype. A newly discovered wiring, rating, footprint, or measured hardware defect is a real blocker and must be addressed.

Keep `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`, `harness-lab/engineering/approved-evidence.json`, existing fixtures, requirements, and simulator model unchanged. The production board hash at planning is `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9`. Production DRC-ceiling remeasurement applies if that board changes; do not modify it or apply a 120-run production ceiling exercise to the new standalone project.

Existing engineering/scored-pilot gates remain intact. “Prototype build-ready” must never be reported as “fully qualified,” “model validated,” or “approved engineering evidence.” Keep telemetry disabled. Do not purchase parts, place fabrication orders, send vendor messages, or energize hardware as part of preparing these deliverables.

At completion, each agent returns changed paths, exact verification performed, any failed or unrun checks, and the next owner's concrete inputs. Report blockers with a specific defect and smallest resolution, rather than reopening the entire buck investigation.
