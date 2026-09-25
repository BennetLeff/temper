//! Fault-loop connectivity check CLI.
//!
//! An element can carry current in a declared loop only when at least two of its
//! terminals lie on that loop's nets. This is a necessary connectivity check and
//! nothing more: it does not prove a conductive path, a device state, a current
//! direction, or a current distribution.
//!
//! usage: zapote-fault-loop NETLIST.json --loop-nets A,B,C --assignments ASSIGNMENTS.json
//!
//! Exit 0 when every non-zero assignment is connectivity-consistent, 1 when any
//! is not.
use anyhow::{Context, Result};
use std::{collections::BTreeMap, env, fs, process::ExitCode};
use zapote_erc::fault_loop::{loop_inconsistencies, NetlistEvidence};

fn main() -> Result<ExitCode> {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut netlist: Option<String> = None;
    let mut loop_nets_raw: Option<String> = None;
    let mut assignments: Option<String> = None;
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--loop-nets" => {
                index += 1;
                loop_nets_raw = args.get(index).cloned();
            }
            "--assignments" => {
                index += 1;
                assignments = args.get(index).cloned();
            }
            other => netlist = Some(other.to_string()),
        }
        index += 1;
    }
    let (netlist, loop_nets_raw, assignments) = match (netlist, loop_nets_raw, assignments) {
        (Some(n), Some(l), Some(a)) => (n, l, a),
        _ => anyhow::bail!(
            "usage: zapote-fault-loop NETLIST.json --loop-nets A,B,C --assignments ASSIGNMENTS.json"
        ),
    };

    let evidence: NetlistEvidence = serde_json::from_str(
        &fs::read_to_string(&netlist).context("netlist evidence")?,
    )
    .context("parse netlist evidence")?;
    let assigned: BTreeMap<String, f64> = serde_json::from_str(
        &fs::read_to_string(&assignments).context("assignments")?,
    )
    .context("parse assignments")?;
    let loop_nets: std::collections::BTreeSet<String> = loop_nets_raw
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect();
    anyhow::ensure!(!loop_nets.is_empty(), "no loop nets given");

    let failures = loop_inconsistencies(&evidence, &loop_nets, &assigned);
    if failures.is_empty() {
        println!("FAULT LOOP CONSISTENT (connectivity only; not a conductive-path or distribution claim)");
        Ok(ExitCode::from(0))
    } else {
        println!("FAULT LOOP INCONSISTENT");
        for failure in &failures {
            println!("  - {failure}");
        }
        Ok(ExitCode::from(1))
    }
}
