# Zapote seeding ledger

The user selected incremental copying of existing Rust validators into
Zapote-owned packages. Keep the working Python/KiCad bridge; replacing it is
deferred so broad Rust board validation can proceed now.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the governing boundary.

## Planned mapping

| Donor | Zapote destination | Boundary |
|---|---|---|
| Existing board/constraint/finding types | `packages/zapote-core/` | One shared Rust representation |
| Applicable physical/routing/safety rules and tests | `packages/zapote-drc/` | Preserve checked rules; omit Python bridges and unused dependencies |
| Applicable ERC rules and tests | `packages/zapote-erc/` | Preserve actual coverage; no placeholder passes |
| Existing Python/KiCad adapter | Retained current adapter | Native editing now; Rust client migration later |
| Source identity kernels | Core and harness source module | Atopile remains an external compiler |
| Pure Rust policy and existing host contracts | `packages/zapote-harness/` plus retained host | Rust validation/policy with thin Python transport |
| Existing notes and retained evidence | `skills/` and evidence references | Historical runs keep their historical identity |

These are planned homes, not completed package copies. Each port records donor
paths, source commit if resolvable, exact donor hashes, target paths, copied
tests, extraction changes, and comparison evidence in `ports.toml`. Record dirty
bytes honestly and retain required notices and independent oracles. Separate
mechanical extraction from intentional behavior changes.

Zapote owns its copied implementation; legacy Temper callers keep theirs.
Do not add runtime dependencies back into Temper packages, promise automatic
two-way synchronization, or delete legacy code during seeding.

## First useful slice

Bootstrap Rust validator packages and connect them to the existing editing
path. Record full-board coverage/results, let the agent correct real findings,
and expand the suite per `VALIDATION.md`. Do not delay this for a new editor,
Rust-only host, or broad package cleanup.

The existing Makefile/project configuration remain legacy scaffolding. P1
updates them during bootstrap; delegated checks are not evidence of a working
Zapote implementation.
