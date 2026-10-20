//! Audit native KiCad exports against schematic connectivity and divider symmetry.
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
};
fn attr<'a>(s: &'a str, key: &str) -> &'a str {
    s.split_once(&format!("{key}=\""))
        .unwrap()
        .1
        .split('"')
        .next()
        .unwrap()
}
fn body<'a>(s: &'a str, key: &str) -> &'a str {
    s.split_once(&format!("<{key}>"))
        .map(|(_, v)| v.split_once(&format!("</{key}>")).unwrap().0)
        .unwrap_or("")
}
fn nm(s: &str) -> i64 {
    (s.parse::<f64>().unwrap() * 1e6).round() as i64
}
fn rows(path: &str) -> Vec<Vec<String>> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .skip(1)
        .map(|l| l.split('\t').map(str::to_string).collect())
        .collect()
}
fn main() {
    let xml = fs::read_to_string("validation/netlist.xml").unwrap();
    let components: BTreeMap<_, _> = xml
        .split("<comp ref=")
        .skip(1)
        .map(|s| {
            let c = s.split("</comp>").next().unwrap();
            (
                c.split('"').nth(1).unwrap().to_string(),
                (
                    body(c, "value").to_string(),
                    body(c, "footprint").to_string(),
                    c.contains("name=\"dnp\""),
                ),
            )
        })
        .collect();
    let fp_rows = rows("validation/pcb-footprints.tsv");
    let fps: BTreeMap<_, _> = fp_rows.iter().map(|r| (r[0].clone(), r)).collect();
    assert_eq!(fps.len(), fp_rows.len(), "duplicate physical references");
    let mut expected = BTreeMap::new();
    for section in xml.split("<net code=").skip(1) {
        let s = section.split("</net>").next().unwrap();
        let net = attr(s, "name");
        for node in s.split("<node ").skip(1) {
            let r = attr(node, "ref");
            if components.get(r).is_some_and(|c| !c.1.is_empty()) {
                expected.insert(format!("{r}.{}", attr(node, "pin")), net.to_string());
            }
        }
    }
    for r in rows("layout/landings.tsv") {
        assert!(expected
            .insert(format!("{}.{}", r[0], r[1]), r[2].clone())
            .is_none());
    }
    let pad_rows = rows("validation/pcb-pads.tsv");
    let mut pads = BTreeMap::new();
    for p in &pad_rows {
        if p[1].is_empty() {
            assert!(p[2].is_empty(), "NPTH with assigned net");
            continue;
        }
        let key = format!("{}.{}", p[0], p[1]);
        assert_eq!(
            expected.get(&key),
            Some(&p[2]),
            "physical pad net mismatch: {key}"
        );
        pads.entry(key).or_insert(p);
    }
    assert_eq!(pads.len(), expected.len(), "missing PCB pads");
    for (r, (value, fp, dnp)) in &components {
        if fp.is_empty() {
            assert!(
                !fps.contains_key(r),
                "offboard component unexpectedly mounted: {r}"
            );
            continue;
        }
        let physical = fps
            .get(r)
            .unwrap_or_else(|| panic!("missing footprint {r}"));
        assert_eq!(&physical[1], value, "value mismatch {r}");
        assert_eq!(
            physical[2],
            fp.split(':').nth(1).unwrap(),
            "footprint mismatch {r}"
        );
        assert_eq!(physical[3] == "1", *dnp, "DNP mismatch {r}");
    }
    let extras: BTreeSet<_> = rows("layout/landings.tsv")
        .iter()
        .map(|r| r[0].clone())
        .chain(["H5".into(), "H6".into()])
        .collect();
    for r in fps.keys() {
        assert!(
            components.contains_key(r) || extras.contains(r),
            "unexplained footprint {r}"
        );
    }
    let mut pairs = Vec::new();
    for n in 1..=12 {
        pairs.push((format!("R{n}"), format!("R{}", n + 20)));
    }
    for n in 1..=5 {
        pairs.push((format!("C{n}"), format!("C{}", n + 20)));
    }
    for n in 41..=47 {
        pairs.push((format!("C{n}"), format!("C{}", n + 10)));
    }
    for (a, b) in [
        ("U1", "U2"),
        ("D1", "D2"),
        ("RV1", "RV2"),
        ("C81", "C83"),
        ("C82", "C84"),
        ("W_HV1", "W_HV2"),
    ] {
        pairs.push((a.into(), b.into()));
    }
    pairs.push(("CT1".into(), "CT2".into()));
    let mut matched_pads = 0;
    for (a, b) in &pairs {
        for p in pad_rows.iter().filter(|p| &p[0] == a && !p[1].is_empty()) {
            let q = pads[&format!("{}.{}", b, p[1])];
            assert_eq!(nm(&p[3]), nm(&q[3]), "x symmetry {a} {b}");
            assert_eq!(nm(&p[4]) + 35_000_000, nm(&q[4]), "y symmetry {a} {b}");
            for k in 5..=8 {
                assert_eq!(p[k], q[k], "pad geometry symmetry {a} {b}");
            }
            matched_pads += 1;
        }
    }
    let tracks = rows("validation/pcb-tracks.tsv");
    let shape = |net: &str, dy: i64| -> Vec<_> {
        let mut result = Vec::new();
        for t in tracks.iter().filter(|t| t[1] == net) {
            let mut ends = [(nm(&t[4]), nm(&t[5]) - dy), (nm(&t[6]), nm(&t[7]) - dy)];
            ends.sort();
            result.push((t[0].clone(), t[2].clone(), nm(&t[3]), ends));
        }
        result.sort();
        result
    };
    let mut matched_nets = 0;
    for (a, b) in (1..=10)
        .map(|i| (format!("R{i}.1"), format!("R{}.1", i + 20)))
        .chain([
            ("R10.2".into(), "R30.2".into()),
            ("U1.3".into(), "U2.3".into()),
        ])
    {
        let na = &pads[&a][2];
        let nb = &pads[&b][2];
        let sa = shape(na, 0);
        let sb = shape(nb, 35_000_000);
        assert!(!sa.is_empty(), "missing track geometry {na}");
        assert_eq!(sa, sb, "divider track symmetry {na} vs {nb}");
        matched_nets += 1;
    }
    for i in 1..=10 {
        for base in [0, 20] {
            let net = &pads[&format!("R{}.1", base + i)][2];
            for t in tracks.iter().filter(|t| &t[1] == net) {
                assert_eq!(t[0], "track", "HV via present");
                assert_eq!(t[2], "F.Cu", "HV routing on hidden layer");
            }
        }
    }
    // Extract the wanted path from the native F.Cu graph, independently of
    // the hand-authored waypoint lists. Comparator islands are on other layers.
    let wanted_length = |source: &str, target: &str| -> f64 {
        let net = &pads[source][2];
        let start = (nm(&pads[source][3]), nm(&pads[source][4]));
        let end = (nm(&pads[target][3]), nm(&pads[target][4]));
        let mut graph: BTreeMap<(i64, i64), Vec<((i64, i64), f64)>> = BTreeMap::new();
        for t in tracks
            .iter()
            .filter(|t| t[0] == "track" && t[1] == *net && t[2] == "F.Cu")
        {
            let a = (nm(&t[4]), nm(&t[5]));
            let b = (nm(&t[6]), nm(&t[7]));
            let length = ((a.0 - b.0) as f64).hypot((a.1 - b.1) as f64) / 1e6;
            graph.entry(a).or_default().push((b, length));
            graph.entry(b).or_default().push((a, length));
        }
        let mut distance = BTreeMap::from([(start, 0.0_f64)]);
        let mut visited = BTreeSet::new();
        loop {
            let (&point, &length) = distance
                .iter()
                .filter(|(p, _)| !visited.contains(*p))
                .min_by(|a, b| a.1.total_cmp(b.1))
                .expect("wanted F.Cu path disconnected");
            if point == end {
                break length;
            }
            visited.insert(point);
            for &(next, edge) in graph.get(&point).expect("wanted path node absent") {
                let candidate = length + edge;
                distance
                    .entry(next)
                    .and_modify(|d| *d = d.min(candidate))
                    .or_insert(candidate);
            }
        }
    };
    let p_length = wanted_length("U1.6", "R61.1");
    let n_length = wanted_length("U2.6", "R62.1");
    assert!(
        (p_length - n_length).abs() < 0.001,
        "wanted feed length mismatch: {p_length}/{n_length} mm"
    );
    // Independently maximize each linear voltage difference at the vertices of
    // |VP|<=3kV, |VN|<=3kV, |VP-VN|<=3kV. The extrema are exact integer volts.
    let vertices = [
        (-3000i32, -3000i32),
        (-3000, 0),
        (0, 3000),
        (3000, 3000),
        (3000, 0),
        (0, -3000),
    ];
    for a in 0..=10i32 {
        for b in 0..=10i32 {
            let cross = vertices
                .iter()
                .map(|&(p, n)| (a * p / 10 - b * n / 10).abs())
                .max()
                .unwrap();
            assert_eq!(
                cross,
                300 * a.max(b),
                "opposite-leg voltage envelope ranks {a}/{b}"
            );
            let same = vertices
                .iter()
                .map(|&(p, _)| ((a - b) * p / 10).abs())
                .max()
                .unwrap();
            assert_eq!(
                same,
                300 * (a - b).abs(),
                "same-leg voltage envelope ranks {a}/{b}"
            );
        }
    }
    let rules = fs::read_to_string("cad/differential-probe.kicad_dru").unwrap();
    assert!(rules.contains("(rule \"TIP_P to TIP_N\" (condition \"A.NetName == 'TIP_P' && B.NetName == 'TIP_N'\") (constraint clearance (min 10mm)) (constraint creepage (min 20mm)))"),"opposing-tip DRC rule must encode the approved 3kV differential envelope");
    let report=format!("PASS: {} physical footprints; every circuit value, selected footprint and DNP state matches KiCad XML.\nPASS: {} unique physical pin mappings match the schematic and explicit offboard landings; duplicate switch pads checked individually.\nPASS: {} paired footprints / {matched_pads} pad pairs translate exactly 35 mm; identical pad dimensions and orientation.\nPASS: {matched_nets} paired divider/tap/input nets have identical native track/via geometry after that translation.\nPASS: all 20 elevated ladder nodes routed only on F.Cu, without vias.\nPASS: wanted U1-to-R61 and U2-to-R62 feeds use F.Cu throughout; native shortest-path lengths {p_length:.3} / {n_length:.3} mm agree within 0.001 mm.\nPASS: all rank-pair voltage bounds agree with independent maximization over the six allowed input-envelope vertices; opposing-tip DRC is 10 mm air / 20 mm surface.\nThese checks do not establish capacitance matching, CMRR, stability or an insulation rating.\n",fps.len(),pads.len(),pairs.len());
    print!("{report}");
    fs::write("validation/pcb-checks.txt", report).unwrap();
}
