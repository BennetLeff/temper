//! Zone-assignment backtracking search.
//!
//! # Why the candidate order is an *input*
//!
//! `ZoneSolver._backtrack` iterates `self._candidates[component]`, which is a
//! Python `set` of zone names, and returns the first assignment that succeeds.
//! Set iteration order for strings is salted by PYTHONHASHSEED, so the solver
//! is **nondeterministic across processes** — measured on origin/main
//! f57b52d51: the same 3 components over 5 zones assign to `ZA`, `ZD` or `ZB`
//! depending only on the seed.
//!
//! That means "bit-identical to Python" is not a property of the *algorithm*;
//! it is a property of the algorithm *plus* the order it was handed. So this
//! kernel takes the candidate lists as ordered slices and never sorts them.
//! The Python shim passes its own live `list(self._candidates[c])`, which
//! makes the composed behaviour identical to the pre-migration code on every
//! run, hash seed included — without this port either inheriting the
//! nondeterminism into Rust or silently "fixing" it, which would be an
//! unobservable behaviour change (the #688 judgment).

/// Depth-first assignment over `candidates[i]` for `components[i]`.
///
/// Returns the chosen zone index per component, or `None` if no complete
/// assignment exists. `components` is expected pre-ordered by the caller's
/// most-constrained-variable heuristic.
pub fn zone_backtrack(candidates: &[Vec<usize>]) -> Option<Vec<usize>> {
    let mut chosen = Vec::with_capacity(candidates.len());
    if search(candidates, 0, &mut chosen) { Some(chosen) } else { None }
}

fn search(candidates: &[Vec<usize>], depth: usize, chosen: &mut Vec<usize>) -> bool {
    if depth == candidates.len() {
        return true;
    }
    for &zone in &candidates[depth] {
        chosen.push(zone);
        // `_is_consistent` is unconditionally True in the Python today. The
        // recursion is kept rather than collapsed to "take the first
        // candidate" so that adding a real consistency check later is a local
        // change here, not a re-derivation of the search.
        if is_consistent(chosen) && search(candidates, depth + 1, chosen) {
            return true;
        }
        chosen.pop();
    }
    false
}

/// Mirrors `ZoneSolver._is_consistent`, which accepts every partial
/// assignment. Kept as a named seam so the intent is explicit.
#[inline]
fn is_consistent(_partial: &[usize]) -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_components_is_a_trivially_complete_assignment() {
        assert_eq!(zone_backtrack(&[]), Some(vec![]));
    }

    #[test]
    fn an_empty_candidate_list_makes_the_problem_unsolvable() {
        assert_eq!(zone_backtrack(&[vec![0], vec![]]), None);
    }

    #[test]
    fn the_first_candidate_in_the_given_order_wins() {
        assert_eq!(zone_backtrack(&[vec![2, 0, 1]]), Some(vec![2]));
        assert_eq!(zone_backtrack(&[vec![1, 0, 2]]), Some(vec![1]));
    }

    #[test]
    fn candidate_order_is_never_normalised() {
        // Two orders of the same candidate *set* must give different answers,
        // proving the kernel does not sort behind the caller's back.
        let a = zone_backtrack(&[vec![0, 1, 2]]);
        let b = zone_backtrack(&[vec![2, 1, 0]]);
        assert_ne!(a, b);
    }

    #[test]
    fn every_component_receives_a_zone_from_its_own_list() {
        let cands = vec![vec![1, 0], vec![0], vec![2, 1]];
        let Some(got) = zone_backtrack(&cands) else {
            panic!("all candidate lists are non-empty, so a solution must exist")
        };
        assert_eq!(got.len(), 3);
        for (i, z) in got.iter().enumerate() {
            assert!(cands[i].contains(z));
        }
    }
}
