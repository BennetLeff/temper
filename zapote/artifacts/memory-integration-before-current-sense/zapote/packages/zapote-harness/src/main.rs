use serde_json::Value;
use std::{
    env, fs,
    io::{self, Read},
};
use zapote_harness::{parse_input, run};

fn main() {
    let mut input_path = None;
    let mut unit_input_path = None;
    let mut memory_input_path = None;
    let mut output_path = None;
    let mut no_telemetry = false;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--input" => input_path = args.next(),
            "--unit-input" => unit_input_path = args.next(),
            "--memory-input" => memory_input_path = args.next(),
            "--output" => output_path = args.next(),
            "--no-telemetry" => no_telemetry = true,
            "--help" | "-h" => {
                println!("zapote-rtd [--input FILE | --unit-input FILE | --memory-input FILE] [--output FILE] [--no-telemetry]");
                return;
            }
            other => {
                eprintln!("unknown argument: {other}");
                std::process::exit(2);
            }
        }
    }
    if let Some(path) = memory_input_path {
        if input_path.is_some() || unit_input_path.is_some() {
            eprintln!("--memory-input cannot be combined with --input or --unit-input");
            std::process::exit(2);
        }
        let bytes = if path == "-" {
            let mut bytes = Vec::new();
            io::stdin().read_to_end(&mut bytes).unwrap_or_else(|e| {
                eprintln!("cannot read memory input: {e}");
                std::process::exit(2);
            });
            bytes
        } else {
            fs::read(path).unwrap_or_else(|e| {
                eprintln!("cannot read memory input: {e}");
                std::process::exit(2);
            })
        };
        let response = match serde_json::from_slice::<Value>(&bytes) {
            Ok(input) => match zapote_harness::memory::dispatch(input.clone()) {
                Ok(output) => output,
                Err(error) => zapote_harness::memory::error_response(Some(&input), &error),
            },
            Err(error) => zapote_harness::memory::error_response(None, &anyhow::anyhow!(error)),
        };
        let encoded = serde_json::to_vec_pretty(&response).expect("response serializes");
        if let Some(path) = output_path {
            fs::write(path, &encoded).unwrap_or_else(|e| {
                eprintln!("cannot write output: {e}");
                std::process::exit(2);
            });
        } else {
            println!("{}", String::from_utf8(encoded).expect("JSON is UTF-8"));
        }
        if response["status"] != "pass" {
            std::process::exit(1);
        }
        return;
    }
    if let Some(path) = unit_input_path {
        let bytes = fs::read(path).unwrap_or_else(|e| {
            eprintln!("cannot read unit input: {e}");
            std::process::exit(2);
        });
        let input: zapote_core::unit::UnitInput =
            serde_json::from_slice(&bytes).unwrap_or_else(|e| {
                eprintln!("invalid zapote.rtd.unit-input.v1 input: {e}");
                std::process::exit(2);
            });
        let report = zapote_harness::run_unit(&input);
        let encoded = serde_json::to_vec_pretty(&report).expect("report serializes");
        if let Some(path) = output_path {
            fs::write(path, &encoded).unwrap_or_else(|e| {
                eprintln!("cannot write output: {e}");
                std::process::exit(2);
            });
        } else {
            println!("{}", String::from_utf8(encoded).expect("JSON is UTF-8"));
        }
        if report.status != zapote_core::Status::Pass {
            std::process::exit(1);
        }
        return;
    }
    let bytes = match input_path {
        Some(path) => fs::read(path).unwrap_or_else(|e| {
            eprintln!("cannot read input: {e}");
            std::process::exit(2);
        }),
        None => {
            let mut bytes = Vec::new();
            io::stdin().read_to_end(&mut bytes).unwrap_or_else(|e| {
                eprintln!("cannot read stdin: {e}");
                std::process::exit(2);
            });
            bytes
        }
    };
    let input = parse_input(&bytes).unwrap_or_else(|e| {
        eprintln!("invalid zapote-rtd.v1 input: {e}");
        std::process::exit(2);
    });
    let report = run(&input, no_telemetry);
    let encoded = serde_json::to_vec_pretty(&report).expect("report serializes");
    if let Some(path) = output_path {
        fs::write(path, &encoded).unwrap_or_else(|e| {
            eprintln!("cannot write output: {e}");
            std::process::exit(2);
        });
    } else {
        println!("{}", String::from_utf8(encoded).expect("JSON is UTF-8"));
    }
    if report.status != zapote_core::Status::Pass {
        std::process::exit(1);
    }
}
