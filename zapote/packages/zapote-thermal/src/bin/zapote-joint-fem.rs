use anyhow::{Context, Result};
use std::{env, fs, path::PathBuf, time::Duration};
use zapote_thermal::joint_fem::{self, JointInput, RunConfig};

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let mut input = None;
    let mut out = None;
    let mut gmsh = PathBuf::from("/opt/homebrew/bin/gmsh");
    let mut grid = PathBuf::from("/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerGrid");
    let mut solver = PathBuf::from("/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerSolver");
    let mut replay = None;
    while let Some(arg) = args.next() {
        let mut value = || args.next().context(format!("missing value for {arg}"));
        match arg.as_str() {
            "--input" => input = Some(PathBuf::from(value()?)),
            "--out" => out = Some(PathBuf::from(value()?)),
            "--gmsh" => gmsh = PathBuf::from(value()?),
            "--elmergrid" => grid = PathBuf::from(value()?),
            "--elmersolver" => solver = PathBuf::from(value()?),
            "--replay" => replay = Some(PathBuf::from(value()?)),
            "--help" => {
                println!("zapote-joint-fem --input JSON --out DIR [--gmsh PATH --elmergrid PATH --elmersolver PATH]\nzapote-joint-fem --replay DIR");
                return Ok(());
            }
            _ => anyhow::bail!("unknown argument {arg}"),
        }
    }
    if let Some(root) = replay {
        let report = joint_fem::replay(&root)?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Ok(());
    }
    let input = match input {
        Some(path) => serde_json::from_slice::<JointInput>(&fs::read(path)?)?,
        None => JointInput::default(),
    };
    let output_dir = out.context("--out is required")?;
    let report = joint_fem::run(&RunConfig {
        input,
        output_dir,
        gmsh,
        elmergrid: grid,
        elmersolver: solver,
        timeout: Duration::from_secs(1200),
    })?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}
