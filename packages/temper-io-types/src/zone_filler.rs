// zone_filler: fill_zones_pcbnew, fill_zones_if_present.
//
// Genuinely not convertible to pure Rust: this writes a throwaway Python
// script that imports KiCad's `pcbnew` module (a C++ extension with no
// Rust equivalent) and shells out to the *host Python interpreter*
// (`sys.executable`) via `subprocess.run` to execute it. The entire
// operation is "drive a live Python + KiCad process from Rust" — there is
// no pure kernel to extract. It stays behind the `python` feature in full
// and is not exported on wasm32 (which additionally has no filesystem or
// process-spawning capability to do this even in principle).
//
// Restored 2026-07-27. These two functions, together with
// ConfigBoardMismatchError/extract_config_refs/verify_config_matches_netlist,
// were added by 67e4d4ab and silently discarded by the merge commit cd4e896a,
// which kept the Python shims importing them. zone_filler.py:7 has been raising
// ImportError at module load ever since; nothing caught it because no test
// exercises that module.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::path::PathBuf;

#[pyfunction]
pub fn fill_zones_pcbnew(py: Python<'_>, pcb_file: PathBuf) -> PyResult<bool> {
    let script_path = pcb_file
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."))
        .join("_zone_fill_temp.py");
    let pcb_str = pcb_file.to_str().unwrap_or("?");
    let script_content = format!(
        r#"#!/usr/bin/env python3
import sys

try:
    import pcbnew
except ImportError:
    print("ERROR: pcbnew module not available. KiCad Python API is required.", file=sys.stderr)
    print("Zone filling skipped. Zones will need to be filled manually in KiCad.", file=sys.stderr)
    sys.exit(0)

board = pcbnew.LoadBoard(r"{}")

zones = list(board.Zones())

if len(zones) == 0:
    print("No zones found in PCB - nothing to fill")
    sys.exit(0)

print(f"Found {{len(zones)}} zones in PCB")

filler = pcbnew.ZONE_FILLER(board)

print(f"Filling {{len(zones)}} zones...")
try:
    filler.Fill(zones)
    board.Save(r"{}")
    print("✓ Successfully filled {{len(zones)}} zones")
except Exception as e:
    print(f"ERROR filling zones: {{e}}", file=sys.stderr)
    sys.exit(1)
"#,
        pcb_str, pcb_str
    );

    std::fs::write(&script_path, &script_content).map_err(|e| {
        pyo3::exceptions::PyOSError::new_err(format!("Error writing temp script: {}", e))
    })?;

    let sys = py.import("sys")?;
    let exe: String = sys.getattr("executable")?.extract()?;
    let subprocess = py.import("subprocess")?;

    let kwargs = PyDict::new(py);
    kwargs.set_item("capture_output", true)?;
    kwargs.set_item("text", true)?;
    kwargs.set_item("timeout", 30)?;

    let script_path_str = script_path.to_str().unwrap_or("?");
    let args = PyList::new(py, [exe.as_str(), script_path_str])?;
    let result = subprocess.call_method("run", (args,), Some(&kwargs));

    let _ = std::fs::remove_file(&script_path);

    match result {
        Ok(r) => {
            let stdout: String = r.getattr("stdout")?.extract().unwrap_or_default();
            let stderr: String = r.getattr("stderr")?.extract().unwrap_or_default();
            let returncode: i32 = r.getattr("returncode")?.extract().unwrap_or(1);
            let trimmed_out = stdout.trim();
            if !trimmed_out.is_empty() {
                println!("{}", trimmed_out);
            }
            let trimmed_err = stderr.trim();
            if !trimmed_err.is_empty() {
                eprintln!("{}", trimmed_err);
            }
            Ok(returncode == 0)
        }
        Err(e) => {
            if e.is_instance_of::<pyo3::exceptions::PyBaseException>(py) {
                eprintln!("Zone filling timed out after 30 seconds");
            } else {
                eprintln!("Error filling zones: {}", e);
            }
            Ok(false)
        }
    }
}

#[pyfunction]
#[pyo3(signature = (pcb_file, verbose = true))]
pub fn fill_zones_if_present(py: Python<'_>, pcb_file: PathBuf, verbose: bool) -> PyResult<bool> {
    if !pcb_file.exists() {
        if verbose {
            eprintln!("PCB file not found: {}", pcb_file.display());
        }
        return Ok(false);
    }

    if verbose {
        println!("\n=== Zone Filling ===");
        println!(
            "PCB: {}",
            pcb_file.file_name().unwrap_or_default().to_string_lossy()
        );
    }

    let success = fill_zones_pcbnew(py, pcb_file)?;

    if verbose && success {
        println!("=== Zone Filling Complete ===\n");
    }

    Ok(success)
}
