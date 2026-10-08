use std::{collections::BTreeMap, fs, path::PathBuf};
use zapote_core::{CheckReport, Finding, Status};
use zapote_harness::runner::{self, Manifest, NativeCommand};

fn manifest() -> Manifest {
    let base = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../validation");
    let mut m: Manifest =
        serde_json::from_slice(&fs::read(base.join("units.json")).unwrap()).unwrap();
    for s in &mut m.units {
        for p in [&mut s.source, &mut s.native, &mut s.board, &mut s.schematic]
            .into_iter()
            .chain(s.contract.iter_mut())
            .chain(s.composite.iter_mut())
        {
            *p = base.join(&*p);
        }
    }
    m
}

#[test]
fn all_maintained_saved_units_bind_and_execute_their_truth_functions() {
    let m = manifest();
    runner::validate_manifest(&m).unwrap();
    for spec in m.units {
        let (report, native, hashes) =
            runner::evaluate(&spec).unwrap_or_else(|e| panic!("{}: {e}", spec.unit.name()));
        assert!(!report.checked_rules.is_empty(), "{}", spec.unit.name());
        assert!(!native.traces.is_empty(), "{}", spec.unit.name());
        assert_eq!(hashes[&spec.board], native.board_sha256);
    }
}

#[test]
fn missing_or_duplicate_unit_cannot_shrink_the_suite() {
    let mut m = manifest();
    runner::validate_manifest(&m).unwrap();
    m.units.pop();
    assert!(runner::validate_manifest(&m)
        .unwrap_err()
        .contains("exactly once"));
    m.units.push(m.units[0].clone());
    assert!(runner::validate_manifest(&m)
        .unwrap_err()
        .contains("exactly once"));
}

#[test]
fn omitted_check_fails_and_mixed_status_never_loses_failure() {
    let required = vec!["a".into(), "b".into()];
    let mut report = CheckReport::from_findings(vec![], required.clone(), vec![]);
    assert_eq!(
        runner::enforce_required(&required, &report).status,
        Status::Pass
    );
    report.checked_rules.pop();
    let missing = runner::enforce_required(&required, &report);
    assert_eq!(missing.status, Status::Fail);
    let incomplete = CheckReport::from_findings(
        vec![Finding::indeterminate("x", "missing", "x")],
        vec!["x".into()],
        vec![],
    );
    assert_eq!(
        runner::combine(&[&report, &missing, &incomplete]).status,
        Status::Fail
    );
}

struct Temp(PathBuf);
impl Temp {
    fn new(name: &str) -> Self {
        let p = std::env::temp_dir().join(format!("zapote-runner-{}-{name}", std::process::id()));
        fs::create_dir(&p).unwrap();
        Self(p)
    }
}
impl Drop for Temp {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn stale_native_receipt_is_rejected_even_with_same_basename() {
    let t = Temp::new("receipt");
    let source = t.0.join("section.kicad_pcb");
    fs::write(&source, b"original board").unwrap();
    let report = include_bytes!("../../../interlock/evidence/final-native-04/drc.json");
    let c = NativeCommand {
        argv: vec![],
        returncode: 0,
        input_sha256: runner::digest(b"original board"),
        report_sha256: runner::digest(report),
        report_path: t.0.join("drc.json"),
        dependency_hashes: BTreeMap::from([(source.clone(), runner::digest(b"original board"))]),
        tool_version: "10.0.4".into(),
    };
    runner::verify_native_binding(&c, &source, report).unwrap();
    assert!(
        runner::verify_native_binding(&c, &source, b"replacement report")
            .unwrap_err()
            .contains("hash mismatch")
    );
    fs::write(&source, b"changed board").unwrap();
    assert!(runner::verify_native_binding(&c, &source, report)
        .unwrap_err()
        .contains("hash mismatch"));
}

#[test]
fn changed_saved_pcb_and_composite_identity_fail_after_passing_baseline() {
    let t = Temp::new("composite");
    let mut s = manifest().units.remove(0);
    runner::evaluate(&s).unwrap();
    let mut composite: serde_json::Value =
        serde_json::from_slice(&fs::read(s.composite.as_ref().unwrap()).unwrap()).unwrap();
    composite["identity"]["source_manifest_sha256"] = "0".repeat(64).into();
    let p = t.0.join("input.json");
    fs::write(&p, serde_json::to_vec(&composite).unwrap()).unwrap();
    s.composite = Some(p);
    assert!(runner::evaluate(&s)
        .unwrap_err()
        .contains("composite source/native/board binding differs"));
    s = manifest().units.remove(0);
    let p = t.0.join("section.kicad_pcb");
    let mut bytes = fs::read(&s.board).unwrap();
    bytes.push(b' ');
    fs::write(&p, bytes).unwrap();
    s.board = p;
    assert!(runner::evaluate(&s)
        .unwrap_err()
        .contains("saved PCB bytes"));
}
