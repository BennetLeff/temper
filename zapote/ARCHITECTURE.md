# Zapote architecture

Zapote is Temper's agent engineering subproject centered on Rust validation.
The agent chooses placements/routes; KiCad edits the board through the working
Python adapter. Zapote supplies a large engineering validation suite, context,
memory, budgets and feedback. It does not implement a placer or autorouter.

The user's latest clarification keeps the existing Python/KiCad adapter for
now. Rust-only transport/editor migration is deferred. [VALIDATION.md](VALIDATION.md)
defines the primary objective and the 100–1,000× validation ambition. Packages
below are planned, not already implemented.

## Workspace and package ownership

Use `zapote/Cargo.toml` as an independent Cargo workspace, with these initial
packages under `zapote/packages/`:

| Package | Responsibility | Donors to copy selectively |
|---|---|---|
| `zapote-core` | Shared typed board, circuit, constraints, findings, identities, and required geometry | `temper-drc-rs` types and needed `temper-design-bundle` / `temper-geometry` kernels |
| `zapote-drc` | Applicable physical, placement, routing, isolation, and manufacturing checks | Existing Rust rules and their actual dependencies/tests |
| `zapote-erc` | Applicable circuit/connectivity checks | Existing ERC rules and source-pin identity checks |
| `zapote-kicad` (later) | Rust client to KiCad; not a replacement editor | Existing editing contract; migration only when needed |
| `zapote-harness` | Rust validation composition, task policy, memory and evidence interfaces | Pure Rust policy; retained Python host provides current transport/editing |
| `zapote-thermal` | Gmsh/Elmer reference execution, evidence and analytic acceptance checks | External Gmsh and Elmer executables; no new FEM implementation |

DRC and ERC depend on core; the harness composes them. Core never
depends on those consumers. Keep one shared board/constraint/finding model.
Additional packages are introduced only when a real requirement needs them.
`zapote-thermal` starts with the [electrothermal reference](thermal/README.md)
needed before modeling power-entry terminal necks. It does not yet supply a
board thermal qualification gate. Do not copy the optimizer workspace wholesale.

## Rust validators; working KiCad transport retained

New validation logic and tests live in Rust Zapote packages. Copy needed donor
kernels behind typed Rust inputs and keep engineering rules out of Python.
The existing Python `pcbnew` adapter, source/export glue and agent host may be
reused now. Thin bridging to the Rust validator CLI/API is permitted; retain
actual input/output and version identities. The copied Rust rule remains the
acceptance authority. No optimizer dependency is required.

Keep KiCad responsible for its board objects, geometry edits, serialization and
zone refill. Do not build a Rust PCB editor or demand a Rust IPC client first.
A future Rust transport can replace Python with equivalent behavior; neither
language cleanup nor binding removal is a condition for today's board work.
Atopile/KiCad stay external tools. Legacy production sources remain shared.

## Copy code with evidence and a clear new owner

Copy needed validator code and meaningful tests, retaining authorship/license
notices. Record donor paths, resolvable commit if available, exact donor hashes,
target paths, copied tests, extraction changes, and verification in
`zapote/ports.toml`. Dirty donor bytes need their own hashes and must not be
attributed to a commit that does not contain them.

The copy is authoritative for Zapote; the original remains authoritative for
legacy Temper callers. This is a deliberate fork with provenance, not runtime
imports or automatic two-way synchronization. Later imports/backports are
separately reviewed and recorded. First preserve behavior while removing
bindings and unnecessary dependencies; distinguish intentional corrections
from mechanical extraction.

Retain production-shaped cases, supported failing examples, and independent
KiCad/brute-force oracles. Donor agreement alone is not correctness. Do not
register placeholders or describe coarse component-membership checks as full
pin-level ERC. Delete no legacy code during seeding; retire it only after its
remaining consumers are inventoried and migrated. Initial cleanup comes from
Zapote's dependency graph and ownership boundaries.

## The working loop

1. The existing host supplies source-derived inputs and authored constraints.
2. The agent sees the board, applicable memory, and findings.
3. The agent chooses explicit moves/rotations or track/via paths.
4. KiCad applies edits through the existing Python adapter; the host invokes
   the copied Rust engineering validators on the resulting measured candidate.
5. Findings return with rule, object/location, and actual/required values where
   supplied; the agent revises its design.
6. Final acceptance runs all applicable checks plus independent native KiCad
   verification on the saved candidate.

Geometry queries and explicit edit batches are tools, not hidden search or
repair. Memory starts with prose procedures; compiled Rust helpers are added
only for concrete repeated operations. Engineering limits stay in constraints
and validators. Record which checks ran with sufficient inputs; missing
required inputs cannot become an empty success. Inapplicable differs from pass.

## First slice and implementer ownership

P1 owns validator workspace manifests, port ledger, core, DRC/ERC extraction,
coverage inventory and thin integration with existing adapters. P2 owns memory
module/tests/catalog; P1 integrates it. P3 owns assembly-specific Rust
composition/tests and physical contracts. Shared-file changes go through P1.

First connect existing Rust validation to the current editing path and record
full-board coverage/results. Prove a real finding reaches the agent and its
correction is checked. Expand required rules and fault coverage as described in
`VALIDATION.md`; two smoke-test rules alone do not satisfy the board objective.

Keep copied validator kernels independent of Python and optimizer code; record
the retained host/adapter dependency explicitly. Run Rust, adapter and native
controls. Keep build output distinct from legacy PyO3 artifacts so Cargo does
not overwrite an extension another checkout imports.

## Shared inputs and current scaffold

Temper's `elec/`, `pcb/`, `firmware/`, `components/`, and `datasheets/` remain
shared product inputs. Hashed run snapshots are evidence, not second editable
product sources. Candidate boards remain distinct from the production board.

Current commands delegate to the legacy harness. P1 adds explicit Zapote
validation integration; delegation alone does not prove Zapote checks ran.
