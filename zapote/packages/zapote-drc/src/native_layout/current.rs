//! Board-derived conditional current experiments. The operating currents below
//! come from the retained A4 study; neither that study nor this solve qualifies
//! their waveform, finished plating, cooling or local current-density peaks.
use super::{mesh, require, sheet, Result, Snapshot};
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Serialize)]
pub struct CurrentReport {
    pub schema: &'static str,
    pub board_sha256: String,
    pub profile: &'static str,
    pub interpretation: &'static str,
    pub resistivity_ohm_m: f64,
    pub mesh_area_limits_mm2: [f64; 2],
    pub resistance_refinement_limit_fraction: f64,
    pub cases: Vec<CurrentCase>,
    pub status: &'static str,
    pub geometry_gaps: Vec<String>,
}
#[derive(Serialize)]
pub struct CurrentCase {
    pub id: String,
    pub net: String,
    pub source: String,
    pub sink: String,
    pub plating_um: f64,
    pub imposed_current_a: f64,
    pub coarse: Option<sheet::SheetSolution>,
    pub refined: Option<sheet::SheetSolution>,
    pub resistance_change_fraction: Option<f64>,
    pub gaps: Vec<String>,
}

/// Run the declared A4 two-terminal experiment subset on freshly extracted
/// copper. Identifies unresolved topology/numerics explicitly, never as zero R.
pub fn evaluate(snapshot: &Snapshot, board: &[u8]) -> Result<CurrentReport> {
    snapshot.validate(board)?;
    let stack =
        crate::stackup::layout_stack(std::str::from_utf8(board).map_err(|e| e.to_string())?)?;
    require(
        snapshot.layers
            == stack
                .copper
                .iter()
                .map(|l| l.name.clone())
                .collect::<Vec<_>>(),
        "native layer order differs from stackup",
    )?;
    let cases = [
        ("bus-a", "bus_p", ("J8", "1"), ("Q2", "2"), 15.),
        ("bus-b", "bus_p", ("J8", "1"), ("Q5", "2"), 15.),
        ("hv-return", "hv_ret", ("R5", "4"), ("J10", "1"), 15.),
        ("leg-a", "leg_ret", ("Q3", "3"), ("R5", "1"), 18.7),
        ("leg-b", "leg_ret", ("Q6", "3"), ("R5", "1"), 18.7),
        ("switch-a", "sw_a", ("Q2", "3"), ("T1", "1"), 18.7),
        ("coil-feed", "coil_feed", ("T1", "2"), ("J2", "1"), 18.7),
    ];
    let areas = [0.5, 0.125];
    let rho = 1.724e-8;
    let mut models = BTreeMap::new();
    for (_, net, source, sink, _) in cases {
        for (r, p) in [source, sink] {
            let pins: Vec<_> = snapshot
                .pads
                .iter()
                .filter(|pad| pad.reference == r && pad.number == p)
                .collect();
            require(
                !pins.is_empty() && pins.iter().all(|p| p.net == net),
                format!("current profile requires {r}.{p} on {net}"),
            )?;
        }
        models
            .entry(net)
            .or_insert_with(|| areas.map(|area| mesh::build(snapshot, &[net], Some(area))));
    }
    let mut output = vec![];
    for (name, net, source, sink, current) in cases {
        for plating in [18., 12.] {
            let mut gaps = vec![];
            let mut solutions = vec![];
            for (level, model) in models[net].iter().enumerate() {
                let result = model.as_ref().map_err(Clone::clone).and_then(|mesh| {
                    sheet::solve(
                        snapshot,
                        &stack,
                        mesh,
                        [source, sink],
                        current,
                        plating / 1000.,
                        rho,
                    )
                });
                match result {
                    Ok(solution) => solutions.push(Some(solution)),
                    Err(e) => {
                        gaps.push(format!("area {} mm2: {e}", areas[level]));
                        solutions.push(None);
                    }
                }
            }
            let change = solutions[0]
                .as_ref()
                .zip(solutions[1].as_ref())
                .map(|(a, b)| (a.resistance_ohm / b.resistance_ohm - 1.).abs());
            if change.is_some_and(|c| c > 0.03) {
                gaps.push("resistance changed more than 3% under mesh refinement".into());
            }
            let refined = solutions.pop().flatten();
            let coarse = solutions.pop().flatten();
            output.push(CurrentCase {
                id: format!("{name}/plating-{plating}um"),
                net: net.into(),
                source: format!("{}.{}", source.0, source.1),
                sink: format!("{}.{}", sink.0, sink.1),
                plating_um: plating,
                imposed_current_a: current,
                coarse,
                refined,
                resistance_change_fraction: change,
                gaps,
            });
        }
    }
    let status = if snapshot.gaps.is_empty() && output.iter().all(|c| c.gaps.is_empty()) {
        "conditional_numerics_complete"
    } else {
        "incomplete"
    };
    Ok(CurrentReport {
        schema: "zapote.native-current.v1",
        board_sha256: snapshot.board_sha256.clone(),
        profile: "a4-two-terminal.v1",
        interpretation: concat!(
            "Conditional two-terminal DC sheet FEM at 20 C with ideal equipotential ",
            "pad/via annuli and ideal component terminal electrodes, finite plated ",
            "barrel R, 12/18 um assumed plating. Currents follow the retained A4 ",
            "experiment subset; source-lead sharing here is equipotential, not the ",
            "older equal-injection assumption. No AC, lead/contact R, thermal feedback, ",
            "ampacity verdict or converged local peak claim. Separate islands remain ",
            "unused. Not operating qualification."
        ),
        resistivity_ohm_m: rho,
        mesh_area_limits_mm2: areas,
        resistance_refinement_limit_fraction: 0.03,
        cases: output,
        status,
        geometry_gaps: snapshot.gaps.clone(),
    })
}

impl CurrentReport {
    /// Add resolved conditional R/loss measurements to the existing comparison
    /// path. A missing or unconverged solve contributes no numeric value; report
    /// comparison consequently retains a removed measurement as null, not zero.
    pub fn append_measurements(
        &self,
        snapshot: &Snapshot,
        report: &mut super::NativeReport,
    ) -> Result<()> {
        use crate::layout_quality::report::Family;
        require(
            self.board_sha256 == report.board_sha256 && self.board_sha256 == snapshot.board_sha256,
            "current/layout board identities differ",
        )?;
        report.profile = format!("{}+{}", report.profile, self.profile);
        for case in &self.cases {
            if !case.gaps.is_empty() || !self.geometry_gaps.is_empty() {
                continue;
            }
            let Some(solution) = &case.refined else {
                continue;
            };
            let source = snapshot
                .pads
                .iter()
                .find(|p| format!("{}.{}", p.reference, p.number) == case.source)
                .ok_or("current source absent from snapshot")?;
            for (name, value) in [
                ("dc_resistance_ohm_20c", solution.resistance_ohm),
                ("dc_loss_w_20c", solution.loss_w),
            ] {
                report.metric(super::Measurement {
                    id: format!("current/{}", case.id),
                    family: Family::CopperDistribution,
                    objects: vec![case.source.clone(), case.sink.clone()],
                    location_mm: source.position_mm,
                    metric: name.into(),
                    value,
                    interpretation: format!(
                        "{}; imposed {} A, assumed {} um plating",
                        self.interpretation, case.imposed_current_a, case.plating_um
                    ),
                })?;
            }
        }
        report
            .measurements
            .sort_by(|a, b| (&a.id, &a.metric).cmp(&(&b.id, &b.metric)));
        for coverage in &mut report.coverage {
            coverage.native_measurements = report
                .measurements
                .iter()
                .filter(|m| m.family == coverage.family)
                .count();
        }
        Ok(())
    }
}
