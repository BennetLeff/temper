//! Expected-negative source graph check for the retained pre-fix export.
//! The old polarity must not satisfy the corrected graph contract.
use std::{env, fs, process::ExitCode};

fn block<'a>(net: &'a str, name: &str) -> &'a str {
    net.split("    (net ")
        .find(|b| b.contains(&format!("(name \"{name}\")")))
        .unwrap_or_else(|| panic!("missing net {name}"))
}
fn has(b: &str, pin: &str) -> bool {
    b.contains(&format!("(ref \"U35\") (pin \"{pin}\")"))
}
fn main() -> ExitCode {
    let path = env::args().nth(1).expect("pre-fix netlist path");
    let net = fs::read_to_string(path).expect("read pre-fix netlist");
    let old_ground = block(&net, "PFC_BUS_MINUS");
    let old_shunt = block(&net, "minus");
    let old_isense = block(&net, "isense");
    let expected_negative = has(old_ground, "1") && has(old_shunt, "2") && !has(old_isense, "1") && !has(old_isense, "3");
    assert!(expected_negative, "pre-fix source unexpectedly satisfies corrected graph");
    println!("PASS expected-negative pre-fix graph: U35 pin1 ground, pin2 shunt, no isense node");
    ExitCode::SUCCESS
}
