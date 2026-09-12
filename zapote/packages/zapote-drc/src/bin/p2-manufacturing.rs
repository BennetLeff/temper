use std::{env, fs};
use zapote_drc::manufacturing::{validate, ManufacturingInput};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = env::args().nth(1).ok_or("usage: p2-manufacturing INPUT.json")?;
    let input: ManufacturingInput = serde_json::from_slice(&fs::read(path)?)?;
    println!("{}", serde_json::to_string_pretty(&validate(&input))?);
    Ok(())
}
