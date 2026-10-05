//! Authoritative prototype supervisor connectivity. Rust emits the Atopile source
//! and typed pin table; the Python adapter only renders the emitted table.
use std::collections::{BTreeMap, BTreeSet};
use std::{env, fs, path::Path};
#[derive(Clone, Debug)]
struct Pin {
    number: String,
    name: String,
    kind: String,
    net: String,
}
#[derive(Clone, Debug)]
struct Part {
    reference: String,
    mpn: String,
    footprint: String,
    sheet: String,
    pins: Vec<Pin>,
}
#[derive(Clone, Default)]
struct Circuit {
    parts: Vec<Part>,
}
impl Circuit {
    fn add(
        &mut self,
        r: &str,
        mpn: &str,
        fp: &str,
        sheet: &str,
        pins: &[(&str, &str, &str, &str)],
    ) {
        self.parts.push(Part {
            reference: r.into(),
            mpn: mpn.into(),
            footprint: fp.into(),
            sheet: sheet.into(),
            pins: pins
                .iter()
                .map(|(n, f, k, s)| Pin {
                    number: (*n).into(),
                    name: (*f).into(),
                    kind: (*k).into(),
                    net: (*s).into(),
                })
                .collect(),
        });
    }
    fn r(&mut self, r: &str, v: &str, a: &str, b: &str, s: &str) {
        self.add(
            r,
            v,
            if v.contains("1206") {
                "Resistor_SMD:R_1206_3216Metric"
            } else {
                "Resistor_SMD:R_0603_1608Metric"
            },
            s,
            &[("1", "1", "passive", a), ("2", "2", "passive", b)],
        );
    }
    fn cap(&mut self, r: &str, v: &str, a: &str, b: &str, s: &str) {
        self.add(
            r,
            v,
            if v.contains("12063") || v.contains("12065") {
                "Capacitor_SMD:C_1206_3216Metric"
            } else if v.contains("C2012") {
                "Capacitor_SMD:C_0805_2012Metric"
            } else {
                "Capacitor_SMD:C_0603_1608Metric"
            },
            s,
            &[("1", "1", "passive", a), ("2", "2", "passive", b)],
        );
    }
    fn gate(&mut self, r: &str, op: &str, a: &str, b: &str, y: &str, s: &str) {
        let mpn = match op {
            "and" => "SN74LVC1G08DBVR",
            "or" => "SN74LVC1G32DBVR",
            _ => panic!("unsupported gate"),
        };
        self.add(
            r,
            mpn,
            "Package_TO_SOT_SMD:SOT-23-5",
            s,
            &[
                ("1", "A", "input", a),
                ("2", "B", "input", b),
                ("3", "GND", "power_in", "AUX_0V"),
                ("4", "Y", "output", y),
                ("5", "VCC", "power_in", "POD_3V3"),
            ],
        );
        self.cap(
            &format!("C_{r}"),
            "100nF C0603C104K5RACAUTO",
            "POD_3V3",
            "AUX_0V",
            s,
        );
    }
    fn inv(&mut self, r: &str, a: &str, y: &str, s: &str) {
        self.add(
            r,
            "SN74LVC1G04DBVR",
            "Package_TO_SOT_SMD:SOT-23-5",
            s,
            &[
                ("1", "NC", "no_connect", "NC"),
                ("2", "A", "input", a),
                ("3", "GND", "power_in", "AUX_0V"),
                ("4", "Y", "output", y),
                ("5", "VCC", "power_in", "POD_3V3"),
            ],
        );
        self.cap(
            &format!("C_{r}"),
            "100nF C0603C104K5RACAUTO",
            "POD_3V3",
            "AUX_0V",
            s,
        );
    }
    fn ff(&mut self, r: &str, d: &str, clk: &str, clear_n: &str, q: &str, s: &str) {
        self.add(
            r,
            "SN74LVC1G74DCUR",
            "Package_SO:VSSOP-8_2.3x2mm_P0.5mm",
            s,
            &[
                ("1", "CLR_N", "input", clear_n),
                ("2", "D", "input", d),
                ("3", "CLK", "input", clk),
                ("4", "GND", "power_in", "AUX_0V"),
                ("5", "Q", "output", q),
                ("6", "Q_N", "output", "NC"),
                ("7", "PRE_N", "input", "POD_3V3"),
                ("8", "VCC", "power_in", "POD_3V3"),
            ],
        );
        self.cap(
            &format!("C_{r}"),
            "100nF C0603C104K5RACAUTO",
            "POD_3V3",
            "AUX_0V",
            s,
        );
    }
    fn and_chain(&mut self, prefix: &str, inputs: &[&str], output: &str, s: &str) {
        let mut prev = inputs[0].to_string();
        for (i, input) in inputs.iter().enumerate().skip(1) {
            let next = if i == inputs.len() - 1 {
                output.to_string()
            } else {
                format!("{prefix}_{i}")
            };
            self.gate(&format!("{prefix}{i}"), "and", &prev, input, &next, s);
            prev = next;
        }
    }
    fn connector(&mut self, r: &str, mpn: &str, pins: &[&str], s: &str) {
        let pins: Vec<Pin> = pins
            .iter()
            .enumerate()
            .map(|(i, n)| Pin {
                number: (i + 1).to_string(),
                name: (*n).into(),
                kind: "passive".into(),
                net: (*n).into(),
            })
            .collect();
        self.parts.push(Part {
            reference: r.into(),
            mpn: mpn.into(),
            footprint: "REVIEW_ONLY:Connector_mechanical_drawing_required".into(),
            sheet: s.into(),
            pins,
        });
    }
    fn net(&self, r: &str, p: &str) -> &str {
        &self
            .parts
            .iter()
            .find(|x| x.reference == r)
            .expect("part")
            .pins
            .iter()
            .find(|x| x.number == p)
            .expect("pin")
            .net
    }
    fn check(&self) -> Result<(), String> {
        let mut refs = BTreeSet::new();
        let mut outputs: BTreeMap<&str, Vec<String>> = BTreeMap::new();
        for p in &self.parts {
            if !refs.insert(&p.reference) {
                return Err(format!("duplicate {}", p.reference));
            }
            let mut pins = BTreeSet::new();
            for pin in &p.pins {
                if !pins.insert(&pin.number) {
                    return Err(format!("duplicate pin {}.{}", p.reference, pin.number));
                }
                if pin.net != "NC" && pin.kind == "output" {
                    outputs
                        .entry(&pin.net)
                        .or_default()
                        .push(format!("{}.{}", p.reference, pin.number));
                }
            }
        }
        for (net, drivers) in outputs {
            if drivers.len() > 1 {
                return Err(format!("push-pull contention {net}: {drivers:?}"));
            }
        }
        for (r, p, n) in [
            ("U_K1_HI", "3", "K1_HIGH_EN"),
            ("U_K2_HI", "3", "K2_HIGH_EN"),
            ("Q_K1", "2", "K1_COIL_LOW"),
            ("Q_K2", "2", "K2_COIL_LOW"),
            ("U_FAULT", "1", "FAULT_CLEAR_N"),
            ("U_FAULT", "3", "RESET_QUALIFIED"),
            ("U_ATTEMPT", "3", "START_QUALIFIED"),
            ("U_WD", "4", "MCU_WDI"),
            ("JCTRL", "1", "CTRL_3V3"),
            ("JCTRL", "2", "CTRL_GND"),
            ("U_VCATCH", "8", "HV_RET"),
            ("U_VBUS", "8", "HV_RET"),
            ("U_VTANK", "8", "SW_B"),
            ("R_VTANKH0", "1", "RES_A"),
        ] {
            if self.net(r, p) != n {
                return Err(format!("contract {r}.{p} != {n}"));
            }
        }
        if self.net("U_K1_HI", "3") == self.net("U_K2_HI", "3") {
            return Err("source enables collapsed".into());
        }
        if self
            .parts
            .iter()
            .flat_map(|p| &p.pins)
            .any(|p| p.net == "J4_V15" || p.net == "LEG_RET" || p.net == "OCP_KELVIN_N")
        {
            return Err("forbidden backfeed/catch return".into());
        }
        Ok(())
    }
}
fn voltage(
    c: &mut Circuit,
    name: &str,
    high: &str,
    low: &str,
    count: usize,
    lower: &str,
    sheet: &str,
) {
    let tap = format!("{name}_TAP");
    let mut prev = high.to_string();
    for i in 0..count {
        let next = if i == count - 1 {
            tap.clone()
        } else {
            format!("{name}_DIV{i}")
        };
        c.add(
            &format!("R_{name}H{i}"),
            "TNPW1206249KBEEA 249kR 0.1%",
            "Resistor_SMD:R_1206_3216Metric",
            sheet,
            &[("1", "1", "passive", &prev), ("2", "2", "passive", &next)],
        );
        prev = next;
    }
    c.add(
        &format!("R_{name}L"),
        lower,
        "Resistor_SMD:R_1206_3216Metric",
        sheet,
        &[("1", "1", "passive", &tap), ("2", "2", "passive", low)],
    );
    c.cap(
        &format!("C_{name}IN"),
        "1nF C0603C102J5GACTU",
        &tap,
        low,
        sheet,
    );
    let dh = format!("{name}_DCDC_H");
    let hl = format!("{name}_HLDO");
    let dl = format!("{name}_DCDC_L");
    let p = format!("{name}_P");
    let n = format!("{name}_N");
    let diag = format!("{name}_DIAG_N");
    c.add(
        &format!("U_{name}"),
        "AMC3330DWE",
        "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
        sheet,
        &[
            ("1", "DCDC_OUT", "power_out", &dh),
            ("2", "DCDC_HGND", "passive", low),
            ("3", "HLDO_IN", "power_in", &dh),
            ("4", "NC", "no_connect", "NC"),
            ("5", "HLDO_OUT", "power_out", &hl),
            ("6", "INP", "input", &tap),
            ("7", "INN", "input", low),
            ("8", "HGND", "passive", low),
            ("9", "GND", "power_in", "AUX_0V"),
            ("10", "OUTN", "output", &n),
            ("11", "OUTP", "output", &p),
            ("12", "VDD", "power_in", "POD_3V3"),
            ("13", "LDO_OUT", "power_out", &dl),
            ("14", "DIAG_N", "open_collector", &diag),
            ("15", "DCDC_GND", "power_in", "AUX_0V"),
            ("16", "DCDC_IN", "power_in", &dl),
        ],
    );
    for (suffix, mpn, a, b) in [
        ("V1", "1nF 12065C102KAT2A", "POD_3V3", "AUX_0V"),
        ("V2", "1uF 12063C105KAT2A", "POD_3V3", "AUX_0V"),
        ("H1", "1uF CGA3E1X7R1E105K080AC", dh.as_str(), low),
        ("H2", "1nF C0603C102K5RACTU", dh.as_str(), low),
        ("L", "100nF C0603C104K5RACAUTO", dl.as_str(), "AUX_0V"),
        ("HL1", "100nF C0603C104K5RACAUTO", hl.as_str(), low),
        ("HL2", "1nF C0603C102K5RACTU", hl.as_str(), low),
    ] {
        c.cap(&format!("C_{name}{suffix}"), mpn, a, b, sheet)
    }
    c.r(
        &format!("R_{name}DIAG"),
        "10kR CRCW060310K0FKEA",
        "POD_3V3",
        &diag,
        sheet,
    );
    // Identical 1:1 dividers reduce differential output gain 2 to net gain 1.
    for (suffix, raw) in [("P", p), ("N", n)] {
        let out = format!("{name}_ADC_{suffix}");
        c.r(
            &format!("R_{name}{suffix}A"),
            "10kR 0.1% TNPW060310K0BEEA",
            &raw,
            &out,
            "ADC",
        );
        c.r(
            &format!("R_{name}{suffix}B"),
            "10kR 0.1% TNPW060310K0BEEA",
            &out,
            "AUX_0V",
            "ADC",
        );
    }
    c.cap(
        &format!("C_{name}ADC"),
        "1nF C0603C102J5GACTU",
        &format!("{name}_ADC_P"),
        &format!("{name}_ADC_N"),
        "ADC",
    );
}
fn timer(c: &mut Circuit, name: &str, trigger: &str, out: &str, rset: &str, div: &str) {
    let s = "HARDWARE";
    let set = format!("{name}_SET");
    let dn = format!("{name}_DIV");
    c.add(
        name,
        "LTC6993HS6-1#TRMPBF",
        "Package_TO_SOT_SMD:TSOT-23-6",
        s,
        &[
            ("1", "TRIG", "input", trigger),
            ("2", "GND", "power_in", "AUX_0V"),
            ("3", "SET", "passive", &set),
            ("4", "DIV", "input", &dn),
            ("5", "VCC", "power_in", "POD_3V3"),
            ("6", "OUT", "output", out),
        ],
    );
    c.r(&format!("R_{name}SET"), rset, &set, "AUX_0V", s);
    c.r(
        &format!("R_{name}UP"),
        "1MR 0.1% TNPW06031M00BEEA",
        "POD_3V3",
        &dn,
        s,
    );
    c.r(&format!("R_{name}LO"), div, &dn, "AUX_0V", s);
    c.cap(
        &format!("C_{name}"),
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        s,
    );
}
fn opamp(c: &mut Circuit, r: &str, plus: &str, minus: &str, out: &str) {
    c.add(
        r,
        "TLV9061IDBVR",
        "Package_TO_SOT_SMD:SOT-23-5",
        "ANALOG_GUARD",
        &[
            ("1", "OUT", "output", out),
            ("2", "V-", "power_in", "AUX_0V"),
            ("3", "IN+", "input", plus),
            ("4", "IN-", "input", minus),
            ("5", "V+", "power_in", "POD_3V3"),
        ],
    );
    c.cap(
        &format!("C_{r}"),
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        "ANALOG_GUARD",
    );
}
fn cmp(c: &mut Circuit, r: &str, plus: &str, minus: &str, out: &str) {
    c.add(
        r,
        "TLV3201AIDBVR",
        "Package_TO_SOT_SMD:SOT-23-5",
        "ANALOG_GUARD",
        &[
            ("1", "OUT", "output", out),
            ("2", "GND", "power_in", "AUX_0V"),
            ("3", "IN+", "input", plus),
            ("4", "IN-", "input", minus),
            ("5", "VCC", "power_in", "POD_3V3"),
        ],
    );
    c.cap(
        &format!("C_{r}"),
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        "ANALOG_GUARD",
    );
}
fn threshold(c: &mut Circuit, name: &str, upper: &str, lower: &str, rail: &str) {
    c.r(&format!("R_{name}H"), upper, rail, name, "ANALOG_GUARD");
    c.r(&format!("R_{name}L"), lower, name, "AUX_0V", "ANALOG_GUARD");
    c.cap(
        &format!("C_{name}"),
        "1nF C0603C102J5GACTU",
        name,
        "AUX_0V",
        "ANALOG_GUARD",
    );
}
fn analog_guard(c: &mut Circuit) {
    c.add(
        "U_REF",
        "LM4040A25IDBZR",
        "Package_TO_SOT_SMD:SOT-23",
        "ANALOG_GUARD",
        &[
            ("1", "K", "passive", "REF_2V5"),
            ("2", "A", "passive", "AUX_0V"),
            ("3", "NC", "no_connect", "NC"),
        ],
    );
    c.r(
        "R_REF_BIAS",
        "330R CRCW0603330RFKEA",
        "POD_3V3",
        "REF_2V5",
        "ANALOG_GUARD",
    );
    c.cap(
        "C_REF",
        "100nF C0603C104K5RACAUTO",
        "REF_2V5",
        "AUX_0V",
        "ANALOG_GUARD",
    );
    threshold(
        c,
        "REF_HALF",
        "10kR 0.1% TNPW060310K0BEEA",
        "10kR 0.1% TNPW060310K0BEEA",
        "REF_2V5",
    );
    opamp(c, "U_REF_BUFFER", "REF_HALF", "REF_1V25", "REF_1V25");
    for n in ["VBUS", "VCATCH", "VTANK"] {
        let plus = format!("{n}_DIFF_PLUS");
        let minus = format!("{n}_DIFF_MINUS");
        let out = format!("{n}_GUARD");
        c.r(
            &format!("R_{n}DP"),
            "20kR 0.1% TNPW060320K0BEEA",
            &format!("{n}_P"),
            &plus,
            "ANALOG_GUARD",
        );
        c.r(
            &format!("R_{n}DR"),
            "10kR 0.1% TNPW060310K0BEEA",
            "REF_1V25",
            &plus,
            "ANALOG_GUARD",
        );
        c.r(
            &format!("R_{n}DN"),
            "20kR 0.1% TNPW060320K0BEEA",
            &format!("{n}_N"),
            &minus,
            "ANALOG_GUARD",
        );
        c.r(
            &format!("R_{n}DF"),
            "10kR 0.1% TNPW060310K0BEEA",
            &out,
            &minus,
            "ANALOG_GUARD",
        );
        opamp(c, &format!("U_{n}DIFF"), &plus, &minus, &out);
    }
    for (n, r) in [
        ("BUS_TRIP", "62.6kR 0.1% TNPW060362K6BEEA"),
        ("CATCH_TRIP", "60.1kR 0.1% TNPW060360K1BEEA"),
        ("TANK_HI", "57.8kR 0.1% TNPW060357K8BEEA"),
        ("TANK_LO", "173kR 0.1% TNPW0603173KBEEA"),
        ("ILINE_HI", "6.34kR 0.1% TNPW06036K34BEEA"),
        ("ILINE_LO", "1.56MR 0.1% TNPW06031M56BEEA"),
        ("TEMP_LO", "284kR 0.1% TNPW0603284KBEEA"),
    ] {
        threshold(c, n, r, "100kR 0.1% TNPW0603100KBEEA", "REF_2V5");
    }
    cmp(c, "U_BUS_LIMIT", "BUS_TRIP", "VBUS_GUARD", "BUS_LIMIT_OK");
    cmp(
        c,
        "U_CATCH_LIMIT",
        "CATCH_TRIP",
        "VCATCH_GUARD",
        "CATCH_LIMIT_OK",
    );
    cmp(c, "U_TANK_HI", "TANK_HI", "VTANK_GUARD", "TANK_HI_OK");
    cmp(c, "U_TANK_LO", "VTANK_GUARD", "TANK_LO", "TANK_LO_OK");
    c.gate(
        "U_TANK_OK",
        "and",
        "TANK_HI_OK",
        "TANK_LO_OK",
        "TANK_LIMIT_OK",
        "ANALOG_GUARD",
    );
    for (suffix, guarded) in [("HI", "ILINE_GUARD_HI"), ("LO", "ILINE_GUARD_LO")] {
        c.r(
            &format!("R_ILINE_{suffix}_LIMIT"),
            "20kR CRCW060320K0FKEA",
            "ILINE_RAW",
            guarded,
            "ANALOG_GUARD",
        );
    }
    cmp(c, "U_ILINE_HI", "ILINE_HI", "ILINE_GUARD_HI", "ILINE_HI_OK");
    cmp(c, "U_ILINE_LO", "ILINE_GUARD_LO", "ILINE_LO", "ILINE_LO_OK");
    c.gate(
        "U_ILINE_OK",
        "and",
        "ILINE_HI_OK",
        "ILINE_LO_OK",
        "ILINE_LIMIT_OK",
        "ANALOG_GUARD",
    );
    threshold(
        c,
        "RAIL24_DIV",
        "110kR 0.1% TNPW0603110KBEEA",
        "10kR 0.1% TNPW060310K0BEEA",
        "AUX_24V",
    );
    threshold(
        c,
        "RAIL24_LO",
        "49.9kR 0.1% TNPW060349K9BEEA",
        "100kR 0.1% TNPW0603100KBEEA",
        "REF_2V5",
    );
    cmp(c, "U_RAIL24LO", "RAIL24_DIV", "RAIL24_LO", "RAIL24_LO_OK");
    cmp(c, "U_RAIL24HI", "REF_2V5", "RAIL24_DIV", "RAIL24_HI_OK");
    c.gate(
        "U_RAIL24",
        "and",
        "RAIL24_LO_OK",
        "RAIL24_HI_OK",
        "RAIL24_OK",
        "ANALOG_GUARD",
    );
    threshold(
        c,
        "TEMP_HI",
        "10kR 0.1% TNPW060310K0BEEA",
        "100kR 0.1% TNPW0603100KBEEA",
        "POD_3V3",
    );
    for i in 1..=2 {
        let node = format!("RP{i}_TEMP");
        c.r(
            &format!("R_TEMP{i}"),
            "10kR 0.1% TNPW060310K0BEEA",
            "POD_3V3",
            &node,
            "ANALOG_GUARD",
        );
        c.connector(
            &format!("J_TEMP{i}"),
            "1725669 Phoenix MKDS1/2-3.81",
            &[&node, "AUX_0V"],
            "ANALOG_GUARD",
        );
        c.add(
            &format!("NTC{i}"),
            "NTCLE100E3103JB0",
            "EXTERNAL:Insulated_resistor_case_thermal_bond",
            "ANALOG_GUARD",
            &[
                ("1", "1", "passive", &node),
                ("2", "2", "passive", "AUX_0V"),
            ],
        );
        c.r(
            &format!("R_TEMP{i}_ADC"),
            "1kR CRCW06031K00FKEA",
            &node,
            &format!("RP{i}_TEMP_ADC"),
            "ANALOG_GUARD",
        );
        c.cap(
            &format!("C_TEMP{i}_ADC"),
            "1nF C0603C102J5GACTU",
            &format!("RP{i}_TEMP_ADC"),
            "AUX_0V",
            "ANALOG_GUARD",
        );
        cmp(
            c,
            &format!("U_TEMP{i}LO"),
            &node,
            "TEMP_LO",
            &format!("TEMP{i}_LO_OK"),
        );
        cmp(
            c,
            &format!("U_TEMP{i}HI"),
            "TEMP_HI",
            &node,
            &format!("TEMP{i}_HI_OK"),
        );
    }
    c.and_chain(
        "U_TEMPS",
        &["TEMP1_LO_OK", "TEMP1_HI_OK", "TEMP2_LO_OK", "TEMP2_HI_OK"],
        "RP_TEMP_OK",
        "ANALOG_GUARD",
    );
    // Disconnected/open/short sensors remain imperfect: DIAG only validates AMC supply,
    // while ladder continuity and frozen in-range analog output require POST injection.
}

fn circuit() -> Circuit {
    let mut c = Circuit::default();
    // Physical mains assembly terminals retain round3 identities, distinct pole/coil/feedback pins.
    c.add(
        "PS_AUX",
        "HDR-60-24",
        "EXTERNAL:DIN_HDR60",
        "MAINS",
        &[
            ("L", "L", "passive", "L_AUX_FUSED"),
            ("N", "N", "passive", "N_AUX"),
            ("+V", "+V", "power_out", "AUX_24V"),
            ("-V", "-V", "power_out", "AUX_0V"),
        ],
    );
    for (r, mpn, a, b) in [
        ("F0", "KLDR015.TXP", "PLUG_L", "L_FUSED"),
        ("F2", "KLDR002.TXP", "L_AUX", "L_AUX_FUSED"),
        ("FT", "KLDR001.TXP", "L_PRE", "PROOF_FUSED"),
        ("TF1", "SDF DF128S", "L_SER", "RP1_HOT"),
        ("TF2", "SDF DF128S", "L_SER", "RP2_HOT"),
        ("RP1", "HS200 22R F", "RP1_HOT", "L_PRE"),
        ("RP2", "HS200 22R F", "RP2_HOT", "L_PRE"),
        ("RTEST", "HS100 220R F", "PROOF_LOAD", "N_PRE"),
    ] {
        c.add(
            r,
            mpn,
            "EXTERNAL:Manufacturer_terminal_drawing",
            "MAINS",
            &[("1", "1", "passive", a), ("2", "2", "passive", b)],
        );
    }
    c.add(
        "S0",
        "4435.0002",
        "EXTERNAL:Schurter",
        "MAINS",
        &[
            ("1", "L_IN", "passive", "L_FUSED"),
            ("2", "L_OUT", "passive", "L_AUX"),
            ("3", "N_IN", "passive", "PLUG_N"),
            ("4", "N_OUT", "passive", "N_AUX"),
        ],
    );
    for (r, li, lo, ni, no) in [
        ("K1", "L_AUX", "L_K1", "N_AUX", "N_K1"),
        ("K2", "L_K1", "L_SER", "N_K1", "N_PRE"),
        ("KB", "L_SER", "L_PRE", "NC", "NC"),
    ] {
        let coilhi = format!("{r}_COIL_HIGH");
        let coillo = format!("{r}_COIL_LOW");
        let fb = format!("{r}_MIRROR_RAW");
        let ex = format!("{r}_FB_EXC");
        c.add(
            r,
            "LC1D18BD",
            "EXTERNAL:LC1D18BD",
            "MAINS",
            &[
                ("1L1", "L_IN", "passive", li),
                ("2T1", "L_OUT", "passive", lo),
                ("3L2", "N_IN", "passive", ni),
                ("4T2", "N_OUT", "passive", no),
                ("5L3", "UNUSED", "passive", "NC"),
                ("6T3", "UNUSED", "passive", "NC"),
                ("A1", "COIL+", "passive", &coilhi),
                ("A2", "COIL-", "passive", &coillo),
                ("21", "NC_MIRROR", "passive", &ex),
                ("22", "NC_MIRROR", "passive", &fb),
                ("13", "NO_AUX", "passive", "NC"),
                ("14", "NO_AUX", "passive", "NC"),
            ],
        );
    }
    // Omron G5Q datasheet p4 bottom view: coil1/5, common2, NO3.
    c.add(
        "KT",
        "G5Q-1A-EU DC24",
        "Relay_THT:Relay_SPST_Omron-G5Q-1A",
        "MAINS",
        &[
            ("1", "COIL1", "passive", "POD_24V_ACT"),
            ("5", "COIL2", "passive", "KT_COIL_LOW"),
            ("2", "COM", "passive", "PROOF_FUSED"),
            ("3", "NO", "passive", "PROOF_LOAD"),
        ],
    );
    c.connector(
        "J_IN",
        "POINT_TO_POINT_INLET",
        &["PLUG_L", "PLUG_N", "PE"],
        "MAINS",
    );
    c.connector(
        "J_OUT",
        "POINT_TO_POINT_D22_INPUT",
        &["L_PRE", "N_PRE", "PE"],
        "MAINS",
    );
    c.add(
        "REG5",
        "R-78HB5.0-0.5/W",
        "EXTERNAL:Wired_RECOM_R78HB_mount_drawing_required",
        "POWER",
        &[
            ("1", "VIN", "power_in", "AUX_24V"),
            ("2", "GND", "power_in", "AUX_0V"),
            ("3", "VOUT", "power_out", "POD_5V"),
        ],
    );
    c.r(
        "R_MINLOAD",
        "499R 0.1% TNPW1206499RBEEA",
        "POD_5V",
        "AUX_0V",
        "POWER",
    );
    c.add(
        "C5IN",
        "22uF EEUFR1H220",
        "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        "POWER",
        &[
            ("1", "+", "passive", "AUX_24V"),
            ("2", "-", "passive", "AUX_0V"),
        ],
    );
    c.add(
        "C5OUT",
        "22uF T491B226K016AT",
        "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
        "POWER",
        &[
            ("1", "+", "passive", "POD_5V"),
            ("2", "-", "passive", "AUX_0V"),
        ],
    );
    // All analog outputs, ADC, reference and MCU share the same 3.3 V rail.
    // LD1117 replaces the thermally small SOT-23 regulator; thermal copper is
    // still a layout constraint (approximately 0.65 W at a 350 mA rail load).
    c.add(
        "REG3",
        "LD1117S33TR",
        "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        "POWER",
        &[
            ("1", "GND", "power_in", "AUX_0V"),
            ("2", "VOUT", "power_out", "POD_3V3"),
            ("3", "VIN", "power_in", "POD_5V"),
        ],
    );
    c.cap("C3IN", "1uF 12063C105KAT2A", "POD_5V", "AUX_0V", "POWER");
    c.add(
        "C3OUT",
        "22uF T491B226K016AT",
        "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
        "POWER",
        &[
            ("1", "+", "passive", "POD_3V3"),
            ("2", "-", "passive", "AUX_0V"),
        ],
    );
    c.add(
        "U_WD",
        "TPS3820-33DBVR",
        "Package_TO_SOT_SMD:SOT-23-5",
        "HARDWARE",
        &[
            ("1", "RESET_N", "output", "WD_RESET_N"),
            ("2", "GND", "power_in", "AUX_0V"),
            ("3", "MR_N", "input", "POD_3V3"),
            ("4", "WDI", "input", "MCU_WDI"),
            ("5", "VDD", "power_in", "POD_3V3"),
        ],
    );
    c.r(
        "R_WDI_PD",
        "1kR CRCW06031K00FKEA",
        "MCU_WDI",
        "AUX_0V",
        "HARDWARE",
    );
    c.cap(
        "C_WD",
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        "HARDWARE",
    );
    c.add(
        "U_PG5",
        "TPS3825-50DBVR",
        "Package_TO_SOT_SMD:SOT-23-5",
        "POWER",
        &[
            ("1", "RESET_N", "output", "PG5_RAW"),
            ("2", "GND", "power_in", "AUX_0V"),
            ("3", "RESET", "output", "NC"),
            ("4", "MR_N", "input", "POD_5V"),
            ("5", "VDD", "power_in", "POD_5V"),
        ],
    );
    c.r(
        "R_PG5A",
        "10kR CRCW060310K0FKEA",
        "PG5_RAW",
        "PG5_N",
        "POWER",
    );
    c.r(
        "R_PG5B",
        "20kR CRCW060320K0FKEA",
        "PG5_N",
        "AUX_0V",
        "POWER",
    );
    // STOP and buttons use 3V3 locally; series resistors and receiver pulldowns.
    for signal in ["START", "RESET", "STOP"] {
        let raw = format!("POD_{signal}_RAW");
        let node = format!("POD_{signal}");
        c.connector(
            &format!("J_{signal}"),
            "1725669 Phoenix MKDS1/2-3.81",
            &["POD_3V3", &raw],
            "OPERATORS",
        );
        c.r(
            &format!("R_{signal}S"),
            "1kR CRCW06031K00FKEA",
            &raw,
            &node,
            "OPERATORS",
        );
        c.r(
            &format!("R_{signal}D"),
            "10kR CRCW060310K0FKEA",
            &node,
            "AUX_0V",
            "OPERATORS",
        );
        c.cap(
            &format!("C_{signal}"),
            "10nF C0603C103K5RACAUTO",
            &node,
            "AUX_0V",
            "OPERATORS",
        );
    }
    for (n, h, l, count, lo) in [
        ("VLINE", "L_AUX", "N_AUX", 4, "TNPW12064K02BEEA 4.02kR 0.1%"),
        ("VPRE", "L_SER", "L_PRE", 4, "TNPW12064K02BEEA 4.02kR 0.1%"),
        ("VOUT", "L_PRE", "N_PRE", 4, "TNPW12064K02BEEA 4.02kR 0.1%"),
        ("VBUS", "BUS_P", "HV_RET", 8, "TNPW12062K49BEEA 2.49kR 0.1%"),
        (
            "VCATCH",
            "CATCH_P",
            "HV_RET",
            8,
            "TNPW12062K49BEEA 2.49kR 0.1%",
        ),
        ("VTANK", "RES_A", "SW_B", 12, "TNPW12061K00BEEA 1kR 0.1%"),
    ] {
        voltage(&mut c, n, h, l, count, lo, n);
    }
    c.connector(
        "J_SENSE_BUS",
        "EXTERNAL_NATIVE19_J8_J10_KELVIN_HARNESS_HOLD",
        &["BUS_P", "HV_RET"],
        "VBUS",
    );
    c.connector(
        "J_SENSE_CATCH",
        "EXTERNAL_CATCH_TERMINAL_PAIR_HOLD",
        &["CATCH_P", "HV_RET"],
        "VCATCH",
    );
    // Six-conductor SELV harness from the remote catch sensor to the pod.
    // HV remains on J_SENSE_CATCH; no power is taken from the capacitor itself.
    for (name, sheet) in [("J_CATCH_REMOTE", "VCATCH"), ("J_CATCH_POD", "ADC")] {
        c.connector(
            name,
            "20021121-00006T4LF mating-cable-review",
            &[
                "POD_3V3",
                "AUX_0V",
                "VCATCH_P",
                "VCATCH_N",
                "VCATCH_DIAG_N",
                "AUX_0V",
            ],
            sheet,
        );
    }
    c.connector(
        "J_SENSE_TANK",
        "EXTERNAL_RES_A_SW_B_2KV_HARNESS_HOLD",
        &["RES_A", "SW_B"],
        "VTANK",
    );
    // Current channel burden/CT is isolated. Permanent dual burdens at actual secondary pins.
    for (n, mpn, rv) in [
        ("IPROOF", "AC1005", "200R CRCW1206200RFKEA"),
        ("ILINE", "AC1020", "100R CRCW1206100RFKEA"),
    ] {
        let p = format!("{n}_RAW");
        c.add(
            &format!("CT_{n}"),
            mpn,
            "REVIEW_ONLY:Talema_CT_primary_harness",
            "CURRENT",
            &[
                ("1", "SEC1", "passive", &p),
                ("2", "SEC2", "passive", "REF_1V25"),
                ("3", "SUPPORT", "passive", "NC"),
            ],
        );
        for i in 1..=2 {
            c.r(&format!("R_{n}B{i}"), rv, &p, "REF_1V25", "CURRENT");
        }
        c.r(
            &format!("R_{n}ADC"),
            "1kR CRCW06031K00FKEA",
            &p,
            &format!("{n}_ADC"),
            "CURRENT",
        );
        c.cap(
            &format!("C_{n}ADC"),
            "1nF C0603C102J5GACTU",
            &format!("{n}_ADC"),
            "AUX_0V",
            "CURRENT",
        );
        c.add(
            &format!("TVS_{n}"),
            "SMCJ5.0CA-E3/57T",
            "Diode_SMD:D_SMC",
            "CURRENT",
            &[
                ("1", "BIDIR1", "passive", &p),
                ("2", "BIDIR2", "passive", "REF_1V25"),
            ],
        );
        c.add(
            &format!("D_{n}"),
            "BAV199,215",
            "Package_TO_SOT_SMD:SOT-23",
            "CURRENT",
            &[
                ("1", "A1", "passive", "AUX_0V"),
                ("2", "K2", "passive", "POD_3V3"),
                ("3", "K1_A2", "passive", &format!("{n}_ADC")),
            ],
        );
    }
    analog_guard(&mut c);
    // ADC differential gain1: OUTP/OUTN both divided2. This ADC is not tank waveform qualification.
    let mut adc = vec![
        ("13", "AGND", "power_in", "AUX_0V"),
        ("28", "AGND", "power_in", "AUX_0V"),
        ("15", "AVDD", "power_in", "POD_3V3"),
        ("26", "DVDD", "power_in", "POD_3V3"),
        ("25", "DGND", "power_in", "AUX_0V"),
        ("24", "CAP", "power_out", "ADC_CAP"),
        ("14", "REFIN", "input", "NC"),
        ("27", "NC", "no_connect", "NC"),
        ("17", "CS_N", "input", "ADC_CS_N"),
        ("18", "DRDY_N", "output", "ADC_DRDY_N"),
        ("19", "SCLK", "input", "ADC_SCLK"),
        ("20", "DOUT", "output", "ADC_DOUT"),
        ("21", "DIN", "input", "ADC_DIN"),
        ("16", "SYNC_RESET_N", "input", "ADC_RESET_N"),
        ("23", "CLKIN", "input", "ADC_CLKIN"),
        ("22", "XTAL2", "output", "NC"),
    ];
    let pairs = [
        ("29", "30", "VLINE_ADC_P", "VLINE_ADC_N"),
        ("32", "31", "VPRE_ADC_P", "VPRE_ADC_N"),
        ("1", "2", "VOUT_ADC_P", "VOUT_ADC_N"),
        ("4", "3", "VBUS_ADC_P", "VBUS_ADC_N"),
        ("5", "6", "VCATCH_ADC_P", "VCATCH_ADC_N"),
        ("8", "7", "VTANK_ADC_P", "VTANK_ADC_N"),
        ("9", "10", "IPROOF_ADC", "REF_1V25"),
        ("12", "11", "ILINE_ADC", "REF_1V25"),
    ];
    for (p, n, a, b) in pairs {
        adc.push((p, "AINP", "input", a));
        adc.push((n, "AINN", "input", b));
    }
    c.add(
        "U_ADC",
        "ADS131M08IPBSR",
        "Package_QFP:TQFP-32_5x5mm_P0.5mm",
        "ADC",
        &adc,
    );
    c.cap(
        "C_ADC_CAP",
        "220nF C0603C224K4RACAUTO",
        "ADC_CAP",
        "AUX_0V",
        "ADC",
    );
    c.cap("C_ADC_A", "1uF 12063C105KAT2A", "POD_3V3", "AUX_0V", "ADC");
    c.cap("C_ADC_D", "1uF 12063C105KAT2A", "POD_3V3", "AUX_0V", "ADC");
    c.r(
        "R_ADC_RESET",
        "10kR CRCW060310K0FKEA",
        "ADC_RESET_N",
        "AUX_0V",
        "ADC",
    );
    c.r(
        "R_ADC_CS",
        "10kR CRCW060310K0FKEA",
        "ADC_CS_N",
        "POD_3V3",
        "ADC",
    );
    c.connector(
        "J_CLK",
        "CLOCK_TEST_HEADER_DNP",
        &["POD_3V3", "AUX_0V", "ADC_CLKIN"],
        "ADC",
    );
    // The local independent analog guards also expose a DNP diagnostic test header.
    // Guard outputs have pull-downs; software cannot replace an absent healthy signal.
    c.connector(
        "J_ANALOG_GUARD",
        "ANALOG_GUARD_TEST_HEADER_DNP",
        &[
            "POD_3V3",
            "AUX_0V",
            "BUS_LIMIT_OK",
            "CATCH_LIMIT_OK",
            "TANK_LIMIT_OK",
            "ILINE_LIMIT_OK",
            "RP_TEMP_OK",
            "RAIL24_OK",
        ],
        "HARDWARE",
    );
    for n in [
        "BUS_LIMIT_OK",
        "CATCH_LIMIT_OK",
        "TANK_LIMIT_OK",
        "ILINE_LIMIT_OK",
        "RP_TEMP_OK",
        "RAIL24_OK",
        "MCU_HEALTHY",
        "MCU_POST_OK",
        "MCU_RESET_OK",
        "MCU_PRECHARGE_DONE",
        "MCU_BYPASS_PROVEN",
        "MCU_RUN",
        "MCU_STOP_DONE",
        "CMD_K1",
        "CMD_K2",
        "CMD_KB",
        "CMD_KT",
        "START_RELEASED",
    ] {
        c.r(
            &format!("R_PD_{n}"),
            "10kR CRCW060310K0FKEA",
            n,
            "AUX_0V",
            "HARDWARE",
        );
    }
    // Pull-downs stay at the pod input; pull-ups stay beside the sensor.
    // An open diagnostic conductor must not leave an un-driven healthy input.
    for n in ["VLINE", "VPRE", "VOUT", "VBUS", "VCATCH", "VTANK"] {
        c.r(
            &format!("R_{n}DIAG_POD_PD"),
            "47kR CRCW060347K0FKEA",
            &format!("{n}_DIAG_N"),
            "AUX_0V",
            "HARDWARE",
        );
    }
    c.and_chain(
        "U_HEALTH",
        &[
            "POD_STOP",
            "WD_RESET_N",
            "PG5_N",
            "RAIL24_OK",
            "BUS_LIMIT_OK",
            "CATCH_LIMIT_OK",
            "TANK_LIMIT_OK",
            "ILINE_LIMIT_OK",
            "RP_TEMP_OK",
            "VLINE_DIAG_N",
            "VPRE_DIAG_N",
            "VOUT_DIAG_N",
            "VBUS_DIAG_N",
            "VCATCH_DIAG_N",
            "VTANK_DIAG_N",
            "MCU_HEALTHY",
        ],
        "BASIC_HEALTHY",
        "HARDWARE",
    );
    c.inv("U_NARM", "TIMER_ARMED", "TIMER_NOT_ARMED", "HARDWARE");
    c.gate(
        "U_BUDGET1",
        "or",
        "TOTAL_WINDOW",
        "BYPASS_PROVEN",
        "BUDGET_OR_PROOF",
        "HARDWARE",
    );
    c.gate(
        "U_BUDGET2",
        "or",
        "TIMER_NOT_ARMED",
        "BUDGET_OR_PROOF",
        "TOTAL_BUDGET_OK",
        "HARDWARE",
    );
    c.gate(
        "U_HEALTH_BUDGET",
        "and",
        "BASIC_HEALTHY",
        "TOTAL_BUDGET_OK",
        "ALL_BUDGET_OK",
        "HARDWARE",
    );
    c.gate(
        "U_BOTH_BUDGET",
        "and",
        "ALL_BUDGET_OK",
        "START_BUDGET_OK",
        "FAULT_PRE_RUNTIME",
        "HARDWARE",
    );
    c.gate(
        "U_RUNTIME_FAULT",
        "and",
        "FAULT_PRE_RUNTIME",
        "RUNTIME_ALLOWED",
        "FAULT_CHAIN_HEALTHY",
        "HARDWARE",
    );
    // This external prototype pod requires a physical RESET after EVERY attempt,
    // including ordinary OFF. Do not rely on the timer RC tail to retain a latch.
    c.gate(
        "U_SESSION_END",
        "and",
        "FAULT_CHAIN_HEALTHY",
        "STOP_DONE_N",
        "FAULT_CLEAR_N",
        "HARDWARE",
    );
    c.gate(
        "U_RESET_QUAL",
        "and",
        "POD_RESET",
        "MCU_RESET_OK",
        "RESET_QUALIFIED",
        "HARDWARE",
    );
    c.ff(
        "U_FAULT",
        "POD_3V3",
        "RESET_QUALIFIED",
        "FAULT_CLEAR_N",
        "LATCH_OK",
        "HARDWARE",
    );
    c.and_chain(
        "U_START",
        &["POD_START", "START_RELEASED", "MCU_POST_OK", "LATCH_OK"],
        "START_QUALIFIED",
        "HARDWARE",
    );
    c.inv("U_STOP_DONE", "MCU_STOP_DONE", "STOP_DONE_N", "HARDWARE");
    c.gate(
        "U_ATTEMPT_CLEAR",
        "and",
        "LATCH_OK",
        "STOP_DONE_N",
        "ATTEMPT_CLEAR_N",
        "HARDWARE",
    );
    c.ff(
        "U_ATTEMPT",
        "POD_3V3",
        "START_QUALIFIED",
        "ATTEMPT_CLEAR_N",
        "ATTEMPT",
        "HARDWARE",
    );
    timer(
        &mut c,
        "UT_START",
        "ATTEMPT",
        "START_WINDOW",
        "54.2kR 0.1% TNPW060354K2BEEA",
        "681kR 0.1% TNPW0603681KBEEA",
    );
    timer(
        &mut c,
        "UT_TOTAL",
        "ATTEMPT",
        "TOTAL_WINDOW",
        "81.1kR 0.1% TNPW060381K1BEEA",
        "681kR 0.1% TNPW0603681KBEEA",
    );
    timer(
        &mut c,
        "UT_PROOF",
        "PROOF_STARTED",
        "PROOF_WINDOW",
        "140kR 0.1% TNPW0603140KBEEA",
        "523kR 0.1% TNPW0603523KBEEA",
    );
    c.r(
        "R_ATT_DELAY",
        "10kR CRCW060310K0FKEA",
        "ATTEMPT",
        "ATTEMPT_RC",
        "HARDWARE",
    );
    c.cap(
        "C_ATT_DELAY",
        "10nF C0603C103K5RACAUTO",
        "ATTEMPT_RC",
        "AUX_0V",
        "HARDWARE",
    );
    c.add(
        "U_TIMER_ARM",
        "SN74LVC1G17DBVR",
        "Package_TO_SOT_SMD:SOT-23-5",
        "HARDWARE",
        &[
            ("1", "NC", "no_connect", "NC"),
            ("2", "A", "input", "ATTEMPT_RC"),
            ("3", "GND", "power_in", "AUX_0V"),
            ("4", "Y", "output", "TIMER_ARMED"),
            ("5", "VCC", "power_in", "POD_3V3"),
        ],
    );
    c.cap(
        "C_TIMER_ARM",
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        "HARDWARE",
    );
    c.gate(
        "U_START_BUDGET1",
        "or",
        "START_WINDOW",
        "PRECHARGE_DONE",
        "START_OR_DONE",
        "HARDWARE",
    );
    c.gate(
        "U_START_BUDGET2",
        "or",
        "START_OR_DONE",
        "TIMER_NOT_ARMED",
        "START_BUDGET_OK",
        "HARDWARE",
    );
    c.ff(
        "U_PROOF_ONCE",
        "POD_3V3",
        "PROOF_REQUEST",
        "ATTEMPT",
        "PROOF_STARTED",
        "HARDWARE",
    );
    c.gate(
        "U_PRE_VALID",
        "and",
        "START_WINDOW",
        "ATTEMPT",
        "PRE_CAPTURE_VALID",
        "HARDWARE",
    );
    c.ff(
        "U_PRE_DONE",
        "PRE_CAPTURE_VALID",
        "MCU_PRECHARGE_DONE",
        "ATTEMPT",
        "PRECHARGE_DONE",
        "HARDWARE",
    );
    c.and_chain(
        "U_PROOFREQ",
        &["CMD_KT", "PRECHARGE_DONE", "ATTEMPT", "LATCH_OK"],
        "PROOF_REQUEST",
        "HARDWARE",
    );
    c.gate(
        "U_PROOF_CAPTURE",
        "and",
        "PROOF_WINDOW",
        "PRECHARGE_DONE",
        "PROOF_CAPTURE_VALID",
        "HARDWARE",
    );
    c.ff(
        "U_PROVEN",
        "PROOF_CAPTURE_VALID",
        "MCU_BYPASS_PROVEN",
        "ATTEMPT",
        "BYPASS_PROVEN",
        "HARDWARE",
    );
    for k in ["K1", "K2"] {
        c.and_chain(
            &format!("U_{k}HI"),
            &["ATTEMPT", "LATCH_OK", &format!("CMD_{k}")],
            &format!("{k}_HIGH_EN"),
            "COILS",
        );
    }
    c.and_chain(
        "U_KBGATE",
        &["CMD_KB", "PRECHARGE_DONE", "LATCH_OK", "ATTEMPT"],
        "KB_DRIVE",
        "COILS",
    );
    c.and_chain(
        "U_KTGATE",
        &["CMD_KT", "PROOF_WINDOW", "ATTEMPT", "LATCH_OK"],
        "KT_DRIVE",
        "COILS",
    );
    // Arm native/controller faults only after valid RUN admission; they remain
    // latched as faults if the controller later withdraws RUN or loses its rail.
    c.ff(
        "U_RUN_ARM",
        "POD_3V3",
        "MCU_RUN",
        "ATTEMPT",
        "RUN_ARMED",
        "HARDWARE",
    );
    c.inv("U_RUN_NOT_ARMED", "RUN_ARMED", "RUN_NOT_ARMED", "HARDWARE");
    c.and_chain(
        "U_RUNTIME",
        &[
            "CTRL_RAIL_OK_LOCAL",
            "CTRL_HEARTBEAT_OK",
            "NATIVE_FAULT_N",
            "CTRL_INTERLOCK_OK_LOCAL",
        ],
        "RUNTIME_HEALTHY",
        "HARDWARE",
    );
    c.gate(
        "U_RUNTIME_ALLOW",
        "or",
        "RUN_NOT_ARMED",
        "RUNTIME_HEALTHY",
        "RUNTIME_ALLOWED",
        "HARDWARE",
    );
    c.and_chain(
        "U_RUN",
        &[
            "MCU_RUN",
            "BYPASS_PROVEN",
            "LATCH_OK",
            "CTRL_RAIL_OK_LOCAL",
            "CTRL_HEARTBEAT_OK",
            "NATIVE_FAULT_N",
        ],
        "SUP_RUN_OK_LOCAL",
        "HARDWARE",
    );
    c.and_chain(
        "U_PERMIT",
        &[
            "SUP_RUN_OK_LOCAL",
            "CTRL_PWM_REQUEST_LOCAL",
            "CTRL_INTERLOCK_OK_LOCAL",
        ],
        "PERMIT_LOCAL",
        "HARDWARE",
    );
    // High-side cut followed by independent low-side command, one channel per source coil.
    for k in ["K1", "K2"] {
        let out = format!("{k}_COIL_HIGH");
        let en = format!("{k}_HIGH_EN");
        let st = format!("{k}_ST_N");
        let cl = format!("{k}_CL");
        c.add(
            &format!("U_{k}_HI"),
            "TPS1H100AQPWPRQ1",
            "Package_SO:Texas_HTSSOP-14-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask3.155x3.255mm",
            "COILS",
            &[
                ("1", "NC", "no_connect", "NC"),
                ("2", "GND", "power_in", "AUX_0V"),
                ("3", "IN", "input", &en),
                ("4", "NC", "no_connect", "NC"),
                ("5", "OUT", "power_out", &out),
                ("6", "OUT", "passive", &out),
                ("7", "OUT", "passive", &out),
                ("8", "VS", "power_in", "AUX_24V"),
                ("9", "VS", "power_in", "AUX_24V"),
                ("10", "VS", "power_in", "AUX_24V"),
                ("11", "NC", "no_connect", "NC"),
                ("12", "DIAG_EN", "input", "POD_3V3"),
                ("13", "CL", "passive", &cl),
                ("14", "ST_N", "open_collector", &st),
                ("15", "EP", "power_in", "AUX_0V"),
            ],
        );
        c.cap(
            &format!("C_{k}VS"),
            "100nF C0603C104K5RACAUTO",
            "AUX_24V",
            "AUX_0V",
            "COILS",
        );
        c.r(
            &format!("R_{k}CL"),
            "4.87kR 0.1% TNPW06034K87BEEA",
            &cl,
            "AUX_0V",
            "COILS",
        );
        c.r(
            &format!("R_{k}ST"),
            "10kR CRCW060310K0FKEA",
            "POD_3V3",
            &st,
            "COILS",
        );
        c.r(
            &format!("R_{k}HI_PD"),
            "10kR CRCW060310K0FKEA",
            &en,
            "AUX_0V",
            "COILS",
        );
    }
    c.r(
        "R_KB_SUPPLY",
        "0R CRCW12060000Z0EA",
        "AUX_24V",
        "KB_COIL_HIGH",
        "COILS",
    );
    c.r(
        "R_KT_SUPPLY",
        "0R CRCW12060000Z0EA",
        "AUX_24V",
        "POD_24V_ACT",
        "COILS",
    );
    let mut buf = vec![
        ("14", "VCC", "power_in", "POD_5V"),
        ("7", "GND", "power_in", "AUX_0V"),
    ];
    for (k, oe, a, y, cmd) in [
        ("K1", "1", "2", "3", "CMD_K1"),
        ("K2", "4", "5", "6", "CMD_K2"),
        ("KB", "10", "9", "8", "KB_DRIVE"),
        ("KT", "13", "12", "11", "KT_DRIVE"),
    ] {
        buf.push((oe, "OE_N", "input", "AUX_0V"));
        buf.push((a, "A", "input", cmd));
        let drive = format!("{k}_BUF");
        let gate = format!("{k}_GATE");
        c.r(
            &format!("R_{k}G"),
            "1kR CRCW06031K00FKEA",
            &drive,
            &gate,
            "COILS",
        );
        c.r(
            &format!("R_{k}GS"),
            "22kR CRCW060322K0FKEA",
            &gate,
            "AUX_0V",
            "COILS",
        );
        c.add(
            &format!("Q_{k}"),
            "IRL540NPBF",
            "Package_TO_SOT_THT:TO-220-3_Vertical",
            "COILS",
            &[
                ("1", "G", "input", &gate),
                ("2", "D", "passive", &format!("{k}_COIL_LOW")),
                ("3", "S", "passive", "AUX_0V"),
            ],
        ); // buffer Y bindings added below after owned strings
        let _ = y;
    }
    c.add(
        "U_BUF",
        "SN74AHCT125PWR",
        "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        "COILS",
        &buf,
    );
    let b = c.parts.last_mut().expect("buffer");
    for (p, k) in [("3", "K1"), ("6", "K2"), ("8", "KB"), ("11", "KT")] {
        b.pins.push(Pin {
            number: p.into(),
            name: "Y".into(),
            kind: "output".into(),
            net: format!("{k}_BUF"),
        });
    }
    c.cap(
        "C_BUF",
        "100nF C0603C104K5RACAUTO",
        "POD_5V",
        "AUX_0V",
        "COILS",
    );
    c.add(
        "D_KT",
        "1N4007-E3/54",
        "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
        "COILS",
        &[
            ("1", "K", "passive", "POD_24V_ACT"),
            ("2", "A", "passive", "KT_COIL_LOW"),
        ],
    );
    for k in ["K1", "K2", "KB"] {
        c.r(
            &format!("R_{k}FB"),
            "10kR CRCW060310K0FKEA",
            &format!("{k}_MIRROR_RAW"),
            "AUX_0V",
            "FEEDBACK",
        );
        c.r(
            &format!("R_{k}FB_SER"),
            "1kR CRCW06031K00FKEA",
            &format!("{k}_MIRROR_RAW"),
            &format!("{k}_MIRROR"),
            "FEEDBACK",
        );
    }
    // Isolated controller interface: implemented with individual fail-low ISO7710F channels.
    c.connector(
        "JCTRL",
        "20021121-00010T4LF Amphenol Minitek 2x5 keyed-cable-review",
        &[
            "CTRL_3V3",
            "CTRL_GND",
            "SUP_RUN_OK",
            "CTRL_PWM_REQUEST",
            "CTRL_HEARTBEAT",
            "CTRL_FAULT_HIGH",
            "CTRL_TX",
            "CTRL_RX",
            "CTRL_RAIL_OK",
            "CTRL_INTERLOCK_OK",
        ],
        "CONTROLLER",
    );
    // These are explicit external supply assertions at the controller connector,
    // not extra supplies generated or tied to the always-powered AUX domain.
    for p in &mut c.parts.last_mut().expect("JCTRL").pins {
        if p.number == "1" || p.number == "2" {
            p.kind = "power_out".into();
        }
    }
    for (r, input, output, reverse) in [
        ("U_ISO_RUN", "SUP_RUN_OK_LOCAL", "SUP_RUN_OK", false),
        ("U_ISO_TX", "MCU_UART_TX", "CTRL_RX", false),
        (
            "U_ISO_PWM",
            "CTRL_PWM_REQUEST",
            "CTRL_PWM_REQUEST_LOCAL",
            true,
        ),
        ("U_ISO_HB", "CTRL_HEARTBEAT", "CTRL_HEARTBEAT_LOCAL", true),
        ("U_ISO_FAULT", "CTRL_FAULT_HIGH", "CTRL_FAULT_LOCAL", true),
        ("U_ISO_RX", "CTRL_TX", "MCU_UART_RX", true),
        ("U_ISO_RAIL", "CTRL_RAIL_OK", "CTRL_RAIL_OK_LOCAL", true),
        (
            "U_ISO_IL",
            "CTRL_INTERLOCK_OK",
            "CTRL_INTERLOCK_OK_LOCAL",
            true,
        ),
    ] {
        let (v1, g1, v2, g2) = if reverse {
            ("CTRL_3V3", "CTRL_GND", "POD_3V3", "AUX_0V")
        } else {
            ("POD_3V3", "AUX_0V", "CTRL_3V3", "CTRL_GND")
        };
        c.add(
            r,
            if r == "U_ISO_FAULT" {
                "ISO7710DR"
            } else {
                "ISO7710FDR"
            },
            "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "CONTROLLER",
            &[
                ("1", "VCC1", "power_in", v1),
                ("2", "IN", "input", input),
                ("3", "VCC1", "power_in", v1),
                ("4", "GND1", "power_in", g1),
                ("5", "GND2", "power_in", g2),
                ("6", "OUT", "output", output),
                ("7", "NC", "no_connect", "NC"),
                ("8", "VCC2", "power_in", v2),
            ],
        );
        c.cap(
            &format!("C_{r}1"),
            "100nF C0603C104K5RACAUTO",
            v1,
            g1,
            "CONTROLLER",
        );
        c.cap(
            &format!("C_{r}2"),
            "100nF C0603C104K5RACAUTO",
            v2,
            g2,
            "CONTROLLER",
        );
        c.r(
            &format!("R_{r}PD"),
            "10kR CRCW060310K0FKEA",
            output,
            g2,
            "CONTROLLER",
        );
    }
    c.inv(
        "U_NFAULT",
        "CTRL_FAULT_LOCAL",
        "NATIVE_FAULT_N",
        "CONTROLLER",
    );
    c.r(
        "R_NATIVE_PULLUP",
        "10kR CRCW060310K0FKEA",
        "CTRL_FAULT_HIGH",
        "CTRL_3V3",
        "CONTROLLER",
    );
    // Separate existing-J4 permit driver output powered ONLY by controller rail.
    c.add(
        "U_ISO_PERMIT",
        "ISO7710FDR",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "CONTROLLER",
        &[
            ("1", "VCC1", "power_in", "POD_3V3"),
            ("2", "IN", "input", "PERMIT_LOCAL"),
            ("3", "VCC1", "power_in", "POD_3V3"),
            ("4", "GND1", "power_in", "AUX_0V"),
            ("5", "GND2", "power_in", "CTRL_GND"),
            ("6", "OUT", "output", "NATIVE_PERMIT"),
            ("7", "NC", "no_connect", "NC"),
            ("8", "VCC2", "power_in", "CTRL_3V3"),
        ],
    );
    for (suffix, supply, ground) in [("1", "POD_3V3", "AUX_0V"), ("2", "CTRL_3V3", "CTRL_GND")] {
        c.cap(
            &format!("C_U_ISO_PERMIT{suffix}"),
            "100nF C0603C104K5RACAUTO",
            supply,
            ground,
            "CONTROLLER",
        );
    }
    for signal in [
        "CTRL_PWM_REQUEST",
        "CTRL_HEARTBEAT",
        "CTRL_RAIL_OK",
        "CTRL_INTERLOCK_OK",
        "CTRL_TX",
    ] {
        c.r(
            &format!("R_{signal}_PD"),
            "10kR CRCW060310K0FKEA",
            signal,
            "CTRL_GND",
            "CONTROLLER",
        );
    }
    c.connector(
        "J_PERMIT",
        "EXTERNAL_J4_9_INLINE_INTERCEPT",
        &["NATIVE_PERMIT", "CTRL_GND"],
        "CONTROLLER",
    );
    c.r(
        "R_PERMIT_PD",
        "10kR CRCW060310K0FKEA",
        "NATIVE_PERMIT",
        "CTRL_GND",
        "CONTROLLER",
    );
    // Exact LQFP64 pin number assignment from ST DS12232 rev5 fig9/table12.
    let gpio = [
        "PC11", "PC12", "PC13", "PC14", "PC15", "VBAT", "VREF+", "VDD", "VSS", "NRST", "PF0",
        "PF1", "PC0", "PC1", "PC2", "PC3", "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7",
        "PC4", "PC5", "PB0", "PB1", "PB2", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15", "PA8",
        "PA9", "PC6", "PC7", "PD8", "PD9", "PA10", "PA11", "PA12", "PA13", "PA14", "PA15", "PC8",
        "PC9", "PD0", "PD1", "PD2", "PD3", "PD4", "PD5", "PD6", "PB3", "PB4", "PB5", "PB6", "PB7",
        "PB8", "PB9", "PC10",
    ];
    let bindings: BTreeMap<&str, &str> = [
        ("VBAT", "POD_3V3"),
        ("VREF+", "POD_3V3"),
        ("VDD", "POD_3V3"),
        ("VSS", "AUX_0V"),
        ("NRST", "WD_RESET_N"),
        ("PA4", "ADC_CS_N"),
        ("PA5", "ADC_SCLK"),
        ("PA6", "ADC_DOUT"),
        ("PA7", "ADC_DIN"),
        ("PA8", "ADC_CLKIN"),
        ("PA9", "MCU_UART_TX"),
        ("PA10", "MCU_UART_RX"),
        ("PA13", "SWDIO"),
        ("PA14", "SWCLK"),
        ("PA0", "ADC_DRDY_N"),
        ("PA2", "RP1_TEMP_ADC"),
        ("PA3", "RP2_TEMP_ADC"),
        ("PA11", "CTRL_INTERLOCK_OK_LOCAL"),
        ("PA1", "ADC_RESET_N"),
        ("PC0", "POD_START"),
        ("PC1", "POD_RESET"),
        ("PC2", "POD_STOP"),
        ("PC3", "MCU_WDI"),
        ("PC4", "CMD_K1"),
        ("PC5", "CMD_K2"),
        ("PB0", "CMD_KB"),
        ("PB1", "CMD_KT"),
        ("PB2", "MCU_HEALTHY"),
        ("PB10", "MCU_POST_OK"),
        ("PB11", "MCU_RESET_OK"),
        ("PB12", "MCU_PRECHARGE_DONE"),
        ("PB13", "MCU_BYPASS_PROVEN"),
        ("PB14", "MCU_RUN"),
        ("PB15", "MCU_STOP_DONE"),
        ("PC6", "START_RELEASED"),
        ("PC7", "K1_MIRROR"),
        ("PC8", "K2_MIRROR"),
        ("PC9", "KB_MIRROR"),
        ("PD0", "K1_FB_EXC"),
        ("PD1", "K2_FB_EXC"),
        ("PD2", "KB_FB_EXC"),
        ("PD3", "CTRL_HEARTBEAT_LOCAL"),
        ("PD4", "CTRL_HEARTBEAT_OK"),
        ("PD5", "K1_ST_N"),
        ("PD6", "K2_ST_N"),
        ("PB3", "LATCH_OK"),
        ("PB4", "ATTEMPT"),
        ("PB5", "BYPASS_PROVEN"),
        ("PB6", "TOTAL_WINDOW"),
        ("PB7", "START_WINDOW"),
        ("PB8", "PROOF_WINDOW"),
        ("PB9", "BASIC_HEALTHY"),
        ("PC10", "CTRL_PWM_REQUEST_LOCAL"),
        ("PC11", "CTRL_RAIL_OK_LOCAL"),
        ("PC12", "CTRL_FAULT_LOCAL"),
    ]
    .into_iter()
    .collect();
    let pins: Vec<Pin> = gpio
        .iter()
        .enumerate()
        .map(|(i, n)| Pin {
            number: (i + 1).to_string(),
            name: (*n).into(),
            kind: if ["VDD", "VBAT", "VREF+", "VSS"].contains(n) {
                "power_in"
            } else {
                "bidirectional"
            }
            .into(),
            net: bindings.get(n).copied().unwrap_or("NC").into(),
        })
        .collect();
    c.parts.push(Part {
        reference: "U_MCU".into(),
        mpn: "STM32G071RBT6".into(),
        footprint: "Package_QFP:LQFP-64_10x10mm_P0.5mm".into(),
        sheet: "MCU".into(),
        pins,
    });
    c.cap(
        "C_MCU",
        "100nF C0603C104K5RACAUTO",
        "POD_3V3",
        "AUX_0V",
        "MCU",
    );
    c.cap(
        "C_MCUBULK",
        "4.7uF C2012X7R1E475K125AB",
        "POD_3V3",
        "AUX_0V",
        "MCU",
    );
    c.connector(
        "J_SWD",
        "20021121-00006T4LF",
        &["POD_3V3", "SWDIO", "AUX_0V", "SWCLK", "WD_RESET_N", "NC"],
        "MCU",
    );
    c
}
fn identity(value: &str) -> String {
    for token in value.split_whitespace() {
        if [
            "TNPW", "CRCW", "C0603", "12063", "12065", "CGA3", "T491", "EEU", "C2012",
        ]
        .iter()
        .any(|p| token.starts_with(p))
        {
            return token.into();
        }
    }
    value.to_string()
}
fn emit(c: &Circuit, out: &Path) -> Result<(), Box<dyn std::error::Error>> {
    fs::create_dir_all(out)?;
    let mut table = String::from("reference\tmpn\tfootprint\tsheet\tpin\tfunction\ttype\tnet\n");
    let mut ato =
        String::from("# GENERATED by circuit.rs; edit Rust authority. No physical release.\n");
    let mut signals = BTreeSet::new();
    for p in &c.parts {
        ato+=&format!("\ncomponent Part_{}:\n    designator_prefix = \"{}\"\n    mpn = \"{}\"\n    footprint = \"{}\"\n",p.reference,p.reference,p.mpn,p.footprint);
        for pin in &p.pins {
            ato += &format!(
                "    signal p{} ~ pin \"{}\"\n",
                pin.number.replace('+', "P").replace('-', "M"),
                pin.number
            );
            table += &format!(
                "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
                p.reference, p.mpn, p.footprint, p.sheet, pin.number, pin.name, pin.kind, pin.net
            );
            if pin.net != "NC" {
                signals.insert(&pin.net);
            }
        }
    }
    ato += "\nmodule Supervisor:\n";
    for n in signals {
        ato += &format!("    signal {n}\n");
    }
    for p in &c.parts {
        ato += &format!(
            "    {} = new Part_{}\n",
            p.reference.to_lowercase(),
            p.reference
        );
        for pin in &p.pins {
            if pin.net != "NC" {
                ato += &format!(
                    "    {}.p{} ~ {}\n",
                    p.reference.to_lowercase(),
                    pin.number.replace('+', "P").replace('-', "M"),
                    pin.net
                );
            }
        }
    }
    let mut bom = String::from("reference,mpn,value,footprint,sheet,status\n");
    for p in &c.parts {
        let status = if p.mpn.contains("HOLD") || p.footprint.contains("REVIEW_ONLY") {
            "HOLD-exact-part-or-footprint-unresolved"
        } else if p.footprint.starts_with("EXTERNAL:") {
            "external-point-to-point-review"
        } else {
            "candidate-not-release"
        };
        bom += &format!(
            "\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",{}\n",
            p.reference,
            identity(&p.mpn),
            p.mpn,
            p.footprint,
            p.sheet,
            status
        );
    }
    fs::write(out.join("bom.csv"), bom)?;
    fs::write(out.join("pins.tsv"), table)?;
    fs::write(out.join("supervisor.ato"), ato)?;
    fs::write(
        out.join("ato.yaml"),
        "ato-version: 0.2.69\nbuilds:\n  default:\n    entry: supervisor.ato:Supervisor\n",
    )?;
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let c = circuit();
    c.check()?;
    let path = env::args().nth(1).ok_or("output directory required")?;
    emit(&c, Path::new(&path))?;
    println!("PASS structural audit: {} parts, {} pins. This is not a circuit safety or fabrication release.",c.parts.len(),c.parts.iter().map(|p|p.pins.len()).sum::<usize>());
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_contract() {
        assert!(circuit().check().is_ok())
    }
    #[test]
    fn wrong_independent_enable_is_rejected() {
        let mut c = circuit();
        c.parts
            .iter_mut()
            .find(|p| p.reference == "U_K2_HI")
            .unwrap()
            .pins
            .iter_mut()
            .find(|p| p.number == "3")
            .unwrap()
            .net = "K1_HIGH_EN".into();
        assert!(c.check().is_err());
    }
    #[test]
    fn fault_latch_clear_bypass_is_rejected() {
        let mut c = circuit();
        c.parts
            .iter_mut()
            .find(|p| p.reference == "U_FAULT")
            .unwrap()
            .pins
            .iter_mut()
            .find(|p| p.number == "1")
            .unwrap()
            .net = "POD_3V3".into();
        assert!(c.check().is_err());
    }
    #[test]
    fn catch_reference_mutation_is_rejected() {
        let mut c = circuit();
        c.parts
            .iter_mut()
            .find(|p| p.reference == "U_VCATCH")
            .unwrap()
            .pins
            .iter_mut()
            .find(|p| p.number == "8")
            .unwrap()
            .net = "LEG_RET".into();
        assert!(c.check().is_err());
    }
    #[test]
    fn output_short_is_rejected() {
        let mut c = circuit();
        c.parts
            .iter_mut()
            .find(|p| p.reference == "U_NFAULT")
            .unwrap()
            .pins
            .iter_mut()
            .find(|p| p.number == "4")
            .unwrap()
            .net = "TOTAL_WINDOW".into();
        assert!(c.check().is_err());
    }
    #[test]
    fn upstream_sensor_remains_live() {
        let c = circuit();
        assert_eq!(c.net("R_VLINEH0", "1"), "L_AUX");
        assert_eq!(c.net("U_VLINE", "8"), "N_AUX");
    }
    #[test]
    fn no_aux_to_controller_supply() {
        let c = circuit();
        assert_ne!(c.net("JCTRL", "1"), c.net("REG3", "2"));
    }
    #[test]
    fn amc_ldo_no_external_supply_load() {
        let c = circuit();
        for n in ["VLINE", "VPRE", "VOUT", "VBUS", "VCATCH", "VTANK"] {
            let net = format!("{n}_DCDC_L");
            let count = c
                .parts
                .iter()
                .flat_map(|p| &p.pins)
                .filter(|p| p.net == net)
                .count();
            assert_eq!(count, 3);
        }
    }
}
#[cfg(test)]
mod logic_tests {
    use super::*;
    /// Evaluates actual emitted single-gate pin connectivity. Timers and analog
    /// decisions are explicit injected inputs; this does not simulate their delay.
    fn settle(c: &Circuit, n: &mut BTreeMap<String, bool>) {
        for _ in 0..32 {
            for _ in 0..128 {
                let before = n.clone();
                for p in &c.parts {
                    let get = |pin: &str| -> bool {
                        p.pins
                            .iter()
                            .find(|x| x.number == pin)
                            .and_then(|x| n.get(&x.net))
                            .copied()
                            .unwrap_or(false)
                    };
                    let value = if p.mpn.starts_with("SN74LVC1G08") {
                        Some(get("5") && get("1") && get("2"))
                    } else if p.mpn.starts_with("SN74LVC1G32") {
                        Some(get("5") && (get("1") || get("2")))
                    } else if p.mpn.starts_with("SN74LVC1G04") {
                        Some(get("5") && !get("2"))
                    } else {
                        None
                    };
                    if let Some(value) = value {
                        let out = &p.pins.iter().find(|x| x.number == "4").unwrap().net;
                        n.insert(out.clone(), value);
                    }
                }
                if *n == before {
                    break;
                }
            }
            let before = n.clone();
            for p in &c.parts {
                if p.mpn.starts_with("SN74LVC1G74") {
                    let get = |pin: &str| -> bool {
                        p.pins
                            .iter()
                            .find(|x| x.number == pin)
                            .and_then(|x| n.get(&x.net))
                            .copied()
                            .unwrap_or(false)
                    };
                    if !get("8") || !get("1") {
                        let out = &p.pins.iter().find(|x| x.number == "5").unwrap().net;
                        n.insert(out.clone(), false);
                    }
                }
            }
            if *n == before {
                return;
            }
        }
        panic!("logic did not converge");
    }
    fn running() -> BTreeMap<String, bool> {
        let mut n = BTreeMap::new();
        for s in [
            "POD_3V3",
            "POD_5V",
            "POD_STOP",
            "WD_RESET_N",
            "PG5_N",
            "RAIL24_LO_OK",
            "RAIL24_HI_OK",
            "BUS_LIMIT_OK",
            "CATCH_LIMIT_OK",
            "TANK_HI_OK",
            "TANK_LO_OK",
            "ILINE_HI_OK",
            "ILINE_LO_OK",
            "TEMP1_LO_OK",
            "TEMP1_HI_OK",
            "TEMP2_LO_OK",
            "TEMP2_HI_OK",
            "VLINE_DIAG_N",
            "VPRE_DIAG_N",
            "VOUT_DIAG_N",
            "VBUS_DIAG_N",
            "VCATCH_DIAG_N",
            "VTANK_DIAG_N",
            "MCU_HEALTHY",
            "LATCH_OK",
            "ATTEMPT",
            "PRECHARGE_DONE",
            "BYPASS_PROVEN",
            "MCU_RUN",
            "CTRL_RAIL_OK_LOCAL",
            "CTRL_HEARTBEAT_OK",
            "CTRL_PWM_REQUEST_LOCAL",
            "CTRL_INTERLOCK_OK_LOCAL",
            "CMD_K1",
            "CMD_K2",
            "CMD_KB",
            "TIMER_ARMED",
            "RUN_ARMED",
        ] {
            n.insert(s.into(), true);
        }
        n
    }
    #[test]
    fn healthy_running_path_is_actually_connected() {
        let c = circuit();
        let mut n = running();
        settle(&c, &mut n);
        for out in ["K1_HIGH_EN", "K2_HIGH_EN", "PERMIT_LOCAL"] {
            assert!(n[out], "{out}");
        }
    }
    #[test]
    fn ordinary_stop_deliberately_requires_a_new_physical_reset() {
        let c = circuit();
        for arm_state in [true, false] {
            let mut n = running();
            settle(&c, &mut n);
            assert!(n["LATCH_OK"]);
            // Mature RUN: both start windows expired. Clear is required with
            // either RC-tail state, not merely the incidental original hazard.
            n.insert("START_WINDOW".into(), false);
            n.insert("TOTAL_WINDOW".into(), false);
            n.insert("TIMER_ARMED".into(), arm_state);
            n.insert("MCU_STOP_DONE".into(), true);
            settle(&c, &mut n);
            assert!(!n["LATCH_OK"]);
            assert!(!n["ATTEMPT"]);
            assert!(!n["PERMIT_LOCAL"]);
            n.insert("MCU_STOP_DONE".into(), false);
            n.insert("TIMER_ARMED".into(), false);
            n.insert("POD_START".into(), true);
            settle(&c, &mut n);
            assert!(!n["LATCH_OK"]);
            assert!(!n["ATTEMPT"]);
        }
    }
    #[test]
    fn every_hardware_fault_asynchronously_clears_both_source_channels_and_gates() {
        let c = circuit();
        for fault in [
            "POD_STOP",
            "WD_RESET_N",
            "PG5_N",
            "RAIL24_LO_OK",
            "RAIL24_HI_OK",
            "BUS_LIMIT_OK",
            "CATCH_LIMIT_OK",
            "TANK_HI_OK",
            "TANK_LO_OK",
            "ILINE_HI_OK",
            "ILINE_LO_OK",
            "TEMP1_LO_OK",
            "TEMP1_HI_OK",
            "TEMP2_LO_OK",
            "TEMP2_HI_OK",
            "VLINE_DIAG_N",
            "VPRE_DIAG_N",
            "VOUT_DIAG_N",
            "VBUS_DIAG_N",
            "VCATCH_DIAG_N",
            "VTANK_DIAG_N",
            "MCU_HEALTHY",
            "POD_3V3",
        ] {
            let mut n = running();
            n.insert(fault.into(), false);
            settle(&c, &mut n);
            for out in ["LATCH_OK", "K1_HIGH_EN", "K2_HIGH_EN", "PERMIT_LOCAL"] {
                assert!(!n[out], "{fault} did not drop {out}");
            }
        }
    }
    #[test]
    fn restoring_healthy_inputs_does_not_unlatch_or_restart() {
        let c = circuit();
        let mut n = running();
        n.insert("POD_STOP".into(), false);
        settle(&c, &mut n);
        n.insert("POD_STOP".into(), true);
        settle(&c, &mut n);
        assert!(!n["LATCH_OK"]);
        assert!(!n["PERMIT_LOCAL"]);
    }
    #[test]
    fn permission_cannot_pass_a_missing_controller_health_wire() {
        let c = circuit();
        for missing in [
            "CTRL_RAIL_OK_LOCAL",
            "CTRL_HEARTBEAT_OK",
            "CTRL_PWM_REQUEST_LOCAL",
            "CTRL_INTERLOCK_OK_LOCAL",
            "MCU_RUN",
        ] {
            let mut n = running();
            n.insert(missing.into(), false);
            settle(&c, &mut n);
            assert!(!n["PERMIT_LOCAL"], "{missing}");
        }
    }
    #[test]
    fn native_bus_fault_cannot_be_software_overridden() {
        let c = circuit();
        let mut n = running();
        n.insert("CTRL_FAULT_LOCAL".into(), true);
        settle(&c, &mut n);
        assert!(!n["PERMIT_LOCAL"]);
    }
    #[test]
    fn cold_precharge_cannot_grant_gate_permission() {
        let c = circuit();
        let mut n = running();
        n.insert("BYPASS_PROVEN".into(), false);
        n.insert("TOTAL_WINDOW".into(), true);
        n.insert("START_WINDOW".into(), true);
        settle(&c, &mut n);
        assert!(n["K1_HIGH_EN"]);
        assert!(!n["PERMIT_LOCAL"]);
    }
    #[test]
    fn total_timeout_latches_and_prevents_retrigger() {
        let c = circuit();
        let mut n = running();
        n.insert("BYPASS_PROVEN".into(), false);
        n.insert("TOTAL_WINDOW".into(), false);
        settle(&c, &mut n);
        assert!(!n["LATCH_OK"]);
        n.insert("TOTAL_WINDOW".into(), true);
        settle(&c, &mut n);
        assert!(!n["K1_HIGH_EN"]);
    }
    #[test]
    fn start_timeout_cannot_be_hidden_by_a_stuck_total_timer() {
        let c = circuit();
        let mut n = running();
        n.insert("PRECHARGE_DONE".into(), false);
        n.insert("BYPASS_PROVEN".into(), false);
        n.insert("START_WINDOW".into(), false);
        n.insert("TOTAL_WINDOW".into(), true);
        settle(&c, &mut n);
        assert!(!n["LATCH_OK"]);
    }
    #[test]
    fn stuck_low_total_timer_is_detected_after_independent_rc_arm() {
        let c = circuit();
        let mut n = running();
        n.insert("BYPASS_PROVEN".into(), false);
        n.insert("TOTAL_WINDOW".into(), false);
        n.insert("TIMER_ARMED".into(), true);
        settle(&c, &mut n);
        assert!(!n["K2_HIGH_EN"]);
    }
    #[test]
    fn proof_drive_is_bounded_by_actual_timer_net() {
        let c = circuit();
        let mut n = running();
        n.insert("CMD_KT".into(), true);
        n.insert("PROOF_WINDOW".into(), false);
        settle(&c, &mut n);
        assert!(!n["KT_DRIVE"]);
    }
    #[test]
    fn bypass_cannot_close_without_precharge_capture() {
        let c = circuit();
        let mut n = running();
        n.insert("PRECHARGE_DONE".into(), false);
        n.insert("START_WINDOW".into(), true);
        settle(&c, &mut n);
        assert!(!n["KB_DRIVE"]);
    }
    #[test]
    fn bypassed_fault_gate_mutation_is_seen_by_logic_oracle() {
        let mut c = circuit();
        let p = c
            .parts
            .iter_mut()
            .find(|p| p.reference == "U_FAULT")
            .unwrap();
        p.pins.iter_mut().find(|x| x.number == "1").unwrap().net = "POD_3V3".into();
        let mut n = running();
        n.insert("POD_STOP".into(), false);
        settle(&c, &mut n);
        assert!(
            n["PERMIT_LOCAL"],
            "mutation must expose real unsafe path, not be masked by duplicate model"
        );
    }
    #[test]
    fn proof_timer_is_one_attempt_latched_not_software_retriggered() {
        let c = circuit();
        assert_eq!(c.net("UT_PROOF", "1"), "PROOF_STARTED");
        assert_eq!(c.net("U_PROOF_ONCE", "1"), "ATTEMPT");
    }
    #[test]
    fn fault_isolator_and_permit_isolator_have_opposite_power_loss_defaults() {
        let c = circuit();
        let fault = c
            .parts
            .iter()
            .find(|x| x.reference == "U_ISO_FAULT")
            .unwrap();
        let permit = c
            .parts
            .iter()
            .find(|x| x.reference == "U_ISO_PERMIT")
            .unwrap();
        assert_eq!(fault.mpn, "ISO7710DR");
        assert_eq!(permit.mpn, "ISO7710FDR");
        assert_eq!(c.net("U_ISO_PERMIT", "6"), "NATIVE_PERMIT");
        assert_eq!(c.net("U_ISO_PERMIT", "3"), "POD_3V3");
    }
}

#[cfg(test)]
mod rail_tests {
    use super::*;
    #[test]
    fn all_analog_sources_follow_adc_supply_on_rail_loss() {
        let c = circuit();
        for name in ["VLINE", "VPRE", "VOUT", "VBUS", "VCATCH", "VTANK"] {
            assert_eq!(c.net(&format!("U_{name}"), "12"), "POD_3V3");
        }
        assert_eq!(c.net("R_REF_BIAS", "1"), "POD_3V3");
        assert_eq!(c.net("REG3", "2"), "POD_3V3");
    }
    #[test]
    fn watchdog_cannot_float_disable_at_mcu_reset() {
        let c = circuit();
        let r = c.parts.iter().find(|p| p.reference == "R_WDI_PD").unwrap();
        assert!(r.mpn.starts_with("1kR "));
        assert_eq!(c.net("R_WDI_PD", "1"), c.net("U_WD", "4"));
        assert_eq!(c.net("R_WDI_PD", "2"), "AUX_0V");
        assert!(190e-6_f64 * 1000.0 < 0.3 * 3.0);
    }
}

#[cfg(test)]
mod harness_tests {
    use super::*;
    #[test]
    fn open_diagnostic_wire_has_a_local_low_default() {
        let c = circuit();
        for name in ["VLINE", "VPRE", "VOUT", "VBUS", "VCATCH", "VTANK"] {
            let r = c
                .parts
                .iter()
                .find(|p| p.reference == format!("R_{name}DIAG_POD_PD"))
                .unwrap();
            assert_eq!(r.sheet, "HARDWARE");
            assert!(r.mpn.starts_with("47kR "));
            assert_eq!(c.net(&r.reference, "1"), format!("{name}_DIAG_N"));
            assert_eq!(c.net(&r.reference, "2"), "AUX_0V");
            assert!(c
                .parts
                .iter()
                .find(|p| p.reference == format!("R_{name}DIAG"))
                .unwrap()
                .mpn
                .starts_with("10kR "));
        }
        // ±1% resistor corners, 5uA LVC input + 100nA AMC leakage, 3.0V rail.
        let r_up = 10_000.0_f64 * 1.01;
        let r_down = 47_000.0_f64 * 0.99;
        let healthy_min = 3.0 * r_down / (r_up + r_down) - 5.1e-6 / (1.0 / r_up + 1.0 / r_down);
        assert!(healthy_min > 2.0); // LVC VIH at3.0..3.6V.
        assert!(5e-6 * 47_000.0 * 1.01 < 0.8); // broken conductor, local IIL.
    }
}

#[cfg(test)]
mod review_regressions {
    use super::*;
    #[test]
    fn tps3825_is_not_the_tps3820_pinout() {
        let c = circuit();
        assert_eq!(c.net("U_PG5", "3"), "NC");
        assert_eq!(c.net("U_PG5", "4"), "POD_5V");
        assert_eq!(c.net("U_WD", "3"), "POD_3V3");
        assert_eq!(c.net("U_WD", "4"), "MCU_WDI");
    }
    #[test]
    fn current_comparator_inputs_are_not_connected_directly_to_ct() {
        let c = circuit();
        assert_eq!(c.net("U_ILINE_HI", "4"), "ILINE_GUARD_HI");
        assert_eq!(c.net("U_ILINE_LO", "3"), "ILINE_GUARD_LO");
        for suffix in ["HI", "LO"] {
            let r = c
                .parts
                .iter()
                .find(|p| p.reference == format!("R_ILINE_{suffix}_LIMIT"))
                .unwrap();
            assert!(r.mpn.starts_with("20kR "));
            assert_eq!(c.net(&r.reference, "1"), "ILINE_RAW");
        }
        for name in ["IPROOF", "ILINE"] {
            assert_eq!(c.net(&format!("TVS_{name}"), "1"), format!("{name}_RAW"));
            assert_eq!(c.net(&format!("TVS_{name}"), "2"), "REF_1V25");
        }
        // Conditional input bound: <=12V raw after a functioning, qualified CT clamp.
        // No claim that 1500W/1ms establishes a 500ms fault-energy rating.
        assert!(12.0_f64 / (20_000.0 * 0.99) < 0.01);
    }
}
