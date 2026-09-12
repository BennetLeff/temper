//! Projected two-domain copper spacing check.
//!
//! This is a bounded cross-domain screen. It deliberately does not claim
//! whole-board insulation when third-party nets are outside the two sets.

use crate::current_sense::native_clearance;
use std::collections::BTreeSet;
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};

const RULE: &str = "DRC.NATIVE.DOMAIN_SEPARATION";
const LEFT: &str = "__DOMAIN_LEFT__";
const RIGHT: &str = "__DOMAIN_RIGHT__";

fn fail(message: impl Into<String>, object: impl Into<String>) -> CheckReport {
    CheckReport::from_findings(
        vec![Finding::fail(RULE, message, object)],
        vec![RULE.into()],
        vec![],
    )
}

fn classify<'a>(
    net: &'a str,
    left: &BTreeSet<String>,
    right: &BTreeSet<String>,
) -> Option<&'a str> {
    if left.contains(net) {
        Some(LEFT)
    } else if right.contains(net) {
        Some(RIGHT)
    } else {
        None
    }
}

fn project(
    native: &UnitNativeEvidence,
    left: &BTreeSet<String>,
    right: &BTreeSet<String>,
) -> UnitNativeEvidence {
    let map = |net: &str| classify(net, left, right).unwrap().to_owned();
    let mut projected = native.clone();
    projected.components = native
        .components
        .iter()
        .cloned()
        .map(|mut component| {
            component.footprint_pads = component
                .footprint_pads
                .into_iter()
                .filter(|pad| classify(&pad.net, left, right).is_some())
                .map(|mut pad| {
                    pad.net = map(&pad.net);
                    pad.layers = vec!["F.Cu".into()];
                    pad
                })
                .collect();
            component
        })
        .collect();
    projected.connections = native
        .connections
        .iter()
        .cloned()
        .filter(|c| classify(&c.net, left, right).is_some())
        .map(|mut c| {
            c.net = map(&c.net);
            c
        })
        .collect();
    projected.connectivity_clusters = native
        .connectivity_clusters
        .iter()
        .cloned()
        .filter(|c| classify(&c.net, left, right).is_some())
        .map(|mut c| {
            c.net = map(&c.net);
            c
        })
        .collect();
    projected.traces = native
        .traces
        .iter()
        .cloned()
        .filter(|t| classify(&t.net, left, right).is_some())
        .map(|mut t| {
            t.net = map(&t.net);
            t.layer = "F.Cu".into();
            t
        })
        .collect();
    projected.vias = native
        .vias
        .iter()
        .cloned()
        .filter(|v| classify(&v.net, left, right).is_some())
        .map(|mut v| {
            v.net = map(&v.net);
            v.from_layer = "F.Cu".into();
            v.to_layer = "F.Cu".into();
            v
        })
        .collect();
    projected.zones = native
        .zones
        .iter()
        .cloned()
        .filter(|z| classify(&z.net, left, right).is_some())
        .map(|mut z| {
            z.net = map(&z.net);
            z.layer = "F.Cu".into();
            z
        })
        .collect();
    projected.copper_layer_count = 1;
    projected
}

/// Check only geometry belonging to the disjoint `left` and `right` net sets.
/// Unlisted nets are returned as a coverage gap and remain out of scope.
pub fn validate(
    native: &UnitNativeEvidence,
    left: &BTreeSet<String>,
    right: &BTreeSet<String>,
    minimum_mm: f64,
) -> CheckReport {
    if left.is_empty() || right.is_empty() {
        return fail("left and right net sets must both be non-empty", "net_sets");
    }
    if !left.is_disjoint(right) {
        return fail("left and right net sets must be disjoint", "net_sets");
    }
    if !minimum_mm.is_finite() || minimum_mm <= 0.0 {
        return fail(
            "minimum clearance must be finite and positive",
            "minimum_mm",
        );
    }
    let observed_nets: BTreeSet<_> = native
        .components
        .iter()
        .flat_map(|c| c.footprint_pads.iter().map(|p| p.net.as_str()))
        .chain(native.traces.iter().map(|t| t.net.as_str()))
        .chain(native.vias.iter().map(|v| v.net.as_str()))
        .chain(native.zones.iter().map(|z| z.net.as_str()))
        .collect();
    if left.iter().any(|net| !observed_nets.contains(net.as_str()))
        || right
            .iter()
            .any(|net| !observed_nets.contains(net.as_str()))
    {
        return fail(
            "a classified net has no observed native geometry",
            "net_sets",
        );
    }
    let observed_left = native
        .components
        .iter()
        .flat_map(|c| &c.footprint_pads)
        .any(|p| left.contains(&p.net))
        || native.traces.iter().any(|t| left.contains(&t.net))
        || native.vias.iter().any(|v| left.contains(&v.net))
        || native.zones.iter().any(|z| left.contains(&z.net));
    let observed_right = native
        .components
        .iter()
        .flat_map(|c| &c.footprint_pads)
        .any(|p| right.contains(&p.net))
        || native.traces.iter().any(|t| right.contains(&t.net))
        || native.vias.iter().any(|v| right.contains(&v.net))
        || native.zones.iter().any(|z| right.contains(&z.net));
    if !observed_left || !observed_right {
        return fail(
            "both domains must have observed native geometry",
            "net_sets",
        );
    }
    let projected = project(native, left, right);
    let mut report = native_clearance(&projected, minimum_mm);
    for finding in &mut report.findings {
        finding.rule = RULE.into();
        if finding.status != Status::Pass {
            finding.object = format!("left/right::{}", finding.object);
        }
    }
    let all_nets: BTreeSet<_> = native
        .components
        .iter()
        .flat_map(|c| c.footprint_pads.iter().map(|p| p.net.as_str()))
        .chain(native.traces.iter().map(|t| t.net.as_str()))
        .chain(native.vias.iter().map(|v| v.net.as_str()))
        .chain(native.zones.iter().map(|z| z.net.as_str()))
        .collect();
    let unlisted: Vec<_> = all_nets
        .into_iter()
        .filter(|net| !left.contains(*net) && !right.contains(*net))
        .collect();
    if !unlisted.is_empty() {
        report.coverage_gaps.push(format!(
            "unlisted native nets are out of scope: {}",
            unlisted.join(", ")
        ));
    }
    CheckReport::from_findings(report.findings, vec![RULE.into()], report.coverage_gaps)
}
