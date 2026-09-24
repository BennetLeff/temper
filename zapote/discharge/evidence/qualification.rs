//! Evidence boundary and deterministic adverse-case sweep for the P2 discharge model.
//! A manifest proves only completeness and byte identity; there is no trusted
//! physical-evidence review authority wired into this executable.

use super::{evaluate, Fault, GateCase, GateResult, Verdict};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::Command;

const REQUIRED: [&str; 10] = [
    "adopted_criterion",
    "exact_part_variants",
    "maximum_island_bounds",
    "coil_waveform_contact_life",
    "mounted_thermal",
    "fan_off_thermal",
    "f2_sense_service",
    "detached_inverter_energy",
    "fault_detection_lockout",
    "deliberate_rearm",
];

#[derive(Clone, Debug)]
struct Record {
    kind: String,
    article: String,
    case: String,
    range: String,
    raw_path: String,
    raw_sha256: String,
    adoption_id: String,
    independent_review_id: String,
}

impl Record {
    fn complete(&self, article: &str) -> bool {
        self.article == article
            && [
                &self.kind,
                &self.case,
                &self.range,
                &self.raw_path,
                &self.raw_sha256,
                &self.adoption_id,
                &self.independent_review_id,
            ]
            .iter()
            .all(|v| !v.is_empty() && *v != "UNKNOWN")
    }
}

pub(super) struct Manifest {
    records: BTreeMap<String, Record>,
    article: String,
    rejects: Vec<String>,
    unknowns: Vec<String>,
}

fn sha256(path: &str) -> Result<String, String> {
    let output = Command::new("shasum")
        .args(["-a", "256", path])
        .output()
        .map_err(|e| format!("cannot run shasum: {e}"))?;
    if !output.status.success() {
        return Err(format!("cannot hash {path}"));
    }
    let stdout = String::from_utf8(output.stdout).map_err(|_| "non-UTF8 digest output")?;
    stdout
        .split_whitespace()
        .next()
        .map(str::to_owned)
        .ok_or_else(|| "empty digest output".to_owned())
}

fn digest_is_valid(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}

impl Manifest {
    #[cfg(not(test))]
    pub(super) fn is_source_bound(&self) -> bool {
        self.rejects.is_empty()
    }

    pub(super) fn read(path: &str, case_path: &str) -> Self {
        let input = match std::fs::read_to_string(path) {
            Ok(v) => v,
            Err(e) => {
                return Self {
                    records: BTreeMap::new(),
                    article: "UNKNOWN".into(),
                    rejects: Vec::new(),
                    unknowns: vec![format!("qualification manifest unavailable: {e}")],
                };
            }
        };
        Self::parse(&input, case_path)
    }

    fn parse(input: &str, case_path: &str) -> Self {
        let mut manifest = Self {
            records: BTreeMap::new(),
            article: "UNKNOWN".into(),
            rejects: Vec::new(),
            unknowns: Vec::new(),
        };
        let mut header = BTreeMap::new();
        for (n, raw) in input.lines().enumerate() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(rest) = line.strip_prefix("record|") {
                let columns: Vec<&str> = rest.split('|').collect();
                if columns.len() != 9 {
                    manifest
                        .rejects
                        .push(format!("record line {} needs 9 columns", n + 1));
                    continue;
                }
                let id = columns[0].to_owned();
                if !REQUIRED.contains(&id.as_str()) {
                    manifest.rejects.push(format!("unknown evidence role {id}"));
                    continue;
                }
                let record = Record {
                    kind: columns[1].into(),
                    article: columns[2].into(),
                    case: columns[3].into(),
                    range: columns[4].into(),
                    raw_path: columns[5].into(),
                    raw_sha256: columns[6].into(),
                    adoption_id: columns[7].into(),
                    independent_review_id: columns[8].into(),
                };
                if manifest.records.insert(id.clone(), record).is_some() {
                    manifest
                        .rejects
                        .push(format!("duplicate evidence role {id}"));
                }
            } else if let Some((key, value)) = line.split_once('=') {
                if !["source_lock_sha256", "case_sha256", "article"].contains(&key) {
                    manifest.rejects.push(format!("unknown header {key}"));
                } else if header.insert(key.to_owned(), value.to_owned()).is_some() {
                    manifest.rejects.push(format!("duplicate header {key}"));
                }
            } else {
                manifest.rejects.push(format!("invalid line {}", n + 1));
            }
        }
        let source_lock = "zapote/discharge/evidence/source-inputs.sha256";
        for (name, path) in [
            ("source_lock_sha256", source_lock),
            ("case_sha256", case_path),
        ] {
            match header.get(name) {
                None => manifest.unknowns.push(format!("missing {name}")),
                Some(value) if !digest_is_valid(value) => {
                    if value == "UNKNOWN" {
                        manifest.unknowns.push(format!("{name} is UNKNOWN"));
                    } else {
                        manifest.rejects.push(format!("invalid {name}"));
                    }
                }
                Some(value) => match sha256(path) {
                    Ok(actual) if actual.eq_ignore_ascii_case(value) => {}
                    Ok(_) => manifest.rejects.push(format!("{name} mismatch for {path}")),
                    Err(e) => manifest.rejects.push(e),
                },
            }
        }
        manifest.article = header
            .get("article")
            .cloned()
            .unwrap_or_else(|| "UNKNOWN".into());
        if manifest.article == "UNKNOWN" || manifest.article.is_empty() {
            manifest.unknowns.push("article identity is UNKNOWN".into());
        }
        for id in REQUIRED {
            match manifest.records.get(id) {
                None => manifest
                    .unknowns
                    .push(format!("missing evidence role {id}")),
                Some(record) if !record.complete(&manifest.article) => manifest.unknowns.push(
                    format!("incomplete or different-article evidence role {id}"),
                ),
                Some(record) => {
                    if !digest_is_valid(&record.raw_sha256) {
                        manifest
                            .rejects
                            .push(format!("invalid raw SHA-256 for {id}"));
                    } else if !Path::new(&record.raw_path).is_file() {
                        manifest
                            .unknowns
                            .push(format!("raw record absent for {id}"));
                    } else {
                        match sha256(&record.raw_path) {
                            Ok(actual) if actual.eq_ignore_ascii_case(&record.raw_sha256) => {}
                            Ok(_) => manifest
                                .rejects
                                .push(format!("raw record hash mismatch for {id}")),
                            Err(e) => manifest.rejects.push(e),
                        }
                    }
                }
            }
        }
        manifest
    }
}

pub(super) fn apply_evidence_boundary(
    case: &GateCase,
    result: &mut GateResult,
    manifest: Option<&Manifest>,
) {
    if let Some(m) = manifest {
        result.rejects.extend(m.rejects.iter().cloned());
        result.unknowns.extend(m.unknowns.iter().cloned());
        for (asserted, role) in [
            (case.criteria_adopted, "adopted_criterion"),
            (case.exact_parts_verified, "exact_part_variants"),
            (
                case.contact_dc_life_verified || case.coil_timing_verified,
                "coil_waveform_contact_life",
            ),
            (case.installed_thermal_verified, "mounted_thermal"),
            (case.fan_off_thermal_verified, "fan_off_thermal"),
            (
                case.service_measurement_verified || case.f2_continuity_verified,
                "f2_sense_service",
            ),
            (case.fault_detection_verified, "fault_detection_lockout"),
            (case.deliberate_rearm_verified, "deliberate_rearm"),
        ] {
            if asserted && !m.records.get(role).is_some_and(|r| r.complete(&m.article)) {
                result.unknowns.push(format!(
                    "asserted case flag lacks matching evidence role {role}"
                ));
            }
        }
    } else {
        result
            .unknowns
            .push("no qualification manifest accompanies case booleans".into());
    }
    // A hash and a typed review-ID string cannot authenticate an independent
    // physical review. An external, trusted review workflow must consume the
    // records and issue its own verdict; this tool has no such authority.
    result.unknowns.push("physical evidence and independent adoption/review have not been authenticated by an external authority".into());
    result.verdict = if result.rejects.is_empty() {
        Verdict::Indeterminate
    } else {
        Verdict::Rejected
    };
}

const FAULTS: [(&str, Fault); 10] = [
    ("none", Fault::None),
    ("vd_string_open", Fault::VdStringOpen),
    ("vd_resistor_short", Fault::VdResistorShort),
    ("vb_resistor_open", Fault::VbResistorOpen),
    ("vb_resistor_short", Fault::VbResistorShort),
    ("contact_stuck_open", Fault::ContactStuckOpen),
    ("contact_stuck_closed", Fault::ContactStuckClosed),
    ("coil_stuck_energized", Fault::CoilStuckEnergized),
    ("vd_sense_open", Fault::VdSenseOpen),
    ("vb_sense_open", Fault::VbSenseOpen),
];

pub(super) fn sweep(base: &GateCase, manifest: &Manifest) -> String {
    let mut output = "id,f2_closed,mains_isolated,fault,model_verdict,qualification_verdict,vd_s,vb_s,coupled_s,vb_path_if_held_at_max_v_w,reject_count,unknown_count\n".to_owned();
    let mut seen = BTreeSet::new();
    for f2_closed in [false, true] {
        for mains_isolated in [false, true] {
            for (name, fault) in FAULTS {
                let mut case = base.clone();
                case.f2_closed = f2_closed;
                case.mains_isolated = mains_isolated;
                case.fault = fault;
                case.claim_deadline_while_mains_live = false;
                case.restart_claim = false;
                let id = format!(
                    "f2_{}_mains_{}_{}",
                    if f2_closed { "closed" } else { "open" },
                    if mains_isolated {
                        "isolated"
                    } else {
                        "attached"
                    },
                    name
                );
                row(&mut output, &mut seen, &id, name, &case, manifest);
            }
        }
    }
    let adverse: [(&str, &str, fn(&mut GateCase)); 5] = [
        ("coil_overvoltage_15p75", "none", |c| {
            c.coil_supply_max_v = 15.75
        }),
        ("detached_island_no_path", "none", |c| {
            c.inverter_detached_uf = 10.0
        }),
        ("mains_live_deadline", "none", |c| {
            c.mains_isolated = false;
            c.claim_deadline_while_mains_live = true;
        }),
        ("equal_charged_restart", "none", |c| {
            c.f2_closed = true;
            c.restart_claim = true;
            c.residual_vd_v = 100.0;
            c.residual_vb_v = 100.0;
        }),
        ("open_f2_sense_restart", "vd_sense_open", |c| {
            c.f2_closed = false;
            c.restart_claim = true;
            c.fault = Fault::VdSenseOpen;
        }),
    ];
    for (id, fault, mutate) in adverse {
        let mut case = base.clone();
        mutate(&mut case);
        row(&mut output, &mut seen, id, fault, &case, manifest);
    }
    output
}

fn row(
    output: &mut String,
    seen: &mut BTreeSet<String>,
    id: &str,
    fault: &str,
    case: &GateCase,
    manifest: &Manifest,
) {
    assert!(seen.insert(id.into()), "duplicate sweep case");
    let mut result = evaluate(case);
    let model = result.verdict;
    apply_evidence_boundary(case, &mut result, Some(manifest));
    let v = |x: Option<f64>| x.map_or_else(String::new, |n| format!("{n:.6}"));
    output.push_str(&format!(
        "{id},{},{},{fault},{model:?},{:?},{},{},{},{:.6},{},{}\n",
        case.f2_closed,
        case.mains_isolated,
        result.verdict,
        v(result.vd_seconds),
        v(result.vb_seconds),
        v(result.coupled_seconds),
        result.vb_continuous_w,
        result.rejects.len(),
        result.unknowns.len()
    ));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::illustrative_case;

    #[test]
    fn booleans_alone_never_grant_hardware_conditional() {
        let mut c = illustrative_case();
        c.criteria_adopted = true;
        c.exact_parts_verified = true;
        c.contact_dc_life_verified = true;
        c.coil_timing_verified = true;
        c.installed_thermal_verified = true;
        c.fan_off_thermal_verified = true;
        c.service_measurement_verified = true;
        let mut r = evaluate(&c);
        assert_eq!(r.verdict, Verdict::Conditional);
        apply_evidence_boundary(&c, &mut r, None);
        assert_eq!(r.verdict, Verdict::Indeterminate);
    }

    #[test]
    fn manifest_is_source_and_case_bound_and_incomplete() {
        let m = Manifest::read(
            "zapote/discharge/evidence/qualification-manifest.txt",
            "zapote/discharge/evidence/isolated-illustrative.case",
        );
        assert!(m.rejects.is_empty(), "{:?}", m.rejects);
        assert_eq!(m.records.len(), REQUIRED.len());
        assert!(m.unknowns.len() >= REQUIRED.len());
        let mut altered =
            std::fs::read_to_string("zapote/discharge/evidence/qualification-manifest.txt")
                .unwrap();
        altered = altered.replace("source_lock_sha256=787ac3", "source_lock_sha256=000000");
        assert!(Manifest::parse(
            &altered,
            "zapote/discharge/evidence/isolated-illustrative.case"
        )
        .rejects
        .iter()
        .any(|s| s.contains("source_lock_sha256 mismatch")));
        let source =
            std::fs::read_to_string("zapote/discharge/evidence/qualification-manifest.txt")
                .unwrap();
        let changed_case = source.replace("case_sha256=7acf2f", "case_sha256=000000");
        assert!(Manifest::parse(
            &changed_case,
            "zapote/discharge/evidence/isolated-illustrative.case"
        )
        .rejects
        .iter()
        .any(|s| s.contains("case_sha256 mismatch")));
    }

    #[test]
    fn duplicate_and_omitted_evidence_roles_fail_closed() {
        let source =
            std::fs::read_to_string("zapote/discharge/evidence/qualification-manifest.txt")
                .unwrap();
        let line = source
            .lines()
            .find(|s| s.starts_with("record|adopted_criterion|"))
            .unwrap();
        let duplicate = format!("{source}\n{line}\n");
        assert!(Manifest::parse(
            &duplicate,
            "zapote/discharge/evidence/isolated-illustrative.case"
        )
        .rejects
        .iter()
        .any(|s| s.contains("duplicate evidence role")));
        let omitted = source.replace(line, "");
        assert!(Manifest::parse(
            &omitted,
            "zapote/discharge/evidence/isolated-illustrative.case"
        )
        .unknowns
        .iter()
        .any(|s| s.contains("missing evidence role adopted_criterion")));
    }

    #[test]
    fn complete_self_authored_records_still_cannot_promote() {
        let source =
            std::fs::read_to_string("zapote/discharge/evidence/qualification-manifest.txt")
                .unwrap();
        let sha = sha256("zapote/discharge/evidence/isolated-illustrative.case").unwrap();
        let mut filled = String::new();
        for line in source.lines() {
            if line.starts_with("record|") {
                let id = line.split('|').nth(1).unwrap();
                filled.push_str(&format!("record|{id}|bench|article-A|case-A|0-450V|zapote/discharge/evidence/isolated-illustrative.case|{sha}|adoption-A|review-A\n"));
            } else if line.starts_with("article=") {
                filled.push_str("article=article-A\n");
            } else {
                filled.push_str(line);
                filled.push('\n');
            }
        }
        let m = Manifest::parse(
            &filled,
            "zapote/discharge/evidence/isolated-illustrative.case",
        );
        assert!(m.rejects.is_empty(), "{:?}", m.rejects);
        assert!(m.unknowns.is_empty(), "{:?}", m.unknowns);
        let mut r = evaluate(&illustrative_case());
        apply_evidence_boundary(&illustrative_case(), &mut r, Some(&m));
        assert_eq!(r.verdict, Verdict::Indeterminate);
        assert!(r.unknowns.iter().any(|s| s.contains("external authority")));
        let tampered = filled.replace(&format!("|{sha}|"), &format!("|{}|", "0".repeat(64)));
        assert!(Manifest::parse(
            &tampered,
            "zapote/discharge/evidence/isolated-illustrative.case"
        )
        .rejects
        .iter()
        .any(|s| s.contains("raw record hash mismatch")));
    }

    #[test]
    fn sweep_covers_all_topologies_and_adverse_controls() {
        let m = Manifest::read(
            "zapote/discharge/evidence/qualification-manifest.txt",
            "zapote/discharge/evidence/isolated-illustrative.case",
        );
        let csv = sweep(&illustrative_case(), &m);
        assert_eq!(csv.lines().count(), 46);
        for id in [
            "coil_overvoltage_15p75",
            "detached_island_no_path",
            "mains_live_deadline",
            "equal_charged_restart",
            "open_f2_sense_restart",
        ] {
            assert!(
                csv.lines()
                    .any(|line| line.starts_with(&format!("{id},")) && line.contains("Rejected")),
                "{id}"
            );
        }
        assert!(csv.contains("f2_open_mains_attached_none,false,false,none"));
        assert!(csv.contains("f2_closed_mains_isolated_none,true,true,none"));
    }
}
