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
        // Unnumbered holes and "MP" mechanical support pins carry no net.
        if p[1].is_empty() || p[1] == "MP" {
            assert!(p[2].is_empty(), "mechanical pad with assigned net");
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
        .chain(["H3".into(), "H4".into()])
        .collect();
    for r in fps.keys() {
        assert!(
            components.contains_key(r) || extras.contains(r),
            "unexplained footprint {r}"
        );
    }
    // Rev C legs are mirror images about the inter-leg slot axis y = AXIS.
    const AXIS: i64 = 35_000_000;
    let mirror = |y: i64| 2 * AXIS - y;
    let mut pairs = Vec::new();
    for n in 1..=5 {
        pairs.push((format!("R{n}"), format!("R{}", n + 20)));
        pairs.push((format!("C{n}"), format!("C{}", n + 20)));
    }
    for (a, b) in [
        ("R11", "R31"),
        ("R12", "R32"),
        ("C41", "C51"),
        ("C42", "C52"),
        ("C43", "C53"),
        ("RV1", "RV2"),
        ("CT1", "CT2"),
        ("D1", "D2"),
        ("W_HV1", "W_HV2"),
    ] {
        pairs.push((a.into(), b.into()));
    }
    // Pad geometry as an unordered set: mirroring a SOT-23 about a horizontal
    // line exchanges its pins 1 and 2 (the two rail clamps), as recorded.
    let pad_shape = |p: &Vec<String>, flip: bool| {
        let angle: f64 = p[7].parse().unwrap();
        let quarter = ((angle / 90.).round() as i64).rem_euclid(2);
        let (w, h) = if quarter == 1 {
            (nm(&p[6]), nm(&p[5]))
        } else {
            (nm(&p[5]), nm(&p[6]))
        };
        let y = nm(&p[4]);
        (nm(&p[3]), if flip { mirror(y) } else { y }, w, h, p[8].clone())
    };
    let mut matched_pads = 0;
    for (a, b) in &pairs {
        let mut pa: Vec<_> = pad_rows
            .iter()
            .filter(|p| &p[0] == a && !p[1].is_empty())
            .map(|p| pad_shape(p, true))
            .collect();
        let mut pb: Vec<_> = pad_rows
            .iter()
            .filter(|p| &p[0] == b && !p[1].is_empty())
            .map(|p| pad_shape(p, false))
            .collect();
        pa.sort();
        pb.sort();
        assert!(!pa.is_empty(), "missing pads {a}");
        assert_eq!(pa, pb, "mirror pad symmetry {a} {b}");
        matched_pads += pa.len();
    }
    let tracks = rows("validation/pcb-tracks.tsv");
    let shape = |net: &str, flip: bool| -> Vec<_> {
        let mut result = Vec::new();
        for t in tracks.iter().filter(|t| t[1] == net) {
            let fy = |v: &str| if flip { mirror(nm(v)) } else { nm(v) };
            let mut ends = [(nm(&t[4]), fy(&t[5])), (nm(&t[6]), fy(&t[7]))];
            ends.sort();
            result.push((t[0].clone(), t[2].clone(), nm(&t[3]), ends));
        }
        result.sort();
        result
    };
    let mut matched_nets = 0;
    let mut divider_nets = vec![("TIP_P".to_string(), "TIP_N".to_string())];
    for k in 1..=4 {
        divider_nets.push((format!("P_SEG{k}"), format!("N_SEG{k}")));
    }
    for (a, b) in [("TAP_P", "TAP_N"), ("TRIM_P", "TRIM_N")] {
        divider_nets.push((a.into(), b.into()));
    }
    for (na, nb) in &divider_nets {
        let sa = shape(na, true);
        let sb = shape(nb, false);
        assert!(!sa.is_empty(), "missing track geometry {na}");
        assert_eq!(sa, sb, "divider track mirror symmetry {na} vs {nb}");
        matched_nets += 1;
    }
    for base in [0, 20] {
        for i in 1..=5 {
            let net = &pads[&format!("R{}.1", base + i)][2];
            for t in tracks.iter().filter(|t| &t[1] == net) {
                assert_eq!(t[0], "track", "HV via present");
                assert_eq!(t[2], "F.Cu", "HV routing on hidden layer");
            }
        }
    }
    // Shortest routed path between two pads over all layers (vias are zero length).
    let routed_length = |source: &str, target: &str| -> (f64, usize) {
        let net = &pads[source][2];
        let start = (nm(&pads[source][3]), nm(&pads[source][4]));
        let end = (nm(&pads[target][3]), nm(&pads[target][4]));
        let mut graph: BTreeMap<(i64, i64), Vec<((i64, i64), f64)>> = BTreeMap::new();
        let mut vias = BTreeSet::new();
        for t in tracks.iter().filter(|t| t[1] == *net) {
            let a = (nm(&t[4]), nm(&t[5]));
            let b = (nm(&t[6]), nm(&t[7]));
            if t[0] == "via" {
                vias.insert(a);
                continue;
            }
            let length = ((a.0 - b.0) as f64).hypot((a.1 - b.1) as f64) / 1e6;
            graph.entry(a).or_default().push((b, length));
            graph.entry(b).or_default().push((a, length));
        }
        let mut distance = BTreeMap::from([(start, 0.0_f64)]);
        let mut previous: BTreeMap<(i64, i64), (i64, i64)> = BTreeMap::new();
        let mut visited = BTreeSet::new();
        let length = loop {
            let (&point, &length) = distance
                .iter()
                .filter(|(p, _)| !visited.contains(*p))
                .min_by(|a, b| a.1.total_cmp(b.1))
                .unwrap_or_else(|| panic!("routed path {source}-{target} disconnected"));
            if point == end {
                break length;
            }
            visited.insert(point);
            for &(next, edge) in graph.get(&point).expect("routed path node absent") {
                let candidate = length + edge;
                if distance.get(&next).map_or(true, |d| candidate < *d) {
                    distance.insert(next, candidate);
                    previous.insert(next, point);
                }
            }
        };
        let mut count = 0;
        let mut at = end;
        while let Some(&p) = previous.get(&at) {
            if vias.contains(&p) {
                count += 1;
            }
            at = p;
        }
        (length, count)
    };
    let mut paired_lengths = String::new();
    for (label, (a1, b1), (a2, b2)) in [
        ("tap-to-buffer input (R12/R32 to U1)", ("R12.2", "U1.3"), ("R32.2", "U1.5")),
        ("buffer output to subtractor input resistor", ("U1.1", "R61.1"), ("U1.7", "R62.1")),
    ] {
        let (lp, vp) = routed_length(a1, b1);
        let (ln, vn) = routed_length(a2, b2);
        assert!(
            (lp - ln).abs() < 0.001 && vp == vn,
            "{label} mismatch: {lp:.4}/{ln:.4} mm, vias {vp}/{vn}"
        );
        paired_lengths += &format!("PASS: {label}: {lp:.3} / {ln:.3} mm, {vp} / {vn} vias.\n");
    }
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
    for a in 0..=5i32 {
        for b in 0..=5i32 {
            let cross = vertices
                .iter()
                .map(|&(p, n)| (a * p / 5 - b * n / 5).abs())
                .max()
                .unwrap();
            assert_eq!(
                cross,
                600 * a.max(b),
                "opposite-leg voltage envelope ranks {a}/{b}"
            );
            let same = vertices
                .iter()
                .map(|&(p, _)| ((a - b) * p / 5).abs())
                .max()
                .unwrap();
            assert_eq!(
                same,
                600 * (a - b).abs(),
                "same-leg voltage envelope ranks {a}/{b}"
            );
        }
    }
    let rules = fs::read_to_string("cad/differential-probe.kicad_dru").unwrap();
    assert!(rules.contains("(rule \"TIP_P to TIP_N\" (condition \"A.NetName == 'TIP_P' && B.NetName == 'TIP_N'\") (constraint clearance (min 10mm)) (constraint creepage (min 20mm)))"),"opposing-tip DRC rule must encode the approved 3kV differential envelope");
    // Courtyard fill of the LV region (x >= 59 mm; 91 x 70 mm less the two 3 mm
    // corner chamfers = 6361 mm^2), by courtyard layer, counting every courtyard
    // whose bounding-box centre lies in the region (BT top-side screw keep-outs and
    // SW3's bottom tail keep-out included).
    let lv_area = 91. * 70. - 2. * 4.5;
    let mut fill = [0f64; 2];
    for r in rows("validation/pcb-courtyards.tsv") {
        let cx = (r[3].parse::<f64>().unwrap() + r[5].parse::<f64>().unwrap()) / 2.;
        if cx >= 59. {
            fill[(r[1] == "B") as usize] += r[2].parse::<f64>().unwrap();
        }
    }
    let fill_line = format!("INFO: LV-region courtyard fill (x >= 59 mm, {lv_area:.0} mm2): F.CrtYd {:.1} %, B.CrtYd {:.1} %, both sides {:.1} %.\n", fill[0] / lv_area * 100., fill[1] / lv_area * 100., (fill[0] + fill[1]) / 2. / lv_area * 100.);
    let report=format!("PASS: {} physical footprints; every circuit value, selected footprint and DNP state matches KiCad XML.\nPASS: {} unique physical pin mappings match the schematic and explicit landings; duplicate pads checked individually.\nPASS: {} paired footprints / {matched_pads} pad pairs are exact mirror images about the y = 35 mm slot axis (identical pad dimensions; SOT-23 clamp pins 1/2 exchange under the mirror).\nPASS: {matched_nets} paired divider/tap/trim nets have identical native track geometry after mirroring.\nPASS: all 10 elevated ladder nodes routed only on F.Cu, without vias.\n{paired_lengths}{fill_line}PASS: all rank-pair voltage bounds agree with independent maximization over the six allowed input-envelope vertices (600 V per section rank); opposing-tip DRC is 10 mm air / 20 mm surface.\nThese checks do not establish capacitance matching, CMRR, stability or an insulation rating.\n",fps.len(),pads.len(),pairs.len());
    print!("{report}");
    fs::write("validation/pcb-checks.txt", report).unwrap();
}
