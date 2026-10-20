mod strict_order;
use std::{fs, process::Command};
fn main() {
    let base = fs::read_to_string("newton-5k-selected.cir").unwrap();
    let base = base
        .split_once(".control")
        .unwrap()
        .0
        .replace("SIN(0.3 0.3 50k)", "");
    for cf in [0, 10] {
        let n = format!("final_5k_cf{cf}");
        let s = base.replace(
            "CF low tia 10p",
            &format!("CF low tia {}", if cf == 0 { 1e-24 } else { 10e-12 }),
        );
        let s=format!("{s}Itest hi low PULSE(0 1u 1u 1n 1n 5u 12u)\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nset filetype=ascii\nop\nwrite {n}_op.raw all\ntran 1n 10u 0 1n\nwrdata {n}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m)\nquit\n.endc\n.end\n");
        let (_, s) = strict_order::find_order(&format!("init-{n}"), &s, 48).unwrap();
        fs::write(format!("{n}.cir"), s).unwrap();
        let o = Command::new("/opt/homebrew/bin/ngspice")
            .args(["-b", &format!("{n}.cir")])
            .output()
            .unwrap();
        fs::write(format!("{n}.log"), [o.stdout, o.stderr].concat()).unwrap();
        strict_order::true_op(&format!("{n}_op.raw")).unwrap();
        println!("{n} PASS");
    }
}
