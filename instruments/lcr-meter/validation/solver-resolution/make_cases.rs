use std::{fs, process::Command};
fn main() {
    let root = "models/";
    let base = fs::read_to_string("klu.cir").unwrap();
    let base = base.split(".control").next().unwrap().to_string();
    let cases = [
        ("100r_cap100n", 100., 0., "CDUT hi low 100n"),
        ("100r_cap500n", 100., 0., "CDUT hi low 500n"),
        ("100r_cap9u", 100., 0., "CDUT hi low 9u"),
        (
            "100r_coil50u",
            100.,
            0.,
            "RDUT hi coil 0.5\nLDUT coil low 50u",
        ),
        ("5k_resistor", 5000., 0., "RDUT hi low 5000"),
        ("100k_resistor", 100000., 5e-12, "RDUT hi low 100000"),
    ];
    for (name, r, cf, dut) in cases {
        let mut s=base.replace("TI RevB nominal full analog chain","RevB exact full chain; official models; real FDA bias and ADC RC loads").replace(".options reltol=0.001 method=gear", ".options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear\n.include offset-nodeset.inc").replace("Vdds dds0 0 DC 0 AC 1","Vdds dds0 0 DC 0.3 AC 1 SIN(0.3 0.3 50k)").replace("RG source hi 100",&format!("RG source hi {r}")).replace("RF low tia 100",&format!("RF low tia {r}")).replace("CF low tia 0.000000000000000000000001",&format!("CF low tia {}",if cf==0. {1e-24} else {cf})).replace("CDUT hi low 100n",dut)
 .replace("X6B hi highbuf highbuf vp vn OPA2810","X6B hi highbuf high_drv vp vn OPA2810\nVh high_drv highbuf 0")
 .replace("X7B low lowbuf lowbuf vp vn OPA2810","X7B low lowbuf low_drv vp vn OPA2810\nVl low_drv lowbuf 0")
 .replace("X7A 0 low tia vp vn OPA2810","X7A 0 low tia_drv vp vn OPA2810\nVt tia_drv tia 0");
        s+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset filetype=ascii\nop\nwrite {name}_op.raw all\nlet ihload=(v(highbuf)-v(aip))/1000\nlet ilload=(v(lowbuf)-v(aim))/1000+(v(lowbuf)-v(bip))/1000\nlet itload=(v(tia)-v(low))/{r}+(v(tia)-v(bim))/1000\nlet kh=i(vh)-ihload\nlet kl=i(vl)-ilload\nlet kt=i(vt)-itload\nprint v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aip) v(aim) v(bip) v(bim) v(aop) v(aom) v(bop) v(bom) i(vh) i(vl) i(vt) kh kl kt\nwrdata {name}_dc.dat v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aip) v(aim) v(bip) v(bim) v(aop) v(aom) v(bop) v(bom) i(vh) i(vl) i(vt) kh kl kt\nac dec 80 10 100Meg\nlet a=v(aadc_p)-v(aadc_m)\nlet b=v(badc_p)-v(badc_m)\nlet ratio=a/b\nwrdata {name}_ac.dat real(ratio) imag(ratio) mag(a) mag(b)\ntran 10n 120u 0 10n\nlet a=v(aadc_p)-v(aadc_m)\nlet b=v(badc_p)-v(badc_m)\nwrdata {name}_tran.dat v(dds0) v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m) a b\nquit\n.endc\n.end\n");
        s = s
            .replace(
                "X6B hi highbuf high_drv vp vn OPA2810\nVh high_drv highbuf 0",
                "X6B hi highbuf highbuf vp vn OPA2810",
            )
            .replace(
                "X7B low lowbuf low_drv vp vn OPA2810\nVl low_drv lowbuf 0",
                "X7B low lowbuf lowbuf vp vn OPA2810",
            )
            .replace(
                "X7A 0 low tia_drv vp vn OPA2810\nVt tia_drv tia 0",
                "X7A 0 low tia vp vn OPA2810",
            )
            .replace("i(vh)", "(-i(v.x6b.x_h3.vh_h3))")
            .replace("i(vl)", "(-i(v.x7b.x_h3.vh_h3))")
            .replace("i(vt)", "(-i(v.x7a.x_h3.vh_h3))");
        assert!(s.contains(root));
        fs::write(format!("{name}.cir"), s).unwrap();
        let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{name}.cir")])
            .output()
            .unwrap();
        let mut log = o.stdout;
        log.extend(o.stderr);
        fs::write(format!("{name}.log"), &log).unwrap();
        let txt = String::from_utf8_lossy(&log);
        assert!(
            !txt.contains("Error")
                && !txt.contains("aborted")
                && !txt.contains("timestep too small"),
            "{name} failed"
        );
        println!("{name} completed");
    }
}
