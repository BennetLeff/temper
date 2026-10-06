//! Native-21 contracts checked against manufacturer pin tables, not source parsing.
use super::{expect, members, Model};

fn connections() -> Vec<(String, String, String)> {
    let mut rows = Vec::new();
    let mut add = |path: &str, pin: &str, net: &str| {
        rows.push((path.to_owned(), pin.to_owned(), net.to_owned()));
    };
    for (leg, sw, p, n) in [
        ("leg_a", "sw_a", "p_ha", "n_ha"),
        ("leg_b", "sw_b", "p_hb", "n_hb"),
    ] {
        for (pin, net) in [("16", p), ("14", n), ("11", "v15_ls"), ("9", "n_ls")] {
            add(&format!("{leg}.driver"), pin, net);
        }
        for (side, source, positive, negative) in
            [("h", sw, p, n), ("l", "leg_ret", "v15_ls", "n_ls")]
        {
            let bank = format!("{leg}.bias_{side}");
            for cap in [
                "clocal1", "clocal2", "cmid1", "cmid2", "chf1", "chf2", "chf3", "chf4",
            ] {
                add(&format!("{bank}.{cap}"), "1", source);
                add(&format!("{bank}.{cap}"), "2", negative);
            }
            add(&format!("{bank}.rdamp"), "1", source);
            add(&format!("{bank}.rdamp"), "2", &format!("{bank}-damp"));
            add(&format!("{bank}.cbulk"), "1", &format!("{bank}-damp"));
            add(&format!("{bank}.cbulk"), "2", negative);
            add(&format!("{bank}.rbleed"), "1", positive);
            add(&format!("{bank}.rbleed"), "2", source);
            add(
                &format!("{leg}.cgs_{side}"),
                "1",
                &format!("{leg}-gate_{side}"),
            );
            add(&format!("{leg}.cgs_{side}"), "2", source);
            // Nexperia SOD128: pin 2 anode at gate, pin 1 cathode toward 1 ohm.
            add(
                &format!("{leg}.doff_{side}"),
                "2",
                &format!("{leg}-gate_{side}"),
            );
            add(
                &format!("{leg}.doff_{side}"),
                "1",
                &format!("{leg}-off_{side}"),
            );
            add(
                &format!("{leg}.roff_{side}"),
                "1",
                &format!("{leg}-off_{side}"),
            );
            add(
                &format!("{leg}.roff_{side}"),
                "2",
                &format!("{leg}-out_{side}"),
            );
        }
        for (pin, net) in [
            ("1", format!("{leg}-dis")),
            ("2", "bias_bad".into()),
            ("3", "selv_gnd".into()),
            ("4", format!("{leg}-driver_dis")),
            ("5", "v3v3".into()),
        ] {
            add(&format!("{leg}.dis_or"), pin, &net);
        }
        add(&format!("{leg}.r_driver_dis"), "1", "v3v3");
        add(
            &format!("{leg}.r_driver_dis"),
            "2",
            &format!("{leg}-driver_dis"),
        );
        for cap in ["c_ls", "c_ls_bulk"] {
            add(&format!("{leg}.{cap}"), "1", "v15_ls");
            add(&format!("{leg}.{cap}"), "2", "n_ls");
        }
    }
    // TPS7A4700 ANY-OUT = 17 V above N. TLVH431 DBZ differs from TL431 DBZ!
    for (base, raw, p, n, src) in [
        ("bias_ls", "v24_raw", "v15_ls", "n_ls", "leg_ret"),
        ("bias_ha.split", "bias_ha-raw", "p_ha", "n_ha", "sw_a"),
        ("bias_hb.split", "bias_hb-raw", "p_hb", "n_hb", "sw_b"),
    ] {
        for pin in ["1", "3", "20"] {
            add(&format!("{base}.ldo"), pin, p);
        }
        for pin in ["4", "5", "7", "8", "9", "10", "21"] {
            add(&format!("{base}.ldo"), pin, n);
        }
        for pin in ["13", "15", "16"] {
            add(&format!("{base}.ldo"), pin, raw);
        }
        add(&format!("{base}.ldo"), "14", &format!("{base}-nr"));
        add(&format!("{base}.shunt"), "1", &format!("{base}-fb"));
        add(&format!("{base}.shunt"), "2", src);
        add(&format!("{base}.shunt"), "3", n);
        for (part, a, b) in [
            ("rtop", src, format!("{base}-fb")),
            ("rbot", &format!("{base}-fb"), n.into()),
            ("cnr", &format!("{base}-nr"), n.into()),
            ("cin", raw, n.into()),
            ("cout1", p, n.into()),
            ("cout2", p, n.into()),
            ("chf", p, n.into()),
        ] {
            add(&format!("{base}.{part}"), "1", a);
            add(&format!("{base}.{part}"), "2", &b);
        }
    }
    for (base, src, p, n, bad) in [
        ("monitor_ls", "leg_ret", "v15_ls", "n_ls", "bias_ls_bad"),
        ("bias_ha.monitor", "sw_a", "p_ha", "n_ha", "bias_ha_bad"),
        ("bias_hb.monitor", "sw_b", "p_hb", "n_hb", "bias_hb_bad"),
    ] {
        let local = |key: &str| match key {
            "src" => src.into(),
            "p" => p.into(),
            "n" => n.into(),
            _ => format!("{base}-{key}"),
        };
        for (part, a, b) in [
            ("rref", "p", "ref"),
            ("rhalf_top", "ref", "halfref"),
            ("rhalf_bot", "halfref", "n"),
            ("ruv_top", "src", "uv"),
            ("ruv_bot", "uv", "n"),
            ("rov_top", "src", "ov"),
            ("rov_bot", "ov", "n"),
            ("rspanuv_top", "p", "spanuv"),
            ("rspanuv_bot", "spanuv", "n"),
            ("rspanov_top", "p", "spanov"),
            ("rspanov_bot", "spanov", "n"),
            ("rnotice", "ref", "good"),
            ("rbase", "base", "n"),
            ("rled", "p", "leda"),
            ("cuv", "uv", "n"),
            ("cov", "ov", "n"),
            ("cspanuv", "spanuv", "n"),
            ("cspanov", "spanov", "n"),
            ("cmonitor", "p", "n"),
        ] {
            add(&format!("{base}.{part}"), "1", &local(a));
            add(&format!("{base}.{part}"), "2", &local(b));
        }
        // LM339: UV at +, OV at -, all four open collectors in wired-AND.
        for (pin, key) in [
            ("1", "good"),
            ("2", "good"),
            ("3", "p"),
            ("4", "ov"),
            ("5", "halfref"),
            ("6", "halfref"),
            ("7", "uv"),
            ("8", "halfref"),
            ("9", "spanuv"),
            ("10", "spanov"),
            ("11", "halfref"),
            ("12", "n"),
            ("13", "good"),
            ("14", "good"),
        ] {
            add(&format!("{base}.monitor"), pin, &local(key));
        }
        for (part, pin, key) in [
            ("reference", "1", "ref"),
            ("reference", "2", "ref"),
            ("reference", "3", "n"),
            ("dnotice", "2", "good"),
            ("dnotice", "1", "base"),
            ("qnotice", "1", "base"),
            ("qnotice", "2", "n"),
            ("qnotice", "3", "ledk"),
            ("opto", "1", "leda"),
            ("opto", "2", "ledk"),
        ] {
            add(&format!("{base}.{part}"), pin, &local(key));
        }
        add(&format!("{base}.opto"), "3", "selv_gnd");
        add(&format!("{base}.opto"), "4", bad);
        add(&format!("{base}.rbad"), "1", "v3v3");
        add(&format!("{base}.rbad"), "2", bad);
    }
    for (base, n) in [("bias_ha", "n_ha"), ("bias_hb", "n_hb")] {
        for (pin, net) in [
            ("1", "bias_sw1"),
            ("2", "v24_raw"),
            ("3", "v24_raw"),
            ("4", "bias_sw2"),
            ("5", &format!("{base}-sa")),
            ("6", n),
            ("7", n),
            ("8", &format!("{base}-sb")),
        ] {
            add(&format!("{base}.transformer"), pin, net);
        }
        for (part, anode) in [("da", "sa"), ("db", "sb")] {
            add(&format!("{base}.{part}"), "2", &format!("{base}-{anode}"));
            add(&format!("{base}.{part}"), "1", &format!("{base}-rect"));
        }
        add(&format!("{base}.filter"), "1", &format!("{base}-rect"));
        add(&format!("{base}.filter"), "2", &format!("{base}-raw"));
        add(&format!("{base}.craw"), "1", &format!("{base}-raw"));
        add(&format!("{base}.craw"), "2", n);
    }
    for (pin, net) in [
        ("1", "bias_sw1"),
        ("2", "n_ls"),
        ("3", "v24_raw"),
        ("4", "v24_raw"),
        ("6", "sr"),
        ("7", "clk"),
        ("8", "ss"),
        ("9", "n_ls"),
        ("10", "bias_sw2"),
        ("11", "n_ls"),
    ] {
        add("bias_driver", pin, net);
    }
    for (part, net) in [
        ("bias_rclk", "clk"),
        ("bias_rlim", "ss"),
        ("bias_css", "ss"),
        ("bias_rsr", "sr"),
        ("bias_cin", "v24_raw"),
        ("bias_chf", "v24_raw"),
    ] {
        add(part, "1", net);
        add(part, "2", "n_ls");
    }
    for (pin, net) in [
        ("1", "bias_ls_bad"),
        ("2", "selv_gnd"),
        ("3", "bias_ha_bad"),
        ("4", "bias_bad"),
        ("5", "v3v3"),
        ("6", "bias_hb_bad"),
    ] {
        add("bias_or", pin, net);
    }
    for (part, a, b) in [
        ("r1", "l_filt", "r1mid"),
        ("r2", "r1mid", "led1"),
        ("r3", "led2", "r2mid"),
        ("r4", "r2mid", "n_filt"),
        ("pullup", "v3v3", "line_zc-raw"),
        ("cbuffer", "v3v3", "selv_gnd"),
    ] {
        add(&format!("line_zc.{part}"), "1", a);
        add(&format!("line_zc.{part}"), "2", b);
    }
    for (pin, net) in [
        ("1", "led1"),
        ("2", "led2"),
        ("3", "selv_gnd"),
        ("4", "line_zc-raw"),
    ] {
        add("line_zc.opto", pin, net);
    }
    for (pin, net) in [
        ("2", "line_zc-raw"),
        ("3", "selv_gnd"),
        ("4", "line_zc"),
        ("5", "v3v3"),
    ] {
        add("line_zc.buffer", pin, net);
    }
    add("j_selv", "16", "line_zc");
    rows
}

pub(super) fn audit_f6(m: &Model, errors: &mut Vec<String>) {
    for (path, pin, net) in connections() {
        expect(errors, m, &path, &pin, &net);
    }
    for leg in ["leg_a", "leg_b"] {
        for part in ["d_boot", "c_boot", "c_boot_hf"] {
            if m.reff(&format!("{leg}.{part}")).is_some() {
                errors.push(format!("{leg}.{part}: bootstrap must be absent"));
            }
        }
    }
    for base in ["bias_ls", "bias_ha.split", "bias_hb.split"] {
        for pin in ["6", "11", "12"] {
            let path = format!("{base}.ldo");
            if m.net_of(&path, pin)
                .is_some_and(|net| members(m, &net).len() > 1)
            {
                errors.push(format!("{path}.{pin}: unused ANY-OUT bit must float"));
            }
        }
    }
    // Besides exact endpoint checks, reject a newly added line detector part
    // crossing the boundary even if it is not one of today's named resistors.
    let mut sides = std::collections::BTreeMap::<&str, (bool, bool)>::new();
    for (net, nodes) in &m.nets {
        if nodes.len() <= 1 {
            continue;
        }
        for (reference, _) in nodes {
            let flags = sides.entry(reference.as_str()).or_default();
            if super::SELV_NETS.contains(&net.as_str()) {
                flags.1 = true;
            } else {
                flags.0 = true;
            }
        }
    }
    for (reference, component) in &m.comps {
        if component.path.starts_with("line_zc.")
            && component.path != "line_zc.opto"
            && sides.get(reference.as_str()) == Some(&(true, true))
        {
            errors.push(format!(
                "{}: only line_zc.opto may cross line/SELV",
                component.path
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_f6_and_line_connection_rejects_disconnection() {
        let model = crate::tests::built();
        for (path, pin, _) in connections() {
            let mut changed = model.clone();
            changed.rewire(&path, &pin, "mutation_open");
            let mut errors = Vec::new();
            audit_f6(&changed, &mut errors);
            assert!(
                errors.iter().any(|e| e.contains(&format!("{path}.{pin}"))),
                "{path}.{pin}"
            );
        }
    }
    #[test]
    fn every_identity_rejects_a_substituted_part() {
        let model = crate::tests::built();
        for (path, _) in crate::IDENTITY {
            let mut changed = model.clone();
            changed.set_part(path, "WRONG_PART");
            assert!(
                crate::audit(&changed).iter().any(|e| e.contains(path)),
                "{path}"
            );
        }
    }
    #[test]
    fn retained_parts_keep_native20_designators() {
        let old = crate::load(
            include_str!("native-20/frozen/default.net"),
            include_str!("native-20/frozen/default.csv"),
            include_str!("native-20/frozen/resolved-components.json"),
        )
        .unwrap();
        let current = crate::tests::built();
        for (reference, part) in &old.comps {
            if [".d_boot", ".c_boot", ".c_boot_hf"]
                .iter()
                .any(|suffix| part.path.ends_with(suffix))
            {
                continue;
            }
            assert_eq!(
                current.reff(&part.path),
                Some(reference.as_str()),
                "{}",
                part.path
            );
        }
    }
    #[test]
    fn high_sides_cannot_share_the_other_switch_node() {
        for (part, pin) in [("bias_ha.split.shunt", "2"), ("leg_a.bias_h.clocal1", "1")] {
            let mut changed = crate::tests::built();
            changed.rewire(part, pin, "sw_b");
            let mut errors = Vec::new();
            audit_f6(&changed, &mut errors);
            assert!(!errors.is_empty(), "{part}.{pin}");
        }
    }
    #[test]
    fn line_resistor_cannot_cross_to_selv() {
        let mut changed = crate::tests::built();
        changed.rewire("line_zc.r2", "2", "line_zc-raw");
        let mut errors = Vec::new();
        audit_f6(&changed, &mut errors);
        assert!(errors.iter().any(|e| e.contains("only line_zc.opto")));
    }
    #[test]
    fn bias_source_cannot_move_to_ps1() {
        for (part, pin) in [
            ("bias_driver", "3"),
            ("bias_ls.ldo", "15"),
            ("bias_ha.transformer", "2"),
        ] {
            let mut changed = crate::tests::built();
            changed.rewire(part, pin, "v15_selv");
            assert!(
                crate::audit(&changed).iter().any(|e| e.contains(part)),
                "{part}"
            );
        }
    }
    #[test]
    fn rail_bad_cannot_bypass_disable() {
        for leg in ["leg_a", "leg_b"] {
            let mut changed = crate::tests::built();
            changed.rewire(&format!("{leg}.driver"), "5", &format!("{leg}-dis"));
            assert!(crate::audit(&changed)
                .iter()
                .any(|e| e.contains(&format!("{leg}.driver.5"))));
        }
    }
}
