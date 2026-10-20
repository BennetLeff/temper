use std::{fs,process::Command};
fn run(name:&str, circuit:&str) {
 fs::write(format!("{name}.cir"),circuit).unwrap();
 let o=Command::new("/opt/homebrew/bin/ngspice").args(["-b",&format!("{name}.cir")]).output().unwrap();
 let mut log=o.stdout;log.extend(o.stderr);fs::write(format!("{name}.log"),&log).unwrap();
 assert!(o.status.success(),"{name} failed");
 assert!(!String::from_utf8_lossy(&log).contains("Error"),"{name} error, inspect log");
}
fn full(r:f64,c:f64,dut:&str,looptest:bool)->String {
 let mut s=format!("TI RevB nominal full analog chain\n.include ../../sources/ti/models/opa2810_a.lib\n.include ../../sources/ti/models/opa810_a.lib\n.include ../../sources/ti/models/ths4551.lib\n.options reltol=0.0001\nVp vp 0 12\nVn vn 0 -12\nV5 v5 0 5\nVcm cm 0 2.048\nVdds dds0 0 DC 0 AC {}\nRdds dds0 dds 200\nR30 dds lp1 330\nC34 lp1 0 1n\nR31 lp1 lp2 330\nC35 lp2 0 1n\nC36 lp2 acin 1u\nR32 acin 0 100k\nX5 acin srcfb excite vp vn OPA810\nR33 excite srcfb 5k\nR34 srcfb 0 1k\nX6A excite source source vp vn OPA2810\nRG source hi {r}\n{dut}\nRF low tia {r}\nCF low tia {c}\nX6B hi highbuf highbuf vp vn OPA2810\nX7B low lowbuf lowbuf vp vn OPA2810\n",if looptest{0}else{1});
 if looptest{s.push_str("Vtest inv low DC 0 AC 1\nX7A 0 inv tia vp vn OPA2810\n");}else{s.push_str("X7A 0 low tia vp vn OPA2810\n");}
 for (p,positive,negative) in [("a","highbuf","lowbuf"),("b","lowbuf","tia")] {
 s.push_str(&format!("R{p}i1 {positive} {p}ip 1k\nR{p}i2 {negative} {p}im 1k\nR{p}f1 {p}fbm {p}ip 1k\nR{p}f2 {p}fbp {p}im 1k\nR{p}int1 {p}om {p}fbm 3.3\nR{p}int2 {p}op {p}fbp 3.3\nX{p} {p}ip {p}im {p}op {p}om cm v5 0 THS4551\nR{p}iso1 {p}op {p}adc_p 4.02\nR{p}iso2 {p}om {p}adc_m 4.02\nC{p}flt1 {p}adc_p 0 330p\nC{p}flt2 {p}adc_m 0 330p\nC{p}diff {p}adc_p {p}adc_m 3.3n\nC{p}adc1 {p}adc_p 0 16p\nC{p}adc2 {p}adc_m 0 16p\n"));
 }
 s
}
fn main(){
 let cases: [(&str,f64,f64,&str);6]=[("cap100n",100.,0.,"CDUT hi low 100n"),("cap500n",100.,0.,"CDUT hi low 500n"),("cap9u",100.,0.,"CDUT hi low 9u"),("coil50u",100.,0.,"RDUT hi coil 0.5\nLDUT coil low 50u"),("mid5k",5000.,0.,"RDUT hi low 5000"),("high100k",100000.,5e-12,"RDUT hi low 100000")];
 for (name,r,c,dut) in cases {
 for lt in [false,true] {
  let nm=if lt{format!("loop_{name}")}else{format!("transfer_{name}")};
  let mut s=full(r,c.max(1e-24),dut,lt);
  let v=if lt{"let loopgain = -v(low)/v(inv)\nwrdata OUTPUT.dat real(loopgain) imag(loopgain)"}else{"let a = v(aadc_p)-v(aadc_m)\nlet b = v(badc_p)-v(badc_m)\nlet ratio = a/b\nwrdata OUTPUT.dat real(ratio) imag(ratio) mag(a) mag(b) mag(v(source))"};
  s.push_str(&format!(".control\nset wr_singlescale\nset wr_vecnames\nac dec 120 10 1G\n{}\nquit\n.endc\n.end\n",v.replace("OUTPUT",&nm)));
  run(&nm,&s);
 }
 }
 let src="Source RC path only, 200ohm nominal DDS source and ideal gain6 readout\nV1 in0 0 DC 0 AC 1 PULSE(0 0.3 1m 10n 10n 2 4)\nRout in0 in 200\nR30 in lp1 330\nC34 lp1 0 1n\nR31 lp1 lp2 330\nC35 lp2 0 1n\nC36 lp2 acin 1u\nR32 acin 0 100k\nEread out 0 acin 0 6\n.control\nset wr_singlescale\nset wr_vecnames\nac dec 100 0.1 100Meg\nwrdata source_ac.dat real(v(out)) imag(v(out))\ntran 0.0001 1.1\nwrdata source_settle.dat v(out)\nquit\n.endc\n.end\n";
 run("source",src);
}
