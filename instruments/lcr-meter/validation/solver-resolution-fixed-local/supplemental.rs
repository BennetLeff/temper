#[path = "strict_order.rs"]
mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut results = String::from("case,source_case,kind,end_us,max_step_ns,order,status\n");
    for (name, base, kind) in [
        ("uncompensated5k", "matched5k", "pulse"),
        ("sine100", "matched100", "sine"),
        ("sine5k", "matched5k", "sine"),
        ("sine100k", "matched100k", "sine"),
        ("cm5k", "matched5k", "cm"),
    ] {
        let original = fs::read_to_string(format!("{base}.cir"))?;
        let mut deck = original.replace(base, name);
        if kind == "pulse" {
            deck = deck.replace("CF low cf_end 100p", "CF low cf_end 1e-24");
        } else {
            deck = deck
                .lines()
                .map(|l| {
                    if l.starts_with("Itest ") {
                        "Itest hi low DC 0 AC 0"
                    } else {
                        l
                    }
                })
                .collect::<Vec<_>>()
                .join("\n")
                + "\n";
            if kind == "sine" {
                deck = deck.replace(
                    "Vdds dds0 0 DC 0.3 AC 1",
                    "Vdds dds0 0 DC 0.3 AC 1 SIN(0.3 0.3 100k)",
                );
            } else {
                deck = deck.replace(
                    "Vcm cm 0 2.048",
                    "Vcm cm 0 DC 2.048 PULSE(2.048 2.058 1u 1n 1n 10u 50u)",
                );
            }
            // Source-on sine: 12 periods observed at actual 0.3 V peak DDS amplitude.
            deck = deck
                .lines()
                .map(|l| {
                    if l.starts_with("tran ") {
                        if kind == "sine" {
                            "tran 1n 120u 0 5n"
                        } else {
                            "tran 1n 20u 0 1n"
                        }
                    } else {
                        l
                    }
                })
                .collect::<Vec<_>>()
                .join("\n")
                + "\n";
        }
        let (order, deck) = strict_order::find_order(&format!("init-{name}"), &deck, 96)?;
        fs::write(format!("{name}.cir"), deck)?;
        let f = fs::File::create(format!("{name}.log"))?;
        let status = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{name}.cir")])
            .stdout(Stdio::from(f.try_clone()?))
            .stderr(Stdio::from(f))
            .status()?;
        let log = fs::read_to_string(format!("{name}.log"))?;
        let ok = status.success()
            && !log.contains("Error")
            && !log.contains("aborted")
            && strict_order::true_op(&format!("{name}_op.raw")).is_ok();
        let state = if ok { "PASS" } else { "FAIL" };
        results += &format!(
            "{name},{base},{kind},{},{},{order},{state}\n",
            if kind == "sine" { 120 } else { 20 },
            if kind == "sine" { 5 } else { 1 }
        );
        fs::write("supplemental-results.csv", &results)?;
        println!("{name} {state}");
    }
    Ok(())
}
