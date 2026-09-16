use anyhow::{bail, Context, Result};
use std::{env, fs, path::Path};
use zapote_thermal::shunt_model::{cases, gmsh_geometry, ShuntGeometry};

fn main() -> Result<()> {
    let a: Vec<String> = env::args().skip(1).collect();
    if a.len() < 2 || a[0] != "screen" {
        bail!("usage: zapote-shunt-model screen NATIVE_JSON OUTPUT_JSON [GMSH_GEO]");
    }
    let native = fs::read(&a[1]).with_context(|| format!("read {}", a[1]))?;
    let geometry = ShuntGeometry::from_native(&native)?;
    if let Some(path) = a.get(3) {
        gmsh_geometry(&geometry, Path::new(path))?;
    }
    let report = serde_json::json!({
        "schema": "zapote.shunt-thermal.v1",
        "status": "INDETERMINATE_BODY_THERMAL_DATA",
        "geometry": geometry,
        "cases": cases(15.0)?,
        "limitations": ["copper crop only", "resistor body terminal-to-case thermal resistance is not published/validated"]
    });
    fs::write(&a[2], serde_json::to_vec_pretty(&report)?)?;
    println!("wrote {}", a[2]);
    Ok(())
}
