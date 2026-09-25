use std::fs::File;
use std::io::{BufRead, BufReader, Write};
#[derive(Clone)] struct R { line: usize, t: f64, v: Vec<f64> }
fn main() -> Result<(), Box<dyn std::error::Error>> {
 let f=File::open("excerpt.tsv")?; let mut rs=Vec::new();
 for l in BufReader::new(f).lines() { let l=l?; if !l.starts_with("line=") {continue;} let mut it=l.splitn(2," raw="); let meta=it.next().unwrap(); let raw=match it.next(){Some(x)=>x,None=>continue}; let line=meta.strip_prefix("line=").unwrap().split_whitespace().next().unwrap().parse::<usize>()?; let a=raw.split_whitespace().map(|x|x.parse::<f64>()).collect::<Result<Vec<_>,_>>()?; if a.len()>=2 {rs.push(R{line,t:a[0],v:a[1..].to_vec()});}
 }
 let i=rs.windows(2).position(|w| w[1].t<=w[0].t).ok_or("no duplicate")?; let lo=i.saturating_sub(32); let hi=(i+33).min(rs.len()); let names=["acsrc","acn","iVac","load","vb","iL","vd","sw","gate","q","en","fault","vcomp","icomp"];
 let mut out=File::create("node-summary.txt")?; writeln!(out,"duplicate_previous_line={} duplicate_current_line={} previous_time={:.20e} current_time={:.20e}",rs[i].line,rs[i+1].line,rs[i].t,rs[i+1].t)?;
 writeln!(out,"local_window_records={} lines={}..{}",hi-lo,rs[lo].line,rs[hi-1].line)?;
 let dt:Vec<f64>=(lo+1..hi).map(|j|rs[j].t-rs[j-1].t).collect(); let minp=dt.iter().copied().filter(|x|*x>0.0).fold(f64::INFINITY,f64::min); let maxp=dt.iter().copied().fold(f64::NEG_INFINITY,f64::max); writeln!(out,"local_dt_min_positive={:.20e} local_dt_max={:.20e} local_dt_duplicate={:.20e}",minp,maxp,rs[i+1].t-rs[i].t)?;
 for (k,n) in names.iter().enumerate(){ let vals=rs[lo..hi].iter().map(|r|r.v[k]).collect::<Vec<_>>(); let mn=vals.iter().copied().fold(f64::INFINITY,f64::min); let mx=vals.iter().copied().fold(f64::NEG_INFINITY,f64::max); let d=rs[i+1].v[k]-rs[i].v[k]; writeln!(out,"node={} duplicate_delta={:.20e} local_min={:.20e} local_max={:.20e} local_span={:.20e}",n,d,mn,mx,mx-mn)?; }
 Ok(())
}
