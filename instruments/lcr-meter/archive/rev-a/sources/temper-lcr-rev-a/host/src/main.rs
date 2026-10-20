use std::collections::BTreeMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;

use serde::de::DeserializeOwned;
use temper_lcr::{correct, fit, range_bounds, Calibration, Result, Setup, Sweep};

const HELP: &str = "temper-lcr — revision A prototype bench instrument

list
capture --unit UNIT --fixture FIXTURE --range r20 --start 35000 --stop 60000
        --points 51 --out CAPTURE.json [--averages 4] [--settling 15] [--serial SERIAL]
calibrate --open OPEN.json --a A.json --ra 10 --b B.json --rb 40 --out CAL.json
convert --cal CAL.json --raw DUT.json --out DUT.csv

Capture open, load A, load B, and DUT with identical settings and the same fixture.
Standards are measured resistance in ohms; their HF parasitics remain an uncertainty.
Range is an OPERATOR ASSERTION: this PCB cannot read the physical range jumper.
Only connect isolated, fully discharged components. Neither DUT terminal is ground.
No ADC clipping detector, guaranteed ESR floor, USB isolation or milliohm mode.
1kHz r20 acquisition is experimental pending bench qualification.
Output files are never overwritten. No custom MCU firmware is required.
";

struct Args {
    values: BTreeMap<String, String>,
}
impl Args {
    fn new(args: impl Iterator<Item = String>) -> Result<Self> {
        let mut it = args;
        let mut values = BTreeMap::new();
        while let Some(key) = it.next() {
            if !key.starts_with("--") {
                return Err(format!("expected --option, got {key}"));
            }
            let value = it
                .next()
                .ok_or_else(|| format!("missing value for {key}"))?;
            if value.starts_with("--") || values.insert(key.clone(), value).is_some() {
                return Err(format!("missing value or duplicate option {key}"));
            }
        }
        Ok(Self { values })
    }
    fn required(&mut self, key: &str) -> Result<String> {
        self.values
            .remove(key)
            .ok_or_else(|| format!("missing {key}"))
    }
    fn default(&mut self, key: &str, default: &str) -> String {
        self.values.remove(key).unwrap_or_else(|| default.into())
    }
    fn finish(self) -> Result<()> {
        if self.values.is_empty() {
            Ok(())
        } else {
            Err(format!(
                "unknown options: {:?}",
                self.values.keys().collect::<Vec<_>>()
            ))
        }
    }
}
fn number<T: std::str::FromStr>(s: &str) -> Result<T> {
    s.parse().map_err(|_| format!("invalid number {s}"))
}
fn load<T: DeserializeOwned>(path: &str) -> Result<T> {
    serde_json::from_str(&fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?)
        .map_err(|e| format!("{path}: {e}"))
}
fn save(path: &str, bytes: &[u8]) -> Result<()> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| format!("{path}: {e}"))?;
    file.write_all(bytes)
        .and_then(|()| file.sync_all())
        .map_err(|e| format!("{path}: {e}"))
}
fn json(path: &str, value: &impl serde::Serialize) -> Result<()> {
    save(
        path,
        &serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?,
    )
}

fn run() -> Result<()> {
    let mut iter = env::args().skip(1);
    let command = iter.next().unwrap_or_else(|| "help".into());
    let mut args = Args::new(iter)?;
    match command.as_str() {
        "help" | "--help" | "-h" => {
            args.finish()?;
            print!("{HELP}");
        }
        "list" => {
            args.finish()?;
            #[cfg(feature = "usb")]
            {
                let devices = temper_lcr::instrument::Usb::list()?;
                if devices.is_empty() {
                    println!("No MCP2221A HID interfaces found.");
                }
                for d in devices {
                    println!("{d}");
                }
            }
            #[cfg(not(feature = "usb"))]
            {
                return Err("rebuild with the default usb feature".into());
            }
        }
        "capture" => {
            let setup = Setup {
                board_revision: "A".into(),
                unit: args.required("--unit")?,
                fixture: args.required("--fixture")?,
                range: args.required("--range")?,
                clock_hz: 16_000_000,
                excitation_range: 4,
                pga: 1,
                settling_cycles: number(&args.default("--settling", "15"))?,
                averages: number(&args.default("--averages", "4"))?,
                dft_sign: "AD5933-real-minus-i-imag".into(),
            };
            let start = number(&args.required("--start")?)?;
            let stop = number(&args.required("--stop")?)?;
            let count = number(&args.required("--points")?)?;
            let output = args.required("--out")?;
            let serial = args.values.remove("--serial");
            args.finish()?;
            setup.validate()?;
            temper_lcr::instrument::grid(&setup, start, stop, count)?;
            if std::path::Path::new(&output).exists() {
                return Err(format!("output already exists: {output}"));
            }
            eprintln!(
                "Physical jumper must match {}; fixture={}; unit={}",
                setup.range, setup.fixture, setup.unit
            );
            #[cfg(feature = "usb")]
            {
                let usb = temper_lcr::instrument::Usb::open(serial.as_deref())?;
                let sweep =
                    temper_lcr::instrument::Mcp::new(usb).capture(setup, start, stop, count)?;
                json(&output, &sweep)?;
                eprintln!("Saved {} points to {output}", sweep.points.len());
            }
            #[cfg(not(feature = "usb"))]
            {
                let _ = (serial, setup);
                return Err("capture requires the default usb feature".into());
            }
        }
        "calibrate" => {
            let open: Sweep = load(&args.required("--open")?)?;
            let a: Sweep = load(&args.required("--a")?)?;
            let b: Sweep = load(&args.required("--b")?)?;
            let ra = number(&args.required("--ra")?)?;
            let rb = number(&args.required("--rb")?)?;
            let output = args.required("--out")?;
            args.finish()?;
            let cal = fit(&open, &a, ra, &b, rb)?;
            json(&output, &cal)?;
            eprintln!("Saved {} calibration points to {output}", cal.points.len());
        }
        "convert" => {
            let cal: Calibration = load(&args.required("--cal")?)?;
            let raw: Sweep = load(&args.required("--raw")?)?;
            let output = args.required("--out")?;
            args.finish()?;
            let z = correct(&cal, &raw)?;
            let (min, max, _) = range_bounds(&raw.setup.range)?;
            let mut csv=String::from("frequency_hz,R_ohm,X_ohm,magnitude_ohm,phase_deg,series_L_H,series_C_F,Q,dissipation_factor,status\n");
            for (p, z) in raw.points.iter().zip(z) {
                let omega = 2.0 * std::f64::consts::PI * p.frequency_hz;
                let l = if z.im > 0.0 {
                    format!("{:.12e}", z.im / omega)
                } else {
                    String::new()
                };
                let c = if z.im < 0.0 {
                    format!("{:.12e}", -1.0 / (omega * z.im))
                } else {
                    String::new()
                };
                let q = if z.re > 0.0 {
                    format!("{:.9}", z.im.abs() / z.re)
                } else {
                    String::new()
                };
                let d = if z.re >= 0.0 && z.im != 0.0 {
                    format!("{:.9}", z.re / z.im.abs())
                } else {
                    String::new()
                };
                let mut flags = vec!["prototype_unqualified"];
                if z.abs() < min || z.abs() > max {
                    flags.push("outside_range");
                }
                if z.re < 0.0 {
                    flags.push("negative_R_check_calibration");
                }
                if p.frequency_hz < 10_000.0 {
                    flags.push("low_frequency_experimental");
                }
                csv.push_str(&format!(
                    "{:.9},{:.12e},{:.12e},{:.12e},{:.9},{l},{c},{q},{d},{}\n",
                    p.frequency_hz,
                    z.re,
                    z.im,
                    z.abs(),
                    z.im.atan2(z.re).to_degrees(),
                    flags.join("|")
                ));
            }
            save(&output, csv.as_bytes())?;
            eprintln!("Saved {output}. R is series resistance; an ESR accuracy floor has not been established.");
        }
        _ => return Err(format!("unknown command {command}\n{HELP}")),
    }
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
