// When `--no-default-features` deactivates `python`, the pyo3-bridge code
// (each module's `register`, `*_py` functions) is not compiled.  Functions
// reachable ONLY through those bridges then appear dead — they are not, but
// clippy cannot see past the cfg gate.  Allow dead_code in the no-python
// config; production extension builds always enable `python` explicitly.
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
// Shared CPython-exact OverflowError construction for the `pow_operator`
// overflow guard duplicated in escape_via.rs (and formerly in
// placement_suggestions.rs, deleted 2026-08-20).
#[cfg(feature = "python")]
mod py_errors;
#[cfg(feature = "python")]
pub mod escape_via;
#[cfg(feature = "python")]
pub mod routing_demand;
pub mod clearance_geometry;
pub mod body_collision;
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
// Config-space corridor erosion for width-aware A* routing (spike:
// docs/evidence/2026-08-11-corridor-aware-astar-spike.md). Pure module
// (unconditional) so its erosion kernel is wasm32-testable; the pyo3
// bridge function is gated below like the rest of this crate's mixed
// pure/python modules.
pub mod corridor_erosion;
#[cfg(feature = "python")]
pub use corridor_erosion::corridor_mask_for_net_py;
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
pub mod grid_leaf;
#[cfg(feature = "python")]
pub use grid_leaf::{
    block_exclusion_zone_into_grid_py, count_blocked_cells_py, grid_cell_available_py,
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
pub mod via_placement;
pub mod bottleneck_geometry;
#[cfg(feature = "python")]
pub use bottleneck_geometry::{
    build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py, min_cut_py,
};
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
// Wave 4, core graph/geometry cluster: kernels for seven of the nine
// core/{graph, hypergraph, pin_geometry, power_topology, topology,
// courtyard, geometry_types}.py modules (community.py and loop_ownership.py
// are JUSTIFIED-KEEP — see core_graph_geometry.rs's module doc and
// VERIFICATION.md). One registration line covers all seven modules' kernels.
pub mod core_graph_geometry;
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
// Zone-pour OUTLINE generation with per-pair clearance/creepage carving
// (2026-08-15 design, docs/evidence/2026-08-15-rust-zone-pour-design.md):
// keepout-union + polygon-boolean carve on `geo::BooleanOps` (same
// dependency as convex_hull.rs), hole-preserving output.  Pure-Rust core
// (wasm32-safe) with a thin pyo3 surface under the `python` feature.
pub mod zone_generator;
#[cfg(feature = "python")]
pub use zone_generator::{emit_zone_outline_s_expr_py, pour_outline_py};
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
// Wave 4: router_v6 spatial-DRC cluster (resource_bound, power_plane,
// diff_pair_inference, trace_width_assignment, dense_package_detection).
// Declared after channel_mapping (this file's tail) so appends cannot
// rewrite a parallel agent's lines.
pub mod resource_bound;
pub mod power_plane;
pub mod diff_pair_inference;
pub mod trace_width_assignment;
pub mod dense_package_detection;
// Wave 4, tier-2 router_v6 cluster (via_placement, clearance_engine,
// grid_converter, path_simplify) -- see via_clearance.rs's module doc.
pub mod via_clearance;
// Wave 4, spatial-tier-2 unit (router_v6 spatial/router kernels): the
// bottleneck_analysis / layer_capacity / connectivity / obstacle_map
// compute kernels.  Append-only tail — do not move or merge these lines;
// parallel agents append to this file.
pub mod bottleneck_kernels;
pub mod layer_capacity_kernels;
pub mod connectivity_kernels;
// NetRouteResult (2026-08-16): the verified per-net routing verdict --
// `Connected` is constructible only through `verify_continuity`, which runs
// union-find over the ACTUAL emitted copper (see the module doc for the
// fake-completion bug class this closes). Declared after
// `connectivity_kernels` (whose `connectivity_partition` it reuses) so
// appends cannot rewrite a parallel agent's lines.
pub mod net_route_result;
pub mod obstacle_map_kernels;
// Wave 4, spatial-tier-2 unit: router_v6/bundle_analyzer.py's GEOS seam
// (MultiPoint.convex_hull + hull.buffer + STRtree contains) -- GEOS
// ConvexHull and OffsetSegmentGenerator transcriptions, region bit-exact
// against shapely 2.1.2 / GEOS 3.13.1.  See bundle_analyzer.rs's module doc.
pub mod bundle_analyzer;
// Wave 4, Phase 4 tail: topological placement kernels, consolidated from the
// deleted temper-placement-topology crate (graph clustering, constraint
// propagation, force refinement, initial placement, zone backtracking, and
// the heuristics/ slice). Pure kernels are unconditional; placement_topology
// is the wholly-pyo3 surface (see its module doc).
pub mod force;
pub mod graph;
pub mod heuristics;
pub mod numeric;
pub mod placement;
pub mod propagation;
pub mod zone;
#[cfg(feature = "python")]
pub mod placement_topology;
// Wave 4, kicad_transform migration: the sanctioned KiCad footprint-child
// rotation convention (R(-theta)) — the pure kernels behind
// temper_placer.geometry.kicad_transform (now a shim). Declared after
// placement_topology (this file's tail) so appends cannot rewrite a
// parallel agent's lines.
pub mod kicad_transform;
// Property campaign (R7 / WASM-tier volume): metamorphic/invariant
// properties over three pure, deterministic kernels -- kicad_transform's
// rotation convention, convex_hull's hull area, and connected_components'
// 8-connected labeling. See that module's doc comment. Declared after
// kicad_transform (which it depends on) and before units (this file's
// tail) so appends cannot rewrite a parallel agent's lines.
pub mod property_campaigns;
// Second property campaign (R7 / WASM-tier volume): metamorphic/invariant
// properties over four pure, deterministic kernels the first campaign does
// not cover -- sdf.rs, polygon.rs, overlap.rs, and projections.rs. A
// separate module from `property_campaigns` rather than an addition to it
// (see that module's own doc comment for why: appending to a file another
// concurrent agent may be mid-edit on risks a merge collision). Declared
// after `property_campaigns` and before `units` (this file's tail) so
// appends cannot rewrite a parallel agent's lines.
pub mod property_campaigns_2;
// Third property campaign (R7 / WASM-tier volume): metamorphic/invariant
// properties over four pure, deterministic kernels neither earlier campaign
// covers -- edt.rs's exact Euclidean distance transform, pad_geometry.rs's
// shared pad-radius model, copper_reach.rs's per-component copper extent,
// and obstacle_map_kernels.rs's GEOS-exact circle-buffer ring. A separate
// module from both `property_campaigns` and `property_campaigns_2` for the
// same merge-collision reason the second module's own doc comment gives.
// Declared after `property_campaigns_2` and before `units` (this file's
// tail) so appends cannot rewrite a parallel agent's lines.
pub mod property_campaigns_3;
// Wave 4 Phase A: core/units.py's `Mm`, `Mil`, `Inch` newtype wrappers and
// the mm/mil/inch conversion kernels. See units.rs's module doc for why the
// existing units.py kernels are NOT re-migrated here (they live in
// temper-io-types) and the recorded Mm/Mil/Inch pyclass decision.
pub mod units;
// Typed wrapper for the `initial_rotation_quadrant` quarter-turn index
// (renamed 2026-08-13 from `initial_rotation`) -- see its module doc for
// the incident this exists to prevent a recurrence of. Pure Rust, no pyo3
// dependency, so it is unconditional like `units` above.
pub mod rotation_quadrant;
// Layer identity type (2026-08-14): `Layer`/`Stackup`, constructible only
// from parsing the board's own declared `(layers ...)` / `(setup (stackup
// ...))` blocks (or the named `Stackup::test_only` escape hatch), so a
// hardcoded stale copy of a layer's role/copper-weight/position cannot be
// written. Replaces the bare-string layer-name pattern behind the PR #1178
// ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED freeze. Declared after `units`
// (this file's prior tail) so appends cannot rewrite a parallel agent's
// lines.
pub mod layer_identity;
// ClearanceHalo (2026-08-16): conservative-superset obstacle-halo type
// whose constructors guarantee the halo contains the true Minkowski sum
// (obstacle + clearance) — circumscribed polygon for circular pads,
// half-diagonal disc for rect pads — with property tests guarding the
// three geometry bugs found during zone-generator verification (inscribed
// undercut, rect corner reach, 500+ overlap panic). Pure Rust, no pyo3
// surface (adoption by zone_generator.rs is a Rust-side follow-up), so it
// is unconditional like `units` above. Declared after `layer_identity`
// (this file's prior tail) so appends cannot rewrite a parallel agent's
// lines.
pub mod clearance_halo;
// WorldPosition (2026-08-16): a pad's board-frame position, constructible
// ONLY by the rotation kernel (`pin_world_position_kernel`) — private
// fields, no From<(f64,f64)>, no struct literal. Exists because the
// "naive comp_pos + pin_pos without rotation" bug hit three times this
// session (zone-stitch swap shorts, zone hulls at wrong coordinates, the
// run_collect_pad_positions rotation omission); each fix was "call the
// kernel", and nothing prevented the next caller from reintroducing the
// naive sum. Pure Rust, no pyo3 dependency in the type itself (the pyo3
// binding is `#[cfg(feature = "python")]` beside it), so it is
// unconditional like `units`/`clearance_halo` above. Declared after
// `clearance_halo` (this file's prior tail) so appends cannot rewrite a
// parallel agent's lines.
pub mod world_position;
pub use world_position::WorldPosition;
// wasm32 has no OS RNG; getrandom will not compile there without a source.
// See this module's doc comment for why the source fails instead of quietly
// substituting a deterministic PRNG.
#[cfg(target_arch = "wasm32")]
mod wasm_entropy;
// NOT gated on `python`. The wasm32 tier builds with --no-default-features,
// so an added `python` gate here would silently exclude the registry and the
// runner would fail to compile against it. Stacked `cfg` attributes are ANDed.
// `wasm-registry` is implied by every per-family feature and by
// `wasm-test-registry`, so any wasm build compiles this module.
// Generated by `scripts/gen_wasm_test_registry.py --crate temper-geometry`.
#[cfg(feature = "wasm-registry")]
pub mod wasm_test_registry;

#[cfg(feature = "python")]
#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    crate::congestion::register(m)?;
    crate::escape_via::register(m)?;
    crate::routing_demand::register(m)?;
    crate::fixed_copper::register(m)?;
    crate::zone_pour::register(m)?;
    crate::zone_generator::register(m)?;
    crate::channel_skeleton::register(m)?;
    crate::hierarchical_clustering::register(m)?;
    crate::channel_mapping::register(m)?;
    crate::resource_bound::register(m)?;
    crate::power_plane::register(m)?;
    crate::diff_pair_inference::register(m)?;
    crate::trace_width_assignment::register(m)?;
    crate::dense_package_detection::register(m)?;
    crate::core_graph_geometry::register(m)?;
    crate::via_clearance::register(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    m.add_class::<crate::persistent_radius_index::RadiusIndex>()?;
    crate::bottleneck_kernels::register(m)?;
    crate::layer_capacity_kernels::register(m)?;
    crate::connectivity_kernels::register(m)?;
    crate::net_route_result::register(m)?;
    crate::obstacle_map_kernels::register(m)?;
    crate::bundle_analyzer::register(m)?;
    crate::placement_topology::register(m)?;
    crate::kicad_transform::register(m)?;
    crate::units::register(m)?;
    crate::layer_identity::register(m)?;
    Ok(())
}
