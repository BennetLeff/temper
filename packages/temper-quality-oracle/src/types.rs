/// Core types for the temper-quality-oracle pipeline.
///
/// Defines the type system that every pipeline stage consumes and produces:
/// NetClass, NormalizedScore, QualityVerdict, Violation, QualityMetrics.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeSet, HashMap};

/// Closed enum for net classification — 7 canonical variants.
///
/// Precedence order (first-match wins during classification):
/// Ground > Power > HighVoltage > Differential > HighCurrent > GateDrive > Signal
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NetClass {
    Ground,
    Power,
    HighVoltage,
    Differential,
    HighCurrent,
    GateDrive,
    Signal,
}

impl NetClass {
    pub fn as_str(&self) -> &'static str {
        match self {
            NetClass::Ground => "ground",
            NetClass::Power => "power",
            NetClass::HighVoltage => "high_voltage",
            NetClass::Differential => "differential",
            NetClass::HighCurrent => "high_current",
            NetClass::GateDrive => "gate_drive",
            NetClass::Signal => "signal",
        }
    }
}

/// Net name paired with its classification.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NetClassification {
    pub net_name: String,
    pub class: NetClass,
}

/// Bounded score in [0.0, 1.0] enforced at construction.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
pub struct NormalizedScore(f64);

impl NormalizedScore {
    pub fn new(value: f64) -> Result<Self, ScoreError> {
        if value.is_nan() {
            return Err(ScoreError::NaN);
        }
        if value < 0.0 || value > 1.0 {
            return Err(ScoreError::OutOfRange { value });
        }
        Ok(NormalizedScore(value))
    }

    pub fn value(&self) -> f64 {
        self.0
    }
}

#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum ScoreError {
    #[error("score {value} is out of range [0.0, 1.0]")]
    OutOfRange { value: f64 },
    #[error("score is NaN")]
    NaN,
}

/// Pre-computed metric scores from Python/JAX.
///
/// These are validated into NormalizedScore at the Rust boundary.
#[derive(Debug, Clone, PartialEq)]
pub struct PrecomputedMetrics {
    pub thermal_score: f64,
    pub zone_compliance_score: f64,
    pub hv_lv_clearance_score: f64,
    pub loop_area_score: f64,
    pub congestion_score: f64,
    pub compactness_score: f64,
    pub connectivity_clustering_score: f64,
    pub total_wirelength_mm: f64,
}

/// Validated metric scores as NormalizedScore values.
#[derive(Debug, Clone, PartialEq)]
pub struct QualityMetrics {
    pub thermal_score: NormalizedScore,
    pub zone_compliance_score: NormalizedScore,
    pub hv_lv_clearance_score: NormalizedScore,
    pub loop_area_score: NormalizedScore,
    pub congestion_score: NormalizedScore,
    pub compactness_score: NormalizedScore,
    pub connectivity_clustering_score: NormalizedScore,
    pub overall_score: NormalizedScore,
    pub total_wirelength_mm: f64,
}

impl QualityMetrics {
    pub fn from_precomputed(pre: &PrecomputedMetrics) -> Result<Self, ScoreError> {
        let scores = [
            NormalizedScore::new(pre.thermal_score)?,
            NormalizedScore::new(pre.zone_compliance_score)?,
            NormalizedScore::new(pre.hv_lv_clearance_score)?,
            NormalizedScore::new(pre.loop_area_score)?,
            NormalizedScore::new(pre.congestion_score)?,
            NormalizedScore::new(pre.compactness_score)?,
            NormalizedScore::new(pre.connectivity_clustering_score)?,
        ];
        let overall = scores.iter().map(|s| s.value()).sum::<f64>() / scores.len() as f64;
        Ok(QualityMetrics {
            thermal_score: scores[0],
            zone_compliance_score: scores[1],
            hv_lv_clearance_score: scores[2],
            loop_area_score: scores[3],
            congestion_score: scores[4],
            compactness_score: scores[5],
            connectivity_clustering_score: scores[6],
            overall_score: NormalizedScore::new(overall)?,
            total_wirelength_mm: pre.total_wirelength_mm,
        })
    }

    pub fn zeroed() -> Self {
        let z = NormalizedScore::new(0.0).expect("0.0 is a valid NormalizedScore");
        QualityMetrics {
            thermal_score: z,
            zone_compliance_score: z,
            hv_lv_clearance_score: z,
            loop_area_score: z,
            congestion_score: z,
            compactness_score: z,
            connectivity_clustering_score: z,
            overall_score: z,
            total_wirelength_mm: 0.0,
        }
    }
}

/// The type of a quality violation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ViolationType {
    CreepageInsufficient,
    LoopAreaExceeded,
    ThermalClearanceViolated,
    ZoneComplianceFailed,
    InvalidMetric,
}

/// A single quality violation with measured and required values.
#[derive(Debug, Clone, PartialEq)]
pub struct Violation {
    pub violation_type: ViolationType,
    pub description: String,
    pub components: Vec<String>,
    pub actual_value: f64,
    pub required_value: f64,
}

/// The final verdict from the quality oracle.
#[derive(Debug, Clone, PartialEq)]
pub enum QualityVerdict {
    Pass { metrics: QualityMetrics },
    Fail { metrics: QualityMetrics, violations: Vec<Violation> },
}

impl QualityVerdict {
    pub fn is_pass(&self) -> bool {
        matches!(self, QualityVerdict::Pass { .. })
    }

    pub fn metrics(&self) -> &QualityMetrics {
        match self {
            QualityVerdict::Pass { metrics } => metrics,
            QualityVerdict::Fail { metrics, .. } => metrics,
        }
    }
}

/// Derived constraints from PcbSpecification.
#[derive(Debug, Clone, PartialEq)]
pub struct DerivedConstraints {
    /// loop_name → max component spacing (mm)
    pub loop_spacing: HashMap<String, f64>,
    /// component_ref → min clearance (mm)
    pub thermal_clearances: HashMap<String, f64>,
    /// net_name → max placement distance (mm)
    pub si_max_placement_dist: HashMap<String, f64>,
    /// HV-LV isolation distance (mm)
    pub hv_lv_isolation_mm: f64,
}

impl Default for DerivedConstraints {
    fn default() -> Self {
        Self {
            loop_spacing: HashMap::new(),
            thermal_clearances: HashMap::new(),
            si_max_placement_dist: HashMap::new(),
            hv_lv_isolation_mm: 6.5,
        }
    }
}

/// Quality configuration assembled from classification + derived constraints.
#[derive(Debug, Clone)]
pub struct QualityConfig {
    pub thermal_components: BTreeSet<String>,
    pub hv_components: BTreeSet<String>,
    pub lv_components: BTreeSet<String>,
    pub zone_assignments: HashMap<String, String>,
    pub loop_components: Vec<Vec<String>>,
    pub min_hv_lv_clearance_mm: f64,
}

/// Simplified PCB specification for constraint derivation.
#[derive(Debug, Clone)]
pub struct PcbSpecification {
    pub name: String,
    pub max_loop_area_mm2: HashMap<String, f64>,
    pub power_dissipation: HashMap<String, f64>,
    pub max_length_mm: HashMap<String, f64>,
    pub max_junction_temp_c: f64,
    pub ambient_temp_c: f64,
}

/// Simplified placement state.
#[derive(Debug, Clone)]
pub struct PlacementState {
    /// Component positions: [(x, y), ...] in mm
    pub positions: Vec<(f64, f64)>,
    /// Component references in same order as positions
    pub component_refs: Vec<String>,
    /// Board dimensions
    pub board_width_mm: f64,
    pub board_height_mm: f64,
}

/// Simplified netlist for classification and constraint derivation.
#[derive(Debug, Clone)]
pub struct Netlist {
    pub nets: Vec<NetInfo>,
    pub components: Vec<ComponentInfo>,
}

#[derive(Debug, Clone)]
pub struct NetInfo {
    pub name: String,
    pub pins: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct ComponentInfo {
    pub ref_des: String,
    pub footprint: String,
    pub width_mm: f64,
    pub height_mm: f64,
    pub voltage: f64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    #[test]
    fn test_normalized_score_valid() {
        assert!(NormalizedScore::new(0.0).is_ok());
        assert!(NormalizedScore::new(0.73).is_ok());
        assert!(NormalizedScore::new(1.0).is_ok());
    }

    #[test]
    fn test_normalized_score_out_of_range() {
        assert!(matches!(
            NormalizedScore::new(1.2),
            Err(ScoreError::OutOfRange { value: v }) if (v - 1.2).abs() < 1e-10
        ));
        assert!(matches!(
            NormalizedScore::new(-0.1),
            Err(ScoreError::OutOfRange { value: v }) if (v + 0.1).abs() < 1e-10
        ));
    }

    #[test]
    fn test_normalized_score_nan() {
        assert!(matches!(NormalizedScore::new(f64::NAN), Err(ScoreError::NaN)));
    }

    proptest! {
        #[test]
        fn pbt_normalized_score_bounds(v in prop::num::f64::ANY) {
            let result = NormalizedScore::new(v);
            if v.is_nan() {
                prop_assert!(result.is_err());
            } else if v < 0.0 || v > 1.0 {
                prop_assert!(result.is_err());
            } else {
                prop_assert!(result.is_ok());
                prop_assert!((result.unwrap().value() - v).abs() < 1e-15);
            }
        }

        #[test]
        fn pbt_netclass_roundtrip(class in prop::sample::select(&[
            NetClass::Ground, NetClass::Power, NetClass::HighVoltage,
            NetClass::Differential, NetClass::HighCurrent, NetClass::GateDrive,
            NetClass::Signal,
        ])) {
            let s = class.as_str();
            let found: Vec<_> = [
                NetClass::Ground, NetClass::Power, NetClass::HighVoltage,
                NetClass::Differential, NetClass::HighCurrent, NetClass::GateDrive,
                NetClass::Signal,
            ].iter().filter(|c| c.as_str() == s).collect();
            prop_assert_eq!(found.len(), 1);
            prop_assert_eq!(*found[0], class);
        }
    }

    #[test]
    fn test_quality_metrics_from_precomputed() {
        let pre = PrecomputedMetrics {
            thermal_score: 0.9,
            zone_compliance_score: 0.8,
            hv_lv_clearance_score: 1.0,
            loop_area_score: 0.7,
            congestion_score: 0.85,
            compactness_score: 0.75,
            connectivity_clustering_score: 0.6,
            total_wirelength_mm: 150.0,
        };
        let metrics = QualityMetrics::from_precomputed(&pre).unwrap();
        assert!((metrics.overall_score.value() - 0.8).abs() < 1e-10);
        assert_eq!(metrics.total_wirelength_mm, 150.0);
    }

    #[test]
    fn test_quality_metrics_rejects_bad_score() {
        let pre = PrecomputedMetrics {
            thermal_score: 1.5,
            zone_compliance_score: 0.8,
            hv_lv_clearance_score: 1.0,
            loop_area_score: 0.7,
            congestion_score: 0.85,
            compactness_score: 0.75,
            connectivity_clustering_score: 0.6,
            total_wirelength_mm: 150.0,
        };
        assert!(QualityMetrics::from_precomputed(&pre).is_err());
    }

    #[test]
    fn test_netclass_as_str() {
        assert_eq!(NetClass::Ground.as_str(), "ground");
        assert_eq!(NetClass::HighVoltage.as_str(), "high_voltage");
        assert_eq!(NetClass::Signal.as_str(), "signal");
    }

    #[test]
    fn test_verdict_pass() {
        let metrics = QualityMetrics::from_precomputed(&PrecomputedMetrics {
            thermal_score: 0.5,
            zone_compliance_score: 0.5,
            hv_lv_clearance_score: 0.5,
            loop_area_score: 0.5,
            congestion_score: 0.5,
            compactness_score: 0.5,
            connectivity_clustering_score: 0.5,
            total_wirelength_mm: 100.0,
        }).unwrap();
        let verdict = QualityVerdict::Pass { metrics: metrics.clone() };
        assert!(verdict.is_pass());
        assert!((verdict.metrics().overall_score.value() - 0.5).abs() < 1e-10);
    }
}
