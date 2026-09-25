//! Rust-owned acceptance checks for the bounded ISENSE clamp experiment.
//!
//! The SPICE logs are transport artifacts.  This binary parses their retained
//! values and makes the numerical verdict; it deliberately does not claim a
//! production temperature or transient qualification.

use std::{env, fs, process::ExitCode};

fn value_after_line(text: &str, key: &str) -> f64 {
    text.lines()
        .find(|line| line.trim_start().starts_with(key))
        .and_then(|line| line.split_whitespace().last())
        .and_then(|v| v.parse::<f64>().ok())
        .unwrap_or_else(|| panic!("missing numeric line {key:?}"))
}

fn device_value(text: &str, device: &str, key: &str) -> f64 {
    let mut in_device = false;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("device ") {
            in_device = trimmed.split_whitespace().nth(1) == Some(device);
        } else if in_device && trimmed.starts_with(key) {
            return trimmed
                .split_whitespace()
                .last()
                .and_then(|v| v.parse::<f64>().ok())
                .unwrap_or_else(|| panic!("bad {device}.{key} line"));
        }
    }
    panic!("missing device value {device}.{key}");
}

fn net_has_node(block: &str, refdes: &str, pin: &str) -> bool {
    block.contains(&format!("(ref \"{refdes}\") (pin \"{pin}\")"))
}

fn net_block<'a>(net: &'a str, name: &str) -> &'a str {
    net.split("    (net ")
        .find(|block| block.contains(&format!("(name \"{name}\")")))
        .unwrap_or_else(|| panic!("missing net {name}"))
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 6 {
        eprintln!("usage: clamp_checks <net> <csv> <pcl.log> <negative.log> <reversed.log>");
        return ExitCode::from(2);
    }
    let net = fs::read_to_string(&args[1]).expect("read netlist");
    let csv = fs::read_to_string(&args[2]).expect("read BOM");
    let pcl = fs::read_to_string(&args[3]).expect("read PCL log");
    let negative = fs::read_to_string(&args[4]).expect("read negative log");
    let reversed = fs::read_to_string(&args[5]).expect("read reversed log");

    // Export identity and physical pin graph.  Atopile emits control_gnd as
    // the resolved PFC_BUS_MINUS net in this source entry.
    assert!(csv.lines().any(|line| line.starts_with("BAV23C-E3-08,U35,")));
    assert!(net.contains("(footprint \"Package_TO_SOT_SMD:SOT-23\")"));
    assert!(net_block(&net, "PFC_BUS_MINUS").contains("U35") && net_has_node(net_block(&net, "PFC_BUS_MINUS"), "U35", "1"));
    assert!(net_has_node(net_block(&net, "isense"), "U35", "3"));
    assert!(net_has_node(net_block(&net, "a_unused"), "U35", "2"));
    assert!(net_has_node(net_block(&net, "isense"), "U18", "1"));
    assert!(net_has_node(net_block(&net, "minus"), "U18", "2"));

    // PCL preservation around -0.438 V: no meaningful clamp current and no
    // more than 2 mV change in the controller-side node.
    let pcl_shunt = value_after_line(&pcl, "shunt");
    let pcl_isense = value_after_line(&pcl, "isense");
    let pcl_i = device_value(&pcl, "dclamp", "id");
    assert!((pcl_shunt + 0.438).abs() < 1e-9);
    assert!((pcl_isense - pcl_shunt).abs() < 0.002);
    assert!(pcl_i.abs() < 1e-6, "PCL clamp current {pcl_i} A");

    // Negative excursion: the post-220-ohm clamp keeps ISENSE above -1.1 V.
    // The current is checked against the actual resistor formula, not treated
    // as an unconditional 5 mA bound.
    let shunt = value_after_line(&negative, "shunt");
    let isense = value_after_line(&negative, "isense");
    let diode_i = device_value(&negative, "dclamp", "id");
    let expected_i = (isense - shunt) / 220.0;
    assert!(shunt < -1.0 && isense > -1.1 && isense < -0.8);
    assert!(diode_i > 0.015 && diode_i < 0.025);
    assert!((diode_i - expected_i).abs() < 1e-4);

    // Removed/reversed polarity is deliberately expected to fail the pin
    // minimum, demonstrating that the correction is causally exercised.
    let reversed_isense = value_after_line(&reversed, "isense");
    assert!(reversed_isense < -1.1);

    println!(
        "PASS graph; pcl_isense={pcl_isense:.6} V pcl_diode={pcl_i:.3e} A; \
         negative_isense={isense:.6} V negative_diode={diode_i:.6} A; \
         reversed_isense={reversed_isense:.3} V (expected fail)"
    );
    ExitCode::SUCCESS
}
