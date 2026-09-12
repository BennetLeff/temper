use std::{env, fs, process};

fn main() {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() != 3 || args.iter().any(|a| a == "-h" || a == "--help") {
        eprintln!("usage: zapote-thermal SOURCE_MANIFEST NATIVE_EXPORT SENSOR_CONTRACT");
        process::exit(if args.iter().any(|a| a == "-h" || a == "--help") {
            0
        } else {
            2
        });
    }
    let read = |path: &str| {
        fs::read(path).unwrap_or_else(|e| {
            eprintln!("cannot read {path}: {e}");
            process::exit(2)
        })
    };
    let report = zapote_harness::thermal_sense::parse_and_run(
        &read(&args[0]),
        &read(&args[1]),
        &read(&args[2]),
    )
    .unwrap_or_else(|e| {
        eprintln!("invalid thermal input: {e}");
        process::exit(2)
    });
    println!(
        "{}",
        serde_json::to_string_pretty(&report).expect("report serializes")
    );
    if report.status != zapote_core::Status::Pass {
        process::exit(1);
    }
}
