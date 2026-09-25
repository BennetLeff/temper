//! Read pcbnew-measured rectangles from stdin and emit deterministic shelf poses.

use anyhow::{Context, Result};
use std::io::{self, Read};
use zapote_core::shelf::{pack, ShelfInput};

fn main() -> Result<()> {
    let mut payload = String::new();
    io::stdin()
        .read_to_string(&mut payload)
        .context("reading shelf input")?;
    let input: ShelfInput = serde_json::from_str(&payload).context("parsing shelf input")?;
    let result = pack(input).map_err(anyhow::Error::msg)?;
    serde_json::to_writer(io::stdout(), &result).context("writing shelf poses")?;
    Ok(())
}
