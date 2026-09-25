//! Exact pin-membership audit for the compiled ESP-only connectivity fixture.
//! This proves netlist joins only; it does not prove electrical timing/safety.
use std::collections::{BTreeMap, BTreeSet};
use std::fs;

#[derive(Debug)]
enum S { A(String), L(Vec<S>) }
fn parse(s: &[char], p: &mut usize) -> Result<S, String> {
    while s.get(*p).is_some_and(|c| c.is_whitespace()) { *p += 1; }
    match s.get(*p) {
        Some('(') => {
            *p += 1; let mut v = Vec::new();
            loop {
                while s.get(*p).is_some_and(|c| c.is_whitespace()) { *p += 1; }
                match s.get(*p) {
                    Some(')') => { *p += 1; return Ok(S::L(v)); }
                    None => return Err("unclosed list".into()),
                    _ => v.push(parse(s, p)?),
                }
            }
        }
        Some(')') => Err("unexpected )".into()),
        Some('"') => {
            *p += 1; let mut v = String::new();
            loop { match s.get(*p) {
                Some('"') => { *p += 1; return Ok(S::A(v)); }
                Some('\\') => { *p += 1; let c = *s.get(*p).ok_or("bad escape")?; v.push(c); *p += 1; }
                Some(c) => { v.push(*c); *p += 1; }
                None => return Err("unclosed quote".into()),
            }}
        }
        Some(_) => { let b=*p; while s.get(*p).is_some_and(|c| !c.is_whitespace() && *c!='(' && *c!=')') { *p+=1; } Ok(S::A(s[b..*p].iter().collect())) }
        None => Err("unexpected eof".into()),
    }
}
fn elems<'a>(x: &'a S, key: &'a str) -> impl Iterator<Item=&'a S> {
    let v = if let S::L(v)=x { v.as_slice() } else { &[] };
    v.iter().filter(move |x| matches!(x, S::L(y) if matches!(y.first(), Some(S::A(h)) if h==key)))
}
fn field(x: &S, key: &str) -> Result<String,String> {
    let f=elems(x,key).next().ok_or_else(||format!("missing {key}"))?;
    if let S::L(v)=f { if let Some(S::A(a))=v.get(1) { return Ok(a.clone()); } }
    Err(format!("bad {key}"))
}
type Pin=(String,String);
struct Graph { components:BTreeSet<String>, pins:BTreeMap<Pin,String> }
fn graph(text:&str)->Result<Graph,String> {
    let chars:Vec<char>=text.chars().collect(); let mut at=0; let root=parse(&chars,&mut at)?;
    let comps=elems(&root,"components").next().ok_or("no components")?;
    let mut refs=BTreeMap::new(); let mut ids=BTreeSet::new();
    for c in elems(comps,"comp") {
        let r=field(c,"ref")?; let path=elems(c,"sheetpath").next().ok_or("no sheetpath")?;
        let id=field(path,"names")?.split("::").last().ok_or("empty id")?.to_string();
        if refs.insert(r,id.clone()).is_some() || !ids.insert(id) { return Err("duplicate reference/id".into()); }
    }
    let nets=elems(&root,"nets").next().ok_or("no nets")?; let mut pins=BTreeMap::new();
    for n in elems(nets,"net") { let name=field(n,"name")?;
        for node in elems(n,"node") { let r=field(node,"ref")?; let id=refs.get(&r).ok_or("bad ref")?;
            let pin=(id.clone(),field(node,"pin")?); if pins.insert(pin,name.clone()).is_some(){return Err("duplicate pin".into());}
        }
    }
    Ok(Graph{components:ids,pins})
}
fn group(g:&Graph, net:&str)->BTreeSet<Pin>{g.pins.iter().filter(|(_,n)|n.as_str()==net).map(|(p,_)|p.clone()).collect()}
fn check_net(g:&Graph, name:&str, expected:&[(&str,&str)]) -> Result<(),String> {
    let want:BTreeSet<Pin>=expected.iter().map(|(a,b)|(a.to_string(),b.to_string())).collect();
    let got=group(g,name); if got!=want { return Err(format!("{name}: expected {want:?}, got {got:?}")); } Ok(())
}
fn validate(g:&Graph, text:&str)->Result<(),String>{
    if g.components.len()!=30 { return Err(format!("expected 30 parts, got {}",g.components.len())); }
    if text.contains("ATMEGA") || text.contains("Atmega") { return Err("unexpected ATmega in ESP-only fixture".into()); }
    for id in ["ctrl_iso","permit_feedback_iso","source_latch","latch","blanking"] { if !g.components.contains(id){return Err(format!("missing {id}"));} }
    if !text.contains("(part \"ISO7721FDR\")") { return Err("ISO7721FDR absent".into()); }
    for (id,pin,net) in [
        ("ctrl_iso","3","source_permit"),("ctrl_iso","4","source_hot_rearm"),("ctrl_iso","5","source_arm"),
        ("ctrl_iso","6","source_hot_health"),("ctrl_iso","11","hot_raw_health"),
        ("permit_feedback_iso","13","hot_permit_rx"),("permit_feedback_iso","4","source_permit_readback"),
        ("source_latch","5","source_permit"),("source_latch","11","source_permit_readback"),
        ("source_latch","13","source_seen_clear_n"),("source_latch","1","source_permit_clear_n"),
        ("latch","11","hot_rearm_rx"),("latch","13","ready_clear_n"),
        ("latch","9","hot_ready"),("latch","3","hot_arm_rx"),
        ("latch","1","run_clear_n"),("latch","5","hot_run"),
        ("blanking","3","hot_timer_mr"),("blanking","5","hot_timer_ct"),("blanking","6","hot_timer_reset_n"),
    ] { if g.pins.get(&(id.into(),pin.into())).is_none_or(|n|n!=net){return Err(format!("{id}.{pin} must join {net}"));} }
    check_net(g,"source_permit",&[("ctrl_iso","3"),("source_latch","5"),("source_permit_pd","1")])?;
    check_net(g,"source_hot_health",&[("ctrl_iso","6"),("effective_health_gate","2")])?;
    check_net(g,"source_effective_health",&[("effective_health_gate","4"),("source_reset_health_gate","1"),("seen_clear_gate","1")])?;
    check_net(g,"source_permit_readback",&[("permit_feedback_iso","4"),("permit_clear_allow","2"),("source_latch","11")])?;
    check_net(g,"source_permit_not_seen",&[("source_latch","8"),("permit_clear_allow","1")])?;
    check_net(g,"source_clear_allow",&[("permit_clear_allow","4"),("permit_clear_gate","2")])?;
    check_net(g,"source_permit_clear_n",&[("permit_clear_gate","4"),("source_latch","1")])?;
    check_net(g,"source_session_reset_n",&[("seen_clear_gate","2"),("source_session_reset_pullup","1"),("source_reset_health_gate","2")])?;
    check_net(g,"permit_fault_ok",&[("permit_fault_gate","4"),("timer_mr_gate","1")])?;
    check_net(g,"hot_permit_rx",&[("ctrl_iso","14"),("permit_feedback_iso","13"),("permit_fault_gate","1"),("ready_permit_gate","1"),("run_ready_gate","2"),("hot_pd","1")])?;
    check_net(g,"hot_timer_mr",&[("timer_mr_gate","4"),("blanking","3")])?;
    check_net(g,"hot_timer_reset_n",&[("blanking","6"),("ready_timer_gate","2"),("timer_reset_pullup","1")])?;
    check_net(g,"ready_clear_n",&[("ready_timer_gate","4"),("latch","13")])?;
    check_net(g,"run_clear_n",&[("run_rail_gate","4"),("latch","1")])?;
    check_net(g,"hot_rearm_rx",&[("ctrl_iso","13"),("latch","11")])?;
    check_net(g,"hot_arm_rx",&[("ctrl_iso","12"),("latch","3")])?;
    if g.pins.get(&("ctrl_iso".into(),"1".into()))==g.pins.get(&("ctrl_iso".into(),"16".into())) { return Err("ISO7741F SELV/HOT supply pins shorted".into()); }
    if g.pins.get(&("permit_feedback_iso".into(),"3".into()))==g.pins.get(&("permit_feedback_iso".into(),"14".into())) { return Err("ISO7721F SELV/HOT supply pins shorted".into()); }
    Ok(())
}
fn main(){
    let text=fs::read_to_string("build/default.net").expect("build netlist"); let g=graph(&text).expect("parse netlist");
    validate(&g,&text).expect("critical pin joins");
    let mut bad=g.pins.clone(); bad.insert(("permit_feedback_iso".into(),"13".into()),"hot_gnd".into());
    let mutated=Graph{components:g.components.clone(),pins:bad};
    assert!(validate(&mutated,&text).is_err(),"permit-return miswire mutation accepted");
    println!("PASS: {} components; exact HOT permit, fault, MR, rearm, ARM, latch, and readback joins audited. Connectivity only.",g.components.len());
}
