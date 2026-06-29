/// Rewrite engine — RW1-RW7 on `InternalConstraintModel`.
///
/// Applies simplification rules to the flattened `InternalConstraint` list
/// until fixpoint. The engine operates on the constraint multiset.

use crate::types::{InternalConstraint, InternalConstraintModel};

/// Error returned when the rewrite engine detects a structural contradiction.
#[derive(Debug, PartialEq)]
pub enum RewriteError {
    /// Structural contradiction detected pre-solve (RW7).
    UnsatPreSolve {
        var_name: String,
        constraint1: String,
        constraint2: String,
    },
}

/// Apply RW1-RW7 rewrite rules to an `InternalConstraintModel`.
///
/// Returns the simplified model or `RewriteError::UnsatPreSolve` if a
/// structural contradiction is detected.
pub fn rewrite(model: &InternalConstraintModel) -> Result<InternalConstraintModel, RewriteError> {
    let _ = model;
    Err(RewriteError::UnsatPreSolve {
        var_name: "placeholder".into(),
        constraint1: "placeholder1".into(),
        constraint2: "placeholder2".into(),
    })
}
