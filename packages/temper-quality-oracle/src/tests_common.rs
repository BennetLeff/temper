/// Shared test helpers for the temper-quality-oracle crate.
///
/// Provides common constructors used across multiple test modules to avoid
/// byte-identical duplication of `empty_spec()`, `empty_placement()`,
/// `dummy_metrics()`, and `valid_metrics()`.

use std::collections::HashMap;

use crate::types::{
    PcbSpecification, PlacementState, PrecomputedMetrics, QualityMetrics,
};

pub fn empty_spec() -> PcbSpecification {
    PcbSpecification {
        name: "test".into(),
        max_loop_area_mm2: HashMap::new(),
        power_dissipation: HashMap::new(),
        max_length_mm: HashMap::new(),
        max_junction_temp_c: 125.0,
        ambient_temp_c: 40.0,
    }
}

pub fn empty_placement() -> PlacementState {
    PlacementState {
        positions: vec![],
        component_refs: vec![],
        board_width_mm: 100.0,
        board_height_mm: 100.0,
    }
}

pub fn valid_metrics() -> PrecomputedMetrics {
    PrecomputedMetrics {
        thermal_score: 0.5,
        zone_compliance_score: 0.5,
        hv_lv_clearance_score: 0.5,
        loop_area_score: 0.5,
        congestion_score: 0.5,
        compactness_score: 0.5,
        connectivity_clustering_score: 0.5,
        total_wirelength_mm: 100.0,
    }
}

pub fn dummy_metrics() -> QualityMetrics {
    QualityMetrics::from_precomputed(&valid_metrics()).unwrap()
}
