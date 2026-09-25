use std::{env, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    let mut args = env::args_os();
    let _program = args.next();
    let Some(trace) = args.next() else {
        eprintln!("usage: rail-trace TRACE.tsv [SOURCE_BASE]");
        return ExitCode::from(2);
    };
    let trace = PathBuf::from(trace);
    let base = args
        .next()
        .map(PathBuf::from)
        .or_else(|| trace.parent().and_then(|p| p.parent()).map(PathBuf::from));
    let Some(base) = base else {
        eprintln!("cannot infer source base; pass SOURCE_BASE");
        return ExitCode::from(2);
    };
    match a5_rail_contract::validate_trace(&trace, &base) {
        Ok(samples) => {
            println!(
                "PASS: validated {} trace samples through {:.6} s",
                samples.len(),
                samples.last().unwrap().time_s
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("FAIL: {error}");
            ExitCode::from(1)
        }
    }
}
