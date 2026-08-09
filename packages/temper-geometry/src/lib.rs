// When `--no-default-features` deactivates `python`, the pyo3-bridge code
// (each module's `register`, `*_py` functions) is not compiled.  Functions
// reachable ONLY through those bridges then appear dead — they are not, but
// clippy cannot see past the cfg gate.  Allow dead_code in the no-python
// config; the production (python ON) build gates nothing.
// WASM CI guard (plan 2026-08-03-002, U3).
#![cfg_attr(not(feature = "python"), allow(dead_code))]
pub mod types;
pub mod primitives;
pub mod smooth;
pub mod polygon;
pub mod sdf;
pub mod transform;
pub mod overlap;
pub mod projections;
pub mod constraints;
pub mod drc_inflate;
// Wholly pyo3 surface (see congestion_tensor.rs's module doc comment for
// why this can't be split into a kernel + wrapper like the other modules).
#[cfg(feature = "python")]
pub mod congestion_tensor;
// Wave 4 Phase 4: analysis/_area_sufficiency.py aggregation kernels
// (wholly pyo3 surface — the module is the pyfunction wrapper + the
// Neumaier kernel it owns).
#[cfg(feature = "python")]
pub mod area_sufficiency;
pub mod copper_reach;
pub mod pad_geometry;
// Wave 4 Phase B: router_v6/escape_via_generator.py (survey cluster G, split)
// and the six-module congestion & placement-feedback cluster E. Both are
// wholly pyo3 surfaces: the kernel and its bridge are one module, because
// every entry point exists to mirror one Python function bit-for-bit.
#[cfg(feature = "python")]
pub mod congestion;
#[cfg(feature = "python")]
pub mod congestion_analysis;
// Shared CPython-exact OverflowError construction for the `pow_operator`
// overflow guard duplicated in escape_via.rs and placement_suggestions.rs.
#[cfg(feature = "python")]
mod py_errors;
#[cfg(feature = "python")]
pub mod escape_via;
#[cfg(feature = "python")]
pub mod routing_demand;
#[cfg(feature = "python")]
pub mod placement_suggestions;
#[cfg(feature = "python")]
pub mod apply_suggestions;
#[cfg(feature = "python")]
pub mod congestion_heatmap;
pub mod clearance_geometry;
pub mod spice_estimators;
#[cfg(feature = "python")]
pub use pad_geometry::{
    barrier_axis_gap_py, best_rotation_for_barrier_py, pad_axis_radius_py, pad_bounding_radius_py,
    pad_corner_radius_py, pad_core_half_extents_py, pad_support_radius_py,
};
#[cfg(feature = "python")]
pub use clearance_geometry::{
    component_reach_py, copper_scan_py, origin_distance_py, pad_pair_distance_py,
    rotate_local_to_world_py,
};
#[cfg(feature = "python")]
pub use spice_estimators::{spice_infer_unit_py, spice_loop_inductance_py};
pub mod corridor;
pub mod copper_coverage;
pub mod channel_widths;
// KTD8 spike (docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md):
// exact Euclidean distance transform, Felzenszwalb-Huttenlocher. See
// docs/evidence/2026-08-07-exact-edt-rust-spike.md.
pub mod edt;
#[cfg(feature = "python")]
pub use edt::exact_edt_transform;
// KTD8 follow-up (docs/evidence/2026-08-07-rust-connected-components-spike.md):
// exact 8-connected connected-component labeling, matching
// scipy.ndimage.label(mask, structure=np.ones((3, 3), dtype=bool)) --
// routability_check.py's last scipy binding (check_routability_cc).
pub mod connected_components;
#[cfg(feature = "python")]
pub use connected_components::connected_components_8_transform;
pub mod grid_raster;
#[cfg(feature = "python")]
pub use grid_raster::{
    block_circle_into_grid_py, block_rect_into_grid_py, block_segment_into_grid_py,
    clear_circle_from_grid_py, closest_component_for_zone_py, effective_creepage_py,
    fence_samples_py, occupancy_bitmap_row_py,
};
#[cfg(feature = "python")]
pub mod occupancy_raster;
#[cfg(feature = "python")]
pub use occupancy_raster::{
    blocking_net_ids_py, downsample_or_blocks_py, mark_path_rect_into_grid_py,
    mark_segment_rect_into_grid_py, mark_via_circle_into_grid_py, unmark_path_rect_into_grid_py,
    unmark_segment_rect_into_grid_py,
};
pub mod host_math;
pub mod grid_utils;
#[cfg(feature = "python")]
pub use grid_utils::{add_endpoint_nudge_py, snap_to_grid_py};
pub mod via_placement;
#[cfg(feature = "python")]
pub use via_placement::{is_via_position_valid_py, place_via_with_clearance_py, via_distance_py};
pub mod bottleneck_geometry;
#[cfg(feature = "python")]
pub use bottleneck_geometry::{build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py};
// Wave 4 Phase B: temper_placer/heuristics/structural.py's create_keepout_mask.
pub mod heuristics_geometry;
#[cfg(feature = "python")]
pub use heuristics_geometry::keepout_mask_flags_py;
// Wave 4: temper_placer/heuristics/organizational.py's five _place_* position
// kernels (module grid, circular offset, power-flow stage layout, decoupling
// candidate positions, domain grid) -- see organizational_geometry.rs's
// module doc for the classification-vs-placement triage.
pub mod organizational_geometry;
#[cfg(feature = "python")]
pub use organizational_geometry::{
    circle_offsets_py, decoupling_candidate_positions_py, domain_grid_positions_py,
    module_grid_positions_py, power_flow_positions_py,
};
// Wave 4: temper_placer/heuristics/style.py's two _place_* position kernels
// (star-ground radial sector placement, signal-chain linear placement) --
// see style_geometry.rs's module doc for the classification-vs-placement
// triage.
pub mod style_geometry;
#[cfg(feature = "python")]
pub use style_geometry::{radial_sector_positions_py, signal_chain_positions_py};
pub mod audit;
pub mod creepage_check;
// Wave 4: placer/cp_sat/fixed_copper.py's pad-rotation/half-extent/item-
// geometry/exact-clearance-oracle kernels, carved out of the placer/cp_sat/**
// whole-subtree JUSTIFIED-KEEP per docs/evidence/2026-08-06-never-port-triage.md.
// Declared after congestion (ceil_to_int), creepage_check (py_min/py_max) and
// pad_geometry (math_cos_sin/py_hypot), which it reuses.
#[cfg(feature = "python")]
pub mod fixed_copper;
// Wave 4: router_v6/zone_emission.py + _zone_pour_stitch.py's geometry
// (emit_zone_s_expr, _chamfer_path_points, and _stitch_isolated_pads's
// point-in-polygon + nearest-vertex core). Wholly pyo3 surface, own
// register().
#[cfg(feature = "python")]
pub mod zone_pour;
// router_v6/zone_emission.py's `_cluster_positions`: Ward-linkage
// hierarchical clustering + flat-cut, replacing
// scipy.cluster.hierarchy.linkage/fcluster/pdist. See this module's own doc
// comment for the consumer-contract verification, crate choice, and the
// scipy-boundary tie-break semantics the flat-cut reconstruction depends on.
pub mod hierarchical_clustering;
// Wave 4, router_v6 core slice: the DRC constraint-geometry kernel behind
// router_v6/constraints_geometry.py. Declared after creepage_check because
// it reuses that module's CPython min/max replications.
pub mod drc_constraints_geometry;
// Wave 4: router_v6/channel_skeleton.py's medial-axis (Voronoi) extraction.
// Declared after creepage_check (py_min) and host_math (pow), which it
// reuses.
pub mod channel_skeleton;
// router_v6/channel_skeleton.py's island-bridging MST candidate generation:
// exact all-pairs-within-radius query (rstar R*-tree), replacing
// scipy.spatial.cKDTree.query_pairs. See
// docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md for the
// bridging algorithm this feeds, and this module's own doc comment for the
// crate-choice and tie-breaking contract determination.
pub mod radius_pairs;
#[cfg(feature = "python")]
pub use radius_pairs::radius_pairs_transform;
// router_v6/constraints_spatial_index.py's PCBGeometry: a persistent
// rstar R*-tree handle (build once per rebuild_index() batch, query many
// times via query_ball_point), replacing the per-kind scipy.spatial.cKDTree
// instances that call site built. Different contract from radius_pairs.rs
// above (one-shot batch all-pairs) -- see this module's own doc comment.
pub mod persistent_radius_index;
// scipy.spatial.ConvexHull -> geo::ConvexHull port for
// physics/loop_area.py + validation/trace_analyzer.py's hull *area* call
// sites (scalar-only consumers -- see docs/evidence/2026-08-07-scipy-keeps-
// re-triage.md Sec 2 and this module's own doc comment for the verified
// contract).
pub mod convex_hull;
#[cfg(feature = "python")]
pub use convex_hull::convex_hull_area_py;
// validation/mfem_compare.py's project_mfem_to_fdm: batch single-nearest-
// neighbor lookup (rstar), replacing
// scipy.interpolate.griddata(method="nearest"). One-shot batch shape, same
// as radius_pairs.rs above -- see this module's own doc comment for the
// contract determination and tie-breaking discussion.
pub mod nearest_neighbor;
#[cfg(feature = "python")]
pub use nearest_neighbor::nearest_neighbor_transform;
#[cfg(feature = "python")]
pub use drc_constraints_geometry::{
    drc_closest_points_segment_segment_py, drc_point_to_circle_distance_py,
    drc_point_to_rotated_rect_distance_py, drc_point_to_segment_distance_py,
    drc_rotated_rect_bounding_radius_py, drc_rotated_rect_corners_py, drc_segment_direction_py,
    drc_segment_length_py, drc_segment_midpoint_py, drc_segment_to_rotated_rect_distance_py,
    drc_segment_to_segment_distance_py, drc_segments_intersect_py,
};
#[cfg(feature = "python")]
mod bridge;

#[cfg(feature = "python")]
use pyo3::prelude::*;

// Wave 4: requirements/validators/_geometry.py's shared geometry helpers
// (distance, point-in-rect, rect overlap, point/segment/polyline kernels) —
// see geometry_kernels.rs's module doc for the numerical contract and why
// the segment kernels are NOT drc_constraints_geometry.rs's.  Python-gated
// like area_sufficiency.rs, which it reuses (py_sum_neumaier).
#[cfg(feature = "python")]
pub mod geometry_kernels;
// Wave 4: router_v6/channel_mapping.py's four pure-geometry kernels
// (path length, nearest skeleton node, near-skeleton test, nearest-terminal
// greedy order) — the Stage 4.1 orchestration stays in Python.
pub mod channel_mapping;

#[cfg(feature = "python")]
#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    crate::congestion::register(m)?;
    crate::congestion_analysis::register(m)?;
    crate::escape_via::register(m)?;
    crate::routing_demand::register(m)?;
    crate::placement_suggestions::register(m)?;
    crate::apply_suggestions::register(m)?;
    crate::congestion_heatmap::register(m)?;
    crate::fixed_copper::register(m)?;
    crate::zone_pour::register(m)?;
    crate::channel_skeleton::register(m)?;
    crate::hierarchical_clustering::register(m)?;
    crate::geometry_kernels::register(m)?;
    crate::channel_mapping::register(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    m.add_class::<crate::persistent_radius_index::RadiusIndex>()?;
    Ok(())
}
