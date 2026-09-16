//! A valid local heat-spreading experiment never qualifies the whole shunt.
use std::path::Path;
use zapote_core::{CheckReport, Finding};
pub const RULES: [&str; 3] = [
    "THERMAL.PFC.SHUNT_LOCAL_NUMERICAL",
    "THERMAL.PFC.SHUNT_ASSEMBLY",
    "THERMAL.PFC.SHUNT_ASSEMBLY_NUMERICAL",
];

pub fn run(
    root: Option<&Path>,
    assembly_root: Option<&Path>,
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
    let assembly = match assembly_root {
        None => {
            Finding::indeterminate(RULES[2], "no retained assembly heat-path evidence", "shunt")
        }
        Some(root) => {
            let result = (|| -> anyhow::Result<_> {
                let stress = &pfc
                    .ok_or_else(|| anyhow::anyhow!("source-bound PFC waveform missing"))?
                    .shunt_stress;
                anyhow::ensure!(
                    stress.mpn == "HCSM2818FT10L0"
                        && (stress.resistance_ohm - 0.01).abs() < 1e-12
                        && (stress.rms_current_a - 15.).abs() < 1e-8,
                    "assembly heat input differs from source-bound waveform/part"
                );
                zapote_thermal::shunt_assembly::replay(native, root)
            })();
            match result {
                Ok(r)=>Finding::pass(RULES[2],format!("{} native copper/via/substrate/solder solves verified; internal resistor and enclosure parameters remain unresolved",r.cases.len()),"shunt"),
                Err(e)=>Finding::fail(RULES[2],format!("assembly replay rejected: {e:#}"),"shunt"),
            }
        }
    };
    CheckReport::from_findings(vec![numerical,assembly,Finding::indeterminate(RULES[1], "5 W requires 500 mm² copper and resistor surface below 100 C. The heat-path study adds native vias/back copper/substrate and assumed solder, but its crop temperatures, heat split and material properties are sensitivity inputs. Internal resistor thermal resistance, full-board cooling, other component/copper losses and pulse capability remain unresolved", "shunt")], RULES.map(str::to_owned).to_vec(), vec![])
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;
    #[test]
    fn missing_evidence_and_missing_waveform_cannot_qualify() {
        let missing = run(None, None, b"{}", None);
        assert_eq!(missing.status, Status::Indeterminate);
        assert_eq!(missing.checked_rules.len(), 3);
        assert_eq!(
            run(Some(Path::new("absent")), None, b"{}", None).status,
            Status::Fail
        );
    }
    #[test]
    fn retained_assembly_replay_passes_numerics_without_qualifying_hardware() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let candidate = root.join("power-entry/shunt-repair");
        let source =
            std::fs::read_to_string(candidate.join("candidate/source-manifest.json")).unwrap();
        let native = std::fs::read_to_string(candidate.join("evidence/native-04.json")).unwrap();
        let board = std::fs::read_to_string(candidate.join("candidate/section.kicad_pcb")).unwrap();
        let manufacturing = serde_json::from_slice(
            &std::fs::read(root.join(
                "validation/runs/shunt-20260916-final-02/power-entry/manufacturing-input.json",
            ))
            .unwrap(),
        )
        .unwrap();
        let pfc = crate::pfc_power::run(&source, &native, &board, &manufacturing).unwrap();
        let report = run(
            None,
            Some(&root.join("power-entry/shunt-assembly/run-15")),
            native.as_bytes(),
            Some(&pfc),
        );
        assert_eq!(report.status, Status::Indeterminate, "{report:?}");
        assert_eq!(
            report
                .findings
                .iter()
                .find(|f| f.rule == RULES[2])
                .unwrap()
                .status,
            Status::Pass,
            "{report:?}"
        );
        assert_eq!(
            report
                .findings
                .iter()
                .find(|f| f.rule == RULES[1])
                .unwrap()
                .status,
            Status::Indeterminate
        );
    }
}
