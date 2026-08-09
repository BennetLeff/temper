//! Topological placement compute for `temper_placer.topological` (Wave 4,
//! Phase 4).
//!
//! Graph clustering, constraint propagation, force-directed refinement and
//! initial placement, ported from Python under the R1 gate set. The Python
//! package keeps its public API and its networkx storage; only the compute
//! moved.
//!
//! # Ordering contract
//!
//! Several inputs here carry an order that is *incidental* in Python — it
//! comes from `set`/`dict` iteration or from networkx insertion order — yet
//! is observable in the output. Every such input is taken as an ordered slice
//! and is consumed exactly as given. Nothing in this crate sorts a
//! caller-supplied sequence. See `zone.rs` for the fully worked case.

pub mod force;
pub mod graph;
pub mod heuristics;
pub mod numeric;
pub mod placement;
pub mod propagation;
pub mod zone;

#[cfg(feature = "python")]
mod bridge {
    use pyo3::IntoPyObjectExt;
    use pyo3::prelude::*;

    use crate::{force, graph, heuristics, placement, propagation, zone};

    /// Run a kernel with a panic guard at the pyo3 boundary (R1g): a Rust
    /// panic must surface as a Python exception, never unwind into CPython.
    fn catch_unwind_py<F, R>(f: F) -> PyResult<R>
    where
        F: FnOnce() -> R + std::panic::UnwindSafe,
    {
        temper_py_bridge::catch_unwind(f).map_err(temper_py_bridge::panic_to_err)
    }

    /// Transitive adjacency closure from `seed`.
    ///
    /// `edges` is `(source, target, edge_type, distance)` in graph order.
    #[pyfunction]
    fn adjacency_cluster(
        seed: &str,
        edges: Vec<(String, String, String, f64)>,
    ) -> PyResult<Vec<String>> {
        catch_unwind_py(|| {
            let borrowed: Vec<graph::Edge<'_>> = edges
                .iter()
                .map(|(s, t, ty, d)| graph::Edge {
                    source: s.as_str(),
                    target: t.as_str(),
                    edge_type: ty.as_str(),
                    distance: *d,
                })
                .collect();
            graph::adjacency_cluster(seed, &borrowed)
        })
    }

    /// Indices of conflicting `(adjacent_edge, separated_edge)` pairs.
    #[pyfunction]
    fn separation_conflicts(
        edges: Vec<(String, String, String, f64)>,
    ) -> PyResult<Vec<(usize, usize)>> {
        catch_unwind_py(|| {
            let borrowed: Vec<graph::Edge<'_>> = edges
                .iter()
                .map(|(s, t, ty, d)| graph::Edge {
                    source: s.as_str(),
                    target: t.as_str(),
                    edge_type: ty.as_str(),
                    distance: *d,
                })
                .collect();
            graph::separation_conflicts(&borrowed)
        })
    }

    /// Floyd-Warshall bound propagation.
    ///
    /// Returns `(feasible, min_matrix, max_matrix)` with both matrices flat
    /// row-major of length `n * n`.
    #[pyfunction]
    fn propagate_bounds(
        n: usize,
        adjacent: Vec<(usize, usize, f64)>,
        separated: Vec<(usize, usize, f64)>,
        max_iterations: usize,
    ) -> PyResult<(bool, Vec<f64>, Vec<f64>)> {
        catch_unwind_py(|| {
            let out = propagation::propagate(n, &adjacent, &separated, max_iterations);
            let mins = out.bounds.iter().map(|b| b.min_distance).collect();
            let maxs = out.bounds.iter().map(|b| b.max_distance).collect();
            (out.feasible, mins, maxs)
        })
    }

    #[pyfunction]
    fn adjacency_force(
        pos_a: (f64, f64),
        pos_b: (f64, f64),
        target_distance: f64,
    ) -> PyResult<((f64, f64), (f64, f64))> {
        catch_unwind_py(|| force::adjacency_force(pos_a, pos_b, target_distance))
    }

    #[pyfunction]
    fn separation_force(
        pos_a: (f64, f64),
        pos_b: (f64, f64),
        min_distance: f64,
    ) -> PyResult<((f64, f64), (f64, f64))> {
        catch_unwind_py(|| force::separation_force(pos_a, pos_b, min_distance))
    }

    #[pyfunction]
    fn boundary_force(position: (f64, f64), bounds: (f64, f64, f64, f64)) -> PyResult<(f64, f64)> {
        catch_unwind_py(|| force::boundary_force(position, bounds))
    }

    /// Force-directed refinement over caller-ordered edges.
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn force_refine(
        positions: Vec<(f64, f64)>,
        adjacencies: Vec<(usize, usize, f64)>,
        separations: Vec<(usize, usize, f64)>,
        zone_bounds: Vec<(f64, f64, f64, f64)>,
        iterations: usize,
        lr: f64,
    ) -> PyResult<Vec<(f64, f64)>> {
        if zone_bounds.len() != positions.len() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "zone_bounds must be parallel to positions",
            ));
        }
        let n = positions.len();
        for &(i, j, _) in adjacencies.iter().chain(separations.iter()) {
            if i >= n || j >= n {
                return Err(pyo3::exceptions::PyIndexError::new_err(
                    "edge endpoint out of range for positions",
                ));
            }
        }
        catch_unwind_py(|| {
            force::force_refine(
                &positions,
                &adjacencies,
                &separations,
                &zone_bounds,
                iterations,
                lr,
            )
        })
    }

    /// Union-find clustering; returns clusters as index lists.
    #[pyfunction]
    fn identify_clusters(
        components: Vec<String>,
        adjacent: Vec<(usize, usize)>,
    ) -> PyResult<Vec<Vec<usize>>> {
        let n = components.len();
        for &(a, b) in &adjacent {
            if a >= n || b >= n {
                return Err(pyo3::exceptions::PyIndexError::new_err(
                    "adjacency endpoint out of range for components",
                ));
            }
        }
        catch_unwind_py(|| placement::identify_clusters(&components, &adjacent))
    }

    /// Circular arrangement inside a zone.
    ///
    /// Returns `("ok", positions)`, `("component_too_large", index,
    /// zone_width, zone_height)` or `("zone_too_small", total_area,
    /// zone_area)`. Errors are returned rather than raised so the Python
    /// caller can format `PlacementError` with CPython's own float
    /// formatting.
    #[pyfunction]
    fn place_components_in_zone(
        bounds: (f64, f64, f64, f64),
        sizes: Vec<(f64, f64)>,
    ) -> PyResult<Py<PyAny>> {
        let outcome = catch_unwind_py(|| placement::place_components_in_zone(bounds, &sizes))?;
        Python::attach(|py| match outcome {
            placement::ZonePlacement::Placed(p) => ("ok", p).into_py_any(py),
            placement::ZonePlacement::ComponentTooLarge(i, w, h) => {
                ("component_too_large", i, w, h).into_py_any(py)
            }
            placement::ZonePlacement::ZoneTooSmall(total, zone) => {
                ("zone_too_small", total, zone).into_py_any(py)
            }
        })
    }

    #[pyfunction]
    fn place_cluster(
        bounds: (f64, f64, f64, f64),
        sorted_sizes: Vec<(f64, f64)>,
        min_adjacency_distance: f64,
        cluster_index: usize,
        total_clusters: usize,
    ) -> PyResult<Vec<(f64, f64)>> {
        catch_unwind_py(|| {
            placement::place_cluster(
                bounds,
                &sorted_sizes,
                min_adjacency_distance,
                cluster_index,
                total_clusters,
            )
        })
    }

    /// Backtracking zone assignment over caller-ordered candidate lists.
    #[pyfunction]
    fn zone_backtrack(candidates: Vec<Vec<usize>>) -> PyResult<Option<Vec<usize>>> {
        catch_unwind_py(|| zone::zone_backtrack(&candidates))
    }

    // --- heuristics/ slice (Wave 4) ---

    /// First overlapping placement; returns `(index, overlap)` or `None`.
    #[pyfunction]
    fn overlap_check(
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        boxes: Vec<(f64, f64, f64, f64)>,
        min_spacing: f64,
    ) -> PyResult<Option<(usize, f64)>> {
        catch_unwind_py(|| heuristics::overlap_check(x, y, width, height, &boxes, min_spacing))
    }

    /// Ordered nudge candidates: the primary + the four fallback directions.
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn nudge_candidates(
        x: f64,
        y: f64,
        cx: f64,
        cy: f64,
        overlap_mm: f64,
        min_spacing: f64,
    ) -> PyResult<Vec<(f64, f64)>> {
        catch_unwind_py(|| heuristics::nudge_candidates(x, y, cx, cy, overlap_mm, min_spacing))
    }

    /// Feasibility arithmetic; returns `(fits, total_component_area,
    /// total_zone_area)`.
    #[pyfunction]
    fn feasibility_check(
        sizes: Vec<(f64, f64)>,
        zone_dims: Vec<(f64, f64)>,
        margin: f64,
    ) -> PyResult<(Vec<bool>, f64, f64)> {
        catch_unwind_py(|| heuristics::feasibility_check(&sizes, &zone_dims, margin))
    }

    /// Boundary clamp with numpy `np.clip` semantics (B12).
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn clamp_position(
        x: f64,
        y: f64,
        width: f64,
        height: f64,
        board_w: f64,
        board_h: f64,
        margin: f64,
    ) -> PyResult<(f64, f64)> {
        catch_unwind_py(|| heuristics::clamp_position(x, y, width, height, board_w, board_h, margin))
    }

    #[pymodule]
    fn temper_placement_topology(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(adjacency_cluster, m)?)?;
        m.add_function(wrap_pyfunction!(separation_conflicts, m)?)?;
        m.add_function(wrap_pyfunction!(propagate_bounds, m)?)?;
        m.add_function(wrap_pyfunction!(adjacency_force, m)?)?;
        m.add_function(wrap_pyfunction!(separation_force, m)?)?;
        m.add_function(wrap_pyfunction!(boundary_force, m)?)?;
        m.add_function(wrap_pyfunction!(force_refine, m)?)?;
        m.add_function(wrap_pyfunction!(identify_clusters, m)?)?;
        m.add_function(wrap_pyfunction!(place_components_in_zone, m)?)?;
        m.add_function(wrap_pyfunction!(place_cluster, m)?)?;
        m.add_function(wrap_pyfunction!(zone_backtrack, m)?)?;
        m.add_function(wrap_pyfunction!(overlap_check, m)?)?;
        m.add_function(wrap_pyfunction!(nudge_candidates, m)?)?;
        m.add_function(wrap_pyfunction!(feasibility_check, m)?)?;
        m.add_function(wrap_pyfunction!(clamp_position, m)?)?;
        Ok(())
    }
}
