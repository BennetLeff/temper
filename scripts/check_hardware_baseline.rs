//! Fail closed unless the complete current hardware snapshot and selected PCB match.
//! Standalone rustc tool: does not build or modify any shared pyo3 extension.
use std::{
    collections::HashSet,
    env, fs,
    path::{Component, Path},
    process::{Command, ExitCode},
};

struct Input<'a> {
    role: &'a str,
    path: &'a str,
    hash: &'a str,
}

fn parse(text: &str) -> Result<Vec<Input<'_>>, String> {
    let mut inputs = Vec::new();
    let mut paths = HashSet::new();
    for (line, row) in text.lines().enumerate() {
        if row.is_empty() || row.starts_with('#') {
            continue;
        }
        let fields: Vec<_> = row.split('\t').collect();
        if fields.len() != 3 {
            return Err(format!("invalid manifest row {}", line + 1));
        }
        let (role, path, hash) = (fields[0], fields[1], fields[2]);
        if !matches!(role, "board" | "input")
            || path.is_empty()
            || Path::new(path)
                .components()
                .any(|p| !matches!(p, Component::Normal(_)))
            || !paths.insert(path)
            || hash.len() != 64
            || !hash
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err(format!(
                "invalid or duplicate manifest entry on row {}",
                line + 1
            ));
        }
        inputs.push(Input { role, path, hash });
    }
    if inputs.iter().filter(|i| i.role == "board").count() != 1 || inputs.len() < 4 {
        return Err("manifest must pin exactly one board and its supporting inputs".into());
    }
    Ok(inputs)
}

fn sha256(path: &Path) -> Result<String, String> {
    if !path.is_file() {
        return Err(format!("missing input: {}", path.display()));
    }
    // Use platform SHA tools instead of maintaining another crypto implementation.
    for (name, flags) in [
        ("sha256sum", vec!["--"]),
        ("shasum", vec!["-a", "256", "--"]),
    ] {
        match Command::new(name).args(flags).arg(path).output() {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(format!("{name}: {e}")),
            Ok(result) if !result.status.success() => {
                return Err(format!(
                    "{name} failed for {}: {}",
                    path.display(),
                    String::from_utf8_lossy(&result.stderr)
                ))
            }
            Ok(result) => {
                let output = String::from_utf8(result.stdout).map_err(|e| e.to_string())?;
                let digest = output.split_whitespace().next().ok_or("empty SHA output")?;
                if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_hexdigit()) {
                    return Err("malformed SHA output".into());
                }
                return Ok(digest.to_ascii_lowercase());
            }
        }
    }
    Err("install sha256sum or shasum; no hash check was performed".into())
}

fn run(args: &[String]) -> Result<(), String> {
    if args.len() != 1 && !(args.len() == 3 && args[1] == "--board") {
        return Err("usage: check_hardware_baseline ROOT [--board PCB]".into());
    }
    let root = Path::new(&args[0]);
    let text = fs::read_to_string(root.join("hardware/CURRENT.tsv")).map_err(|e| e.to_string())?;
    let inputs = parse(&text)?;
    for input in &inputs {
        let actual = sha256(&root.join(input.path))?;
        if actual != input.hash {
            return Err(format!("changed current input: {}\nexpected {}\nactual   {}\nReconcile the design revision; never silently repin it.", input.path, input.hash, actual));
        }
    }
    let board = inputs
        .iter()
        .find(|i| i.role == "board")
        .ok_or("missing board")?;
    if args.len() == 3 {
        let selected = Path::new(&args[2]);
        if sha256(selected)? != board.hash {
            return Err(format!("WRONG HARDWARE BASELINE: {}\nUse {} (SHA-256 {}). Legacy, placement-only, stale routed and modified boards are not the current candidate.", selected.display(), root.join(board.path).display(), board.hash));
        }
    }
    println!("PASS: {}\nSHA-256 {}\n{} pinned inputs checked. Identity only; not manufacturing or mains release.", root.join(board.path).display(), board.hash, inputs.len());
    Ok(())
}

fn main() -> ExitCode {
    match run(&env::args().skip(1).collect::<Vec<_>>()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("HARDWARE BASELINE BLOCKED: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn manifest() -> String {
        [
            "board\tboard.pcb",
            "input\tproject.pro",
            "input\tschematic.sch",
            "input\tcopper.json",
        ]
        .map(|s| format!("{s}\t{}", "a".repeat(64)))
        .join("\n")
    }
    #[test]
    fn valid_manifest_is_accepted() {
        assert!(parse(&manifest()).is_ok());
    }
    #[test]
    fn second_board_is_rejected() {
        assert!(parse(&manifest().replace("input\tproject", "board\tproject")).is_err());
    }
    #[test]
    fn traversal_is_rejected() {
        assert!(parse(&manifest().replace("board.pcb", "../board.pcb")).is_err());
    }
    #[test]
    fn shortened_digest_is_rejected() {
        assert!(parse(&manifest().replace(&"a".repeat(64), &"a".repeat(16))).is_err());
    }
    #[test]
    fn duplicate_path_is_rejected() {
        assert!(parse(&manifest().replace("project.pro", "board.pcb")).is_err());
    }
    #[test]
    fn empty_manifest_is_rejected() {
        assert!(parse("# absent\n").is_err());
    }
    #[test]
    fn changed_and_missing_sidecars_are_rejected() {
        let root = env::temp_dir().join(format!("temper-baseline-test-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        fs::create_dir(root.join("hardware")).unwrap();
        let mut rows = Vec::new();
        for (role, name) in [
            ("board", "board.pcb"),
            ("input", "project.pro"),
            ("input", "schematic.sch"),
            ("input", "copper.json"),
        ] {
            let path = root.join(name);
            fs::write(&path, name).unwrap();
            rows.push(format!("{role}\t{name}\t{}", sha256(&path).unwrap()));
        }
        fs::write(root.join("hardware/CURRENT.tsv"), rows.join("\n")).unwrap();
        let args = vec![root.to_string_lossy().into_owned()];
        assert!(run(&args).is_ok());
        fs::write(root.join("project.pro"), "different rules").unwrap();
        assert!(run(&args).unwrap_err().contains("changed current input"));
        fs::remove_file(root.join("project.pro")).unwrap();
        assert!(run(&args).unwrap_err().contains("missing input"));
        fs::remove_dir_all(root).unwrap();
    }
}
