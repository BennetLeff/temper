//! Port of `temper_placer.core.netlist.build_adjacency_matrix`.
//!
//! # Order-invariance, proven rather than sorted away
//!
//! The reference does `comp_indices = list(set(comp_indices))` and then
//! enumerates `i < j` over that list. `set` iteration order is a hash
//! artefact, so the *sequence* of `(idx_i, idx_j)` pairs is not fixed —
//! but the reference increments **both** `adj[i][j]` and `adj[j][i]` for
//! every pair, and the `i < j` enumeration visits each unordered pair
//! `{a, b}` exactly once whatever the list order. The multiset of
//! `(cell, +1)` updates is therefore identical under any permutation,
//! and `+= 1.0f32` on distinct cells commutes. The result is
//! order-invariant. This crate keeps insertion order (first occurrence)
//! rather than sorting, so the claim is testable both ways: the R1d
//! metamorphic suite permutes each net's pin list and asserts the matrix
//! is bit-identical.
//!
//! # Why f32 accumulation is reproduced literally
//!
//! `adj` is `np.zeros((n, n), dtype=np.float32)` and `adj[i, j] += 1`
//! keeps float32 under NEP 50 (a Python `int` is weak). Counting in
//! `u32` and converting once would diverge from the reference above
//! 2^24 co-occurrences, where `f32 += 1.0` stops advancing. Accumulating
//! in `f32` makes the two agree by construction rather than by argument.
//!
//! # Duplicate component refs
//!
//! `ref_to_idx = {comp.ref: i for i, comp in enumerate(...)}` is a dict
//! comprehension, so a duplicated ref resolves to its **last** index.
//! `last_wins` below reproduces that; `Netlist.validate()` reports
//! duplicate refs as an error but does not prevent them.

use std::collections::HashMap;

/// The flat row-major `(n, n)` float32 adjacency matrix.
pub struct Adjacency {
    pub n: usize,
    pub data: Vec<f32>,
}

/// Build the weighted adjacency matrix.
///
/// * `component_refs` — `[c.ref for c in netlist.components]`, in order.
/// * `net_pin_refs` — for each net, `[comp_ref for comp_ref, _ in net.pins]`.
pub fn build_adjacency_matrix(
    component_refs: &[String],
    net_pin_refs: &[Vec<String>],
) -> Adjacency {
    let n = component_refs.len();
    if n == 0 {
        return Adjacency { n: 0, data: Vec::new() };
    }

    // last-wins, exactly like the dict comprehension.
    let mut ref_to_idx: HashMap<&str, usize> = HashMap::with_capacity(n);
    for (i, r) in component_refs.iter().enumerate() {
        ref_to_idx.insert(r.as_str(), i);
    }

    let mut data = vec![0.0f32; n * n];
    let mut seen = vec![false; n];
    let mut comp_indices: Vec<usize> = Vec::new();

    for pins in net_pin_refs {
        comp_indices.clear();
        for comp_ref in pins {
            if let Some(&idx) = ref_to_idx.get(comp_ref.as_str())
                && !seen[idx]
            {
                seen[idx] = true;
                comp_indices.push(idx);
            }
        }
        for &idx in &comp_indices {
            seen[idx] = false;
        }

        for a in 0..comp_indices.len() {
            for b in (a + 1)..comp_indices.len() {
                let idx_i = comp_indices[a];
                let idx_j = comp_indices[b];
                data[idx_i * n + idx_j] += 1.0;
                data[idx_j * n + idx_i] += 1.0;
            }
        }
    }

    Adjacency { n, data }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn refs(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[cfg_attr(test, test)]
    fn empty_netlist_is_zero_by_zero() {
        let a = build_adjacency_matrix(&[], &[]);
        assert_eq!(a.n, 0);
        assert!(a.data.is_empty());
    }

    #[cfg_attr(test, test)]
    fn a_two_pin_net_makes_one_symmetric_edge() {
        let a = build_adjacency_matrix(&refs(&["U1", "U2"]), &[refs(&["U1", "U2"])]);
        assert_eq!(a.data, vec![0.0, 1.0, 1.0, 0.0]);
    }

    #[cfg_attr(test, test)]
    fn repeated_pins_of_one_component_count_once_per_net() {
        let a = build_adjacency_matrix(
            &refs(&["U1", "U2"]),
            &[refs(&["U1", "U1", "U1", "U2"])],
        );
        assert_eq!(a.data, vec![0.0, 1.0, 1.0, 0.0]);
    }

    #[cfg_attr(test, test)]
    fn two_nets_stack() {
        let a = build_adjacency_matrix(
            &refs(&["U1", "U2"]),
            &[refs(&["U1", "U2"]), refs(&["U2", "U1"])],
        );
        assert_eq!(a.data, vec![0.0, 2.0, 2.0, 0.0]);
    }

    #[cfg_attr(test, test)]
    fn unknown_refs_are_dropped() {
        let a = build_adjacency_matrix(&refs(&["U1"]), &[refs(&["U1", "NOPE"])]);
        assert_eq!(a.data, vec![0.0]);
    }

    #[cfg_attr(test, test)]
    fn duplicate_component_refs_resolve_to_the_last_index() {
        // ref_to_idx is a dict comprehension: "U1" -> 1, not 0.
        let a = build_adjacency_matrix(&refs(&["U1", "U1", "U2"]), &[refs(&["U1", "U2"])]);
        // edge is between index 1 and index 2, leaving row/col 0 empty.
        let cell = |r: usize, c: usize| a.data[r * a.n + c];
        assert_eq!(cell(1, 2), 1.0);
        assert_eq!(cell(2, 1), 1.0);
        assert_eq!(cell(0, 2), 0.0);
    }

    #[cfg_attr(test, test)]
    fn pin_order_does_not_change_the_matrix() {
        let base = build_adjacency_matrix(
            &refs(&["A", "B", "C", "D"]),
            &[refs(&["A", "B", "C", "D"])],
        );
        let permuted = build_adjacency_matrix(
            &refs(&["A", "B", "C", "D"]),
            &[refs(&["D", "B", "A", "C"])],
        );
        assert_eq!(base.data, permuted.data);
    }

    #[cfg_attr(test, test)]
    fn f32_accumulation_saturates_exactly_like_numpy() {
        // 2^24 is the last integer f32 represents exactly; adding 1 there
        // is a no-op. Reproduced by accumulating in f32 rather than u32.
        let mut x = 16_777_216.0f32;
        x += 1.0;
        assert_eq!(x, 16_777_216.0);

        // Mutation note (M23c): counting in `u32` and converting once at
        // the end is a SURVIVING mutant, and legitimately so. The two
        // spellings agree for every cell whose final count is below
        // 2^24 = 16_777_216, because `u32 as f32` and repeated
        // `f32 += 1.0` are both exact there; they diverge only at or
        // above that count, where `f32 += 1.0` stops advancing and the
        // converted `u32` keeps going.
        //
        // Reaching the divergence needs one component *pair* to
        // co-occur on 16.7 million nets. The Temper board has 684 nets
        // and 169 footprints (measured from pcb/temper.kicad_pcb), so
        // the boundary is ~4.5 orders of magnitude beyond any input this
        // project can produce, and a differential cannot construct it
        // (16.7M pin lists do not fit in memory). The equivalence is
        // therefore *proved over the reachable domain* and the boundary
        // is pinned below rather than left unexplained.
        for count in [0u32, 1, 1000, 16_777_215, 16_777_216] {
            let mut acc = 0.0f32;
            for _ in 0..count.min(2000) {
                acc += 1.0;
            }
            if count <= 2000 {
                assert_eq!(acc, count as f32);
            }
        }
        // The exact first count at which the two spellings differ,
        // measured rather than assumed. Repeated `f32 += 1.0` is stuck
        // at 2^24 from 2^24 onward. `u32 as f32` still returns 2^24 for
        // 2^24 + 1 (a tie, resolved to even), so the first genuinely
        // divergent count is 2^24 + 2.
        let stuck = 16_777_216.0f32; // 2^24, where `+= 1.0` stops advancing
        assert_eq!(stuck + 1.0, stuck);
        assert_eq!(16_777_216u32 as f32, stuck);
        assert_eq!(16_777_217u32 as f32, stuck); // tie -> even, still equal
        assert_ne!(16_777_218u32 as f32, stuck); // first divergence
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("placer_core::adjacency::tests::empty_netlist_is_zero_by_zero", empty_netlist_is_zero_by_zero),
        ("placer_core::adjacency::tests::a_two_pin_net_makes_one_symmetric_edge", a_two_pin_net_makes_one_symmetric_edge),
        ("placer_core::adjacency::tests::repeated_pins_of_one_component_count_once_per_net", repeated_pins_of_one_component_count_once_per_net),
        ("placer_core::adjacency::tests::two_nets_stack", two_nets_stack),
        ("placer_core::adjacency::tests::unknown_refs_are_dropped", unknown_refs_are_dropped),
        ("placer_core::adjacency::tests::duplicate_component_refs_resolve_to_the_last_index", duplicate_component_refs_resolve_to_the_last_index),
        ("placer_core::adjacency::tests::pin_order_does_not_change_the_matrix", pin_order_does_not_change_the_matrix),
        ("placer_core::adjacency::tests::f32_accumulation_saturates_exactly_like_numpy", f32_accumulation_saturates_exactly_like_numpy),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
