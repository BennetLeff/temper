//! Verify retained conditional-study measurements without rerunning the solver.
use std::{collections::BTreeMap, error::Error, fs, path::Path};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
fn read_rows(text: &str) -> Result<BTreeMap<String, BTreeMap<String, f64>>> {
    let mut lines = text.lines();
    let header: Vec<_> = lines.next().ok_or("missing header")?.split(',').collect();
    let mut rows = BTreeMap::new();
    for line in lines {
        let cells: Vec<_> = line.split(',').collect();
        if cells.len() != header.len() {
            return Err("wrong field count".into());
        }
        let mut values = BTreeMap::new();
        for (key, value) in header.iter().skip(1).zip(cells.iter().skip(1)) {
            let x: f64 = value.parse()?;
            if !x.is_finite() {
                return Err("nonfinite CSV".into());
            }
            values.insert(key.to_string(), x);
        }
        if rows.insert(cells[0].to_string(), values).is_some() {
            return Err("duplicate case".into());
        }
    }
    Ok(rows)
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 2 {
        return Err("verify OUTPUT_DIR".into());
    }
    let out = Path::new(&args[1]);
    fs::write(
        out.join("verification.json"),
        "{\"class\":\"INCOMPLETE\"}\n",
    )?;
    let rows = read_rows(&fs::read_to_string(out.join("catch.csv"))?)?;
    if rows.len() != 52 {
        return Err("requires all 52 cases".into());
    }
    let base = rows.get("catch-042").ok_or("missing baseline")?;
    let metrics = [
        "vbus_pk",
        "catch_pk",
        "catch_i_pk",
        "catch_i2t",
        "vcap_pk",
        "current_pk",
    ];
    let mut max_delta: f64 = 0.;
    let mut max_energy: f64 = 0.;
    for row in rows.values() {
        let error = *row
            .get("energy_residual")
            .ok_or("missing energy residual")?;
        max_energy = max_energy.max(error.abs());
    }
    for name in ["refine-049", "refine-050"] {
        let row = rows.get(name).ok_or("missing refinement")?;
        for key in metrics {
            let b = *base.get(key).ok_or("missing baseline metric")?;
            let r = *row.get(key).ok_or("missing refinement metric")?;
            if b <= 0. {
                return Err("nonpositive peak metric".into());
            }
            max_delta = max_delta.max((r - b).abs() / b);
        }
    }
    if max_delta > 0.02 || max_energy > 0.005 {
        return Err("numerical screen failed".into());
    }
    for (name, threshold) in [("invalid-rearm-051", 350.), ("invalid-rearm-052", 500.)] {
        if *rows
            .get(name)
            .and_then(|r| r.get("vbus_pk"))
            .ok_or("missing restart probe")?
            <= threshold
        {
            return Err("negative restart example no longer exposes headroom loss".into());
        }
    }
    let result=format!("{{\n  \"class\": \"NUMERICAL_METRIC_SCREEN_NOT_HARDWARE\",\n  \"cases\": 52,\n  \"baseline\": \"catch-042\",\n  \"maximum_relative_peak_difference\": {max_delta:.12},\n  \"maximum_energy_residual_fraction_all_cases\": {max_energy:.12},\n  \"invalid_restart_probes_exceed_350_and_500_v\": true\n}}\n");
    fs::write(out.join("verification.json"), result)?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_duplicate_cases() {
        assert!(read_rows("case,a\nx,1\nx,2\n").is_err());
    }
    #[test]
    fn rejects_nonfinite() {
        assert!(read_rows("case,a\nx,NaN\n").is_err());
    }
    #[test]
    fn rejects_truncated_row() {
        assert!(read_rows("case,a,b\nx,1\n").is_err());
    }
}
