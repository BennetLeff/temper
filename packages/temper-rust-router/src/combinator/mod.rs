/// Constraint Combinator — proven sound primitive CNF encodings, composition
/// operators, and a rewrite engine that eliminates redundancy from
/// `InternalConstraintModel` before CNF encoding.
///
/// # Type hierarchy
///
/// ```text
/// Composition Operators  (Conjoin, Conditional, RestrictDomain)
///         │
///         ▼  lower_composed()
/// Primitive Types        (P1: MutualExclusion, P2: CardinalityBound, P4: LayerAssignment)
///         │
///         ▼  map to variants
/// InternalConstraint      (Capacity, DiffPair, LayerRestriction)
///         │
///         ▼  encode_to_cnf()
/// CNF Clauses             (fed to CaDiCaL via rustsat)
/// ```
///
/// # Pipeline integration
///
/// The rewrite engine runs synchronously after `model_from_python` and before
/// `encode_to_cnf` in `lib.rs`:
///
/// ```text
/// model_from_python()          ← existing: Python → InternalConstraintModel
///     │
///     ▼
/// combinator::rewrite(&model)  ← NEW: RW1-RW7, returns simplified model
///     │
///     ▼
/// encode_to_cnf(&model)        ← existing: InternalConstraintModel → CnfFormula
/// ```
///
/// # Rewrite rules
///
/// | Rule | Name | Effect |
/// |------|------|--------|
/// | RW1 | CapSubsume | Tighten loober capacity bounds under tighter ones |
/// | RW2 | CapEliminate | Remove trivially satisfiable capacity constraints |
/// | RW3 | LayerPropagate | Remove true unit-clause vars from Capacity, decrement K |
/// | RW4 | LayerPropagateFalse | Remove false unit-clause vars from Capacity |
/// | RW5 | DiffPairDedup | Drop duplicate DiffPair constraints |
/// | RW6 | LayerDedup | Drop duplicate LayerRestriction constraints |
/// | RW7 | LayerConflict | Detect contradictory layer restrictions (pre-solve UNSAT) |
///
/// The rewrite engine is terminating, confluent, and semantics-preserving.

pub mod lower;
pub mod proofs;
pub mod rewrite;
pub mod types;

pub use lower::lower_composed;
pub use rewrite::{rewrite, RewriteError};
pub use types::{
    cardinality_bound_new, compose_conjoin, compose_conditional, compose_restrict_domain,
    layer_assignment_new, mutual_exclusion_equality, ComposedConstraint, PrimitiveConstraint,
};
