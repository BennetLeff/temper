//! Canonical router decline-reason vocabulary.
//!
//! Search remains fail-closed in Python, where the route objects and local
//! evidence live.  This Rust kernel owns the stable external reason strings
//! so they cannot drift across the several orchestration call paths.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ForcedSegmentContext {
    TerminalTreeEdge,
    TreeWaypointChain,
    PointToPoint,
    NlayerTierExhausted,
    NlayerIterationCap,
    NlayerFrontierExhausted,
}

impl ForcedSegmentContext {
    fn parse(value: &str) -> Option<Self> {
        match value {
            "terminal_tree_edge" => Some(Self::TerminalTreeEdge),
            "tree_waypoint_chain" => Some(Self::TreeWaypointChain),
            "point_to_point" => Some(Self::PointToPoint),
            "nlayer_tier_exhausted" => Some(Self::NlayerTierExhausted),
            "nlayer_iteration_cap" => Some(Self::NlayerIterationCap),
            "nlayer_frontier_exhausted" => Some(Self::NlayerFrontierExhausted),
            _ => None,
        }
    }

    fn reason(self, has_partial_geometry: bool) -> &'static str {
        match (self, has_partial_geometry) {
            (Self::TerminalTreeEdge, _) => "forced_segment_terminal_tree_edge",
            (Self::TreeWaypointChain, true) => "forced_segment_tree_waypoint_partial",
            (Self::TreeWaypointChain, false) => "forced_segment_tree_waypoint_empty",
            (Self::PointToPoint, _) => "forced_segment_point_to_point",
            (Self::NlayerTierExhausted, true) => "forced_segment_all_tiers_failed_partial",
            (Self::NlayerTierExhausted, false) => "forced_segment_all_tiers_failed_empty",
            (Self::NlayerIterationCap, true) => "forced_segment_iteration_cap_partial",
            (Self::NlayerIterationCap, false) => "forced_segment_iteration_cap_empty",
            (Self::NlayerFrontierExhausted, true) => "forced_segment_frontier_exhausted_partial",
            (Self::NlayerFrontierExhausted, false) => "forced_segment_frontier_exhausted_empty",
        }
    }
}

#[pyfunction]
fn forced_segment_decline_reason_py(
    context: &str,
    has_partial_geometry: bool,
) -> PyResult<&'static str> {
    let context = ForcedSegmentContext::parse(context).ok_or_else(|| {
        PyValueError::new_err(format!("unknown forced-segment decline context: {context}"))
    })?;
    Ok(context.reason(has_partial_geometry))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(forced_segment_decline_reason_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contexts_have_stable_distinct_reasons() {
        assert_eq!(
            ForcedSegmentContext::TerminalTreeEdge.reason(false),
            "forced_segment_terminal_tree_edge"
        );
        assert_eq!(
            ForcedSegmentContext::PointToPoint.reason(true),
            "forced_segment_point_to_point"
        );
        assert_ne!(
            ForcedSegmentContext::TreeWaypointChain.reason(true),
            ForcedSegmentContext::TreeWaypointChain.reason(false)
        );
        assert_ne!(
            ForcedSegmentContext::NlayerTierExhausted.reason(true),
            ForcedSegmentContext::NlayerTierExhausted.reason(false)
        );
    }

    #[test]
    fn unknown_context_is_not_silently_coerced() {
        assert_eq!(ForcedSegmentContext::parse("congestion"), None);
    }
}
