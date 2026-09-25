use anyhow::{bail, Result};
use std::{env, fs, path::Path};
use zapote_thermal::neck_run::{self, Tools};

fn main() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    let report = match args.as_slice() {
        [mode, board, native, manufacturing, output, gmsh, grid, solver] if mode == "run" => {
            neck_run::run(Path::new(board), Path::new(native), Path::new(manufacturing),
                Path::new(output), &Tools { gmsh: gmsh.into(), grid: grid.into(), solver: solver.into() })?
        }
        [mode, evidence, board] if mode == "replay" => {
            neck_run::replay(Path::new(evidence), &fs::read(board)?)?
        }
        _ => bail!("usage: zapote-thermal-necks run BOARD NATIVE MANUFACTURING OUTPUT GMSH ELMERGRID ELMERSOLVER | replay EVIDENCE BOARD (run paths must be absolute)"),
    };
    println!(
        "{}: {} verified cases, board {}",
        report.status,
        report.cases.len(),
        report.board_sha256
    );
    for case in &report.cases {
        println!(
            "{} {:25} {:7.2} °C  {:.4} W  {} nodes",
            case.net,
            case.scenario.name,
            case.measurement.max_temperature_k - 273.15,
            case.measurement.joule_power_w,
            case.nodes
        );
    }
    Ok(())
}
