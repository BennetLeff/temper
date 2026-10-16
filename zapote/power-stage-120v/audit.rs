//! Exact-pin safety audit of the 120 V full-bridge power stage netlist.
//!
//! Checks part identity, the HOT/SELV isolation boundary, and the
//! safety-relevant joins (fail-safe driver disable, shoot-through shunt
//! orientation, thermal-cutoff gate-supply loop, OCP polarity through the
//! default-high isolator, tank series path, controller header map).
//! Includes the conditional REF25 DC-bias corner in REFERENCE-BIAS.md;
//! no bus-voltage bound, timing, creepage or thermal qualification.
//!
//!   rustc --edition=2021 -O zapote/power-stage-120v/audit.rs -o /tmp/ps_audit
//!   /tmp/ps_audit zapote/power-stage-120v/frozen/default.net zapote/power-stage-120v/frozen/default.csv \
//!       zapote/power-stage-120v/frozen/resolved-components.json
//!   rustc --edition=2021 --test zapote/power-stage-120v/audit.rs -o /tmp/ps_audit_t && /tmp/ps_audit_t

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
mod audit_f6;

// ------------------------------------------------------------ s-expression

#[derive(Debug, Clone)]
enum Sexp {
    Atom(String),
    List(Vec<Sexp>),
}

fn parse(input: &str) -> Result<Sexp, String> {
    fn one(b: &[u8], i: &mut usize) -> Result<Sexp, String> {
        while b.get(*i).is_some_and(u8::is_ascii_whitespace) {
            *i += 1;
        }
        match b.get(*i) {
            Some(b'(') => {
                *i += 1;
                let mut items = Vec::new();
                loop {
                    while b.get(*i).is_some_and(u8::is_ascii_whitespace) {
                        *i += 1;
                    }
                    match b.get(*i) {
                        Some(b')') => {
                            *i += 1;
                            return Ok(Sexp::List(items));
                        }
                        None => return Err("unclosed list".into()),
                        _ => items.push(one(b, i)?),
                    }
                }
            }
            Some(b'"') => {
                *i += 1;
                let mut v = Vec::new();
                loop {
                    match b.get(*i) {
                        Some(b'"') => {
                            *i += 1;
                            return String::from_utf8(v).map(Sexp::Atom).map_err(|e| e.to_string());
                        }
                        Some(b'\\') => {
                            *i += 1;
                            v.push(*b.get(*i).ok_or("trailing escape")?);
                            *i += 1;
                        }
                        Some(c) => {
                            v.push(*c);
                            *i += 1;
                        }
                        None => return Err("unclosed string".into()),
                    }
                }
            }
            Some(b')') => Err("unexpected close".into()),
            Some(_) => {
                let s = *i;
                while b.get(*i).is_some_and(|c| !c.is_ascii_whitespace() && *c != b'(' && *c != b')') {
                    *i += 1;
                }
                Ok(Sexp::Atom(String::from_utf8_lossy(&b[s..*i]).into_owned()))
            }
            None => Err("empty input".into()),
        }
    }
    let mut i = 0;
    one(input.as_bytes(), &mut i)
}

fn head(s: &Sexp) -> Option<&str> {
    match s {
        Sexp::List(v) => match v.first() {
            Some(Sexp::Atom(a)) => Some(a),
            _ => None,
        },
        _ => None,
    }
}

fn children<'a>(s: &'a Sexp, name: &'a str) -> impl Iterator<Item = &'a Sexp> + 'a {
    let v: &[Sexp] = match s {
        Sexp::List(v) => v,
        _ => &[],
    };
    v.iter().filter(move |c| head(c) == Some(name))
}

fn atom_arg(s: &Sexp, name: &str) -> Option<String> {
    let c = children(s, name).next()?;
    match c {
        Sexp::List(v) => match v.get(1) {
            Some(Sexp::Atom(a)) => Some(a.clone()),
            _ => None,
        },
        _ => None,
    }
}

// ------------------------------------------------------------------ model

#[derive(Debug, Clone)]
struct Comp {
    path: String, // instance path below PowerStage120V, e.g. "leg_a.q_low"
    footprint: String,
    #[allow(dead_code)]
    part: String, // netlist libsource part: footprint-aliased, diagnostic only
}

#[derive(Debug, Clone, Default)]
struct Model {
    comps: BTreeMap<String, Comp>,              // ref -> comp
    nets: BTreeMap<String, BTreeSet<(String, String)>>, // net -> {(ref, pin)}
    bom: BTreeMap<String, String>,              // ref -> CSV MPN
    resolved: BTreeMap<String, String>,         // instance path -> MPN (resolved export)
}

/// Minimal scan of resolved-components.json: each component record has an
/// "address" ending in "PowerStage120V::<path>" followed by its "mpn".
fn load_resolved(json: &str) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for rec in json.split("\"address\": \"").skip(1) {
        let addr = rec.split('"').next().unwrap_or("");
        let Some(path) = addr.split("PowerStage120V::").nth(1) else { continue };
        if let Some(m) = rec.split("\"mpn\": \"").nth(1) {
            out.insert(path.to_string(), m.split('"').next().unwrap_or("").to_string());
        }
    }
    out
}

/// Split one CSV record (RFC 4180 quoting: "" is a literal quote).
fn csv_fields(line: &str) -> Result<Vec<String>, String> {
    let mut fields = Vec::new();
    let mut cur = String::new();
    let mut quoted = false;
    let mut chars = line.chars().peekable();
    while let Some(c) = chars.next() {
        match (quoted, c) {
            (true, '"') if chars.peek() == Some(&'"') => { cur.push('"'); chars.next(); }
            (true, '"') => quoted = false,
            (false, '"') if cur.is_empty() => quoted = true,
            (false, ',') => fields.push(std::mem::take(&mut cur)),
            (_, c) => cur.push(c),
        }
    }
    if quoted {
        return Err("unterminated quoted csv field".into());
    }
    fields.push(cur);
    Ok(fields)
}

fn load(net_text: &str, csv_text: &str, resolved_json: &str) -> Result<Model, String> {
    let root = parse(net_text)?;
    let mut m = Model::default();
    for comps in children(&root, "components") {
        for c in children(comps, "comp") {
            let r = atom_arg(c, "ref").ok_or("comp without ref")?;
            let part = children(c, "libsource").next().and_then(|l| atom_arg(l, "part")).unwrap_or_default();
            let path = children(c, "sheetpath")
                .next()
                .and_then(|s| atom_arg(s, "names"))
                .and_then(|n| n.split("PowerStage120V::").nth(1).map(str::to_string))
                .ok_or(format!("{r}: no instance path"))?;
            let footprint = atom_arg(c, "footprint").unwrap_or_default();
            m.comps.insert(r, Comp { path, part, footprint });
        }
    }
    for nets in children(&root, "nets") {
        for n in children(nets, "net") {
            let name = atom_arg(n, "name").ok_or("net without name")?;
            let mut set = BTreeSet::new();
            for node in children(n, "node") {
                set.insert((atom_arg(node, "ref").unwrap_or_default(), atom_arg(node, "pin").unwrap_or_default()));
            }
            m.nets.insert(name, set);
        }
    }
    for line in csv_text.lines().skip(1) {
        // Comment,"Designator list",Footprint,LCSC,Price. Fields may be
        // quoted and contain commas (e.g. Nexperia "BAT54H,115").
        let fields = csv_fields(line)?;
        let (mpn, refs) = match (fields.first(), fields.get(1)) {
            (Some(a), Some(b)) => (a.clone(), b.clone()),
            _ => return Err("bad csv line".into()),
        };
        for r in refs.split(',') {
            m.bom.insert(r.trim().to_string(), mpn.clone());
        }
    }
    m.resolved = load_resolved(resolved_json);
    Ok(m)
}

impl Model {
    fn reff(&self, path: &str) -> Option<&str> {
        self.comps.iter().find(|(_, c)| c.path == path).map(|(r, _)| r.as_str())
    }
    fn net_of(&self, path: &str, pin: &str) -> Option<String> {
        let r = self.reff(path)?;
        self.nets
            .iter()
            .find(|(_, s)| s.contains(&(r.to_string(), pin.to_string())))
            .map(|(n, _)| n.clone())
    }
    /// Test helper: move one pin onto another (possibly new) net.
    #[cfg(test)]
    fn rewire(&mut self, path: &str, pin: &str, to: &str) {
        let r = self.reff(path).expect("path").to_string();
        let key = (r, pin.to_string());
        for s in self.nets.values_mut() {
            s.remove(&key);
        }
        self.nets.entry(to.to_string()).or_default().insert(key);
    }
    #[cfg(test)]
    fn set_part(&mut self, path: &str, mpn: &str) {
        let r = self.reff(path).expect("path").to_string();
        self.comps.get_mut(&r).unwrap().part = mpn.into();
        self.bom.insert(r, mpn.into());
        self.resolved.insert(path.into(), mpn.into());
    }
}

// ----------------------------------------------------------------- checks

const SELV_NETS: &[&str] = &[
    // stage 38 (candidate 23): v15_selv is gone with PS1; J4 pin 1 was the single-pin SELV net j4_nc1. Stage 48
    // (B13 H2): J4 pin 1 is bias_good_j4, BIAS_GOOD through the 220 k readback resistor
    "bias_good_j4", "selv_gnd", "v3v3", "pwm_ha", "pwm_la", "pwm_hb", "pwm_lb", "permit",
    "bus_fault", "vbus_p", "vbus_n", "ct_s1", "ct_s2",
    "ct_sense_mon", "ct_ref_hi", "ct_ref_lo", "ct_oc_pos", "ct_oc_neg", "ct_zc", "ct_mon",
    "bus_fault_iso", "bus_fault_flt", "bias_good",
    // stage 30 (DECISIONS 33): heartbeat SELV side
    "hb_rx", "hb_bufo", "hb_s", "hb_m", "hb_x", "hb_hold", "hsb_good",
    "line_zc", "line_zc_raw", "leg_a-driver_dis", "leg_b-driver_dis",
    "leg_a-permit_gate", "leg_a.driver-dt",
    "leg_b-permit_gate", "leg_b.driver-dt",
];

/// Stage 31 (DECISIONS 34): the CA-IS3720 is a 2-channel isolator on the ISO7710DW pinout. Its spare channel is
/// pin 5 (A-side input) and pin 12 (B-side driven output); both must stay on single-pin nets.
const SPARE_CHANNEL_PARTS: &[&str] = &["u_iso", "hb.iso"];   // stage 40: bias_hb.verdict is gone (HS-B link, ISO6721FB)

/// Parts allowed to have pins in both domains, and which pins are SELV.
const BARRIER_PARTS: &[(&str, &str, &[&str])] = &[
    // stage 29 (DECISIONS 31): Infineon 2EDR8259X, same DWK pads; SELV side pins 1-8 as before
    ("leg_a.driver", "2EDR8259XXUMA1", &["1", "2", "3", "4", "5", "6", "7", "8"]),
    ("leg_b.driver", "2EDR8259XXUMA1", &["1", "2", "3", "4", "5", "6", "7", "8"]),
    ("u_vsense", "AMC1311BDWVR", &["5", "6", "7", "8"]),
    // stage 31 (DECISIONS 34): Chipanalog CA-IS3720HW/LW in place of ISO7710DWR/FDWR, same pins and land pattern
    ("u_iso", "CA-IS3720HW", &["9", "13", "14", "16"]),
    ("t_ct", "CST3015-200ED", &["3", "4"]),
    // stage 30: the monitor group crosses once, as the heartbeat (U32); the HS links (ISO6721FB) are HOT-HOT
    ("hb.iso", "CA-IS3720HW", &["9", "13", "14", "16"]),
    // stage 40 (candidate 30a): HS-B's verdict crosses to LS on an ISO6721FB like HS-A's, so the stage-30 HS-B -> SELV
    // CA-IS3720LW (bias_hb.verdict) is gone and the group crosses HOT -> SELV once (hb.iso)
    ("line_zc.opto", "VOL628A-2X001T", &["3", "4"]),
];

/// Safety-relevant part identities (path -> MPN).
const IDENTITY: &[(&str, &str)] = &[
    ("j_mains", "1714971"),   // stage 27: UL group B 30 A (DECISIONS 29)
    ("j_pe", "1704004"),
    ("j_coil", "7466004R"),          // stage 35: REDCUBE SMT WP-SMBU (candidate 35; was the THR 74650074)
    ("j_coil_return", "7466004R"),
    ("c_bus1", "B32676G1905K000"),
    ("c_bus2", "B32676G1905K000"),
    ("c_hf_a1", "B32652A0104K000"),
    ("c_hf_a2", "B32652A0104K000"),
    ("c_hf_b1", "B32652A0104K000"),
    ("c_hf_b2", "B32652A0104K000"),
    // stage 49 (DECISIONS 68, candidate 34): the resonant bank was 5 x TDK B32643B8104J000 (2000 V DC, P22.5, dT 15 K).
    // Stage 51 (DECISIONS 73, c51-bank-source): 5 x KNSCHA MMK104J3DF1KN208G2 (2000 V DC, P27.5, JLC C528962) fitted on
    // the dual-pitch footprint; the TDK part is its 28 A drop-in alternate (stage51_checks)
    // Stage 52 (DECISIONS 74, prototype lot): 5 x TDK B32643H8104J000 (2000 V DC, P22.5, 24 A strict) in the dual-pitch
    // footprint's 22.5 mm hole; KNSCHA (in-stock fallback) and B32643B8104J000 (28 A) stay carried parts (stage51_checks)
    ("c_res1", "B32643H8104J000"),
    ("c_res2", "B32643H8104J000"),
    ("c_res3", "B32643H8104J000"),
    ("c_res4", "B32643H8104J000"),
    ("c_res5", "B32643H8104J000"),
    // Stage 52: Y1 400 V H01F variant of the same Murata Type RA disc (same body and certificates; stage52_checks)
    ("cy1", "DE1E3RA222MJ4BH01F"),
    ("cy2", "DE1E3RA222MJ4BH01F"),
    // Stage 52: L1 is the 24 A B82726S2243A020 for the prototype lot (production B82726S2203A020; stage52_checks)
    ("l1", "B82726S2243A020"),
    ("cx1", "R463N410050N1K"),
    ("cx2", "R463N410050N1K"),
    ("f1", "KLDR025.TXP"),
    // Stage 16 (DECISIONS 16): blower-supply mains tap, F2 3.15 A T then J11 to the chassis PS3.
    ("f_blw", "3403.0279.23"),   // stage 28: UMT-H, 1.5 kA (DECISIONS 30)
    ("r_blw", "AC05000001507JAC00"),   // stage 28: 0.15 ohm fault-current limiter
    // Stage 19b (DECISIONS 19b): pwm_hb's v3v3 <-> selv_gnd reference-transfer caps.
    ("c_ref_xfer_1", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_2", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_3", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_4", "CC0603KRX7R9BB104"),
    // Stage 40: pwm_hb's fifth; stage 44 (candidate 44, OPEN-ITEMS S10): one beside each SELV return-path open change of
    // PERMIT (3), BUS_FAULT, BUS_FAULT_ISO and BIAS_GOOD (2).
    ("c_ref_xfer_5", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_6", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_7", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_8", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_9", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_10", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_11", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_12", "CC0603KRX7R9BB104"),
    // stage 48 (B13 H2): BIAS_GOOD's J4.1 branch, one beside each of its three layer changes (C176-C178)
    ("c_ref_xfer_13", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_14", "CC0603KRX7R9BB104"),
    ("c_ref_xfer_15", "CC0603KRX7R9BB104"),
    ("j_blw_ac", "B2P3-VH(LF)(SN)"),
    ("rv1", "TMOV20RP175E"),
    ("br1", "GBJ2510-F"),
    ("tvs_bus", "30KPA150CA"),
    ("tvs_bus_b", "30KPA150CA"),
    ("bias_ha.ren_top", "0603WAF1003T5E"),
    ("bias_ha.ren_bot", "0603WAF2702T5E"),
    ("bias_hb.ren_top", "0603WAF1003T5E"),
    ("bias_hb.ren_bot", "0603WAF2702T5E"),
    ("r_shunt", "CSS2H-2512R-1L00F"),   // stage 17: replaces WSK25121L000FEA (derating, DECISIONS 17)
    // DECISIONS.md 2026-10-03: dead-time resistors (native-18 onward).
    // stage 29: 8.2 ohm gate resistors set the edge the 2EDR8259X's CMTI ratio (1.58) is computed at.
    // stage 42 (candidate 39, DECISIONS 54): 68 ohm 2512 turn-on resistors (with Cgs 4.7 nF) hold the CFD7's S4
    // reverse-diode dv/dt and diF/dt; the 8.2 ohm 1206 broke both limits (85.8 V/ns, 2,101 A/us)
    ("leg_a.r_gh", "25121WF680JT4E"),
    ("leg_a.r_gl", "25121WF680JT4E"),
    ("leg_b.r_gh", "25121WF680JT4E"),
    ("leg_b.r_gl", "25121WF680JT4E"),
    ("leg_a.r_dt", "RT0603BRD0749K9L"),
    ("leg_b.r_dt", "RT0603BRD0749K9L"),
    // stage 43: the 1 kV drain-source snubbers are the ordered YAGEO part (JLC C113872); the former source MPN
    // GRM31A5C3A102JW01D is not a Murata part
    ("leg_a.c_snub_h", "CC1206JKNPOCBN102"),
    ("leg_a.c_snub_l", "CC1206JKNPOCBN102"),
    ("leg_b.c_snub_h", "CC1206JKNPOCBN102"),
    ("leg_b.c_snub_l", "CC1206JKNPOCBN102"),
    ("leg_a.q_high", "IPW65R018CFD7"),
    ("leg_a.q_low", "IPW65R018CFD7"),
    ("leg_b.q_high", "IPW65R018CFD7"),
    ("leg_b.q_low", "IPW65R018CFD7"),
    ("u_iso", "CA-IS3720HW"),
    ("u_ocp", "TLV3201AIDBVR"),
    ("u_ovp", "TLV3201AIDBVR"),
    ("u_nand", "SN74LVC1G10DBVR"),
    ("u_hot5_uv", "TPS3700DDCR"),
    ("u_hot5_schmitt", "SN74LVC1G17DBVR"),
    ("r_hot5_uv_top", "RT0603BRD07105KL"),
    ("r_hot5_uv_bot", "RT0603BRD0710KL"),
    ("r_hot5_uv_pull", "RT0603BRD0710KL"),
    ("r_fe", "0603WAF0000T5E"),
    ("u_ref", "LM4050AEM3-2.5/NOPB"),   // stage 47 (S17 hot copper; c47-ref25-grade): TA -40..125 C (SNOS455H 5.3 p.5); was LM4040A25IDBZR (85 C)
    // stage 48 (OPEN-ITEMS S19; c48-ldo-en-ref-watch): the Q1 grade, +-1 % over -40 <= TJ, TA <= 125 C (SLVSCE6D
    // 5.5 p.5); the catalog TPS70950DBVR is specified only to TA 85 C (SBVS186H 6.5 p.5) and U3 sits at 106.7 C
    ("u_ldo", "TPS70950QDBVRQ1"),
    ("r_ldo_en_top", "0603WAF1003T5E"),
    ("r_ldo_en_bot", "0603WAF2702T5E"),
    // stage 48 (B13 H1): the REF25 watchdog divider, 0.1 % / 25 ppm (RT0603 B-D, TNPW B-E)
    ("r_ref_wd_top", "RT0603BRD0763K4L"),
    ("r_ref_wd_bot", "TNPW060311K7BEEA"),
    // stage 48 (B13 H2): BIAS_GOOD -> J4.1 readback, >= 160 k (J4.1-J4.9 short analysis)
    ("r_bias_good_j4", "RC1206FR-07220KL"),
    ("r_ref_bias", "0603WAF5601T5E"),
    ("r_ocp_ref", "RT0603BRD0710KL"),
    // Trip thresholds: ~93 A OCP and ~280 V OVP (10 k / 140 k). Stage 49 (OPEN-ITEMS S23, B'-1.02 V): R33 7.5 k,
    // R34 16 k, R35 11 k (was 10 k / 12.6 k / 11.7 k) hold the 92.593 A nominal with U6's trip VCM at 1.0185 V
    // (stage49_checks).
    ("r_ocp_sense", "RT0603BRD077K5L"),
    ("r_th_top", "RT0603BRD0716KL"),
    ("r_th_bot", "RT0603BRD0711KL"),
    ("r_ovp_top", "RT0603BRD0710KL"),
    ("r_ovp_bot", "RT0603BRD07140KL"),
    ("r_div1", "RC1206FR-07470KL"),
    ("r_div2", "RC1206FR-07470KL"),
    ("r_div3", "RC1206FR-07470KL"),
    ("r_div4", "RC1206FR-07470KL"),
    ("r_div_bot", "RT0603BRD0715K8L"),
    ("ps_gate", "MPM-20-24"),   // stage 38 (DECISIONS 47 item 2): touch current < 80 uA / 264 VAC, same Case 219A
    ("t_ct", "CST3015-200ED"),
    // Tank-CT detector (tools/ct_detector): burden, trip references, clamps.
    ("r_ct_burden", "RC1206FR-073RL"),
    ("c_ct_burden", "GRM31C5C1H104JA01L"),
    ("r_ct_bias_top", "RT0603BRD071KL"),
    ("r_ct_bias_bot", "RT0603BRD071KL"),
    ("c_ct_bias", "GRM31C5C1H104JA01L"),
    ("r_ct_series", "1206W4F1001T5E"),
    ("d_ct_hi", "BAS116H,115"),
    ("d_ct_lo", "BAS116H,115"),
    ("r_ct_hi_top", "RT0603BRD072K21L"),
    ("r_ct_hi_bot", "RT0603BRD0710KL"),
    ("r_ct_lo_top", "RT0603BRD0710KL"),
    ("r_ct_lo_bot", "RT0603BRD072K21L"),
    ("u_ct_pos", "TLV3201AIDBVR"),
    ("u_ct_neg", "TLV3201AIDBVR"),
    ("u_ct_zc", "TLV3201AIDBVR"),
    ("u_fault_or", "SN74LVC1G332DBVR"),
    // Fast PERMIT -> DIS path (validation-results/02-protection-timing).
    ("leg_a.r_permit", "0603WAF1000T5E"),
    ("leg_b.r_permit", "0603WAF1000T5E"),
    // Native-21 F6 and isolated mains detector: every added part.
    ("leg_a.bias_h.clocal1", "CL32B106KBJNNNE"),
    ("leg_a.bias_h.clocal2", "CL32B106KBJNNNE"),
    ("leg_a.bias_h.cmid1", "GRM188R71E105KA12D"),
    ("leg_a.bias_h.cmid2", "GRM188R71E105KA12D"),
    ("leg_a.bias_h.chf1", "CL05B104KB54PNC"),
    ("leg_a.bias_h.chf2", "CL05B104KB54PNC"),
    ("leg_a.bias_h.chf3", "CL05B104KB54PNC"),
    ("leg_a.bias_h.chf4", "CL05B104KB54PNC"),
    ("leg_a.bias_h.rdamp", "RL1206FR-070R68L"),
    ("leg_a.bias_h.cbulk", "6SVPC220MV"),
    ("leg_a.bias_h.rbleed", "0603WAF4991T5E"),
    ("leg_a.bias_l.clocal1", "CL32B106KBJNNNE"),
    ("leg_a.bias_l.clocal2", "CL32B106KBJNNNE"),
    ("leg_a.bias_l.cmid1", "GRM188R71E105KA12D"),
    ("leg_a.bias_l.cmid2", "GRM188R71E105KA12D"),
    ("leg_a.bias_l.chf1", "CL05B104KB54PNC"),
    ("leg_a.bias_l.chf2", "CL05B104KB54PNC"),
    ("leg_a.bias_l.chf3", "CL05B104KB54PNC"),
    ("leg_a.bias_l.chf4", "CL05B104KB54PNC"),
    ("leg_a.bias_l.rdamp", "RL1206FR-070R68L"),
    ("leg_a.bias_l.cbulk", "6SVPC220MV"),
    ("leg_a.bias_l.rbleed", "0603WAF4991T5E"),
    ("leg_a.dis_or", "SN74LVC1G00DBVR"),
    ("leg_a.c_dis_or", "CC0603KRX7R9BB104"),
    ("leg_a.r_driver_dis", "0603WAF1002T5E"),
    ("leg_a.cgs_h", "GRM1885C1H472JA01D"),   // stage 42: Cgs 4.7 nF C0G (candidate 39)
    ("leg_a.doff_h", "PMEG6030EP,115"),
    ("leg_a.roff_h", "1206W4F100KT5E"),
    ("leg_a.cgs_l", "GRM1885C1H472JA01D"),
    ("leg_a.doff_l", "PMEG6030EP,115"),
    ("leg_a.roff_l", "1206W4F100KT5E"),
    ("leg_b.bias_h.clocal1", "CL32B106KBJNNNE"),
    ("leg_b.bias_h.clocal2", "CL32B106KBJNNNE"),
    ("leg_b.bias_h.cmid1", "GRM188R71E105KA12D"),
    ("leg_b.bias_h.cmid2", "GRM188R71E105KA12D"),
    ("leg_b.bias_h.chf1", "CL05B104KB54PNC"),
    ("leg_b.bias_h.chf2", "CL05B104KB54PNC"),
    ("leg_b.bias_h.chf3", "CL05B104KB54PNC"),
    ("leg_b.bias_h.chf4", "CL05B104KB54PNC"),
    ("leg_b.bias_h.rdamp", "RL1206FR-070R68L"),
    ("leg_b.bias_h.cbulk", "6SVPC220MV"),
    ("leg_b.bias_h.rbleed", "0603WAF4991T5E"),
    ("leg_b.bias_l.clocal1", "CL32B106KBJNNNE"),
    ("leg_b.bias_l.clocal2", "CL32B106KBJNNNE"),
    ("leg_b.bias_l.cmid1", "GRM188R71E105KA12D"),
    ("leg_b.bias_l.cmid2", "GRM188R71E105KA12D"),
    ("leg_b.bias_l.chf1", "CL05B104KB54PNC"),
    ("leg_b.bias_l.chf2", "CL05B104KB54PNC"),
    ("leg_b.bias_l.chf3", "CL05B104KB54PNC"),
    ("leg_b.bias_l.chf4", "CL05B104KB54PNC"),
    ("leg_b.bias_l.rdamp", "RL1206FR-070R68L"),
    ("leg_b.bias_l.cbulk", "6SVPC220MV"),
    ("leg_b.bias_l.rbleed", "0603WAF4991T5E"),
    ("leg_b.dis_or", "SN74LVC1G00DBVR"),
    ("leg_b.c_dis_or", "CC0603KRX7R9BB104"),
    ("leg_b.r_driver_dis", "0603WAF1002T5E"),
    ("leg_b.cgs_h", "GRM1885C1H472JA01D"),
    ("leg_b.doff_h", "PMEG6030EP,115"),
    ("leg_b.roff_h", "1206W4F100KT5E"),
    ("leg_b.cgs_l", "GRM1885C1H472JA01D"),
    ("leg_b.doff_l", "PMEG6030EP,115"),
    ("leg_b.roff_l", "1206W4F100KT5E"),
    ("bias_ls.ldo", "TPS7A4700RGWR"),
    ("bias_ls.cnr", "GRM188R71E105KA12D"),
    ("bias_ls.cin", "CL32B106KBJNNNE"),
    ("bias_ls.cout1", "CL32B106KBJNNNE"),
    ("bias_ls.cout2", "CL32B106KBJNNNE"),
    ("bias_ls.chf", "CC0603KRX7R9BB104"),
    ("bias_ls.shunt", "TLVH431BQDBZR"),
    ("bias_ls.rtop", "RT0603BRD076K2L"),
    ("bias_ls.rbot", "RT0603BRD0710KL"),
    ("monitor_ls.reference", "TL431BQDBZR"),   // stage 45 (S16, DECISIONS 59, option 1c-4420): TL431B, halfref 4.42 k / 10 k, re-centred taps;
                                               // stage 46 (S17 hot copper): the 125 C grades TL431BQDBZR / LM2901BIDR
    ("monitor_ls.rref", "RC1206FR-072K2L"),
    ("monitor_ls.rhalf_top", "RT0603BRD074K42L"),
    ("monitor_ls.rhalf_bot", "RT0603BRD0710KL"),
    ("monitor_ls.ruv_top", "RT0603BRD07750RL"),
    ("monitor_ls.ruv_bot", "RT0603BRD0710KL"),
    ("monitor_ls.rov_top", "RT0603BRD072K94L"),
    ("monitor_ls.rov_bot", "RT0603BRD0710KL"),
    ("monitor_ls.rspanuv_top", "RT0603BRD0790K9L"),
    ("monitor_ls.rspanuv_bot", "RT0603BRD0711KL"),
    ("monitor_ls.rspanov_top", "RT0603BRD07104KL"),
    ("monitor_ls.rspanov_bot", "RT0603BRD0711KL"),
    ("monitor_ls.monitor", "LM2901BIDR"),
    ("monitor_ls.rpull", "0603WAF1002T5E"),
    ("u_bias_flt", "SN74LVC1G17DBVR"),
    // stage 30 (DECISIONS 33): HS links and the heartbeat
    ("bias_ha.link", "ISO6721FBDR"),
    ("bias_hb.link", "ISO6721FBDR"),   // stage 40 (candidate 30a): HS-B -> LS, default LOW
    ("hb.vote", "BAT54S-7-F"),
    ("hb.vote_b", "BAT54S-7-F"),
    ("hb.rgate", "0603WAF1003T5E"),   // stage 50 (c50-permit-gate): 100 k from PERMIT (10 k from v3v3 before)
    ("hb.osc", "SN74LVC1G132DBVR"),
    ("hb.rosc", "0603WAF4991T5E"),
    ("hb.cosc", "CL10C331JB8NNNC"),
    ("hb.iso", "CA-IS3720HW"),
    ("hb.buf", "SN74LVC1G132DBVR"),
    ("hb.rs", "0603WAF2200T5E"),
    ("hb.cp1", "C0603C102J5GACTU"),
    ("hb.cp2", "C0603C102J5GACTU"),
    ("hb.pump", "BAT54S-7-F"),
    ("hb.chold", "C0603C102J5GACTU"),
    ("hb.rbleed", "RT0603BRD0749K9L"),
    ("r_bf", "0603WAF1001T5E"),
    ("c_bf", "CL10C101JB8NNNC"),
    ("monitor_ls.ldo5", "TPS70950QDBVRQ1"),   // stage 48 (S19)
    ("monitor_ls.rldo_en_top", "0603WAF1003T5E"),
    ("monitor_ls.rldo_en_bot", "0603WAF2702T5E"),
    ("monitor_ls.cuv", "C0603C102J5GACTU"),
    ("monitor_ls.cov", "C0603C102J5GACTU"),
    ("monitor_ls.cspanuv", "C0603C102J5GACTU"),
    ("monitor_ls.cspanov", "C0603C102J5GACTU"),
    ("monitor_ls.cmonitor", "CC0603KRX7R9BB104"),
    ("bias_ha.iso", "R24C2T25/R-R"),
    ("bias_ha.split.cout1", "CL32B106KBJNNNE"),
    ("bias_ha.cin1", "CL32B106KBJNNNE"),
    ("bias_ha.cin2", "CL32B106KBJNNNE"),
    ("bias_ha.cinhf", "CC0603KRX7R9BB104"),
    ("bias_ha.cavin", "CL10C331JB8NNNC"),
    ("bias_ha.rfbt", "RT0603BRD0763K4L"),
    ("bias_ha.rfbb", "RT0603BRD0711KL"),
    ("bias_ha.cfb", "CL10C331JB8NNNC"),
    ("bias_ha.split.chf", "CC0603KRX7R9BB104"),
    ("bias_ha.split.shunt", "TLVH431BQDBZR"),
    ("bias_ha.split.rtop", "RT0603BRD076K2L"),
    ("bias_ha.split.rbot", "RT0603BRD0710KL"),
    ("bias_ha.monitor.reference", "TL431BQDBZR"),
    ("bias_ha.monitor.rref", "RC1206FR-072K2L"),
    ("bias_ha.monitor.rhalf_top", "RT0603BRD074K42L"),
    ("bias_ha.monitor.rhalf_bot", "RT0603BRD0710KL"),
    ("bias_ha.monitor.ruv_top", "RT0603BRD07750RL"),
    ("bias_ha.monitor.ruv_bot", "RT0603BRD0710KL"),
    ("bias_ha.monitor.rov_top", "RT0603BRD072K94L"),
    ("bias_ha.monitor.rov_bot", "RT0603BRD0710KL"),
    ("bias_ha.monitor.rspanuv_top", "RT0603BRD0790K9L"),
    ("bias_ha.monitor.rspanuv_bot", "RT0603BRD0711KL"),
    ("bias_ha.monitor.rspanov_top", "RT0603BRD07104KL"),
    ("bias_ha.monitor.rspanov_bot", "RT0603BRD0711KL"),
    ("bias_ha.monitor.monitor", "LM2901BIDR"),
    ("bias_ha.monitor.rpull", "0603WAF1002T5E"),
    ("bias_ha.monitor.ldo5", "TPS70950QDBVRQ1"),   // stage 48 (S19)
    ("bias_ha.monitor.rldo_en_top", "0603WAF1003T5E"),
    ("bias_ha.monitor.rldo_en_bot", "0603WAF2702T5E"),
    ("bias_ha.monitor.cuv", "C0603C102J5GACTU"),
    ("bias_ha.monitor.cov", "C0603C102J5GACTU"),
    ("bias_ha.monitor.cspanuv", "C0603C102J5GACTU"),
    ("bias_ha.monitor.cspanov", "C0603C102J5GACTU"),
    ("bias_ha.monitor.cmonitor", "CC0603KRX7R9BB104"),
    ("bias_hb.iso", "R24C2T25/R-R"),
    ("bias_hb.split.cout1", "CL32B106KBJNNNE"),
    ("bias_hb.cin1", "CL32B106KBJNNNE"),
    ("bias_hb.cin2", "CL32B106KBJNNNE"),
    ("bias_hb.cinhf", "CC0603KRX7R9BB104"),
    ("bias_hb.cavin", "CL10C331JB8NNNC"),
    ("bias_hb.rfbt", "RT0603BRD0763K4L"),
    ("bias_hb.rfbb", "RT0603BRD0711KL"),
    ("bias_hb.cfb", "CL10C331JB8NNNC"),
    ("bias_hb.split.chf", "CC0603KRX7R9BB104"),
    ("bias_hb.split.shunt", "TLVH431BQDBZR"),
    ("bias_hb.split.rtop", "RT0603BRD076K2L"),
    ("bias_hb.split.rbot", "RT0603BRD0710KL"),
    ("bias_hb.monitor.reference", "TL431BQDBZR"),
    ("bias_hb.monitor.rref", "RC1206FR-072K2L"),
    ("bias_hb.monitor.rhalf_top", "RT0603BRD074K42L"),
    ("bias_hb.monitor.rhalf_bot", "RT0603BRD0710KL"),
    ("bias_hb.monitor.ruv_top", "RT0603BRD07750RL"),
    ("bias_hb.monitor.ruv_bot", "RT0603BRD0710KL"),
    ("bias_hb.monitor.rov_top", "RT0603BRD072K94L"),
    ("bias_hb.monitor.rov_bot", "RT0603BRD0710KL"),
    ("bias_hb.monitor.rspanuv_top", "RT0603BRD0790K9L"),
    ("bias_hb.monitor.rspanuv_bot", "RT0603BRD0711KL"),
    ("bias_hb.monitor.rspanov_top", "RT0603BRD07104KL"),
    ("bias_hb.monitor.rspanov_bot", "RT0603BRD0711KL"),
    ("bias_hb.monitor.monitor", "LM2901BIDR"),
    ("bias_hb.monitor.rpull", "0603WAF1002T5E"),
    ("bias_hb.monitor.ldo5", "TPS70950QDBVRQ1"),   // stage 48 (S19)
    ("bias_hb.monitor.rldo_en_top", "0603WAF1003T5E"),
    ("bias_hb.monitor.rldo_en_bot", "0603WAF2702T5E"),
    ("bias_hb.monitor.cuv", "C0603C102J5GACTU"),
    ("bias_hb.monitor.cov", "C0603C102J5GACTU"),
    ("bias_hb.monitor.cspanuv", "C0603C102J5GACTU"),
    ("bias_hb.monitor.cspanov", "C0603C102J5GACTU"),
    ("bias_hb.monitor.cmonitor", "CC0603KRX7R9BB104"),
    ("line_zc.r1", "RC1206FR-0716K5L"),
    ("line_zc.r2", "RC1206FR-0716K5L"),
    ("line_zc.opto", "VOL628A-2X001T"),
    ("line_zc.r3", "RC1206FR-0716K5L"),
    ("line_zc.r4", "RC1206FR-0716K5L"),
    ("line_zc.pullup", "0603WAF3302T5E"),
    ("line_zc.buffer", "SN74LVC1G17DBVR"),
    ("line_zc.cbuffer", "CC0603KRX7R9BB104"),

];

fn expect(errs: &mut Vec<String>, m: &Model, path: &str, pin: &str, net: &str) {
    match m.net_of(path, pin) {
        Some(n) if n == net => {}
        Some(n) => errs.push(format!("{path}.{pin} on {n}, expected {net}")),
        None => errs.push(format!("{path}.{pin} unconnected or missing, expected {net}")),
    }
}

fn members(m: &Model, net: &str) -> BTreeSet<(String, String)> {
    m.nets
        .get(net)
        .map(|s| {
            s.iter()
                .map(|(r, p)| (m.comps.get(r).map(|c| c.path.clone()).unwrap_or_default(), p.clone()))
                .collect()
        })
        .unwrap_or_default()
}

/// REF25 shunt data for the bias-window checks: (V max with the full-range tolerance and the current-regulation
/// shift, V min likewise, full-range minimum cathode current in uA, top of the current-regulation window in uA).
fn reference_spec(mpn: &str) -> Option<(f64, f64, f64, f64)> {
    match mpn {
        // TI SLOS456Q 6.8 p.9 (A25I, TA -40..85 C): 2.5 V +-19 mV at 100 uA, +-1 mV for IZ,min < IZ < 1 mA,
        // IZ,min 80 uA over the full range
        "LM4040A25IDBZR" => Some((2.520, 2.480, 80.0, 1000.0)),
        // stage 47: TI SNOS455H 5.6 p.7 (LM4050AEM3, TA = TJ -40..125 C): 2.5 V +-15 mV over the extended range
        // (note 5 p.11: +-0.1 % +- 50 ppm/C x 100 K), +-1.2 mV for IRMIN <= IR <= 1 mA over temperature, IRMIN 65 uA
        "LM4050AEM3-2.5/NOPB" => Some((2.5162, 2.4838, 65.0, 1000.0)),
        _ => None,
    }
}

/// Minimum REF25 cathode current with the selected three REF25 loads. This
/// checks the reference's DC bias, not comparator response or trip timing.
fn min_reference_cathode_current_ua(bias_ohm: f64, ref_max: f64) -> f64 {
    // Source: HOT5 min 4.75 V (U3 TPS70950, SBVS186H 6.5 p.5: +-1 % for VOUT >= 3.3 V; 4.75 V is the older
    // MC78L05AC bound, kept as the conservative floor), the reference at its maximum (reference_spec). The 1 %
    // bias resistor is high; all three 0.1 % thin-film load strings are low.
    let bias_current = (4.75 - ref_max) / (bias_ohm * 1.01);
    // -0.15 V at OCP_KELVIN_N corresponds to 150 A through the 1 mΩ
    // shunt. This bounds loading beyond the nominal 51–71 A trip spread;
    // it does not assert that the power path survives a 150 A fault.
    // R32 + R33 = 10 k + 7.5 k (stage 49, S23 B'-1.02 V; 10 k + 10 k before).
    let ocp_offset_load = (ref_max + 0.15) / (17_500.0 * 0.999);
    // R34 + R35 = 16 k + 11 k (stage 49; 12.6 k + 11.7 k from stage 15, 12.4 k + 11.7 k, and 10.6 k + 10 k before 2026-10-09).
    let ocp_threshold_load = ref_max / (27_000.0 * 0.999);
    let ovp_threshold_load = ref_max / (150_000.0 * 0.999);
    // stage 48 (B13 H1): the REF25 watchdog divider R144 + R145 = 63.4 k + 11.7 k into U14 INB-
    let watchdog_load = ref_max / (75_100.0 * 0.999);
    (bias_current - ocp_offset_load - ocp_threshold_load - ovp_threshold_load - watchdog_load) * 1e6
}

/// Stage 47: the most REF25 cathode current can be, the whole bias-resistor current with every load open (the
/// ceiling), at HOT5 5.15 V (TPS70950 +1 % + 10 mV line + 50 mV load, SBVS186H 6.5 p.5, rounded up) and the
/// reference at its minimum. It must stay inside the current-regulation window the reference error assumes.
fn max_reference_cathode_current_ua(bias_ohm: f64, ref_min: f64) -> f64 {
    (5.15 - ref_min) / (bias_ohm * 0.99) * 1e6
}

// Dead-time window. Stage 29 (DECISIONS 31; 11-candidates/c25-driver/results/dtband): on the as-built F6
// deck (-1.6 V off bias, PMEG discharge) with the 2EDR8259X and 8.2 ohm gates, 3095/3095 D2 runs pass every
// screen for driver dead times 340-600 ns at 27/100/150 C and the weak / strong output corners. The former
// [391, 498] ns window came from the pre-F6 unipolar deck (`grid-best-longdt`, FINDINGS F7).
const DT_WINDOW_NS: (f64, f64) = (340.0, 600.0);
const DT_RESISTORS: &[(&str, f64, f64, f64)] = &[
    // (MPN, kOhm, tolerance, TCR ppm/K) from the Yageo datasheets (out-D12/SOURCES.md)
    ("RC0603FR-0739KL", 39.0, 0.01, 100.0),
    ("RC0603FR-0749K9L", 49.9, 0.01, 100.0),
    ("RT0603BRD0749K9L", 49.9, 0.001, 25.0),
];

/// 2EDR8259 STP/DTC dead time (Infineon datasheet Rev 1.7 Table 19: kOhm, min / typ / max ns; the 100 k row is
/// characterisation only) - c25-driver/scripts/dt_window.py.
const DT_TABLE_2EDR: &[(f64, f64, f64, f64)] = &[(10.0, 85.0, 100.0, 115.0), (30.0, 255.0, 300.0, 345.0), (100.0, 800.0, 950.0, 1100.0)];

fn dt_lin(r: f64, col: usize) -> f64 {
    for w in DT_TABLE_2EDR.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (ya, yb) = ([a.1, a.2, a.3][col], [b.1, b.2, b.3][col]);
        if r >= a.0 && r <= b.0 {
            return ya + (r - a.0) * (yb - ya) / (b.0 - a.0);
        }
    }
    f64::NAN
}

fn dt_ratio(r: f64, col: usize) -> f64 {
    for w in DT_TABLE_2EDR.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (q0, q1) = ([a.1, a.2, a.3][col] / (10.0 * a.0), [b.1, b.2, b.3][col] / (10.0 * b.0));
        if r >= a.0 && r <= b.0 {
            return 10.0 * r * (q0 + (r - a.0) * (q1 - q0) / (b.0 - a.0));
        }
    }
    f64::NAN
}

/// (min, max) estimated 2EDR8259 dead time in ns for a DT resistor: the min / max columns at the resistor's
/// tolerance and TCR corners over -40..150 C (|dT| = 125 K), the envelope of linear and ratio interpolation.
/// An estimate from the datasheet table, not an Infineon guarantee.
fn dead_time_window_ns(r_kohm: f64, tol: f64, tcr_ppm: f64) -> (f64, f64) {
    let drift = tcr_ppm * 1e-6 * 125.0;
    let rmin = r_kohm * (1.0 - tol) * (1.0 - drift);
    let rmax = r_kohm * (1.0 + tol) * (1.0 + drift);
    (dt_lin(rmin, 0).min(dt_ratio(rmin, 0)), dt_lin(rmax, 2).max(dt_ratio(rmax, 2)))
}

// Stage 48 (c48-ldo-en-ref-watch). Resistor data used by the arithmetic checks: (MPN, ohm, tolerance, TCR ppm/K).
// UNI-ROYAL 0603WAF / Yageo RC1206FR: +-1 %, +-100 ppm/K; Yageo RT0603 B-D and Vishay TNPW B-E: +-0.1 %, +-25 ppm/K.
const S48_RESISTORS: &[(&str, f64, f64, f64)] = &[
    ("0603WAF1003T5E", 100_000.0, 0.01, 100.0),
    ("0603WAF2702T5E", 27_000.0, 0.01, 100.0),
    ("RT0603BRD0763K4L", 63_400.0, 0.001, 25.0),
    ("TNPW060311K7BEEA", 11_700.0, 0.001, 25.0),
    ("RC1206FR-07220KL", 220_000.0, 0.01, 100.0),
];
/// |dT| for the ratio drift: 25 C to the 125 C rating corner (100 K).
const S48_DT_K: f64 = 100.0;
/// TPS709(-Q1) EN: VEN(HI) >= 0.9 V, recommended VEN <= 6.5 V (SBVS186H 6.3 / 6.5 p.4-5; SLVSCE6D 5.3 / 5.5 p.4-5).
/// IEN is 300 nA typical only (no limit); the check carries 1 uA out of the pin (pull-up) as a bound.
const S48_VEN_HI: f64 = 0.9;
const S48_VEN_MAX: f64 = 6.5;
const S48_IEN_A: f64 = 1.0e-6;
/// IN - GND of each LDO (V): U3 = V15_LS - OCP_KELVIN_P 14.50-15.46 V (S16 rail model, s20-286v-recite 1.6); U37-U39 =
/// the rail span 16.575-17.425 V, rounded up to 17.43 V. The checks also hold the span-OV corner 18.643 V (DECISIONS
/// 62) and U3's 16.68 V there.
const S48_LDO_IN: &[(&str, &str, f64, f64, f64)] = &[
    ("u_ldo", "", 14.50, 15.46, 16.68),
    ("monitor_ls.ldo5", "monitor_ls.", 16.575, 17.43, 18.643),
    ("bias_ha.monitor.ldo5", "bias_ha.monitor.", 16.575, 17.43, 18.643),
    ("bias_hb.monitor.ldo5", "bias_hb.monitor.", 16.575, 17.43, 18.643),
];
/// TPS3700 INB-: VIT+ 396-404 mV, I(INB-) +-15 nA (SBVS187G 6.5 p.6).
const S48_VIT: (f64, f64) = (0.396, 0.404);
const S48_IINB_A: f64 = 15.0e-9;
/// LM4050AEM3-2.5 VR max (reference_spec) and REF25 with U5 open: R31 5.6 k (+1 %) from HOT5 >= 4.632 V (the
/// HOT5-UV no-trip ceiling, s20-286v-recite 1.4) into the REF25 loads at their maxima (+0.1 %), KELVIN_N at 0 V.
const S48_U5_OPEN_MIN_FLOOR: f64 = 2.80;

fn s48_res(m: &Model, path: &str) -> Option<(f64, f64, f64)> {
    let mpn = m.resolved.get(path)?;
    S48_RESISTORS.iter().find(|(p, ..)| p == mpn).map(|&(_, r, t, c)| (r, t, c))
}

/// (min, max) divider ratio bottom / (top + bottom) at tolerance and TCR corners (adverse, untracked).
fn s48_ratio(top: (f64, f64, f64), bot: (f64, f64, f64)) -> (f64, f64) {
    let d = |r: (f64, f64, f64), s: f64| r.0 * (1.0 + s * (r.1 + r.2 * 1e-6 * S48_DT_K));
    let lo = d(bot, -1.0) / (d(bot, -1.0) + d(top, 1.0));
    let hi = d(bot, 1.0) / (d(bot, 1.0) + d(top, -1.0));
    (lo, hi)
}

/// (EN min at IN min, EN max at IN max, EN max at the corner IN) for one LDO divider; the pull-up raises EN by at most
/// IEN x Rth.
fn s48_en_window(top: (f64, f64, f64), bot: (f64, f64, f64), vin_min: f64, vin_max: f64, vin_corner: f64) -> (f64, f64, f64) {
    let (lo, hi) = s48_ratio(top, bot);
    let rth = top.0 * (1.0 + top.1) * bot.0 * (1.0 + bot.1) / (top.0 * (1.0 + top.1) + bot.0 * (1.0 + bot.1));
    (vin_min * lo, vin_max * hi + S48_IEN_A * rth, vin_corner * hi + S48_IEN_A * rth)
}

/// REF25 trip window of the watchdog: REF = (VIT+ +- I x Rth) / ratio.
fn s48_trip_window(top: (f64, f64, f64), bot: (f64, f64, f64)) -> (f64, f64) {
    let (lo, hi) = s48_ratio(top, bot);
    let rth = top.0 * bot.0 / (top.0 + bot.0);
    ((S48_VIT.0 - S48_IINB_A * rth) / hi, (S48_VIT.1 + S48_IINB_A * rth) / lo)
}

/// REF25 with U5 open, at its lowest: HOT5 4.632 V over R31 (+1 %) into the loads (OCP 17.5 k, threshold 27 k from
/// stage 49; 20 k / 24.3 k before; OVP 150 k, watchdog top + bottom, each +0.1 %).
fn s48_u5_open_min(wd_ohm: f64) -> f64 {
    let g: f64 = [17_500.0, 27_000.0, 150_000.0, wd_ohm].iter().map(|r| 1.0 / (r * 1.001)).sum();
    let rl = 1.0 / g;
    4.632 * rl / (rl + 5_600.0 * 1.01)
}

// Stage 49 (c49-c34-bank). Bank: TDK B3264*B (6/26) p.11, VR 2000 V DC for B32643B8104J000 (p.2 / p.11 footprint and
// body); B3265*A (6/26) p.23 VR 1600 V DC for the former B32654A1104J000. F3, the third-fault bank peak, is 1683 V
// (DECISIONS 23 / item 853); the ledger's peak-voltage rule is <= 0.85 of VR for that out-of-scope case (c34 README:
// 0.84 x 2000 V), so the bank must be rated >= 1980 V.
// Stage 51: KNSCHA MMK104J3DF1KN208G2, VR 2000 V DC (spec KNS20200505002 p.1 'MMKP82 104J2000V P=27.5', p.4 rated voltage).
// Stage 52: TDK B32643H8104J000, VR 2000 V DC at 105 C (B3264*H June 2026 p.14 row 'VR, DC = 2000 V DC', p.15).
const S49_BANK_VR: &[(&str, f64)] = &[("B32643B8104J000", 2000.0), ("MMK104J3DF1KN208G2", 2000.0),
                                       ("B32643H8104J000", 2000.0), ("B32654A1104J000", 1600.0)];
const S49_F3_V: f64 = 1683.0;
const S49_F3_MAX_RATIO: f64 = 0.85;
// OCP divider (S23, 11-candidates/s23-ocp-cm-2026-10-16): Yageo RT0603 B-D, +-0.1 %, +-25 ppm/K (resistor, ohm).
const S49_OCP_RESISTORS: &[(&str, f64)] = &[
    ("RT0603BRD0710KL", 10_000.0), ("RT0603BRD077K5L", 7_500.0), ("RT0603BRD0716KL", 16_000.0),
    ("RT0603BRD0711KL", 11_000.0), ("RT0603BRD0712K6L", 12_600.0), ("TNPW060311K7BEEA", 11_700.0),
];
/// Nominal OCP trip (A) and U6 trip common mode (V) at REF 2.5 V and R5 1 mOhm: ocp_node = k' REF - w I R5 meets
/// ocp_thresh = k REF, k' = R33 / (R32 + R33), w = 1 - k', k = R35 / (R34 + R35) (s23_optb.py nominal()).
fn s49_ocp_nominal(r32: f64, r33: f64, r34: f64, r35: f64) -> (f64, f64) {
    let (k, kp) = (r35 / (r34 + r35), r33 / (r32 + r33));
    (2.5 * (kp - k) / (1.0 - kp) / 1e-3, 2.5 * k)
}
/// The as-built nominal trip (stage 15 / s48, 92.593 A); B' holds it within 0.25 A.
const S49_TRIP_NOM_A: f64 = 92.593;
/// U6 trip VCM window for B': below the as-built 1.20 V (offset sensitivity 2.0 -> 1.75 A/mV) and above the TLV3201
/// input-pair transition tail (~0.3-0.9 V, SBOS561C Fig 6-5 p.7, typical units).
const S49_VCM: (f64, f64) = (0.95, 1.10);
/// C30 (c_ocp_node): Samsung CL10C101JB8NNNC, 100 pF C0G (farad); and the OCP front-end RC the timing budget assumes
/// (R32 || R33 = 5 k x 100 pF = 500 ns as built to s48; B' gives 4.29 k x 100 pF = 429 ns).
const S49_C30: &[(&str, f64)] = &[("CL10C101JB8NNNC", 100e-12)];
const S49_TAU_MAX_NS: f64 = 500.0;

fn stage49_checks(m: &Model, e: &mut Vec<String>) {
    for c in ["c_res1", "c_res2", "c_res3", "c_res4", "c_res5"] {
        let mpn = m.resolved.get(c).cloned().unwrap_or_default();
        match S49_BANK_VR.iter().find(|(p, _)| *p == mpn) {
            Some((_, vr)) if S49_F3_V <= S49_F3_MAX_RATIO * vr => {}
            Some((_, vr)) => e.push(format!(
                "stage49: {c} ({mpn}) VR {vr} V: F3 {S49_F3_V} V is {:.3} of VR, above {S49_F3_MAX_RATIO}", S49_F3_V / vr)),
            None => e.push(format!("stage49: {c} ({mpn}) has no bank voltage rating (S49_BANK_VR)")),
        }
    }
    let r = |p: &str| m.resolved.get(p).and_then(|mpn| S49_OCP_RESISTORS.iter().find(|(q, _)| q == mpn)).map(|x| x.1);
    match (r("r_ocp_ref"), r("r_ocp_sense"), r("r_th_top"), r("r_th_bot")) {
        (Some(a), Some(b), Some(c), Some(d)) => {
            let (i, vcm) = s49_ocp_nominal(a, b, c, d);
            if (i - S49_TRIP_NOM_A).abs() > 0.25 {
                e.push(format!("stage49: OCP nominal trip {i:.3} A, not {S49_TRIP_NOM_A} +- 0.25 A"));
            }
            if vcm < S49_VCM.0 || vcm > S49_VCM.1 {
                e.push(format!("stage49: U6 trip common mode {vcm:.4} V outside {:.2}-{:.2} V (S23 B')", S49_VCM.0, S49_VCM.1));
            }
            // C30 (ocp_node to OCP_KELVIN_P) filters the source R32 || R33: its time constant must not exceed the 500 ns
            // front-end RC the 555 ns OCP front-end budget is built on (stage15-28A fault_check.py)
            match m.resolved.get("c_ocp_node").and_then(|p| S49_C30.iter().find(|(q, _)| q == p)).map(|x| x.1) {
                Some(c) => {
                    let tau_ns = a * b / (a + b) * c * 1e9;
                    if tau_ns > S49_TAU_MAX_NS {
                        e.push(format!("stage49: C30 x (R32 || R33) = {tau_ns:.0} ns, above the {S49_TAU_MAX_NS} ns front-end RC"));
                    }
                }
                None => e.push("stage49: c_ocp_node has no capacitance data (S49_C30)".into()),
            }
        }
        _ => e.push("stage49: r_ocp_ref / r_ocp_sense / r_th_top / r_th_bot have no resistor data (S49_OCP_RESISTORS)".into()),
    }
}

// Stage 51 (DECISIONS 73, c51-bank-source): the bank sits on one dual-pitch footprint whose pad 1 (RES_A) is shared and
// whose pad 2 (SW_B) has a hole at 22.5 mm (TDK B32643B8104J000, the 28 A alternate) and one at 27.5 mm (KNSCHA
// MMK104J3DF1KN208G2, fitted). Either part fits the same board; any other footprint, or a bank part the footprint does not
// carry, fails.
const S51_BANK_FP: &str = "temper:Bank_Film_DualPitch_P22.5_P27.5_Radial";
// stage 52: + TDK B32643H8104J000 (the prototype-lot part, 22.5 mm hole; same body and leads as B32643B)
const S51_BANK_PARTS: &[&str] = &["MMK104J3DF1KN208G2", "B32643B8104J000", "B32643H8104J000"];

fn stage51_checks(m: &Model, e: &mut Vec<String>) {
    for c in ["c_res1", "c_res2", "c_res3", "c_res4", "c_res5"] {
        match m.reff(c).and_then(|r| m.comps.get(r)) {
            Some(comp) if comp.footprint == S51_BANK_FP => {}
            Some(comp) => e.push(format!("stage51: {c} footprint {} is not the dual-pitch bank footprint {S51_BANK_FP}",
                                         comp.footprint)),
            None => e.push(format!("stage51: {c} not found")),
        }
        let mpn = m.resolved.get(c).cloned().unwrap_or_default();
        if !S51_BANK_PARTS.contains(&mpn.as_str()) {
            e.push(format!("stage51: {c} ({mpn}) is not a part the dual-pitch bank footprint carries"));
        }
    }
}

// Stage 52 (DECISIONS 74; 11-candidates/b15-proto-alternates): BOM-only prototype swaps on unchanged footprints. L1 must be
// a part of TDK's B82726S22*3A020 sheet (same drawing IND2421-G-E, 10 x 25 mm pins): the fitted 24 A 2243 or the 20 A
// production 2203. C3 / C4 must be a Murata Type RA 2.2 nF disc of the fitted body (D 9.0, T 4.0, F 10, d 0.6) with the
// E37921 / 40043033 / CQC16001138225 certificates: the fitted H01F (Y1 400 V) or the former P01F (Y1 300 V). Any other
// choke or Y capacitor, or another footprint, fails (the S1 touch-current and EMI records assume these parts).
const S52_L1_FP: &str = "temper:B82726S2_ReviewOnly";
const S52_L1_PARTS: &[&str] = &["B82726S2243A020", "B82726S2203A020"];
const S52_CY_FP: &str = "temper:Murata_DE1E3RA222MA4BP01F_P10.0_Pad1.5_ReviewOnly";
const S52_CY_PARTS: &[&str] = &["DE1E3RA222MJ4BH01F", "DE1E3RA222MA4BP01F"];

fn stage52_checks(m: &Model, e: &mut Vec<String>) {
    for (c, fp, parts) in [("l1", S52_L1_FP, S52_L1_PARTS), ("cy1", S52_CY_FP, S52_CY_PARTS), ("cy2", S52_CY_FP, S52_CY_PARTS)] {
        match m.reff(c).and_then(|r| m.comps.get(r)) {
            Some(comp) if comp.footprint == fp => {}
            Some(comp) => e.push(format!("stage52: {c} footprint {} is not {fp}", comp.footprint)),
            None => e.push(format!("stage52: {c} not found")),
        }
        let mpn = m.resolved.get(c).cloned().unwrap_or_default();
        if !parts.contains(&mpn.as_str()) {
            e.push(format!("stage52: {c} ({mpn}) is not a qualified part for its footprint ({})", parts.join(" / ")));
        }
    }
}

fn stage48_checks(m: &Model, e: &mut Vec<String>) {
    // S19: every TPS70950(Q)'s EN on its own divider tap, inside VEN(HI) .. 6.5 V across its IN range
    for (ldo, base, vin_min, vin_max, vin_corner) in S48_LDO_IN {
        let (top, bot, en) = if base.is_empty() {
            ("r_ldo_en_top".to_string(), "r_ldo_en_bot".to_string(), "hot5_en".to_string())
        } else {
            let b = base.trim_end_matches('.');
            (format!("{base}rldo_en_top"), format!("{base}rldo_en_bot"), format!("{b}-ldo_en"))
        };
        match m.net_of(ldo, "3") {
            Some(n) if n == en => {}
            n => e.push(format!("stage48: {ldo}.3 (EN) on {n:?}, expected the divider tap {en}")),
        }
        let want: BTreeSet<(String, String)> = [(ldo.to_string(), "3"), (top.clone(), "2"), (bot.clone(), "1")]
            .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
        if members(m, &en) != want {
            e.push(format!("stage48: {en} must join only {ldo}.3 and its divider, found {:?}", members(m, &en)));
        }
        if m.net_of(&top, "1") != m.net_of(ldo, "1") || m.net_of(&bot, "2") != m.net_of(ldo, "2") {
            e.push(format!("stage48: {top} / {bot} must run from {ldo} IN to its GND"));
        }
        match (s48_res(m, &top), s48_res(m, &bot)) {
            (Some(t), Some(b)) => {
                let (lo, hi, corner) = s48_en_window(t, b, *vin_min, *vin_max, *vin_corner);
                if lo < S48_VEN_HI || hi > S48_VEN_MAX || corner > S48_VEN_MAX {
                    e.push(format!(
                        "stage48: {ldo} EN {lo:.3}-{hi:.3} V (corner {corner:.3} V) outside VEN(HI) {S48_VEN_HI} .. {S48_VEN_MAX} V"
                    ));
                }
            }
            _ => e.push(format!("stage48: {top} / {bot} have no resistor data (S48_RESISTORS)")),
        }
    }
    // B13 H1: the watchdog trips above VR max and below REF25 with U5 open, and its input stays in its 6.5 V range
    match (s48_res(m, "r_ref_wd_top"), s48_res(m, "r_ref_wd_bot")) {
        (Some(t), Some(b)) => {
            let (lo, hi) = s48_trip_window(t, b);
            let vr_max = m.resolved.get("u_ref").and_then(|p| reference_spec(p)).map(|s| s.0).unwrap_or(f64::NAN);
            let open = s48_u5_open_min(t.0 + b.0);
            if !(lo > vr_max) {
                e.push(format!("stage48: REF25 watchdog trips from {lo:.4} V, not above the reference maximum {vr_max:.4} V"));
            }
            if !(hi < open && open > S48_U5_OPEN_MIN_FLOOR) {
                e.push(format!("stage48: REF25 watchdog trips up to {hi:.4} V, not below REF25 with U5 open ({open:.4} V)"));
            }
        }
        _ => e.push("stage48: r_ref_wd_top / r_ref_wd_bot have no resistor data (S48_RESISTORS)".into()),
    }
    // B13 H2: the readback resistor is >= 160 k, so a J4.1-J4.9 short holds PERMIT_GATE below VIL 0.8 V with the two
    // 100 k pulldowns (3.3 V x 50 k / (50 k + R) < 0.8 V needs R > 156 k)
    match s48_res(m, "r_bias_good_j4") {
        Some((r, tol, _)) if 3.6 * 50_000.0 * 1.01 / (50_000.0 * 1.01 + r * (1.0 - tol)) < 0.8 => {}
        _ => e.push("stage48: r_bias_good_j4 must be >= 160 k (a J4.1-J4.9 short must not lift PERMIT)".into()),
    }
}

fn audit(m: &Model) -> Vec<String> {
    let mut e = Vec::new();

    // 1. Identity. Atopile 0.2.69 writes a footprint-aliased libsource part
    //    into default.net (e.g. every 0603 resistor as one MPN, LM4040 as
    //    AO3400A), so the netlist part field is NOT an identity source. The
    //    per-instance resolved export is; the CSV BOM must agree with it for
    //    every designator, and safety-relevant paths carry the selected MPN.
    if m.resolved.len() != m.comps.len() {
        e.push(format!("resolved export has {} instances, netlist {}", m.resolved.len(), m.comps.len()));
    }
    for (r, c) in &m.comps {
        let want = m.resolved.get(&c.path);
        match (want, m.bom.get(r)) {
            (Some(w), Some(b)) if w == b => {}
            (w, b) => e.push(format!("{r} ({}) resolved {:?} vs BOM {:?}", c.path, w, b)),
        }
    }
    for (path, mpn) in IDENTITY {
        match m.resolved.get(*path) {
            Some(p) if p == mpn => {}
            Some(p) => e.push(format!("{path} is {p} not {mpn}")),
            None => e.push(format!("{path} missing")),
        }
    }

    // 2. Isolation boundary. Only barrier parts may touch both domains, and
    //    each of their pins must sit on the declared side.
    let selv: BTreeSet<&str> = SELV_NETS.iter().copied().collect();
    let mut side: BTreeMap<String, (bool, bool)> = BTreeMap::new(); // ref -> (touches selv, touches hot)
    for (net, nodes) in &m.nets {
        let is_selv = selv.contains(net.as_str());
        let single = nodes.len() <= 1; // NC stubs carry no potential
        for (r, _) in nodes {
            if single {
                continue;
            }
            let s = side.entry(r.clone()).or_default();
            if is_selv { s.0 = true } else { s.1 = true }
        }
    }
    for (r, (s, h)) in &side {
        if *s && *h {
            let path = &m.comps[r].path;
            // PE is separate from live HOT, but is outside SELV_NETS. Only the
            // exact functional link below may join PE and the controller return.
            if path != "r_fe" && !BARRIER_PARTS.iter().any(|(p, _, _)| p == path) {
                e.push(format!("{r} ({path}) bridges SELV and HOT nets"));
            }
        }
    }
    for (path, mpn, selv_pins) in BARRIER_PARTS {
        let Some(r) = m.reff(path) else {
            e.push(format!("barrier part {path} missing"));
            continue;
        };
        if m.resolved.get(*path).map(String::as_str) != Some(*mpn) {
            e.push(format!("barrier part {path} is {:?} not {mpn}", m.resolved.get(*path)));
        }
        for (net, nodes) in &m.nets {
            for (rr, pin) in nodes {
                if rr != r || nodes.len() <= 1 {
                    continue;
                }
                let want_selv = selv_pins.contains(&pin.as_str());
                if want_selv != selv.contains(net.as_str()) {
                    e.push(format!("{path}.{pin} on {net} crosses to the wrong side of the barrier"));
                }
            }
        }
    }

    for path in SPARE_CHANNEL_PARTS {
        for pin in ["5", "12"] {
            if let Some(n) = m.net_of(path, pin) {
                if members(m, &n).len() > 1 {
                    e.push(format!("{path}.{pin} is the isolator's spare channel and must stay unconnected, found on {n}"));
                }
            }
        }
    }

    expect(&mut e, m, "r_fe", "1", "pe");
    expect(&mut e, m, "r_fe", "2", "selv_gnd");

    // 3. Mains entry: the fuse is the only path from the inlet L terminal.
    let l_in = members(m, "ac_l_in");
    let want: BTreeSet<(String, String)> = [("j_mains", "1"), ("f1", "1")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if l_in != want {
        e.push(format!("ac_l_in must be exactly J1.1 and F1.1, found {:?}", l_in));
    }
    expect(&mut e, m, "j_mains", "2", "ac_n_in");
    if m.net_of("j_mains", "3").is_some() {
        e.push("j_mains.3 must not exist on the L/N-only inlet".into());
    }
    // The cord's primary PE bond is made directly at the chassis stud.
    // J_PE is a separately wired PCB branch, not that protective bond.
    expect(&mut e, m, "j_pe", "1", "pe");
    expect(&mut e, m, "j_pe", "2", "pe");
    expect(&mut e, m, "cy1", "1", "l_filt");
    expect(&mut e, m, "cy2", "1", "n_filt");
    let pe = members(m, "pe");
    let want: BTreeSet<(String, String)> = [
        ("j_pe", "1"), ("j_pe", "2"), ("r_fe", "1"),
        ("cy1", "2"), ("cy2", "2"),
    ].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if pe != want {
        e.push(format!("pe must join only the PE branch, Y capacitors and functional link, found {pe:?}"));
    }
    // Common-mode choke: TDK windings are 1-4 (line) and 2-3 (neutral).
    expect(&mut e, m, "l1", "1", "l_f");
    expect(&mut e, m, "l1", "4", "l_filt");
    expect(&mut e, m, "l1", "2", "ac_n_in");
    expect(&mut e, m, "l1", "3", "n_filt");

    // 4. Stage 21 (DECISIONS 25): BR1 feeds BUS_P / HV_RET directly; the removable rail links
    //    are gone and floating bring-up leaves BR1 unfitted (its holes are the bench landings).
    //    BR1's minus must land on HV_RET, the capacitor side of the shunt, never LEG_RET: the
    //    hv_ret membership check below catches a rectifier return that bypasses the shunt.
    expect(&mut e, m, "br1", "1", "bus_p");
    expect(&mut e, m, "br1", "4", "hv_ret");
    for gone in ["rect_p", "rect_n"] {
        if m.nets.contains_key(gone) {
            e.push(format!("{gone} exists: the rectifier must feed the bus directly (stage 21)"));
        }
    }
    // Shoot-through shunt: every low-side source returns via LEG_RET.
    expect(&mut e, m, "r_shunt", "1", "leg_ret");
    expect(&mut e, m, "r_shunt", "2", "ocp_kelvin_p");
    expect(&mut e, m, "r_shunt", "3", "ocp_kelvin_n");
    expect(&mut e, m, "r_shunt", "4", "hv_ret");
    for leg in ["leg_a", "leg_b"] {
        expect(&mut e, m, &format!("{leg}.q_low"), "3", "leg_ret");
        expect(&mut e, m, &format!("{leg}.q_high"), "2", "bus_p");
    }
    for c in ["c_bus1", "c_bus2"] {
        expect(&mut e, m, c, "1", "bus_p");
        expect(&mut e, m, c, "2", "bus_p");
        expect(&mut e, m, c, "3", "hv_ret");
        expect(&mut e, m, c, "4", "hv_ret");
    }
    for c in ["c_hf_a1", "c_hf_a2", "c_hf_b1", "c_hf_b2"] {
        expect(&mut e, m, c, "1", "bus_p");
        expect(&mut e, m, c, "2", "hv_ret");
    }
    // The TVS must protect the capacitor side of the shunt, not bridge the
    // shunt and hide a fault current from the DC return measurement.
    // Stage 14: two TVS in series; the midpoint is the R3/R4 bleed midpoint.
    expect(&mut e, m, "tvs_bus", "1", "bus_p");
    expect(&mut e, m, "tvs_bus", "2", "busbleed_mid");
    expect(&mut e, m, "tvs_bus_b", "1", "busbleed_mid");
    expect(&mut e, m, "tvs_bus_b", "2", "hv_ret");
    let hv = members(m, "hv_ret");
    let want: BTreeSet<(String, String)> = [
        ("c_bus1", "3"), ("c_bus1", "4"),
        ("c_bus2", "3"), ("c_bus2", "4"),
        ("r_bus2", "2"), ("r_shunt", "4"), ("tvs_bus_b", "2"),
        ("c_hf_a1", "2"), ("c_hf_a2", "2"),
        ("c_hf_b1", "2"), ("c_hf_b2", "2"),
        ("br1", "4"),
    ].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if hv != want {
        e.push(format!("hv_ret has unexpected or missing members, possibly bypassing the shunt: {hv:?}"));
    }

    // Stage 17: the 1 mOhm CSS2H sits on Bourns' Kelvin land (sense fingers net-tied to the current
    // pads in the footprint, pads 1-4 as for the WSK it replaces).
    if let Some(reference) = m.reff("r_shunt") {
        if m.comps[reference].footprint != "temper:R_Shunt_Bourns_CSS2H-2512_Kelvin" {
            e.push("r_shunt footprint must be the Bourns CSS2H-2512 Kelvin land".into());
        }
    }
    expect(&mut e, m, "c_v15", "2", "n_ls");
    // Gate recharge must not use the sense terminal. All analog returns
    // are a separate loaded Kelvin island; its finite error needs testing.
    for (path, pin) in members(m, "ocp_kelvin_p") {
        if path.starts_with("leg_") || path == "ps_gate" || path == "c_v15" {
            e.push(format!("gate recharge return {path}.{pin} must not load ocp_kelvin_p"));
        }
    }

    let expected_kelvin: BTreeSet<(String, String)> = [
        ("c_div", "2"),
        ("c_hot5_schmitt", "2"),
        ("c_hot5_uv", "2"),
        ("c_iso1", "2"),
        ("c_ldo_in", "2"),
        ("c_ldo_out", "2"),
        ("c_nand_vcc", "2"),
        ("c_ocp_node", "2"),
        ("c_ocp_vcc", "2"),
        ("c_ovp_th", "2"),
        ("c_ovp_vcc", "2"),
        ("c_th", "2"),
        ("c_vs1", "2"),
        ("c_vs1_1u", "2"), // AMC1311 VDD1 1 uF beside c_vs1 (SBAS786C section 10; stage 10)
        ("r_div_bot", "2"),
        ("r_hot5_uv_bot", "2"),
        ("r_ovp_bot", "2"),
        ("r_shunt", "2"),
        ("r_th_bot", "2"),
        ("u_hot5_schmitt", "3"),
        ("u_hot5_uv", "2"),
        // stage 48: U14 INB (pin 4) is the REF25 watchdog input now; its divider bottom and U3's EN divider bottom
        // return here (0.034 / 0.122-0.130 mA, in the Kelvin census)
        ("r_ref_wd_bot", "2"),
        ("r_ldo_en_bot", "2"),
        ("u_iso", "1"),
        ("u_iso", "7"),
        ("u_ldo", "2"),
        ("u_nand", "2"),
        ("u_ocp", "2"),
        ("u_ovp", "2"),
        ("u_ref", "2"),
        ("u_vsense", "3"),
        ("u_vsense", "4"),
    ].iter().map(|(path, pin)| (path.to_string(), pin.to_string())).collect();
    if members(m, "ocp_kelvin_p") != expected_kelvin {
        e.push("ocp_kelvin_p exact analog-return membership differs".into());
    }

    // 5. Legs: fail-safe DIS, dead time, F6 bias and gate hold-offs.
    for (leg, sw) in [("leg_a", "sw_a"), ("leg_b", "sw_b")] {
        // stage 22: DIS = NAND(permit_gate, bias_good); pins checked in audit_f6 (dis_or A/B/Y)
        let pg = format!("{leg}-permit_gate");
        expect(&mut e, m, &format!("{leg}.driver"), "5", &format!("{leg}-driver_dis"));
        expect(&mut e, m, &format!("{leg}.dis_or"), "1", &pg);
        expect(&mut e, m, &format!("{leg}.r_permit_pd"), "1", &pg);
        expect(&mut e, m, &format!("{leg}.r_permit_pd"), "2", "selv_gnd");
        expect(&mut e, m, &format!("{leg}.r_permit"), "1", "permit");
        expect(&mut e, m, &format!("{leg}.r_dt"), "2", "selv_gnd");
        expect(&mut e, m, &format!("{leg}.driver"), "11", "v15_ls");
        expect(&mut e, m, &format!("{leg}.driver"), "9", "n_ls");
        expect(&mut e, m, &format!("{leg}.q_high"), "1", &format!("{leg}-gate_h"));
        expect(&mut e, m, &format!("{leg}.q_high"), "3", sw);
        expect(&mut e, m, &format!("{leg}.q_low"), "1", &format!("{leg}-gate_l"));
        expect(&mut e, m, &format!("{leg}.q_low"), "2", sw);
        expect(&mut e, m, &format!("{leg}.r_gh_pd"), "2", sw);
        expect(&mut e, m, &format!("{leg}.r_gl_pd"), "2", "leg_ret");
    }
    expect(&mut e, m, "leg_a.driver", "1", "pwm_ha");
    expect(&mut e, m, "leg_a.driver", "2", "pwm_la");
    expect(&mut e, m, "leg_b.driver", "1", "pwm_hb");
    expect(&mut e, m, "leg_b.driver", "2", "pwm_lb");

    // 6. Thermal cutoffs gate the gate-driver supply: PS2 line input only
    //    through the TCO loop header; N_LS is split below the LEG_RET midpoint.
    expect(&mut e, m, "j_tco", "1", "l_filt");
    expect(&mut e, m, "j_tco", "2", "tco_l");
    expect(&mut e, m, "ps_gate", "1", "tco_l"); // IRM-20 pin 1 = AC/L
    expect(&mut e, m, "ps_gate", "2", "n_filt");
    expect(&mut e, m, "ps_gate", "4", "v24_raw");
    expect(&mut e, m, "ps_gate", "3", "n_ls");
    let tco: BTreeSet<String> = members(m, "tco_l").into_iter().map(|(p, _)| p).collect();
    if tco != ["j_tco", "ps_gate"].iter().map(|s| s.to_string()).collect() {
        e.push(format!("tco_l must join only the TCO header and PS2, found {:?}", tco));
    }
    // Blower-supply tap (stage 16): fused after F1 and the filter, a branch of its own to J11.
    // Reference-transfer caps (stage 19b; 5 stage 40; 6-12 stage 44; 13-15 stage 48): each joins the two SELV reference
    // planes, v3v3 (In1) and selv_gnd (In2).
    for i in 1..=15 {
        let p = format!("c_ref_xfer_{i}");
        expect(&mut e, m, &p, "1", "v3v3");
        expect(&mut e, m, &p, "2", "selv_gnd");
    }
    expect(&mut e, m, "f_blw", "1", "l_filt");
    expect(&mut e, m, "f_blw", "2", "blw_l");
    expect(&mut e, m, "r_blw", "1", "blw_l");
    expect(&mut e, m, "r_blw", "2", "blw_lr");
    expect(&mut e, m, "j_blw_ac", "1", "blw_lr");
    expect(&mut e, m, "j_blw_ac", "2", "n_filt");
    let blw: BTreeSet<String> = members(m, "blw_l").into_iter().map(|(p, _)| p).collect();
    if blw != ["f_blw", "r_blw"].iter().map(|s| s.to_string()).collect() {
        e.push(format!("blw_l must join only F2 and the limiter R_blw, found {:?}", blw));
    }
    let blwr: BTreeSet<String> = members(m, "blw_lr").into_iter().map(|(p, _)| p).collect();
    if blwr != ["r_blw", "j_blw_ac"].iter().map(|s| s.to_string()).collect() {
        e.push(format!("blw_lr must join only the limiter R_blw and J11, found {:?}", blwr));
    }
    // Stage 38 (candidate 23, DECISIONS 47 item 1): no mains-to-SELV supply on this board. PS1 is deleted and the
    // controller logic runs from PS3 over the controller's J13; only PS2 (TCO_L / N_FILT -> HOT V24_RAW) is mains-fed.
    if m.reff("ps_selv").is_some() {
        e.push("ps_selv (PS1) is back: stage 38 deleted it (the controller logic runs from PS3 over J13)".into());
    }
    for (path, mpn) in &m.resolved {
        if mpn.starts_with("IRM-") {
            e.push(format!("{path} is {mpn}: the IRM supplies' 0.25 mA leakage cannot meet the touch-current budget (DECISIONS 47)"));
        }
    }
    // stage 48 (OPEN-ITEMS S19): EN from the divider, never on IN (SBVS186H 7.4 p.13)
    expect(&mut e, m, "u_ldo", "3", "hot5_en");
    expect(&mut e, m, "u_ldo", "1", "v15_ls");
    expect(&mut e, m, "u_ldo", "5", "hot5");

    // 7. OCP and OVP: node = offset + shunt Kelvin; bus-sense node vs the
    //    OVP threshold; both OK-high comparators and V15-powered HOT5 monitor
    //    NANDed into the default-high
    //    isolator, isolator output on header pin 10.
    expect(&mut e, m, "r_ref_bias", "1", "hot5");
    expect(&mut e, m, "r_ref_bias", "2", "ref25");
    let ref25 = members(m, "ref25");
    let want: BTreeSet<(String, String)> = [
        ("r_ref_bias", "2"), ("u_ref", "1"), ("r_ocp_ref", "1"),
        ("r_th_top", "1"), ("r_ovp_top", "1"),
        ("r_ref_wd_top", "1"),   // stage 48 (B13 H1): the REF25 watchdog divider
    ]
    .iter()
    .map(|(path, pin)| (path.to_string(), pin.to_string()))
    .collect();
    if ref25 != want {
        e.push(format!("ref25 has unexpected loads: {ref25:?}"));
    }
    let bias_ohm = match m.resolved.get("r_ref_bias").map(String::as_str) {
        Some("0603WAF5601T5E") => Some(5_600.0),
        Some("RC0603FR-076K8L") => Some(6_800.0),
        _ => None, // The identity check reports unknown resistor selections.
    };
    let ref_spec = m.resolved.get("u_ref").and_then(|p| reference_spec(p)); // unknown parts: the identity check
    if let (Some(bias_ohm), Some((ref_max, ref_min, iz_min, iz_win))) = (bias_ohm, ref_spec) {
        let cathode_ua = min_reference_cathode_current_ua(bias_ohm, ref_max);
        if cathode_ua < iz_min {
            e.push(format!("reference cathode current {cathode_ua:.1} uA is below the {iz_min:.0} uA full-temperature minimum"));
        }
        let ceiling_ua = max_reference_cathode_current_ua(bias_ohm, ref_min);
        if ceiling_ua > iz_win {
            e.push(format!("reference cathode current ceiling {ceiling_ua:.1} uA is above the {iz_win:.0} uA current-regulation window"));
        }
    }
    expect(&mut e, m, "r_ocp_sense", "2", "ocp_kelvin_n");
    expect(&mut e, m, "r_ocp_ref", "1", "ref25");
    expect(&mut e, m, "r_ocp_ref", "2", "ocp_node");
    expect(&mut e, m, "r_ocp_sense", "1", "ocp_node");
    expect(&mut e, m, "u_ocp", "3", "ocp_node");
    expect(&mut e, m, "u_ocp", "4", "ocp_thresh");
    expect(&mut e, m, "u_ocp", "1", "ocp_ok_hot");
    expect(&mut e, m, "u_ocp", "2", "ocp_kelvin_p");
    expect(&mut e, m, "u_ovp", "3", "ovp_thresh");
    expect(&mut e, m, "u_ovp", "4", "vsense_in");
    expect(&mut e, m, "u_ovp", "1", "ovp_ok_hot");
    expect(&mut e, m, "u_ovp", "2", "ocp_kelvin_p");
    expect(&mut e, m, "u_ovp", "5", "hot5");
    expect(&mut e, m, "r_ovp_top", "1", "ref25");
    expect(&mut e, m, "r_ovp_top", "2", "ovp_thresh");
    expect(&mut e, m, "r_ovp_bot", "1", "ovp_thresh");
    expect(&mut e, m, "r_ovp_bot", "2", "ocp_kelvin_p");
    expect(&mut e, m, "r_th_top", "1", "ref25");
    expect(&mut e, m, "r_th_top", "2", "ocp_thresh");
    expect(&mut e, m, "r_th_bot", "1", "ocp_thresh");
    expect(&mut e, m, "r_th_bot", "2", "ocp_kelvin_p");
    // stage 48 (B13 H1): VDD on HOT5 (an INB-VDD pin 4-5 short then stays inside INB's 7 V rating, SBVS187G 6.1
    // p.5); INB- watches REF25 and OUTB joins OUTA on hot5_uv_raw
    expect(&mut e, m, "u_hot5_uv", "5", "hot5");
    expect(&mut e, m, "u_hot5_uv", "2", "ocp_kelvin_p");
    expect(&mut e, m, "u_hot5_uv", "3", "hot5_uv_sense");
    expect(&mut e, m, "u_hot5_uv", "4", "ref25_wd");
    expect(&mut e, m, "u_hot5_uv", "1", "hot5_uv_raw");
    expect(&mut e, m, "u_hot5_uv", "6", "hot5_uv_raw");
    expect(&mut e, m, "r_hot5_uv_top", "1", "hot5");
    expect(&mut e, m, "r_hot5_uv_top", "2", "hot5_uv_sense");
    expect(&mut e, m, "r_hot5_uv_bot", "1", "hot5_uv_sense");
    expect(&mut e, m, "r_hot5_uv_bot", "2", "ocp_kelvin_p");
    expect(&mut e, m, "r_hot5_uv_pull", "1", "hot5");
    expect(&mut e, m, "r_hot5_uv_pull", "2", "hot5_uv_raw");
    expect(&mut e, m, "u_hot5_schmitt", "2", "hot5_uv_raw");
    expect(&mut e, m, "u_hot5_schmitt", "3", "ocp_kelvin_p");
    expect(&mut e, m, "u_hot5_schmitt", "4", "hot5_ok_hot");
    expect(&mut e, m, "u_hot5_schmitt", "5", "hot5");
    expect(&mut e, m, "c_hot5_uv", "1", "hot5");   // stage 48: decouples U14 VDD on HOT5
    expect(&mut e, m, "c_hot5_uv", "2", "ocp_kelvin_p");
    expect(&mut e, m, "c_hot5_schmitt", "1", "hot5");
    expect(&mut e, m, "c_hot5_schmitt", "2", "ocp_kelvin_p");
    for (net, wanted) in [
        ("hot5_uv_sense", vec![("u_hot5_uv", "3"), ("r_hot5_uv_top", "2"), ("r_hot5_uv_bot", "1")]),
        ("hot5_uv_raw", vec![("u_hot5_uv", "1"), ("u_hot5_uv", "6"), ("r_hot5_uv_pull", "2"), ("u_hot5_schmitt", "2")]),
        ("ref25_wd", vec![("u_hot5_uv", "4"), ("r_ref_wd_top", "2"), ("r_ref_wd_bot", "1")]),
        ("hot5_en", vec![("u_ldo", "3"), ("r_ldo_en_top", "2"), ("r_ldo_en_bot", "1")]),
        ("hot5_ok_hot", vec![("u_hot5_schmitt", "4"), ("u_nand", "6")]),
    ] {
        let want: BTreeSet<(String, String)> = wanted.iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
        if members(m, net) != want {
            e.push(format!("{net} has unexpected loads: {:?}", members(m, net)));
        }
    }
    expect(&mut e, m, "u_nand", "1", "ocp_ok_hot");
    expect(&mut e, m, "u_nand", "3", "ovp_ok_hot");
    expect(&mut e, m, "u_nand", "6", "hot5_ok_hot");
    expect(&mut e, m, "u_nand", "4", "bus_fault_hot");
    expect(&mut e, m, "u_nand", "2", "ocp_kelvin_p");
    expect(&mut e, m, "u_nand", "5", "hot5");
    expect(&mut e, m, "u_iso", "4", "bus_fault_hot");
    let bus_fault: BTreeSet<(String, String)> = members(m, "bus_fault_hot");
    let want: BTreeSet<(String, String)> = [("u_nand", "4"), ("u_iso", "4")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if bus_fault != want {
        e.push(format!("bus_fault_hot must join only the NAND output and the isolator input, found {:?}", bus_fault));
    }
    expect(&mut e, m, "u_iso", "13", "bus_fault_iso");
    let iso_out = members(m, "bus_fault_iso");
    // stage 30: 1 k / 100 pF (r_bf / c_bf) between the isolator and the fault OR filters CMTI upsets
    let want: BTreeSet<(String, String)> = [("u_iso", "13"), ("r_bf", "1")]
        .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if iso_out != want {
        e.push(format!("bus_fault_iso must join only the isolator output and the filter resistor, found {:?}", iso_out));
    }
    expect(&mut e, m, "r_bf", "2", "bus_fault_flt");
    expect(&mut e, m, "c_bf", "1", "bus_fault_flt");
    expect(&mut e, m, "c_bf", "2", "selv_gnd");
    let flt = members(m, "bus_fault_flt");
    let want: BTreeSet<(String, String)> = [("r_bf", "2"), ("c_bf", "1"), ("u_fault_or", "1")]
        .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if flt != want {
        e.push(format!("bus_fault_flt must join only r_bf, c_bf and the fault OR input, found {:?}", flt));
    }
    // BUS_FAULT = OR(isolated bus fault, CT over-current either polarity).
    // The receiving pullup is off-board. Added local loads or another driver
    // could suppress the fault while all existing pin checks still pass.
    expect(&mut e, m, "u_fault_or", "4", "bus_fault");
    let fault_output = members(m, "bus_fault");
    let want: BTreeSet<(String, String)> = [("u_fault_or", "4"), ("j_selv", "10")]
        .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if fault_output != want {
        e.push(format!("bus_fault has unexpected loads: {:?}", fault_output));
    }
    expect(&mut e, m, "u_iso", "3", "hot5");
    expect(&mut e, m, "u_ref", "1", "ref25");
    expect(&mut e, m, "u_ref", "2", "ocp_kelvin_p");
    // stage 47: pin 3 has no internal connection and must float or tie to pin 2 (SNOS455H 4 p.3; SLOS456Q p.4 the
    // same); here it floats on its own single-pad net
    expect(&mut e, m, "u_ref", "3", "u_ref-nc");
    let want: BTreeSet<(String, String)> = [("u_ref", "3")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if members(m, "u_ref-nc") != want {
        e.push(format!("u_ref-nc has unexpected members: {:?}", members(m, "u_ref-nc")));
    }

    // 8. Tank: SW_A -> CT primary -> coil terminal -> C_res bank -> SW_B.
    //    The CT primary must sit on the switch node, not the resonant node.
    expect(&mut e, m, "t_ct", "1", "sw_a");
    expect(&mut e, m, "t_ct", "2", "coil_feed");
    expect(&mut e, m, "j_coil", "1", "coil_feed");
    expect(&mut e, m, "j_coil_return", "1", "res_a");
    for c in ["c_res1", "c_res2", "c_res3", "c_res4", "c_res5"] {
        expect(&mut e, m, c, "1", "res_a");
        expect(&mut e, m, c, "2", "sw_b");
    }
    let feed: BTreeSet<(String, String)> = members(m, "coil_feed");
    let want: BTreeSet<(String, String)> = [("t_ct", "2"), ("j_coil", "1")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if feed != want {
        e.push(format!("coil_feed must join only CT P2 and the coil terminal, found {:?}", feed));
    }
    let res_a: BTreeSet<String> = members(m, "res_a").into_iter().map(|(p, _)| p).collect();
    if res_a != ["j_coil_return", "c_res1", "c_res2", "c_res3", "c_res4", "c_res5", "r_crb1"].iter().map(|s| s.to_string()).collect() {
        e.push(format!("res_a must join only the coil return, the resonant bank and its bleed, found {:?}", res_a));
    }
    // Resonant-bank bleed: four series resistors from RES_A to SW_B.
    let chain = ["res_a", "crbleed_1", "crbleed_2", "crbleed_3", "sw_b"];
    for (i, r) in ["r_crb1", "r_crb2", "r_crb3", "r_crb4"].iter().enumerate() {
        expect(&mut e, m, r, "1", chain[i]);
        expect(&mut e, m, r, "2", chain[i + 1]);
    }

    // 9. Bus sense also feeds OVP: every divider join must be intact.
    let divider = ["bus_p", "vdiv_1", "vdiv_2", "vdiv_3", "vsense_in"];
    for (i, path) in ["r_div1", "r_div2", "r_div3", "r_div4"].iter().enumerate() {
        expect(&mut e, m, path, "1", divider[i]);
        expect(&mut e, m, path, "2", divider[i + 1]);
    }
    expect(&mut e, m, "r_div_bot", "1", "vsense_in");
    expect(&mut e, m, "r_div_bot", "2", "ocp_kelvin_p");
    let sense_members: BTreeSet<(String, String)> = [
        ("r_div4", "2"), ("r_div_bot", "1"), ("c_div", "1"),
        ("u_vsense", "2"), ("u_ovp", "4"),
    ].iter().map(|(path, pin)| (path.to_string(), pin.to_string())).collect();
    if members(m, "vsense_in") != sense_members {
        e.push("vsense_in has unexpected loads or missing endpoints".into());
    }
    expect(&mut e, m, "u_vsense", "2", "vsense_in");
    expect(&mut e, m, "u_vsense", "3", "ocp_kelvin_p"); // SHTDN low = enabled
    expect(&mut e, m, "u_vsense", "7", "vbus_p");
    expect(&mut e, m, "u_vsense", "6", "vbus_n");

    // 10. Controller header map.
    let header = [
        "bias_good_j4", "selv_gnd", "v3v3", "selv_gnd", "pwm_ha", "pwm_la", "pwm_hb", "pwm_lb",
        "permit", "bus_fault", "vbus_p", "vbus_n", "ct_zc", "ct_mon", "selv_gnd", "line_zc",
    ];
    for (i, net) in header.iter().enumerate() {
        expect(&mut e, m, "j_selv", &(i + 1).to_string(), net);
    }
    // stage 38: pin 1 carried PS1's 15 V and was then left not connected. Stage 48 (B13 H2): it carries only
    // BIAS_GOOD through r_bias_good_j4, so nothing on this board can drive J4.1 harder than 3.3 V / 220 k
    let j41: BTreeSet<(String, String)> = [("j_selv", "1"), ("r_bias_good_j4", "2")]
        .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if members(m, "bias_good_j4") != j41 {
        e.push(format!("bias_good_j4 (J4 pin 1) must join only J4.1 and the readback resistor, found {:?}", members(m, "bias_good_j4")));
    }
    expect(&mut e, m, "r_bias_good_j4", "1", "bias_good");
    stage48_checks(m, &mut e);
    stage49_checks(m, &mut e);
    stage51_checks(m, &mut e);
    stage52_checks(m, &mut e);

    // 11. Tank CT: the secondary is terminated on this board, at the CT, and
    //     never reaches the connector (an open secondary spikes to hundreds of
    //     volts: validation-results/06-controller-interface).
    expect(&mut e, m, "t_ct", "3", "ct_s1");
    expect(&mut e, m, "t_ct", "4", "ct_s2");
    expect(&mut e, m, "r_ct_burden", "1", "ct_s1");
    expect(&mut e, m, "r_ct_burden", "2", "ct_s2");
    for net in ["ct_s1", "ct_s2"] {
        if members(m, net).iter().any(|(p, _)| p == "j_selv") {
            e.push(format!("CT secondary {net} reaches the SELV header; terminate it on this board"));
        }
    }
    let s1: BTreeSet<(String, String)> = [("t_ct", "3"), ("r_ct_burden", "1"), ("c_ct_burden", "1"), ("r_ct_series", "1")]
        .iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if members(m, "ct_s1") != s1 {
        e.push(format!("ct_s1 must join only the CT, burden, burden capacitor and series input, found {:?}", members(m, "ct_s1")));
    }
    // Bias midpoint: 1 k / 1 k from V3V3, bypassed; also the zero-cross reference.
    expect(&mut e, m, "r_ct_bias_top", "1", "v3v3");
    expect(&mut e, m, "r_ct_bias_top", "2", "ct_s2");
    expect(&mut e, m, "r_ct_bias_bot", "1", "ct_s2");
    expect(&mut e, m, "r_ct_bias_bot", "2", "selv_gnd");
    expect(&mut e, m, "c_ct_bias", "1", "ct_s2");
    expect(&mut e, m, "c_ct_bias", "2", "selv_gnd");
    expect(&mut e, m, "r_ct_series", "2", "ct_sense_mon");
    expect(&mut e, m, "d_ct_hi", "2", "ct_sense_mon"); // anode
    expect(&mut e, m, "d_ct_hi", "1", "v3v3");         // cathode
    expect(&mut e, m, "d_ct_lo", "1", "ct_sense_mon"); // cathode
    expect(&mut e, m, "d_ct_lo", "2", "selv_gnd");     // anode
    // Trip references: REF_HI = 3.3 * 10/12.21, REF_LO = 3.3 * 2.21/12.21 (stage 15: 64.55-76.09 A band).
    expect(&mut e, m, "r_ct_hi_top", "1", "v3v3");
    expect(&mut e, m, "r_ct_hi_top", "2", "ct_ref_hi");
    expect(&mut e, m, "r_ct_hi_bot", "1", "ct_ref_hi");
    expect(&mut e, m, "r_ct_hi_bot", "2", "selv_gnd");
    expect(&mut e, m, "r_ct_lo_top", "1", "v3v3");
    expect(&mut e, m, "r_ct_lo_top", "2", "ct_ref_lo");
    expect(&mut e, m, "r_ct_lo_bot", "1", "ct_ref_lo");
    expect(&mut e, m, "r_ct_lo_bot", "2", "selv_gnd");
    // TLV3201 DBV: 1 OUT, 2 GND, 3 IN+, 4 IN-, 5 VCC.
    for (u, inp, inn, out) in [("u_ct_pos", "ct_sense_mon", "ct_ref_hi", "ct_oc_pos"),
                               ("u_ct_neg", "ct_ref_lo", "ct_sense_mon", "ct_oc_neg"),
                               ("u_ct_zc", "ct_sense_mon", "ct_s2", "ct_zc")] {
        expect(&mut e, m, u, "3", inp);
        expect(&mut e, m, u, "4", inn);
        expect(&mut e, m, u, "1", out);
        expect(&mut e, m, u, "5", "v3v3");
        expect(&mut e, m, u, "2", "selv_gnd");
    }
    // LVC1G332 DBV: 1 A, 2 GND, 3 B, 4 Y, 5 VCC, 6 C.
    expect(&mut e, m, "u_fault_or", "1", "bus_fault_flt");
    expect(&mut e, m, "u_fault_or", "3", "ct_oc_pos");
    expect(&mut e, m, "u_fault_or", "6", "ct_oc_neg");
    expect(&mut e, m, "u_fault_or", "5", "v3v3");
    expect(&mut e, m, "u_fault_or", "2", "selv_gnd");
    expect(&mut e, m, "r_ct_mon", "1", "ct_sense_mon");
    expect(&mut e, m, "r_ct_mon", "2", "ct_mon");
    for (net, want) in [("ct_zc", [("u_ct_zc", "1"), ("j_selv", "13")]),
                        ("ct_mon", [("r_ct_mon", "2"), ("j_selv", "14")])] {
        let w: BTreeSet<(String, String)> = want.iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
        if members(m, net) != w {
            e.push(format!("{net} has unexpected loads: {:?}", members(m, net)));
        }
    }

    // 12. Dead-time window: each leg's DT resistor must keep the estimated
    //     driver dead time inside the simulated window (FINDINGS F7).
    for leg in ["leg_a", "leg_b"] {
        let path = format!("{leg}.r_dt");
        let Some(mpn) = m.resolved.get(&path) else {
            e.push(format!("{path}: no resolved part"));
            continue;
        };
        match DT_RESISTORS.iter().find(|(p, ..)| p == mpn) {
            None => e.push(format!(
                "{path}: dead-time resistor {mpn} has no tolerance/TCR data; add it to DT_RESISTORS with a datasheet citation"
            )),
            Some(&(_, r, tol, tcr)) => {
                let (lo, hi) = dead_time_window_ns(r, tol, tcr);
                if lo < DT_WINDOW_NS.0 || hi > DT_WINDOW_NS.1 {
                    e.push(format!(
                        "{path}: {mpn} gives estimated dead time {lo:.1}-{hi:.1} ns, outside the simulated window {}-{} ns",
                        DT_WINDOW_NS.0, DT_WINDOW_NS.1
                    ));
                }
            }
        }
    }
    audit_f6::audit_f6(m, &mut e);
    e
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (net, csv, res) = match (args.get(1), args.get(2), args.get(3)) {
        (Some(a), Some(b), Some(c)) => (a.clone(), b.clone(), c.clone()),
        _ => {
            eprintln!("usage: audit <default.net> <default.csv> <resolved-components.json>");
            std::process::exit(2);
        }
    };
    let m = load(
        &fs::read_to_string(&net).expect("net"),
        &fs::read_to_string(&csv).expect("csv"),
        &fs::read_to_string(&res).expect("resolved"),
    )
    .expect("parse");
    let errs = audit(&m);
    println!("components {}, nets {}", m.comps.len(), m.nets.len());
    if errs.is_empty() {
        println!("PASS: power-stage-120v connectivity audit");
    } else {
        for e in &errs {
            println!("FAIL: {e}");
        }
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(super) fn built() -> Model {
        load(include_str!("frozen/default.net"), include_str!("frozen/default.csv"), include_str!("frozen/resolved-components.json")).unwrap()
    }

    fn fails(m: &Model, needle: &str) {
        let errs = audit(m);
        assert!(errs.iter().any(|e| e.contains(needle)), "expected a failure mentioning {needle:?}, got {errs:#?}");
    }

    #[test]
    fn built_netlist_passes() {
        let errs = audit(&built());
        assert!(errs.is_empty(), "{errs:#?}");
    }

    #[test]
    fn analog_reference_returns_cannot_move_to_power_island() {
        for (path, pin) in [("u_ldo", "2"), ("u_iso", "1"), ("c_ldo_in", "2")] {
            let mut m = built();
            m.rewire(path, pin, "leg_ret");
            fails(&m, "ocp_kelvin_p exact analog-return membership");
        }
    }

    #[test]
    fn wrong_low_ohm_shunt_footprint_fails() {
        let mut m = built();
        let reference = m.reff("r_shunt").unwrap().to_string();
        // the stage-16 WSK land no longer matches the part
        m.comps.get_mut(&reference).unwrap().footprint = "Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T2.21mm".into();
        fails(&m, "r_shunt footprint");
    }

    #[test]
    fn kelvin_positive_must_not_be_copper_joined_to_power_return() {
        let mut m = built();
        m.rewire("r_shunt", "2", "leg_ret");
        fails(&m, "r_shunt.2");
    }

    #[test]
    fn supply_recharge_cannot_return_through_sense_terminal() {
        for path in ["ps_gate", "c_v15"] {
            let mut m = built();
            let pin = if path == "ps_gate" { "3" } else { "2" };
            m.rewire(path, pin, "ocp_kelvin_p");
            fails(&m, "gate recharge return");
        }
    }

    #[test]
    fn low_side_source_bypassing_shunt_fails() {
        let mut m = built();
        m.rewire("leg_b.q_low", "3", "hv_ret");
        fails(&m, "leg_b.q_low.3");
    }

    #[test]
    fn swapped_shunt_current_terminals_fail() {
        let mut m = built();
        m.rewire("r_shunt", "1", "hv_ret");
        m.rewire("r_shunt", "4", "leg_ret");
        fails(&m, "r_shunt.1");
    }

    #[test]
    fn dis_nand_inputs_cannot_be_swapped_or_bypassed() {
        // stage 22: a DIS NAND input off permit_gate / bias_good, or its output off the driver's DIS, must fail
        let mut m = built();
        m.rewire("leg_a.dis_or", "1", "v3v3");
        fails(&m, "leg_a.dis_or.1");
        let mut m = built();
        m.rewire("leg_b.dis_or", "2", "v3v3");
        fails(&m, "leg_b.dis_or.2");
        let mut m = built();
        m.rewire("u_bias_flt", "4", "hb_hold");
        fails(&m, "u_bias_flt.4");
    }

    #[test]
    fn permit_gate_without_pulldown_fails() {
        let mut m = built();
        m.rewire("leg_b.r_permit_pd", "2", "leg_ret");
        fails(&m, "leg_b.r_permit_pd.2");
    }

    #[test]
    fn gate_supply_bypassing_tco_fails() {
        let mut m = built();
        m.rewire("ps_gate", "1", "l_filt");
        fails(&m, "ps_gate.1");
    }

    #[test]
    fn irm20_line_neutral_swap_fails() {
        let mut m = built();
        m.rewire("ps_gate", "1", "n_filt");
        m.rewire("ps_gate", "2", "tco_l");
        fails(&m, "ps_gate.2");
    }

    #[test]
    fn selv_ground_tied_to_hot_fails() {
        let mut m = built();
        m.rewire("leg_a.r_permit_pd", "2", "leg_ret");
        fails(&m, "bridges SELV and HOT");
    }

    #[test]
    fn csv_fields_handle_quoted_commas() {
        assert_eq!(csv_fields(r#""BAT54H,115","D4,D5",fp,"BAT54H,115",0.00"#).unwrap(),
                   vec!["BAT54H,115", "D4,D5", "fp", "BAT54H,115", "0.00"]);
        assert_eq!(csv_fields("TLV3201AIDBVR,U6,fp,x,0").unwrap()[1], "U6");
        assert!(csv_fields(r#""open,1"#).is_err());
    }

    #[test]
    fn ct_secondary_on_header_fails() {
        let mut m = built();
        m.rewire("j_selv", "13", "ct_s1");
        fails(&m, "CT secondary ct_s1 reaches the SELV header");
    }

    #[test]
    fn missing_ct_burden_fails() {
        let mut m = built();
        m.rewire("r_ct_burden", "1", "floating_test");
        fails(&m, "r_ct_burden.1");
    }

    #[test]
    fn ct_fault_bypassing_or_fails() {
        let mut m = built();
        m.rewire("u_fault_or", "3", "selv_gnd");
        fails(&m, "u_fault_or.3");
    }

    #[test]
    fn swapped_ct_clamp_fails() {
        let mut m = built();
        m.rewire("d_ct_hi", "1", "ct_sense_mon");
        m.rewire("d_ct_hi", "2", "v3v3");
        fails(&m, "d_ct_hi");
    }

    #[test]
    fn isolator_output_on_hot_side_fails() {
        let mut m = built();
        m.rewire("u_iso", "13", "ocp_ok_hot");
        fails(&m, "wrong side of the barrier");
    }

    #[test]
    fn default_low_isolator_fails() {
        let mut m = built();
        m.set_part("u_iso", "CA-IS3720LW");
        fails(&m, "u_iso is CA-IS3720LW");
    }

    #[test]
    fn isolator_spare_output_tied_to_rail_fails() {
        for path in ["u_iso", "hb.iso"] {   // stage 40: bias_hb.verdict is gone
            let mut m = built();
            m.rewire(path, "12", "v3v3");
            fails(&m, "spare channel");
        }
        let mut m = built();
        m.rewire("hb.iso", "5", "n_ls");
        fails(&m, "spare channel");
    }

    #[test]
    fn and_gate_with_healthy_high_output_fails() {
        let mut m = built();
        m.set_part("u_nand", "SN74LVC1G08DBVR");
        fails(&m, "u_nand is SN74LVC1G08DBVR");
    }

    #[test]
    fn missing_hot5_supervisor_fails() {
        let mut m = built();
        let r = m.reff("u_hot5_uv").unwrap().to_string();
        m.comps.remove(&r);
        m.bom.remove(&r);
        m.resolved.remove("u_hot5_uv");
        for nodes in m.nets.values_mut() { nodes.retain(|(rr, _)| rr != &r); }
        fails(&m, "u_hot5_uv missing");
    }

    #[test]
    fn hot5_supervisor_vdd_on_hot5() {
        // stage 48 (B13 H1): VDD moved V15_LS -> HOT5 so an INB-VDD short stays inside INB's 7 V rating; back on
        // V15_LS must fail
        let mut m = built();
        m.rewire("u_hot5_uv", "5", "v15_ls");
        fails(&m, "u_hot5_uv.5");
    }

    #[test]
    fn hot5_supervisor_cannot_bypass_fault_gate() {
        let mut m = built();
        m.rewire("u_nand", "6", "hot5");
        fails(&m, "u_nand.6");
    }

    #[test]
    fn hot5_slow_open_drain_cannot_feed_nand_directly() {
        let mut m = built();
        m.rewire("u_nand", "6", "hot5_uv_raw");
        fails(&m, "u_nand.6");
    }

    #[test]
    fn hot5_supervisor_cannot_pull_pushpull_ocp() {
        let mut m = built();
        m.rewire("u_hot5_uv", "1", "ocp_ok_hot");
        fails(&m, "u_hot5_uv.1");
    }

    #[test]
    fn fault_header_disconnected_from_isolator_fails() {
        let mut m = built();
        m.rewire("j_selv", "10", "floating");
        fails(&m, "j_selv.10");
    }

    #[test]
    fn extra_fault_output_load_fails() {
        for other_net in ["selv_gnd", "permit"] {
            let mut m = built();
            let path = "r_fault_load";
            let mpn = "0603WAF0000T5E";
            m.comps.insert("R999".into(), Comp { path: path.into(), part: mpn.into(), footprint: String::new() });
            m.resolved.insert(path.into(), mpn.into());
            m.bom.insert("R999".into(), mpn.into());
            m.nets.get_mut("bus_fault").unwrap().insert(("R999".into(), "1".into()));
            m.nets.get_mut(other_net).unwrap().insert(("R999".into(), "2".into()));
            fails(&m, "bus_fault has unexpected loads");
        }
    }

    #[test]
    fn functional_earth_link_to_live_hot_fails() {
        let mut m = built();
        m.rewire("r_fe", "1", "leg_ret");
        fails(&m, "r_fe.1");
    }

    #[test]
    fn disconnected_functional_earth_link_fails() {
        let mut m = built();
        m.rewire("r_fe", "2", "floating");
        fails(&m, "r_fe.2");
    }

    #[test]
    fn swapped_ocp_comparator_inputs_fail() {
        let mut m = built();
        m.rewire("u_ocp", "3", "ocp_thresh");
        m.rewire("u_ocp", "4", "ocp_node");
        fails(&m, "u_ocp.3");
    }

    #[test]
    fn resonant_capacitor_bypass_fails() {
        let mut m = built();
        m.rewire("j_coil_return", "1", "sw_b");
        fails(&m, "j_coil_return.1");
    }

    #[test]
    fn ct_on_resonant_node_fails() {
        let mut m = built();
        m.rewire("t_ct", "1", "res_a");
        m.rewire("j_coil_return", "1", "sw_a");
        fails(&m, "t_ct.1");
    }

    #[test]
    fn missing_resonant_bleed_fails() {
        let mut m = built();
        m.rewire("r_crb4", "2", "floating");
        fails(&m, "r_crb4.2");
    }

    #[test]
    fn swapped_ovp_comparator_inputs_fail() {
        let mut m = built();
        m.rewire("u_ovp", "3", "vsense_in");
        m.rewire("u_ovp", "4", "ovp_thresh");
        fails(&m, "u_ovp.3");
    }

    #[test]
    fn ovp_bypassing_isolator_path_fails() {
        let mut m = built();
        m.rewire("u_iso", "4", "ocp_ok_hot");
        fails(&m, "u_iso.4");
    }

    #[test]
    fn stage14_ocp_top_leg_fails() {
        // 12.4 k puts the shunt low corner at 47.3 A, under the 28 A envelope peak + pickup + margin (64.17 A).
        let mut m = built();
        m.set_part("r_th_top", "RT0603BRD0712K4L");
        fails(&m, "r_th_top is RT0603BRD0712K4L");
    }

    #[test]
    fn stage14_ct_references_fail() {
        // 3.32 k references put the CT trip at 50.56-60.01 A, inside the 28 A envelope (59.2 A peak).
        for path in ["r_ct_hi_top", "r_ct_lo_bot"] {
            let mut m = built();
            m.set_part(path, "RT0603BRD073K32L");
            fails(&m, &format!("{path} is RT0603BRD073K32L"));
        }
    }

    #[test]
    fn reference_transfer_caps_must_join_the_selv_planes() {
        // A transfer cap moved off v3v3 / selv_gnd (or a different part) must fail.
        let mut m = built();
        m.rewire("c_ref_xfer_2", "1", "hot5");
        fails(&m, "c_ref_xfer_2.1");
        let mut m = built();
        m.rewire("c_ref_xfer_4", "2", "n_ls");
        fails(&m, "c_ref_xfer_4.2");
        let mut m = built();
        m.set_part("c_ref_xfer_1", "CL10A106KP8NNNC");
        fails(&m, "c_ref_xfer_1 is CL10A106KP8NNNC");
    }

    #[test]
    fn blower_tap_must_be_fused_after_the_filter() {
        // F2 ahead of F1 / the EMI filter, or J11 bypassing F2, must fail.
        let mut m = built();
        m.rewire("f_blw", "1", "ac_l_in");
        fails(&m, "f_blw.1");
        let mut m = built();
        m.rewire("j_blw_ac", "1", "l_filt");
        fails(&m, "j_blw_ac.1");
        let mut m = built();
        m.set_part("f_blw", "3403.0201");
        fails(&m, "f_blw is 3403.0201");
        // stage 28: the limiter bypassed (J11 straight on F2's output) or the old 200 A UMT 250 must fail
        let mut m = built();
        m.rewire("j_blw_ac", "1", "blw_l");
        fails(&m, "j_blw_ac.1");
        let mut m = built();
        m.set_part("f_blw", "3403.0171");
        fails(&m, "f_blw is 3403.0171");
    }

    #[test]
    fn old_91a_threshold_fails() {
        let mut m = built();
        m.set_part("r_th_bot", "RT0603BRD079K76L");
        fails(&m, "r_th_bot is RT0603BRD079K76L");
    }

    #[test]
    fn old_reference_bias_fails_full_temperature_corner() {
        // the 6.8 k bias on the LM4040A25I (80 uA IZ,min) is the regression this guards
        let mut m = built();
        m.set_part("u_ref", "LM4040A25IDBZR");
        m.set_part("r_ref_bias", "RC0603FR-076K8L");
        fails(&m, "reference cathode current");
    }

    #[test]
    fn missing_bus_tvs_fails() {
        let mut m = built();
        let r = m.reff("tvs_bus").unwrap().to_string();
        m.comps.remove(&r);
        m.bom.remove(&r);
        m.resolved.remove("tvs_bus");
        for nodes in m.nets.values_mut() {
            nodes.retain(|(node_ref, _)| node_ref != &r);
        }
        fails(&m, "tvs_bus missing");
    }

    #[test]
    fn stage16_wsk_shunt_identity_fails() {
        // stage 17 (DECISIONS 17): the 1 W WSK25121L000FEA fails derating at 28 A
        let mut m = built();
        m.set_part("r_shunt", "WSK25121L000FEA");
        fails(&m, "r_shunt is WSK25121L000FEA");
    }

    #[test]
    fn wrong_bus_tvs_mpn_fails() {
        let mut m = built();
        m.set_part("tvs_bus", "30KPA160CA");
        fails(&m, "tvs_bus is 30KPA160CA");
    }

    #[test]
    fn bus_tvs_wrong_link_fails() {
        let mut m = built();
        m.rewire("tvs_bus", "1", "sw_a");
        fails(&m, "tvs_bus.1");
    }

    #[test]
    fn bus_tvs_bypassing_shunt_fails() {
        let mut m = built();
        m.rewire("tvs_bus_b", "2", "leg_ret");
        fails(&m, "tvs_bus_b.2");
    }

    #[test]
    fn old_coil_terminal_block_fails() {
        let mut m = built();
        m.set_part("j_coil", "1711725");
        fails(&m, "j_coil is 1711725");
    }

    #[test]
    fn old_three_position_mains_terminal_fails() {
        let mut m = built();
        m.set_part("j_mains", "1711039");
        fails(&m, "j_mains is 1711039");
    }

    #[test]
    fn pe_branch_to_mains_fails() {
        let mut m = built();
        m.rewire("j_pe", "2", "ac_n_in");
        fails(&m, "j_pe.2");
    }

    #[test]
    fn y_capacitor_line_side_must_follow_its_mains_conductor() {
        let mut m = built();
        m.rewire("cy2", "1", "l_filt");
        fails(&m, "cy2.1");
    }

    #[test]
    fn missing_pe_branch_fails() {
        let mut m = built();
        let r = m.reff("j_pe").unwrap().to_string();
        m.comps.remove(&r);
        m.bom.remove(&r);
        m.resolved.remove("j_pe");
        for nodes in m.nets.values_mut() {
            nodes.retain(|(rr, _)| rr != &r);
        }
        fails(&m, "j_pe missing");
    }

    #[test]
    fn wrong_bulk_capacitor_and_one_mispaired_pad_fail() {
        let mut m = built();
        m.set_part("c_bus1", "942C6W2P5K-F");
        fails(&m, "c_bus1 is 942C6W2P5K-F");
        let mut m = built();
        m.rewire("c_bus2", "2", "hv_ret");
        fails(&m, "c_bus2.2");
    }

    #[test]
    fn local_bus_capacitor_cannot_bypass_shunt() {
        for path in ["c_hf_a1", "c_hf_a2", "c_hf_b1", "c_hf_b2"] {
            let mut m = built();
            m.rewire(path, "2", "leg_ret");
            fails(&m, &format!("{path}.2"));
        }
    }

    #[test]
    fn local_bus_capacitor_identity_is_pinned() {
        let mut m = built();
        m.set_part("c_hf_b2", "B32652A1104K000");
        fails(&m, "c_hf_b2 is B32652A1104K000");
    }

    #[test]
    fn rectifier_feeds_bus_and_returns_on_the_capacitor_side_of_the_shunt() {
        // stage 21: BR1 minus on LEG_RET would bypass the OCP shunt for the rectifier current
        let mut m = built();
        m.rewire("br1", "4", "leg_ret");
        fails(&m, "br1.4");
        let mut m = built();
        m.rewire("br1", "1", "floating_test");
        fails(&m, "br1.1");
    }

    #[test]
    fn coil_return_terminal_must_be_separate_and_m4() {
        let mut m = built();
        m.rewire("j_coil_return", "1", "coil_feed");
        fails(&m, "j_coil_return.1");
        let mut m = built();
        m.set_part("j_coil_return", "1711725");
        fails(&m, "j_coil_return is 1711725");
        // stage 35: the THR 74650074 needs a 1.6-2.0 mm board (DECISIONS 42); the SMT 7466004R replaces it
        let mut m = built();
        m.set_part("j_coil", "74650074");
        fails(&m, "j_coil is 74650074");
    }

    #[test]
    fn stage42_gate_network_holds() {
        // candidate 39 (DECISIONS 54): the 8.2 ohm 1206 turn-on resistor or the 1 nF Cgs back on any gate must fail
        let mut m = built();
        m.set_part("leg_b.r_gl", "RS-06L8R20FT");
        fails(&m, "leg_b.r_gl is RS-06L8R20FT");
        let mut m = built();
        m.set_part("leg_a.cgs_h", "C0603C102J5GACTU");
        fails(&m, "leg_a.cgs_h is C0603C102J5GACTU");
    }

    #[test]
    fn stage43_snubber_mpn_holds() {
        // the non-existent GRM31A5C3A102JW01D back on any drain-source snubber must fail
        let mut m = built();
        m.set_part("leg_b.c_snub_l", "GRM31A5C3A102JW01D");
        fails(&m, "leg_b.c_snub_l is GRM31A5C3A102JW01D");
    }

    #[test]
    fn stage44_selv_transfer_caps_hold() {
        // candidate 44: a stage-44 transfer cap off the SELV planes, or a different part, must fail
        let mut m = built();
        m.rewire("c_ref_xfer_8", "1", "bias_good");
        fails(&m, "c_ref_xfer_8.1");
        let mut m = built();
        m.rewire("c_ref_xfer_12", "2", "permit");
        fails(&m, "c_ref_xfer_12.2");
        let mut m = built();
        m.set_part("c_ref_xfer_6", "CL10A106KP8NNNC");
        fails(&m, "c_ref_xfer_6 is CL10A106KP8NNNC");
    }

    #[test]
    fn stage45_rail_monitor_values_hold() {
        // S16 (DECISIONS 59, option 1c-4420): the TL431A reference, the 10 k halfref top or any pre-stage-45 tap value
        // back on a rail monitor must fail (the windows overlap the rails' worst-case tolerance with those values)
        let mut m = built();
        m.set_part("bias_ha.monitor.reference", "TL431AIDBZR");
        fails(&m, "bias_ha.monitor.reference is TL431AIDBZR");
        let mut m = built();
        m.set_part("monitor_ls.rhalf_top", "RT0603BRD0710KL");
        fails(&m, "monitor_ls.rhalf_top is RT0603BRD0710KL");
        let mut m = built();
        m.set_part("bias_hb.monitor.rspanov_top", "ARG03BTC1333");
        fails(&m, "bias_hb.monitor.rspanov_top is ARG03BTC1333");
        let mut m = built();
        m.set_part("monitor_ls.rspanuv_bot", "RT0603BRD0710KL");
        fails(&m, "monitor_ls.rspanuv_bot is RT0603BRD0710KL");
        let mut m = built();
        m.set_part("bias_ha.monitor.ruv_top", "RT0603BRD074K42L");
        fails(&m, "bias_ha.monitor.ruv_top is RT0603BRD074K42L");
        let mut m = built();
        m.set_part("bias_hb.monitor.rov_top", "RT0603BRD077K68L");
        fails(&m, "bias_hb.monitor.rov_top is RT0603BRD077K68L");
    }

    #[test]
    fn stage46_monitor_grades_hold() {
        // S17 hot copper (b3-ratings monitor-probes-2026-10-15): the 85 C grades back on any rail monitor must fail;
        // at the c18 @ 61 release case the LM339B rows read -11.6..-17.9 K and the TL431BI rows up to -7.7 K
        let mut m = built();
        m.set_part("monitor_ls.reference", "TL431BIDBZR");
        fails(&m, "monitor_ls.reference is TL431BIDBZR");
        let mut m = built();
        m.set_part("bias_hb.monitor.reference", "TL431BIDBZR");
        fails(&m, "bias_hb.monitor.reference is TL431BIDBZR");
        let mut m = built();
        m.set_part("monitor_ls.monitor", "LM339BIDR");
        fails(&m, "monitor_ls.monitor is LM339BIDR");
        let mut m = built();
        m.set_part("bias_ha.monitor.monitor", "LM339BIDR");
        fails(&m, "bias_ha.monitor.monitor is LM339BIDR");
    }

    #[test]
    fn stage48_ldo_en_ref_watch_holds() {
        let m = built();
        assert!(audit(&m).is_empty(), "{:#?}", audit(&m));
        // S19: EN back on IN must fail, on U3 and on each monitor LDO
        let mut m = built();
        m.rewire("u_ldo", "3", "v15_ls");
        fails(&m, "stage48: u_ldo.3 (EN)");
        for (ldo, inn) in [("monitor_ls.ldo5", "v15_ls"), ("bias_ha.monitor.ldo5", "p_ha"), ("bias_hb.monitor.ldo5", "p_hb")] {
            let mut m = built();
            m.rewire(ldo, "3", inn);
            fails(&m, &format!("stage48: {ldo}.3 (EN)"));
        }
        // the catalog grade back must fail
        let mut m = built();
        m.set_part("u_ldo", "TPS70950DBVR");
        fails(&m, "u_ldo is TPS70950DBVR");
        // a divider that lets EN pass 6.5 V at the IN maximum must fail by arithmetic (27 k top / 100 k bottom swapped)
        let t = (27_000.0, 0.01, 100.0);
        let b = (100_000.0, 0.01, 100.0);
        assert!(s48_en_window(t, b, 14.5, 15.46, 16.68).1 > S48_VEN_MAX);
        // and the chosen one holds: EN 2.987-3.41 V on U3, <= 4.11 V at the 18.643 V span-OV corner on U37-U39
        let (lo, hi, _) = s48_en_window(b, t, 14.5, 15.46, 16.68);
        assert!(lo > 2.98 && lo < 2.99 && hi < 3.42, "{lo} {hi}");
        let (_, _, c) = s48_en_window(b, t, 16.575, 17.43, 18.643);
        assert!(c < 4.12, "{c}");
        // H1: the trip window 2.526-2.610 V sits above VR max 2.5162 V and below REF25 with U5 open
        let (lo, hi) = s48_trip_window((63_400.0, 0.001, 25.0), (11_700.0, 0.001, 25.0));
        assert!(lo > 2.5162 && lo < 2.527 && hi > 2.609 && hi < 2.611, "{lo} {hi}");
        assert!(s48_u5_open_min(75_100.0) > 2.80);
        // a 10 k / 10 k watchdog trips at ~0.8 V (fails: below VR) and a 105 k / 10 k one at ~4.6 V (U5 open missed)
        let mut m = built();
        m.set_part("r_ref_wd_top", "TNPW060311K7BEEA");
        fails(&m, "stage48: REF25 watchdog trips from");
        // INB back on the Kelvin net, or OUTB left open, must fail
        let mut m = built();
        m.rewire("u_hot5_uv", "4", "ocp_kelvin_p");
        fails(&m, "u_hot5_uv.4");
        let mut m = built();
        m.rewire("u_hot5_uv", "6", "ref25");
        fails(&m, "u_hot5_uv.6");
        // H2: a 1 k readback (a J4.1-J4.9 short would lift PERMIT) must fail; J4.1 straight onto BIAS_GOOD must fail
        let mut m = built();
        m.set_part("r_bias_good_j4", "0603WAF1001T5E");
        fails(&m, "stage48: r_bias_good_j4 must be >= 160 k");
        let mut m = built();
        m.rewire("j_selv", "1", "bias_good");
        fails(&m, "j_selv.1");
    }

    #[test]
    fn stage51_dual_pitch_bank_holds() {
        // c51-bank-source: KNSCHA fitted on the dual-pitch footprint passes; the TDK alternate on it fails only the
        // identity row (it is the documented drop-in, not the fitted part); the stage-49 P22.5-only footprint fails
        let m = built();
        assert!(audit(&m).is_empty(), "{:#?}", audit(&m));
        let mut m = built();
        m.set_part("c_res2", "B32643B8104J000");
        fails(&m, "c_res2 is B32643B8104J000");
        assert!(!audit(&m).iter().any(|x| x.starts_with("stage51") || x.starts_with("stage49")), "{:#?}", audit(&m));
        let mut m = built();
        let r = m.reff("c_res3").unwrap().to_string();
        m.comps.get_mut(&r).unwrap().footprint = "temper:TDK_B32643B_P22.5_W14.5_L26.5_Radial".into();
        fails(&m, "stage51: c_res3 footprint");
        let mut m = built();
        m.set_part("c_res5", "R75UR31004030J");
        fails(&m, "stage51: c_res5 (R75UR31004030J)");
        fails(&m, "stage49: c_res5 (R75UR31004030J) has no bank voltage rating");
    }

    #[test]
    fn stage52_proto_bom_holds() {
        // b15-proto-alternates / c51-bank-source: the prototype BOM passes; each documented alternate on the same footprint
        // (production L1 2203, P01F Y caps, KNSCHA / B32643B bank) fails only its identity row; an unqualified part fails
        // the stage-52 / stage-51 whitelist
        let m = built();
        assert!(audit(&m).is_empty(), "{:#?}", audit(&m));
        for (path, alt) in [("l1", "B82726S2203A020"), ("cy1", "DE1E3RA222MA4BP01F"), ("c_res4", "MMK104J3DF1KN208G2"),
                            ("c_res1", "B32643B8104J000")] {
            let mut m = built();
            m.set_part(path, alt);
            fails(&m, &format!("{path} is {alt}"));
            assert!(!audit(&m).iter().any(|x| x.starts_with("stage5") || x.starts_with("stage49")), "{path}: {:#?}", audit(&m));
        }
        let mut m = built();
        m.set_part("l1", "B82726S2183N020");
        fails(&m, "stage52: l1 (B82726S2183N020)");
        let mut m = built();
        m.set_part("cy2", "DE1E3RA222MA4BQ01F");
        fails(&m, "stage52: cy2 (DE1E3RA222MA4BQ01F)");
        let mut m = built();
        let r = m.reff("cy1").unwrap().to_string();
        m.comps.get_mut(&r).unwrap().footprint = "temper:C_Disc_D12.0mm_P10.00mm".into();
        fails(&m, "stage52: cy1 footprint");
        let mut m = built();
        m.set_part("c_res3", "B32643H8823J000");
        fails(&m, "stage51: c_res3 (B32643H8823J000)");
        fails(&m, "stage49: c_res3 (B32643H8823J000) has no bank voltage rating");
    }

    #[test]
    fn stage50_heartbeat_gated_by_permit() {
        // c50-permit-gate: U46.A (hsb_good) takes PERMIT through R135 100 k; the stage-40 pull-up to v3v3 and the
        // 10 k part both fail (10 k: a U37 Hi-Z + v3v3-on-hsb_good double fault would put PERMIT at 1.58 V)
        let m = built();
        assert!(audit(&m).is_empty(), "{:#?}", audit(&m));
        assert_eq!(m.net_of("hb.rgate", "1").as_deref(), Some("permit"));
        assert_eq!(m.net_of("hb.rgate", "2").as_deref(), Some("hsb_good"));
        let mut m = built();
        m.rewire("hb.rgate", "1", "v3v3");
        fails(&m, "hb.rgate.1");
        let mut m = built();
        m.set_part("hb.rgate", "0603WAF1002T5E");
        fails(&m, "hb.rgate is 0603WAF1002T5E");
    }

    #[test]
    fn stage49_bank_and_ocp_divider_hold() {
        let m = built();
        assert!(audit(&m).is_empty(), "{:#?}", audit(&m));
        // B': the chosen divider holds 92.593 A at a 1.0185 V trip common mode; the as-built one sat at 1.204 V
        let (i, vcm) = s49_ocp_nominal(10_000.0, 7_500.0, 16_000.0, 11_000.0);
        assert!((i - 92.593).abs() < 0.05 && (vcm - 1.0185).abs() < 0.001, "{i} {vcm}");
        let (i0, vcm0) = s49_ocp_nominal(10_000.0, 10_000.0, 12_600.0, 11_700.0);
        assert!((i0 - 92.593).abs() < 0.05 && vcm0 > 1.2, "{i0} {vcm0}");
        // the former bank part fails identity and its 1600 V rating fails F3 (1683 V = 1.05 x VR)
        let mut m = built();
        m.set_part("c_res4", "B32654A1104J000");
        fails(&m, "c_res4 is B32654A1104J000");
        fails(&m, "stage49: c_res4 (B32654A1104J000) VR 1600 V");
        // R33 back to 10 k with R34 / R35 new: the trip moves to ~138 A
        let mut m = built();
        m.set_part("r_ocp_sense", "RT0603BRD0710KL");
        fails(&m, "stage49: OCP nominal trip");
        // R34 / R35 swapped: the VCM leaves the window
        let mut m = built();
        m.set_part("r_th_top", "RT0603BRD0711KL");
        m.set_part("r_th_bot", "RT0603BRD0716KL");
        fails(&m, "stage49: U6 trip common mode");
        // the REF25 minimum current with the new loads and the watchdog together stays above IRMIN 65 uA
        let iz = min_reference_cathode_current_ua(5_600.0, 2.5162);
        assert!(iz > 65.0 && (iz - 98.8).abs() < 0.1, "{iz}");
        let open = s48_u5_open_min(75_100.0);
        let (_, wd_hi) = s48_trip_window((63_400.0, 0.001, 25.0), (11_700.0, 0.001, 25.0));
        assert!(open > 2.80 && wd_hi < open, "{open} {wd_hi}");
        // C30 x (R32 || R33): 429 ns with B' (500 ns as built); a C30 the table does not know fails
        let tau: f64 = 10_000.0 * 7_500.0 / 17_500.0 * 100e-12 * 1e9;
        assert!((tau - 428.6).abs() < 0.1 && tau <= S49_TAU_MAX_NS);
        let mut m = built();
        m.set_part("c_ocp_node", "CL10C151JB8NNNC");
        fails(&m, "stage49: c_ocp_node has no capacitance data");
    }

    #[test]
    fn stage47_ref25_grade_holds() {
        // S17 hot copper (c47-ref25-grade): U5 reads 88.9 C at the c17.5 @ 61 release case (s46 B3 probes), over the
        // LM4040A25I's 85 C; the 85 C grade back at REF25 must fail, and so must a pin 3 that is not left floating
        let mut m = built();
        m.set_part("u_ref", "LM4040A25IDBZR");
        fails(&m, "u_ref is LM4040A25IDBZR");
        let mut m = built();
        m.set_part("u_ref", "LM4050AIM3-2.5/NOPB");   // the industrial (85 C) range of the same die
        fails(&m, "u_ref is LM4050AIM3-2.5/NOPB");
        let mut m = built();
        let r = m.reff("u_ref").unwrap().to_string();
        m.nets.get_mut("u_ref-nc").unwrap().remove(&(r.clone(), "3".into()));
        m.nets.get_mut("hot5").unwrap().insert((r, "3".into()));
        fails(&m, "u_ref.3 on hot5");
        // a weaker bias that starves the LM4050 below its 65 uA IRMIN at the full-range corner must fail
        assert!(min_reference_cathode_current_ua(6_800.0 * 1.15, 2.5162) < 65.0);
    }

    #[test]
    fn stage38_supply_topology_holds() {
        // PS2 back to the IRM-20-24 (0.25 mA leakage) must fail, by identity and by the IRM rule
        let mut m = built();
        m.set_part("ps_gate", "IRM-20-24");
        fails(&m, "ps_gate is IRM-20-24");
        fails(&m, "IRM supplies");
        // anything else on J4 pin 1 (the former PS1 15 V, now the BIAS_GOOD readback) must fail
        let mut m = built();
        m.rewire("c_iso2", "1", "bias_good_j4");
        fails(&m, "bias_good_j4 (J4 pin 1)");
        let mut m = built();
        m.rewire("j_selv", "1", "v3v3");
        fails(&m, "j_selv.1");
    }

    #[test]
    fn extra_shunt_bypass_fails_exact_hv_ret_membership() {
        let mut m = built();
        let path = "shunt_bypass";
        let mpn = "RC1206FR-070RL";
        m.comps.insert("R999".into(), Comp { path: path.into(), part: mpn.into(), footprint: String::new() });
        m.resolved.insert(path.into(), mpn.into());
        m.bom.insert("R999".into(), mpn.into());
        m.nets.get_mut("hv_ret").unwrap().insert(("R999".into(), "1".into()));
        m.nets.get_mut("leg_ret").unwrap().insert(("R999".into(), "2".into()));
        fails(&m, "hv_ret has unexpected or missing members");
    }

    #[test]
    fn selected_reference_bias_covers_shunt_loading_corner() {
        let (vmax, vmin, izmin, izwin) = reference_spec("LM4050AEM3-2.5/NOPB").unwrap();
        assert!(min_reference_cathode_current_ua(5_600.0, vmax) >= izmin);
        assert!(max_reference_cathode_current_ua(5_600.0, vmin) <= izwin);
        let (vmax, _, izmin, _) = reference_spec("LM4040A25IDBZR").unwrap();
        assert!(min_reference_cathode_current_ua(5_600.0, vmax) >= izmin);
    }

    #[test]
    fn every_bus_divider_open_fails() {
        for path in ["r_div1", "r_div2", "r_div3", "r_div4", "r_div_bot"] {
            for pin in ["1", "2"] {
                let mut m = built();
                m.rewire(path, pin, "floating_divider");
                fails(&m, &format!("{path}.{pin}"));
            }
        }
    }

    #[test]
    fn extra_bus_sense_load_fails() {
        let mut m = built();
        m.rewire("r_bus1", "1", "vsense_in");
        fails(&m, "vsense_in has unexpected loads");
    }

    #[test]
    fn fuse_bypass_fails() {
        let mut m = built();
        m.rewire("rv1", "1", "ac_l_in");
        fails(&m, "ac_l_in must be exactly");
    }

    #[test]
    fn choke_winding_crossed_fails() {
        let mut m = built();
        m.rewire("l1", "2", "l_filt");
        m.rewire("l1", "4", "ac_n_in");
        fails(&m, "l1.4");
    }

    #[test]
    fn header_pin_swap_fails() {
        let mut m = built();
        m.rewire("j_selv", "5", "pwm_la");
        m.rewire("j_selv", "6", "pwm_ha");
        fails(&m, "j_selv.5");
    }

    #[test]
    fn bom_alias_fails() {
        let mut m = built();
        let r = m.reff("leg_a.r_dt").unwrap().to_string();
        m.bom.insert(r, "0603WAF1002T5E".into());
        fails(&m, "resolved Some(\"RT0603BRD0749K9L\") vs BOM");
    }

    #[test]
    fn resolved_identity_swap_fails() {
        let mut m = built();
        m.resolved.insert("u_ref".into(), "AO3400A".into());
        fails(&m, "u_ref");
    }

    #[test]
    fn f6_discharge_diode_reversed_fails() {
        let mut m = built();
        m.rewire("leg_a.doff_h", "2", "leg_a-off_h");
        m.rewire("leg_a.doff_h", "1", "leg_a-gate_h");
        fails(&m, "leg_a.doff_h.2");
    }

    #[test]
    fn dead_time_window_matches_c25() {
        // c25-driver/results/dt_window.json: 49.9 k 0.1 % 25 ppm -> 408.3-569.0 ns
        let (lo, hi) = dead_time_window_ns(49.9, 0.001, 25.0);
        assert!((lo - 408.3).abs() < 0.1 && (hi - 569.0).abs() < 0.1, "{lo} {hi}");
        let (lo, _) = dead_time_window_ns(39.0, 0.01, 100.0);
        assert!(lo < DT_WINDOW_NS.0, "{lo}");
    }

    #[test]
    fn old_39k_dead_time_resistor_fails_window() {
        let mut m = built();
        m.resolved.insert("leg_a.r_dt".into(), "RC0603FR-0739KL".into());
        fails(&m, "leg_a.r_dt: RC0603FR-0739KL gives estimated dead time");
    }

    #[test]
    fn standard_tolerance_49k9_inside_2edr_window() {
        // stage 29: with the 2EDR8259X and the F6-deck window (340-600 ns) the +-1 % 49.9 kOhm part gives about
        // 401-579 ns, inside; only the identity check still pins R9/R17 to the 0.1 % part
        let (lo, hi) = dead_time_window_ns(49.9, 0.01, 100.0);
        assert!(lo >= DT_WINDOW_NS.0 && hi <= DT_WINDOW_NS.1, "{lo} {hi}");
    }

    #[test]
    fn enable_polarity_sibling_2edr8258x_fails() {
        // 2EDR8258X has EN (active high, open = disabled), not DIS: the NAND drive would invert; it must fail
        let mut m = built();
        m.set_part("leg_a.driver", "2EDR8258XXUMA1");
        fails(&m, "barrier part leg_a.driver is Some(\"2EDR8258XXUMA1\")");
    }

    #[test]
    fn unknown_dead_time_resistor_fails() {
        let mut m = built();
        m.resolved.insert("leg_a.r_dt".into(), "RC0603FR-0751KL".into());
        fails(&m, "has no tolerance/TCR data");
    }
}
