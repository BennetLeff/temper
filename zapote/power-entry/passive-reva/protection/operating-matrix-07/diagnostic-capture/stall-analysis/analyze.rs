use std::{env, fs::File, io::{BufRead, BufReader}};

const TINY: [f64; 4] = [1e-15, 1e-14, 1e-12, 1e-10];
const KEYS: [&str; 10] = [
    "v(xu.raw)", "v(xu.pwm_hold)", "v(xu.phase)", "v(xu.m1)", "v(xu.m2)",
    "v(xu.blank)", "v(xu.icomp_reset)", "v(xu.pcl_hold)", "v(icomp)", "v(pwm)",
];

#[derive(Clone)] struct Sample { t: f64, x: Vec<f64> }
struct Stats {
    rows: u64, intervals: u64, min_dt: f64, min_at: f64, min_prev: Sample, min_now: Sample,
    tiny: [u64; 4], tiny_phase: [u64; 4], tiny_margin_neg: [u64; 4], tiny_edges: [[u64; 10]; 4],
    tiny_crossings: [[u64; 2]; 4], ordinary_crossings: [u64; 2],
    ordinary_edges: [u64; 10], ordinary_edge_examples: Vec<(f64, f64, usize, f64)>,
    tiny_cross_examples: Vec<(f64, f64, usize, f64, f64)>, ordinary_cross_examples: Vec<(f64, f64, usize, f64, f64)>,
    min_margin: f64, min_margin_t: f64, margin_samples: u64,
    tiny_examples: Vec<(f64, f64, [f64; 10], [f64; 10], f64)>,
}
impl Stats {
    fn new() -> Self { Self { rows:0, intervals:0, min_dt:f64::INFINITY, min_at:0., min_prev:Sample{t:0.,x:vec![]}, min_now:Sample{t:0.,x:vec![]}, tiny:[0;4], tiny_phase:[0;4], tiny_margin_neg:[0;4], tiny_edges:[[0;10];4], tiny_crossings:[[0;2];4], ordinary_crossings:[0;2], ordinary_edges:[0;10], ordinary_edge_examples:Vec::new(), tiny_cross_examples:Vec::new(), ordinary_cross_examples:Vec::new(), min_margin:f64::INFINITY, min_margin_t:0., margin_samples:0, tiny_examples:Vec::new() } }
}
fn idx(header:&[String], key:&str)->Result<usize,String>{header.iter().position(|x|x==key).ok_or_else(||format!("missing required column {key}"))}
fn main()->Result<(),String>{
    let path=env::args().nth(1).ok_or("usage: analyze TRACE.tsv")?;
    let mut lines=BufReader::new(File::open(path).map_err(|e|e.to_string())?).lines();
    let header=lines.next().ok_or("missing header")?.map_err(|e|e.to_string())?;
    let hs=header.split_whitespace().map(str::to_owned).collect::<Vec<_>>();
    let time_idx=idx(&hs,"time")?;
    let mut inds=Vec::new(); for k in KEYS { inds.push(idx(&hs,k)?); }
    let icomp=idx(&hs,"v(icomp)")?; let phase=idx(&hs,"v(xu.phase)")?; let m2=idx(&hs,"v(xu.m2)")?;
    let mut st=Stats::new(); let mut prev:Option<Sample>=None;
    for (ln,line) in lines.enumerate(){
        let line=line.map_err(|e|e.to_string())?;
        let vals=line.split_whitespace().map(|s|s.parse::<f64>()).collect::<Result<Vec<_>,_>>().map_err(|_|format!("non-numeric row {}",ln+2))?;
        if vals.len()!=hs.len(){return Err(format!("row {} field count {} != header {}",ln+2,vals.len(),hs.len()))}
        if vals.iter().any(|x|!x.is_finite()){return Err(format!("non-finite row {}",ln+2))}
        let now=Sample{t:vals[time_idx],x:vals}; st.rows+=1;
        if let Some(old)=prev.take(){
            let dt=now.t-old.t; if !(dt>0.){return Err(format!("non-increasing time at row {}",ln+2))}
            st.intervals+=1; if dt<st.min_dt{st.min_dt=dt;st.min_at=now.t;st.min_prev=old.clone();st.min_now=now.clone()}
            let mut delta=[0.;10]; for j in 0..10{delta[j]=(now.x[inds[j]]-old.x[inds[j]]).abs()}
            let edge_lim=[1e-3,1e-3,1e-8,1e-3,1e-3,1e-3,1e-6,1e-3,1e-3,1e-3];
            let margin=0.72+now.x[m2]*1e6*(now.x[phase]-570e-9)-now.x[icomp];
            let crossing = |a:f64,b:f64| (a < 2.5) != (b < 2.5);
            let raw_cross = crossing(old.x[inds[0]],now.x[inds[0]]);
            let hold_cross = crossing(old.x[inds[1]],now.x[inds[1]]);
            for (k,&lim) in TINY.iter().enumerate(){
                if dt<=lim {
                    st.tiny[k]+=1;
                    if now.x[phase]>570e-9{st.tiny_phase[k]+=1}
                    if now.x[phase]>570e-9&&margin<0.{st.tiny_margin_neg[k]+=1}
                    for j in 0..10{if delta[j]>edge_lim[j]{st.tiny_edges[k][j]+=1}}
                    if raw_cross { st.tiny_crossings[k][0]+=1; if st.tiny_cross_examples.len()<20 { st.tiny_cross_examples.push((now.t,dt,0,old.x[inds[0]],now.x[inds[0]])); } }
                    if hold_cross { st.tiny_crossings[k][1]+=1; if st.tiny_cross_examples.len()<20 { st.tiny_cross_examples.push((now.t,dt,1,old.x[inds[1]],now.x[inds[1]])); } }
                    if k==0&&st.tiny_examples.len()<20{let mut a=[0.;10];let mut b=[0.;10];for j in 0..10{a[j]=old.x[inds[j]];b[j]=now.x[inds[j]]}st.tiny_examples.push((old.t,now.t,a,b,margin))}
                }
            }
            if dt>1e-10 {
                for j in 0..10{if delta[j]>edge_lim[j]{st.ordinary_edges[j]+=1;if st.ordinary_edge_examples.len()<20{st.ordinary_edge_examples.push((now.t,dt,j,delta[j]))}}}
                if raw_cross { st.ordinary_crossings[0]+=1; if st.ordinary_cross_examples.len()<20 { st.ordinary_cross_examples.push((now.t,dt,0,old.x[inds[0]],now.x[inds[0]])); } }
                if hold_cross { st.ordinary_crossings[1]+=1; if st.ordinary_cross_examples.len()<20 { st.ordinary_cross_examples.push((now.t,dt,1,old.x[inds[1]],now.x[inds[1]])); } }
            }
            let margin=0.72+now.x[m2]*1e6*(now.x[phase]-570e-9)-now.x[icomp];
            if now.x[phase]>570e-9{st.margin_samples+=1;if margin<st.min_margin{st.min_margin=margin;st.min_margin_t=now.t}}
            prev=Some(now)
        } else {prev=Some(now)}
    }
    if st.rows<2{return Err("fewer than two rows".into())}
    println!("rows={} intervals={} min_dt={:.17e} min_time={:.17e}",st.rows,st.intervals,st.min_dt,st.min_at);
    println!("phase_margin_samples={} min_margin={:.9e} at_time={:.17e} (margin=0.72+M2*1e6*(phase-570ns)-icomp, phase>570ns only)",st.margin_samples,st.min_margin,st.min_margin_t);
    println!("tiny_thresholds_s={:?}",TINY);println!("tiny_counts={:?}",st.tiny);println!("tiny_phase_gt_570ns={:?}",st.tiny_phase);println!("tiny_negative_margin={:?}",st.tiny_margin_neg);println!("tiny_edge_counts_by_threshold=[");for k in 0..4{println!("  {:?}",st.tiny_edges[k]);}println!("]");println!("tiny_crossings_raw_then_pwm_hold_by_threshold=[");for k in 0..4{println!("  {:?}",st.tiny_crossings[k]);}println!("]");println!("ordinary_edge_counts={:?}",st.ordinary_edges);println!("ordinary_crossings_raw_then_pwm_hold={:?}",st.ordinary_crossings);
    println!("min_interval_prev_time={:.17e}",st.min_prev.t);println!("min_interval_now_time={:.17e}",st.min_now.t);println!("min_interval_values (key prev -> now -> delta):");for j in 0..10{println!("  {}: {:.17e} -> {:.17e} (delta {:.9e})",KEYS[j],st.min_prev.x[inds[j]],st.min_now.x[inds[j]],(st.min_now.x[inds[j]]-st.min_prev.x[inds[j]]).abs())}
    let min_phase=st.min_now.x[phase];let min_margin=0.72+st.min_now.x[m2]*1e6*(min_phase-570e-9)-st.min_now.x[icomp];println!("min_interval_phase={:.17e} m2={:.17e} icomp={:.17e} branch_margin={:.9e}",min_phase,st.min_now.x[m2],st.min_now.x[icomp],min_margin);
    println!("tiny_examples_first_{}:",st.tiny_examples.len());for (a,b,p,n,m) in &st.tiny_examples{println!("  t={:.17e}->{:.17e} dt={:.3e} phase={:.9e}->{:.9e} raw={:.6e}->{:.6e} pwm_hold={:.6e}->{:.6e} blank={:.6e}->{:.6e} icomp={:.6e}->{:.6e} margin={:.6e}",a,b,b-a,p[2],n[2],p[0],n[0],p[1],n[1],p[5],n[5],p[8],n[8] ,m) }
    println!("ordinary_edge_examples_first_{}:",st.ordinary_edge_examples.len());for (t,dt,j,d) in &st.ordinary_edge_examples{println!("  t={:.17e} dt={:.3e} key={} delta={:.9e}",t,dt,KEYS[*j],d)}
    println!("tiny_crossing_examples_first_{}:",st.tiny_cross_examples.len());for (t,dt,j,a,b) in &st.tiny_cross_examples{println!("  t={:.17e} dt={:.3e} key={} value={:.9e}->{:.9e}",t,dt,KEYS[*j],a,b)}
    println!("ordinary_crossing_examples_first_{}:",st.ordinary_cross_examples.len());for (t,dt,j,a,b) in &st.ordinary_cross_examples{println!("  t={:.17e} dt={:.3e} key={} value={:.9e}->{:.9e}",t,dt,KEYS[*j],a,b)}
    Ok(())
}
