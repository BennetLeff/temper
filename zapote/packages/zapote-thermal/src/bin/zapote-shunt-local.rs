use anyhow::{ensure, Result};
use std::{env, fs, path::PathBuf};
use zapote_thermal::{neck_run::Tools, shunt_local};
fn main() -> Result<()> {
    let a: Vec<_> = env::args().collect();
    ensure!(
        a.len() == 4 || a.len() == 7,
        "usage: zapote-shunt-local replay NATIVE OUT | run NATIVE OUT GMSH ELMERGRID ELMERSOLVER"
    );
    let native = fs::read(&a[2])?;
    let out = PathBuf::from(&a[3]);
    let r = if a[1] == "replay" && a.len() == 4 {
        shunt_local::replay(&native, &out)?
    } else {
        ensure!(a[1] == "run" && a.len() == 7, "invalid command");
        shunt_local::run(
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
