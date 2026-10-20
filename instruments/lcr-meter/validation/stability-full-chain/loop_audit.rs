//! Full-chain external loop audit using Tian et al. Eq.30 bilateral double injection.
//! Vendor models remain unmodified; ngspice KLU addresses SPARSE numerical failure.
use std::{fs,process::Command,ops::{Add,Sub,Mul,Div}};
#[derive(Clone,Copy,Debug)]struct C{r:f64,i:f64}
impl C{fn n(r:f64,i:f64)->Self{Self{r,i}}fn abs(self)->f64{self.r.hypot(self.i)}fn phase(self)->f64{self.i.atan2(self.r)}}
impl Add for C{type Output=Self;fn add(self,b:Self)->Self{Self::n(self.r+b.r,self.i+b.i)}}
impl Sub for C{type Output=Self;fn sub(self,b:Self)->Self{Self::n(self.r-b.r,self.i-b.i)}}
impl Mul for C{type Output=Self;fn mul(self,b:Self)->Self{Self::n(self.r*b.r-self.i*b.i,self.r*b.i+self.i*b.r)}}
impl Div for C{type Output=Self;fn div(self,b:Self)->Self{let q=b.r*b.r+b.i*b.i;Self::n((self.r*b.r+self.i*b.i)/q,(self.i*b.r-self.r*b.i)/q)}}
#[derive(Clone)]struct Case{name:String,r:f64,cf:f64,dut:String,stray:f64,rail:f64,five:f64}
fn circuit(c:&Case,lp:&str)->String{
 let mut s=format!("Full exact coupled RevB external loop: {} / {lp}\n.include ../../sources/ti/models/opa2810_a.lib\n.include ../../sources/ti/models/opa810_a.lib\n.include ../../sources/ti/models/ths4551.lib\n.options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear rshunt=1e30\nVp vp 0 {}\nVn vn 0 -{}\nV5 v5 0 {}\nVcm cm 0 2.048\nVdds dds0 0 DC 0.3 AC 0\nRdds dds0 dds 200\nR30 dds lp1 330\nC34 lp1 0 1n\nR31 lp1 lp2 330\nC35 lp2 0 1n\nC36 lp2 acin 1u\nR32 acin 0 100k\nR33 excite srcfb 5k\nR34 srcfb 0 1k\nRG source hi {}\n{}\nRF low tia {}\nCF low tia {}\nCstraylo low 0 {}\nCstrayhi hi 0 {}\n",c.name,c.rail,c.rail,c.five,c.r,c.dut,c.r,c.cf.max(1e-24),c.stray.max(1e-24),c.stray.max(1e-24));
 for(name,positive,negative,out,model,tag)in[("5","acin","srcfb","excite","OPA810","source"),("6A","excite","source","source","OPA2810","drive"),("6B","hi","highbuf","highbuf","OPA2810","high"),("7B","low","lowbuf","lowbuf","OPA2810","low"),("7A","0","low","tia","OPA2810","tia")] {
 let o=if tag==lp{"probe_f"}else{out};s+=&format!("X{name} {positive} {negative} {o} vp vn {model}\n");
 if tag==lp{s+=&format!("Vinj {out} probe_f DC 0 AC 1\nIinj 0 {out} DC 0 AC 0\n");}
 }
 for(p,positive,negative)in[("a","highbuf","lowbuf"),("b","lowbuf","tia")] {
 s+=&format!("R{p}i1 {positive} {p}ip 1k\nR{p}i2 {negative} {p}im 1k\nR{p}f1 {p}fbm {p}ip 1k\nR{p}f2 {p}fbp {p}im 1k\nR{p}int1 {p}om {p}fbm 3.3\nR{p}int2 {p}op {p}fbp 3.3\n");
 if lp==format!("fda_{p}"){s+=&format!("X{p} probe_fp probe_fm {p}op {p}om cm v5 0 THS4551\nVinj drive 0 DC 0 AC 1\nEinjp {p}ip probe_fp drive 0 0.5\nEinjm {p}im probe_fm drive 0 -0.5\nIinj 0 {p}ip DC 0 AC 0\nIinjm {p}im 0 DC 0 AC 0\n");}else{s+=&format!("X{p} {p}ip {p}im {p}op {p}om cm v5 0 THS4551\n");}
 s+=&format!("R{p}iso1 {p}op {p}adc_p 4.02\nR{p}iso2 {p}om {p}adc_m 4.02\nC{p}flt1 {p}adc_p 0 330p\nC{p}flt2 {p}adc_m 0 330p\nC{p}diff {p}adc_p {p}adc_m 3.3n\nC{p}adc1 {p}adc_p 0 16p\nC{p}adc2 {p}adc_m 0 16p\n");
 }
 let(f,v)=match lp{"source"=>("-i(vinj)".to_string(),"v(excite)".to_string()),"drive"=>("-i(vinj)".into(),"v(source)".into()),"high"=>("-i(vinj)".into(),"v(highbuf)".into()),"low"=>("-i(vinj)".into(),"v(lowbuf)".into()),"tia"=>("-i(vinj)".into(),"v(tia)".into()),"fda_a"=>("-(i(einjp)-i(einjm))/2".into(),"v(aip)-v(aim)".into()),"fda_b"=>("-(i(einjp)-i(einjm))/2".into(),"v(bip)-v(bim)".into()),_=>panic!("loop")};
 let name=format!("{}_{}",c.name,lp);
 s+=&format!(".include seed-nodeset.inc\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nprint v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aop) v(aom) v(bop) v(bom)\nac dec 120 1 1G\nlet b={f}\nlet d={v}\nwrdata {name}_voltage.dat real(b) imag(b) real(d) imag(d)\nalter Vinj ac=0\nalter Iinj ac=1\n");if lp.starts_with("fda_"){s+="alter Iinjm ac=1\n";}
 s+=&format!("ac dec 120 1 1G\nlet a={f}\nlet c={v}\nwrdata {name}_current.dat real(a) imag(a) real(c) imag(c)\nquit\n.endc\n.end\n");s
}
fn data(p:&str)->Vec<Vec<f64>>{fs::read_to_string(p).unwrap().lines().skip(1).map(|l|l.split_whitespace().map(|x|{let n:f64=x.parse().unwrap();assert!(n.is_finite(),"nonfinite {p}");n}).collect()).collect()}
fn analyze(name:&str)->String{
 let v=data(&format!("{name}_voltage.dat"));let i=data(&format!("{name}_current.dat"));assert_eq!(v.len(),1081);assert_eq!(v.len(),i.len());
 let mut points=vec![];let mut prev=0.;let mut first=true;let mut csv="frequency_hz,return_real,return_imag,gain_db,unwrapped_phase_deg,return_difference_abs\n".to_string();
 for(v,i)in v.iter().zip(i.iter()){assert_eq!(v[0],i[0]);let a=C::n(i[1],i[2]);let b=C::n(v[1],v[2]);let c=C::n(i[3],i[4]);let d=C::n(v[3],v[4]);let n=C::n(2.,0.)*(a*d-b*c)-a+d;let t=n/(C::n(1.,0.)-n);assert!(t.abs().is_finite());let mut phase=t.phase()*180./std::f64::consts::PI;if !first{while phase-prev>180.{phase-=360.;}while phase-prev < -180.{phase+=360.;}}first=false;prev=phase;let db=20.*t.abs().log10();let delta=(C::n(1.,0.)+t).abs();points.push((v[0],db,phase,delta));csv+=&format!("{:.12e},{:.12e},{:.12e},{db:.9},{phase:.9},{delta:.12e}\n",v[0],t.r,t.i);}
 fs::write(format!("{name}_return.csv"),csv).unwrap();
 let mut crossings=vec![];for p in points.windows(2){let(a,b)=(p[0],p[1]);if (a.1>=0.&&b.1<0.)||(a.1<0.&&b.1>=0.){let k=a.1/(a.1-b.1);let freq=(a.0.ln()+k*(b.0/a.0).ln()).exp();let phase=a.2+k*(b.2-a.2);crossings.push(format!("{:.4} MHz / {:.2}° ({})",freq/1e6,180.+phase,if b.1<a.1{"down"}else{"up"}));}}
 let min=points.iter().min_by(|a,b|a.3.total_cmp(&b.3)).unwrap();format!("| {name} | {} | {:.5} at {:.4} MHz |\n",crossings.join("; "),min.3,min.0/1e6)
}
fn main(){
 let mode=std::env::args().nth(1).unwrap_or("nominal".into());let mut cases=vec![];
 for(tag,r,cf)in[("r100",100.,0.),("r5k",5000.,0.),("r100k",100000.,5e-12)]{cases.push(Case{name:format!("{tag}_matched"),r,cf,dut:format!("RDUT hi low {r}"),stray:0.,rail:12.,five:5.});if mode=="grid"{for(n,d)in[("short","RDUT hi low 0.01"),("open","RDUT hi low 1e12"),("cap100n","CDUT hi low 100n"),("cap500n","CDUT hi low 500n"),("cap9u","CDUT hi low 9u"),("coil50u","RDUT hi coil 0.5\nLDUT coil low 50u")] {cases.push(Case{name:format!("{tag}_{n}"),r,cf,dut:d.into(),stray:0.,rail:12.,five:5.});}}}
 if mode=="comp"{cases.clear();for cf in [2.2e-12,4.7e-12,10e-12,22e-12]{for stray in [0.,10e-12,30e-12,100e-12]{cases.push(Case{name:format!("comp_cf{:.1}_stray{:.0}",cf*1e12,stray*1e12),r:5000.,cf,dut:"RDUT hi low 5000".into(),stray,rail:12.,five:5.});}}}
 let mut report="# Full-chain external loop results\n\nTian bilateral double injection, unmodified typical vendor models. All crossings are reported; modes and limitations require accompanying methodology.\n\n| Case / loop | Unity crossings / phase margin | Minimum |1+T| |\n|---|---|---|\n".to_string();
 for c in cases{let loops:Vec<&str>=if mode=="tia"||mode=="comp"{vec!["tia"]}else if c.name.ends_with("matched"){vec!["source","drive","high","low","tia","fda_a","fda_b"]}else{vec!["tia"]};for lp in loops{let name=format!("{}_{}",c.name,lp);fs::write(format!("{name}.cir"),if mode=="comp"{circuit(&c,lp).replace("reltol=1e-5 abstol=1e-12 vntol=1e-7","reltol=0.001").replace("Vdds dds0 0 DC 0.3","Vdds dds0 0 DC 0").replace(".include seed-nodeset.inc\n", "")}else{circuit(&c,lp)}).unwrap();for suffix in ["voltage","current"]{let _=fs::remove_file(format!("{name}_{suffix}.dat"));}let out=Command::new("/opt/homebrew/bin/ngspice").args(["-b",&format!("{name}.cir")]).output().unwrap();let mut log=out.stdout;log.extend(out.stderr);fs::write(format!("{name}.log"),&log).unwrap();assert!(!String::from_utf8_lossy(&log).contains("Error:"),"{name}: simulator error, inspect log");assert!(out.status.success(),"{name} failed");let row=analyze(&name);print!("{row}");report+=&row;fs::write("loop-results.md",&report).unwrap();}}
}
