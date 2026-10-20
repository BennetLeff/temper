//! Native-coordinate planar path measurements, not an inductance extractor.
use std::{collections::HashMap, env, fs};
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct Point(i64, i64);
fn distance(a: Point, b: Point) -> f64 { ((a.0-b.0) as f64).hypot((a.1-b.1) as f64) / 1e6 }
fn on_segment(p: Point, a: Point, b: Point) -> bool {
    (distance(a,p)+distance(p,b)-distance(a,b)).abs() < 0.000002
}
#[derive(Clone)]
struct Segment { net: String, layer: String, a: Point, b: Point }
fn main() {
    let text = fs::read_to_string(env::args().nth(1).expect("native geometry TSV")).unwrap();
    let board_hash=text.lines().find_map(|line|line.strip_prefix("# board_sha256=")).expect("native board hash");
    assert!(board_hash.len()==64 && board_hash.chars().all(|c|c.is_ascii_hexdigit()));
    let mut segments = Vec::new();
    let mut pads = HashMap::new();
    let mut through = Vec::new();
    let point = |fields: &[&str], i: usize| Point(fields[i].parse().unwrap(), fields[i+1].parse().unwrap());
    for line in text.lines().filter(|line| !line.starts_with('#')) {
        let c: Vec<_> = line.split('\t').collect();
        match c[0] {
            "SEG" => segments.push(Segment { net: c[1].into(), layer:c[2].into(), a:point(&c,3), b:point(&c,5) }),
            "VIA" => through.push((c[1].to_string(),point(&c,2))),
            "PAD" => {
                let p=point(&c,3);
                pads.insert(c[1].to_string(),(c[2].to_string(),p));
                if c[5]=="1" { through.push((c[2].to_string(),p)); }
            },
            _ => panic!("unexpected export row"),
        }
    }
    let queries = [
        ("local_cf_input", "U7.2", "C104.1"),
        ("local_cf_output", "C104.2", "U7.1"),
        ("100r_input", "U7.2", "R43.1"),
        ("100r_rf_to_header", "R43.2", "JP4.2"),
        ("100r_header_to_output", "JP4.1", "U7.1"),
        ("5k_input", "U7.2", "R44.1"),
        ("5k_rf_to_header", "R44.2", "JP5.2"),
        ("5k_header_to_output", "JP5.1", "U7.1"),
        ("100k_input", "U7.2", "R45.1"),
        ("100k_rf_to_header", "R45.2", "JP6.2"),
        ("100k_header_to_output", "JP6.1", "U7.1"),
    ];
    println!("{{\n  \"board_sha256\": \"{board_hash}\",\n  \"method\": \"Native KiCad segment graph, physical vias/PTH only; planar lengths exclude component conductors and vertical via length\",\n  \"paths\": [");
    for (q,(label,start,end)) in queries.iter().enumerate() {
        let (net,start_point)=pads.get(*start).expect(start);
        let (end_net,end_point)=pads.get(*end).expect(end);
        assert_eq!(net,end_net,"query endpoints on different nets");
        let selected:Vec<_>=segments.iter().filter(|s| &s.net==net).collect();
        let mut nodes:Vec<(String,Point)>=Vec::new();
        for segment in &selected {
            for p in [segment.a,segment.b,*start_point,*end_point]
                .into_iter().chain(through.iter().filter(|(n,_)| n==net).map(|(_,p)| *p)) {
                if on_segment(p,segment.a,segment.b) && !nodes.contains(&(segment.layer.clone(),p)) {
                    nodes.push((segment.layer.clone(),p));
                }
            }
        }
        let mut edges=vec![Vec::<(usize,f64,bool)>::new();nodes.len()];
        for segment in selected {
            let mut points:Vec<_>=nodes.iter().enumerate().filter(|(_, (layer,p))|layer==&segment.layer&&on_segment(*p,segment.a,segment.b))
                .map(|(i,(_,p))|(i,distance(segment.a,*p))).collect();
            points.sort_by(|a,b|a.1.total_cmp(&b.1));
            for pair in points.windows(2) {
                let ((i,a),(j,b))=(pair[0],pair[1]);
                edges[i].push((j,b-a,false)); edges[j].push((i,b-a,false));
            }
        }
        for (i,(layer,a)) in nodes.iter().enumerate() {
            for (j,(other,b)) in nodes.iter().enumerate().skip(i+1) {
                if a==b && layer!=other && through.contains(&(net.clone(),*a)) {
                    edges[i].push((j,0.,true)); edges[j].push((i,0.,true));
                }
            }
        }
        let index=|p:Point|nodes.iter().position(|(layer,pt)|layer=="F.Cu"&&*pt==p).unwrap_or_else(||panic!("{label}: point {p:?} has no F.Cu segment"));
        let (s,e)=(index(*start_point),index(*end_point));
        let mut costs=vec![f64::INFINITY;nodes.len()]; let mut used=vec![false;nodes.len()];
        let mut prev=vec![None;nodes.len()];costs[s]=0.;
        for _ in 0..nodes.len() {
            let i=(0..nodes.len()).filter(|i|!used[*i]).min_by(|a,b|costs[*a].total_cmp(&costs[*b])).unwrap();
            if !costs[i].is_finite() || i==e { break; }
            used[i]=true;
            for &(j,len,transition) in &edges[i] {
                if costs[i]+len<costs[j] { costs[j]=costs[i]+len;prev[j]=Some((i,transition)); }
            }
        }
        assert!(costs[e].is_finite(),"no connected path for {label}");
        let mut transitions=0; let mut cursor=e;
        while cursor!=s { let (parent,via)=prev[cursor].unwrap();transitions+=usize::from(via);cursor=parent; }
        println!("    {{\"name\":\"{label}\",\"start\":\"{start}\",\"end\":\"{end}\",\"net\":\"{net}\",\"planar_mm\":{:.6},\"layer_transitions\":{transitions}}}{}",costs[e],if q+1==queries.len(){""}else{","});
    }
    println!("  ]\n}}");
}
