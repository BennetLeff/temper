use sha2::{Digest, Sha256};
use std::{fs, path::Path};
use zapote_thermal::{
    parse_elmer_outputs_named, validate_measurements, CaseResult, AMBIENT_K, MESH_SIZES_M,
};

const MANIFEST: &str = include_str!("reference.sha256");
const MANIFEST_SHA256: &str = "bcc689ab278bd4e27cbd8f64dc8f51320bbdc01a4cf1835c9e278a859bfdfe10";

fn verify(root: &Path) -> bool {
    if format!("{:x}", Sha256::digest(MANIFEST.as_bytes())) != MANIFEST_SHA256 {
        return false;
    }
    MANIFEST.lines().all(|line| {
        let Some((digest, path)) = line.split_once("  ") else {
            return false;
        };
        fs::read(root.join(path))
            .is_ok_and(|bytes| format!("{:x}", Sha256::digest(bytes)) == digest)
    })
}

#[test]
fn replay_all_three_live_meshes_with_exact_inputs_and_raw_outputs() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    assert!(
        verify(root),
        "reference bytes changed; investigate before deliberately repinning"
    );
    let cases: Vec<_> = MESH_SIZES_M
        .iter()
        .map(|size| {
            let dir = root.join(format!("tests/fixtures/mesh-{size:.7}"));
            let m = parse_elmer_outputs_named(
                &fs::read(dir.join("elmersolver.log")).unwrap(),
                &fs::read(dir.join("scalars.dat")).unwrap(),
                Some(&fs::read(dir.join("scalars.dat.names")).unwrap()),
            )
            .unwrap();
            CaseResult {
                mesh_size_m: *size,
                temperature_rise_k: m.peak_temperature_k - AMBIENT_K,
                measurement: m,
            }
        })
        .collect();
    validate_measurements(&cases).unwrap();
}

#[test]
fn edited_deck_or_raw_result_cannot_retain_reference_identity() {
    let original = Path::new(env!("CARGO_MANIFEST_DIR"));
    let root = std::env::temp_dir().join(format!("zapote-thermal-pin-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    for line in MANIFEST.lines() {
        let (_, path) = line.split_once("  ").unwrap();
        let dest = root.join(path);
        fs::create_dir_all(dest.parent().unwrap()).unwrap();
        fs::copy(original.join(path), dest).unwrap();
    }
    assert!(verify(&root));
    for path in [
        "fixtures/case.sif",
        "tests/fixtures/mesh-0.0005000/elmersolver.log",
        "tests/fixtures/mesh-0.0005000/scalars.dat",
    ] {
        let bytes = fs::read(root.join(path)).unwrap();
        let mut changed = bytes.clone();
        changed.extend_from_slice(b"\nchanged\n");
        fs::write(root.join(path), changed).unwrap();
        assert!(!verify(&root), "changed {path} was accepted");
        fs::write(root.join(path), bytes).unwrap();
    }
    fs::remove_dir_all(root).unwrap();
}
