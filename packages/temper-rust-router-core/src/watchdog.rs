// Lazy grounding watchdog — CEGAR loop between incremental CaDiCaL solves.
//
// Origin: U4 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
//
// Flow: solve safety CNF → inspect assignment → detect Performance
// violations → instantiate per-net vars + blocking clauses → re-solve.

use std::collections::HashMap;
use std::time::Instant;

use rustsat::{
    solvers::{Solve, SolverResult},
    types::{Clause, Lit, TernaryVal, Var},
};
use rustsat_cadical::CaDiCaL;

use crate::types::{BundledSolverResult, InternalBundleManifest, SolverStatus};

/// Maximum CEGAR iterations before returning Unknown.
const MAX_CEGAR_ITERATIONS: usize = 20;

/// Budget multiplier M (R7.1 — initial value: 10).
const BUDGET_MULTIPLIER: usize = 10;

/// A detected Performance constraint violation.
#[derive(Debug)]
#[allow(dead_code)]
struct Violation {
    bundle_id: usize,
    kind: ViolationKind,
    channel_id: String,
}

#[derive(Debug)]
enum ViolationKind {
    DiffPairSplit,
    CapacityExceeded,
}

/// The CEGAR watchdog.
pub struct Watchdog<'term, 'learn> {
    solver: CaDiCaL<'term, 'learn>,
    manifest: InternalBundleManifest,
    /// Per-net variable names → SAT indices
    per_net_var_map: HashMap<String, usize>,
    /// Fixed number of class-level variables (from safety CNF)
    eager_var_count: usize,
    /// Total budget for per-net variable instantiation
    budget_total: usize,
    /// Consumed budget
    budget_used: usize,
    /// Iteration counter
    cegar_iterations: usize,
    /// Nets marked for A* fallback due to budget exhaustion
    budget_exhausted_nets: Vec<String>,
    /// Mapping from SAT index → variable name (for result extraction)
    var_names: Vec<String>,
}

impl<'term, 'learn> Watchdog<'term, 'learn> {
    /// Create a new watchdog with a safety-only CNF already loaded into the solver.
    ///
    /// `class_var_names` are the SAT variable names for class-level variables.
    /// `class_var_count` is the number of class-variable SAT indices.
    /// `net_names` maps net_idx → net name string (for degraded logging).
    pub fn new(
        solver: CaDiCaL<'term, 'learn>,
        class_var_names: Vec<String>,
        class_var_count: usize,
        manifest: InternalBundleManifest,
        _net_names: &[String],
    ) -> Self {
        // Compute budget (R7.1).
        let total_nets_in_bundles: usize = manifest
            .bundles
            .iter()
            .map(|b| b.net_indices.len())
            .sum();
        let budget_total = BUDGET_MULTIPLIER * total_nets_in_bundles.max(1);

        Self {
            solver,
            manifest,
            per_net_var_map: HashMap::new(),
            eager_var_count: class_var_count,
            budget_total,
            budget_used: 0,
            cegar_iterations: 0,
            budget_exhausted_nets: Vec::new(),
            var_names: class_var_names,
        }
    }

    /// Run the full CEGAR loop. Returns a BundledSolverResult.
    pub fn solve(&mut self, net_names: &[String]) -> BundledSolverResult {
        let start = Instant::now();

        loop {
            // ----- Step 1: Solve -----
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                self.solver.solve()
            }));

            let elapsed = start.elapsed().as_secs_f64() * 1000.0;

            let result = match result {
                Ok(r) => r,
                Err(_) => {
                    return BundledSolverResult {
                        status: SolverStatus::Unknown,
                        assignments: HashMap::new(),
                        var_names: self.var_names.clone(),
                        num_vars: self.var_names.len(),
                        num_clauses: 0,
                        solver_time_ms: elapsed,
                        cegar_iterations: self.cegar_iterations,
                        budget_used: self.budget_used,
                        degraded_nets: self.budget_exhausted_nets.clone(),
                    };
                }
            };

            match result {
                Ok(SolverResult::Unsat) => {
                    return BundledSolverResult {
                        status: SolverStatus::Unsatisfiable,
                        assignments: HashMap::new(),
                        var_names: self.var_names.clone(),
                        num_vars: self.var_names.len(),
                        num_clauses: 0,
                        solver_time_ms: elapsed,
                        cegar_iterations: self.cegar_iterations,
                        budget_used: self.budget_used,
                        degraded_nets: self.budget_exhausted_nets.clone(),
                    };
                }
                Ok(SolverResult::Interrupted) => {
                    return BundledSolverResult {
                        status: SolverStatus::Unknown,
                        assignments: HashMap::new(),
                        var_names: self.var_names.clone(),
                        num_vars: self.var_names.len(),
                        num_clauses: 0,
                        solver_time_ms: elapsed,
                        cegar_iterations: self.cegar_iterations,
                        budget_used: self.budget_used,
                        degraded_nets: self.budget_exhausted_nets.clone(),
                    };
                }
                Ok(SolverResult::Sat) => {
                    let sol = match self.solver.full_solution() {
                        Ok(s) => s,
                        Err(_) => {
                            return BundledSolverResult {
                                status: SolverStatus::Unknown,
                                assignments: HashMap::new(),
                                var_names: self.var_names.clone(),
                                num_vars: self.var_names.len(),
                                num_clauses: 0,
                                solver_time_ms: elapsed,
                                cegar_iterations: self.cegar_iterations,
                                budget_used: self.budget_used,
                                degraded_nets: self.budget_exhausted_nets.clone(),
                            };
                        }
                    };

                    // Build assignment map for current var count
                    let mut assignments = HashMap::new();
                    for i in 0..self.var_names.len() {
                        if (i as u32) < sol.len() as u32 {
                            match sol[Var::new(i as u32)] {
                                TernaryVal::True => { assignments.insert(i, true); }
                                TernaryVal::False => { assignments.insert(i, false); }
                                TernaryVal::DontCare => {}
                            }
                        }
                    }

                    // ----- Step 2: Inspect for Performance violations -----
                    let violations = self.inspect_violations(&assignments);

                    if violations.is_empty() {
                        return BundledSolverResult {
                            status: SolverStatus::Satisfiable,
                            assignments,
                            var_names: self.var_names.clone(),
                            num_vars: self.var_names.len(),
                            num_clauses: 0,
                            solver_time_ms: elapsed,
                            cegar_iterations: self.cegar_iterations,
                            budget_used: self.budget_used,
                            degraded_nets: self.budget_exhausted_nets.clone(),
                        };
                    }

                    // ----- Step 3: Instantiate per-net vars + blocking clauses -----
                    let clauses_added = self.instantiate_per_net_vars(
                        &violations, net_names,
                    );

                    // Check iteration limit
                    self.cegar_iterations += 1;
                    if self.cegar_iterations >= MAX_CEGAR_ITERATIONS {
                        return BundledSolverResult {
                            status: SolverStatus::Unknown,
                            assignments,
                            var_names: self.var_names.clone(),
                            num_vars: self.var_names.len(),
                            num_clauses: 0,
                            solver_time_ms: elapsed,
                            cegar_iterations: self.cegar_iterations,
                            budget_used: self.budget_used,
                            degraded_nets: self.budget_exhausted_nets.clone(),
                        };
                    }

                    if !clauses_added {
                        // Budget exhausted for all violations — return degraded.
                        return BundledSolverResult {
                            status: SolverStatus::Satisfiable,
                            assignments,
                            var_names: self.var_names.clone(),
                            num_vars: self.var_names.len(),
                            num_clauses: 0,
                            solver_time_ms: elapsed,
                            cegar_iterations: self.cegar_iterations,
                            budget_used: self.budget_used,
                            degraded_nets: self.budget_exhausted_nets.clone(),
                        };
                    }

                    // Loop: re-solve with new blocking clauses.
                }
                Err(_) => {
                    return BundledSolverResult {
                        status: SolverStatus::Unsatisfiable,
                        assignments: HashMap::new(),
                        var_names: self.var_names.clone(),
                        num_vars: self.var_names.len(),
                        num_clauses: 0,
                        solver_time_ms: elapsed,
                        cegar_iterations: self.cegar_iterations,
                        budget_used: self.budget_used,
                        degraded_nets: self.budget_exhausted_nets.clone(),
                    };
                }
            }
        }
    }

    /// Inspect full assignment for Performance constraint violations.
    ///
    /// For each diff-pair bundle: check if the bundle's class variable is
    /// assigned TRUE on more than one channel (split possible).
    fn inspect_violations(
        &self,
        assignments: &HashMap<usize, bool>,
    ) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Find class variables that are TRUE, grouped by bundle.
        // Naming convention: uses_B{bundle_id}_{channel_id}
        let mut bundle_true_channels: HashMap<usize, Vec<String>> = HashMap::new();

        for (idx, val) in assignments {
            if !val || *idx >= self.var_names.len() {
                continue;
            }
            let name = &self.var_names[*idx];
            if name.starts_with("uses_B") {
                // Parse uses_B{bundle_id}_{channel_id}
                let rest = &name[6..]; // strip "uses_B"
                if let Some(underscore_pos) = rest.find('_') {
                    let bid_str = &rest[..underscore_pos];
                    let ch_id = &rest[underscore_pos + 1..];
                    if let Ok(bid) = bid_str.parse::<usize>() {
                        bundle_true_channels
                            .entry(bid)
                            .or_default()
                            .push(ch_id.to_string());
                    }
                }
            }
        }

        // Check diff-pair bundles: if the bundle has >1 true channel, it's split.
        for bundle in &self.manifest.bundles {
            if !bundle.is_diff_pair {
                continue;
            }
            let chs = bundle_true_channels
                .get(&bundle.bundle_id)
                .map(|v| v.len())
                .unwrap_or(0);
            if chs > 1 {
                let ch_list = &bundle_true_channels[&bundle.bundle_id];
                violations.push(Violation {
                    bundle_id: bundle.bundle_id,
                    kind: ViolationKind::DiffPairSplit,
                    channel_id: ch_list[0].clone(),
                });
            }
        }

        // Check capacity: if any channel has more class vars assigned than
        // the AtMostK allows. The safety CNF already enforces this for class
        // vars, so we only check if per-net vars were explicitly instantiated
        // and may have broken the capacity bound.
        // (For now, the safety CNF class-level AtMostK handles this.)

        violations
    }

    /// Instantiate per-net variables and add blocking clauses for violations.
    ///
    /// Returns true if at least one clause was added.
    fn instantiate_per_net_vars(
        &mut self,
        violations: &[Violation],
        net_names: &[String],
    ) -> bool {
        let mut any_added = false;

        for v in violations {
            if self.budget_used >= self.budget_total {
                // Mark remaining bundle nets as degraded.
                if let Some(bundle) = self.manifest.bundles.iter().find(|b| b.bundle_id == v.bundle_id) {
                    for &ni in &bundle.net_indices {
                        if let Some(name) = net_names.get(ni) {
                            if !self.budget_exhausted_nets.contains(name) {
                                self.budget_exhausted_nets.push(name.clone());
                            }
                        }
                    }
                }
                continue;
            }

            match &v.kind {
                ViolationKind::DiffPairSplit => {
                    any_added |= self.instantiate_diff_pair_clauses(v.bundle_id);
                }
                ViolationKind::CapacityExceeded => {
                    // Covered by safety CNF at class level.
                }
            }
        }

        any_added
    }

    /// For a diff-pair bundle, create per-net variables and add equivalence
    /// clauses ensuring both members use the same channels.
    fn instantiate_diff_pair_clauses(&mut self, bundle_id: usize) -> bool {
        let bundle = match self.manifest.bundles.iter().find(|b| b.bundle_id == bundle_id) {
            Some(b) => b,
            None => return false,
        };

        if bundle.net_indices.len() != 2 {
            return false;
        }

        let p_idx = bundle.net_indices[0];
        let n_idx = bundle.net_indices[1];

        // Collect channel IDs from class variables for this bundle
        let mut channel_ids: Vec<String> = Vec::new();
        for name in &self.var_names {
            if name.starts_with("uses_B") {
                let rest = &name[6..];
                if rest.starts_with(&format!("{bundle_id}_")) {
                    let ch = rest[format!("{bundle_id}_").len()..].to_string();
                    channel_ids.push(ch);
                }
            }
        }

        let mut any_added = false;

        for ch in &channel_ids {
            let p_name = format!("uses_N{p_idx}_{ch}");
            let n_name = format!("uses_N{n_idx}_{ch}");

            // Create per-net variables (CaDiCaL creates them implicitly from
            // literals in clauses; we track the names).
            let p_var = self.get_or_add_var(&p_name);
            let n_var = self.get_or_add_var(&n_name);
            if p_var == n_var {
                continue;
            }

            // Equivalence: (¬p ∨ n) ∧ (p ∨ ¬n)
            let clause1 = vec![Lit::negative((p_var as u32 + 1) as u32), Lit::positive((n_var as u32 + 1) as u32)];
            let clause2 = vec![Lit::positive((p_var as u32 + 1) as u32), Lit::negative((n_var as u32 + 1) as u32)];

            if self.solver.add_clause(Clause::from(&clause1[..])).is_ok()
                && self.solver.add_clause(Clause::from(&clause2[..])).is_ok()
            {
                self.budget_used += 2; // cost of creating two per-net vars
                any_added = true;
            }
        }

        any_added
    }

    /// Get or create a SAT variable index for the given name.
    fn get_or_add_var(&mut self, name: &str) -> usize {
        if let Some(&idx) = self.per_net_var_map.get(name) {
            return idx;
        }
        let idx = self.var_names.len();
        self.var_names.push(name.to_string());
        self.per_net_var_map.insert(name.to_string(), idx);
        idx
    }
}
