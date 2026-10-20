use std::{fs,f64::consts::PI};
fn data(p:&str)->Vec<Vec<f64>>{fs::read_to_string(p).unwrap().lines().skip(1).map(|l|l.split_whitespace().map(|x|x.parse::<f64>().unwrap()).collect()).filter(|v: &Vec<f64>|!v.is_empty()).collect()}
fn near(d:&[Vec<f64>],f:f64)->&Vec<f64>{d.iter().min_by(|a,b|(a[0]-f).abs().partial_cmp(&(b[0]-f).abs()).unwrap()).unwrap()}
fn mul(a:(f64,f64),b:(f64,f64))->(f64,f64){(a.0*b.0-a.1*b.1,a.0*b.1+a.1*b.0)}
fn main(){
 let mut s=String::from("# Nominal simulations — generated numerical results\n\nThese results describe specified SPICE cases, not hardware measurements. AFE cases use incremental ideal-FDA loading with zero DC common-mode bias; full-chain model fails convergence.\n\n## Passive source path\n\n200Ω DDS Thevenin resistance; 330Ω/1nF twice; 1µF/100kΩ coupling; ideal readout gain 6.\n\n| Actual frequency (Hz) | Gain V/V | Phase ° |\n|---:|---:|---:|\n");
 let source=data("source_ac.dat");
 for f in [100.,1000.,35000.,50000.,60000.,100000.,24000000.] {let x=near(&source,f);s+=&format!("| {:.2} | {:.6} | {:.3} |\n",x[0],x[1].hypot(x[2]),x[2].atan2(x[1])*180./PI);}
 let settle=data("source_settle.dat");s+="\n0→0.3V DDS DC step at 1ms; output values below are elapsed since that step.\n\n";
 for t in [0.2,0.5,1.0]{let x=near(&settle,t+0.001);s+=&format!("- {:.3}s: {:.6}mV residual.\n",x[0]-0.001,x[1]*1000.);}
 s+="\n## AFE complex ratio sanity\n\nZest=(RF || CF)×(HIGH_BUF−LOW_BUF)/(LOW_BUF−TIA_OUT). Errors relative to the nominal DUT at the actual sweep frequency. These omit coupled FDA DC bias and finite-bandwidth input loading.\n\n| Case | f Hz | Re Z Ω | Im Z Ω | Complex relative error % |\n|---|---:|---:|---:|---:|\n";
 for (case,r,cf) in [("cap100n",100.,0.),("cap500n",100.,0.),("cap9u",100.,0.),("coil50u",100.,0.),("mid5k",5000.,0.),("high100k",100000.,5e-12)]{
 let d=data(&format!("transfer_{case}.dat"));
 for f in if case=="cap9u"{vec![1000.]}else{vec![35000.,60000.,100000.]}{
 let x=near(&d,f);let w=2.*PI*x[0];let k=w*r*cf;let z=mul((x[1],x[2]),(r/(1.+k*k),-r*k/(1.+k*k)));
 let target=match case{"cap100n"=>(0.,-1./(w*100e-9)),"cap500n"=>(0.,-1./(w*500e-9)),"cap9u"=>(0.,-1./(w*9e-6)),"coil50u"=>(0.5,w*50e-6),_ => (r,0.)};
 let err=(z.0-target.0).hypot(z.1-target.1)/target.0.hypot(target.1)*100.;s+=&format!("| {case} | {:.2} | {:.6} | {:.6} | {:.5} |\n",x[0],z.0,z.1,err);
 }
 }
 s+="\n## TIA return-ratio diagnostic\n\nSeries AC voltage at TIA inverting input, DC zero; T=−V(DUT_LO)/V(IN−). Other loops closed. Figures are nominal single-loop diagnostics with approximate incremental FDA loading and zero FDA-induced DC bias. They are **not full-board phase-margin guarantees**.\n\n| Case | Crossing MHz | Nominal phase margin ° |\n|---|---:|---:|\n";
 for case in ["cap100n","cap500n","cap9u","coil50u","mid5k","high100k"]{
 let d=data(&format!("loop_{case}.dat"));let mut crossings=0;
 for pair in d.windows(2){let a=&pair[0];let b=&pair[1];let ma=a[1].hypot(a[2]);let mb=b[1].hypot(b[2]);if ma>=1. && mb<1.{crossings+=1;let k=ma.ln()/(ma.ln()-mb.ln());let f=(a[0].ln()+k*(b[0]/a[0]).ln()).exp();let phase=a[2].atan2(a[1])*(1.-k)+b[2].atan2(b[1])*k;s+=&format!("| {case} | {:.4} | {:.2} |\n",f/1e6,180.+phase*180./PI);}}
 assert!(crossings>0,"missing crossing {case}");
 }
 s+="\n## Standalone FDA\n\nOfficial THS4551 model at 5V, VOCM 2.048V, 1k input and 1003.3Ω total feedback per side,4.02Ω output isolation,330pF toground and 3.3nF differential,16pF static ADC input eachside. Ideal zero-ohm input source; ADC sampling switches omitted.\n\n";
 let fda=data("fda_ac.dat");let low=fda[0][1].hypot(fda[0][2]);let peak=fda.iter().max_by(|a,b|a[1].hypot(a[2]).partial_cmp(&b[1].hypot(b[2])).unwrap()).unwrap();let bw=fda.iter().find(|x|x[1].hypot(x[2])<low/2f64.sqrt()).unwrap();
 s+=&format!("- Low-frequency differential gain: {low:.7} V/V.\n- Maximum ACgain: {:.7}V/V at {:.2}Hz.\n- First sweep point below −3dB: {:.3}MHz.\n",peak[1].hypot(peak[2]),peak[0],bw[0]/1e6);
 let step=data("fda_step.dat");let baseline=near(&step,0.9e-6)[2];let finalv=step.last().unwrap()[2];let amp=finalv-baseline;let max=step.iter().filter(|x|x[0]>1e-6).map(|x|x[2]).fold(f64::NEG_INFINITY,f64::max);let lastbad=step.iter().filter(|x|x[0]>1.01e-6 && ((x[2]-finalv)/amp).abs()>0.001).map(|x|x[0]).fold(1.01e-6,f64::max);
 s+=&format!("- 10mV input step: output increment {:.6}mV; overshoot {:.4}%; last >0.1% error {:.2}ns after end of 10 ns input edge (1ns requested timestep).\n",amp*1000.,(max-finalv)/amp*100.,(lastbad-1.01e-6)*1e9);
 fs::write("results.md",s).unwrap();
 let mut svg=String::from("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"900\" height=\"440\" viewBox=\"0 0 900 440\"><rect width=\"900\" height=\"440\" fill=\"white\"/><g font-family=\"sans-serif\" fill=\"#172b4d\"><text x=\"65\" y=\"28\" font-size=\"19\">Source and standalone ADC-driver nominal AC response</text><text x=\"65\" y=\"50\" font-size=\"12\">SPICE models; normalized gain. Excludes coupled FDA bias and ADC switching.</text>");
 for db in [0,-10,-20,-30,-40]{let y=80.-db as f64*7.;svg+=&format!("<path d=\"M65 {y} H850\" stroke=\"#ddd\"/><text x=\"20\" y=\"{}\" font-size=\"12\">{db}dB</text>",y+4.);}
 for log in 2..=7{let x=65.+(log as f64-2.)*157.;svg+=&format!("<path d=\"M{x} 80 V360\" stroke=\"#ddd\"/><text x=\"{}\" y=\"382\" font-size=\"12\">10^{log}Hz</text>",x-15.);}
 for (d,norm,color) in [(&source,6.,"#007f87"),(&fda,low,"#b75214")]{let pts=d.iter().filter(|v|v[0]>=100.&&v[0]<=1e7).map(|v|{let x=65.+(v[0].log10()-2.)*157.;let db=(20.*(v[1].hypot(v[2])/norm).log10()).clamp(-40.,1.);format!("{x:.2},{:.2}",80.-db*7.)}).collect::<Vec<_>>().join(" ");svg+=&format!("<polyline points=\"{pts}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/>");}
 svg+="<text x=\"65\" y=\"418\" fill=\"#007f87\">Source passive network / gain 6</text><text x=\"410\" y=\"418\" fill=\"#b75214\">Standalone THS4551 + ADC RC load</text></g></svg>";fs::write("ac-response.svg",svg).unwrap();
}
