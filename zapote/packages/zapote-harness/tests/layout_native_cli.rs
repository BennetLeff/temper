//! Real KiCad boundary test: a saved copper edit must change Rust measurements.
//! Run explicitly with KICAD_PYTHON and --ignored; never substitutes mock geometry.
use serde_json::Value;
use std::{fs, path::Path, process::Command};

fn execute(board: &Path, output: &Path, baseline: Option<&Path>) -> Value {
    let python = std::env::var_os("KICAD_PYTHON").expect("set KICAD_PYTHON to a pcbnew runtime");
    let mut command = Command::new(env!("CARGO_BIN_EXE_zapote-layout-quality"));
    command
        .args(["--native"])
        .arg(board)
        .arg("--python")
        .arg(python)
        .arg("--output")
        .arg(output);
    if let Some(baseline) = baseline {
        command.arg("--baseline").arg(baseline);
    }
    let result = command.output().unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    serde_json::from_slice(&result.stdout).unwrap()
}
#[test]
#[ignore = "requires the live KiCad pcbnew runtime; keeps full evidence in temp directory"]
fn native_width_edit_changes_bound_report_and_preserves_source() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let board = root.join("power-stage-120v/native-17/section.kicad_pcb");
    let original = fs::read(&board).unwrap();
    let dir =
        std::env::temp_dir().join(format!("zapote-native-layout-proof-{}", std::process::id()));
    fs::create_dir(&dir).unwrap();
    let before = execute(&board, &dir.join("before"), None);
    // Every graph transition on the newly reconstructed C16 return must also
    // exist in KiCad's connectivity engine, independent of Rust's graph.
    let oracle = Command::new(std::env::var_os("KICAD_PYTHON").unwrap())
        .arg("-c")
        .arg(
            r#"
import json, sys, wx, pcbnew as p
app=wx.App(False)
b=p.LoadBoard(sys.argv[1])
b.BuildConnectivity()
c=b.GetConnectivity()
objects={t.m_Uuid.AsString():t for t in b.GetTracks()}
objects.update({pad.m_Uuid.AsString():pad for fp in b.GetFootprints() for pad in fp.Pads()})
route=json.load(open(sys.argv[2]))['native']['routes']['decoupling/C16/return']
ids=[v.split(':')[-1] for v in route['track_objects']]
checked=[]
for a,z in zip(ids,ids[1:]):
    if a==z:
        continue
    item=objects[a]
    # Native neighbour queries, not net-name equality or Rust coordinates.
    neighbours=list(c.GetConnectedTracks(item))+list(c.GetConnectedPads(item))
    assert z in {v.m_Uuid.AsString() for v in neighbours}, (a,z)
    checked.append([a,z])
assert len(checked)>2
print(json.dumps({'native_connected_transitions':checked, 'version':p.Version()}))
"#,
        )
        .arg(&board)
        .arg(dir.join("before/report.json"))
        .output()
        .unwrap();
    fs::write(dir.join("connectivity-oracle.stdout"), &oracle.stdout).unwrap();
    fs::write(dir.join("connectivity-oracle.stderr"), &oracle.stderr).unwrap();
    assert!(
        oracle.status.success(),
        "{}",
        String::from_utf8_lossy(&oracle.stderr)
    );
    let objects = before["native"]["routes"]["gate/A-high/driver"]["track_objects"]
        .as_array()
        .unwrap();
    let uuid = objects
        .iter()
        .filter_map(Value::as_str)
        .find(|s| !s.contains(':'))
        .unwrap();
    let changed = dir.join("narrowed.kicad_pcb");
    let mutation = Command::new(std::env::var_os("KICAD_PYTHON").unwrap())
        .arg("-c")
        .arg(
            r#"
import sys, wx, pcbnew as p
app=wx.App(False)
board=p.LoadBoard(sys.argv[1])
tracks=[t for t in board.GetTracks() if t.m_Uuid.AsString()==sys.argv[3]]
assert len(tracks)==1
track=tracks[0]
assert track.GetWidth()%2==0
track.SetWidth(track.GetWidth()//2)
p.SaveBoard(sys.argv[2],board)
"#,
        )
        .arg(&board)
        .arg(&changed)
        .arg(uuid)
        .output()
        .unwrap();
    fs::write(dir.join("mutation.stderr"), &mutation.stderr).unwrap();
    assert!(
        mutation.status.success(),
        "{}",
        String::from_utf8_lossy(&mutation.stderr)
    );
    let after = execute(
        &changed,
        &dir.join("after"),
        Some(&dir.join("before/report.json")),
    );
    assert_ne!(
        before["native"]["board_sha256"],
        after["native"]["board_sha256"]
    );
    let rows = after["comparison"]["changes"].as_array().unwrap();
    let row = rows
        .iter()
        .find(|r| {
            r["id"] == format!("copper/{uuid}") && r["metric"] == "section_resistance_ohm_20c"
        })
        .unwrap();
    let a = row["before"].as_f64().unwrap();
    let b = row["after"].as_f64().unwrap();
    assert!(
        (b / a - 2.).abs() < 1e-10,
        "halving native width must double section R"
    );
    let gate = rows
        .iter()
        .find(|r| r["id"] == "gate/A-high/driver" && r["metric"] == "track_resistance_ohm_20c")
        .unwrap();
    assert!((gate["change"].as_f64().unwrap() - a).abs() < 1e-10);
    let entry_before = before["native"]["pad_entries"]
        .as_array()
        .unwrap()
        .iter()
        .find(|e| e["track_uuid"] == uuid)
        .unwrap();
    let entry_after = after["native"]["pad_entries"]
        .as_array()
        .unwrap()
        .iter()
        .find(|e| e["track_uuid"] == uuid && e["pad_uuid"] == entry_before["pad_uuid"])
        .unwrap();
    // U1.15 is 0.6 mm wide. This real 0.8 -> 0.4 mm trace edit changes a
    // partial-width witness into a full-width witness at the same pad.
    assert_eq!(entry_before["entry"]["full_width_chord_observed"], false);
    assert!(
        (entry_before["entry"]["certified_chord_mm"]
            .as_f64()
            .unwrap()
            - 0.6)
            .abs()
            < 1e-9
    );
    assert_eq!(entry_after["entry"]["full_width_chord_observed"], true);
    assert!((entry_after["entry"]["certified_chord_mm"].as_f64().unwrap() - 0.4).abs() < 1e-9);
    assert_eq!(fs::read(&board).unwrap(), original);
    eprintln!("Native edit proof retained at {}", dir.display());
}

#[test]
fn native_options_fail_closed_without_launching_kicad() {
    for args in [
        vec!["--native"],
        vec!["--native", "missing.kicad_pcb"],
        vec!["--native", "missing.kicad_pcb", "--output"],
        vec!["--native", "missing.kicad_pcb", "--typo", "value"],
        vec![
            "--native",
            "missing.kicad_pcb",
            "--output",
            "a",
            "--output",
            "b",
        ],
    ] {
        let result = Command::new(env!("CARGO_BIN_EXE_zapote-layout-quality"))
            .args(args)
            .output()
            .unwrap();
        assert_eq!(result.status.code(), Some(2));
        assert!(result.stdout.is_empty());
        assert!(!result.stderr.is_empty());
    }
}
