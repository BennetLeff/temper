//! Bounded device thermal and shutdown timing operating limits.
//!
//! These are analytical models.  They require explicit loss, thermal-path,
//! ambient, and delay bounds; nominal values never become guarantees.

use zapote_core::{CheckReport, Finding};

const THERMAL: &str = "ERC.P3.THERMAL_OPERATING_LIMIT";
const SHUTDOWN: &str = "ERC.P3.SHUTDOWN_TIMING_BOUND";

#[derive(Debug, Clone, PartialEq)]
pub struct DeviceOperatingPoint {
    pub device: String,
    pub loss_w: f64,
    pub theta_jc_c_per_w: f64,
    pub theta_cs_c_per_w: Option<f64>,
    pub theta_sa_c_per_w: Option<f64>,
    pub ambient_c: f64,
    pub max_junction_c: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ShutdownTimingBound {
    pub path: String,
    pub detection_ms: Option<f64>,
    pub actuation_ms: Option<f64>,
    pub switching_off_ms: Option<f64>,
    pub max_response_ms: Option<f64>,
}

pub fn junction_temperature(point: &DeviceOperatingPoint) -> Option<f64> {
    let r = point.theta_cs_c_per_w? + point.theta_sa_c_per_w? + point.theta_jc_c_per_w;
    (point.loss_w.is_finite()
        && point.loss_w >= 0.0
        && point.theta_jc_c_per_w.is_finite()
        && point.theta_jc_c_per_w >= 0.0
        && point
            .theta_cs_c_per_w
            .is_some_and(|v| v.is_finite() && v >= 0.0)
        && point
            .theta_sa_c_per_w
            .is_some_and(|v| v.is_finite() && v >= 0.0)
        && r.is_finite()
        && point.ambient_c.is_finite())
    .then_some(point.ambient_c + point.loss_w * r)
}

pub fn response_time_ms(bound: &ShutdownTimingBound) -> Option<f64> {
    let values = [
        bound.detection_ms?,
        bound.actuation_ms?,
        bound.switching_off_ms?,
    ];
    (values.iter().all(|v| v.is_finite() && *v >= 0.0)
        && values.iter().copied().sum::<f64>().is_finite())
    .then_some(values.iter().sum())
}

/// Evaluate modeled thermal margin and a separately bounded shutdown path.
/// Missing heatsink or delay bounds produce indeterminate findings.
pub fn validate(
    point: Option<DeviceOperatingPoint>,
    timing: Option<ShutdownTimingBound>,
) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    match point {
        Some(p) if p.max_junction_c.is_finite() && p.max_junction_c > 0.0 => match junction_temperature(&p) {
            Some(t) if t <= p.max_junction_c => findings.push(Finding::pass(THERMAL, format!("modeled junction {t:.2} °C is within {:.2} °C limit; model requires validated thermal path", p.max_junction_c), p.device.clone())),
            Some(t) => findings.push(Finding::fail(THERMAL, format!("modeled junction {t:.2} °C exceeds {:.2} °C limit", p.max_junction_c), p.device.clone())),
            None => { gaps.push(format!("thermal path for {} is incomplete", p.device)); findings.push(Finding::indeterminate(THERMAL, "loss, ambient, junction-case, case-sink, and sink-ambient inputs are required", p.device.clone())); }
        },
        _ => { gaps.push("no device operating point supplied".into()); findings.push(Finding::indeterminate(THERMAL, "device loss and thermal-path inputs are required", "device")); }
    }
    match timing {
        Some(t) if t.max_response_ms.is_some_and(|v| v.is_finite() && v > 0.0) => {
            match response_time_ms(&t) {
                Some(actual) if actual <= t.max_response_ms.unwrap() => {
                    findings.push(Finding::pass(
                        SHUTDOWN,
                        format!(
                            "bounded response {actual:.3} ms is within {:.3} ms",
                            t.max_response_ms.unwrap()
                        ),
                        t.path.clone(),
                    ))
                }
                Some(actual) => findings.push(Finding::fail(
                    SHUTDOWN,
                    format!(
                        "bounded response {actual:.3} ms exceeds {:.3} ms",
                        t.max_response_ms.unwrap()
                    ),
                    t.path.clone(),
                )),
                None => {
                    gaps.push(format!("shutdown delay bound for {} is incomplete", t.path));
                    findings.push(Finding::indeterminate(
                        SHUTDOWN,
                        "detection, actuation, and switch-off worst-case bounds are all required",
                        t.path.clone(),
                    ));
                }
            }
        }
        Some(t) => {
            gaps.push(format!("shutdown response limit for {} is absent", t.path));
            findings.push(Finding::indeterminate(
                SHUTDOWN,
                "a guaranteed maximum response bound is required; nominal delay is insufficient",
                t.path,
            ));
        }
        None => {
            gaps.push("no shutdown timing contract supplied".into());
            findings.push(Finding::indeterminate(
                SHUTDOWN,
                "shutdown timing inputs are required",
                "timing",
            ));
        }
    }
    CheckReport::from_findings(findings, vec![THERMAL.into(), SHUTDOWN.into()], gaps)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn point(loss: f64) -> DeviceOperatingPoint {
        DeviceOperatingPoint {
            device: "Q1".into(),
            loss_w: loss,
            theta_jc_c_per_w: 2.0,
            theta_cs_c_per_w: Some(1.0),
            theta_sa_c_per_w: Some(5.0),
            ambient_c: 40.0,
            max_junction_c: 100.0,
        }
    }
    fn timing(limit: f64) -> ShutdownTimingBound {
        ShutdownTimingBound {
            path: "gate_fault".into(),
            detection_ms: Some(1.0),
            actuation_ms: Some(1.0),
            switching_off_ms: Some(1.0),
            max_response_ms: Some(limit),
        }
    }
    #[test]
    fn passing_models_are_reported() {
        assert_eq!(
            validate(Some(point(5.0)), Some(timing(4.0))).status,
            zapote_core::Status::Pass
        );
    }
    #[test]
    fn stressed_device_fails() {
        assert_eq!(
            validate(Some(point(20.0)), Some(timing(4.0))).status,
            zapote_core::Status::Fail
        );
    }
    #[test]
    fn excessive_shutdown_fails() {
        assert_eq!(
            validate(Some(point(5.0)), Some(timing(2.0))).status,
            zapote_core::Status::Fail
        );
    }
    #[test]
    fn missing_heatsink_is_indeterminate() {
        let mut p = point(5.0);
        p.theta_sa_c_per_w = None;
        assert_eq!(
            validate(Some(p), Some(timing(4.0))).status,
            zapote_core::Status::Indeterminate
        );
    }
    #[test]
    fn nominal_timing_without_guarantee_is_indeterminate() {
        let mut t = timing(4.0);
        t.max_response_ms = None;
        assert_eq!(
            validate(Some(point(5.0)), Some(t)).status,
            zapote_core::Status::Indeterminate
        );
    }
    #[test]
    fn missing_delay_corner_is_indeterminate() {
        let mut t = timing(4.0);
        t.switching_off_ms = None;
        assert_eq!(
            validate(Some(point(5.0)), Some(t)).status,
            zapote_core::Status::Indeterminate
        );
    }
    #[test]
    fn negative_resistance_and_delay_cannot_manufacture_margin() {
        let mut p = point(5.);
        p.theta_cs_c_per_w = Some(-100.);
        assert_eq!(
            validate(Some(p), Some(timing(4.))).status,
            zapote_core::Status::Indeterminate
        );
        let mut t = timing(4.);
        t.actuation_ms = Some(-100.);
        assert_eq!(
            validate(Some(point(5.)), Some(t)).status,
            zapote_core::Status::Indeterminate
        );
    }
}
