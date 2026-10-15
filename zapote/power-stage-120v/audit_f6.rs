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
            ("1", format!("{leg}-permit_gate")),
            ("2", "bias_good".into()),
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
    // TPS7A4700 ANY-OUT = 17 V above N (low side only since stage 14). TLVH431 DBZ differs from TL431 DBZ!
    for (base, raw, p, n) in [("bias_ls", "v24_raw", "v15_ls", "n_ls")] {
        for pin in ["1", "3", "20"] {
            add(&format!("{base}.ldo"), pin, p);
        }
        for pin in ["4", "5", "7", "8", "9", "10", "21"] {
            add(&format!("{base}.ldo"), pin, n);
        }
        for pin in ["13", "15", "16"] {
            add(&format!("{base}.ldo"), pin, raw);
        }
        add(&format!("{base}.ldo"), "14", "ldo_nr");
        for (part, a, b) in [("cnr", "ldo_nr", n), ("cin", raw, n), ("cout2", p, n)] {
            add(&format!("{base}.{part}"), "1", a);
            add(&format!("{base}.{part}"), "2", b);
        }
    }
    // Every split: TLVH431 shunt midpoint plus the P-N output caps.
    for (base, p, n, src) in [
        ("bias_ls", "v15_ls", "n_ls", "leg_ret"),
        ("bias_ha.split", "p_ha", "n_ha", "sw_a"),
        ("bias_hb.split", "p_hb", "n_hb", "sw_b"),
    ] {
        add(&format!("{base}.shunt"), "1", &format!("{base}-fb"));
        add(&format!("{base}.shunt"), "2", src);
        add(&format!("{base}.shunt"), "3", n);
        for (part, a, b) in [
            ("rtop", src, format!("{base}-fb")),
            ("rbot", &format!("{base}-fb"), n.into()),
            ("cout1", p, n.into()),
            ("chf", p, n.into()),
        ] {
            add(&format!("{base}.{part}"), "1", a);
            add(&format!("{base}.{part}"), "2", &b);
        }
    }
    // Stage 30 (DECISIONS 33): the window monitors end at the wired-AND 'good' node (rpull to the local 5 V);
    // the notice stage and the per-rail SELV crossing are gone.
    for (base, src, p, n) in [
        ("monitor_ls", "leg_ret", "v15_ls", "n_ls"),
        ("bias_ha.monitor", "sw_a", "p_ha", "n_ha"),
        ("bias_hb.monitor", "sw_b", "p_hb", "n_hb"),
    ] {
        let local = |key: &str| match key {
            "src" => src.into(),
            "p" => p.into(),
            "n" => n.into(),
            // stage 30: the LS monitor's 5 V also feeds the HS links and the heartbeat, so it is named ls_v5
            "v5" if base == "monitor_ls" => "ls_v5".into(),
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
            ("rpull", "v5", "good"),
            ("cldo_in", "p", "n"),
            ("cldo_out", "v5", "n"),
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
            // TPS70950 SOT-23-5: 1 IN, 2 GND, 3 EN, 5 OUT.
            ("ldo5", "1", "p"),
            ("ldo5", "2", "n"),
            ("ldo5", "3", "p"),
            ("ldo5", "5", "v5"),
        ] {
            add(&format!("{base}.{part}"), pin, &local(key));
        }
    }
    // Stage 30: HS-A's verdict crosses to the LS domain through an ISO6721FB (default LOW = not good).
    // D: 1 VCC1, 2 OUTA, 3 INB, 4 GND1, 5 GND2, 6 OUTB, 7 INA, 8 VCC2. Reverse input tied to GND2, OUTA open.
    for (base, n, good) in [("bias_ha", "n_ha", "mon_good_ha")] {
        let v5 = format!("{base}.monitor-v5");
        for (pin, net) in [
            ("1", v5.as_str()),
            ("2", "outa_nc"),
            ("3", &format!("{base}.monitor-good")),
            ("4", n),
            ("5", "n_ls"),
            ("6", good),
            ("7", "n_ls"),
            ("8", "ls_v5"),
        ] {
            add(&format!("{base}.link"), pin, net);
        }
        for (part, a, b) in [("clink1", v5.as_str(), n), ("clink2", "ls_v5", "n_ls")] {
            add(&format!("{base}.{part}"), "1", a);
            add(&format!("{base}.{part}"), "2", b);
        }
    }
    // Stage 30: HS-B's verdict crosses straight to SELV on a default-LOW reinforced isolator (ISO7710F; CA-IS3720LW since stage 31) and gates the heartbeat NAND.
    for (pin, net) in [
        ("1", "n_hb"),
        ("7", "n_hb"),
        ("3", "bias_hb.monitor-v5"),
        ("4", "bias_hb.monitor-good"),
        ("9", "selv_gnd"),
        ("16", "selv_gnd"),
        ("14", "v3v3"),
        ("13", "hsb_good"),
    ] {
        add("bias_hb.verdict", pin, net);
    }
    for (part, a, b) in [("cver1", "bias_hb.monitor-v5", "n_hb"), ("cver2", "v3v3", "selv_gnd")] {
        add(&format!("bias_hb.{part}"), "1", a);
        add(&format!("bias_hb.{part}"), "2", b);
    }
    // Stage 30 heartbeat (f6_bias.ato Heartbeat; FMEA 6a design J). LS: diode-AND vote, gated G132 oscillator,
    // U32 the heartbeat's reinforced crossing; SELV: G132 NAND gated by HS-B's verdict, 220 ohm, 2 x 1 nF series, BAT54S pump, hold.
    for (part, pin, net) in [
        ("vote", "1", "monitor_ls-good"),
        ("vote", "3", "mon_good_ha"),
        ("osc", "1", "monitor_ls-good"),
        ("osc", "2", "hb_rc"),
        ("osc", "3", "n_ls"),
        ("osc", "4", "hb_tx"),
        ("osc", "5", "ls_v5"),
        ("iso", "1", "n_ls"),
        ("iso", "7", "n_ls"),
        ("iso", "3", "ls_v5"),
        ("iso", "4", "hb_tx"),
        ("iso", "9", "selv_gnd"),
        ("iso", "16", "selv_gnd"),
        ("iso", "14", "v3v3"),
        ("iso", "13", "hb_rx"),
        ("buf", "2", "hb_rx"),
        ("buf", "1", "hsb_good"),
        ("buf", "3", "selv_gnd"),
        ("buf", "4", "hb_bufo"),
        ("buf", "5", "v3v3"),
        ("pump", "1", "selv_gnd"),
        ("pump", "3", "hb_x"),
        ("pump", "2", "hb_hold"),
    ] {
        add(&format!("hb.{part}"), pin, net);
    }
    for (part, a, b) in [
        ("rosc", "hb_tx", "hb_rc"),
        ("cosc", "hb_rc", "n_ls"),
        ("cosc_vcc", "ls_v5", "n_ls"),
        ("civcc1", "ls_v5", "n_ls"),
        ("civcc2", "v3v3", "selv_gnd"),
        ("cbuf", "v3v3", "selv_gnd"),
        ("rs", "hb_bufo", "hb_s"),
        ("cp1", "hb_s", "hb_m"),
        ("cp2", "hb_m", "hb_x"),
        ("chold", "hb_hold", "selv_gnd"),
        ("rbleed", "hb_hold", "selv_gnd"),
    ] {
        add(&format!("hb.{part}"), "1", a);
        add(&format!("hb.{part}"), "2", b);
    }
    // Stage 14: one RECOM R24C2T25/R-R per high side (R24C2T25/R Rev.1-2024 p.12 pin map). Primary on
    // V24_RAW / N_LS; secondary P-N single 17 V output (FBVOUT- tied to FBVOUT+, COM and PG open).
    for (base, p, n) in [("bias_ha", "p_ha", "n_ha"), ("bias_hb", "p_hb", "n_hb")] {
        let fbm = format!("{base}-fbm");
        let en = format!("{base}-en");
        add(&format!("{base}.ren_top"), "1", "v24_raw");
        add(&format!("{base}.ren_top"), "2", &en);
        add(&format!("{base}.ren_bot"), "1", &en);
        add(&format!("{base}.ren_bot"), "2", "n_ls");
        for pin in ["1", "2", "5", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18"] {
            add(&format!("{base}.iso"), pin, "n_ls");
        }
        add(&format!("{base}.iso"), "4", &en);
        add(&format!("{base}.iso"), "6", "v24_raw");
        add(&format!("{base}.iso"), "7", "v24_raw");
        for pin in ["19", "20", "21", "22", "23", "24", "25", "26", "27", "30", "31", "36", "35"] {
            add(&format!("{base}.iso"), pin, n);
        }
        add(&format!("{base}.iso"), "28", p);
        add(&format!("{base}.iso"), "29", p);
        add(&format!("{base}.iso"), "33", &fbm);
        add(&format!("{base}.iso"), "34", &fbm);
        for cap in ["cin1", "cin2", "cinhf", "cavin"] {
            add(&format!("{base}.{cap}"), "1", "v24_raw");
            add(&format!("{base}.{cap}"), "2", "n_ls");
        }
        for (part, a, b) in [("rfbt", p, fbm.as_str()), ("rfbb", fbm.as_str(), n), ("cfb", fbm.as_str(), n)] {
            add(&format!("{base}.{part}"), "1", a);
            add(&format!("{base}.{part}"), "2", b);
        }
    }
    for (part, a, b) in [
        ("r1", "l_filt", "r1mid"),
        ("r2", "r1mid", "led1"),
        ("r3", "led2", "r2mid"),
        ("r4", "r2mid", "n_filt"),
        ("pullup", "v3v3", "line_zc_raw"),
        ("cbuffer", "v3v3", "selv_gnd"),
    ] {
        add(&format!("line_zc.{part}"), "1", a);
        add(&format!("line_zc.{part}"), "2", b);
    }
    for (pin, net) in [
        ("1", "led1"),
        ("2", "led2"),
        ("3", "selv_gnd"),
        ("4", "line_zc_raw"),
    ] {
        add("line_zc.opto", pin, net);
    }
    for (pin, net) in [
        ("2", "line_zc_raw"),
        ("3", "selv_gnd"),
        ("4", "line_zc"),
        ("5", "v3v3"),
    ] {
        add("line_zc.buffer", pin, net);
    }
    add("j_selv", "16", "line_zc");
    // Stage 30: U40 is a non-inverting G17 on the heartbeat hold node; it alone drives BIAS_GOOD.
    add("c_bias_flt_vcc", "1", "v3v3");
    add("c_bias_flt_vcc", "2", "selv_gnd");
    for (pin, net) in [("2", "hb_hold"), ("3", "selv_gnd"), ("4", "bias_good"), ("5", "v3v3")] {
        add("u_bias_flt", pin, net);
    }
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
    for base in ["bias_ls"] {
        for pin in ["6", "11", "12"] {
            let path = format!("{base}.ldo");
            if m.net_of(&path, pin)
                .is_some_and(|net| members(m, &net).len() > 1)
            {
                errors.push(format!("{path}.{pin}: unused ANY-OUT bit must float"));
            }
        }
    }
    // Single-output module configuration: COM (32) and PG (3) must stay open.
    for base in ["bias_ha.iso", "bias_hb.iso"] {
        for pin in ["3", "32"] {
            if m.net_of(base, pin).is_some_and(|net| members(m, &net).len() > 1) {
                errors.push(format!("{base}.{pin}: must be left open (single-output module)"));
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
            // stage 21 (DECISIONS 25): the J7-J10 rail-link studs are deleted, BR1 feeds the bus
            if part.path.starts_with("link_pos.") || part.path.starts_with("link_neg.") {
                continue;
            }
            // stage 22 (DECISIONS 27): the PERMIT inverter FET and its 330 ohm pull-up are deleted (DIS NAND)
            if part.path.ends_with(".permit_fet") || part.path.ends_with(".r_dis_pu") {
                continue;
            }
            // stage 30 (DECISIONS 33): notice stages, per-rail crossings, the OR3 and the RC filter are deleted;
            // U32 / C133 / C134 keep their designators under the heartbeat (hb.iso / hb.civcc1 / hb.civcc2)
            if [".rnotice", ".rbase", ".dnotice", ".qnotice", ".iso", ".civcc1", ".civcc2"]
                .iter()
                .any(|suffix| part.path.ends_with(suffix) && part.path.contains("monitor"))
                || ["bias_or", "bias_c_or", "r_bias_flt", "c_bias_flt"].contains(&part.path.as_str())
            {
                continue;
            }
            // stage 38 (candidate 23, DECISIONS 47): PS1 (ps_selv) is deleted; PS1 stays vacant
            if part.path == "ps_selv" {
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
        changed.rewire("line_zc.r2", "2", "line_zc_raw");
        let mut errors = Vec::new();
        audit_f6(&changed, &mut errors);
        assert!(errors.iter().any(|e| e.contains("only line_zc.opto")));
    }
    #[test]
    fn bias_module_single_output_and_pins_are_enforced() {
        // COM tied anywhere breaks the single-output configuration.
        let mut changed = crate::tests::built();
        changed.rewire("bias_ha.iso", "32", "n_ha");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("bias_ha.iso.32")));
        // VOUT+ on the primary ground is a miswire.
        let mut changed = crate::tests::built();
        changed.rewire("bias_hb.iso", "28", "n_ls");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("bias_hb.iso")));
        // The feedback divider must sense P-N of its own side.
        let mut changed = crate::tests::built();
        changed.rewire("bias_ha.rfbt", "1", "p_hb");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("bias_ha.rfbt")));
    }
    #[test]
    fn bias_source_cannot_move_to_selv() {   // stage 38: PS1 / v15_selv are gone; the SELV rail is v3v3
        for (part, pin) in [
            ("bias_ha.iso", "7"),
            ("bias_ls.ldo", "15"),
            ("bias_hb.iso", "6"),
        ] {
            let mut changed = crate::tests::built();
            changed.rewire(part, pin, "v3v3");
            assert!(
                crate::audit(&changed).iter().any(|e| e.contains(part)),
                "{part}"
            );
        }
    }
    #[test]
    fn rail_monitor_crossings_must_be_reinforced_high_cmti_isolators() {
        // Stage 30: the group's SELV crossings are hb.iso (U32, CA-IS3720HW since stage 31) and bias_hb.verdict (U44,
        // CA-IS3720LW);
        // a phototransistor opto fails.
        let mut changed = crate::tests::built();
        changed.set_part("hb.iso", "VO617A-3X017T");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("hb.iso")));
        // The HS verdict crossings must default LOW: the default-HIGH ISO6721B (HS-A) or CA-IS3720HW (HS-B) would read an
        // unpowered HS monitor as 'good' (the masking failure the F options exist to prevent).
        for (path, wrong) in [("bias_ha.link", "ISO6721BDR"), ("bias_hb.verdict", "CA-IS3720HW")] {
            let mut changed = crate::tests::built();
            changed.set_part(path, wrong);
            assert!(crate::audit(&changed).iter().any(|e| e.contains(path)), "{path}");
        }
        // HS-B's verdict must gate the SELV NAND: the gate input tied to V3V3 (the verdict bypassed) fails.
        let mut changed = crate::tests::built();
        changed.rewire("hb.buf", "1", "v3v3");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("hb.buf.1")));
        // The SELV wave taken from the HOT side instead of the isolator output fails.
        let mut changed = crate::tests::built();
        changed.rewire("hb.iso", "13", "hb_tx");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("hb.iso")));
    }
    #[test]
    fn heartbeat_pump_must_stay_ac_coupled() {
        // A static level must never reach the hold node: a pump series cap replaced by a link (0 ohm), or the
        // series pair bridged, fails; so does the hold driven straight from the buffer.
        for cap in ["hb.cp1", "hb.cp2"] {
            let mut changed = crate::tests::built();
            changed.set_part(cap, "0603WAF0000T5E");
            assert!(crate::audit(&changed).iter().any(|e| e.contains(cap)), "{cap}");
        }
        let mut changed = crate::tests::built();
        changed.rewire("hb.cp2", "1", "hb_s");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("hb.cp2")));
        let mut changed = crate::tests::built();
        changed.rewire("u_bias_flt", "2", "hb_bufo");
        assert!(crate::audit(&changed).iter().any(|e| e.contains("u_bias_flt.2")));
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
