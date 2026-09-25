use std::{env, path::PathBuf, process};
use zapote_thermal::{run, Config};

fn main() {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() != 4 || args.iter().any(|a| a == "-h" || a == "--help") {
        eprintln!("usage: zapote-thermal-reference GMSH ELMERGRID ELMERSOLVER NEW_OUTPUT_DIR");
        process::exit(if args.iter().any(|a| a == "-h" || a == "--help") {
            0
        } else {
            2
        });
    }
    let geo = format!("{}/fixtures/bar.geo", env!("CARGO_MANIFEST_DIR"));
    let sif = format!("{}/fixtures/case.sif", env!("CARGO_MANIFEST_DIR"));
    let config = Config {
        gmsh: PathBuf::from(&args[0]),
        elmergrid: PathBuf::from(&args[1]),
        elmersolver: PathBuf::from(&args[2]),
        output_dir: PathBuf::from(&args[3]),
        bar_geo: PathBuf::from(geo),
        case_sif: PathBuf::from(sif),
        timeout: std::time::Duration::from_secs(300),
    };
    match run(&config) {
        Ok(report) => println!(
            "{}",
            serde_json::to_string_pretty(&report).unwrap_or_default()
        ),
        Err(error) => {
            eprintln!("thermal reference failed: {error:#}");
            process::exit(1);
        }
    }
}
