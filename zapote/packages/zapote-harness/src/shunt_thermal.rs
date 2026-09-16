//! A valid local heat-spreading experiment never qualifies the whole shunt.
use std::path::Path;
use zapote_core::{CheckReport, Finding};
pub const RULES: [&str; 2] = [
    "THERMAL.PFC.SHUNT_LOCAL_NUMERICAL",
    "THERMAL.PFC.SHUNT_ASSEMBLY",
];

pub fn run(
    root: Option<&Path>,
    native: &[u8],
    pfc: Option<&crate::pfc_power::Report>,
) -> CheckReport {
    let numerical = match root {
        None => Finding::indeterminate(RULES[0], "no retained local shunt model supplied", "shunt"),
        Some(root) => {
            let result = (|| -> anyhow::Result<_> {
                let pfc =
                    pfc.ok_or_else(|| anyhow::anyhow!("source-bound PFC waveform missing"))?;
                let s = &pfc.shunt_stress;
                anyhow::ensure!(
                    s.mpn == "HCSM2818FT10L0"
                        && (s.resistance_ohm - 0.01).abs() < 1e-12
                        && (s.rms_current_a - 15.).abs() < 1e-8,
                    "retained heat input differs from source-bound waveform/part"
                );
                zapote_thermal::shunt_local::replay(native, root)
            })();
            match result {
                Ok(r) => Finding::pass(RULES[0], format!("{} source-bound solves: mesh geometry, heat balance, convergence, boundary/material sensitivities and retained decks/logs verified", r.cases.len()), "shunt"),
                Err(e) => Finding::fail(RULES[0], format!("local shunt replay rejected: {e:#}"), "shunt"),
            }
        }
    };
    CheckReport::from_findings(vec![numerical, Finding::indeterminate(RULES[1], "5 W is conditional on 500 mm² copper and resistor surface below 100 C. Local front copper with imposed cut temperatures omits body/solder/vias/board cooling and cannot establish either condition or pulse capability", "shunt")], RULES.map(str::to_owned).to_vec(), vec![])
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;
    #[test]
    fn missing_evidence_and_missing_waveform_cannot_qualify() {
        let missing = run(None, b"{}", None);
        assert_eq!(missing.status, Status::Indeterminate);
        assert_eq!(missing.checked_rules.len(), 2);
        assert_eq!(
            run(Some(Path::new("absent")), b"{}", None).status,
            Status::Fail
        );
    }
}
