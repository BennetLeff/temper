//! Standalone cross-unit memory judge (P2).
//!
//! Thin stdin/stdout bridge over `memory.rs` so the Python host can call
//! the Rust selection/validation policy without carrying a duplicate
//! policy. P1 later registers `memory` in the main dispatcher
//! (`src/main.rs`); this bridge is then the test/transition path, not a
//! second authority. It deliberately does not touch `main.rs`,
//! `workspace.py`, or any shared runtime file.

#[path = "../memory.rs"]
mod memory;

use serde_json::Value;
use std::io::{self, Read};

fn run() -> Result<Value, anyhow::Error> {
    let mut input_text = String::new();
    io::stdin()
        .lock()
        .read_to_string(&mut input_text)
        .map_err(|e| anyhow::anyhow!("read stdin: {e}"))?;
    let raw: Value =
        serde_json::from_str(&input_text).map_err(|e| anyhow::anyhow!("invalid JSON: {e}"))?;
    // Reject duplicate keys the way continual.rs does is unnecessary here:
    // memory commands carry hashes the policy re-verifies, and the host
    // canonicalizes. Keep strict object shapes per command instead.
    Ok(match memory::dispatch(raw.clone()) {
        Ok(result) => result,
        Err(error) => memory::error_response(Some(&raw), &error),
    })
}

fn main() {
    match run() {
        Ok(result) => {
            println!("{result}");
            if result.get("status").and_then(Value::as_str) != Some("pass") {
                std::process::exit(1);
            }
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::json!({"schema":memory::SCHEMA,"command":"unknown","status":"indeterminate","error":format!("{error:#}")})
            );
            std::process::exit(2);
        }
    }
}
