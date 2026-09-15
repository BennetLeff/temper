//! Evaluate native joints using production PFC currents and one package source.
use anyhow::{ensure, Result};
use std::{env, fs, path::PathBuf};
use zapote_thermal::{joint_model, neck_run::Tools, physical_model};

fn main() -> Result<()> {
    let mut args: Vec<_> = env::args_os().skip(1).collect();
    let replay = args.first().is_some_and(|a| a == "--replay");
    if replay {
        args.remove(0);
    }
    ensure!(args.len()==6,"usage: zapote-joint-model [--replay] SOURCE.json NATIVE.json BOARD.kicad_pcb MANUFACTURING.json SOURCE.pdf NEW_OUTPUT_DIR");
    let source = fs::read_to_string(&args[0])?;
    let native = fs::read(&args[1])?;
    let board = fs::read_to_string(&args[2])?;
    let manufacturing = fs::read(&args[3])?;
    let pfc = zapote_harness::pfc_power::run(
        &source,
        std::str::from_utf8(&native)?,
        &board,
        &serde_json::from_slice(&manufacturing)?,
    )
    .map_err(anyhow::Error::msg)?;
    let waveform = zapote_harness::bridge_thermal::physical_waveform_for_native(
        &pfc,
        &native,
        &manufacturing,
    )?;
    let tool = |key: &str, default: &str| {
        env::var_os(key)
            .map(PathBuf::from)
            .unwrap_or_else(|| default.into())
    };
    let tools = Tools {
        gmsh: tool("GMSH", "/opt/homebrew/bin/gmsh"),
        grid: tool(
            "ELMERGRID",
            "/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerGrid",
        ),
        solver: tool(
            "ELMERSOLVER",
            "/Users/bennet/.local/opt/elmer-26.2.1/bin/ElmerSolver",
        ),
    };
    let out = PathBuf::from(&args[5]);
    if replay {
        let report = joint_model::replay(&out, &native, &manufacturing, &waveform)?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Ok(());
    }
    let report = joint_model::run(
        &PathBuf::from(&args[1]),
        &PathBuf::from(&args[3]),
        &waveform,
        &PathBuf::from(&args[4]),
        &out,
        &tools,
    )?;
    // The reduced legacy network is a GBU-only approximation. The GBJ run
    // already contains its four-diode/case network and must not inherit it.
    if report.gbj_diode_power_w.is_some() {
        println!("{}", serde_json::to_string_pretty(&report)?);
        return Ok(());
    }
    let mut contract = physical_model::contract_from_native(&native, &manufacturing)?;
    contract.loss.source_sha256 = Some(physical_model::REVIEWED_SOURCE_SHA256.into());
    contract.loss.source_status = "byte_archived".into();
    contract.loss.pfc_profile_sha256 = Some(physical_model::waveform_sha256(&waveform)?);
    let approximation =
        physical_model::evaluate_with_source_bytes(&contract, &waveform, &fs::read(&args[4])?)?;
    fs::write(
        out.join("physical-contract.json"),
        serde_json::to_vec_pretty(&contract)?,
    )?;
    fs::write(
        out.join("physical-assessment.json"),
        serde_json::to_vec_pretty(&approximation)?,
    )?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}
