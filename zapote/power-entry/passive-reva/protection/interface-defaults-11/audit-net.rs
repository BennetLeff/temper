//! Local fixture connectivity checks. Resolved instance attributes, not netlist
//! libsource aliases, identify parts. This is not a general ERC implementation.
use std::{collections::BTreeMap, error::Error, fs};

fn main() -> Result<(), Box<dyn Error>> {
    let text = fs::read_to_string("source-candidate/build/default.net")?;
    let mut names = BTreeMap::new();
    for block in text.split("    (comp (ref \"").skip(1) {
        let reference = block.split('"').next().ok_or("missing ref")?;
        let address = block.split("(sheetpath (names \"").nth(1)
            .and_then(|s| s.split('"').next()).ok_or("missing address")?;
        let name = address.split("::").nth(1).ok_or("missing instance name")?;
        names.insert(reference.to_string(), name.to_string());
    }
    assert_eq!(names.len(), 136);
    let mut pins = BTreeMap::new();
    for (index, block) in text.split("    (net (code ").skip(1).enumerate() {
        for line in block.lines().filter(|line| line.contains("(node (ref")) {
            let fields: Vec<_> = line.split('"').collect();
            let name = names.get(fields[1]).ok_or("unknown node ref")?;
            let pin = format!("{name}.{}", fields[3]);
            assert!(pins.insert(pin, index).is_none(), "pin appears twice");
        }
    }
    let net = |name: &str| *pins.get(name).unwrap_or_else(|| panic!("missing pin {name}"));
    let groups: &[&[&str]] = &[
        &["protection.permit_input_pd.1", "protection.permit_buf.2"],
        &["protection.arm_input_pd.1", "protection.arm_buf.2"],
        &["protection.permit_input_pd.2", "protection.arm_input_pd.2", "protection.aux_window_and.3", "protection.aux_fast_cmp.4", "protection.aux_ov_bottom.2", "protection.aux_window_bypass.2"],
        &["protection.aux_window_and.5", "protection.aux_fast_cmp.8", "protection.aux_window_bypass.1"],
        &["protection.aux_ov_top.1", "protection.aux_fast_top.1"],
        &["protection.aux_ov_top.2", "protection.aux_ov_bottom.1", "protection.aux_ov_iso.1"],
        &["protection.aux_ov_iso.2", "protection.aux_fast_cmp.6"],
        &["protection.aux_ov_ref.2", "protection.aux_fast_cmp.5"],
        &["protection.aux_ov_ref.1", "protection.aux_fast_cmp.2"],
        &["protection.aux_fast_cmp.1", "protection.aux_window_and.1"],
        &["protection.aux_fast_cmp.7", "protection.aux_window_and.2"],
        &["protection.aux_window_and.4", "protection.health.13"],
        &["protection.sup_logic.6", "protection.sup_aux.6", "protection.reset_pull_aux.2", "protection.rail_pd.1"],
    ];
    for group in groups {
        for pin in *group {
            assert_eq!(net(group[0]), net(pin), "disconnected {pin}");
        }
    }
    let separate = ["protection.aux_fast_cmp.1", "protection.aux_fast_cmp.7", "protection.aux_window_and.4", "protection.sup_logic.6"];
    for (i, a) in separate.iter().enumerate() {
        for b in &separate[i + 1..] {
            assert_ne!(net(a), net(b), "shorted outputs {a} {b}");
        }
    }
    assert_ne!(net("protection.permit_buf.2"), net("protection.permit_buf.4"));
    assert_ne!(net("protection.arm_buf.2"), net("protection.arm_buf.4"));
    for group in groups {
        let members: Vec<_> = pins.iter().filter(|(_, n)| **n == net(group[0]))
            .map(|(name, _)| name.as_str()).collect();
        println!("{}", members.join(", "));
    }
    println!("PASS: 136 instances; 13 connectivity groups; distinct comparator, window and RESET outputs; raw input bias.");
    Ok(())
}
