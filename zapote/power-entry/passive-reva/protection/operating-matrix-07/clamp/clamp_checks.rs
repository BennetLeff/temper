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

fn comp_block<'a>(net: &'a str, refdes: &str) -> &'a str {
    net.split("    (comp ")
        .find(|block| block.contains(&format!("(ref \"{refdes}\")")))
        .unwrap_or_else(|| panic!("missing component {refdes}"))
}

fn net_block<'a>(net: &'a str, name: &str) -> &'a str {
    net.split("    (net ")
        .find(|block| block.contains(&format!("(name \"{name}\")")))
        .unwrap_or_else(|| panic!("missing net {name}"))
}

fn temperature_rows(text: &str) -> Vec<(f64, f64, f64)> {
    let mut rows = Vec::new();
    let mut temp = None;
    let mut isense = None;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("Doing analysis at TEMP =") {
            temp = trimmed
                .split_whitespace()
                .nth(5)
                .and_then(|v| v.parse::<f64>().ok());
        } else if trimmed.starts_with("v(isense) =") {
            isense = trimmed
                .split('=').nth(1)
                .and_then(|v| v.trim().parse::<f64>().ok());
        } else if trimmed.starts_with("@dclamp[id] =") {
            let current = trimmed
                .split('=').nth(1)
                .and_then(|v| v.trim().parse::<f64>().ok());
            if let (Some(t), Some(v), Some(i)) = (temp, isense, current) {
                rows.push((t, v, i));
            }
            isense = None;
        }
    }
    rows
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 8 {
        eprintln!("usage: clamp_checks <net> <csv> <pcl.log> <negative.log> <reversed.log> <pcl-temp.log> <negative-temp.log>");
        return ExitCode::from(2);
    }
    let net = fs::read_to_string(&args[1]).expect("read netlist");
    let csv = fs::read_to_string(&args[2]).expect("read BOM");
    let pcl = fs::read_to_string(&args[3]).expect("read PCL log");
    let negative = fs::read_to_string(&args[4]).expect("read negative log");
    let reversed = fs::read_to_string(&args[5]).expect("read reversed log");
    let pcl_temp = fs::read_to_string(&args[6]).expect("read PCL temperature log");
    let negative_temp = fs::read_to_string(&args[7]).expect("read negative temperature log");

    // Export identity and physical pin graph.  Atopile emits control_gnd as
    // the resolved PFC_BUS_MINUS net in this source entry.
    assert_eq!(csv.lines().filter(|line| line.starts_with("BAV23C-E3-08,U35,")).count(), 1);
    assert!(comp_block(&net, "U35").contains("(footprint \"Package_TO_SOT_SMD:SOT-23\")"));
    assert!(net_block(&net, "PFC_BUS_MINUS").contains("U35") && net_has_node(net_block(&net, "PFC_BUS_MINUS"), "U35", "1"));
    assert!(net_has_node(net_block(&net, "isense"), "U35", "3"));
    let unused = net_block(&net, "a_unused");
    assert!(net_has_node(unused, "U35", "2"));
    assert_eq!(unused.matches("(node ").count(), 1, "unused anode is not exactly NC");
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

    // Temperature sensitivity is reported against a deliberately chosen
    // loading screen (1 uA and 2 mV), not a datasheet requirement.  Do not
    // tune the assumed model to make this green: retain failures explicitly.
    let mut temp_failures = 0;
    let pcl_rows = temperature_rows(&pcl_temp);
    let negative_rows = temperature_rows(&negative_temp);
    assert_eq!(pcl_rows.len(), 4, "expected four PCL temperature rows");
    assert_eq!(negative_rows.len(), 4, "expected four negative temperature rows");
    for (temp, v, i) in pcl_rows {
        let delta_mv = (v + 0.438).abs() * 1000.0;
        let ok = i.abs() < 1e-6 && delta_mv < 2.0;
        println!("TEMP_SCREEN PCL {temp:.0}C: {} (isense={v:.6} V, id={i:.3e} A, delta={delta_mv:.3} mV)", if ok { "PASS" } else { "FAIL" });
        if !ok { temp_failures += 1; }
    }
    for (temp, v, i) in negative_rows {
        let ok = v > -1.1;
        println!("TEMP_SCREEN NEGATIVE {temp:.0}C: {} (isense={v:.6} V, id={i:.6} A)", if ok { "PASS" } else { "FAIL" });
        if !ok { temp_failures += 1; }
    }

    println!(
        "PASS graph; pcl_isense={pcl_isense:.6} V pcl_diode={pcl_i:.3e} A; \
         negative_isense={isense:.6} V negative_diode={diode_i:.6} A; \
         reversed_isense={reversed_isense:.3} V (expected fail)"
    );
    if temp_failures == 0 { ExitCode::SUCCESS } else { ExitCode::from(1) }
}
