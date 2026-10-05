//! Source-derived prototype board partition. No shared placer code is replaced.
use std::{collections::BTreeMap, fs, path::Path};
fn connector(rows: &mut Vec<Vec<String>>, name: &str, nets: &[&str], sheet: &str) {
    let n = nets.len();
    let fp = format!("Connector_JST:JST_XH_B{n}B-XH-A_1x{n:02}_P2.50mm_Vertical");
    for (i, net) in nets.iter().enumerate() {
        rows.push(vec![
            name.into(),
            format!("B{n}B-XH-A(LF)(SN)"),
            fp.clone(),
            sheet.into(),
            (i + 1).to_string(),
            (i + 1).to_string(),
            "passive".into(),
            (*net).into(),
        ]);
    }
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = Path::new(file!()).parent().unwrap();
    let src = out.join("../../round4/supervisor/generated/pins.tsv");
    let text = fs::read_to_string(&src)?;
    let rows: Vec<Vec<String>> = text
        .lines()
        .skip(1)
        .map(|l| l.split('\t').map(str::to_owned).collect())
        .collect();
    let mut central = Vec::new();
    let mut excluded = Vec::new();
    for mut r in rows.clone() {
        if ["VLINE", "VPRE", "VOUT", "VBUS", "VCATCH", "VTANK", "MAINS"].contains(&r[3].as_str())
            || r[0].starts_with("CT_")
            || r[0].starts_with("NTC")
            || r[0] == "REG5"
            || r[0].ends_with("B1") && r[0].starts_with("R_I")
            || r[0].ends_with("B2") && r[0].starts_with("R_I")
            || r[0].starts_with("TVS_I")
        {
            excluded.push(r);
            continue;
        }
        if r[2].starts_with("REVIEW_ONLY:") {
            let n = rows.iter().filter(|x| x[0] == r[0]).count();
            if r[1].starts_with("1725669") {
                r[2]="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1-2-3.81_1x02_P3.81mm_Horizontal".into();
            } else {
                r[1] = format!("B{n}B-XH-A(LF)(SN)");
                r[2] = format!("Connector_JST:JST_XH_B{n}B-XH-A_1x{n:02}_P2.50mm_Vertical");
            }
        }
        // R5 ECO: >=10 mA preload at the LD1117 valid 4.75 V lower input bound.
        if r[0] == "R_MINLOAD" {
            r[1] = "470R 0.1% TNPW1206470RBEEA".into();
        }
        central.push(r);
    }
    connector(&mut central, "J_AUX24", &["AUX_24V", "AUX_0V"], "POWER");
    connector(
        &mut central,
        "J_REG5",
        &["AUX_24V", "AUX_0V", "POD_5V"],
        "POWER",
    );
    for name in ["K1", "K2", "KB"] {
        connector(
            &mut central,
            &format!("J_{name}"),
            &[
                &format!("{name}_COIL_HIGH"),
                &format!("{name}_COIL_LOW"),
                &format!("{name}_FB_EXC"),
                &format!("{name}_MIRROR_RAW"),
            ],
            "COILS",
        );
    }
    connector(
        &mut central,
        "J_KT",
        &["POD_24V_ACT", "KT_COIL_LOW"],
        "COILS",
    );
    for name in ["VLINE", "VPRE", "VOUT", "VBUS", "VTANK"] {
        connector(
            &mut central,
            &format!("J_{name}_POD"),
            &[
                "POD_3V3",
                "AUX_0V",
                &format!("{name}_P"),
                &format!("{name}_N"),
                &format!("{name}_DIAG_N"),
                "AUX_0V",
            ],
            "ADC",
        );
    }
    for name in ["IPROOF", "ILINE"] {
        connector(
            &mut central,
            &format!("J_{name}_BURDEN"),
            &[&format!("{name}_RAW"), "REF_1V25"],
            "CURRENT",
        );
    }
    let mut count: BTreeMap<char, usize> = BTreeMap::new();
    let mut map = BTreeMap::new();
    for r in &central {
        if !map.contains_key(&r[0]) {
            let k = if r[0].starts_with("REG") {
                'U'
            } else {
                r[0].chars().next().unwrap()
            };
            let num = count.entry(k).or_default();
            *num += 1;
            map.insert(r[0].clone(), format!("{k}{num}"));
        }
    }
    let mut data =
        "reference\tmpn\tfootprint\tsheet\tpin\tfunction\ttype\tnet\tsource_ref\n".to_owned();
    for r in central {
        let mut rr = r.clone();
        rr[0] = map[&r[0]].clone();
        rr.push(r[0].clone());
        data.push_str(&rr.join("\t"));
        data.push('\n');
    }
    fs::create_dir_all(out.join("central/generated"))?;
    fs::write(out.join("central/generated/pins.tsv"), data)?;
    let mut ext = text.lines().next().unwrap().to_owned() + "\n";
    for r in excluded {
        ext.push_str(&r.join("\t"));
        ext.push('\n');
    }
    fs::write(out.join("external-pins.tsv"), ext)?;
    let mut refs = "source_ref\tboard_ref\n".to_owned();
    for (a, b) in map {
        refs.push_str(&format!("{a}\t{b}\n"));
    }
    fs::write(out.join("central/ref-map.tsv"), refs)?;
    println!("Central board pin capture emitted; external rows retained separately");
    Ok(())
}
