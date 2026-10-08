# Temper review baseline

Reviewed 2026-10-03. This review compares both enclosure packages at the user's request and examines the newer electrical source candidate. It does not designate a fabrication release or replace another team's design authority.

## Input identity

The source checkout is `/Users/bennet/Desktop/temper`, HEAD `84c5e5b61000d45eec09834cb23e6bba8fa51169`, with existing modified and untracked work. The isolated research branch starts at that commit, but **the reviewed product includes untracked source not represented by HEAD**. [input-manifest.json](input-manifest.json) hashes 21 explicitly selected files; their byte-for-byte snapshots are in the local, Git-excluded `inputs/` directory. Snapshotting preserves evidence, not authority to modify or publish the other task's original packages. A fresh clone of the research branch contains the review and hashes, not these working-source snapshots.

| Scope | Selected evidence | Status in the source |
|---|---|---|
| Folded aluminum enclosure | `output/temper-folded-aluminum/verification.json`, bend layout, geometry checks | Computed geometry with limits; provisional DXFs; no shop bend, structural, thermal, or electrical validation |
| Manufacturing R2 | `output/temper-manufacturing-r2/CURRENT.json`, README, change register, saved validation | Prototype review only; several geometry improvements; inherited click-window failure and unresolved cooling, glass, seals, controls, electrical interfaces |
| Current electrical candidate examined | `zapote/power-stage-120v/README.md`, Atopile source, audit, build receipt | Full bridge with unfiltered rectified bus; source compiled/audited according to saved receipts; native schematic/PCB and physical tests not run |
| Electrical assumptions | `docs/hardware/power-section-120v/{POWER-SECTION,COIL-MC,LOSS-REFACTOR}.md` | Analytical screens, assumed coil/pan distributions, part and hardware limits still open |

The historical `pcb/temper.kicad_pcb`, PFC revision records, and September 25 front-end decision brief are useful context but are not interchangeable with the selected full-bridge source. In particular, enclosure packaging of an older exported board cannot establish fit of a new board that has not yet been laid out. Do not import the old design's numerical creepage, heat-sink, power, or component assumptions into this candidate without rederiving their applicability.

## Review questions

1. Which product experience survives wet hands, poor visibility, interrupted cooking, pan changes, and cleaning?
2. Which mechanical interfaces are controlled by datums, tolerance bounds, compliance, or adjustment rather than nominal alignment?
3. Are thermal, insulation, electromagnetic, structural, and harness requirements co-designed across PCB and enclosure?
4. Can each protection path stop the specific fault, including a device already shorted, an unpowered rail, or a sensor that still returns plausible data?
5. Can a supplier build and an operator assemble/inspect/service the selected revision without guessing?
6. Which conclusions are directly reproduced, inherited from receipts, modeled under assumptions, or require a physical test?

Course material supplies methods for these questions. Component ratings, standards applicability, process capability, and measured hardware determine product acceptance limits. The course corpus itself cannot establish them.
