//! Conditional cooling budget for the reviewed GBJ study assembly.
//! Catalog airflow is an imposed operating point, not an installed-flow result.
use anyhow::{ensure, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

pub const SOURCES: [(&str, &str); 2] = [
    (
        "wakefield-bonded-fin.pdf",
        "d7f9c8636915b10c858c0df9940547f51925ed9fe30d7a6416e192928f3d5952",
    ),
    (
        "sanyo-san-ace-e.pdf",
        "a9dd3971db4030adab9935759c83c4ca7d6ad785ff6692113a231ea97ab4962e",
    ),
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Budget {
    pub total_heat_allowance_w: f64,
    pub required_installed_flow_cfm: f64,
    pub forced_sink_resistance_k_per_w: f64,
    pub bulk_air_rise_k: f64,
    pub conditional_sink_c: f64,
    pub nominal_fem_sink_c: f64,
    pub fan_loss_fem_sink_c: f64,
    pub natural_convection_catalog_sink_c: f64,
    pub applicability: String,
    pub assumptions: Vec<String>,
}

pub fn evaluate(root: &Path) -> Result<Budget> {
    for (name, expected) in SOURCES {
        ensure!(
            format!("{:x}", Sha256::digest(fs::read(root.join(name))?)) == expected,
            "unreviewed GBJ cooling source {name}"
        );
    }
    // Deliberately assign the fan's entire electrical rating to the shared
    // heat budget. The other PFC losses and this assignment are allowances.
    let heat = 40.0 + 65.0 + 5.6;
    let flow_m3_s = 100.0 * 0.028316846592 / 60.0;
    let air_rise = heat / (1.2 * 1005.0 * flow_m3_s);
    Ok(Budget {
        total_heat_allowance_w: heat, required_installed_flow_cfm: 100.0,
        forced_sink_resistance_k_per_w: 0.16,
        bulk_air_rise_k: air_rise,
        conditional_sink_c: 40.0 + heat * 0.16 + air_rise,
        nominal_fem_sink_c: 60.0, fan_loss_fem_sink_c: 100.0,
        natural_convection_catalog_sink_c: 40.0 + heat * 0.50,
        applicability: "indeterminate".into(),
        assumptions: vec![
            "Wakefield392-120AB catalog .16 K/W at100 CFM and .50 K/W natural convection; local spreading and actual orientation are unresolved.".into(),
            "Sanyo9RA1212E1001 has120 CFM free-air and100 Pa shutoff endpoints; neither proves100 CFM installed. Fan rating5.6 W is included in the shared heat allowance.".into(),
            "40 C inlet,65 W other-PFC heat and40 W bridge heat are allowances. Adding the whole bulk-air rise to the catalog sink rise is a conservative inlet-warming allowance, not a CFD solution.".into(),
            "60 C nominal reservoir has little margin over this catalog calculation.100 C fan-loss reservoir is a separate sensitivity, not a guaranteed no-flow bound or a shutdown-transient model.".into(),
        ],
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn catalog_budget_includes_shared_load_and_fan_heat_once() {
        let root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../thermal/cooling-options/sources");
        let b = evaluate(&root).unwrap();
        assert_eq!(b.total_heat_allowance_w, 110.6);
        assert!((b.conditional_sink_c - 59.639).abs() < 0.01);
        assert_eq!(b.natural_convection_catalog_sink_c, 95.3);
        assert_eq!(b.applicability, "indeterminate");
    }
}
