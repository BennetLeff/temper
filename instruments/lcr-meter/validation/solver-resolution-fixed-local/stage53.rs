#[path = "strict_order.rs"]
mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base = fs::read_to_string("matched100-network.txt")?;
    let mut manifest = String::from("case,hz,end_s,max_step_s,order,status\n");
    for (name, dut, f, end, step) in [
        ("stage100n", "CDUT hi low 100n", 50000., 240e-6, 10e-9),
        ("stage500n", "CDUT hi low 500n", 50000., 600e-6, 10e-9),
        ("stage9u", "CDUT hi low 9u", 1000., 0.012, 250e-9),
        (
            "stagecoil",
            "RDUT hi coil 0.5\nLDUT coil low 50u",
            50000.,
            240e-6,
            10e-9,
        ),
    ] {
        let mut deck = base.replace("RDUT hi low 100", dut).replace(
            "Vdds dds0 0 DC 0.3 AC 1",
            &format!("Vdds dds0 0 DC 0.3 AC 1 SIN(0.3 0.3 {f})"),
        );
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
        deck+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nset filetype=ascii\nop\nwrite {name}_op.raw all\nlet kh=-i(v.x6b.x_h3.vh_h3)-(v(highbuf)-v(aip))/1000\nlet kl=-i(v.x7b.x_h3.vh_h3)-(v(lowbuf)-v(aim))/1000-(v(lowbuf)-v(bip))/1000\nlet kt=-i(v.x7a.x_h3.vh_h3)-(v(tia)-v(low))/100-(v(tia)-v(bim))/1000\nwrdata {name}_kcl.dat kh kl kt\nac lin 1 {f} {f}\nlet a=v(aadc_p)-v(aadc_m)\nlet b=v(badc_p)-v(badc_m)\nlet ratio=b/a\nwrdata {name}_signal.dat real(ratio) imag(ratio) mag(a) mag(b) mag(v(source))\ntran 1n {end} 0 {step}\nlet ihout=-i(v.x6b.x_h3.vh_h3)\nlet ilout=-i(v.x7b.x_h3.vh_h3)\nlet itout=-i(v.x7a.x_h3.vh_h3)\nwrdata {name}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m) i(Lrf) i(Lcf) ihout ilout itout\nquit\n.endc\n.end\n");
        let (order, deck) = strict_order::find_order(&format!("init-{name}"), &deck, 96)?;
        fs::write(format!("{name}.cir"), deck)?;
        let file = fs::File::create(format!("{name}.log"))?;
        let status = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{name}.cir")])
            .stdout(Stdio::from(file.try_clone()?))
            .stderr(Stdio::from(file))
            .status()?;
        let log = fs::read_to_string(format!("{name}.log"))?;
        let ok = status.success()
            && !log.contains("Error")
            && !log.contains("aborted")
            && strict_order::true_op(&format!("{name}_op.raw")).is_ok();
        let state = if ok { "PASS" } else { "FAIL" };
        manifest += &format!("{name},{f},{end},{step},{order},{state}\n");
        fs::write("stage53-cases.csv", &manifest)?;
        println!("{name} {state}");
    }
    Ok(())
}
