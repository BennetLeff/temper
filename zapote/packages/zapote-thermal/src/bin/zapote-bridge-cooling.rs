use anyhow::{bail, Result};
use std::{env, fs, path::Path};
use zapote_thermal::{bridge_cooling, neck_run::Tools};

fn main() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    let report = match args.as_slice() {
        [mode, board, native, manufacturing, contract, output, gmsh, grid, solver]
            if mode == "run" => bridge_cooling::run(
                Path::new(board),
                Path::new(native),
                Path::new(manufacturing),
                Path::new(contract),
                Path::new(output),
                &Tools {
                    gmsh: gmsh.into(),
                    grid: grid.into(),
                    solver: solver.into(),
                },
            )?,
        [mode, evidence, board, contract] if mode == "replay" => bridge_cooling::replay(
            Path::new(evidence),
            &fs::read(board)?,
            &fs::read(contract)?,
        )?,
        _ => bail!(
            "usage: zapote-bridge-cooling run BOARD NATIVE MANUFACTURING CONTRACT OUTPUT GMSH ELMERGRID ELMERSOLVER | replay EVIDENCE BOARD CONTRACT"
        ),
    };
    println!(
        "{}: design={} failed_fan={} board {}",
        report.status,
        report.design_fine_compliant,
        report.failed_fan_budget_compliant,
        report.board_sha256
    );
    for (net, temperatures) in report.per_net {
        println!(
            "{net:5} design-fine {:7.2} °C  weak-contact-fine {:7.2} °C",
            temperatures.design_fine_c, temperatures.weak_contact_fine_c
        );
    }
    Ok(())
}
