//! Source-locked integration readiness gate. Run with rustc; no board is modified.
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const REQUIRED_EDGES: &[&str] = &[
    "bus_to_legacy_voltage",
    "hot_return_to_legacy_return",
    "hot0_to_selv",
    "ctrl_to_selv",
    "pfc_run_to_inverter_permit",
    "interlock_to_inverter",
    "interlock_to_pfc",
    "kelvin_hot_join",
    "voltage_fault",
    "current_fault",
    "thermal_hs_fault",
    "thermal_coil_fault",
    "rtd_fault",
    "cooling_fault",
    "global_sensor_live",
    "f2_equal_voltage",
    "fan_off_discharge_heat",
    "programming_reset_stop",
];
const REQUIRED_FAULTS: &[&str] = &[
    "rtd",
    "current",
    "voltage",
    "thermal_heatsink",
    "thermal_coil",
    "cooling",
    "aux",
];
const REQUIRED_PORTS: &[&str] = &[
    "rev38.vb",
    "rev38.vd",
    "rev38.hot0",
    "rev38.run",
    "voltage.bus",
    "voltage.return",
    "voltage.fault",
    "gate.permit",
    "gate.ctrl",
    "gate.hvreturn",
    "interlock.permit",
    "interlock.gnd",
    "interlock.live",
    "interlock.ocp",
    "interlock.ovp",
    "interlock.hs",
    "interlock.coil",
    "interlock.rtd",
    "interlock.aux",
    "current.fault",
    "thermal.hs",
    "thermal.coil",
    "rtd.fault",
    "cooling.fault",
    "global.live",
    "discharge.fanoff",
    "f2.continuity",
    "programming.ui",
];
const REQUIRED_UNITS: &[&str] = &[
    "power_entry",
    "auxiliary",
    "discharge",
    "inverter",
    "cooling",
    "programming_ui",
    "rtd",
    "current",
    "voltage",
    "thermal",
    "interlock",
    "gate_drive",
    "mcu",
    "buck",
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Verdict {
    Blocked,
    Indeterminate,
    ReadyForDesign,
}
impl Verdict {
    fn label(self) -> &'static str {
        match self {
            Self::Blocked => "BLOCKED",
            Self::Indeterminate => "INDETERMINATE",
            Self::ReadyForDesign => "READY_FOR_DESIGN",
        }
    }
    fn combine(self, other: Self) -> Self {
        if self == Self::Blocked || other == Self::Blocked {
            Self::Blocked
        } else if self == Self::Indeterminate || other == Self::Indeterminate {
            Self::Indeterminate
        } else {
            Self::ReadyForDesign
        }
    }
}

#[derive(Clone, Debug)]
struct Port {
    id: String,
    source: String,
    needle: String,
    board: String,
    reference: String,
    pin: String,
    net: String,
    domain: String,
    return_net: String,
    direction: String,
    vmax: f64,
    fault: String,
    timing: String,
    evidence: String,
}
#[derive(Clone, Debug)]
struct Edge {
    id: String,
    from: String,
    to: String,
    kind: String,
    contract: String,
}
#[derive(Clone, Debug)]
struct Fault {
    id: String,
    input: String,
    validity: String,
    open: String,
    unpowered: String,
    pfc: String,
    inverter: String,
    timing: String,
}
#[derive(Clone, Debug)]
struct Row {
    id: String,
    verdict: Verdict,
    reason: String,
}

fn rows(path: &Path, header: &str, fields: usize) -> Result<Vec<Vec<String>>, String> {
    let data = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut lines = data.lines();
    if lines.next() != Some(header) {
        return Err(format!("{}: schema header mismatch", path.display()));
    }
    let mut out = Vec::new();
    for (i, line) in lines.enumerate() {
        if line.trim().is_empty() {
            return Err(format!("{}:{}: blank row", path.display(), i + 2));
        }
        let f: Vec<String> = line.split('\t').map(String::from).collect();
        if f.len() != fields || f.iter().any(String::is_empty) {
            return Err(format!(
                "{}:{}: expected {fields} nonempty fields",
                path.display(),
                i + 2
            ));
        }
        out.push(f);
    }
    Ok(out)
}
fn relative(path: &str) -> Result<&Path, String> {
    let p = Path::new(path);
    if p.is_absolute()
        || p.components()
            .any(|c| !matches!(c, std::path::Component::Normal(_)))
    {
        return Err(format!("unsafe path: {path}"));
    }
    Ok(p)
}
fn hash(root: &Path, path: &str) -> Result<String, String> {
    let p = relative(path)?;
    let out = Command::new("shasum")
        .arg("-a")
        .arg("256")
        .arg(root.join(p))
        .output()
        .map_err(|e| format!("shasum {path}: {e}"))?;
    if !out.status.success() {
        return Err(format!("missing or unreadable source: {path}"));
    }
    let text = String::from_utf8(out.stdout).map_err(|e| e.to_string())?;
    let h = text.split_whitespace().next().ok_or("empty hash output")?;
    if h.len() != 64 || !h.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(format!("invalid hash output for {path}"));
    }
    Ok(h.into())
}
fn locks(root: &Path) -> Result<BTreeMap<String, String>, String> {
    let mut m = BTreeMap::new();
    for f in rows(
        &root.join("zapote/integration/sources.tsv"),
        "path\tsha256",
        2,
    )? {
        relative(&f[0])?;
        if f[1].len() != 64
            || !f[1].bytes().all(|b| b.is_ascii_hexdigit())
            || m.insert(f[0].clone(), f[1].clone()).is_some()
        {
            return Err(format!("invalid or duplicate source lock: {}", f[0]));
        }
    }
    Ok(m)
}
fn ports(root: &Path) -> Result<BTreeMap<String, Port>, String> {
    let mut m = BTreeMap::new();
    for f in rows(&root.join("zapote/integration/ports.tsv"),
        "id\tsource\tneedle\tboard\tref\tpin\tnet\tdomain\treturn\tdirection\tvmax_v\tfault_default\tstop_timing\tevidence", 14)? {
        let vmax: f64 = f[10].parse().map_err(|_| format!("{}: invalid vmax", f[0]))?;
        if !vmax.is_finite() || vmax < 0.0 { return Err(format!("{}: invalid vmax", f[0])); }
        if !["HOT", "LEGACY_HOT", "LEGACY_COMMON", "SELV", "CTRL", "FLOATING_HOT", "THERMAL"].contains(&f[7].as_str()) ||
           !["IN", "OUT", "RETURN", "EVIDENCE"].contains(&f[9].as_str()) ||
           !["digital", "source", "missing"].contains(&f[13].as_str()) {
            return Err(format!("{}: unknown port type", f[0]));
        }
        let p = Port { id:f[0].clone(), source:f[1].clone(), needle:f[2].clone(), board:f[3].clone(), reference:f[4].clone(), pin:f[5].clone(), net:f[6].clone(), domain:f[7].clone(), return_net:f[8].clone(), direction:f[9].clone(), vmax, fault:f[11].clone(), timing:f[12].clone(), evidence:f[13].clone() };
        if m.insert(p.id.clone(), p).is_some() { return Err(format!("duplicate port: {}", f[0])); }
    }
    for id in REQUIRED_PORTS {
        if !m.contains_key(*id) {
            return Err(format!("required port omitted: {id}"));
        }
    }
    Ok(m)
}
fn edges(root: &Path) -> Result<Vec<Edge>, String> {
    let mut out = Vec::new();
    let mut ids = BTreeSet::new();
    for f in rows(
        &root.join("zapote/integration/edges.tsv"),
        "id\tfrom\tto\tkind\tcontract",
        5,
    )? {
        if !ids.insert(f[0].clone()) {
            return Err(format!("duplicate edge: {}", f[0]));
        }
        out.push(Edge {
            id: f[0].clone(),
            from: f[1].clone(),
            to: f[2].clone(),
            kind: f[3].clone(),
            contract: f[4].clone(),
        });
    }
    for id in REQUIRED_EDGES {
        if !ids.contains(*id) {
            return Err(format!("required edge omitted: {id}"));
        }
    }
    Ok(out)
}
fn faults(root: &Path) -> Result<Vec<Fault>, String> {
    let mut out = Vec::new();
    let mut ids = BTreeSet::new();
    for f in rows(&root.join("zapote/integration/faults.tsv"), "id\tinput_port\tvalidity_contributor\topen_wire\tunpowered\tpfc_inhibit\tinverter_inhibit\tstop_timing", 8)? {
        if !ids.insert(f[0].clone()) { return Err(format!("duplicate fault: {}", f[0])); }
        out.push(Fault {id:f[0].clone(), input:f[1].clone(), validity:f[2].clone(), open:f[3].clone(), unpowered:f[4].clone(), pfc:f[5].clone(), inverter:f[6].clone(), timing:f[7].clone()});
    }
    for id in REQUIRED_FAULTS {
        if !ids.contains(*id) {
            return Err(format!("required fault contributor omitted: {id}"));
        }
    }
    Ok(out)
}
fn units(root: &Path, lock: &BTreeMap<String, String>) -> Result<Vec<Row>, String> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for f in rows(
        &root.join("zapote/integration/units.tsv"),
        "unit\tstatus\treceipt",
        3,
    )? {
        if !seen.insert(f[0].clone()) {
            return Err(format!("duplicate unit: {}", f[0]));
        }
        let (verdict, reason) = match f[1].as_str() {
            "digital" => (
                Verdict::Indeterminate,
                "standalone digital construction; integration and physical qualification open",
            ),
            "candidate" => (
                Verdict::Indeterminate,
                "candidate source/evidence; unit acceptance open",
            ),
            "missing" => (
                Verdict::Blocked,
                "required unit interface source unavailable in this base",
            ),
            "unbound" => (
                Verdict::Blocked,
                "earlier standalone unit has no source/native acceptance binding in this snapshot",
            ),
            _ => return Err(format!("{}: unknown unit status", f[0])),
        };
        if matches!(f[1].as_str(), "digital" | "candidate") {
            if f[2] == "-" || !lock.contains_key(&f[2]) {
                return Err(format!("{}: unit receipt not source-locked", f[0]));
            }
        } else if f[2] != "-" {
            return Err(format!("{}: missing/unbound unit claims a receipt", f[0]));
        }
        out.push(Row {
            id: format!("unit.{}", f[0]),
            verdict,
            reason: reason.into(),
        });
    }
    for id in REQUIRED_UNITS {
        if !seen.contains(*id) {
            return Err(format!("required unit omitted: {id}"));
        }
    }
    Ok(out)
}

// Extract one balanced KiCad expression, honoring quoted strings and escapes.
fn expression(s: &str, start: usize) -> Option<&str> {
    if s.as_bytes().get(start) != Some(&b'(') {
        return None;
    }
    let (mut depth, mut quoted, mut escaped) = (0i32, false, false);
    for (offset, b) in s.as_bytes()[start..].iter().enumerate() {
        if quoted {
            if escaped {
                escaped = false;
            } else if *b == b'\\' {
                escaped = true;
            } else if *b == b'"' {
                quoted = false;
            }
        } else if *b == b'"' {
            quoted = true;
        } else if *b == b'(' {
            depth += 1;
        } else if *b == b')' {
            depth -= 1;
            if depth == 0 {
                return s.get(start..start + offset + 1);
            }
        }
    }
    None
}
fn quoted_after<'a>(s: &'a str, prefix: &str) -> Option<&'a str> {
    let tail = s.split_once(prefix)?.1;
    tail.split_once('"').map(|(v, _)| v)
}
fn native_net(board: &str, reference: &str, pin: &str) -> Option<String> {
    for part in board.match_indices("(footprint ") {
        let fp = expression(board, part.0)?;
        let r = quoted_after(fp, "(property \"Reference\" \"")?;
        if r != reference {
            continue;
        }
        for pad_pos in fp.match_indices("(pad \"") {
            let pad = expression(fp, pad_pos.0)?;
            if quoted_after(pad, "(pad \"")? != pin {
                continue;
            }
            let net_pos = pad.find("(net ")?;
            let net = expression(pad, net_pos)?;
            return quoted_after(net, "\"").map(String::from);
        }
        return None;
    }
    None
}
fn identity(root: &Path, p: &Port, lock: &BTreeMap<String, String>) -> Result<Verdict, String> {
    for path in [&p.source, &p.board] {
        if path == "-" {
            continue;
        }
        let expected = lock
            .get(path)
            .ok_or_else(|| format!("{}: unlocked input {path}", p.id))?;
        let observed = hash(root, path)?;
        if observed != *expected {
            return Err(format!("{}: stale input {path}", p.id));
        }
    }
    if p.evidence == "missing" {
        return Ok(Verdict::Blocked);
    }
    if p.source != "-" {
        let content =
            fs::read_to_string(root.join(relative(&p.source)?)).map_err(|e| e.to_string())?;
        if p.needle == "-" || !content.lines().any(|line| line.trim() == p.needle) {
            return Err(format!("{}: source pin/net assertion absent", p.id));
        }
    }
    if p.evidence == "digital" {
        if p.board == "-" || p.reference == "-" || p.pin == "-" {
            return Err(format!("{}: digital port lacks native identity", p.id));
        }
        let board =
            fs::read_to_string(root.join(relative(&p.board)?)).map_err(|e| e.to_string())?;
        if native_net(&board, &p.reference, &p.pin).as_deref() != Some(p.net.as_str()) {
            return Err(format!(
                "{}: native {}.{} is not net {}",
                p.id, p.reference, p.pin, p.net
            ));
        }
    }
    Ok(Verdict::Indeterminate) // Digital construction is not an accepted system contract.
}

fn assess_edge(
    e: &Edge,
    ports: &BTreeMap<String, Port>,
    ids: &BTreeMap<String, Verdict>,
) -> Result<Row, String> {
    let a = ports
        .get(&e.from)
        .ok_or_else(|| format!("{}: unknown source port", e.id))?;
    let b = ports
        .get(&e.to)
        .ok_or_else(|| format!("{}: unknown receiver port", e.id))?;
    let (v, reason) = match e.kind.as_str() {
        "bus_sense" if a.domain == "HOT" && a.vmax > b.vmax => (
            Verdict::Blocked,
            "390 V-class bus exceeds native 0-250 V legacy sense envelope",
        ),
        "bus_sense" => (
            Verdict::Indeterminate,
            "bus/sense envelope and return need review",
        ),
        "domain_join" if a.domain != b.domain => (
            Verdict::Blocked,
            "HOT0 return join would carry mains reference into a host/common-ground domain",
        ),
        "domain_join" => (
            Verdict::Indeterminate,
            "return join location and current path unreviewed",
        ),
        "control_return" if a.domain == "CTRL" && b.domain == "SELV" => (
            Verdict::Indeterminate,
            "gate-drive CTRL_GND-to-SELV join and isolation policy unreviewed",
        ),
        "control_return" => (
            Verdict::Blocked,
            "control return mapping is not CTRL-to-SELV",
        ),
        "pfc_as_inverter" => (Verdict::Blocked, "PFC HOT RUN is not inverter PERMIT"),
        "kelvin" if a.id == "gate.hvreturn" && b.id == "rev38.hot0" => (
            Verdict::Indeterminate,
            "HV_RETURN-HOT0 Kelvin join, isolated bias and return-current path unreviewed",
        ),
        "kelvin" => (Verdict::Blocked, "unrecognized Kelvin join"),
        "f2_equal" => (Verdict::Blocked, "equal VD/VB does not prove F2 continuity"),
        "heat" if e.contract == "OMITTED" => {
            (Verdict::Blocked, "fan-off discharge heat path omitted")
        }
        "heat" => (
            Verdict::Indeterminate,
            "installed heat destination and duty unqualified",
        ),
        "global_live" if a.evidence == "missing" => {
            (Verdict::Blocked, "global SENSOR_LIVE producer absent")
        }
        "global_live" => (
            Verdict::Indeterminate,
            "all sensing validity contributors and defaults unqualified",
        ),
        "stop_pfc" => (
            Verdict::Indeterminate,
            "interlock-to-Rev38 isolated PFC inhibit and timing unproved",
        ),
        "stop_inverter" => (
            Verdict::Indeterminate,
            "interlock-to-gate-drive domain, driven high and loaded stop unproved",
        ),
        "service" => (
            Verdict::Blocked,
            "programming/UI pin allocation and reset-to-both-stage-stop contract unresolved",
        ),
        "signal" if a.evidence == "missing" || b.evidence == "missing" => (
            Verdict::Blocked,
            "fault signal producer or receiver lacks native identity",
        ),
        "signal" if a.domain != b.domain || a.return_net != b.return_net => (
            Verdict::Blocked,
            "fault producer and receiver returns/domains differ; no isolation interface",
        ),
        "signal"
            if a.direction == "OUT"
                && b.direction == "IN"
                && a.vmax <= b.vmax
                && a.timing != "PROVEN" =>
        {
            (
                Verdict::Indeterminate,
                "native endpoints exist; unpowered clamp, voltage and timing unqualified",
            )
        }
        "signal" if a.direction == "OUT" && b.direction == "IN" && a.vmax <= b.vmax => (
            Verdict::Indeterminate,
            "native endpoints exist; physical fault behavior remains unqualified",
        ),
        "signal" => (
            Verdict::Blocked,
            "fault signal direction or voltage mismatch",
        ),
        _ => return Err(format!("{}: unknown edge kind or invalid contract", e.id)),
    };
    let v = v
        .combine(*ids.get(&e.from).ok_or("missing source identity")?)
        .combine(*ids.get(&e.to).ok_or("missing receiver identity")?);
    Ok(Row {
        id: e.id.clone(),
        verdict: v,
        reason: reason.into(),
    })
}
fn assess_fault(f: &Fault, ports: &BTreeMap<String, Port>) -> Result<Row, String> {
    let input = ports
        .get(&f.input)
        .ok_or_else(|| format!("{}: unknown fault input", f.id))?;
    if input.direction != "IN" || input.fault != "HIGH" {
        return Err(format!("{}: fault input does not default high", f.id));
    }
    let required = [
        (&f.validity, "MISSING"),
        (&f.open, "FAULT_HIGH"),
        (&f.unpowered, "UNKNOWN"),
        (&f.pfc, "UNKNOWN"),
        (&f.inverter, "UNKNOWN"),
        (&f.timing, "UNKNOWN"),
    ];
    for (value, _) in required {
        if ![
            "MISSING",
            "UNKNOWN",
            "FAULT_HIGH",
            "PROVEN_LOW",
            "PROVEN_INHIBIT",
            "PROVEN",
        ]
        .contains(&value.as_str())
        {
            return Err(format!("{}: invalid fault state {value}", f.id));
        }
    }
    let blocked = f.validity == "MISSING"
        || f.open != "FAULT_HIGH"
        || f.unpowered != "PROVEN_INHIBIT"
        || f.pfc != "PROVEN_INHIBIT"
        || f.inverter != "PROVEN_INHIBIT";
    let (verdict, reason) = if blocked {
        (
            Verdict::Blocked,
            "missing global validity or open-wire/unpowered fault-to-both-stage stop proof",
        )
    } else if f.timing != "PROVEN" {
        (
            Verdict::Indeterminate,
            "both stop paths declared; timing evidence missing",
        )
    } else {
        (
            Verdict::Indeterminate,
            "typed declaration still lacks independently replayed system evidence",
        )
    };
    Ok(Row {
        id: format!("fault.{}", f.id),
        verdict,
        reason: reason.into(),
    })
}
fn run(root: &Path) -> Result<Vec<Row>, String> {
    let lock = locks(root)?;
    for (p, h) in &lock {
        if hash(root, p)? != *h {
            return Err(format!("stale source lock: {p}"));
        }
    }
    let ports = ports(root)?;
    let edges = edges(root)?;
    let faults = faults(root)?;
    let unit_rows = units(root, &lock)?;
    let mut identity_verdict = BTreeMap::new();
    for (id, p) in &ports {
        identity_verdict.insert(id.clone(), identity(root, p, &lock)?);
    }
    let mut out = unit_rows;
    for e in &edges {
        out.push(assess_edge(e, &ports, &identity_verdict)?);
    }
    for f in &faults {
        out.push(assess_fault(f, &ports)?);
    }
    out.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(out)
}
fn main() {
    let root = std::env::args().nth(1).unwrap_or_else(|| ".".into());
    match run(&PathBuf::from(root)) {
        Ok(rows) => {
            let mut overall = Verdict::ReadyForDesign;
            for r in &rows {
                println!("{}\t{}\t{}", r.id, r.verdict.label(), r.reason);
                overall = overall.combine(r.verdict);
            }
            println!("OVERALL\t{}\t{} edges and fault paths; readiness is permission to design, never whole-board acceptance",overall.label(),rows.len());
            if overall != Verdict::ReadyForDesign {
                std::process::exit(2);
            }
        }
        Err(e) => {
            eprintln!("BLOCKED: {e}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn root() -> PathBuf {
        std::env::current_dir().unwrap()
    }
    #[test]
    fn actual_sources_and_matrix_are_blocked() {
        let rows = run(&root()).unwrap();
        assert_eq!(
            rows.len(),
            REQUIRED_EDGES.len() + REQUIRED_FAULTS.len() + REQUIRED_UNITS.len()
        );
        assert!(rows
            .iter()
            .any(|r| r.id == "kelvin_hot_join" && r.verdict == Verdict::Indeterminate));
        for id in [
            "bus_to_legacy_voltage",
            "hot_return_to_legacy_return",
            "pfc_run_to_inverter_permit",
            "global_sensor_live",
            "f2_equal_voltage",
            "fan_off_discharge_heat",
        ] {
            assert!(
                rows.iter()
                    .any(|r| r.id == id && r.verdict == Verdict::Blocked),
                "{id}"
            );
        }
    }
    #[test]
    fn source_and_native_identity_are_real() {
        let locks = locks(&root()).unwrap();
        let p = ports(&root()).unwrap();
        assert_eq!(
            identity(&root(), &p["voltage.bus"], &locks).unwrap(),
            Verdict::Indeterminate
        );
        let mut swapped = p["voltage.bus"].clone();
        swapped.pin = "2".into();
        assert!(identity(&root(), &swapped, &locks).is_err());
        swapped = p["gate.permit"].clone();
        swapped.net = "pwm_l".into();
        assert!(identity(&root(), &swapped, &locks).is_err());
        swapped = p["interlock.live"].clone();
        swapped.needle = "sensor_live ~ host.p6".into();
        assert!(identity(&root(), &swapped, &locks).is_err());
        let mut stale = locks.clone();
        stale.insert(swapped.source.clone(), "0".repeat(64));
        assert!(identity(&root(), &p["interlock.live"], &stale).is_err());
    }
    #[test]
    fn negative_edges_cannot_be_renamed_ready() {
        let p = ports(&root()).unwrap();
        let mut ids = BTreeMap::new();
        for id in p.keys() {
            ids.insert(id.clone(), Verdict::Indeterminate);
        }
        for (kind, a, b) in [
            ("bus_sense", "rev38.vb", "voltage.bus"),
            ("domain_join", "rev38.hot0", "voltage.return"),
            ("pfc_as_inverter", "rev38.run", "gate.permit"),
            ("f2_equal", "f2.continuity", "rev38.run"),
            ("heat", "discharge.fanoff", "rev38.vb"),
            ("global_live", "global.live", "interlock.live"),
        ] {
            let edge = Edge {
                id: kind.into(),
                from: a.into(),
                to: b.into(),
                kind: kind.into(),
                contract: if kind == "heat" { "OMITTED" } else { "DIRECT" }.into(),
            };
            assert_eq!(
                assess_edge(&edge, &p, &ids).unwrap().verdict,
                Verdict::Blocked,
                "{kind}"
            );
        }
    }
    #[test]
    fn fault_paths_require_both_stages_and_unpowered_response() {
        let p = ports(&root()).unwrap();
        let mut f = faults(&root()).unwrap().remove(0);
        assert_eq!(assess_fault(&f, &p).unwrap().verdict, Verdict::Blocked);
        f.validity = "PROVEN".into();
        f.unpowered = "PROVEN_INHIBIT".into();
        f.pfc = "PROVEN_INHIBIT".into();
        assert_eq!(assess_fault(&f, &p).unwrap().verdict, Verdict::Blocked);
        f.inverter = "PROVEN_INHIBIT".into();
        assert_eq!(
            assess_fault(&f, &p).unwrap().verdict,
            Verdict::Indeterminate
        );
        f.open = "UNKNOWN".into();
        assert_eq!(assess_fault(&f, &p).unwrap().verdict, Verdict::Blocked);
    }
    #[test]
    fn missing_closed_registry_is_fatal() {
        let dir = std::env::temp_dir().join(format!("zapote-r6-registry-{}", std::process::id()));
        let path = dir.join("zapote/integration");
        fs::create_dir_all(&path).unwrap();
        let source = fs::read_to_string(root().join("zapote/integration/edges.tsv")).unwrap();
        let omitted = source
            .lines()
            .filter(|line| !line.starts_with("programming_reset_stop\t"))
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        fs::write(path.join("edges.tsv"), omitted).unwrap();
        assert!(edges(&dir).unwrap_err().contains("required edge omitted"));
        fs::write(
            path.join("edges.tsv"),
            format!("{source}{}\n", source.lines().nth(1).unwrap()),
        )
        .unwrap();
        assert!(edges(&dir).unwrap_err().contains("duplicate edge"));
        let source = fs::read_to_string(root().join("zapote/integration/ports.tsv")).unwrap();
        let omitted = source
            .lines()
            .filter(|line| !line.starts_with("global.live\t"))
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        fs::write(path.join("ports.tsv"), omitted).unwrap();
        assert!(ports(&dir).unwrap_err().contains("required port omitted"));
        let source = fs::read_to_string(root().join("zapote/integration/units.tsv")).unwrap();
        let omitted = source
            .lines()
            .filter(|line| !line.starts_with("mcu\t"))
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        fs::write(path.join("units.tsv"), omitted).unwrap();
        assert!(units(&dir, &locks(&root()).unwrap())
            .unwrap_err()
            .contains("required unit omitted"));
        fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn parser_handles_nested_pad_and_reference() {
        let board="(kicad_pcb (footprint \"x\" (property \"Reference\" \"J1\") (pad \"1\" smd rect (net 1 \"HOT0\"))))";
        assert_eq!(native_net(board, "J1", "1").as_deref(), Some("HOT0"));
        assert_eq!(native_net(board, "J1", "2"), None);
    }
}
