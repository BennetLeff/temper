// SAT encoding — constraint model → CNF translation.
//
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::collections::HashSet;

use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable, SatVariable};

/// A CNF formula: a flat literal pool plus a CSR-style clause-offset index,
/// replacing the earlier `Vec<Vec<i32>>` (one heap allocation per clause).
/// Positive literal = true, negative = false. `clause_offsets` always has
/// `num_clauses() + 1` entries (starting at 0); clause `i`'s literals are
/// `literals[clause_offsets[i]..clause_offsets[i + 1]]`.
///
/// Representation-only change (R2 of
/// docs/plans/2026-08-12-004-feat-cnf-representation-plan.md): same literal
/// content, same clause order as the `Vec<Vec<i32>>` form it replaces --
/// measured at 13.81 bytes/clause vs. 56.00 bytes/clause, a 4.06x reduction
/// on our side of the CaDiCaL FFI boundary (see the plan for the full
/// measurement, including why CaDiCaL's own clause storage dominates the
/// total either way).
pub struct CnfFormula {
    pub num_vars: usize,
    pub literals: Vec<i32>,
    pub clause_offsets: Vec<u32>,
    pub var_to_net: Vec<usize>,
}

impl CnfFormula {
    /// Build a packed `CnfFormula` from a nested clause list (CSR flatten).
    /// Preserves clause order and literal content exactly.
    pub fn from_clauses(num_vars: usize, clauses: Vec<Vec<i32>>, var_to_net: Vec<usize>) -> Self {
        let mut literals = Vec::with_capacity(clauses.iter().map(Vec::len).sum());
        let mut clause_offsets = Vec::with_capacity(clauses.len() + 1);
        clause_offsets.push(0u32);
        for clause in clauses {
            literals.extend(clause);
            clause_offsets.push(literals.len() as u32);
        }
        Self {
            num_vars,
            literals,
            clause_offsets,
            var_to_net,
        }
    }

    /// Number of clauses in the packed representation.
    pub fn num_clauses(&self) -> usize {
        self.clause_offsets.len().saturating_sub(1)
    }

    /// True when there are no clauses.
    pub fn clauses_is_empty(&self) -> bool {
        self.clause_offsets.len() <= 1
    }

    /// Iterate over clauses as literal slices, in original order.
    pub fn clauses(&self) -> impl Iterator<Item = &[i32]> + '_ {
        self.clause_offsets
            .windows(2)
            .map(move |w| &self.literals[w[0] as usize..w[1] as usize])
    }
}

/// Encode AtMostK cardinality constraint via Sinz (2005) sequential counter.
///
/// Adds O(n·k) auxiliary variables to `var_map` and O(n·k) clauses to
/// `clauses`.  Variables are referenced by index into `var_map`.
fn encode_at_most_k(
    clauses: &mut Vec<Vec<i32>>,
    var_map: &mut Vec<SatVariable>,
    vars: &[usize],
    k: usize,
) {
    let n = vars.len();
    if k >= n {
        return;
    }
    if k == 0 {
        for &vi in vars {
            clauses.push(vec![-((vi + 1) as i32)]);
        }
        return;
    }

    // Register variables r[i][j] for i=0..n-2, j=0..k-1.
    // r[i][j]: at least j+1 of vars[0..i] are true.
    //
    // R1 (docs/plans/2026-08-12-004-feat-cnf-representation-plan.md): no
    // per-variable `String` is formatted for these Sinz auxiliary
    // variables -- `solve_with_cadical` never reads `encode_to_cnf`'s
    // `var_names` output and `extract_topology`/`expand_assignments` only
    // ever match a `"uses_"` prefix no aux name carries, so a formatted
    // `"sc_r{i}_{j}"` name (measured 56.0 bytes/aux-var, 21.1 GB at full
    // scale) was pure waste for those two consumers. `bmc.rs::bmc_verify`
    // is the one real consumer that reads aux-var names -- it filters them
    // out of the primary-variable set -- so it must keep working; it does,
    // via `String::is_empty()` (an empty `String` never heap-allocates,
    // unlike `format!(...)`, and every primary variable's name is
    // guaranteed non-empty by `add_var_with_net`, `encoding.rs:91-106`).
    let r_start = var_map.len();
    for i in 0..(n - 1) {
        for j in 0..k {
            var_map.push(SatVariable::new(
                String::new(),
                format!("seq-counter r{i}.{j}"),
            ));
        }
    }

    let r = |i: usize, j: usize| -> i32 {
        (r_start + i * k + j + 1) as i32
    };

    let v = |i: usize| -> i32 { (vars[i] + 1) as i32 };

    // Position 0.
    clauses.push(vec![-v(0), r(0, 0)]);
    for j in 1..k {
        clauses.push(vec![-r(0, j)]);
    }

    // Positions 1..n-2.
    for i in 1..(n - 1) {
        clauses.push(vec![-v(i), r(i, 0)]);
        clauses.push(vec![-r(i - 1, 0), r(i, 0)]);
        for j in 1..k {
            clauses.push(vec![-v(i), -r(i - 1, j - 1), r(i, j)]);
            clauses.push(vec![-r(i - 1, j), r(i, j)]);
        }
    }

    // Exclusion: if count already reaches k, no further variable may be true.
    for i in k..n {
        clauses.push(vec![-v(i), -r(i - 1, k - 1)]);
    }
}

/// Convert the internal constraint model to CNF.
pub fn encode_to_cnf(model: &InternalConstraintModel) -> (CnfFormula, Vec<String>) {
    let n_vars = model.variables.len();
    let n_cons = model.constraints.len();
    let mut var_map: Vec<SatVariable> = Vec::with_capacity(n_vars);
    let mut var_to_net: Vec<usize> = Vec::with_capacity(n_vars);
    let mut name_to_idx: std::collections::HashMap<String, usize> =
        std::collections::HashMap::with_capacity(n_vars);
    let mut clauses: Vec<Vec<i32>> = Vec::with_capacity(n_cons * 2);

    // Sentinel value for auxiliary variables that don't map to a specific net.
    const NO_NET: usize = usize::MAX;

    let add_var_with_net = |vm: &mut Vec<SatVariable>,
                            vn: &mut Vec<usize>,
                            nm: &mut std::collections::HashMap<String, usize>,
                            name: &str,
                            net_idx: usize|
     -> usize {
        if let Some(&idx) = nm.get(name) {
            idx
        } else {
            let idx = vm.len();
            vm.push(SatVariable::new(name, ""));
            vn.push(net_idx);
            nm.insert(name.to_string(), idx);
            idx
        }
    };

    let encode_lit = |idx: usize, pos: bool| -> i32 {
        if pos { (idx + 1) as i32 } else { -((idx + 1) as i32) }
    };

    // Map all internal variables to SAT variable indices with net tracking.
    for v in &model.variables {
        match v {
            InternalVariable::NetChannel { name, net_idx, .. } => {
                add_var_with_net(&mut var_map, &mut var_to_net, &mut name_to_idx, name, *net_idx);
            }
            InternalVariable::NetLayer { name, net_idx, .. } => {
                add_var_with_net(&mut var_map, &mut var_to_net, &mut name_to_idx, name, *net_idx);
            }
            InternalVariable::Via { name, net_idx, .. } => {
                add_var_with_net(&mut var_map, &mut var_to_net, &mut name_to_idx, name, *net_idx);
            }
            InternalVariable::Ordering { name, net1_idx, .. } => {
                add_var_with_net(&mut var_map, &mut var_to_net, &mut name_to_idx, name, *net1_idx);
            }
        }
    }

    // Encode constraints.
    for c in &model.constraints {
        match c {
            InternalConstraint::Capacity { channel_id: _ch, capacity: _cap, slack_factor: _sf, terms } => {
                if terms.is_empty() {
                    continue;
                }
                // Compute max_nets = floor(capacity * slack / min_width)
                let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
                let max_nets = ((_cap * _sf) / min_width).floor() as usize;

                let mut var_indices: Vec<usize> = Vec::new();
                for (vname, _w) in terms {
                    if let Some(&idx) = name_to_idx.get(vname) {
                        var_indices.push(idx);
                    }
                }

                if !var_indices.is_empty() && max_nets < var_indices.len() {
                    // Encode AtMostK as CNF via sequential counter (Sinz 2005),
                    let aux_start = var_map.len();
                    encode_at_most_k(&mut clauses, &mut var_map, &var_indices, max_nets);
                    // Auxiliary variables don't map to a specific net.
                    for _i in aux_start..var_map.len() {
                        var_to_net.push(NO_NET);
                    }
                }
            }
            InternalConstraint::DiffPair { p_var_name, n_var_name, .. } => {
                if let (Some(&p), Some(&n)) = (name_to_idx.get(p_var_name), name_to_idx.get(n_var_name)) {
                    // p ↔ n: (¬p ∨ n) ∧ (p ∨ ¬n)
                    clauses.push(vec![encode_lit(p, false), encode_lit(n, true)]);
                    clauses.push(vec![encode_lit(p, true), encode_lit(n, false)]);
                }
            }
            InternalConstraint::LayerRestriction { var_name, allowed } => {
                if let Some(&idx) = name_to_idx.get(var_name) {
                    // Unit clause: var = allowed
                    clauses.push(vec![encode_lit(idx, *allowed)]);
                }
            }
            InternalConstraint::ChannelSeparation { group_a, group_b, min_slots, channel_id: _ch } => {
                // For each pair (a in A, b in B), enforce ordering separation.
                // The encoding adds AtMostK cardinality: at most min_slots
                // nets from (A U B) can share contiguous channel slots.
                let combined_len = group_a.len() + group_b.len();
                if *min_slots >= combined_len {
                    continue; // Trivially satisfied.
                }
                // Collect all relevant variables (NetChannelVar for these nets on this channel).
                // They were already registered as variables during model conversion.
                // For each a in A, b in B, enforce the ordering variable.
                // Dedup normalized (min, max) pairs: when a net is in BOTH
                // groups the same unit clause would be pushed twice — a CNF
                // no-op, so skip repeats (F5).
                let mut seen_pairs: HashSet<(usize, usize)> = HashSet::new();
                for &a_idx in group_a {
                    for &b_idx in group_b {
                        let pair = (a_idx.min(b_idx), a_idx.max(b_idx));
                        if !seen_pairs.insert(pair) {
                            continue;
                        }
                        let order_name = format!("order_N{}_N{}_{}", pair.0, pair.1, _ch);
                        // If there's an ordering var, enforce it.
                        if let Some(&order_idx) = name_to_idx.get(&order_name) {
                            // a must be before b (positive order) OR must not share.
                            // This is a soft constraint in MVP — encoded as hard.
                            clauses.push(vec![encode_lit(order_idx, true)]);
                        }
                    }
                }
                // Also add an AtMostK cardinality: at most min_slots nets from
                // (A U B) can be active on this channel.
                let mut all_indices: Vec<usize> = Vec::new();
                for &idx in group_a.iter().chain(group_b.iter()) {
                    let nc_name = format!("uses_N{}_{}", idx, _ch);
                    if let Some(&var_idx) = name_to_idx.get(&nc_name) {
                        all_indices.push(var_idx);
                    }
                }
                if !all_indices.is_empty() && *min_slots < all_indices.len() {
                    encode_at_most_k(&mut clauses, &mut var_map, &all_indices, *min_slots);
                }
            }
        }
    }

    let var_names: Vec<String> = var_map.iter().map(|v| v.name.clone()).collect();
    let num_vars = var_map.len();

    (
        CnfFormula::from_clauses(num_vars, clauses, var_to_net),
        var_names,
    )
}

// ---------------------------------------------------------------------------
// Inductive correctness proof
// ---------------------------------------------------------------------------
// The Sinz (2005) sequential counter encoding is correct by published proof.
//
// Inductive hypothesis: assume encode_at_most_k produces correct CNF for n-1
// variables with bound k. For n variables, register r[n-2][k-1] correctly
// indicates whether k variables are already true among the first n-1. The
// exclusion clause (¬x_n ∨ ¬r[n-2][k-1]) ensures x_n is false when the
// count is already at k. The propagation clauses ensure r[i][j] correctly
// tracks the running count for all i < n-1.
//
// Base cases (n ≤ 8) are exhaustively verified by the tests in this module.
// By induction, correctness holds for all n.
//
// Reference: Sinz, C. (2005). "Towards an Optimal CNF Encoding of Boolean
// Cardinality Constraints." CP 2005.

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Mini DPLL solver for satisfiability checking of small CNFs.
    /// Unit propagation + backtracking. Sufficient for n ≤ 8 exhaustives.
    fn dpll_sat(clauses: &[Vec<i32>], assignment: &[Option<bool>]) -> bool {
        let mut assign = assignment.to_vec();
        dpll_rec(clauses, &mut assign, 0)
    }

    #[allow(unused_variables, clippy::only_used_in_recursion)]
    fn dpll_rec(clauses: &[Vec<i32>], assign: &mut [Option<bool>], depth: usize) -> bool {
        // Unit propagation pass.
        loop {
            let mut changed = false;
            for clause in clauses {
                let mut unset_count = 0;
                let mut unset_idx = 0;
                let mut clause_sat = false;
                let mut unset_sign = true;

                for &lit in clause {
                    let var = (lit.unsigned_abs() as usize) - 1;
                    let sign = lit > 0;
                    if var >= assign.len() {
                        clause_sat = true;
                        break;
                    }
                    match assign[var] {
                        Some(v) if v == sign => { clause_sat = true; break; }
                        Some(_) => {} // falsified literal
                        None => { unset_count += 1; unset_idx = var; unset_sign = sign; }
                    }
                }
                if clause_sat {
                    continue;
                }
                if unset_count == 0 {
                    return false; // conflicting clause
                }
                if unset_count == 1 {
                    assign[unset_idx] = Some(unset_sign);
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }

        // All clauses satisfied?
        let all_sat = clauses.iter().all(|clause| {
            clause.iter().any(|&lit| {
                let var = (lit.unsigned_abs() as usize) - 1;
                if var >= assign.len() { return true; }
                match assign[var] {
                    Some(v) => v == (lit > 0),
                    None => false,
                }
            })
        });
        if all_sat {
            return true;
        }

        // Pick first unset variable and branch.
        if let Some(idx) = assign.iter().position(|v| v.is_none()) {
            assign[idx] = Some(false);
            if dpll_rec(clauses, assign, depth + 1) {
                return true;
            }
            assign[idx] = Some(true);
            if dpll_rec(clauses, assign, depth + 1) {
                return true;
            }
            assign[idx] = None;
        }
        false
    }

    #[cfg_attr(test, test)]
    fn exhaustive_at_most_k_n1_to_n8() {
        // For every n ∈ 1..8, k ∈ 0..n-1, verify the encoding against
        // all 2^n primary variable assignments.
        for n in 1..=8u32 {
            for k in 0..n {
                // Build primary vars.
                let mut var_map: Vec<SatVariable> = (0..n)
                    .map(|i| SatVariable::new(format!("x{i}"), ""))
                    .collect();
                let var_indices: Vec<usize> = (0..(n as usize)).collect();
                let mut clauses: Vec<Vec<i32>> = Vec::new();

                encode_at_most_k(&mut clauses, &mut var_map, &var_indices, k as usize);

                let total_vars = var_map.len();

                // For each assignment of primary variables (2^n):
                for bits in 0..(1u32 << n) {
                    let mut assign = vec![None; total_vars];
                    let mut true_count = 0usize;
                    for i in 0..(n as usize) {
                        let val = (bits >> i) & 1 == 1;
                        assign[i] = Some(val);
                        if val { true_count += 1; }
                    }
                    // All aux vars start unset.

                    let sat = dpll_sat(&clauses, &assign);

                    if true_count > k as usize {
                        assert!(!sat,
                            "UNSAT expected: n={n} k={k} assignment={bits:0>n$b} true_count={true_count} but CNF was SAT",
                            n = n as usize);
                    } else {
                        assert!(sat,
                            "SAT expected: n={n} k={k} assignment={bits:0>n$b} true_count={true_count} but CNF was UNSAT",
                            n = n as usize);
                    }
                }
            }
        }
    }

    #[cfg_attr(test, test)]
    fn encode_to_cnf_empty_model() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![],
        };
        let (cnf, var_names) = encode_to_cnf(&model);
        assert_eq!(cnf.num_vars, 0);
        assert!(cnf.clauses_is_empty());
        assert!(cnf.var_to_net.is_empty());
        assert!(var_names.is_empty());
    }

    // --- proptest: encode_to_cnf structural invariants ---

    // `#[cfg(test)]` is redundant under `cargo test` (the parent module
    // already carries it) and load-bearing everywhere else: the wasm32 test
    // registry compiles the parent into an ordinary build, where the
    // `proptest` dev-dependency is not linked. Same gate
    // `temper-thermal/src/thermal_edges.rs`'s nested proptest module already
    // carries. `items_after_test_module` is allowed because the item after
    // this module is the enclosing module's generated `WASM_TESTS` const,
    // appended there by design.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        use super::*;
        use proptest::prelude::*;

        /// Build a model with some NetChannel variables.
        fn model_with_net_channels(count: usize) -> InternalConstraintModel {
            let variables: Vec<InternalVariable> = (0..count)
                .map(|i| InternalVariable::NetChannel {
                    name: format!("uses_N{i}_ch0"),
                    net_idx: i,
                    channel_id: "ch0".to_string(),
                })
                .collect();
            InternalConstraintModel {
                variables,
                constraints: vec![],
            }
        }

        /// Build a model with some LayerRestriction constraints.
        fn model_with_layer_restrictions(count: usize) -> InternalConstraintModel {
            let variables: Vec<InternalVariable> = (0..count)
                .map(|i| InternalVariable::NetLayer {
                    name: format!("layer_N{i}_seg0"),
                    net_idx: i,
                    segment_id: "seg0".to_string(),
                })
                .collect();
            let constraints: Vec<InternalConstraint> = variables
                .iter()
                .enumerate()
                .map(|(i, _)| InternalConstraint::LayerRestriction {
                    var_name: format!("layer_N{i}_seg0"),
                    allowed: i % 2 == 0,
                })
                .collect();
            InternalConstraintModel {
                variables,
                constraints,
            }
        }

        proptest! {
            // --------------------------------------------------------------
            // Property E1: encode_to_cnf produces consistent output sizes.
            // var_names.len() == num_vars == var_to_net.len().
            // --------------------------------------------------------------
            #[test]
            fn prop_output_sizes_consistent(n in 0usize..=20usize) {
                let model = model_with_net_channels(n);
                let (cnf, var_names) = encode_to_cnf(&model);
                prop_assert_eq!(cnf.num_vars, var_names.len());
                prop_assert_eq!(cnf.var_to_net.len(), var_names.len());
            }

            // --------------------------------------------------------------
            // Property E1b: the packed CSR representation is internally
            // consistent -- clause_offsets is non-decreasing, starts at 0,
            // ends at literals.len(), and has num_clauses() + 1 entries.
            // Guards R2's flatten step (encoding.rs's `from_clauses`).
            // --------------------------------------------------------------
            #[test]
            fn prop_csr_offsets_consistent(n in 0usize..=20usize) {
                let model = model_with_layer_restrictions(n);
                let (cnf, _) = encode_to_cnf(&model);
                prop_assert_eq!(cnf.clause_offsets.len(), cnf.num_clauses() + 1);
                prop_assert_eq!(cnf.clause_offsets.first().copied(), Some(0u32));
                prop_assert_eq!(
                    cnf.clause_offsets.last().copied(),
                    Some(cnf.literals.len() as u32)
                );
                prop_assert!(cnf.clause_offsets.windows(2).all(|w| w[0] <= w[1]));
            }

            // --------------------------------------------------------------
            // Property E2: All variable indices in clauses are within
            // [-num_vars, num_vars] \ {0}.
            // --------------------------------------------------------------
            #[test]
            fn prop_clause_indices_in_bounds(n in 0usize..=20usize) {
                let model = model_with_layer_restrictions(n);
                let (cnf, _) = encode_to_cnf(&model);
                let num_v = cnf.num_vars as i32;
                for clause in cnf.clauses() {
                    for &lit in clause {
                        prop_assert!(lit != 0,
                            "clause contains literal 0");
                        prop_assert!(lit.unsigned_abs() <= num_v as u32,
                            "literal {lit} out of range [1, {num_v}]");
                    }
                }
            }

            // --------------------------------------------------------------
            // Property E3: No clause is empty.
            // --------------------------------------------------------------
            #[test]
            fn prop_no_empty_clauses(n in 0usize..=20usize) {
                let model = model_with_layer_restrictions(n);
                let (cnf, _) = encode_to_cnf(&model);
                for clause in cnf.clauses() {
                    prop_assert!(!clause.is_empty(),
                        "encoded CNF contains an empty clause");
                }
            }

            // --------------------------------------------------------------
            // Property E4: No clause contains both a variable and its
            // negation => would be a tautology (can't happen for these
            // simple models but structurally important to check).
            // --------------------------------------------------------------
            #[test]
            fn prop_no_tautological_clause(n in 0usize..=10usize) {
                let model = model_with_layer_restrictions(n);
                let (cnf, _) = encode_to_cnf(&model);
                for clause in cnf.clauses() {
                    for &lit in clause {
                        // Check the negation is NOT also in the same clause.
                        prop_assert!(!clause.contains(&-lit),
                            "clause {:?} contains both {lit} and -{lit} (tautology)",
                            clause);
                    }
                }
            }

            // --------------------------------------------------------------
            // Property E5: For a model with no constraints, the CNF has
            // no clauses.
            // --------------------------------------------------------------
            #[test]
            fn prop_empty_constraints_no_clauses(n in 0usize..=10usize) {
                let model = model_with_net_channels(n);
                let (cnf, _) = encode_to_cnf(&model);
                prop_assert!(cnf.clauses_is_empty());
                prop_assert_eq!(cnf.num_vars, n);
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("encoding::tests::exhaustive_at_most_k_n1_to_n8", exhaustive_at_most_k_n1_to_n8),
        ("encoding::tests::encode_to_cnf_empty_model", encode_to_cnf_empty_model),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
