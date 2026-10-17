# Standalone current-sensing unit

User approved construction on 2026-09-11. Build and validate this unit separately; cooker integration follows later.

Scope: existing transformer current-sensing front end and its primary overcurrent comparator, explicit power/signal/fault/primary interfaces, source-derived standalone schematic and routed board. Reconcile actual circuit behavior before copying legacy assumptions. Fix required defects in the standalone source without silently changing the full-cooker circuit. Exact parts, conditions and acceptance bounds come from reviewed source/datasheets and declared engineering requirements.

Sequence: (1) reconcile circuit and freeze contract/model boundaries; (2) generate native source-derived KiCad and implement applicable Rust checks, with deliberate counterexamples; (3) coordinator authors placement/routes through existing native adapters using Rust feedback; (4) native/ERC/DRC/parity plus source identity and Rust acceptance on final files; (5) BOM, interface handoff, reviewed lessons and frozen receipts.

Root owns canonical integration, board placement/routing, source-to-board validation, acceptance and documentation. Luna owns bounded circuit/source/model and adapter/validator work in isolated directories. Existing RTD/buck/MCU outputs and the shared dirty worktree remain preserved. New policy lives in Rust. No placer/router algorithms, no purchase, no powered testing and no full-cooker composition. Physical tests remain NOT RUN. A required unsupported claim remains INDETERMINATE and cannot be hidden by green CAD checks.

Completion: source-derived placed/routed standalone unit, circuit/model checks with explicit applicability limits, complete adopted Rust/native checks and defect controls, exact BOM/pinout, reproducible evidence and lessons. Record current limits honestly; no claim of physical qualification from simulation.
