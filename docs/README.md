# Temper Documentation Index

This index maps every subdirectory and top-level file in `docs/`. Use it to
answer "where do I find X?" without grepping. For help, jump to the
[FAQ matrix](#where-to-look-faq) or the [conventions section](#conventions).

## Directory Tree

Each entry includes a short description of what the directory contains and when
to use it. Subdirectories of `solutions/` are enumerated inline because they
form a nested taxonomy.

| Directory | Description |
|-----------|-------------|
| `adr/` | Architectural Decision Records — formal, dated records of significant technical decisions with context and consequences. |
| `analysis/` | Data and trend analysis outputs (e.g., thermal field analysis, cost breakdowns). |
| `architecture/` | System architecture documents, component diagrams, and architectural critiques. |
| `audits/` | Formal audit reports (safety, security, code quality, regulatory). |
| `benchmarks/` | Performance benchmark results and run logs (firmware timing, solver speed). |
| `brainstorms/` | Structured requirements documents for scoped ideas — 100+ entries. Lightweight counterpart to `plans/`. |
| `bugs/` | Bug reports, reproduction steps, and diagnostic notes. |
| `closure-reports/` | Post-mortem and completion summaries for finished features, bug fixes, or experiments. |
| `experiments/` | Experiment writeups with methodology, data, and conclusions. |
| `guides/` | How-to guides: dev environment setup, walkthroughs, thermal design guidance. |
| `handoffs/` | Context-passing documents between contributors during multi-session work. |
| `hardware/` | Hardware design documents: schematics, BOM, mechanical drawings, thermal models. |
| `ideation/` | Idea sketches and early-stage design explorations — lighter than `brainstorms/`. |
| `legacy/` | Deprecated or superseded documentation retained for historical reference. |
| `metrics/` | Project metrics, tracking dashboards, and progress reports. |
| `plans/` | Implementation plans — 100+ entries. Each plan breaks a feature or fix into units with test scenarios. |
| `reports/` | Generated reports: test run summaries, DRC results, benchmark outputs. |
| `requirements/` | Formal requirement specifications and verification matrices. |
| `router/` | Router-specific architecture documents and evaluation reports. |
| `session-reports/` | Per-session agent or developer logs capturing what was done and why. |
| `solutions/` | Categorized, reusable solutions to recurring problems (see [Solutions taxonomy](#solutions-taxonomy) below). |
| `specs/` | Technical specifications: net classes, vias, PCB requirements, clearance rules. |
| `triaged/` | Triaged bug assessments: severity, scope, and recommended actions. |

### Solutions taxonomy

`solutions/` is organized into 10 subcategories, each holding documented fixes
for a specific class of problem:

| Subdirectory | Scope |
|-------------|-------|
| `architecture-patterns/` | Reusable architectural patterns extracted from past work. |
| `best-practices/` | Established practices for recurring development tasks. |
| `build-errors/` | Fixes for build system, linker, and compilation failures. |
| `conventions/` | Coding conventions, naming rules, and style decisions. |
| `design-patterns/` | Software design patterns applied in the codebase. |
| `logic-errors/` | Root-cause analyses and fixes for logic bugs. |
| `performance-issues/` | Diagnoses and resolutions for performance bottlenecks. |
| `test-failures/` | Reproductions and fixes for test suite failures. |
| `tooling-decisions/` | Rationale for tool choices, version pins, and workflow decisions. |
| `workflow-issues/` | Fixes for CI, git, review, and process problems. |

## Top-Level Files

All 25 top-level `.md` files are grouped by thematic category. Within each
category, entries are listed alphabetically.

### Procedures

Step-by-step instructions for recurring tasks.

| File | Description |
|------|-------------|
| `ASSEMBLY_GUIDE.md` | End-to-end assembly instructions for the Temper induction cooker. |
| `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` | Procedure for verifying safety-critical functional behavior against specified gates. |
| `FUNCTIONAL_TEST_PROCEDURE.md` | General functional test procedure for verifying feature-level correctness. |
| `HV_SAFETY_TEST_PROCEDURE.md` | High-voltage safety test procedure for isolation, clearance, and creepage. |
| `PLL_ZVS_INTEGRATION_GUIDE.md` | Guide for integrating the PLL-based zero-voltage switching subsystem into the firmware. |

### Design Specs

Formal technical specifications for subsystems and components.

| File | Description |
|------|-------------|
| `CHASSIS_AIRFLOW_DESIGN.md` | Thermal airflow design specification for the chassis. |
| `COIL_BRACKET_DESIGN.md` | Mechanical design specification for the induction coil bracket. |
| `CONNECTORS_AND_WIRING.md` | Connector pinouts, wiring diagrams, and harness specification. |
| `COOKTOP_PANEL_SOURCING.md` | Sourcing requirements and evaluation criteria for the glass-ceramic cooktop panel. |
| `ENVIRONMENTAL_SPEC.md` | Environmental operating limits: temperature, humidity, altitude, vibration. |
| `NET_NAME_MAPPING.md` | Mapping between schematic net names and physical board signals. |
| `PCB_SILKSCREEN_MARKINGS.md` | Specification for silkscreen labels, orientation marks, and reference designators on the PCB. |
| `SENSOR_MOUNT_DESIGN.md` | Mechanical design for spring-loaded pan sensor (RTD) mount ensuring consistent thermal contact. |

### Checklists

Pre-flight or quality-gate checklists used before key actions.

| File | Description |
|------|-------------|
| `LAYOUT_REVIEW_CHECKLIST.md` | PCB layout review checklist covering DFM, signal integrity, and clearance. |
| `PRE_FAB_SIGN_OFF.md` | Pre-fabrication sign-off checklist verifying all gates are met before sending boards to fab. |
| `SAFETY_TEST_CHECKLIST.md` | Safety test coverage checklist ensuring all protection circuits are verified. |

### Templates

Boilerplate documents for creating new files.

| File | Description |
|------|-------------|
| `COMPLIANCE_REPORT_TEMPLATE.md` | Template for regulatory compliance test reports. |
| `SAFETY_TEST_LOG_TEMPLATE.md` | Template for logging safety test results with pass/fail criteria and traceability. |

### Standards

Normative conventions: rules, limits, and regulatory requirements.

| File | Description |
|------|-------------|
| `FUNCTIONAL_TEST_CRITERIA.md` | Pass/fail criteria for functional tests. |
| `PCB_DFM_GUIDELINES.md` | Design-for-manufacturing guidelines for PCB fabrication and assembly. |
| `PCB_SAFETY_DESIGN_RULES.md` | Mandatory PCB safety design rules: clearance, creepage, isolation, and current capacity. |
| `REGULATORY_COMPLIANCE.md` | Regulatory compliance requirements (FCC, CE, UL) and verification methods. |

### Project-Level

Meta-documents that govern project processes and conventions.

| File | Description |
|------|-------------|
| `physics-verification-methodology.md` | Methodology for verifying physics-informed EDA features with bounded model checking and oracle tests. |
| `STRATEGY.md` | Project strategy: target problem, approach, non-negotiable safety and performance gates. |
| `TRACEABILITY.md` | Convention for linking code to plan requirements via `@req()` annotations with CI enforcement. |

## Where-to-Look FAQ

| Question | Answer targets |
|----------|---------------|
| "What are we building and why?" | `STRATEGY.md`, `ideation/`, `specs/` |
| "How do I set up my dev environment?" | `guides/WALKTHROUGH.md` |
| "What's the architecture of X?" | `architecture/`, `router/` |
| "Has this decision already been made?" | `adr/`, `solutions/tooling-decisions/`, `solutions/conventions/` |
| "Why did we choose approach A over B?" | `adr/`, `solutions/tooling-decisions/` |
| "What was the plan for feature X?" | `plans/`, `brainstorms/` |
| "Is there a known fix for this bug?" | `solutions/`, `bugs/`, `triaged/` |
| "What are the safety / compliance rules?" | `specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`, `PCB_SAFETY_DESIGN_RULES.md`, `REGULATORY_COMPLIANCE.md` |
| "What testing procedures exist?" | `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`, `FUNCTIONAL_TEST_PROCEDURE.md`, `HV_SAFETY_TEST_PROCEDURE.md`, `solutions/test-failures/` |
| "Where do PCB design rules live?" | `PCB_DFM_GUIDELINES.md`, `PCB_SAFETY_DESIGN_RULES.md`, `specs/PCB_SPECIFICATION.md` |
| "What got finished / closed recently?" | `closure-reports/`, `session-reports/` |
| "Where's the hardware BOM / mechanical?" | `hardware/`, `ASSEMBLY_GUIDE.md`, `COOKTOP_PANEL_SOURCING.md` |

## Conventions

### File naming

Top-level and subdirectory files use the pattern
`YYYY-MM-DD-<slug>-<kind>.md`:
- **Date**: ISO 8601 (`YYYY-MM-DD`), the creation or decision date.
- **Slug**: kebab-case short descriptor (e.g., `docs-index`, `import-linter-boundary`).
- **Kind**: the document type as a suffix (e.g., `plan`, `spec`, `guide`,
  `requirements`, `checklist`, `procedure`).

### Frontmatter

Most files carry YAML frontmatter between `---` delimiters. Common fields:

| Field | Purpose |
|-------|---------|
| `date` | ISO 8601 creation or decision date. |
| `topic` | Short kebab-case topic slug (brainstorms). |
| `status` | Lifecycle stage: `active`, `done`, `closed`, `deferred`, `superseded`. |
| `tier` | Priority tier: `infra`, `core`, `peripheral`. |
| `type` | Document kind for plans: `feat`, `fix`, `refactor`, `docs`, `ops`. |

### Documentation lifecycle

Documents progress through stages as work advances:

1. **Ideation** — raw idea, captured in `ideation/`.
2. **Brainstorm** — structured requirements exploration, captured in `brainstorms/`.
3. **Plan** — implementation plan with units, test scenarios, and
   dependencies, captured in `plans/`.
4. **Implementation** — the work is executed; the plan's `status` field tracks
   progress.
5. **Closure** — after completion, one of:
   - `closure-reports/` — post-mortem or completion summary.
   - `adr/` — architectural decision record (if the work produced a
     significant design decision).
   - `solutions/` — reusable fix or pattern (if the work solved a recurring
     problem).

### Solutions taxonomy walkthrough

`solutions/` is a categorized knowledge base of documented fixes for recurring
problems. Each subcategory holds markdown files with YAML frontmatter
describing the problem, its root cause, the fix applied, and any related
issues. When you encounter a problem:
1. Check the relevant subcategory first (e.g., `solutions/build-errors/` for
   compilation failures).
2. If you solve a problem that is likely to recur, document it in the
   appropriate subcategory so the next person benefits.

The 10 subcategories are listed in the [Solutions taxonomy](#solutions-taxonomy)
table above.

## Keeping This Index Fresh

This index is **human-maintained**. When you make structural changes to `docs/`,
please update this file:

- **New top-level directory**: Add an entry to the [Directory Tree](#directory-tree)
  table with a 1--2 sentence description.
- **New top-level `.md` file**: Determine its category and add it in alphabetical
  order to the appropriate [Top-Level Files](#top-level-files) subsection.
- **Removed or renamed file/directory**: Update the corresponding entry.
- **New frequently-asked question**: Add a row to the [FAQ matrix](#where-to-look-faq).
- **Bump the date** in the footer below on every structural change.

Last updated: 2026-07-13
