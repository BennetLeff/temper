//! Independent continuous-phase CCM and triangle-energy audit.
//!
//! Standalone `rustc`; no imports from the production model. Input is one TSV
//! row per case: id, line, frequency, gate_bias, Rds, Qg, Qgd, plateau,
//! lumped_external_R, intrinsic_R, transfer_charge, Eoss, followed by the eight
//! reported values (on_A, off_A, switch_rms_A, input_W, overlap_W, Eoss_W,
//! conduction_W, gate_W), then reported partial_W. Bus=400V, L=180uH, input=15A.
//! All values are SI. The CSV/JSON-to-TSV step is transport, not engineering.
use std::io::{self, BufRead};
use std::f64::consts::{PI, SQRT_2};

fn reference(x: &[f64]) -> Result<[f64; 9], String> {
    if x.len() != 11 || x.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err("expected eleven finite positive SI inputs".into());
    }
    let [line, f, gate, rds, qg, qgd, plateau, rext, rint, qt, eoss]: [f64; 11] =
        x.try_into().map_err(|_| "input count")?;
    if gate <= plateau { return Err("gate must exceed plateau".into()); }
    let bus = 400.0;
    let a = line * SQRT_2 / (180e-6 * f);
    let k = line * SQRT_2 / bus;
    // <sin^n(theta)> over [0,pi], n=1..5. Integrate the squared ripple
    // analytically; the production implementation samples switching ramps.
    let s1 = 2.0 / PI;
    let s2 = 0.5;
    let s3 = 4.0 / (3.0 * PI);
    let s4 = 3.0 / 8.0;
    let s5 = 16.0 / (15.0 * PI);
    let ripple_variance = a*a/12.0 * (s2 - 2.0*k*s3 + k*k*s4);
    let fundamental_sq = 225.0 - ripple_variance;
    if fundamental_sq <= 0.0 || k >= 1.0 { return Err("invalid boost operating point".into()); }
    let peak = (2.0 * fundamental_sq).sqrt();
    if peak < a/2.0 { return Err("continuous CCM condition violated".into()); }
    let mean_ripple = a * (s1 - k*s2);
    let on = peak*s1 - mean_ripple/2.0;
    let off = peak*s1 + mean_ripple/2.0;
    let rms_sq = peak*peak*(s2-k*s3)
        + a*a/12.0*(s2-3.0*k*s3+3.0*k*k*s4-k*k*k*s5);
    let source_current = 1.5_f64.min((gate-plateau)/(rext+rint));
    let sink_current = 2.0_f64.min(plateau/(rext+rint));
    let overlap = 0.5*bus*f*(qt+qgd)*(on/source_current+off/sink_current);
    let cap = eoss*f;
    let conduction = rms_sq*rds;
    let gate_loss = qg*gate*f;
    let values = [on, off, rms_sq.sqrt(), line*fundamental_sq.sqrt(), overlap,
        cap, conduction, gate_loss, overlap+cap+conduction+gate_loss];
    if values.iter().any(|v| !v.is_finite() || *v < 0.0) {
        return Err("non-finite reference result".into());
    }
    Ok(values)
}

fn audit_row(line: &str) -> Result<f64, String> {
    let columns: Vec<_> = line.split('\t').collect();
    if columns.len() != 21 { return Err(format!("expected 21 columns, got {}", columns.len())); }
    let numbers: Vec<f64> = columns[1..].iter().map(|s| s.parse::<f64>()
        .map_err(|_| format!("invalid numeric field {s}"))).collect::<Result<_,_>>()?;
    let expected = reference(&numbers[..11])?;
    let mut largest = 0.0_f64;
    for (index, (actual, expected)) in numbers[11..].iter().zip(expected).enumerate() {
        let scale = expected.abs().max(1e-12);
        if !actual.is_finite() || (actual-expected).abs() > 1e-7*scale {
            return Err(format!("{} field {index}: actual={actual}, reference={expected}", columns[0]));
        }
        largest = largest.max((actual-expected).abs()/scale);
    }
    Ok(largest)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut count = 0_usize;
    let mut max_error = 0.0_f64;
    for line in io::stdin().lock().lines() {
        let line = line?;
        max_error = max_error.max(audit_row(&line)?);
        count += 1;
    }
    if count == 0 { return Err("no cases supplied".into()); }
    println!("{{\"cases\":{count},\"max_relative_error\":{max_error:.16e},\"relative_tolerance\":1e-7,\"status\":\"pass\",\"scope\":\"independent conditional arithmetic; not physical qualification\"}}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn valid_row() -> String {
        let x = [120.0,129_107.39198577,10.0,0.05,120e-9,58e-9,6.2,10.0,3.3,10e-9,17.5e-6];
        let mut fields = vec!["control".to_owned()];
        fields.extend(x.into_iter().chain(reference(&x).unwrap()).map(|v| v.to_string()));
        fields.join("\t")
    }
    #[test]
    fn changed_report_value_and_nan_are_rejected_after_valid_control() {
        let row = valid_row();
        assert!(audit_row(&row).is_ok());
        for bad in ["0", "NaN", "inf"] {
            let mut cols: Vec<_> = row.split('\t').collect();
            cols[16] = bad;
            assert!(audit_row(&cols.join("\t")).is_err());
        }
    }
    #[test]
    fn asymmetric_gate_currents_use_distinct_voltage_differences() {
        let mut x = [120.0,129_107.39198577,10.0,0.05,120e-9,58e-9,6.2,10.0,3.3,10e-9,17.5e-6];
        let a = reference(&x).unwrap();
        x[6] = 3.8;
        let b = reference(&x).unwrap();
        // Plateau reflection swaps source/sink times but unequal event currents
        // mean total overlap must differ. A copied turn-on expression fails this.
        assert!((a[4]-b[4]).abs()>1.0);
    }
}
