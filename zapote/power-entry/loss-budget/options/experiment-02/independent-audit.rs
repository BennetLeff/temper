//! Independent continuous-phase CCM and asymmetric triangle-energy audit.
//! Driver caps are 5 A in both directions for experiment 02 candidate cases.
//!
//! Standalone `rustc`; no imports from the production model. Input is one TSV
//! row per case: index, device, driver_profile, device_source_sha256, line, frequency, gate_bias, Rds, Qg, Qgd, plateau,
//! external_R_on, external_R_off, intrinsic_R, transfer_charge, Eoss, followed by the eight
//! reported values (on_A, off_A, switch_rms_A, input_W, overlap_W, Eoss_W,
//! conduction_W, gate_W), then reported partial_W. Bus=400V, L=180uH, input=15A.
//! All values are SI. The CSV/JSON-to-TSV step is transport, not engineering.
use std::collections::HashSet;
use std::io::{self, BufRead};
use std::f64::consts::{PI, SQRT_2};

fn reference(x: &[f64]) -> Result<[f64; 9], String> {
    if x.len() != 12 || x.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err("expected twelve finite positive SI inputs".into());
    }
    let [line, f, gate, rds, qg, qgd, plateau, ron, roff, rint, qt, eoss]: [f64; 12] =
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
    let source_current = 5.0_f64.min((gate-plateau)/(ron+rint));
    let sink_current = 5.0_f64.min(plateau/(roff+rint));
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

const DEVICES: [(&str, &str, f64, f64, f64, f64, f64, f64); 2] = [
    ("STW65N65DM2AG", "6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322", 120e-9, 58e-9, 6.2, 3.3, 17.5e-6, 0.050),
    ("IPW65R045C7", "7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a", 93e-9, 30e-9, 5.4, 0.85, 11.7e-6, 0.045),
];
const PROFILES: [(&str, f64, f64); 3] = [
    ("full-assist", 1.04 * 5.0 / (1.04 + 5.0), 0.6),
    ("no-assist", 5.0, 0.6),
    ("dc-max", 8.5, 1.1),
];
const LINES: [f64; 3] = [108.0, 120.0, 132.0];
const GATES: [f64; 3] = [11.4, 12.0, 12.6];
const EXTERNAL: [f64; 3] = [2.2, 4.7, 10.0];
const QGD_MULTIPLIERS: [f64; 3] = [0.5, 1.0, 1.5];
const TRANSFER: [f64; 3] = [5e-9, 10e-9, 20e-9];
const RDS_MULTIPLIERS: [f64; 2] = [1.0, 2.0];
const FREQUENCY: f64 = 129107.39198576905;

fn close(actual: f64, expected: f64) -> bool {
    (actual - expected).abs() <= expected.abs().max(1e-12) * 1e-9
}

fn canonical_inputs(index: usize) -> Result<(String, String, String, [f64; 12]), String> {
    let mut i = 0;
    for &(device, source, qg, qgd, plateau, rint, eoss, rds) in &DEVICES {
        for &line in &LINES { for &gate in &GATES { for &external in &EXTERNAL {
            for &(profile, source_r, sink_r) in &PROFILES { for &qgd_mult in &QGD_MULTIPLIERS {
                for &transfer in &TRANSFER { for &rds_mult in &RDS_MULTIPLIERS {
                    if i == index {
                        return Ok((device.into(), profile.into(), source.into(), [
                            line, FREQUENCY, gate, rds * rds_mult, qg, qgd * qgd_mult,
                            plateau, external + source_r, external + sink_r, rint, transfer, eoss,
                        ]));
                    }
                    i += 1;
                }}
            }}
        }} }
    }
    Err(format!("index {index} is outside canonical 2916-case grid"))
}

fn audit_row(line: &str) -> Result<(usize, f64), String> {
    let columns: Vec<_> = line.split('\t').collect();
    if columns.len() != 25 { return Err(format!("expected 25 columns, got {}", columns.len())); }
    let index = columns[0].parse::<usize>().map_err(|_| "invalid index".to_owned())?;
    let (device, profile, source, expected_inputs) = canonical_inputs(index)?;
    if columns[1] != device || columns[2] != profile || columns[3] != source {
        return Err(format!("index {index} has non-canonical identity"));
    }
    let numbers: Vec<f64> = columns[4..].iter().map(|s| s.parse::<f64>()
        .map_err(|_| format!("invalid numeric field {s}"))).collect::<Result<_,_>>()?;
    let expected = reference(&numbers[..12])?;
    for (actual, canonical) in numbers[..12].iter().zip(expected_inputs) {
        if !actual.is_finite() || !close(*actual, canonical) {
            return Err(format!("index {index} is off canonical grid: {actual} vs {canonical}"));
        }
    }
    let mut largest = 0.0_f64;
    for (field_index, (actual, expected)) in numbers[12..].iter().zip(expected).enumerate() {
        let scale = expected.abs().max(1e-12);
        if !actual.is_finite() || (actual-expected).abs() > 1e-7*scale {
            return Err(format!("row {index} field {field_index}: actual={actual}, reference={expected}"));
        }
        largest = largest.max((actual-expected).abs()/scale);
    }
    Ok((index, largest))
}

fn audit_lines<I>(lines: I) -> Result<(usize, f64), String>
where
    I: IntoIterator<Item = String>,
{
    let mut count = 0_usize;
    let mut max_error = 0.0_f64;
    let mut indices = HashSet::new();
    for line in lines {
        let (index, error) = audit_row(&line)?;
        if !indices.insert(index) {
            return Err(format!("duplicate canonical index {index}"));
        }
        max_error = max_error.max(error);
        count += 1;
    }
    if count != 2916 || indices.len() != 2916 {
        return Err(format!("expected exactly 2916 unique canonical cases, got {count}"));
    }
    Ok((count, max_error))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (count, max_error) = audit_lines(io::stdin().lock().lines().collect::<Result<Vec<_>, _>>()?)?;
    println!("{{\"cases\":{count},\"max_relative_error\":{max_error:.16e},\"relative_tolerance\":1e-7,\"status\":\"pass\",\"scope\":\"independent conditional arithmetic; not physical qualification\"}}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn row_for(index: usize) -> String {
        let (device, profile, source, x) = canonical_inputs(index).unwrap();
        let mut fields = vec![index.to_string(), device, profile, source];
        fields.extend(x.into_iter().chain(reference(&x).unwrap()).map(|v| v.to_string()));
        fields.join("\t")
    }
    fn valid_row() -> String { row_for(0) }
    #[test]
    fn changed_report_value_and_nan_are_rejected_after_valid_control() {
        let row = valid_row();
        assert!(audit_row(&row).is_ok());
        for bad in ["0", "NaN", "inf"] {
            let mut cols: Vec<_> = row.split('\t').collect();
            cols[17] = bad;
            assert!(audit_row(&cols.join("\t")).is_err());
        }
    }
    #[test]
    fn asymmetric_gate_currents_use_distinct_voltage_differences() {
        let mut x = canonical_inputs(0).unwrap().3;
        x[2] = 10.0;
        x[7] = 10.0;
        x[8] = 4.0;
        let a = reference(&x).unwrap();
        x[6] = x[2] - x[6];
        let b = reference(&x).unwrap();
        // Plateau reflection swaps source/sink times but unequal event currents
        // mean total overlap must differ. A copied turn-on expression fails this.
        assert!((a[4]-b[4]).abs()>1.0);
    }
    #[test]
    fn exchanging_on_and_off_paths_rejects_the_unchanged_energy() {
        let mut x = canonical_inputs(0).unwrap().3;
        x[7] = 1.0;
        x[8] = 20.0;
        let baseline = reference(&x).unwrap();
        x.swap(7, 8);
        let swapped = reference(&x).unwrap();
        assert!((baseline[4] - swapped[4]).abs() > 1.0);
    }

    #[test]
    fn identity_and_canonical_grid_mutations_fail_closed() {
        let row = valid_row();
        let mut fields: Vec<_> = row.split('\t').collect();
        fields[1] = "IPW65R045C7";
        assert!(audit_row(&fields.join("\t")).is_err());
        let mut fields: Vec<_> = row.split('\t').collect();
        fields[0] = "2916";
        assert!(audit_row(&fields.join("\t")).is_err());
        let mut fields: Vec<_> = row.split('\t').collect();
        fields[8] = "3.2";
        assert!(audit_row(&fields.join("\t")).is_err());
    }

    #[test]
    fn full_grid_and_population_mutations_fail_closed() {
        let mut rows: Vec<_> = (0..2916).map(row_for).collect();
        assert_eq!(audit_lines(rows.clone()).unwrap().0, 2916);
        rows[2915] = rows[0].clone();
        assert!(audit_lines(rows).is_err());
        let rows: Vec<_> = (0..2915).map(row_for).collect();
        assert!(audit_lines(rows).is_err());
        let mut rows: Vec<_> = (0..2916).map(row_for).collect();
        let duplicate = row_for(2914);
        let mut fields: Vec<_> = duplicate.split('\t').collect();
        fields[0] = "2915";
        rows[2915] = fields.join("\t");
        assert!(audit_lines(rows).is_err());
    }
}
