//! Source-locked measurement inventory. A complete record is review pending,
//! never a native inverter, selected part, or physical safety acceptance.
//! Run from the repository root with rustc; see U3-MEASUREMENT-READINESS.md.
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Component, Path};
use std::process::Command;

const SCENARIOS: &str = "zapote/inverter/evidence/measurement-scenarios.tsv";
const MANIFEST: &str = "zapote/inverter/evidence/measurement-manifest.tsv";
const SOURCES: &str = "zapote/inverter/evidence/measurement-sources.sha256";
const EXPECTED: &[(&str, Kind)] = &[
    ("coil_no_pan", Kind::Coil),
    ("coil_reference_cold", Kind::Coil),
    ("coil_reference_hot", Kind::Coil),
    ("coil_weak_pan", Kind::Coil),
    ("coil_offset", Kind::Coil),
    ("coil_lift", Kind::Coil),
    ("coil_live_removal", Kind::Coil),
    ("bus_startup", Kind::Bus),
    ("bus_loaded_ripple", Kind::Bus),
    ("bus_surge", Kind::Bus),
    ("bus_f2_open", Kind::Bus),
    ("gate_permit", Kind::Stop),
    ("gate_pwm", Kind::Stop),
    ("gate_rail15_loss", Kind::Stop),
    ("gate_3v3_loss", Kind::Stop),
    ("fault_f2_open", Kind::Fault),
    ("fault_direct_bank", Kind::Fault),
    ("part_local_cap", Kind::Part),
    ("part_switch", Kind::Part),
    ("part_tank_cap", Kind::Part),
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Kind {
    Coil,
    Bus,
    Stop,
    Fault,
    Part,
}
impl Kind {
    fn parse(s: &str) -> Option<Self> {
        match s {
            "coil" => Some(Self::Coil),
            "bus" => Some(Self::Bus),
            "stop" => Some(Self::Stop),
            "fault" => Some(Self::Fault),
            "part" => Some(Self::Part),
            _ => None,
        }
    }
}
#[derive(Clone, Debug)]
struct Record {
    id: String,
    kind: Kind,
    origin: String,
    article: String,
    coil: String,
    pan: String,
    return_net: String,
    values: String,
    raw: String,
    digest: String,
    reviewer: String,
}
fn rows<'a>(input: &'a str, header: &str, columns: usize) -> Result<Vec<Vec<&'a str>>, String> {
    let mut lines = input.lines();
    if lines.next() != Some(header) {
        return Err(format!("wrong TSV header: expected {header}"));
    }
    let mut result = Vec::new();
    for (index, line) in lines.enumerate() {
        if line.is_empty() {
            return Err(format!("empty line {}", index + 2));
        }
        let fields: Vec<&str> = line.split('\t').collect();
        if fields.len() != columns {
            return Err(format!(
                "line {} has {} columns, expected {columns}",
                index + 2,
                fields.len()
            ));
        }
        result.push(fields);
    }
    Ok(result)
}
fn scenarios(input: &str) -> Result<(), String> {
    let lines = rows(input, "id\tkind\tcondition", 3)?;
    let mut seen = BTreeSet::new();
    for row in lines {
        let expected = EXPECTED.iter().find(|(id, _)| *id == row[0]);
        match expected {
            Some((_, kind)) if Some(*kind) == Kind::parse(row[1]) && !row[2].trim().is_empty() => {
                ()
            }
            _ => {
                return Err(format!(
                    "unexpected, mismatched, or empty scenario {}",
                    row[0]
                ))
            }
        }
        if !seen.insert(row[0]) {
            return Err(format!("duplicate scenario {}", row[0]));
        }
    }
    for (id, _) in EXPECTED {
        if !seen.contains(id) {
            return Err(format!("missing scenario {id}"));
        }
    }
    Ok(())
}
fn manifest(input: &str) -> Result<BTreeMap<String, Record>, String> {
    let lines = rows(
        input,
        "id\tkind\torigin\tarticle\tcoil\tpan\treturn_net\tvalues\traw_path\traw_sha256\treviewer",
        11,
    )?;
    let mut records = BTreeMap::new();
    for row in lines {
        let kind = Kind::parse(row[1]).ok_or_else(|| format!("unknown kind for {}", row[0]))?;
        let record = Record {
            id: row[0].into(),
            kind,
            origin: row[2].into(),
            article: row[3].into(),
            coil: row[4].into(),
            pan: row[5].into(),
            return_net: row[6].into(),
            values: row[7].into(),
            raw: row[8].into(),
            digest: row[9].into(),
            reviewer: row[10].into(),
        };
        if records.insert(record.id.clone(), record).is_some() {
            return Err(format!("duplicate record {}", row[0]));
        }
    }
    for (id, kind) in EXPECTED {
        let Some(record) = records.get(*id) else {
            return Err(format!("missing record {id}"));
        };
        if record.kind != *kind {
            return Err(format!("wrong kind for {id}"));
        }
    }
    if records.len() != EXPECTED.len() {
        return Err("unregistered record".into());
    }
    Ok(records)
}
fn fields(input: &str) -> Result<BTreeMap<&str, &str>, String> {
    let mut result = BTreeMap::new();
    for item in input.split(';') {
        let (name, value) = item.split_once('=').ok_or("value must be key=value")?;
        if name.is_empty() || value.is_empty() || result.insert(name, value).is_some() {
            return Err("empty or duplicate value key".into());
        }
    }
    Ok(result)
}
fn required<'a>(map: &'a BTreeMap<&str, &str>, key: &str) -> Result<&'a str, String> {
    map.get(key)
        .copied()
        .filter(|v| !v.is_empty() && *v != "UNKNOWN")
        .ok_or_else(|| format!("missing {key}"))
}
fn positive(map: &BTreeMap<&str, &str>, key: &str) -> Result<f64, String> {
    let v = required(map, key)?
        .parse::<f64>()
        .map_err(|_| format!("invalid {key}"))?;
    if !v.is_finite() || v <= 0.0 {
        return Err(format!("nonpositive or nonfinite {key}"));
    }
    Ok(v)
}
fn nonnegative(map: &BTreeMap<&str, &str>, key: &str) -> Result<f64, String> {
    let v = finite(map, key)?;
    if v < 0.0 {
        return Err(format!("negative {key}"));
    }
    Ok(v)
}
fn finite(map: &BTreeMap<&str, &str>, key: &str) -> Result<f64, String> {
    let v = required(map, key)?
        .parse::<f64>()
        .map_err(|_| format!("invalid {key}"))?;
    if !v.is_finite() {
        return Err(format!("nonfinite {key}"));
    }
    Ok(v)
}
fn ordered(map: &BTreeMap<&str, &str>, low: &str, high: &str) -> Result<(), String> {
    if finite(map, high)? < finite(map, low)? {
        return Err(format!("{high} below {low}"));
    }
    Ok(())
}
fn value_shape(record: &Record) -> Result<(), String> {
    if record.return_net != "HOT0" {
        return Err("Rev38 inverter return must be HOT0, never historical PWR_RTN".into());
    }
    let m = fields(&record.values)?;
    let keys: &[&str] = match record.kind {
        Kind::Coil if record.id == "coil_live_removal" => &[
            "f_min_hz",
            "f_max_hz",
            "i_min_a",
            "i_max_a",
            "t_min_c",
            "t_max_c",
            "z_re_min_ohm",
            "z_re_max_ohm",
            "z_im_min_ohm",
            "z_im_max_ohm",
            "u_z_ohm",
            "gap_mm",
            "offset_mm",
            "samples",
            "removal_us",
            "trip_us",
            "current_zero_us",
        ],
        Kind::Coil => &[
            "f_min_hz",
            "f_max_hz",
            "i_min_a",
            "i_max_a",
            "t_min_c",
            "t_max_c",
            "z_re_min_ohm",
            "z_re_max_ohm",
            "z_im_min_ohm",
            "z_im_max_ohm",
            "u_z_ohm",
            "gap_mm",
            "offset_mm",
            "samples",
        ],
        Kind::Bus if record.id == "bus_f2_open" => &[
            "vd_min_v",
            "vd_max_v",
            "vb_min_v",
            "vb_max_v",
            "vd_pp_v",
            "vb_pp_v",
            "u_v",
            "source_i_max_a",
            "source_p_max_w",
            "slew_v_per_us",
            "f2_contact",
            "f2_i_max_a",
        ],
        Kind::Bus => &[
            "vd_min_v",
            "vd_max_v",
            "vb_min_v",
            "vb_max_v",
            "vd_pp_v",
            "vb_pp_v",
            "u_v",
            "source_i_max_a",
            "source_p_max_w",
            "slew_v_per_us",
        ],
        Kind::Stop => &[
            "command_us",
            "gate_off_us",
            "current_zero_us",
            "i_start_a",
            "zero_threshold_a",
            "u_time_us",
        ],
        Kind::Fault => {
            if record.id == "fault_direct_bank" {
                &[
                    "bank_peak_a",
                    "bank_energy_j",
                    "loop_r_mohm",
                    "loop_l_nh",
                    "clearer",
                ]
            } else {
                &[
                    "vd_peak_a",
                    "vb_peak_a",
                    "vd_max_v",
                    "vb_max_v",
                    "energy_j",
                    "clearer",
                ]
            }
        }
        Kind::Part => {
            if record.id == "part_local_cap" {
                &[
                    "mpn",
                    "c_nf",
                    "rated_v",
                    "rated_a",
                    "rated_temp_c",
                    "observed_v",
                    "observed_a",
                    "observed_temp_c",
                ]
            } else {
                &[
                    "mpn",
                    "rated_v",
                    "rated_a",
                    "rated_temp_c",
                    "observed_v",
                    "observed_a",
                    "observed_temp_c",
                ]
            }
        }
    };
    for key in m.keys() {
        if !keys.contains(key) {
            return Err(format!("unknown value key {key}"));
        }
    }
    for key in keys {
        required(&m, key)?;
    }
    match record.kind {
        Kind::Coil => {
            for key in [
                "f_min_hz", "f_max_hz", "i_min_a", "i_max_a", "u_z_ohm", "samples",
            ] {
                positive(&m, key)?;
            }
            for key in [
                "t_min_c",
                "t_max_c",
                "z_re_min_ohm",
                "z_re_max_ohm",
                "z_im_min_ohm",
                "z_im_max_ohm",
                "gap_mm",
                "offset_mm",
            ] {
                finite(&m, key)?;
            }
            for (a, b) in [
                ("f_min_hz", "f_max_hz"),
                ("i_min_a", "i_max_a"),
                ("t_min_c", "t_max_c"),
                ("z_re_min_ohm", "z_re_max_ohm"),
                ("z_im_min_ohm", "z_im_max_ohm"),
            ] {
                ordered(&m, a, b)?;
            }
            if finite(&m, "f_max_hz")? <= finite(&m, "f_min_hz")?
                || finite(&m, "i_max_a")? <= finite(&m, "i_min_a")?
            {
                return Err("loaded impedance needs frequency and current sweep, not one historical operating point".into());
            }
            if positive(&m, "samples")? < 3.0 {
                return Err("coil sweep needs at least three samples".into());
            }
            if record.id == "coil_live_removal" {
                for key in ["removal_us", "trip_us", "current_zero_us"] {
                    nonnegative(&m, key)?;
                }
                if finite(&m, "trip_us")? < finite(&m, "removal_us")?
                    || finite(&m, "current_zero_us")? <= finite(&m, "trip_us")?
                {
                    return Err("pan removal needs ordered trip and measured current-zero".into());
                }
            }
            if record.coil == "UNKNOWN" {
                return Err("unidentified coil article".into());
            }
            if record.id == "coil_no_pan" && record.pan != "NONE" {
                return Err("no-pan row must identify NONE".into());
            }
            if record.id != "coil_no_pan" && record.pan == "UNKNOWN" {
                return Err("unidentified pan article".into());
            }
        }
        Kind::Bus => {
            for key in ["vd_max_v", "vb_max_v", "u_v"] {
                positive(&m, key)?;
            }
            for key in [
                "vd_min_v",
                "vb_min_v",
                "vd_pp_v",
                "vb_pp_v",
                "source_i_max_a",
                "source_p_max_w",
                "slew_v_per_us",
            ] {
                nonnegative(&m, key)?;
            }
            ordered(&m, "vd_min_v", "vd_max_v")?;
            ordered(&m, "vb_min_v", "vb_max_v")?;
            if record.id == "bus_f2_open" {
                if required(&m, "f2_contact")? != "OPEN_CONFIRMED" {
                    return Err(
                        "F2 state needs independent contact evidence, not equal VD/VB".into(),
                    );
                }
                nonnegative(&m, "f2_i_max_a")?;
            }
        }
        Kind::Stop => {
            for key in [
                "command_us",
                "gate_off_us",
                "current_zero_us",
                "i_start_a",
                "zero_threshold_a",
                "u_time_us",
            ] {
                finite(&m, key)?;
            }
            if finite(&m, "i_start_a")? <= finite(&m, "zero_threshold_a")? {
                return Err("stop capture lacks loaded current".into());
            }
            if finite(&m, "command_us")? < 0.0
                || finite(&m, "zero_threshold_a")? <= 0.0
                || finite(&m, "u_time_us")? <= 0.0
                || finite(&m, "gate_off_us")? < finite(&m, "command_us")?
                || finite(&m, "current_zero_us")? <= finite(&m, "gate_off_us")?
            {
                return Err("stop timing invalid or gate-off substituted for current-zero".into());
            }
        }
        Kind::Fault => {
            for key in keys.iter().filter(|k| **k != "clearer") {
                positive(&m, key)?;
            }
            let clearer = required(&m, "clearer")?;
            if record.id == "fault_direct_bank"
                && ["F2", "PFC_RUN", "PERMIT", "NONE"].contains(&clearer)
            {
                return Err("F2/PFC/PERMIT cannot interrupt direct VB-bank short".into());
            }
        }
        Kind::Part => {
            for key in keys.iter().filter(|k| **k != "mpn") {
                positive(&m, key)?;
            }
            if required(&m, "mpn")?.contains("CUSTOM") {
                return Err("placeholder is not an exact part".into());
            }
            for (rated, observed) in [
                ("rated_v", "observed_v"),
                ("rated_a", "observed_a"),
                ("rated_temp_c", "observed_temp_c"),
            ] {
                if positive(&m, observed)? >= positive(&m, rated)? {
                    return Err(format!("{observed} reaches/exceeds {rated}"));
                }
            }
        }
    }
    Ok(())
}
fn safe_raw_path(raw: &str) -> bool {
    raw.starts_with("zapote/inverter/evidence/raw/")
        && Path::new(raw)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
fn raw_inside_evidence(raw: &str) -> bool {
    if !safe_raw_path(raw) {
        return false;
    }
    let Ok(root) = fs::canonicalize("zapote/inverter/evidence/raw") else {
        return false;
    };
    let Ok(real) = fs::canonicalize(raw) else {
        return false;
    };
    real.starts_with(root) && fs::metadata(real).is_ok_and(|m| m.is_file())
}
fn sha256(path: &str) -> Result<String, String> {
    let output = Command::new("shasum")
        .args(["-a", "256", path])
        .output()
        .map_err(|e| format!("shasum unavailable: {e}"))?;
    if !output.status.success() {
        return Err(format!("cannot hash {path}"));
    }
    let stdout = String::from_utf8(output.stdout).map_err(|_| "invalid shasum output")?;
    let digest = stdout
        .split_whitespace()
        .next()
        .ok_or("empty shasum output")?;
    if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("invalid digest".into());
    }
    Ok(digest.into())
}
fn source_check() -> Result<(), String> {
    const PATHS: &[&str] = &[
        "zapote/power-entry/passive-reva/protection/interface-integration-38/elec/src/pfc_power.ato",
        "zapote/gate-drive/source-build-09/elec/src/gate_drive_unit.ato",
        "zapote/inverter/evidence/coupled_transient.rs",
        "zapote/inverter/evidence/transient-cases.csv",
    ];
    let locks = fs::read_to_string(SOURCES).map_err(|e| format!("source lock: {e}"))?;
    let mut found = BTreeSet::new();
    for line in locks.lines() {
        let mut words = line.split_whitespace();
        let digest = words.next().ok_or("empty source lock row")?;
        let path = words.next().ok_or("source lock path absent")?;
        if words.next().is_some()
            || digest.len() != 64
            || !digest.bytes().all(|b| b.is_ascii_hexdigit())
            || !PATHS.contains(&path)
            || !found.insert(path)
        {
            return Err("source lock registry malformed".into());
        }
    }
    if found.len() != PATHS.len() {
        return Err("source lock registry incomplete".into());
    }
    let output = Command::new("shasum")
        .args(["-a", "256", "-c", SOURCES])
        .output()
        .map_err(|e| format!("shasum unavailable: {e}"))?;
    if !output.status.success() {
        return Err(format!(
            "source missing or drifted: {}",
            String::from_utf8_lossy(&output.stdout)
        ));
    }
    Ok(())
}
fn record_result(record: &Record, verify_hash: bool) -> (&'static str, String) {
    if record.return_net != "HOT0" {
        return ("REJECTED", "PWR_RTN or wrong return".into());
    }
    if record.origin == "NONE" {
        return ("INDETERMINATE", "measurement absent".into());
    }
    if record.origin != "MEASURED" && record.origin != "SYNTHETIC" {
        return ("REJECTED", "unknown origin".into());
    }
    if record.article == "UNKNOWN" || record.article.is_empty() {
        return ("REJECTED", "article identity absent".into());
    }
    if let Err(e) = value_shape(record) {
        return ("REJECTED", e);
    }
    if record.origin == "SYNTHETIC" {
        return ("INDETERMINATE", "synthetic checker control only".into());
    }
    if !raw_inside_evidence(&record.raw)
        || record.digest.len() != 64
        || !record.digest.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return ("REJECTED", "raw path or SHA-256 malformed".into());
    }
    if record.reviewer == "UNKNOWN" || record.reviewer.is_empty() {
        return ("INDETERMINATE", "independent review identity absent".into());
    }
    if verify_hash {
        match sha256(&record.raw) {
            Ok(actual) if actual.eq_ignore_ascii_case(&record.digest) => (),
            Ok(_) => return ("REJECTED", "raw bytes drifted".into()),
            Err(e) => return ("REJECTED", e),
        }
    }
    (
        "CAPTURE_RECORDED",
        "typed record and raw hash present; independent engineering review still required".into(),
    )
}
fn report(
    scenario_input: &str,
    manifest_input: &str,
    verify_hash: bool,
) -> Result<(String, i32), String> {
    scenarios(scenario_input)?;
    let records = manifest(manifest_input)?;
    let mut output = String::from("id\tstatus\treason\n");
    let mut rejected = 0;
    let mut incomplete = 0;
    let mut recorded = 0;
    for (id, _) in EXPECTED {
        let (status, reason) = record_result(&records[*id], verify_hash);
        output.push_str(&format!("{id}\t{status}\t{reason}\n"));
        match status {
            "REJECTED" => rejected += 1,
            "INDETERMINATE" => incomplete += 1,
            _ => recorded += 1,
        }
    }
    let articles: BTreeSet<_> = records
        .values()
        .filter(|record| record.origin != "NONE")
        .map(|record| record.article.as_str())
        .collect();
    if articles.len() > 1 {
        rejected += 1;
        output.push_str(
            "ARTICLE_COHORT\tREJECTED\tmeasurement rows name different physical articles\n",
        );
    }
    let coil_articles: BTreeSet<_> = records
        .values()
        .filter(|record| record.kind == Kind::Coil && record.origin != "NONE")
        .map(|record| record.coil.as_str())
        .collect();
    if coil_articles.len() > 1 {
        rejected += 1;
        output.push_str("COIL_COHORT\tREJECTED\tcoil sweep rows name different coil builds\n");
    }
    // Multiple physical load states must not be relabeled copies of one pan.
    let reference = &records["coil_reference_cold"];
    let hot = &records["coil_reference_hot"];
    let weak = &records["coil_weak_pan"];
    if reference.origin != "NONE" && hot.origin != "NONE" && reference.pan != hot.pan {
        rejected += 1;
        output.push_str("COIL_COHORT\tREJECTED\tcold/hot reference-pan identities differ\n");
    }
    if reference.origin != "NONE" && weak.origin != "NONE" && reference.pan == weak.pan {
        rejected += 1;
        output.push_str("COIL_COHORT\tREJECTED\tone favorable pan reused as weak-pan envelope\n");
    }
    let checks: &[(&str, &str, &str, &str)] = &[
        (
            "coil_reference_cold",
            "coil_reference_hot",
            "t_min_c",
            "hot reference temperature must exceed cold",
        ),
        (
            "coil_reference_cold",
            "coil_offset",
            "offset_mm",
            "offset row must exceed centered reference",
        ),
        (
            "coil_reference_cold",
            "coil_lift",
            "gap_mm",
            "lift row must exceed reference gap",
        ),
    ];
    for (base_id, other_id, key, reason) in checks {
        let base = &records[*base_id];
        let other = &records[*other_id];
        if base.origin == "NONE" || other.origin == "NONE" {
            continue;
        }
        if let (Ok(a), Ok(b)) = (fields(&base.values), fields(&other.values)) {
            if let (Ok(a), Ok(b)) = (finite(&a, key), finite(&b, key)) {
                if b <= a {
                    rejected += 1;
                    output.push_str(&format!("COIL_COHORT\tREJECTED\t{reason}\n"));
                }
            }
        }
    }
    let overall = if rejected > 0 {
        "REJECTED"
    } else if incomplete > 0 {
        "INDETERMINATE"
    } else {
        "REVIEW_PENDING"
    };
    output.push_str(&format!("OVERALL\t{overall}\t{recorded} capture records; {incomplete} missing/synthetic; {rejected} rejected; no native or hardware acceptance\n"));
    Ok((output, if rejected > 0 { 1 } else { 2 }))
}
fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 1 {
        eprintln!("usage: measurement_gate (run from repository root)");
        std::process::exit(1);
    }
    let result = source_check().and_then(|_| {
        let scenario_input =
            fs::read_to_string(SCENARIOS).map_err(|e| format!("scenario input: {e}"))?;
        let manifest_input =
            fs::read_to_string(MANIFEST).map_err(|e| format!("manifest input: {e}"))?;
        report(&scenario_input, &manifest_input, true)
    });
    match result {
        Ok((output, exit)) => {
            print!("{output}");
            std::process::exit(exit);
        }
        Err(e) => {
            eprintln!("REJECTED: {e}");
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const COIL_VALUES: &str = "f_min_hz=30000;f_max_hz=50000;i_min_a=0.1;i_max_a=20;t_min_c=20;t_max_c=80;z_re_min_ohm=1;z_re_max_ohm=4;z_im_min_ohm=-10;z_im_max_ohm=12;u_z_ohm=0.1;gap_mm=5;offset_mm=0;samples=5";
    fn base() -> (String, String) {
        (
            include_str!("measurement-scenarios.tsv").into(),
            include_str!("measurement-manifest.tsv").into(),
        )
    }
    fn changed(input: &str, from: &str, to: &str) -> String {
        assert!(input.contains(from));
        input.replacen(from, to, 1)
    }
    #[test]
    fn empty_inventory_stays_indeterminate() {
        let (s, m) = base();
        let (out, code) = report(&s, &m, false).unwrap();
        assert_eq!(code, 2);
        assert!(out.contains("OVERALL\tINDETERMINATE"));
    }
    #[test]
    fn omitted_scenario_fails_closed() {
        let (s, m) = base();
        let s = s
            .lines()
            .filter(|l| !l.starts_with("fault_direct_bank\t"))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(report(&s, &m, false)
            .unwrap_err()
            .contains("missing scenario"));
    }
    #[test]
    fn omitted_manifest_row_fails_closed() {
        let (s, m) = base();
        let m = m
            .lines()
            .filter(|l| !l.starts_with("part_switch\t"))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(report(&s, &m, false)
            .unwrap_err()
            .contains("missing record"));
    }
    #[test]
    fn stale_return_rejected() {
        let (s, m) = base();
        let m = changed(
            &m,
            "coil_no_pan\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tNONE\tHOT0",
            "coil_no_pan\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tNONE\tPWR_RTN",
        );
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("coil_no_pan\tREJECTED"));
    }
    #[test]
    fn unknown_origin_rejected() {
        let (s, m) = base();
        let m = changed(&m, "bus_startup\tbus\tNONE", "bus_startup\tbus\tPASS");
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("bus_startup\tREJECTED"));
    }
    #[test]
    fn gate_off_without_current_zero_rejected() {
        let (s, m) = base();
        let m=changed(&m,"gate_permit\tstop\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN", "gate_permit\tstop\tSYNTHETIC\tfixture-1\tUNKNOWN\tUNKNOWN\tHOT0\tcommand_us=1;gate_off_us=3;i_start_a=10;zero_threshold_a=0.1;u_time_us=0.1");
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("gate_permit\tREJECTED\tmissing current_zero_us"));
    }
    #[test]
    fn nominal_bus_without_maximum_rejected() {
        let (s, m) = base();
        let m = changed(
            &m,
            "bus_surge\tbus\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN",
            "bus_surge\tbus\tSYNTHETIC\tfixture-1\tUNKNOWN\tUNKNOWN\tHOT0\tvb_nominal_v=390",
        );
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("bus_surge\tREJECTED"));
    }
    #[test]
    fn direct_bank_f2_shortcut_rejected() {
        let (s, m) = base();
        let m=changed(&m,"fault_direct_bank\tfault\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN", "fault_direct_bank\tfault\tSYNTHETIC\tfixture-1\tUNKNOWN\tUNKNOWN\tHOT0\tbank_peak_a=100;bank_energy_j=170;loop_r_mohm=10;loop_l_nh=100;clearer=F2");
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("fault_direct_bank\tREJECTED"));
    }
    #[test]
    fn free_air_l_cannot_fill_loaded_impedance() {
        let (s, m) = base();
        let m=changed(&m,"coil_reference_cold\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN", "coil_reference_cold\tcoil\tSYNTHETIC\tfixture-1\tcoil-1\tpan-1\tHOT0\tl_free_air_uh=88");
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("coil_reference_cold\tREJECTED"));
    }
    #[test]
    fn historical_single_frequency_is_not_operating_envelope() {
        let (s, m) = base();
        let values = COIL_VALUES.replace(
            "f_min_hz=30000;f_max_hz=50000",
            "f_min_hz=47000;f_max_hz=47000",
        );
        let m = changed(
            &m,
            "coil_reference_cold\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN",
            &format!(
                "coil_reference_cold\tcoil\tSYNTHETIC\tfixture-1\tcoil-1\tpan-1\tHOT0\t{values}"
            ),
        );
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("coil_reference_cold\tREJECTED\tloaded impedance needs frequency"));
    }
    #[test]
    fn one_pan_cannot_fill_reference_and_weak_states() {
        let (s, m) = base();
        let mut m = m;
        for id in ["coil_reference_cold", "coil_weak_pan"] {
            m = changed(
                &m,
                &format!("{id}\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN"),
                &format!("{id}\tcoil\tSYNTHETIC\tfixture-1\tcoil-1\tpan-1\tHOT0\t{COIL_VALUES}"),
            );
        }
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("COIL_COHORT\tREJECTED\tone favorable pan reused"));
    }
    #[test]
    fn mixed_article_or_coil_build_cannot_form_one_campaign() {
        let (s, m) = base();
        let mut rows = m;
        for (id, article, coil) in [
            ("coil_reference_cold", "fixture-1", "coil-1"),
            ("coil_weak_pan", "fixture-2", "coil-2"),
        ] {
            rows = changed(
                &rows,
                &format!("{id}\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN"),
                &format!(
                    "{id}\tcoil\tSYNTHETIC\t{article}\t{coil}\tpan-{coil}\tHOT0\t{COIL_VALUES}"
                ),
            );
        }
        let out = report(&s, &rows, false).unwrap().0;
        assert!(out.contains("ARTICLE_COHORT\tREJECTED"));
        assert!(out.contains("COIL_COHORT\tREJECTED\tcoil sweep rows name different"));
    }
    #[test]
    fn zero_volt_startup_is_valid_input_shape() {
        let mut r = manifest(&base().1).unwrap().remove("bus_startup").unwrap();
        r.values="vd_min_v=0;vd_max_v=390;vb_min_v=0;vb_max_v=391;vd_pp_v=0;vb_pp_v=0;u_v=1;source_i_max_a=6;source_p_max_w=1800;slew_v_per_us=0.1".into();
        assert!(value_shape(&r).is_ok());
    }
    #[test]
    fn complete_synthetic_control_remains_indeterminate() {
        let (s, m) = base();
        let m=changed(&m,"coil_reference_cold\tcoil\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN",&format!("coil_reference_cold\tcoil\tSYNTHETIC\tfixture-1\tcoil-1\tpan-1\tHOT0\t{COIL_VALUES}"));
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("coil_reference_cold\tINDETERMINATE\tsynthetic checker control only"));
    }
    #[test]
    fn equal_buses_do_not_prove_f2_state() {
        let mut r = manifest(&base().1).unwrap().remove("bus_f2_open").unwrap();
        r.values="vd_min_v=390;vd_max_v=395;vb_min_v=390;vb_max_v=395;vd_pp_v=5;vb_pp_v=5;u_v=1;source_i_max_a=6;source_p_max_w=1800;slew_v_per_us=0.1".into();
        assert!(value_shape(&r).unwrap_err().contains("missing f2_contact"));
        r.values.push_str(";f2_contact=OPEN_CONFIRMED;f2_i_max_a=0");
        assert!(value_shape(&r).is_ok());
    }
    #[test]
    fn forged_measured_row_without_raw_is_rejected() {
        let (s, m) = base();
        let m=changed(&m,"gate_permit\tstop\tNONE\tUNKNOWN\tUNKNOWN\tUNKNOWN\tHOT0\tUNKNOWN", "gate_permit\tstop\tMEASURED\tfixture-1\tUNKNOWN\tUNKNOWN\tHOT0\tcommand_us=1;gate_off_us=3;current_zero_us=6;i_start_a=10;zero_threshold_a=0.1;u_time_us=0.1");
        assert!(report(&s, &m, false)
            .unwrap()
            .0
            .contains("gate_permit\tREJECTED\traw path or SHA-256 malformed"));
    }
    #[test]
    fn missing_source_does_not_pass() {
        assert!(sha256("zapote/inverter/evidence/raw/nonexistent").is_err());
    }
}
