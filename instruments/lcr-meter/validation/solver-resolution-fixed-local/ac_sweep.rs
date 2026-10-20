#[path = "strict_order.rs"]
mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    for name in ["matched100", "matched5k", "matched100k"] {
        let original = fs::read_to_string(format!("{name}.cir"))?;
        let pre = original.split_once(".control").ok_or("control missing")?.0;
        let stem = format!("ac-{name}");
        let s=format!("{pre}.control\nset klu\noptran 1 0 0 0 0 0\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nset filetype=ascii\nop\nwrite {stem}_op.raw all\nac dec 10 1000 100000\nlet a=v(aadc_p)-v(aadc_m)\nlet b=v(badc_p)-v(badc_m)\nlet ratio=b/a\nwrdata {stem}.dat real(ratio) imag(ratio) mag(a) mag(b) mag(v(source))\nquit\n.endc\n.end\n");
        fs::write(format!("{stem}.cir"), s)?;
        let f = fs::File::create(format!("{stem}.log"))?;
        let status = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{stem}.cir")])
            .stdout(Stdio::from(f.try_clone()?))
            .stderr(Stdio::from(f))
            .status()?;
        if !status.success() {
            return Err("simulator exit".into());
        }
        strict_order::true_op(&format!("{stem}_op.raw"))?;
        println!("{stem} complete");
    }
    Ok(())
}
