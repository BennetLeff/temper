#[path = "strict_order.rs"]
mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
};
fn main() {
    let mut result = String::from(
        "case,status,r_ohm,dut,fixture_pf,corner,cf_pf,afe_v,fda_v,end_us,max_step_ns,order\n",
    );
    for (name, r, dut, fixture, corner) in [
        ("matched100", 100, "RDUT hi low 100", 0, 0),
        ("matched5k", 5000, "RDUT hi low 5000", 0, 0),
        ("matched100k", 100000, "RDUT hi low 100000", 0, 0),
        ("open100p", 100, "RDUT hi low 1T", 100, 0),
        (
            "coil100p",
            100,
            "RDUT hi coil 0.5\nLDUT coil low 50u",
            100,
            0,
        ),
        ("open100p_low", 100, "RDUT hi low 1T", 100, -1),
        ("open100p_high", 100, "RDUT hi low 1T", 100, 1),
    ] {
        let cf = 100. * (1. + 0.05 * corner as f64);
        let afe = 12. * (1. + 0.05 * corner as f64);
        let fda = 5. * (1. + 0.05 * corner as f64);
        let original = fs::read_to_string("base.cir").unwrap();
        let mut s = original
            .split_once(".control")
            .unwrap()
            .0
            .to_string()
            .replace("RG source hi 100", &format!("RG source hi {r}"))
            .replace("RF low tia 100", &format!("RF low rf_end {r}"))
            .replace("CF low tia 100p", &format!("CF low cf_end {cf}p"))
            .replace("CDUT hi low 100n", dut)
            .replace("Vp vp 0 12", &format!("Vp vp 0 {afe}"))
            .replace("Vn vn 0 -12", &format!("Vn vn 0 -{afe}"))
            .replace("V5 v5 0 5", &format!("V5 v5 0 {fda}"));
        assert!(s.contains("Raint1 aom afbm 22") && s.contains("Cfba1 afbm aip 100p"));
        let (end, width, step) = if r == 100000 {
            (120, 60, 5)
        } else {
            (20, 10, 1)
        };
        s+=&format!("Lrf rf_end tia 100n\nLcf cf_end tia 5n\nChi hi 0 {}\nClo low 0 {}\nItest hi low DC 0 AC 0 PULSE(0 1u 1u 1n 1n {width}u 300u)\n",if fixture==0{1e-24}else{100e-12},if fixture==0{1e-24}else{100e-12});
        fs::write(format!("{name}-network.txt"), &s).unwrap();
        s+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nset filetype=ascii\nop\nwrite {name}_op.raw all\nlet kh=-i(v.x6b.x_h3.vh_h3)-(v(highbuf)-v(aip))/1000\nlet kl=-i(v.x7b.x_h3.vh_h3)-(v(lowbuf)-v(aim))/1000-(v(lowbuf)-v(bip))/1000\nlet kt=-i(v.x7a.x_h3.vh_h3)-(v(tia)-v(low))/{r}-(v(tia)-v(bim))/1000\nwrdata {name}_kcl.dat kh kl kt\nac lin 2 1000 100000\nlet a=v(aadc_p)-v(aadc_m)\nlet b=v(badc_p)-v(badc_m)\nlet ratio=b/a\nwrdata {name}_signal.dat real(ratio) imag(ratio) mag(a) mag(b) mag(v(source))\nalter Vdds ac=0\nalter Itest ac=1\nac lin 1 1 1\nwrdata {name}_step_target.dat real(v(tia)) real(v(highbuf)) real(v(lowbuf))\nalter Vdds ac=1\nalter Itest ac=0\ntran 1n {end}u 0 {step}n\nlet ihout=-i(v.x6b.x_h3.vh_h3)\nlet ilout=-i(v.x7b.x_h3.vh_h3)\nlet itout=-i(v.x7a.x_h3.vh_h3)\nwrdata {name}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m) i(Lrf) i(Lcf) ihout ilout itout\nquit\n.endc\n.end\n");
        let (order, s) = strict_order::find_order(&format!("init-{name}"), &s, 96).unwrap();
        fs::write(format!("{name}.cir"), s).unwrap();
        let f = fs::File::create(format!("{name}.log")).unwrap();
        let status = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{name}.cir")])
            .stdout(Stdio::from(f.try_clone().unwrap()))
            .stderr(Stdio::from(f))
            .status()
            .unwrap();
        let log = fs::read_to_string(format!("{name}.log")).unwrap();
        let good = status.success()
            && !log.contains("Error")
            && !log.contains("aborted")
            && strict_order::true_op(&format!("{name}_op.raw")).is_ok();
        let state = if good { "PASS" } else { "FAIL" };
        result+=&format!("{name},{state},{r},{dutlabel},{fixture},{corner},{cf},{afe},{fda},{end},{step},{order}\n",dutlabel=if name.starts_with("matched"){"matched"}else if name.starts_with("open"){"open"}else{"coil"});
        fs::write("run-results.csv", &result).unwrap();
        println!("{name} {state}");
    }
}
