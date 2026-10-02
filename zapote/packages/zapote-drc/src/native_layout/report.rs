use super::{finite, geometry, paths::Graph, require, Result, Snapshot};
use crate::{
    layout_quality::{copper, report::Family},
    stackup,
};
use geo::{Area, BooleanOps, Distance, Euclidean, MultiPolygon};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Measurement {
    pub id: String,
    pub family: Family,
    pub objects: Vec<String>,
    pub location_mm: [f64; 2],
    pub metric: String,
    pub value: f64,
    pub interpretation: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Coverage {
    pub family: Family,
    pub native_measurements: usize,
    pub unresolved_model: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NativeReport {
    pub schema: String,
    pub board_sha256: String,
    pub profile: String,
    pub measurements: Vec<Measurement>,
    pub routes: BTreeMap<String, super::Route>,
    pub coverage: Vec<Coverage>,
    pub geometry_gaps: Vec<String>,
    pub population: BTreeMap<String, usize>,
    pub interpretation: String,
}
#[derive(Debug, Serialize)]
pub struct Delta {
    pub id: String,
    pub metric: String,
    pub before: Option<f64>,
    pub after: Option<f64>,
    /// Signed physical change, not a scalar quality score.
    pub change: Option<f64>,
}
impl NativeReport {
    fn metric(&mut self, measurement: Measurement) -> Result<()> {
        finite(measurement.value)?;
        self.measurements.push(measurement);
        Ok(())
    }
}
/// Compare only identical profile/schema definitions. Added/removed witnesses
/// remain explicit; disappearance is never encoded as an improvement to zero.
pub fn compare(before: &NativeReport, after: &NativeReport) -> Result<Vec<Delta>> {
    require(
        before.schema == after.schema && before.profile == after.profile,
        "incompatible layout comparison profiles",
    )?;
    let mut rows = BTreeMap::new();
    for (is_after, report) in [(false, before), (true, after)] {
        let mut seen = std::collections::BTreeSet::new();
        for m in &report.measurements {
            finite(m.value)?;
            let key = (m.id.clone(), m.metric.clone());
            require(
                seen.insert(key.clone()),
                "duplicate metric identity in report",
            )?;
            let row = rows.entry(key).or_insert(Delta {
                id: m.id.clone(),
                metric: m.metric.clone(),
                before: None,
                after: None,
                change: None,
            });
            if is_after {
                row.after = Some(m.value);
            } else {
                row.before = Some(m.value);
            }
        }
    }
    for row in rows.values_mut() {
        row.change = row
            .before
            .zip(row.after)
            .map(|(a, b)| finite(b - a))
            .transpose()?;
    }
    Ok(rows.into_values().collect())
}

/// Evaluate actual native geometry with the reviewed 120 V endpoint profile.
/// Geometry-derived values are returned even when field/operating models are
/// absent. Their coverage rows never claim full electrical qualification.
pub fn evaluate(snapshot: &Snapshot, board: &[u8]) -> Result<NativeReport> {
    snapshot.validate(board)?;
    verify_profile(snapshot)?;
    let stack = stackup::layout_stack(std::str::from_utf8(board).map_err(|e| e.to_string())?)?;
    require(
        stack
            .copper
            .iter()
            .map(|l| &l.name)
            .eq(snapshot.layers.iter()),
        "native layer order differs from saved stackup",
    )?;
    let components: BTreeMap<_, _> = snapshot
        .components
        .iter()
        .map(|c| (c.reference.as_str(), c))
        .collect();
    for required in [
        "U1", "U2", "Q2", "Q3", "Q5", "Q6", "R5", "C38", "C39", "C40", "C41",
    ] {
        require(
            components.contains_key(required),
            format!("120 V profile requires {required}; wrong board/profile"),
        )?;
    }
    let mut report = NativeReport {
        schema: "zapote.layout-native-report.v1".into(),
        board_sha256: snapshot.board_sha256.clone(),
        profile: "power-stage-120v.v1".into(),
        measurements: vec![],
        routes: BTreeMap::new(),
        coverage: vec![],
        geometry_gaps: snapshot.gaps.clone(),
        population: BTreeMap::from([
            ("components".into(), snapshot.components.len()),
            ("pads".into(), snapshot.pads.len()),
            ("tracks".into(), snapshot.tracks.len()),
            ("vias".into(), snapshot.vias.len()),
            ("zones".into(), snapshot.zone_count),
            ("copper_object_layers".into(), snapshot.copper.len()),
        ]),
        interpretation: concat!(
            "Native layout measurements and comparison screens; not a board acceptance ",
            "verdict. Route lengths include straight pad-centre links, exclude zone ",
            "interiors and unsupported junctions. DC track resistance excludes ",
            "pad/via/spreading resistance. No missing coupling, current, thermal or ",
            "tolerance model is assigned zero."
        )
        .into(),
    };
    measure_routes(snapshot, &stack, &mut report)?;
    track_resistance(snapshot, &stack, &mut report)?;
    assembly(snapshot, &components, &mut report)?;
    thermal(&components, &mut report)?;
    coupling(snapshot, &stack, &mut report)?;
    let missing = [
        (Family::GateCoupling,concat!("Operating-slew and extracted mutual-inductance models for both legs; geometry ",
"alone is not induced VGS")),
        (Family::KelvinSense,"Shared-current graph, magnetic/electric pickup and sense-input transfer functions"),
        (Family::SwitchCoupling,"Fringing, same-layer electric fields, shielding and actual differential dv/dt"),
        (Family::Decoupling,"Effective biased capacitance, ESR/ESL and complete extracted supply/return inductance"),
        (Family::ReturnPath,"Distributed zone returns, common-path currents and shared inductance"),
        (Family::CopperDistribution,concat!("Zone/pad/via discretization and operating current injections; section R is ",
"not current distribution")),
        (Family::EmiBypass,"Magnetic bypass and victim transfer impedance; projected overlap is not filter insertion loss"),
        (Family::ThermalInfluence,"Assembly-specific transfer coefficients, source losses and drift coefficients"),
        (Family::AssemblyMargin,"Actual 3D package/hardware envelopes, tolerances and access reservations"),
    ];
    report.coverage = missing
        .into_iter()
        .map(|(family, unresolved_model)| Coverage {
            family,
            native_measurements: report
                .measurements
                .iter()
                .filter(|m| m.family == family)
                .count(),
            unresolved_model: unresolved_model.into(),
        })
        .collect();
    report
        .measurements
        .sort_by(|a, b| (&a.id, &a.metric).cmp(&(&b.id, &b.metric)));
    report.geometry_gaps.sort();
    report.geometry_gaps.dedup();
    Ok(report)
}

/// These are native-17 electrical identities, not fuzzy reference/net matching.
/// Any source/pinout change needs a reviewed profile update and a new baseline.
fn verify_profile(snapshot: &Snapshot) -> Result<()> {
    for (reference, pin, expected) in [
        ("U1", "3", "v3v3"),
        ("U1", "4", "selv_gnd"),
        ("U1", "9", "leg_ret"),
        ("U1", "10", "leg_a-out_l"),
        ("U1", "11", "v15_ls"),
        ("U1", "14", "sw_a"),
        ("U1", "15", "leg_a-out_h"),
        ("U1", "16", "leg_a-boot"),
        ("U2", "3", "v3v3"),
        ("U2", "4", "selv_gnd"),
        ("U2", "9", "leg_ret"),
        ("U2", "10", "leg_b-out_l"),
        ("U2", "11", "v15_ls"),
        ("U2", "14", "sw_b"),
        ("U2", "15", "leg_b-out_h"),
        ("U2", "16", "leg_b-boot"),
        ("Q2", "1", "leg_a-gate_h"),
        ("Q3", "1", "leg_a-gate_l"),
        ("Q5", "1", "leg_b-gate_h"),
        ("Q6", "1", "leg_b-gate_l"),
        ("R5", "2", "leg_ret"),
        ("R5", "3", "ocp_kelvin_n"),
        ("U6", "3", "ocp_node"),
    ] {
        require(
            snapshot
                .pads
                .iter()
                .any(|p| p.reference == reference && p.number == pin && p.net == expected),
            format!("120 V profile requires {reference}.{pin} on {expected}"),
        )?;
    }
    Ok(())
}

fn measure_routes(
    snapshot: &Snapshot,
    stack: &stackup::LayoutStack,
    report: &mut NativeReport,
) -> Result<()> {
    let graph = Graph::new(snapshot, stack)?;
    let mut route = |family, label: String, from: (&str, &str), to: (&str, &str)| -> Result<()> {
        let a = snapshot
            .pads
            .iter()
            .find(|p| p.reference == from.0 && p.number == from.1)
            .ok_or_else(|| format!("missing endpoint {}.{}", from.0, from.1))?;
        let b = snapshot
            .pads
            .iter()
            .find(|p| p.reference == to.0 && p.number == to.1)
            .ok_or_else(|| format!("missing endpoint {}.{}", to.0, to.1))?;
        require(
            !a.net.is_empty() && a.net == b.net,
            format!(
                "profile endpoint nets differ for {label}: {} / {}",
                a.net, b.net
            ),
        )?;
        let objects = vec![
            format!("{}.{}:{}", from.0, from.1, a.uuid),
            format!("{}.{}:{}", to.0, to.1, b.uuid),
        ];
        report.metric(Measurement {
            family,
            id: label.clone(),
            objects: objects.clone(),
            location_mm: a.position_mm,
            metric: "pad_chord_mm".into(),
            value: geometry::distance(a.position_mm, b.position_mm),
            interpretation: "Placement reference only; not routed length".into(),
        })?;
        match graph.route(from, to) {
            Ok(path) => {
                report.metric(Measurement {
                    family,
                    id: label.clone(),
                    objects: objects.clone(),
                    location_mm: a.position_mm,
                    metric: "routed_centerline_mm".into(),
                    value: path.length_mm,
                    interpretation:
                        "Track/via path with straight pad-centre links; no zone shortcut".into(),
                })?;
                report.metric(Measurement {
                    family,
                    id: label.clone(),
                    objects,
                    location_mm: a.position_mm,
                    metric: "track_resistance_ohm_20c".into(),
                    value: path.track_resistance_ohm_20c,
                    interpretation:
                        "Uniform copper at 20 C; excludes pad/via/spreading and AC effects".into(),
                })?;
                report.routes.insert(label, path);
            }
            Err(error) => report.geometry_gaps.push(format!("{label}: {error}")),
        }
        Ok(())
    };
    for (label, driver, out, fet, resistor, ret) in [
        ("A-high", "U1", "15", "Q2", "R10", "14"),
        ("A-low", "U1", "10", "Q3", "R12", "9"),
        ("B-high", "U2", "15", "Q5", "R18", "14"),
        ("B-low", "U2", "10", "Q6", "R20", "9"),
    ] {
        route(
            Family::GateCoupling,
            format!("gate/{label}/driver"),
            (driver, out),
            (resistor, "1"),
        )?;
        route(
            Family::GateCoupling,
            format!("gate/{label}/gate"),
            (resistor, "2"),
            (fet, "1"),
        )?;
        route(
            Family::ReturnPath,
            format!("return/{label}"),
            (driver, ret),
            (fet, "3"),
        )?;
    }
    for (label, a, b) in [
        ("shunt-positive", ("R5", "2"), ("U6", "2")),
        ("shunt-negative", ("R5", "3"), ("R33", "2")),
        ("sense-filter", ("R33", "1"), ("U6", "3")),
    ] {
        route(Family::KelvinSense, format!("kelvin/{label}"), a, b)?;
    }
    for (driver, cap, power, ret) in [
        ("U1", "C7", "3", "4"),
        ("U1", "C8", "11", "9"),
        ("U1", "C9", "11", "9"),
        ("U1", "C10", "16", "14"),
        ("U1", "C11", "16", "14"),
        ("U2", "C14", "3", "4"),
        ("U2", "C15", "11", "9"),
        ("U2", "C16", "11", "9"),
        ("U2", "C17", "16", "14"),
        ("U2", "C18", "16", "14"),
    ] {
        route(
            Family::Decoupling,
            format!("decoupling/{cap}/supply"),
            (cap, "1"),
            (driver, power),
        )?;
        route(
            Family::Decoupling,
            format!("decoupling/{cap}/return"),
            (cap, "2"),
            (driver, ret),
        )?;
    }
    Ok(())
}

fn track_resistance(
    snapshot: &Snapshot,
    stack: &stackup::LayoutStack,
    report: &mut NativeReport,
) -> Result<()> {
    for track in &snapshot.tracks {
        let layer = stack
            .copper
            .iter()
            .find(|l| l.name == track.layer)
            .ok_or("track layer absent")?;
        let resistance = copper::resistance_ohm(
            track.length_mm,
            track.width_mm * layer.thickness_mm,
            1.724e-8,
        )
        .map_err(|e| e.to_string())?;
        report.metric(Measurement {
            family: Family::CopperDistribution,
            id: format!("copper/{}", track.uuid),
            objects: vec![track.uuid.clone(), track.net.clone(), track.layer.clone()],
            location_mm: track.start_mm,
            metric: "section_resistance_ohm_20c".into(),
            value: resistance,
            interpretation: concat!(
                "Ranking of actual track sections; I²R per ampere squared, not ",
                "current-sharing or ampacity"
            )
            .into(),
        })?;
    }
    Ok(())
}

fn assembly(
    snapshot: &Snapshot,
    components: &BTreeMap<&str, &super::Component>,
    report: &mut NativeReport,
) -> Result<()> {
    let mut courtyards = BTreeMap::new();
    for c in &snapshot.components {
        if c.courtyards.is_empty() {
            report
                .geometry_gaps
                .push(format!("{}: no native courtyard", c.reference));
        }
        for courtyard in &c.courtyards {
            courtyards.insert(
                (c.reference.as_str(), courtyard.side.as_str()),
                geometry::shape(&courtyard.polygons)?,
            );
        }
    }
    let entries: Vec<_> = courtyards.iter().collect();
    for (i, ((a, side), shape_a)) in entries.iter().enumerate() {
        for ((b, other_side), shape_b) in &entries[i + 1..] {
            if side != other_side || a == b {
                continue;
            }
            let gap = finite(Euclidean::distance(*shape_a, *shape_b))?;
            if gap <= 5.0 {
                let label = format!("assembly/{a}/{b}/{side}");
                let objects = vec![(*a).to_string(), (*b).to_string()];
                report.metric(Measurement {
                    family: Family::AssemblyMargin,
                    id: label.clone(),
                    objects: objects.clone(),
                    location_mm: components[a].position_mm,
                    metric: "courtyard_gap_mm".into(),
                    value: gap,
                    interpretation: concat!(
                        "Same-side native courtyard clearance; nominal 2D screen, no ",
                        "3D/tolerance/access allowance"
                    )
                    .into(),
                })?;
                let area = shape_a.intersection(*shape_b).unsigned_area();
                if area > 0.0 {
                    report.metric(Measurement {
                        family: Family::AssemblyMargin,
                        id: label,
                        objects,
                        location_mm: components[a].position_mm,
                        metric: "courtyard_overlap_mm2".into(),
                        value: area,
                        interpretation:
                            "Positive native courtyard overlap warrants placement review".into(),
                    })?;
                }
            }
        }
    }
    Ok(())
}

fn thermal(
    components: &BTreeMap<&str, &super::Component>,
    report: &mut NativeReport,
) -> Result<()> {
    for heater in ["Q2", "Q3", "Q5", "Q6", "BR1", "R5"] {
        for victim in ["U4", "U5", "U6", "U7", "R29", "R30", "R31", "R32", "R33"] {
            let a = components
                .get(heater)
                .ok_or_else(|| format!("missing heat source {heater}"))?;
            let b = components
                .get(victim)
                .ok_or_else(|| format!("missing thermal victim {victim}"))?;
            report.metric(Measurement {
                family: Family::ThermalInfluence,
                id: format!("thermal/{heater}/{victim}"),
                objects: vec![heater.into(), victim.into()],
                location_mm: b.position_mm,
                metric: "component_center_distance_mm".into(),
                value: geometry::distance(a.position_mm, b.position_mm),
                interpretation: concat!(
                    "Thermal placement screen only; not temperature, heat-transfer ",
                    "coefficient or drift"
                )
                .into(),
            })?;
        }
    }
    Ok(())
}

fn coupling(
    snapshot: &Snapshot,
    stack: &stackup::LayoutStack,
    report: &mut NativeReport,
) -> Result<()> {
    // Union each net/layer first: overlapping tracks, pads and fills cannot be
    // counted repeatedly. Native polygons preserve holes and flashed pad layers.
    let mut groups: BTreeMap<(&str, &str), MultiPolygon<f64>> = BTreeMap::new();
    let mut copper: Vec<_> = snapshot.copper.iter().collect();
    copper.sort_by_key(|item| (&item.net, &item.layer, &item.uuid));
    for item in copper {
        let shape = geometry::shape(&item.polygons)?;
        let entry = groups
            .entry((&item.net, &item.layer))
            .or_insert_with(|| MultiPolygon(vec![]));
        *entry = entry.union(&shape);
    }
    let switch = ["sw_a", "sw_b", "res_a", "coil_feed"];
    let sensitive = [
        "pwm_ha",
        "pwm_la",
        "pwm_hb",
        "pwm_lb",
        "ocp_node",
        "ocp_thresh",
        "ocp_kelvin_n",
        "vsense_in",
        "ref25",
        "vbus_p",
        "vbus_n",
        "ct_sense_mon",
        "ct_ref_hi",
        "ct_ref_lo",
        "selv_gnd",
    ];
    let mains = ["ac_l_in", "ac_n_in"];
    let filtered = [
        "l_filt", "n_filt", "rect_p", "rect_n", "bus_p", "hv_ret", "sw_a", "sw_b",
    ];
    for net in switch
        .iter()
        .chain(&sensitive)
        .chain(&mains)
        .chain(&filtered)
    {
        if !groups.keys().any(|(name, _)| name == net) {
            report.geometry_gaps.push(format!(
                "coupling/{net}: no captured copper for profile net"
            ));
        }
    }
    for (family, aggressors, victims) in [
        (
            Family::SwitchCoupling,
            switch.as_slice(),
            sensitive.as_slice(),
        ),
        (Family::EmiBypass, mains.as_slice(), filtered.as_slice()),
    ] {
        let prefix = if family == Family::SwitchCoupling {
            "switch"
        } else {
            "emi"
        };
        for &a in aggressors {
            for &b in victims {
                for (upper, lower, electrical_distance) in &stack.adjacent_dielectrics {
                    for (a_layer, b_layer) in [(upper, lower), (lower, upper)] {
                        if let (Some(x), Some(y)) = (
                            groups.get(&(a, a_layer.as_str())),
                            groups.get(&(b, b_layer.as_str())),
                        ) {
                            report.metric(projected_pair(
                                family,
                                format!("{prefix}/{a}/{a_layer}/{b}/{b_layer}"),
                                vec![a.into(), a_layer.clone(), b.into(), b_layer.clone()],
                                x,
                                y,
                                *electrical_distance,
                            )?)?;
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn projected_pair(
    family: Family,
    id: String,
    objects: Vec<String>,
    aggressor: &MultiPolygon<f64>,
    victim: &MultiPolygon<f64>,
    electrical_distance: f64,
) -> Result<Measurement> {
    let overlap = aggressor.intersection(victim);
    let area = overlap.unsigned_area();
    let capacitance = if area == 0.0 {
        0.0
    } else {
        crate::layout_quality::capacitance::parallel_plate_pf(area, electrical_distance, 1.0)
            .map_err(|e| e.to_string())?
    };
    let location = overlap
        .0
        .first()
        .or_else(|| aggressor.0.first())
        .and_then(|p| p.exterior().0.first())
        .ok_or("copper union has no location witness")?;
    Ok(Measurement {
        family,
        id,
        objects,
        location_mm: [location.x, location.y],
        metric: "adjacent_projected_capacitance_pf".into(),
        value: capacitance,
        interpretation: concat!(
            "Native filled-copper union and declared dielectric stackup; ",
            "adjacent layers only, no fringing; zero overlap is not zero real coupling"
        )
        .into(),
    })
}
