//! Reproduce a bounded ADC load stress experiment, separate from full-chain validation.
use std::{fs, process::Command};

fn main() {
    for (tag, on_ns) in [("operating", 360.), ("stress", 860.)] {
        let mut deck = format!("Standalone THS4551 + bounded ADS9224R switched-load stress\n.include ../../sources/ti/models/ths4551.lib\n.options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=trap\nV5 vp 0 5\nVcm cm 0 2.048\nVfull full 0 4.096\nVin inp 0 SIN(0 1.8 100k)\nVsample sample 0 PULSE(0 1 {on_ns}n 0.2n 0.2n {}n 1u)\nBreset reset 0 V=1-V(sample)\n.model sw SW(Ron=0.01 Roff=1e12 Vt=0.5 Vh=0.01)\n",999.8-on_ns);
        for (p, rp, rm) in [
            ("reference", None, None),
            ("center", Some("cm"), Some("cm")),
            ("positive", Some("full"), Some("0")),
            ("negative", Some("0"), Some("full")),
            ("lowcm", Some("0"), Some("0")),
            ("highcm", Some("full"), Some("full")),
        ] {
            deck += &format!("R{p}i1 inp {p}ip 1k\nR{p}i2 0 {p}im 1k\nR{p}fb1 {p}om {p}fbm 22\nR{p}fb2 {p}op {p}fbp 22\nR{p}f1 {p}fbm {p}ip 1k\nR{p}f2 {p}fbp {p}im 1k\nC{p}f1 {p}fbm {p}ip 100p\nC{p}f2 {p}fbp {p}im 100p\nX{p} {p}ip {p}im {p}op {p}om cm vp 0 THS4551\nR{p}iso1 {p}fbp {p}ap 4.32\nR{p}iso2 {p}fbm {p}am 4.32\nC{p}flt1 {p}ap 0 330p\nC{p}flt2 {p}am 0 330p\nC{p}diff {p}ap {p}am 3.3n\nC{p}hold1 {p}ap 0 1p\nC{p}hold2 {p}am 0 1p\nR{p}sam1 {p}ap {p}rs1 120\nR{p}sam2 {p}am {p}rs2 120\nC{p}sam1 {p}sp 0 16p\nC{p}sam2 {p}sm 0 16p\n");
            if let (Some(rp), Some(rm)) = (rp, rm) {
                deck += &format!("S{p}sam1 {p}rs1 {p}sp sample 0 sw\nS{p}sam2 {p}rs2 {p}sm sample 0 sw\nS{p}rst1 {p}sp {rp} reset 0 sw\nS{p}rst2 {p}sm {rm} reset 0 sw\n");
            } else {
                deck += &format!("R{p}link1 {p}rs1 {p}sp 0.01\nR{p}link2 {p}rs2 {p}sm 0.01\n");
            }
        }
        deck += ".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\ntran 0.5n 15u 0 0.5n\nlet reference=v(referencesp)-v(referencesm)\n";
        for p in ["center", "positive", "negative", "lowcm", "highcm"] {
            deck += &format!("let {p}=v({p}sp)-v({p}sm)-reference\nlet {p}cm=(v({p}sp)+v({p}sm)-v(referencesp)-v(referencesm))/2\n");
        }
        deck += &format!("wrdata {tag}.dat v(sample) reference center positive negative lowcm highcm centercm positivecm negativecm lowcmcm highcmcm v(centerap) v(centeram) v(positiveap) v(positiveam) v(negativeap) v(negativeam) v(lowcmap) v(lowcmam) v(highcmap) v(highcmam) v(referenceap) v(referenceam)\nquit\n.endc\n.end\n");
        fs::write(format!("{tag}.cir"), deck).unwrap();
        let data_path = format!("{tag}.dat");
        if fs::exists(&data_path).unwrap() {
            fs::remove_file(&data_path).unwrap();
        }
        let out = Command::new(std::env::var("NGSPICE").unwrap_or("ngspice".into()))
            .args(["-b", &format!("{tag}.cir")])
            .output()
            .unwrap();
        let mut log = out.stdout;
        log.extend(out.stderr);
        fs::write(format!("{tag}.log"), &log).unwrap();
        assert!(
            out.status.success()
                && !String::from_utf8_lossy(&log).contains("Error:")
                && !String::from_utf8_lossy(&log)
                    .to_lowercase()
                    .contains("aborted"),
            "inspect {tag}.log"
        );
        println!("{tag} completed");
    }
}
