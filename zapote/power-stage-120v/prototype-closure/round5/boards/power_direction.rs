//! D-30: board-facing connector directions and joined supply reachability.
//! Standalone std-only tool; PWR_FLAG symbols and connectors are never producers.
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::Path,
    process::ExitCode,
};

const BOARDS: [&str; 9] = [
    "central", "catch", "bus", "line", "pre", "out", "tank", "iproof", "iline",
];
const HARNESSES: [(&str, &str, &str, usize); 8] = [
    ("catch", "J_CATCH_POD", "J2", 6),
    ("bus", "J_VBUS_POD", "J2", 6),
    ("line", "J_VLINE_POD", "J2", 6),
    ("pre", "J_VPRE_POD", "J2", 6),
    ("out", "J_VOUT_POD", "J2", 6),
    ("tank", "J_VTANK_POD", "J2", 6),
    ("iproof", "J_IPROOF_BURDEN", "J_IPROOF_SIGNAL", 2),
    ("iline", "J_ILINE_BURDEN", "J_ILINE_SIGNAL", 2),
];
// Explicit external boundary assumptions, not on-board producers or measured supplies.
// Source identities agree with connector-map.json and the round4 external partition.
const EXTERNAL: [(&str, &str, &str, &str, &str); 5] = [
    (
        "J_AUX24",
        "1",
        "AUX_24V",
        "passive",
        "external AUX 24V supply",
    ),
    ("J_AUX24", "2", "AUX_0V", "passive", "external AUX return"),
    (
        "J_REG5",
        "3",
        "POD_5V",
        "passive",
        "external REG5 converter output",
    ),
    (
        "JCTRL",
        "1",
        "CTRL_3V3",
        "power_in",
        "external controller 3V3 supply",
    ),
    (
        "JCTRL",
        "2",
        "CTRL_GND",
        "passive",
        "external controller return",
    ),
];

#[derive(Clone, Debug)]
struct Pin {
    board: String,
    reference: String,
    source_ref: String,
    number: String,
    net: String,
    kind: String,
    location: String,
}
impl Pin {
    fn connector(&self) -> bool {
        self.reference.starts_with('J')
    }
    fn component(&self) -> bool {
        !self.connector() && !self.reference.starts_with('#')
    }
    fn identity(&self) -> String {
        format!("{}:{}.{}", self.board, self.reference, self.number)
    }
    fn node(&self) -> (String, String) {
        (self.board.clone(), self.net.clone())
    }
    fn power_source(&self) -> bool {
        self.component() && self.kind == "power_out"
    }
    fn signal_source(&self) -> bool {
        self.component()
            && [
                "power_out",
                "output",
                "open_collector",
                "open_emitter",
                "tri_state",
            ]
            .contains(&self.kind.as_str())
    }
}

fn parse_table(board: &str, path: &str, text: &str) -> Result<Vec<Pin>, String> {
    let mut lines = text.lines();
    let header: Vec<_> = lines
        .next()
        .ok_or_else(|| format!("{path}: empty table"))?
        .split('\t')
        .collect();
    if header.iter().collect::<BTreeSet<_>>().len() != header.len() {
        return Err(format!("{path}: duplicate header"));
    }
    let index = |name: &str| {
        header
            .iter()
            .position(|h| *h == name)
            .ok_or_else(|| format!("{path}: missing {name} column"))
    };
    let (r, p, n, t) = (
        index("reference")?,
        index("pin")?,
        index("net")?,
        index("type")?,
    );
    let source = header.iter().position(|h| *h == "source_ref");
    let mut pins = Vec::new();
    let mut seen = BTreeSet::new();
    for (i, line) in lines.enumerate() {
        let location = format!("{path}:{}", i + 2);
        let cells: Vec<_> = line.split('\t').collect();
        if cells.len() != header.len() || cells.iter().any(|s| s.trim().is_empty()) {
            return Err(format!("{location}: malformed or empty field"));
        }
        if ![
            "passive",
            "power_in",
            "power_out",
            "input",
            "output",
            "bidirectional",
            "tri_state",
            "open_collector",
            "open_emitter",
            "no_connect",
            "unspecified",
            "free",
        ]
        .contains(&cells[t])
        {
            return Err(format!("{location}: unknown pin type {}", cells[t]));
        }
        if !seen.insert((cells[r].to_owned(), cells[p].to_owned())) {
            return Err(format!(
                "{location}: duplicate pin {}.{}",
                cells[r], cells[p]
            ));
        }
        pins.push(Pin {
            board: board.into(),
            reference: cells[r].into(),
            source_ref: cells[source.unwrap_or(r)].into(),
            number: cells[p].into(),
            net: cells[n].into(),
            kind: cells[t].into(),
            location,
        });
    }
    if pins.is_empty() {
        return Err(format!("{path}: no pins"));
    }
    Ok(pins)
}

#[derive(Clone, Debug)]
struct Boundary {
    pin: usize,
    expected_type: String,
    description: String,
}
#[derive(Clone, Debug)]
struct Design {
    pins: Vec<Pin>,
    links: Vec<(usize, usize)>,
    boundaries: Vec<Boundary>,
}
fn endpoint(pins: &[Pin], board: &str, source: &str, number: &str) -> Result<usize, String> {
    let matches: Vec<_> = pins
        .iter()
        .enumerate()
        .filter(|(_, p)| p.board == board && p.source_ref == source && p.number == number)
        .map(|(i, _)| i)
        .collect();
    match matches.as_slice() {
        [i] => Ok(*i),
        _ => Err(format!(
            "{board}:{source}.{number}: expected exactly one endpoint, found {}",
            matches.len()
        )),
    }
}
fn load(base: &Path) -> Result<Design, String> {
    let mut pins = Vec::new();
    for board in BOARDS {
        let path = base.join(if board == "central" {
            "central/generated/pins.tsv".into()
        } else {
            format!("{board}-pins.tsv")
        });
        let text = fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        pins.extend(parse_table(board, &path.to_string_lossy(), &text)?);
    }
    let mut links = Vec::new();
    for (board, central, remote, count) in HARNESSES {
        for (b, r) in [("central", central), (board, remote)] {
            if pins
                .iter()
                .filter(|p| p.board == b && p.source_ref == r)
                .count()
                != count
            {
                return Err(format!("{b}:{r}: harness pin inventory changed"));
            }
        }
        for number in 1..=count {
            let a = endpoint(&pins, "central", central, &number.to_string())?;
            let b = endpoint(&pins, board, remote, &number.to_string())?;
            if pins[a].net != pins[b].net {
                return Err(format!(
                    "{} -> {}: straight-through harness net mismatch",
                    pins[a].identity(),
                    pins[b].identity()
                ));
            }
            links.push((a, b));
        }
    }
    let mut boundaries = Vec::new();
    for (source, number, net, expected_type, description) in EXTERNAL {
        let pin = endpoint(&pins, "central", source, number)?;
        if pins[pin].net != net {
            return Err(format!(
                "{}: external supply net changed (expected {net})",
                pins[pin].location
            ));
        }
        boundaries.push(Boundary {
            pin,
            expected_type: expected_type.into(),
            description: description.into(),
        });
    }
    Ok(Design {
        pins,
        links,
        boundaries,
    })
}

#[derive(Debug)]
struct Audit {
    errors: Vec<String>,
    rows: Vec<String>,
}
fn validate(design: &Design) -> Audit {
    let pins = &design.pins;
    let mut nodes = BTreeMap::new();
    let pin_nodes: Vec<_> = pins
        .iter()
        .map(|p| {
            let next = nodes.len();
            *nodes.entry(p.node()).or_insert(next)
        })
        .collect();
    let mut groups: Vec<_> = (0..nodes.len()).collect();
    // Join only explicit harness endpoints, never equal net names on separate boards.
    for &(a, b) in &design.links {
        let old = groups[pin_nodes[b]];
        let new = groups[pin_nodes[a]];
        for g in &mut groups {
            if *g == old {
                *g = new;
            }
        }
    }
    let group = |i: usize| groups[pin_nodes[i]];
    let mut errors = Vec::new();
    for boundary in &design.boundaries {
        let p = &pins[boundary.pin];
        if p.kind != boundary.expected_type {
            errors.push(format!(
                "boundary_direction {} {}: expected {}, found {}",
                p.location,
                p.identity(),
                boundary.expected_type,
                p.kind
            ));
        }
    }
    let mut rows = Vec::new();
    for (i, p) in pins.iter().enumerate() {
        if p.net == "NC" {
            if p.kind == "power_in" {
                errors.push(format!(
                    "unconnected_typed_pin {} {}",
                    p.location,
                    p.identity()
                ));
            }
            continue;
        }
        let local: Vec<_> = pins
            .iter()
            .filter(|q| {
                q.board == p.board
                    && q.net == p.net
                    && if ["power_in", "power_out"].contains(&p.kind.as_str()) {
                        q.power_source()
                    } else {
                        q.signal_source()
                    }
            })
            .map(Pin::identity)
            .collect();
        let mut joined: Vec<_> = pins
            .iter()
            .enumerate()
            .filter(|(j, q)| group(*j) == group(i) && q.power_source())
            .map(|(_, q)| q.identity())
            .collect();
        joined.extend(
            design
                .boundaries
                .iter()
                .filter(|b| group(b.pin) == group(i))
                .map(|b| format!("{} via {}", b.description, pins[b.pin].identity())),
        );
        if p.connector() && ["power_out", "output"].contains(&p.kind.as_str()) && local.is_empty() {
            errors.push(format!(
                "connector_without_onboard_source {} {} {} {}",
                p.location,
                p.identity(),
                p.net,
                p.kind
            ));
        }
        if p.kind == "power_in" && joined.is_empty() {
            errors.push(format!(
                "undriven_power_input {} {} {}",
                p.location,
                p.identity(),
                p.net
            ));
        }
        if p.connector() || p.kind == "power_in" {
            rows.push(format!(
                "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}",
                p.board,
                p.reference,
                p.number,
                p.net,
                p.kind,
                p.location,
                if local.is_empty() {
                    "-".into()
                } else {
                    local.join("; ")
                },
                if joined.is_empty() {
                    "-".into()
                } else {
                    joined.join("; ")
                }
            ));
        }
    }
    let outputs: Vec<_> = pins
        .iter()
        .enumerate()
        .filter(|(_, p)| p.connector() && p.kind == "power_out" && p.net != "NC")
        .collect();
    for (offset, &(i, a)) in outputs.iter().enumerate() {
        for &(j, b) in &outputs[offset + 1..] {
            if a.board != b.board && group(i) == group(j) {
                errors.push(format!(
                    "harness_power_out_conflict {} {} <-> {} {}",
                    a.location,
                    a.identity(),
                    b.location,
                    b.identity()
                ));
            }
        }
    }
    Audit { errors, rows }
}

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 2 {
        return Err("usage: power-direction <round5/boards directory>".into());
    }
    let design = load(Path::new(&args[1]))?;
    let audit = validate(&design);
    println!("board\treference\tpin\tnet\ttype\tfile_line\tonboard_typed_source\tjoined_power_source_or_boundary");
    for row in &audit.rows {
        println!("{row}");
    }
    eprintln!("Audited {} boards, {} pins, {} harness conductors, {} declared external supply/return endpoints; {} findings",
        BOARDS.len(), design.pins.len(), design.links.len(), design.boundaries.len(), audit.errors.len());
    if audit.errors.is_empty() {
        Ok(())
    } else {
        Err(audit.errors.join("\n"))
    }
}
fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn pin(board: &str, reference: &str, net: &str, kind: &str) -> Pin {
        Pin {
            board: board.into(),
            reference: reference.into(),
            source_ref: reference.into(),
            number: "1".into(),
            net: net.into(),
            kind: kind.into(),
            location: "fixture:2".into(),
        }
    }
    fn design(pins: Vec<Pin>, links: Vec<(usize, usize)>) -> Design {
        Design {
            pins,
            links,
            boundaries: vec![],
        }
    }
    fn has(d: &Design, code: &str) -> bool {
        validate(d).errors.iter().any(|s| s.starts_with(code))
    }
    fn production() -> Design {
        load(Path::new(file!()).parent().unwrap()).unwrap()
    }

    #[test]
    fn all_nine_production_boards_pass() {
        assert!(
            validate(&production()).errors.is_empty(),
            "{:?}",
            validate(&production()).errors
        );
    }
    #[test]
    fn actual_j9_supply_regression_is_rejected() {
        let mut d = production();
        let i = endpoint(&d.pins, "central", "JCTRL", "1").unwrap();
        d.pins[i].kind = "power_out".into();
        assert!(has(&d, "connector_without_onboard_source"));
    }
    #[test]
    fn actual_j9_return_regression_is_rejected() {
        let mut d = production();
        let i = endpoint(&d.pins, "central", "JCTRL", "2").unwrap();
        d.pins[i].kind = "power_out".into();
        assert!(has(&d, "connector_without_onboard_source"));
    }
    #[test]
    fn actual_regulator_removal_leaves_six_remote_supplies_undriven() {
        let mut d = production();
        let i = endpoint(&d.pins, "central", "REG3", "2");
        // Bind this mutation to the regulator present in the production pin table.
        assert!(i.is_ok(), "Production regulator alias changed");
        d.pins[i.unwrap()].kind = "passive".into();
        let a = validate(&d);
        for board in ["catch", "bus", "line", "pre", "out", "tank"] {
            assert!(
                a.errors
                    .iter()
                    .any(|e| e.starts_with("undriven_power_input")
                        && e.contains(&format!("{board}:U1.12"))),
                "{board}: {:?}",
                a.errors
            );
        }
    }
    #[test]
    fn missing_controller_boundary_does_not_borrow_aux_supply() {
        let mut d = production();
        d.boundaries.retain(|b| d.pins[b.pin].net != "CTRL_3V3");
        assert!(has(&d, "undriven_power_input"));
    }
    #[test]
    fn connectors_cannot_drive_each_other_without_a_component() {
        let d = design(
            vec![
                pin("a", "J1", "V", "power_out"),
                pin("a", "J2", "V", "output"),
            ],
            vec![],
        );
        assert_eq!(validate(&d).errors.len(), 2);
    }
    #[test]
    fn output_requires_a_driver_even_if_external_power_is_declared() {
        let mut d = design(vec![pin("a", "J1", "V", "output")], vec![]);
        d.boundaries.push(Boundary {
            pin: 0,
            expected_type: "output".into(),
            description: "external".into(),
        });
        assert!(has(&d, "connector_without_onboard_source"));
    }
    #[test]
    fn open_collector_is_a_signal_driver() {
        let d = design(
            vec![
                pin("a", "U1", "SIG", "open_collector"),
                pin("a", "J1", "SIG", "output"),
            ],
            vec![],
        );
        assert!(validate(&d).errors.is_empty());
    }
    #[test]
    fn signal_output_is_not_a_power_producer() {
        let d = design(
            vec![
                pin("a", "U1", "V", "output"),
                pin("a", "J1", "V", "power_out"),
            ],
            vec![],
        );
        assert!(has(&d, "connector_without_onboard_source"));
    }
    #[test]
    fn pwr_flag_is_not_an_onboard_producer() {
        let d = design(
            vec![
                pin("a", "#FLG1", "V", "power_out"),
                pin("a", "J1", "V", "power_out"),
            ],
            vec![],
        );
        assert!(has(&d, "connector_without_onboard_source"));
    }
    #[test]
    fn same_net_name_on_unjoined_boards_is_not_a_source() {
        let d = design(
            vec![
                pin("a", "U1", "V", "power_out"),
                pin("b", "U1", "V", "power_in"),
            ],
            vec![],
        );
        assert!(has(&d, "undriven_power_input"));
    }
    #[test]
    fn joined_real_source_powers_remote_input() {
        let d = design(
            vec![
                pin("a", "U1", "V", "power_out"),
                pin("a", "J1", "V", "passive"),
                pin("b", "J1", "RAIL", "passive"),
                pin("b", "U1", "RAIL", "power_in"),
            ],
            vec![(1, 2)],
        );
        assert!(validate(&d).errors.is_empty());
    }
    #[test]
    fn two_locally_driven_harness_outputs_conflict() {
        let d = design(
            vec![
                pin("a", "U1", "V", "power_out"),
                pin("a", "J1", "V", "power_out"),
                pin("b", "J1", "OTHER", "power_out"),
                pin("b", "U1", "OTHER", "power_out"),
            ],
            vec![(1, 2)],
        );
        assert_eq!(validate(&d).errors.len(), 1);
        assert!(has(&d, "harness_power_out_conflict"));
    }
    #[test]
    fn transitive_harness_outputs_also_conflict() {
        let d = design(
            vec![
                pin("a", "U1", "V", "power_out"),
                pin("a", "J1", "V", "power_out"),
                pin("b", "J1", "B", "passive"),
                pin("b", "J2", "B", "passive"),
                pin("c", "J1", "C", "power_out"),
                pin("c", "U1", "C", "power_out"),
            ],
            vec![(1, 2), (3, 4)],
        );
        assert!(has(&d, "harness_power_out_conflict"));
    }
    #[test]
    fn intentionally_unconnected_component_outputs_are_allowed() {
        assert!(
            validate(&design(vec![pin("a", "U1", "NC", "output")], vec![]))
                .errors
                .is_empty()
        );
    }
    #[test]
    fn unconnected_power_input_is_rejected() {
        assert!(has(
            &design(vec![pin("a", "U1", "NC", "power_in")], vec![]),
            "unconnected_typed_pin"
        ));
    }
    #[test]
    fn empty_table_is_rejected() {
        assert!(parse_table("a", "x", "reference\tpin\tnet\ttype\n").is_err());
    }
    #[test]
    fn duplicate_pin_is_rejected() {
        assert!(parse_table(
            "a",
            "x",
            "reference\tpin\tnet\ttype\nJ1\t1\tV\tpassive\nJ1\t1\tV\tpower_out"
        )
        .is_err());
    }
    #[test]
    fn unknown_pin_type_is_rejected() {
        assert!(parse_table("a", "x", "reference\tpin\tnet\ttype\nJ1\t1\tV\tpower_otu").is_err());
    }
    #[test]
    fn missing_type_column_is_rejected() {
        assert!(parse_table("a", "x", "reference\tpin\tnet\nJ1\t1\tV").is_err());
    }
}
