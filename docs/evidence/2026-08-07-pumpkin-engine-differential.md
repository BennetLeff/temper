<!-- provenance: commit=PENDING dirty=false -->

# Pumpkin run through the BLOCKER-ORTOOLS equivalence harness (2026-08-07)

**Scope:** run the alternate-engine measurement that
`docs/evidence/2026-08-07-cpsat-equivalence-harness.md` Sec 5 identified as
the one remaining gap: no code in `packages/temper-placer/src/temper_placer/placer/cp_sat/`
changed, no call site migrated. Companion code: `docs/evidence/2026-08-07-pumpkin-engine/`
(standalone Rust binary implementing the model, linking `pumpkin-solver`) and
`docs/evidence/2026-08-07-pumpkin-equivalence-run.py` (the harness's `Engine`
protocol implementation + differential runner -- imports the harness `.py`
unchanged, adds nothing else).

**PENDING: fill in after the full differential run completes.**
