//! Exact-pin safety audit of the 120 V full-bridge power stage netlist.
//!
//! Checks part identity, the HOT/SELV isolation boundary, and the
//! safety-relevant joins (fail-safe driver disable, shoot-through shunt
//! orientation, thermal-cutoff gate-supply loop, OCP polarity through the
//! default-low isolator, tank series path, controller header map).
//! Includes the conditional REF25 DC-bias corner in REFERENCE-BIAS.md;
//! no bus-voltage bound, timing, creepage or thermal qualification.
//!
//!   rustc --edition=2021 -O zapote/power-stage-120v/audit.rs -o /tmp/ps_audit
//!   /tmp/ps_audit zapote/power-stage-120v/frozen/default.net zapote/power-stage-120v/frozen/default.csv \
//!       zapote/power-stage-120v/frozen/resolved-components.json
//!   rustc --edition=2021 --test zapote/power-stage-120v/audit.rs -o /tmp/ps_audit_t && /tmp/ps_audit_t

use std::collections::{BTreeMap, BTreeSet};
use std::fs;

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
            m.comps.insert(r, Comp { path, part });
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
        // Comment,"Designator list",Footprint,LCSC,Price
        let (mpn, rest) = line.split_once(',').ok_or("bad csv line")?;
        let refs = if let Some(stripped) = rest.strip_prefix('"') {
            stripped.split_once('"').ok_or("unterminated designators")?.0.to_string()
        } else {
            rest.split(',').next().unwrap_or("").to_string()
        };
        for r in refs.split(',') {
            m.bom.insert(r.trim().to_string(), mpn.to_string());
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
    "v15_selv", "selv_gnd", "v3v3", "pwm_ha", "pwm_la", "pwm_hb", "pwm_lb", "permit",
    "bus_ocp_ok", "vbus_p", "vbus_n", "ct_s1", "ct_s2",
    "leg_a-dis", "leg_a-permit_gate", "leg_a.driver-dt",
    "leg_b-dis", "leg_b-permit_gate", "leg_b.driver-dt",
];

/// Parts allowed to have pins in both domains, and which pins are SELV.
const BARRIER_PARTS: &[(&str, &str, &[&str])] = &[
    ("leg_a.driver", "UCC21550BDWKR", &["1", "2", "3", "4", "5", "6", "7", "8"]),
    ("leg_b.driver", "UCC21550BDWKR", &["1", "2", "3", "4", "5", "6", "7", "8"]),
    ("u_vsense", "AMC1311BDWVR", &["5", "6", "7", "8"]),
    ("u_iso", "ISO7710FDWR", &["9", "13", "14", "16"]),
    ("t_ct", "CST3015-100ED", &["3", "4"]),
    ("ps_selv", "IRM-20-15", &["3", "4"]),
];

/// Safety-relevant part identities (path -> MPN).
const IDENTITY: &[(&str, &str)] = &[
    ("f1", "0326020.MXP"),
    ("rv1", "TMOV20RP175E"),
    ("br1", "GBJ2510-F"),
    ("r_shunt", "WSK2512R0010FEA"),
    ("leg_a.q_high", "IPW65R018CFD7"),
    ("leg_a.q_low", "IPW65R018CFD7"),
    ("leg_b.q_high", "IPW65R018CFD7"),
    ("leg_b.q_low", "IPW65R018CFD7"),
    ("u_iso", "ISO7710FDWR"),
    ("u_ocp", "TLV3201AIDBVR"),
    ("u_ovp", "TLV3201AIDBVR"),
    ("u_and", "SN74LVC1G08DBVR"),
    ("u_ref", "LM4040A25IDBZR"),
    ("u_ldo", "MC78L05ACHT1G"),
    ("r_ref_bias", "RC0603FR-075K6L"),
    ("r_ocp_ref", "RT0603BRD0710KL"),
    ("r_ocp_sense", "RT0603BRD0710KL"),
    // Trip thresholds: ~61 A OCP (10.5 k / 10.0 k) and ~280 V OVP (10 k / 140 k).
    ("r_th_top", "RT0603BRD0710K5L"),
    ("r_th_bot", "RT0603BRD0710KL"),
    ("r_ovp_top", "RT0603BRD0710KL"),
    ("r_ovp_bot", "RT0603BRD07140KL"),
    ("r_div1", "RC1206FR-07470KL"),
    ("r_div2", "RC1206FR-07470KL"),
    ("r_div3", "RC1206FR-07470KL"),
    ("r_div4", "RC1206FR-07470KL"),
    ("r_div_bot", "RT0603BRD0715K8L"),
    ("ps_gate", "IRM-05-15"),
    ("ps_selv", "IRM-20-15"),
    ("t_ct", "CST3015-100ED"),
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

/// Minimum LM4040 cathode current with the selected three REF25 loads. This
/// checks the reference's DC bias, not comparator response or trip timing.
fn min_reference_cathode_current_ua(bias_ohm: f64) -> f64 {
    // Source: MC78L05AC min 4.75 V, LM4040A25I 2.519 V maximum at
    // 100 uA plus 1 mV current-regulation shift, and 80 uA minimum cathode
    // current over its rated temperature range. The 1% bias resistor is
    // high; all three 0.1% thin-film load strings are low.
    let ref_max = 2.520;
    let bias_current = (4.75 - ref_max) / (bias_ohm * 1.01);
    // -0.15 V at OCP_KELVIN_N corresponds to 150 A through the 1 mΩ
    // shunt. This bounds loading beyond the nominal 51–71 A trip spread;
    // it does not assert that the power path survives a 150 A fault.
    let ocp_offset_load = (ref_max + 0.15) / (20_000.0 * 0.999);
    let ocp_threshold_load = ref_max / (20_500.0 * 0.999);
    let ovp_threshold_load = ref_max / (150_000.0 * 0.999);
    (bias_current - ocp_offset_load - ocp_threshold_load - ovp_threshold_load) * 1e6
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
            if !BARRIER_PARTS.iter().any(|(p, _, _)| p == path) {
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

    // 3. Mains entry: the fuse is the only path from the inlet L terminal.
    let l_in = members(m, "ac_l_in");
    let want: BTreeSet<(String, String)> = [("j_mains", "1"), ("f1", "1")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if l_in != want {
        e.push(format!("ac_l_in must be exactly J1.1 and F1.1, found {:?}", l_in));
    }
    expect(&mut e, m, "j_mains", "3", "pe");
    // Common-mode choke: TDK windings are 1-4 (line) and 2-3 (neutral).
    expect(&mut e, m, "l1", "1", "l_f");
    expect(&mut e, m, "l1", "4", "l_filt");
    expect(&mut e, m, "l1", "2", "ac_n_in");
    expect(&mut e, m, "l1", "3", "n_filt");

    // 4. Shoot-through shunt: every low-side source returns via LEG_RET,
    //    the bus caps and bridge minus sit on HV_RET, and the shunt is the
    //    only element joining them.
    expect(&mut e, m, "r_shunt", "1", "leg_ret");
    expect(&mut e, m, "r_shunt", "2", "leg_ret");
    expect(&mut e, m, "r_shunt", "3", "ocp_kelvin_n");
    expect(&mut e, m, "r_shunt", "4", "hv_ret");
    for leg in ["leg_a", "leg_b"] {
        expect(&mut e, m, &format!("{leg}.q_low"), "3", "leg_ret");
        expect(&mut e, m, &format!("{leg}.q_high"), "2", "bus_p");
    }
    expect(&mut e, m, "br1", "4", "hv_ret");
    for c in ["c_bus1", "c_bus2"] {
        expect(&mut e, m, c, "1", "bus_p");
        expect(&mut e, m, c, "2", "hv_ret");
    }
    let hv: Vec<_> = members(m, "hv_ret").into_iter().map(|(p, _)| p).collect();
    for p in &hv {
        if !matches!(p.as_str(), "br1" | "c_bus1" | "c_bus2" | "r_bus2" | "r_shunt") {
            e.push(format!("{p} on hv_ret would bypass the shunt"));
        }
    }

    // 5. Legs: fail-safe DIS, dead time, bootstrap and gate hold-offs.
    for (leg, sw) in [("leg_a", "sw_a"), ("leg_b", "sw_b")] {
        let dis = format!("{leg}-dis");
        let pg = format!("{leg}-permit_gate");
        expect(&mut e, m, &format!("{leg}.driver"), "5", &dis);
        expect(&mut e, m, &format!("{leg}.r_dis_pu"), "1", &dis);
        expect(&mut e, m, &format!("{leg}.r_dis_pu"), "2", "v3v3");
        expect(&mut e, m, &format!("{leg}.permit_fet"), "3", &dis);
        expect(&mut e, m, &format!("{leg}.permit_fet"), "2", "selv_gnd");
        expect(&mut e, m, &format!("{leg}.permit_fet"), "1", &pg);
        expect(&mut e, m, &format!("{leg}.r_permit_pd"), "1", &pg);
        expect(&mut e, m, &format!("{leg}.r_permit_pd"), "2", "selv_gnd");
        expect(&mut e, m, &format!("{leg}.r_permit"), "1", "permit");
        expect(&mut e, m, &format!("{leg}.r_dt"), "2", "selv_gnd");
        expect(&mut e, m, &format!("{leg}.driver"), "11", "v15_ls");
        expect(&mut e, m, &format!("{leg}.driver"), "9", "leg_ret");
        expect(&mut e, m, &format!("{leg}.driver"), "14", sw);
        expect(&mut e, m, &format!("{leg}.d_boot"), "2", "v15_ls");
        expect(&mut e, m, &format!("{leg}.d_boot"), "1", &format!("{leg}-boot"));
        expect(&mut e, m, &format!("{leg}.driver"), "16", &format!("{leg}-boot"));
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
    //    through the TCO loop header, output returns to LEG_RET.
    expect(&mut e, m, "j_tco", "1", "l_filt");
    expect(&mut e, m, "j_tco", "2", "tco_l");
    expect(&mut e, m, "ps_gate", "2", "tco_l"); // IRM-05 pin 2 = AC/L
    expect(&mut e, m, "ps_gate", "1", "n_filt");
    expect(&mut e, m, "ps_gate", "4", "v15_ls");
    expect(&mut e, m, "ps_gate", "3", "leg_ret");
    let tco: BTreeSet<String> = members(m, "tco_l").into_iter().map(|(p, _)| p).collect();
    if tco != ["j_tco", "ps_gate"].iter().map(|s| s.to_string()).collect() {
        e.push(format!("tco_l must join only the TCO header and PS2, found {:?}", tco));
    }
    expect(&mut e, m, "ps_selv", "1", "l_filt"); // IRM-20 pin 1 = AC/L
    expect(&mut e, m, "ps_selv", "2", "n_filt");
    expect(&mut e, m, "u_ldo", "3", "v15_ls");
    expect(&mut e, m, "u_ldo", "1", "hot5");

    // 7. OCP and OVP: node = offset + shunt Kelvin; bus-sense node vs the
    //    OVP threshold; both OK-high comparators ANDed into the default-low
    //    isolator, isolator output on header pin 10.
    expect(&mut e, m, "r_ref_bias", "1", "hot5");
    expect(&mut e, m, "r_ref_bias", "2", "ref25");
    let ref25 = members(m, "ref25");
    let want: BTreeSet<(String, String)> = [
        ("r_ref_bias", "2"), ("u_ref", "1"), ("r_ocp_ref", "1"),
        ("r_th_top", "1"), ("r_ovp_top", "1"),
    ]
    .iter()
    .map(|(path, pin)| (path.to_string(), pin.to_string()))
    .collect();
    if ref25 != want {
        e.push(format!("ref25 has unexpected loads: {ref25:?}"));
    }
    let bias_ohm = match m.resolved.get("r_ref_bias").map(String::as_str) {
        Some("RC0603FR-075K6L") => Some(5_600.0),
        Some("RC0603FR-076K8L") => Some(6_800.0),
        _ => None, // The identity check reports unknown resistor selections.
    };
    if let Some(bias_ohm) = bias_ohm {
        let cathode_ua = min_reference_cathode_current_ua(bias_ohm);
        if cathode_ua < 80.0 {
            e.push(format!("reference cathode current {cathode_ua:.1} uA is below the 80 uA full-temperature minimum"));
        }
    }
    expect(&mut e, m, "r_ocp_sense", "2", "ocp_kelvin_n");
    expect(&mut e, m, "r_ocp_ref", "1", "ref25");
    expect(&mut e, m, "r_ocp_ref", "2", "ocp_node");
    expect(&mut e, m, "r_ocp_sense", "1", "ocp_node");
    expect(&mut e, m, "u_ocp", "3", "ocp_node");
    expect(&mut e, m, "u_ocp", "4", "ocp_thresh");
    expect(&mut e, m, "u_ocp", "1", "ocp_ok_hot");
    expect(&mut e, m, "u_ocp", "2", "leg_ret");
    expect(&mut e, m, "u_ovp", "3", "ovp_thresh");
    expect(&mut e, m, "u_ovp", "4", "vsense_in");
    expect(&mut e, m, "u_ovp", "1", "ovp_ok_hot");
    expect(&mut e, m, "u_ovp", "2", "leg_ret");
    expect(&mut e, m, "u_ovp", "5", "hot5");
    expect(&mut e, m, "r_ovp_top", "1", "ref25");
    expect(&mut e, m, "r_ovp_top", "2", "ovp_thresh");
    expect(&mut e, m, "r_ovp_bot", "1", "ovp_thresh");
    expect(&mut e, m, "r_ovp_bot", "2", "leg_ret");
    expect(&mut e, m, "r_th_top", "1", "ref25");
    expect(&mut e, m, "r_th_top", "2", "ocp_thresh");
    expect(&mut e, m, "r_th_bot", "1", "ocp_thresh");
    expect(&mut e, m, "r_th_bot", "2", "leg_ret");
    expect(&mut e, m, "u_and", "1", "ocp_ok_hot");
    expect(&mut e, m, "u_and", "2", "ovp_ok_hot");
    expect(&mut e, m, "u_and", "4", "bus_ok_hot");
    expect(&mut e, m, "u_and", "3", "leg_ret");
    expect(&mut e, m, "u_and", "5", "hot5");
    expect(&mut e, m, "u_iso", "4", "bus_ok_hot");
    let bus_ok: BTreeSet<(String, String)> = members(m, "bus_ok_hot");
    let want: BTreeSet<(String, String)> = [("u_and", "4"), ("u_iso", "4")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if bus_ok != want {
        e.push(format!("bus_ok_hot must join only the AND output and the isolator input, found {:?}", bus_ok));
    }
    expect(&mut e, m, "u_iso", "13", "bus_ocp_ok");
    expect(&mut e, m, "u_iso", "3", "hot5");
    expect(&mut e, m, "u_ref", "1", "ref25");
    expect(&mut e, m, "u_ref", "2", "leg_ret");

    // 8. Tank: SW_A -> CT primary -> coil terminal -> C_res bank -> SW_B.
    //    The CT primary must sit on the switch node, not the resonant node.
    expect(&mut e, m, "t_ct", "1", "sw_a");
    expect(&mut e, m, "t_ct", "2", "coil_feed");
    expect(&mut e, m, "j_coil", "1", "coil_feed");
    expect(&mut e, m, "j_coil", "2", "res_a");
    for c in ["c_res1", "c_res2", "c_res3"] {
        expect(&mut e, m, c, "1", "res_a");
        expect(&mut e, m, c, "2", "sw_b");
    }
    let feed: BTreeSet<(String, String)> = members(m, "coil_feed");
    let want: BTreeSet<(String, String)> = [("t_ct", "2"), ("j_coil", "1")].iter().map(|(a, b)| (a.to_string(), b.to_string())).collect();
    if feed != want {
        e.push(format!("coil_feed must join only CT P2 and the coil terminal, found {:?}", feed));
    }
    let res_a: BTreeSet<String> = members(m, "res_a").into_iter().map(|(p, _)| p).collect();
    if res_a != ["j_coil", "c_res1", "c_res2", "c_res3", "r_crb1"].iter().map(|s| s.to_string()).collect() {
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
    expect(&mut e, m, "r_div_bot", "2", "leg_ret");
    let sense_members: BTreeSet<(String, String)> = [
        ("r_div4", "2"), ("r_div_bot", "1"), ("c_div", "1"),
        ("u_vsense", "2"), ("u_ovp", "4"),
    ].iter().map(|(path, pin)| (path.to_string(), pin.to_string())).collect();
    if members(m, "vsense_in") != sense_members {
        e.push("vsense_in has unexpected loads or missing endpoints".into());
    }
    expect(&mut e, m, "u_vsense", "2", "vsense_in");
    expect(&mut e, m, "u_vsense", "3", "leg_ret"); // SHTDN low = enabled
    expect(&mut e, m, "u_vsense", "7", "vbus_p");
    expect(&mut e, m, "u_vsense", "6", "vbus_n");

    // 10. Controller header map.
    let header = [
        "v15_selv", "selv_gnd", "v3v3", "selv_gnd", "pwm_ha", "pwm_la", "pwm_hb", "pwm_lb",
        "permit", "bus_ocp_ok", "vbus_p", "vbus_n", "ct_s1", "ct_s2", "selv_gnd", "selv_gnd",
    ];
    for (i, net) in header.iter().enumerate() {
        expect(&mut e, m, "j_selv", &(i + 1).to_string(), net);
    }
    expect(&mut e, m, "t_ct", "3", "ct_s1");
    expect(&mut e, m, "t_ct", "4", "ct_s2");
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

    fn built() -> Model {
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
    fn missing_dis_pullup_fails() {
        let mut m = built();
        m.rewire("leg_a.r_dis_pu", "2", "floating");
        fails(&m, "leg_a.r_dis_pu.2");
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
        m.rewire("ps_gate", "2", "l_filt");
        fails(&m, "ps_gate.2");
    }

    #[test]
    fn irm05_line_neutral_swap_fails() {
        let mut m = built();
        m.rewire("ps_gate", "1", "tco_l");
        m.rewire("ps_gate", "2", "n_filt");
        fails(&m, "ps_gate.2");
    }

    #[test]
    fn selv_ground_tied_to_hot_fails() {
        let mut m = built();
        m.rewire("leg_a.permit_fet", "2", "leg_ret");
        fails(&m, "bridges SELV and HOT");
    }

    #[test]
    fn isolator_output_on_hot_side_fails() {
        let mut m = built();
        m.rewire("u_iso", "13", "ocp_ok_hot");
        fails(&m, "wrong side of the barrier");
    }

    #[test]
    fn non_default_low_isolator_fails() {
        let mut m = built();
        m.set_part("u_iso", "ISO7710DWR");
        fails(&m, "u_iso is ISO7710DWR");
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
        m.rewire("j_coil", "2", "sw_b");
        fails(&m, "j_coil.2");
    }

    #[test]
    fn ct_on_resonant_node_fails() {
        let mut m = built();
        m.rewire("t_ct", "1", "res_a");
        m.rewire("j_coil", "2", "sw_a");
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
    fn old_91a_threshold_fails() {
        let mut m = built();
        m.set_part("r_th_bot", "RT0603BRD079K76L");
        fails(&m, "r_th_bot is RT0603BRD079K76L");
    }

    #[test]
    fn old_reference_bias_fails_full_temperature_corner() {
        let mut m = built();
        m.set_part("r_ref_bias", "RC0603FR-076K8L");
        fails(&m, "reference cathode current");
    }

    #[test]
    fn selected_reference_bias_covers_shunt_loading_corner() {
        assert!(min_reference_cathode_current_ua(5_600.0) >= 80.0);
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
        m.bom.insert(r, "RC0603FR-0710KL".into());
        fails(&m, "resolved Some(\"RC0603FR-0739KL\") vs BOM");
    }

    #[test]
    fn resolved_identity_swap_fails() {
        let mut m = built();
        m.resolved.insert("u_ref".into(), "AO3400A".into());
        fails(&m, "u_ref");
    }

    #[test]
    fn bootstrap_diode_reversed_fails() {
        let mut m = built();
        m.rewire("leg_a.d_boot", "2", "leg_a-boot");
        m.rewire("leg_a.d_boot", "1", "v15_ls");
        fails(&m, "leg_a.d_boot.2");
    }
}
