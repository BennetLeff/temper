/// Composition tree types for the constraint combinator.
///
/// Defines the intermediate representation that the combinator manipulates:
/// composition operators (`Conjoin`, `Conditional`, `RestrictDomain`) whose
/// leaves are primitives (P1-P4 active, P3/P5/P6 deferred).
///
/// Type hierarchy:
/// ```text
/// ComposedConstraint (operators + leaves)
///   → lower_composed()      [lower.rs]
///   → InternalConstraint    [types.rs]
///   → encode_to_cnf()       [encoding.rs]
/// ```

/// A primitive constraint in isolation (before composition).
///
/// Active primitives:
/// - **P1. MutualExclusion (equality mode):** `x ↔ y` maps to `DiffPair`
/// - **P2. CardinalityBound:** `∑vars ≤ k` maps to `Capacity`
/// - **P4. LayerAssignment:** `x = v` maps to `LayerRestriction`
///
/// Deferred primitives (no `InternalConstraint` variants yet):
/// - **P3 (SpatialOrder):** `OrderVar` exists in types.rs but has no consumer
/// - **P5 (AdjacencyPair):** requires new `InternalConstraint::Adjacency`
/// - **P6 (SeparationDistance):** requires new `InternalConstraint::Separation`
#[derive(Clone, Debug, PartialEq)]
pub enum PrimitiveConstraint {
    /// P1. MutualExclusion: equality mode (x ↔ y).
    MutualExclusion {
        p_var_name: String,
        n_var_name: String,
    },
    /// P2. CardinalityBound: AtMostK over a set of Boolean variables on one channel.
    CardinalityBound {
        channel_id: String,
        k: usize,
        terms: Vec<(String, f64)>, // (var_name, width)
    },
    /// P4. LayerAssignment: unit clause x = v.
    LayerAssignment {
        var_name: String,
        value: bool,
    },
}

/// A composition tree node.
///
/// Operators:
/// - **Conjoin:** C₁ ∧ C₂ — both constraints must hold.
///   Sound because the conjunction of sound CNFs is sound.
/// - **Conditional:** A → C — if antecedent assignments hold, C must hold.
///   Desugared as conjunction of unit clauses + consequent (acceptable for
///   the initial release; true implication encoding is deferred).
/// - **RestrictDomain:** C|[vars] — restrict C to apply only to `vars`.
///   Desugared via filtering variable sets in the lowered model.
#[derive(Clone, Debug, PartialEq)]
pub enum ComposedConstraint {
    /// A leaf: a single primitive constraint.
    Primitive(PrimitiveConstraint),
    /// C₁ ∧ C₂: both must hold.
    Conjoin(Box<ComposedConstraint>, Box<ComposedConstraint>),
    /// A → C: if all antecedent assignments hold, constraint C must hold.
    Conditional {
        antecedent: Vec<(String, bool)>, // [(var_name, value)]
        consequent: Box<ComposedConstraint>,
    },
    /// C|[vars]: restrict C to apply only to variables in the given set.
    RestrictDomain {
        inner: Box<ComposedConstraint>,
        vars: Vec<String>,
    },
}

// ---------------------------------------------------------------------------
// Helper constructors (public API for constraint authors)
// ---------------------------------------------------------------------------

/// P1 equality mode: `p_var_name ↔ n_var_name`.
pub fn mutual_exclusion_equality(p_var_name: String, n_var_name: String) -> ComposedConstraint {
    ComposedConstraint::Primitive(PrimitiveConstraint::MutualExclusion {
        p_var_name,
        n_var_name,
    })
}

/// P2 cardinality bound: at most `k` of the given terms may be true.
pub fn cardinality_bound_new(
    channel_id: String,
    k: usize,
    terms: Vec<(String, f64)>,
) -> ComposedConstraint {
    ComposedConstraint::Primitive(PrimitiveConstraint::CardinalityBound {
        channel_id,
        k,
        terms,
    })
}

/// P4 layer assignment: `var_name = value`.
pub fn layer_assignment_new(var_name: String, value: bool) -> ComposedConstraint {
    ComposedConstraint::Primitive(PrimitiveConstraint::LayerAssignment {
        var_name,
        value,
    })
}

/// Combine two constraints: both must hold.
pub fn compose_conjoin(
    a: ComposedConstraint,
    b: ComposedConstraint,
) -> ComposedConstraint {
    ComposedConstraint::Conjoin(Box::new(a), Box::new(b))
}

/// Conditional: if antecedent holds, consequent must hold.
pub fn compose_conditional(
    antecedent: Vec<(String, bool)>,
    consequent: ComposedConstraint,
) -> ComposedConstraint {
    ComposedConstraint::Conditional {
        antecedent,
        consequent: Box::new(consequent),
    }
}

/// Restrict a constraint to apply only within the given variable set.
pub fn compose_restrict_domain(
    inner: ComposedConstraint,
    vars: Vec<String>,
) -> ComposedConstraint {
    ComposedConstraint::RestrictDomain {
        inner: Box::new(inner),
        vars,
    }
}

// ---------------------------------------------------------------------------
// Deferred primitive stubs (P3, P5, P6)
// ---------------------------------------------------------------------------

/// P3. SpatialOrder — deferred.
/// `OrderVar` exists in `types.rs` but is never populated by `ModelBuilder`.
/// No `InternalConstraint::SpatialOrder` variant exists yet.
#[allow(dead_code)]
struct SpatialOrderStub {
    net1_idx: usize,
    net2_idx: usize,
    channel_id: String,
}

/// P5. AdjacencyPair — deferred.
/// Requires new `InternalConstraint::Adjacency` variant.
#[allow(dead_code)]
struct AdjacencyPairStub {
    net_idx: usize,
    channel_id: String,
    neighbors: Vec<usize>,
}

/// P6. SeparationDistance — deferred.
/// Requires new `InternalConstraint::Separation` variant.
#[allow(dead_code)]
struct SeparationDistanceStub {
    net1_idx: usize,
    net2_idx: usize,
    channel_id: String,
    min_sep_mm: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn construct_conjoin() {
        let p2 = cardinality_bound_new(
            "L1_E5".into(), 3,
            vec![("A".into(), 1.0), ("B".into(), 1.0), ("C".into(), 1.0)],
        );
        let p4 = layer_assignment_new("A".into(), true);
        let composed = compose_conjoin(p2, p4);
        match &composed {
            ComposedConstraint::Conjoin(left, right) => {
                assert!(matches!(&**left, ComposedConstraint::Primitive(PrimitiveConstraint::CardinalityBound { .. })));
                assert!(matches!(&**right, ComposedConstraint::Primitive(PrimitiveConstraint::LayerAssignment { .. })));
            }
            _ => panic!("expected Conjoin"),
        }
    }

    #[test]
    fn construct_conditional() {
        let p1 = mutual_exclusion_equality("p".into(), "n".into());
        let cond = compose_conditional(vec![("guard".into(), true)], p1);
        match &cond {
            ComposedConstraint::Conditional { antecedent, consequent: _ } => {
                assert_eq!(antecedent, &vec![("guard".to_string(), true)]);
            }
            _ => panic!("expected Conditional"),
        }
    }

    #[test]
    fn construct_restrict_domain() {
        let p2 = cardinality_bound_new(
            "CH1".into(), 2,
            vec![("A".into(), 1.0), ("B".into(), 1.0), ("C".into(), 1.0)],
        );
        let restricted = compose_restrict_domain(p2, vec!["A".into(), "B".into()]);
        match &restricted {
            ComposedConstraint::RestrictDomain { inner: _, vars } => {
                assert_eq!(vars, &vec!["A".to_string(), "B".to_string()]);
            }
            _ => panic!("expected RestrictDomain"),
        }
    }
}
