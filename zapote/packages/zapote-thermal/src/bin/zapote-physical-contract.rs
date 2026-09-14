//! Build a bridge physical-model contract from native and manufacturing captures.
//!
//! Keeping this conversion in the Rust crate makes the generated contract use
//! the same strict importer and geometry fingerprint as replay. The command
//! intentionally does not infer a manufacturer source identity; source bytes
//! are added only by a reviewed evidence workflow.

use anyhow::{bail, Context, Result};
use std::{env, fs, path::Path};
use zapote_thermal::physical_model::contract_from_native;

fn main() -> Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    let [native, manufacturing, output] = args.as_slice() else {
        bail!("usage: zapote-physical-contract NATIVE_JSON MANUFACTURING_JSON OUTPUT_JSON");
    };
    let native_bytes = fs::read(native).with_context(|| format!("read native capture {native}"))?;
    let manufacturing_bytes = fs::read(manufacturing)
        .with_context(|| format!("read manufacturing capture {manufacturing}"))?;
    let contract = contract_from_native(&native_bytes, &manufacturing_bytes)?;
    let json = serde_json::to_vec_pretty(&contract)?;
    fs::write(Path::new(output), json)
        .with_context(|| format!("write physical-model contract {output}"))?;
    println!(
        "built {}: board={} geometry={} paths={}",
        output,
        contract.board_sha256,
        contract.geometry_sha256.as_deref().unwrap_or("MISSING"),
        contract.paths.len()
    );
    Ok(())
}
