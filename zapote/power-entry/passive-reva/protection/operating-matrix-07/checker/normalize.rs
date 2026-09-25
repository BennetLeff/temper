//! Stream the actual floating-input SPICE trace into the operating checker.
//! No verdicts or summary metrics here: operating_point_checker.rs owns them.
use std::{
    env,
    io::{self, BufRead, Write},
    process::ExitCode,
};

const SOURCE: [&str; 13] = [
    "time",
    "v(acsrc)",
    "v(acn)",
    "i(Vac)",
    "v(load)",
    "v(vb)",
    "i(Lboost)",
    "v(vd)",
    "v(sw)",
    "v(gate)",
    "v(q)",
    "v(en)",
    "v(fault)",
];
const HEADER: &str =
    "time_s v_ac_v i_ac_a v_load_v i_load_a v_b_v i_l_a v_d_v v_ds_v v_gs_v armed on";

fn normalize<R: BufRead, W: Write>(
    mut input: R,
    mut output: W,
    resistance: f64,
) -> Result<(), String> {
    if !resistance.is_finite() || resistance <= 0.0 {
        return Err("load resistance must be positive and finite".into());
    }
    let mut line = String::new();
    input.read_line(&mut line).map_err(|e| e.to_string())?;
    let columns: Vec<_> = line.split_whitespace().map(str::to_string).collect();
    let mut indices = [0usize; 13];
    for (i, key) in SOURCE.iter().enumerate() {
        let found: Vec<_> = columns
            .iter()
            .enumerate()
            .filter(|(_, s)| s == key)
            .map(|(i, _)| i)
            .collect();
        if found.len() != 1 {
            return Err(format!("expected exactly one {key} column"));
        }
        indices[i] = found[0];
    }
    writeln!(output, "{HEADER}").map_err(|e| e.to_string())?;
    let mut count = 0usize;
    loop {
        line.clear();
        if input.read_line(&mut line).map_err(|e| e.to_string())? == 0 {
            break;
        }
        let row = line
            .split_whitespace()
            .map(str::parse::<f64>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| "invalid trace number")?;
        if row.len() != columns.len() || row.iter().any(|x| !x.is_finite()) {
            return Err(format!("malformed/nonfinite source row {}", count + 2));
        }
        let x = indices.map(|i| row[i]);
        // Vchannel fixes channel_source at HOT0, so VDS=sw and VGS=gate.
        // on is local enable, never instantaneous PWM gate state.
        let v = [
            x[0],
            x[1] - x[2],
            -x[3],
            x[4],
            x[4] / resistance,
            x[5],
            x[6],
            x[7],
            x[8],
            x[9],
            if x[10] > 2.5 { 1.0 } else { 0.0 },
            if x[11] > 2.5 { 1.0 } else { 0.0 },
        ];
        for (i, value) in v.iter().enumerate() {
            if i > 0 {
                write!(output, " ").map_err(|e| e.to_string())?;
            }
            write!(output, "{value:.17e}").map_err(|e| e.to_string())?;
        }
        writeln!(output).map_err(|e| e.to_string())?;
        count += 1;
    }
    if count < 2 {
        return Err("incomplete source trace".into());
    }
    output.flush().map_err(|e| e.to_string())
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args().collect();
    let result = if args.len() != 2 {
        Err("usage: normalize RLOAD_OHM < raw.tsv | operating_point_checker --end-s T".into())
    } else {
        args[1]
            .parse::<f64>()
            .map_err(|_| "invalid resistance".into())
            .and_then(|r| {
                normalize(
                    io::stdin().lock(),
                    io::BufWriter::new(io::stdout().lock()),
                    r,
                )
            })
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("REJECTED normalizer: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn floating_ac_and_enabled_pwm_low_are_mapped_correctly() {
        let input = SOURCE.join("   ")+"\n0 20 140 2 380 390 3 391 392 0 5 5 0\n0.0000001 20 140 2 380 390 3 391 392 15 5 5 0\n";
        let mut output = Vec::new();
        normalize(io::Cursor::new(input), &mut output, 190.).unwrap();
        let text = String::from_utf8(output).unwrap();
        assert_eq!(text.lines().next().unwrap(), HEADER);
        for line in text.lines().skip(1) {
            let x: Vec<f64> = line
                .split_whitespace()
                .map(|v| v.parse().unwrap())
                .collect();
            assert_eq!(x.len(), 12);
            assert_eq!(x[1], -120.);
            assert_eq!(x[2], -2.);
            assert_eq!(x[4], 2.);
            assert_eq!(x[10], 1.);
            assert_eq!(x[11], 1.);
        }
    }
    #[test]
    fn missing_or_duplicate_columns_reject() {
        for input in ["time v(acsrc)\n".to_string(), SOURCE.join(" ") + " v(q)\n"] {
            assert!(normalize(io::Cursor::new(input), Vec::new(), 190.).is_err());
        }
    }
}
