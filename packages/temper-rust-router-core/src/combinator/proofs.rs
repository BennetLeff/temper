/// Proof registry — debug-assert documentation of the proof chain.
///
/// Every primitive (P1-P4) has:
/// 1. Exhaustive verification tests (n ≤ 4 for P1, n ≤ 8 for P2)
/// 2. Cross-validation against an independent DPLL reference
/// 3. A `PROOFS.toml` entry recording test locations
///
/// Composition operators carry generic soundness proofs:
/// - Conjoin: conjunction of sound CNFs is sound (trivial)
/// - Conditional: reduces to implication-as-clause (deferred; current encoding is conjunction)
/// - RestrictDomain: subset filter preserves soundness
///
/// CI enforces `PROOFS.toml` completeness via `scripts/verify_proofs.py`.

/// Debug-assert proof registry.
#[cfg(debug_assertions)]
pub mod proof_registry {
}
