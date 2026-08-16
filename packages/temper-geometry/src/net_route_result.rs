//! `NetRouteResult` — the verified per-net routing verdict.
//!
//! # The bug class this closes
//!
//! The router's A* engine reports "routed successfully" when it finds a
//! *path through the occupancy grid*. Emitting that path as copper is a
//! separate step with separate failure modes: segments can land on the
//! wrong layer, stop short of a pad boundary, or fail to meet a via; a via
//! can be emitted at the wrong coordinates or not at all; a zone can be
//! declared as an outline with no fill (and this codebase's zone writer
//! never runs KiCad's fill pass, so a zone outline is never copper).
//! Measured on the definitive route of `pcb/temper.kicad_pcb`
//! (2026-08-15): 14 of 139 nets were reported "routed" while the emitted
//! copper joined only a subset of their pads — the "fake completion"
//! shape. The post-hoc audit (`router_v6/pad_connectivity_audit.py`)
//! caught the discrepancy, but the router's own completion claim never
//! went through a check of the *emitted* copper.
//!
//! This module makes that impossible at the type level: the only way to
//! obtain [`NetRouteResult::Connected`] is [`NetRouteResult::verify_continuity`],
//! which runs a union-find over the actual pads / segments / vias and
//! returns `Connected` only when every pad lands in one component.
//! [`VerifiedRoute`]'s fields are private and there is no public
//! constructor, so a caller cannot fabricate a `Connected` verdict by hand
//! — see the `compile_fail` doctest on [`NetRouteResult`].
//!
//! # Zone semantics (deliberate)
//!
//! A zone's `(polygon (pts ...))` block is the pour's drawn *outline* — it
//! is not copper. Only KiCad's own fill pass (or a reimplementation that
//! honours clearance cutouts, thermal-relief spokes and unfilled islands)
//! produces real zone copper, and nothing in this codebase runs that pass
//! (measured: zero `filled_polygon` blocks in this project's written
//! boards — see `pad_connectivity_audit._parse_zones`). Therefore:
//!
//! * zone outlines NEVER union in the connectivity graph (no zone pair is
//!   fed to the union-find), and
//! * a net whose segment/via graph does not join all pads but that has a
//!   zone outline declared on every unreached pad's layer is
//!   [`NetRouteResult::ZoneDependent`] — never `Connected`. The copper
//!   that would connect it has not been produced.
//!
//! This matches the audit's ground truth: `zone_dependent_unmeasured` is a
//! "cannot measure" verdict, not a pass.

use crate::connectivity_kernels::{connectivity_partition, PadData, TrackData, ViaData};

/// Why a net is not [`NetRouteResult::Connected`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureReason {
    /// A* found no path, or the net was skipped entirely.
    NoPathFound,
    /// No copper (segments/vias) was emitted for the net at all.
    NoCopperEmitted,
    /// The net has no pads — there is nothing to verify a connection to.
    NoPads,
}

impl FailureReason {
    /// Stable machine-readable token for diagnostics.
    pub fn as_str(self) -> &'static str {
        match self {
            FailureReason::NoPathFound => "no_path_found",
            FailureReason::NoCopperEmitted => "no_copper_emitted",
            FailureReason::NoPads => "no_pads",
        }
    }
}

/// A continuous copper connection that has been *proven* to exist in the
/// emitted geometry by [`NetRouteResult::verify_continuity`].
///
/// **Every field is private and there is no public constructor.** The only
/// way to obtain a `VerifiedRoute` is as the payload of a
/// [`NetRouteResult::Connected`] returned by [`NetRouteResult::verify_continuity`].
/// A hand-written `VerifiedRoute { .. }` anywhere outside this module does
/// not compile (private fields) — so `Connected` is unrepresentable without
/// a real union-find pass over real copper.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifiedRoute {
    /// Indices into the `pads` slice passed to `verify_continuity` — every
    /// pad of the net (all of them are in the one verified component).
    pad_ids: Vec<usize>,
    /// Indices into the `tracks` slice whose copper actually participates
    /// in the verified component (isolated segments are excluded).
    segment_ids: Vec<usize>,
    /// Indices into the `vias` slice whose copper actually participates in
    /// the verified component (isolated vias are excluded).
    via_ids: Vec<usize>,
}

impl VerifiedRoute {
    /// All of the net's pad indices (each index is into the `pads` slice
    /// the verification ran over).
    pub fn pad_ids(&self) -> &[usize] {
        &self.pad_ids
    }

    /// Indices of the segments that participate in the verified connection.
    pub fn segment_ids(&self) -> &[usize] {
        &self.segment_ids
    }

    /// Indices of the vias that participate in the verified connection.
    pub fn via_ids(&self) -> &[usize] {
        &self.via_ids
    }
}

/// The verified result of routing a single net.
///
/// **`Connected` can ONLY be constructed by [`NetRouteResult::verify_continuity`].**
/// The A* engine cannot claim "connected" — it can only produce segments,
/// which are then checked against the real copper geometry:
///
/// ```compile_fail
/// use temper_geometry::net_route_result::{NetRouteResult, VerifiedRoute};
/// // `VerifiedRoute`'s fields are private to `net_route_result`, so a
/// // caller cannot fabricate a Connected verdict by hand -- this does not
/// // compile. `Connected` is only reachable through
/// // `NetRouteResult::verify_continuity(...)`.
/// let fake = NetRouteResult::Connected(VerifiedRoute {
///     pad_ids: vec![0, 1],
///     segment_ids: vec![],
///     via_ids: vec![],
/// });
/// ```
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NetRouteResult {
    /// All pads are connected by a verified continuous path of segments +
    /// vias. Only `verify_continuity` can produce this.
    Connected(VerifiedRoute),
    /// Zone outline(s) exist for the net but no fill was produced — the
    /// copper that would connect the remaining pads does not exist yet.
    /// NEVER reported as connected.
    ZoneDependent {
        /// Number of zone blocks declared for this net (outline or fill —
        /// in this codebase's writer, always outline).
        outline_count: usize,
        /// How many of the net's unreached pads sit on a layer that has a
        /// zone outline declared for this net.
        pads_in_outlines: usize,
    },
    /// Some copper exists but the net's pads are NOT all connected. This is
    /// an honest "we tried but didn't finish" — never reported as success.
    Partial {
        segment_count: usize,
        via_count: usize,
        /// Every pad group of size >= 2 that the union-find actually joined
        /// (which pads are connected to which).
        connected_pad_groups: Vec<Vec<usize>>,
        /// The pads that are NOT in the majority (largest) component.
        unconnected_pads: Vec<usize>,
    },
    /// No verified connection exists and no partial copper was emitted.
    Failed {
        reason: FailureReason,
    },
}

impl NetRouteResult {
    /// Verify, via union-find on the ACTUAL emitted copper geometry, whether
    /// every pad of the net is reachable from every other pad.
    ///
    /// This is the ONLY constructor of [`NetRouteResult::Connected`]. It
    /// costs ~`pads + segments + vias` union operations — trivial compared
    /// to the A* search that produced the geometry.
    ///
    /// * `pads` / `tracks` / `vias` — the emitted copper, denormalized the
    ///   same way [`connectivity_partition`] expects.
    /// * `zone_layers` — every layer on which the net has ANY zone block
    ///   declared. Zones are outlines, never copper: they only feed the
    ///   [`NetRouteResult::ZoneDependent`] classification.
    /// * `zone_outline_count` — number of zone blocks declared for the net
    ///   (diagnostic; see [`NetRouteResult::ZoneDependent::outline_count`]).
    pub fn verify_continuity(
        pads: &[PadData],
        tracks: &[TrackData],
        vias: &[ViaData],
        zone_layers: &[i64],
        zone_outline_count: usize,
    ) -> NetRouteResult {
        let pad_count = pads.len();

        // Nothing to join: a pad-less net has no connection that could be
        // verified, and claiming "connected" for one would be vacuous.
        if pad_count == 0 {
            return NetRouteResult::Failed {
                reason: FailureReason::NoPads,
            };
        }

        // A single pad is trivially connected to itself — no copper is
        // required for a continuous path, because there is nothing to join.
        // Mirrors the audit's ground truth (`pad_connectivity_audit` counts
        // 0/1-pad nets fully connected).
        if pad_count == 1 {
            return NetRouteResult::Connected(VerifiedRoute {
                pad_ids: vec![0],
                segment_ids: (0..tracks.len()).collect(),
                via_ids: (0..vias.len()).collect(),
            });
        }

        // Zones are OUTLINES, not copper: the union-find runs over pads,
        // tracks and vias only (`zone_pairs` deliberately empty).
        let total_items = pad_count + tracks.len() + vias.len();
        let partition = connectivity_partition(pads, tracks, vias, &[], total_items);

        // Majority component = the largest pad group with >1 pad; ties break
        // toward the group containing the lowest pad index (matches the
        // audit's `max(counts, key=counts.get)` first-max-in-pad-order
        // semantics).
        let mut majority: Option<(usize, &Vec<usize>)> = None; // (root, pads)
        for (root, group) in &partition.pad_components {
            if group.len() > 1 {
                let better = match majority {
                    None => true,
                    Some((_, cur)) => {
                        group.len() > cur.len()
                            || (group.len() == cur.len() && group[0] < cur[0])
                    }
                };
                if better {
                    majority = Some((*root, group));
                }
            }
        }

        let Some((root, majority_group)) = majority else {
            // No component joins more than one pad: every pad is an isolated
            // singleton, so every pad is unreached.
            let unreached: Vec<usize> = (0..pad_count).collect();
            return classify_not_connected(
                pads,
                tracks,
                vias,
                zone_layers,
                zone_outline_count,
                &unreached,
                vec![],
            );
        };

        if majority_group.len() == pad_count {
            // Every pad is in ONE component: the segment/via graph
            // verifiably connects all of them.
            let segment_ids: Vec<usize> = partition
                .track_roots
                .iter()
                .enumerate()
                .filter(|(_, r)| **r == root)
                .map(|(i, _)| i)
                .collect();
            let via_ids: Vec<usize> = partition
                .via_roots
                .iter()
                .enumerate()
                .filter(|(_, r)| **r == root)
                .map(|(i, _)| i)
                .collect();
            return NetRouteResult::Connected(VerifiedRoute {
                pad_ids: (0..pad_count).collect(),
                segment_ids,
                via_ids,
            });
        }

        // Some pads are joined, others are not.
        let unreached: Vec<usize> = (0..pad_count)
            .filter(|p| !majority_group.contains(p))
            .collect();
        let connected_groups: Vec<Vec<usize>> = partition
            .pad_components
            .iter()
            .filter(|(_, g)| g.len() > 1)
            .map(|(_, g)| g.clone())
            .collect();
        classify_not_connected(
            pads,
            tracks,
            vias,
            zone_layers,
            zone_outline_count,
            &unreached,
            connected_groups,
        )
    }
}

/// Shared tail for every not-fully-connected verdict: zone-outline rescue
/// → [`NetRouteResult::ZoneDependent`]; some copper → [`NetRouteResult::Partial`];
/// otherwise → [`NetRouteResult::Failed`].
#[allow(clippy::too_many_arguments)]
fn classify_not_connected(
    pads: &[PadData],
    tracks: &[TrackData],
    vias: &[ViaData],
    zone_layers: &[i64],
    zone_outline_count: usize,
    unreached: &[usize],
    connected_groups: Vec<Vec<usize>>,
) -> NetRouteResult {
    // A pad "could be reached" by a zone outline when any of its conductive
    // layers has a zone declared for this net. A through-hole pad (layers =
    // every copper layer) qualifies when the zone is on ANY layer — the
    // audit's `_zone_could_reach` rule.
    let pads_in_outlines = unreached
        .iter()
        .filter(|p| pads[**p].layers.iter().any(|l| zone_layers.contains(l)))
        .count();
    if !unreached.is_empty() && pads_in_outlines == unreached.len() {
        return NetRouteResult::ZoneDependent {
            outline_count: zone_outline_count,
            pads_in_outlines,
        };
    }
    if tracks.is_empty() && vias.is_empty() {
        return NetRouteResult::Failed {
            reason: FailureReason::NoCopperEmitted,
        };
    }
    NetRouteResult::Partial {
        segment_count: tracks.len(),
        via_count: vias.len(),
        connected_pad_groups: connected_groups,
        unconnected_pads: unreached.to_vec(),
    }
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Python-visible verdict object. Immutable snapshot of a
/// [`NetRouteResult`]: the Python layer can only obtain one through
/// [`verify_net_route_result_py`], which is the pyo3 export of
/// [`NetRouteResult::verify_continuity`] — there is no Python-side
/// constructor, so a `disposition == "connected"` object is proof that the
/// Rust union-find ran over real geometry.
#[cfg(feature = "python")]
#[pyclass(name = "NetRouteResult", module = "temper_geometry", frozen)]
#[derive(Clone)]
pub struct PyNetRouteResult {
    #[pyo3(get)]
    disposition: &'static str,
    #[pyo3(get)]
    pad_ids: Vec<i64>,
    #[pyo3(get)]
    segment_ids: Vec<i64>,
    #[pyo3(get)]
    via_ids: Vec<i64>,
    #[pyo3(get)]
    connected_pad_groups: Vec<Vec<i64>>,
    #[pyo3(get)]
    unconnected_pads: Vec<i64>,
    #[pyo3(get)]
    outline_count: i64,
    #[pyo3(get)]
    pads_in_outlines: i64,
    #[pyo3(get)]
    segment_count: i64,
    #[pyo3(get)]
    via_count: i64,
    #[pyo3(get)]
    reason: Option<String>,
}

#[cfg(feature = "python")]
impl PyNetRouteResult {
    fn from_rust(result: NetRouteResult) -> Self {
        match result {
            NetRouteResult::Connected(route) => PyNetRouteResult {
                disposition: "connected",
                pad_ids: route.pad_ids.iter().map(|i| *i as i64).collect(),
                segment_ids: route.segment_ids.iter().map(|i| *i as i64).collect(),
                via_ids: route.via_ids.iter().map(|i| *i as i64).collect(),
                connected_pad_groups: vec![route
                    .pad_ids
                    .iter()
                    .map(|i| *i as i64)
                    .collect()],
                unconnected_pads: vec![],
                outline_count: 0,
                pads_in_outlines: 0,
                segment_count: route.segment_ids.len() as i64,
                via_count: route.via_ids.len() as i64,
                reason: None,
            },
            NetRouteResult::ZoneDependent {
                outline_count,
                pads_in_outlines,
            } => PyNetRouteResult {
                disposition: "zone_dependent",
                pad_ids: vec![],
                segment_ids: vec![],
                via_ids: vec![],
                connected_pad_groups: vec![],
                unconnected_pads: vec![],
                outline_count: outline_count as i64,
                pads_in_outlines: pads_in_outlines as i64,
                segment_count: 0,
                via_count: 0,
                reason: None,
            },
            NetRouteResult::Partial {
                segment_count,
                via_count,
                connected_pad_groups,
                unconnected_pads,
            } => PyNetRouteResult {
                disposition: "partial",
                pad_ids: vec![],
                segment_ids: vec![],
                via_ids: vec![],
                connected_pad_groups: connected_pad_groups
                    .into_iter()
                    .map(|g| g.into_iter().map(|i| i as i64).collect())
                    .collect(),
                unconnected_pads: unconnected_pads.into_iter().map(|i| i as i64).collect(),
                outline_count: 0,
                pads_in_outlines: 0,
                segment_count: segment_count as i64,
                via_count: via_count as i64,
                reason: None,
            },
            NetRouteResult::Failed { reason } => PyNetRouteResult {
                disposition: "failed",
                pad_ids: vec![],
                segment_ids: vec![],
                via_ids: vec![],
                connected_pad_groups: vec![],
                unconnected_pads: vec![],
                outline_count: 0,
                pads_in_outlines: 0,
                segment_count: 0,
                via_count: 0,
                reason: Some(reason.as_str().to_string()),
            },
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyNetRouteResult {
    fn __repr__(&self) -> String {
        let mut out = format!("NetRouteResult(disposition={:?}", self.disposition);
        if let Some(reason) = &self.reason {
            out.push_str(&format!(", reason={reason:?}"));
        }
        if !self.pad_ids.is_empty() {
            out.push_str(&format!(", pads={:?}", self.pad_ids));
        }
        if !self.connected_pad_groups.is_empty() {
            out.push_str(&format!(", groups={:?}", self.connected_pad_groups));
        }
        if !self.unconnected_pads.is_empty() {
            out.push_str(&format!(", unreached={:?}", self.unconnected_pads));
        }
        if self.outline_count > 0 {
            out.push_str(&format!(
                ", outlines={} pads_in_outlines={}",
                self.outline_count, self.pads_in_outlines
            ));
        }
        out.push(')');
        out
    }
}

/// pyo3 export of [`NetRouteResult::verify_continuity`].
///
/// Input arrays follow the same flattening convention as
/// `connectivity_components_py`: `pads` is `[x, y, rotation, w, h]` per pad
/// (5 floats), `pad_shapes` is `1` for `"circle"` else `0`, `tracks` is
/// `[x1, y1, x2, y2, width]` (5 floats), `vias` is `[x, y, diameter]`
/// (3 floats), with per-item layer lists. `zone_layers` is the net's
/// declared-zone layer set (see [`NetRouteResult::verify_continuity`]).
#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn verify_net_route_result_py(
    pads: Vec<f64>,
    pad_shapes: Vec<i64>,
    pad_layers: Vec<Vec<i64>>,
    tracks: Vec<f64>,
    track_layers: Vec<i64>,
    vias: Vec<f64>,
    via_layers: Vec<Vec<i64>>,
    zone_layers: Vec<i64>,
    zone_outline_count: i64,
) -> PyResult<PyNetRouteResult> {
    let n_pads = pads.len() / 5;
    if !pads.len().is_multiple_of(5) || pad_shapes.len() != n_pads || pad_layers.len() != n_pads {
        return Err(PyValueError::new_err("pad array length mismatch"));
    }
    let n_tracks = tracks.len() / 5;
    if !tracks.len().is_multiple_of(5) || track_layers.len() != n_tracks {
        return Err(PyValueError::new_err("track array length mismatch"));
    }
    let n_vias = vias.len() / 3;
    if !vias.len().is_multiple_of(3) || via_layers.len() != n_vias {
        return Err(PyValueError::new_err("via array length mismatch"));
    }
    if zone_outline_count < 0 {
        return Err(PyValueError::new_err("zone_outline_count must be >= 0"));
    }

    temper_py_bridge::catch_unwind(move || {
        let pads_v: Vec<PadData> = (0..n_pads)
            .map(|k| PadData {
                x: pads[5 * k],
                y: pads[5 * k + 1],
                rotation: pads[5 * k + 2],
                w: pads[5 * k + 3],
                h: pads[5 * k + 4],
                is_circle: pad_shapes[k] == 1,
                layers: pad_layers[k].clone(),
            })
            .collect();
        let tracks_v: Vec<TrackData> = (0..n_tracks)
            .map(|k| TrackData {
                x1: tracks[5 * k],
                y1: tracks[5 * k + 1],
                x2: tracks[5 * k + 2],
                y2: tracks[5 * k + 3],
                layer: track_layers[k],
                width: tracks[5 * k + 4],
            })
            .collect();
        let vias_v: Vec<ViaData> = (0..n_vias)
            .map(|k| ViaData {
                x: vias[3 * k],
                y: vias[3 * k + 1],
                diameter: vias[3 * k + 2],
                layers: via_layers[k].clone(),
            })
            .collect();
        let result = NetRouteResult::verify_continuity(
            &pads_v,
            &tracks_v,
            &vias_v,
            &zone_layers,
            zone_outline_count as usize,
        );
        PyNetRouteResult::from_rust(result)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(verify_net_route_result_py, m)?)?;
    m.add_class::<PyNetRouteResult>()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn pad(x: f64, y: f64, w: f64, h: f64, circle: bool, layers: &[i64]) -> PadData {
        PadData {
            x,
            y,
            rotation: 0.0,
            w,
            h,
            is_circle: circle,
            layers: layers.to_vec(),
        }
    }

    fn track(x1: f64, y1: f64, x2: f64, y2: f64, layer: i64, width: f64) -> TrackData {
        TrackData { x1, y1, x2, y2, layer, width }
    }

    fn via(x: f64, y: f64, d: f64, layers: &[i64]) -> ViaData {
        ViaData { x, y, diameter: d, layers: layers.to_vec() }
    }

    fn disposition(result: &NetRouteResult) -> &'static str {
        match result {
            NetRouteResult::Connected(_) => "connected",
            NetRouteResult::ZoneDependent { .. } => "zone_dependent",
            NetRouteResult::Partial { .. } => "partial",
            NetRouteResult::Failed { .. } => "failed",
        }
    }

    #[cfg_attr(test, test)]
    fn single_pad_is_trivially_connected() {
        let p = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let r = NetRouteResult::verify_continuity(&[p], &[], &[], &[], 0);
        assert_eq!(disposition(&r), "connected");
        let NetRouteResult::Connected(route) = &r else {
            panic!("expected Connected");
        };
        assert_eq!(route.pad_ids(), &[0]);
    }

    #[cfg_attr(test, test)]
    fn zero_pads_is_failed_no_pads() {
        let r = NetRouteResult::verify_continuity(&[], &[], &[], &[], 0);
        assert_eq!(
            r,
            NetRouteResult::Failed {
                reason: FailureReason::NoPads
            }
        );
    }

    #[cfg_attr(test, test)]
    fn all_pads_joined_by_tracks_is_connected() {
        // two pads joined by a single track through both pad centres
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[0]);
        let t = track(0.0, 0.0, 4.0, 0.0, 0, 0.5);
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t], &[], &[], 0);
        assert_eq!(disposition(&r), "connected");
        let NetRouteResult::Connected(route) = &r else {
            panic!("expected Connected");
        };
        assert_eq!(route.pad_ids(), &[0, 1]);
        assert_eq!(route.segment_ids(), &[0]);
    }

    #[cfg_attr(test, test)]
    fn fake_completion_shape_is_partial_with_unconnected_pads() {
        // The b39b382d shape: a segment exists for the net but touches only
        // ONE of the two pads. A naive "has copper" check would call this
        // done; verification must call it partial.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(10.0, 10.0, 1.0, 1.0, true, &[0]);
        let t = track(0.0, 0.0, 2.0, 0.0, 0, 0.5); // touches p1 only
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t], &[], &[], 0);
        assert_eq!(disposition(&r), "partial");
        let NetRouteResult::Partial {
            segment_count,
            connected_pad_groups,
            unconnected_pads,
            ..
        } = &r
        else {
            panic!("expected Partial");
        };
        assert_eq!(*segment_count, 1);
        assert!(connected_pad_groups.is_empty(), "no group joins both pads");
        // Audit-parity semantics: the majority component must join MORE
        // than one pad, and no component here does (pad 0 has copper
        // attached but joins no OTHER pad), so every pad is unreached.
        assert_eq!(unconnected_pads, &vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn three_pads_one_unreached_reports_the_specific_pad() {
        // The real fake-completion shape: copper joins p0-p1, p2 is
        // unreached. Partial must name p2 specifically.
        let p0 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p1 = pad(1.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(10.0, 10.0, 1.0, 1.0, true, &[0]);
        let t = track(0.0, 0.0, 1.0, 0.0, 0, 0.2);
        let r = NetRouteResult::verify_continuity(&[p0, p1, p2], &[t], &[], &[], 0);
        assert_eq!(disposition(&r), "partial");
        let NetRouteResult::Partial {
            connected_pad_groups,
            unconnected_pads,
            ..
        } = &r
        else {
            panic!("expected Partial");
        };
        assert_eq!(connected_pad_groups, &vec![vec![0, 1]]);
        assert_eq!(unconnected_pads, &vec![2]);
    }

    #[cfg_attr(test, test)]
    fn segment_on_wrong_layer_is_partial() {
        // Segment emitted on layer 1 while both pads are on layer 0: the
        // copper exists but never touches the pads -- the M1-bug shape.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[0]);
        let t = track(0.0, 0.0, 4.0, 0.0, 1, 0.5); // wrong layer
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t], &[], &[], 0);
        assert_eq!(disposition(&r), "partial");
        let NetRouteResult::Partial { unconnected_pads, .. } = &r else {
            panic!("expected Partial");
        };
        assert_eq!(unconnected_pads, &vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn via_connects_two_layers() {
        // pad on layer 0, pad on layer 1, joined only through a through via
        // at the track junction.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[1]);
        let t1 = track(0.0, 0.0, 2.0, 0.0, 0, 0.5);
        let t2 = track(2.0, 0.0, 4.0, 0.0, 1, 0.5);
        let v = via(2.0, 0.0, 0.6, &[0, 1]);
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t1, t2], &[v], &[], 0);
        assert_eq!(disposition(&r), "connected");
        let NetRouteResult::Connected(route) = &r else {
            panic!("expected Connected");
        };
        assert_eq!(route.via_ids(), &[0]);
    }

    #[cfg_attr(test, test)]
    fn via_emitted_at_wrong_coordinates_is_partial() {
        // Same layout but the via is 3 mm away from the junction -- the
        // "via failed / wrong coordinates" fake-completion shape.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[1]);
        let t1 = track(0.0, 0.0, 2.0, 0.0, 0, 0.5);
        let t2 = track(2.0, 0.0, 4.0, 0.0, 1, 0.5);
        let v = via(5.0, 3.0, 0.6, &[0, 1]); // nowhere near the tracks
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t1, t2], &[v], &[], 0);
        assert_eq!(disposition(&r), "partial");
    }

    #[cfg_attr(test, test)]
    fn zone_outline_alone_is_zone_dependent_never_connected() {
        // Two pads with NO segment/via copper between them, but a zone
        // outline declared on their shared layer. The audit's
        // zone_dependent_unmeasured shape: unmeasurable, not connected.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[0]);
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[], &[], &[0], 1);
        assert_eq!(disposition(&r), "zone_dependent");
        let NetRouteResult::ZoneDependent {
            outline_count,
            pads_in_outlines,
        } = &r
        else {
            panic!("expected ZoneDependent");
        };
        assert_eq!(*outline_count, 1);
        assert_eq!(*pads_in_outlines, 2);
    }

    #[cfg_attr(test, test)]
    fn zone_outline_on_wrong_layer_does_not_rescue() {
        // Zone declared on layer 1; both pads on layer 0. No rescue
        // possible, no copper emitted -> Failed.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[0]);
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[], &[], &[1], 1);
        assert_eq!(
            r,
            NetRouteResult::Failed {
                reason: FailureReason::NoCopperEmitted
            }
        );
    }

    #[cfg_attr(test, test)]
    fn partial_copper_with_zone_rescue_is_zone_dependent() {
        // One pad joined by a track; the other unreached but covered by a
        // zone outline. ZoneDependent -- not Partial, because a fill (not
        // yet produced) could deliver the missing connection, and not
        // Connected, because no copper does today.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(10.0, 0.0, 1.0, 1.0, true, &[0]);
        let t = track(0.0, 0.0, 1.0, 0.0, 0, 0.5); // touches p1 only
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t], &[], &[0], 1);
        assert_eq!(disposition(&r), "zone_dependent");
    }

    #[cfg_attr(test, test)]
    fn multiple_groups_report_which_pads_join_which() {
        // 4 pads: p0-p1 joined by a track, p2-p3 joined by another track,
        // no connection between the two groups.
        let p0 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p1 = pad(1.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(10.0, 0.0, 1.0, 1.0, true, &[0]);
        let p3 = pad(11.0, 0.0, 1.0, 1.0, true, &[0]);
        let t1 = track(0.0, 0.0, 1.0, 0.0, 0, 0.2);
        let t2 = track(10.0, 0.0, 11.0, 0.0, 0, 0.2);
        let r = NetRouteResult::verify_continuity(&[p0, p1, p2, p3], &[t1, t2], &[], &[], 0);
        assert_eq!(disposition(&r), "partial");
        let NetRouteResult::Partial {
            connected_pad_groups,
            unconnected_pads,
            ..
        } = &r
        else {
            panic!("expected Partial");
        };
        assert_eq!(connected_pad_groups, &vec![vec![0, 1], vec![2, 3]]);
        assert_eq!(unconnected_pads, &vec![2, 3]);
    }

    #[cfg_attr(test, test)]
    fn isolated_segments_are_excluded_from_verified_route() {
        // Two pads joined by t1; an extra segment t2 exists but touches
        // nothing. The verified route must name only the participating
        // copper.
        let p1 = pad(0.0, 0.0, 1.0, 1.0, true, &[0]);
        let p2 = pad(4.0, 0.0, 1.0, 1.0, true, &[0]);
        let t1 = track(0.0, 0.0, 4.0, 0.0, 0, 0.5);
        let t2 = track(20.0, 20.0, 21.0, 20.0, 0, 0.5); // isolated
        let r = NetRouteResult::verify_continuity(&[p1, p2], &[t1, t2], &[], &[], 0);
        assert_eq!(disposition(&r), "connected");
        let NetRouteResult::Connected(route) = &r else {
            panic!("expected Connected");
        };
        assert_eq!(route.segment_ids(), &[0]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("net_route_result::tests::single_pad_is_trivially_connected", single_pad_is_trivially_connected),
        ("net_route_result::tests::zero_pads_is_failed_no_pads", zero_pads_is_failed_no_pads),
        ("net_route_result::tests::all_pads_joined_by_tracks_is_connected", all_pads_joined_by_tracks_is_connected),
        ("net_route_result::tests::fake_completion_shape_is_partial_with_unconnected_pads", fake_completion_shape_is_partial_with_unconnected_pads),
        ("net_route_result::tests::three_pads_one_unreached_reports_the_specific_pad", three_pads_one_unreached_reports_the_specific_pad),
        ("net_route_result::tests::segment_on_wrong_layer_is_partial", segment_on_wrong_layer_is_partial),
        ("net_route_result::tests::via_connects_two_layers", via_connects_two_layers),
        ("net_route_result::tests::via_emitted_at_wrong_coordinates_is_partial", via_emitted_at_wrong_coordinates_is_partial),
        ("net_route_result::tests::zone_outline_alone_is_zone_dependent_never_connected", zone_outline_alone_is_zone_dependent_never_connected),
        ("net_route_result::tests::zone_outline_on_wrong_layer_does_not_rescue", zone_outline_on_wrong_layer_does_not_rescue),
        ("net_route_result::tests::partial_copper_with_zone_rescue_is_zone_dependent", partial_copper_with_zone_rescue_is_zone_dependent),
        ("net_route_result::tests::multiple_groups_report_which_pads_join_which", multiple_groups_report_which_pads_join_which),
        ("net_route_result::tests::isolated_segments_are_excluded_from_verified_route", isolated_segments_are_excluded_from_verified_route),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
