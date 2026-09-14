use anyhow::{bail, Result};
use std::{env, fs, path::Path};
use zapote_thermal::lead_fem::{self, Tools};

fn main() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.as_slice() {
        [mode, input, output, gmsh, grid, solver] if mode == "run" => {
            let report = lead_fem::run(Path::new(input), Path::new(output), &Tools { gmsh: gmsh.into(), elmergrid: grid.into(), elmersolver: solver.into() })?;
            println!("{}: {} cases, {:.6} W copper Joule source", report.status, report.cases.len(), report.geometry.total_copper_joule_w);
        }
        [mode, output, input] if mode == "replay" => {
            let report = lead_fem::replay(Path::new(output), &fs::read(input)?)?;
            println!("{}: replayed {} cases", report.status, report.cases.len());
        }
        _ => bail!("usage: zapote-lead-fem run INPUT_JSON OUTPUT_DIR GMSH ELMERGRID ELMERSOLVER | replay OUTPUT_DIR INPUT_JSON"),
    }
    Ok(())
}
