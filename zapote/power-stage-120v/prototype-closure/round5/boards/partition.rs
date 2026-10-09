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
fn part(rows: &mut Vec<Vec<String>>, name: &str, mpn: &str, fp: &str, sheet: &str, pins: &[(&str,&str,&str,&str)]) {
    for (pin,function,kind,net) in pins {
        rows.push(vec![name.into(),mpn.into(),fp.into(),sheet.into(),(*pin).into(),(*function).into(),(*kind).into(),(*net).into()]);
    }
}
fn passive(rows:&mut Vec<Vec<String>>,name:&str,mpn:&str,fp:&str,a:&str,b:&str) {
    part(rows,name,mpn,fp,"FEEDBACK",&[("1","1","passive",a),("2","2","passive",b)]);
}
fn logic(rows:&mut Vec<Vec<String>>,name:&str,a:&str,b:Option<&str>,y:&str) {
    let inv=b.is_none();
    part(rows,name,if inv {"SN74LVC1G04DBVR"} else {"SN74LVC1G08DBVR"},"Package_TO_SOT_SMD:SOT-23-5","HARDWARE",
        &[("1",if inv {"NC"} else {"A"},if inv {"no_connect"} else {"input"},if inv {"NC"} else {a}),
        ("2",if inv {"A"} else {"B"},"input",b.unwrap_or(a)),("3","GND","power_in","AUX_0V"),
        ("4","Y","output",y),("5","VCC","power_in","POD_3V3")]);
    passive(rows,&format!("C_{name}"),"100nF C0603C104K5RACAUTO","Capacitor_SMD:C_0603_1608Metric","POD_3V3","AUX_0V");
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
        for k in ["K1","K2","KB"] {
            if r[0] == k && r[4] == "21" { r[7]="AUX_24V".into(); }
            if r[0] == k && r[4] == "22" { r[7]=format!("{k}_MIRROR_24V"); }
        }
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
        // REG5 load-regulation specification starts at10% of500mA.
        if r[0] == "R_MINLOAD" {
            r[1] = "82R 1% CRCW251282R0FKEG 1W".into();
            r[2] = "Resistor_SMD:R_2512_6332Metric".into();
        }
        // Proof window accommodates initial line-cycle measurement and 50ms dwell.
        if r[0] == "R_UT_PROOFSET" {
            r[1] = "191kR 0.1% TNPW0603191KBEEA".into();
        }
        // Direct 24 V conversion removes the 3.3 V load and LDO heat from REG5.
        if r[0] == "REG3" {
            r[1] = "R-78B5.0-1.0".into();
            r[2] = "Converter_DCDC:Converter_DCDC_RECOM_R-78HB-0.5_THT".into();
            let (function, kind, net) = match r[4].as_str() {
                "1" => ("VIN", "power_in", "AUX_24V"),
                "2" => ("GND", "power_in", "AUX_0V"),
                "3" => ("VOUT", "power_out", "REG3_5V"),
                _ => panic!("REG3 pin outside manufacturer SIP3 pinout"),
            };
            r[5] = function.into();
            r[6] = kind.into();
            r[7] = net.into();
        }
        if r[0] == "C3IN" {
            r[1] = "1uF C1206C105K5RAC 50V".into();
            if r[4] == "1" { r[7] = "AUX_24V".into(); }
        }
        if r[0] == "U_MCU" && r[4] == "36" {
            r[7] = "ADC_MCO_SOURCE".into();
        }
        // J7 is now a passive clock monitor. No independent oscillator is fitted.
        if r[0] == "J_CLK" && r[4] == "3" {
            r[5] = "ADC_CLK_MONITOR_ONLY".into();
        }
        if r[7] == "AUX_0V" && ["Q_K1", "Q_K2", "Q_KB", "Q_KT", "R_K1GS", "R_K2GS", "R_KBGS", "R_KTGS"].contains(&r[0].as_str()) {
            r[7] = "COIL_RET".into();
        }
        for k in ["K1","K2","KB"] {
            if r[0] == format!("R_{k}FB") {
                r[1]="100kR CRCW0603100KFKEA".into();
                if r[4]=="1" {r[7]=format!("{k}_MIRROR");}
            }
            if r[0] == format!("R_{k}FB_SER") {
                r[1]="562R CRCW0603562RFKEA".into();
                r[7]=if r[4]=="1" {format!("{k}_MIRROR_24V")}else{format!("{k}_FB_IN")};
            }
        }
        if r[0]=="U_MCU" {
            let new = match r[4].as_str() {"40"=>Some("CMD_KPA"),"41"=>Some("CMD_KPB"),"3"=>Some("KPA_MIRROR"),
                "4"=>Some("KPB_MIRROR"),"44"=>Some("KPA_FB_EXC"),"47"=>Some("KPB_FB_EXC"),"5"=>Some("ADMIT"),_=>None};
            if let Some(n)=new {r[7]=n.into();}
        }
        if r[0]=="U_RUN5" && r[4]=="4" {r[7]="PRE_ISO_RUN_OK".into();}
        let revised = match (r[0].as_str(), r[4].as_str()) {
            ("U_ATTEMPT","2")=>Some("ATTEMPT_D"),("U_ATTEMPT","3")=>Some("ADMIT"),
            ("U_PROOF_ONCE","1")=>Some("TOKEN_CLEAR_N"),("U_PROOF_ONCE","2")=>Some("TOKEN_ARM_VALID"),
            ("U_PROOF_ONCE","3")=>Some("START_QUALIFIED"),("U_PROOF_ONCE","5")=>Some("START_TOKEN"),
            ("UT_PROOF","1")=>Some("PROOF_REQUEST"),("U_BUDGET1","2")=>Some("SESSION_BUDGET_OK"),
            ("U_RUN3","2")=>Some("RUNTIME_HEALTHY"),("U_RUN_ARM","3")=>Some("SUP_RUN_OK_LOCAL"),
            ("U_RUN_ARM","1")=>Some("FINAL_PROOF_CLEAR_N"),
            ("U_K1HI1","1") | ("U_K2HI1","1")=>Some("SOURCE_DRIVE_TIMED"),
            ("U_PROVEN","1")=>Some("FINAL_PROOF_CLEAR_N"),("U_PROVEN","2")=>Some("FINAL_PROOF_VALID"),_=>None};
        if let Some(n)=revised {r[7]=n.into();}
        // TI SCES794G p4, DCU: CLK1, D2, /Q3, GND4, Q5, /CLR6, /PRE7, VCC8.
        // Historical capture used logical pin labels with the wrong physical numbers.
        // Apply after logical ECOs so function/type/net move together to the real pad.
        if r[1] == "SN74LVC1G74DCUR" {
            r[4] = match r[4].as_str() {"1"=>"6", "3"=>"1", "6"=>"3", p=>p}.into();
        }

        // Vishay April2026:0.1%0603range ends332k; preserve value/tolerance inlargerpackage.
        if r[1].contains("TNPW0603") {
            let token=r[1].split_whitespace().next().unwrap().trim_end_matches('R');
            let ohms=if let Some(v)=token.strip_suffix('M') {v.parse::<f64>().unwrap()*1e6}
                else if let Some(v)=token.strip_suffix('k') {v.parse::<f64>().unwrap()*1e3}
                else {token.parse::<f64>().unwrap()};
            if ohms>332000.0 {
                let package=if ohms<=1e6 {"0805"}else{"1206"};
                assert!(ohms<=2e6,"TNPW resistor exceeds selectedseriesrange");
                r[1]=r[1].replace("TNPW0603",&format!("TNPW{package}"));
                r[2]=if package=="0805" {"Resistor_SMD:R_0805_2012Metric".into()}else{"Resistor_SMD:R_1206_3216Metric".into()};
            }
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
                "AUX_24V",
                &format!("{name}_MIRROR_24V"),
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
    // Append ECO parts so existing board reference identities remain stable.
    for (name, mpn, a, b, sheet) in [
        ("R_HB_FAIL_LOW", "10kR CRCW060310K0FKEA", "CTRL_HEARTBEAT_OK", "AUX_0V", "HARDWARE"),
        ("R_ADC_MCO", "33R CRCW060333R0FKEA", "ADC_MCO_SOURCE", "ADC_CLKIN", "MCU"),
        ("R_REG3_PRELOAD", "300R 0.1% TNPW1206300RBEEA", "POD_3V3", "AUX_0V", "POWER"),
    ] {
        for (pin, net) in [("1", a), ("2", b)] {
            central.push(vec![name.into(), mpn.into(),
                if name == "R_REG3_PRELOAD" { "Resistor_SMD:R_1206_3216Metric".into() }
                else { "Resistor_SMD:R_0603_1608Metric".into() },
                sheet.into(), pin.into(), pin.into(), "passive".into(), net.into()]);
        }
    }
    for (pin, net) in [("1", "COIL_RET"), ("2", "AUX_0V")] {
        central.push(vec!["NT_COIL_STAR".into(), "PCB copper star 2mm".into(),
            "NetTie:NetTie-2_SMD_Pad2.0mm".into(), "POWER".into(),
            pin.into(), pin.into(), "passive".into(), net.into()]);
    }
    // TPS7A4700 ANY-OUT:1.4+1.6+0.2+0.1=3.3V. Unused selectors float.
    for (pin, function, kind, net) in [
        ("1","OUT","power_out","POD_3V3"),("2","NC","no_connect","NC"),
        ("3","SENSE","input","POD_3V3"),("4","6P4V2","input","NC"),
        ("5","6P4V1","input","NC"),("6","3P2V","input","NC"),
        ("7","GND","power_in","AUX_0V"),("8","1P6V","input","AUX_0V"),
        ("9","0P8V","input","NC"),("10","0P4V","input","NC"),
        ("11","0P2V","input","AUX_0V"),("12","0P1V","input","AUX_0V"),
        ("13","EN","input","REG3_5V"),("14","NR","passive","REG3_NR"),
        ("15","IN","power_in","REG3_5V"),("16","IN","power_in","REG3_5V"),
        ("17","NC","no_connect","NC"),("18","NC","no_connect","NC"),
        ("19","NC","no_connect","NC"),("20","OUT_COMMON","passive","POD_3V3"),
        ("21","EP","power_in","AUX_0V"),
    ] {
        central.push(vec!["U_POSTREG".into(),"TPS7A4700RGWR".into(),
            "Package_DFN_QFN:Texas_RGW0020A_VQFN-20-1EP_5x5mm_P0.65mm_EP3.15x3.15mm".into(),
            "POWER".into(),pin.into(),function.into(),kind.into(),net.into()]);
    }
    for (name, net) in [("C_POSTIN1","REG3_5V"),("C_POSTIN2","REG3_5V"),
        ("C_POSTOUT1","POD_3V3"),("C_POSTOUT2","POD_3V3"),("C_POSTOUT3","POD_3V3"),("C_POSTNR","REG3_NR")] {
        for (pin, n) in [("1",net),("2","AUX_0V")] {
            let nr=name=="C_POSTNR";
            central.push(vec![name.into(),
                if nr {"1uF C1206C105K5RAC 50V".into()} else {"22uF GRM32ER71E226KE15L 25V X7R".into()},
                if nr {"Capacitor_SMD:C_1206_3216Metric".into()} else {"Capacitor_SMD:C_1210_3225Metric".into()},
                "POWER".into(),pin.into(),pin.into(),"passive".into(),n.into()]);
        }
    }
    // Five24V wetted NC mirror receivers; field returns are independently switched.
    for k in ["K1","K2","KB","KPA","KPB"] {
        let sense=format!("{k}_MIRROR_24V");let input=format!("{k}_FB_IN");let sink=format!("{k}_FB_SINK");
        let mirror=format!("{k}_MIRROR");let exc=format!("{k}_FB_EXC");let substrate=format!("{k}_SUB");
        part(&mut central,&format!("U_{k}_RX"),"ISO1211DR","Package_SO:SOIC-8_3.9x4.9mm_P1.27mm","FEEDBACK",
            &[("1","VCC1","power_in","POD_3V3"),("2","EN","input","POD_3V3"),("3","OUT","output",&mirror),
            ("4","GND1","power_in","AUX_0V"),("5","SUB","passive",&substrate),("6","FGND","passive",&sink),
            ("7","IN","passive",&input),("8","SENSE","passive",&sense)]);
        if k=="KPA" || k=="KPB" {
            passive(&mut central,&format!("R_{k}FB"),"100kR CRCW0603100KFKEA","Resistor_SMD:R_0603_1608Metric",&mirror,"AUX_0V");
            passive(&mut central,&format!("R_{k}FB_SER"),"562R CRCW0603562RFKEA","Resistor_SMD:R_0603_1608Metric",&sense,&input);
            connector(&mut central,&format!("J_{k}"),&["AUX_24V",&format!("{k}_COIL_LOW"),"AUX_24V",&sense],"COILS");
        }
        passive(&mut central,&format!("R_{k}_WET"),"4.7kR CRCW20104K70FKEF 0.75W","Resistor_SMD:R_2010_5025Metric",&sense,&sink);
        passive(&mut central,&format!("C_{k}_FIELD"),"1nF C0603C102J5GACTU 50V","Capacitor_SMD:C_0603_1608Metric",&sense,&sink);
        passive(&mut central,&format!("C_{k}_RX"),"100nF C0603C104K5RACAUTO","Capacitor_SMD:C_0603_1608Metric","POD_3V3","AUX_0V");
        passive(&mut central,&format!("R_{k}_EXCPD"),"100kR CRCW0603100KFKEA","Resistor_SMD:R_0603_1608Metric",&exc,"AUX_0V");
    }
    part(&mut central,"U_FB_SINK","TPL7407LDR","Package_SO:SOIC-16_3.9x9.9mm_P1.27mm","FEEDBACK",
        &[("1","IN1","input","K1_FB_EXC"),("2","IN2","input","K2_FB_EXC"),("3","IN3","input","KB_FB_EXC"),
        ("4","IN4","input","KPA_FB_EXC"),("5","IN5","input","KPB_FB_EXC"),("6","IN6","input","AUX_0V"),
        ("7","IN7","input","AUX_0V"),("8","GND","power_in","AUX_0V"),("9","COM","power_in","AUX_24V"),
        ("10","OUT7","open_collector","NC"),("11","OUT6","open_collector","NC"),("12","OUT5","open_collector","KPB_FB_SINK"),
        ("13","OUT4","open_collector","KPA_FB_SINK"),("14","OUT3","open_collector","KB_FB_SINK"),
        ("15","OUT2","open_collector","K2_FB_SINK"),("16","OUT1","open_collector","K1_FB_SINK")]);
    passive(&mut central,"C_FB_COM","100nF C0603C104J5RACTU 50V","Capacitor_SMD:C_0603_1608Metric","AUX_24V","AUX_0V");
    for k in ["KPA","KPB"] {
        logic(&mut central,&format!("U_{k}_NOTCMD"),&format!("CMD_{k}"),None,&format!("{k}_CMD_OFF"));
        passive(&mut central,&format!("R_{k}_CMDPD"),"10kR CRCW060310K0FKEA","Resistor_SMD:R_0603_1608Metric",&format!("CMD_{k}"),"AUX_0V");
    }
    let mut prior="KPA_MIRROR".to_owned();
    for (i,term) in ["KPB_MIRROR","KPA_FB_EXC","KPB_FB_EXC","KPA_CMD_OFF","KPB_CMD_OFF"].iter().enumerate() {
        let output=if i==4 {"PRECHARGE_ISOLATED".to_owned()}else{format!("ISO_RUN_{}",i+1)};
        logic(&mut central,&format!("U_ISORUN{}",i+1),&prior,Some(term),&output);prior=output;
    }
    logic(&mut central,"U_ISORUN6","PRE_ISO_RUN_OK",Some("PRECHARGE_ISOLATED"),"SUP_RUN_OK_LOCAL");
    // Correlated +/-discharged window, independent of MCU measurements.
    for (name,value,a,b) in [("R_SAFE_HI_TOP","620kR 0.1% TNPW0805620KBEEA","REF_2V5","SAFE_HI"),
        ("R_SAFE_HI_BOT","10kR 0.1% TNPW060310K0BEEA","SAFE_HI","REF_1V25"),
        ("R_SAFE_LO_TOP","10kR 0.1% TNPW060310K0BEEA","REF_1V25","SAFE_LO"),
        ("R_SAFE_LO_BOT","620kR 0.1% TNPW0805620KBEEA","SAFE_LO","AUX_0V")] {
        passive(&mut central,name,value,if value.starts_with("620k") {"Resistor_SMD:R_0805_2012Metric"}else{"Resistor_SMD:R_0603_1608Metric"},a,b);
    }
    for k in ["BUS","CATCH"] {
        let guard=format!("V{k}_GUARD");
        for (suffix,plus,minus) in [("HI","SAFE_HI",guard.as_str()),("LO",guard.as_str(),"SAFE_LO")] {
            let name=format!("U_{k}_SAFE_{suffix}");let out=format!("{k}_SAFE_{suffix}");
            part(&mut central,&name,"TLV3201AIDBVR","Package_TO_SOT_SMD:SOT-23-5","ANALOG_GUARD",
                &[("1","OUT","output",&out),("2","GND","power_in","AUX_0V"),("3","IN+","input",plus),
                ("4","IN-","input",minus),("5","VCC","power_in","POD_3V3")]);
            passive(&mut central,&format!("C_{name}"),"100nF C0603C104K5RACAUTO","Capacitor_SMD:C_0603_1608Metric","POD_3V3","AUX_0V");
        }
        logic(&mut central,&format!("U_{k}_SAFE"),&format!("{k}_SAFE_HI"),Some(&format!("{k}_SAFE_LO")),&format!("{k}_DISCHARGED"));
    }
    for k in ["K1","K2","KB"] {logic(&mut central,&format!("U_{k}_NOTCMD"),&format!("CMD_{k}"),None,&format!("{k}_CMD_OFF"));}
    logic(&mut central,"U_CAPS_SAFE1","BUS_DISCHARGED",Some("CATCH_DISCHARGED"),"CAPS_WINDOWS_OK");
    logic(&mut central,"U_CAPS_SAFE2","CAPS_WINDOWS_OK",Some("VBUS_DIAG_N"),"CAPS_BUS_DIAG_OK");
    logic(&mut central,"U_CAPS_SAFE3","CAPS_BUS_DIAG_OK",Some("VCATCH_DIAG_N"),"CAPS_DISCHARGED");
    let mut prior="CAPS_DISCHARGED".to_owned();
    for (i,term) in ["K1_MIRROR","K2_MIRROR","KB_MIRROR","K1_FB_EXC","K2_FB_EXC","KB_FB_EXC","K1_CMD_OFF","K2_CMD_OFF","KB_CMD_OFF"].iter().enumerate() {
        let out=if i==8 {"SOURCE_OFF_PHYSICAL".to_owned()}else{format!("SOURCE_OFF_{}",i+1)};
        logic(&mut central,&format!("U_SOURCE_OFF{}",i+1),&prior,Some(term),&out);prior=out;
    }
    logic(&mut central,"U_NOT_RUN_PERMIT","SUP_RUN_OK_LOCAL",None,"NOT_RUN_PERMIT");
    logic(&mut central,"U_ISO_ATTEMPT","ATTEMPT",Some("TOTAL_WINDOW"),"ISO_TIMED_ATTEMPT");
    logic(&mut central,"U_ISO_ATTEMPT_NO_RUN","ISO_TIMED_ATTEMPT",Some("NOT_RUN_PERMIT"),"ISO_TIMED_NO_RUN");
    // OR gate has the same package/pin allocation as the existing AND helper.
    logic(&mut central,"U_ISO_ALLOW_OR","SOURCE_OFF_PHYSICAL",Some("ISO_TIMED_NO_RUN"),"ISO_ALLOW_OR");
    for row in central.iter_mut().filter(|r|r[0]=="U_ISO_ALLOW_OR") {row[1]="SN74LVC1G32DBVR".into();}
    logic(&mut central,"U_ISO_HEALTH","BASIC_HEALTHY",Some("LATCH_OK"),"ISO_HEALTH");
    logic(&mut central,"U_ISO_ALLOW","ISO_HEALTH",Some("ISO_ALLOW_OR"),"ISO_COIL_ALLOWED");
    for k in ["KPA","KPB"] {
        logic(&mut central,&format!("U_{k}_DRIVE"),"ISO_COIL_ALLOWED",Some(&format!("CMD_{k}")),&format!("{k}_DRIVE"));
        passive(&mut central,&format!("R_{k}_G"),"1kR CRCW06031K00FKEA","Resistor_SMD:R_0603_1608Metric",&format!("{k}_BUF"),&format!("{k}_GATE"));
        passive(&mut central,&format!("R_{k}_GS"),"22kR CRCW060322K0FKEA","Resistor_SMD:R_0603_1608Metric",&format!("{k}_GATE"),"COIL_RET");
        part(&mut central,&format!("Q_{k}"),"IRL540NPBF","Package_TO_SOT_THT:TO-220-3_Vertical","COILS",
            &[("1","G","input",&format!("{k}_GATE")),("2","D","passive",&format!("{k}_COIL_LOW")),("3","S","passive","COIL_RET")]);
    }
    part(&mut central,"U_ISO_COIL_BUF","SN74AHCT125PWR","Package_SO:TSSOP-14_4.4x5mm_P0.65mm","COILS",
        &[("1","OE1_N","input","AUX_0V"),("2","A1","input","KPA_DRIVE"),("3","Y1","output","KPA_BUF"),
        ("4","OE2_N","input","AUX_0V"),("5","A2","input","KPB_DRIVE"),("6","Y2","output","KPB_BUF"),
        ("7","GND","power_in","AUX_0V"),("8","Y3","output","NC"),("9","A3","input","AUX_0V"),
        ("10","OE3_N","input","POD_5V"),("11","Y4","output","NC"),("12","A4","input","AUX_0V"),
        ("13","OE4_N","input","POD_5V"),("14","VCC","power_in","POD_5V")]);
    passive(&mut central,"C_ISO_COIL_BUF","100nF C0603C104K5RACAUTO","Capacitor_SMD:C_0603_1608Metric","POD_5V","AUX_0V");
    // PhysicalSTART token authorizes one MCU admission, and repeated ADMIT cannot clearQ.
    logic(&mut central,"U_NOT_ADMIT","ADMIT",None,"ADMIT_LOW");
    logic(&mut central,"U_TOKEN_SAFE","SOURCE_OFF_PHYSICAL",Some("ISO_HEALTH"),"TOKEN_SAFE");
    logic(&mut central,"U_TOKEN_ARM","TOKEN_SAFE",Some("ADMIT_LOW"),"TOKEN_ARM_VALID");
    logic(&mut central,"U_NOT_ATTEMPT","ATTEMPT",None,"NOT_ATTEMPT");
    logic(&mut central,"U_TOKEN_CLEAR","ATTEMPT_CLEAR_N",Some("NOT_ATTEMPT"),"TOKEN_CLEAR_N");
    logic(&mut central,"U_ADMIT_VALID","START_TOKEN",Some("TOKEN_SAFE"),"ADMIT_VALID");
    logic(&mut central,"U_ATTEMPT_HOLD","ATTEMPT",Some("ADMIT_VALID"),"ATTEMPT_D");
    for row in central.iter_mut().filter(|r|r[0]=="U_ATTEMPT_HOLD") {row[1]="SN74LVC1G32DBVR".into();}
    logic(&mut central,"U_SOURCE_DRIVE_TIMED","ATTEMPT",Some("BUDGET_OR_PROOF"),"SOURCE_DRIVE_TIMED");
    logic(&mut central,"U_FINAL_PROOF_VALID","PROOF_CAPTURE_VALID",Some("PRECHARGE_ISOLATED"),"FINAL_PROOF_VALID");
    logic(&mut central,"U_FINAL_PROOF_CLEAR","ATTEMPT",Some("PRECHARGE_ISOLATED"),"FINAL_PROOF_CLEAR_N");
    passive(&mut central,"R_ADMIT_PD","10kR CRCW060310K0FKEA","Resistor_SMD:R_0603_1608Metric","ADMIT","AUX_0V");
    passive(&mut central,"R_BUCK_PRELOAD","39R 1% PR03000203909FAC00 3W","Resistor_THT:R_Axial_DIN0617_L17.0mm_D6.0mm_P25.40mm_Horizontal","REG3_5V","AUX_0V");
    for n in ["KB_DRIVE","KT_DRIVE","KPA_DRIVE","KPB_DRIVE"] {
        passive(&mut central,&format!("R_BUF_PD_{n}"),"10kR CRCW060310K0FKEA","Resistor_SMD:R_0603_1608Metric",n,"AUX_0V");
    }
    logic(&mut central,"U_SESSION_BUDGET","RUN_ARMED",Some("RUNTIME_HEALTHY"),"SESSION_BUDGET_OK");
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
