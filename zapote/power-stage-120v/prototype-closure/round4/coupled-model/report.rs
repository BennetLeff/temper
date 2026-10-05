//! Package numerical receipts without converting completion into qualification.
use std::{collections::BTreeMap, env, error::Error, fs, path::Path, process::Command};
fn sha(path: &Path) -> Result<String, Box<dyn Error>> {
    let r = Command::new("shasum")
        .arg("-a")
        .arg("256")
        .arg(path)
        .output()?;
    if !r.status.success() {
        return Err("sha256 failed".into());
    }
    Ok(String::from_utf8(r.stdout)?
        .split_whitespace()
        .next()
        .ok_or("empty hash")?
        .into())
}
fn rows(path: &Path) -> Result<(Vec<String>, Vec<Vec<String>>), Box<dyn Error>> {
    let s = fs::read_to_string(path)?;
    let mut lines = s.lines();
    let header = lines
        .next()
        .ok_or("missing header")?
        .split(',')
        .map(str::to_owned)
        .collect();
    let rows = lines
        .map(|l| l.split(',').map(str::to_owned).collect())
        .collect();
    Ok((header, rows))
}
fn main() -> Result<(), Box<dyn Error>> {
    let arg = env::args().nth(1).ok_or("output root required")?;
    let out = Path::new(&arg);
    let base = Path::new("zapote/power-stage-120v/prototype-closure/round4/coupled-model");
    let original = Path::new(
        "zapote/power-stage-120v/prototype-closure/round4/firmware/conductance-study.csv",
    );
    if fs::read(original)? != fs::read(base.join("conductance-study.csv"))? {
        return Err("firmware control snapshot drifted".into());
    }
    let mut inputs = String::from("sha256\tpath\n");
    for path in [
        base.join("runner.rs"),
        base.join("coordination.rs"),
        base.join("report.rs"),
        base.join("reduced.cir"),
        base.join("joined.cir"),
        base.join("conductance-study.csv"),
        base.join("README.md"),
        base.join("protection-coordination.md"),
        base.join("run.sh"),
        original.to_path_buf(),
        Path::new("zapote/power-stage-120v/native-19/section.kicad_pcb").to_path_buf(),
    ] {
        inputs.push_str(&format!("{}\t{}\n", sha(&path)?, path.display()));
    }
    fs::write(out.join("source-hashes.tsv"), inputs)?;
    let mut dirs: Vec<_> = fs::read_dir(out)?
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    let mut index = String::from("batch\tcase\tbatch_status\trole\tdeck_sha256\tlog_sha256\n");
    let (canonical_header, _) = rows(&out.join("joined-v3-crest/results.csv"))?;
    let mut combined = format!("batch,role,batch_status,{}\n", canonical_header.join(","));
    let mut inventory = String::from("batch\tstatus\n");
    for d in dirs {
        let name = d.file_name().ok_or("batch name")?.to_string_lossy();
        let status =
            fs::read_to_string(d.join("STATUS")).unwrap_or_else(|_| "NO_COMPLETION_RECEIPT".into());
        let status = status.trim();
        inventory.push_str(&format!("{name}\t{status}\n"));
        if !d.join("results.csv").exists() {
            continue;
        }
        let (header, rows) = rows(&d.join("results.csv"))?;
        let role = if name.starts_with("joined-v3-") {
            "current_50ms_proof_source_coupled"
        } else {
            "historical_diagnostic_not_current_sequence"
        };
        for row in rows {
            if row.len() != header.len() {
                return Err("bad result column count".into());
            }
            for v in row.iter().skip(1) {
                if !v.parse::<f64>()?.is_finite() {
                    return Err("nonfinite result".into());
                }
            }
            let dir = d.join(&row[0]);
            let log = fs::read_to_string(dir.join("ngspice.log"))?;
            if log.contains("run simulation(s) aborted") || log.contains("Timestep too small") {
                return Err("result from aborted run".into());
            }
            index.push_str(&format!(
                "{name}\t{}\t{status}\t{role}\t{}\t{}\n",
                row[0],
                sha(&dir.join("joined.cir"))?,
                sha(&dir.join("ngspice.log"))?
            ));
            // Historical schemas lack newer admission columns. Missing evidence
            // stays blank; never coerce an unmeasured value to zero.
            let canonical_row: Vec<_> = canonical_header
                .iter()
                .map(|column| {
                    header
                        .iter()
                        .position(|h| h == column)
                        .map_or("", |i| row[i].as_str())
                })
                .collect();
            combined.push_str(&format!(
                "{name},{role},{status},{}\n",
                canonical_row.join(",")
            ));
        }
    }
    fs::write(out.join("run-inventory.tsv"), inventory)?;
    fs::write(out.join("evidence-index.tsv"), index)?;
    fs::write(out.join("all-results.csv"), combined)?;
    let mut convergence = String::from(
        "coarse_batch,fine_batch,metric,coarse,fine,relative_change,within_2_percent\n",
    );
    for (coarse, fine) in [
        ("refine-detuned", "detuned-fine"),
        ("joined-v3-crest", "joined-v3-refine"),
    ] {
        let (h, c) = rows(&out.join(coarse).join("results.csv"))?;
        let (_, f) = rows(&out.join(fine).join("results.csv"))?;
        let c = c.first().ok_or("missing coarse")?;
        let f = f.first().ok_or("missing fine")?;
        let norm = |batch: &str, name: &str| -> Result<String, Box<dyn Error>> {
            Ok(
                fs::read_to_string(out.join(batch).join(name).join("joined.cir"))?
                    .lines()
                    .filter(|l| !l.starts_with(".tran "))
                    .collect::<Vec<_>>()
                    .join("\n"),
            )
        };
        if norm(coarse, &c[0])? != norm(fine, &f[0])? {
            return Err("comparison changes more than timestep".into());
        }
        for i in 1..h.len() {
            let a: f64 = c[i].parse()?;
            let b: f64 = f[i].parse()?;
            let rel = (a - b).abs() / a.abs().max(b.abs()).max(1e-12);
            convergence.push_str(&format!(
                "{coarse},{fine},{},{a:.10e},{b:.10e},{rel:.8e},{}\n",
                h[i],
                rel <= 0.02
            ));
        }
    }
    fs::write(out.join("convergence.csv"), convergence)?;
    let mut verdicts = BTreeMap::new();
    verdicts.insert("hardware_release", "DENIED");
    verdicts.insert(
        "commissioning_current_permission",
        "0 A: exact hot 50kHz capacitor application limits absent",
    );
    verdicts.insert(
        "catch_short_refinement",
        "FAILED numerical convergence; no protective let-through bound",
    );
    verdicts.insert(
        "detailed_four_switch_reference",
        "INCOMPLETE; no cross-model validation",
    );
    verdicts.insert(
        "historical_detuned_integral_convergence",
        "FAILED 2% threshold at0.25us/0.125us; see convergence.csv",
    );
    let body = verdicts
        .into_iter()
        .map(|(k, v)| format!("  {k:?}: {v:?}"))
        .collect::<Vec<_>>()
        .join(",\n");
    fs::write(out.join("verdicts.json"), format!("{{\n{body}\n}}\n"))?;
    println!("Evidence packaged; numerical completion is not qualification.");
    Ok(())
}
