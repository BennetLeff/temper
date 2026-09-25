//! SYNTHETIC-ONLY fixture producer for line-load-native-runner-12.
//!
//! This is not an ngspice host and is never an electrical acceptance result.
//! It emits an exact little-endian normal15 raw plot to the caller's path so
//! the runner's FIFO, native decoder, metadata, and strict-checker rejection
//! paths can be exercised without a full simulation.

use std::fs::{self, File};
use std::io::{self, BufWriter, Write};
use std::path::Path;

const STEP_S: f64 = 500e-9;
const END_S: f64 = 0.65;
const BASE_POINTS: u64 = 1_300_001; // 0 ..= 0.65 at 500 ns
const DUPLICATE_INDEX: u64 = 1_240_000; // t = 0.620000 s
const POINTS: u64 = BASE_POINTS + 1;
const LINE_RMS_V: f64 = 108.0;
const LOAD_OHM: f64 = 416.460_488_957;
const BUS_V: f64 = 389.6;
const HEADER: &str = "Title: SYNTHETIC ONLY -- no ngspice electrical result\nDate: synthetic-fixture\nCommand: parent-fixture\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 15\nNo. Points: 1300002\nVariables:\n\t0\ttime\ttime\n\t1\tv(acsrc)\tvoltage\n\t2\tv(acn)\tvoltage\n\t3\ti(vac)\tcurrent\n\t4\tv(load)\tvoltage\n\t5\tv(vb)\tvoltage\n\t6\ti(lboost)\tcurrent\n\t7\tv(vd)\tvoltage\n\t8\tv(sw)\tvoltage\n\t9\tv(gate)\tvoltage\n\t10\tv(q)\tvoltage\n\t11\tv(en)\tvoltage\n\t12\tv(fault)\tvoltage\n\t13\tv(vcomp)\tvoltage\n\t14\tv(icomp)\tvoltage\nBinary:\n";

fn reject_path(path: &str) -> Result<(), String> {
    if path.is_empty() || path.chars().any(char::is_whitespace) || path.contains([';', '\n', '"']) {
        Err("simple path required".into())
    } else {
        Ok(())
    }
}

fn emit_row<W: Write>(out: &mut W, time_s: f64) -> io::Result<()> {
    let omega_t = 2.0 * std::f64::consts::PI * 60.0 * time_s;
    let vac = LINE_RMS_V * 2.0_f64.sqrt() * omega_t.sin();
    let p_load = BUS_V * BUS_V / LOAD_OHM;
    let i_rms = p_load / LINE_RMS_V;
    // ngspice's source-current convention is opposite the load current;
    // normalize.rs negates i(Vac), giving positive real input power.
    let i_vac = -i_rms * 2.0_f64.sqrt() * omega_t.sin();
    let row = [
        time_s, vac, 0.0, i_vac, BUS_V, BUS_V, 0.0, BUS_V,
        20.0, 10.0, 5.0, 5.0, 0.0, 2.5, 0.0,
    ];
    for (index, value) in row.into_iter().enumerate() {
        if index != 0 { /* binary rows have no separators */ }
        out.write_all(&value.to_le_bytes())?;
    }
    Ok(())
}

fn write_receipts() -> Result<(), String> {
    fs::write("progress.tsv", "wall_s\tsim_s\tpercent\trecent_sim_s_per_wall_s\tcallbacks\tfirst_invalid\tduplicate_count\tbackwards_count\n0.001\t6.50000000000000022e-1\t100.000000\t650.000000\t1300002\ttrue\t1\t0\n").map_err(|e| e.to_string())?;
    fs::write("stop.txt", "reason=solver_stopped\nwall_s=0.001\nsim_s=6.50000000000000022e-1\npoints=1300002\nfirst_invalid=true\nduplicate_count=1\nbackwards_count=0\ncontinue_after_duplicate=true\ndiagnostic_only=true\nsynthetic_fixture=true\n").map_err(|e| e.to_string())?;
    fs::write("first-invalid.tsv", "first_invalid=true\nsynthetic_duplicate_time_s=6.20000000000000000e-1\nsynthetic_fixture=true\n").map_err(|e| e.to_string())?;
    fs::write("capture-metadata.json", format!("{{\n  \"stop_reason\": \"solver_stopped\",\n  \"points\": {POINTS},\n  \"first_invalid\": true,\n  \"seen_names_mask\": 65535,\n  \"expected_names_mask\": 65535,\n  \"duplicate_count\": 1,\n  \"backwards_count\": 0,\n  \"continue_after_duplicate\": true,\n  \"diagnostic_only\": true,\n  \"accepted\": false,\n  \"export_format\": \"ngspice-real-native\",\n  \"byte_order\": \"little\",\n  \"writer_platform\": \"synthetic-fixture\",\n  \"schema\": \"normal15\",\n  \"validation_policy\": \"event-aware-normal-v1\",\n  \"synthetic_fixture\": true,\n  \"synthetic_fixture_note\": \"not ngspice and not electrical evidence\"\n}}\n")).map_err(|e| e.to_string())?;
    Ok(())
}

fn run(args: &[String]) -> Result<(), String> {
    if args.len() != 6 {
        return Err("usage: synthetic_normal15_producer DECK WALL_SECONDS TARGET_SECONDS EXPORT_PATH SNAPSHOT_PATH".into());
    }
    let _deck = Path::new(&args[1]);
    let wall: f64 = args[2].parse().map_err(|_| "invalid wall seconds")?;
    let target: f64 = args[3].parse().map_err(|_| "invalid target seconds")?;
    if !wall.is_finite() || wall <= 0.0 || !target.is_finite() || (target - END_S).abs() > 1e-12 {
        return Err("fixture requires positive wall limit and target 0.65 s".into());
    }
    reject_path(&args[4])?;
    reject_path(&args[5])?;
    write_receipts()?;
    fs::write(&args[5], "first_invalid=true\nsynthetic_duplicate_time_s=6.20000000000000000e-1\nsynthetic_fixture=true\n").map_err(|e| e.to_string())?;
    let file = File::create(&args[4]).map_err(|e| e.to_string())?;
    let mut output = BufWriter::new(file);
    output.write_all(HEADER.as_bytes()).map_err(|e| e.to_string())?;
    for index in 0..BASE_POINTS {
        let time_s = index as f64 * STEP_S;
        emit_row(&mut output, time_s).map_err(|e| e.to_string())?;
        if index == DUPLICATE_INDEX {
            // Intentional equal-time row.  Native transport accepts it, while
            // the legacy operating checker must reject strict monotonicity.
            emit_row(&mut output, time_s).map_err(|e| e.to_string())?;
        }
    }
    output.flush().map_err(|e| e.to_string())?;
    Ok(())
}

fn main() -> Result<(), String> {
    run(&std::env::args().collect::<Vec<_>>())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixture_contract_is_exact() {
        assert_eq!(POINTS, 1_300_002);
        assert_eq!(DUPLICATE_INDEX as f64 * STEP_S, 0.62);
        assert_eq!((BASE_POINTS - 1) as f64 * STEP_S, END_S);
        assert_eq!(HEADER.matches("Variables:\n").count(), 1);
        assert_eq!(HEADER.matches("Binary:\n").count(), 1);
    }
    #[test]
    fn row_is_finite_and_current_is_in_phase_for_positive_power() {
        let mut bytes = Vec::new();
        emit_row(&mut bytes, 1.0 / 240.0).unwrap();
        let values: Vec<f64> = bytes.chunks_exact(8).map(|x| f64::from_le_bytes(x.try_into().unwrap())).collect();
        assert!(values.iter().all(|value| value.is_finite()));
        assert_eq!(values[4], BUS_V);
        assert!(((values[3].abs() / 2.0_f64.sqrt()) * LINE_RMS_V - BUS_V * BUS_V / LOAD_OHM).abs() < 1e-12);
        assert!(values[1] > 0.0 && values[3] < 0.0);
    }
}
