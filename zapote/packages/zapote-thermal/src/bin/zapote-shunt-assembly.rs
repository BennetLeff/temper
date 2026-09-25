use anyhow::{ensure, Result};
use std::{env, fs, path::PathBuf};
use zapote_thermal::{neck_run::Tools, shunt_assembly};
fn main() -> Result<()> {
    let a: Vec<_> = env::args().collect();
    ensure!(
        a.len() == 4 || a.len() == 7 || a.len()==8,
        "usage: zapote-shunt-assembly replay NATIVE OUT | run NATIVE OUT GMSH ELMERGRID ELMERSOLVER | run-from NATIVE OUT GMSH ELMERGRID ELMERSOLVER SEED"
    );
    let native = fs::read(&a[2])?;
    let out = PathBuf::from(&a[3]);
    let r = if a[1] == "replay" && a.len() == 4 {
        shunt_assembly::replay(&native, &out)?
    } else if a[1] == "run-from" && a.len() == 8 {
        shunt_assembly::run_from(
            &native,
            &out,
            &Tools {
                gmsh: PathBuf::from(&a[4]),
                grid: PathBuf::from(&a[5]),
                solver: PathBuf::from(&a[6]),
            },
            Some(std::path::Path::new(&a[7])),
        )?
    } else {
        ensure!(a[1] == "run" && a.len() == 7, "invalid command");
        shunt_assembly::run(
            &native,
            &out,
            &Tools {
                gmsh: PathBuf::from(&a[4]),
                grid: PathBuf::from(&a[5]),
                solver: PathBuf::from(&a[6]),
            },
        )?
    };
    println!("{}", serde_json::to_string_pretty(&r)?);
    Ok(())
}
