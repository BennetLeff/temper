#[cfg(not(test))]
use std::fs::File;
#[cfg(not(test))]
use std::io::BufWriter;
#[cfg(not(test))]
use std::io::BufReader;
#[cfg(not(test))]
use std::io;
use std::io::{BufRead, Write};

const WIDTH: usize = 31;
const RELTOL: f64 = 2e-4;
const VNTOL: f64 = 1e-7;
const ABSTOL: f64 = 1e-10;
#[cfg_attr(test, allow(dead_code))]
const PARAMETER_SPEC_SHA256: &str = "3195dd698608326019ceff6dbd371a60f4feaaf8add7b91e7cab99245e46e24a";

#[derive(Clone, Debug)]
pub struct DeltaStat {
    pub max_abs: f64,
    pub max_normalized: f64,
    pub normalized_applicable: bool,
    pub exact_changes: u64,
    pub max_group: u64,
    pub max_row: u64,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct EnergyStat {
    pub name: &'static str,
    pub coefficient: f64,
    pub signed_sum_j: f64,
    pub absolute_sum_j: f64,
    pub max_absolute_j: f64,
    pub pairs: u64,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Summary {
    pub rows: u64,
    pub equal_groups: u64,
    pub equal_repeats: u64,
    pub first_equal_time: Option<f64>,
    pub last_equal_time: Option<f64>,
    pub max_group_rows: u64,
    pub right_context_missing: u64,
    pub deltas: [DeltaStat; WIDTH],
    pub energies: Vec<EnergyStat>,
    pub selected_energy_absolute_sum_j: f64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditError(pub String);

impl std::fmt::Display for AuditError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for AuditError {}

#[derive(Clone)]
struct Row {
    number: u64,
    time: f64,
    values: [f64; WIDTH],
}

#[derive(Clone, Copy)]
struct EnergyDef {
    name: &'static str,
    coefficient: f64,
    first: &'static str,
    second: Option<&'static str>,
}

const ENERGY_DEFS: [EnergyDef; 11] = [
    EnergyDef { name: "Cbank_vb", coefficient: 2240e-6, first: "v(vb)", second: None },
    EnergyDef { name: "Clocal_vd", coefficient: 19.8e-6, first: "v(vd)", second: None },
    EnergyDef { name: "Lboost_current", coefficient: 180e-6, first: "i(Lboost)", second: None },
    EnergyDef { name: "Cds_sw_ground", coefficient: 344e-12, first: "v(sw)", second: None },
    EnergyDef { name: "Cgd_gate_sw", coefficient: 112e-12, first: "v(gate)", second: Some("v(sw)") },
    EnergyDef { name: "Cgs_gate_ground", coefficient: 12e-9, first: "v(gate)", second: None },
    EnergyDef { name: "Cisense_ground", coefficient: 1e-9, first: "v(isense)", second: None },
    EnergyDef { name: "Cicomp_ground", coefficient: 2.7e-9, first: "v(icomp)", second: None },
    EnergyDef { name: "Cvcomp_p_ground", coefficient: 220e-9, first: "v(vcomp)", second: None },
    EnergyDef { name: "Cdriver_delay_ground", coefficient: 18.75e-9, first: "v(xdriver.drv_delay)", second: None },
    EnergyDef { name: "Cblank_ground", coefficient: 1e-12, first: "v(xu.blank)", second: None },
];

fn parse_row(line: &str, line_number: usize) -> Result<[f64; WIDTH], AuditError> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != WIDTH {
        return Err(AuditError(format!(
            "line {line_number}: expected {WIDTH} fields, got {}",
            fields.len()
        )));
    }
    let mut values = [0.0_f64; WIDTH];
    for (column, field) in fields.iter().enumerate() {
        values[column] = field.parse().map_err(|error| {
            AuditError(format!("line {line_number}, column {column}: invalid {field:?}: {error}"))
        })?;
        if !values[column].is_finite() {
            return Err(AuditError(format!(
                "line {line_number}, column {column}: non-finite value {field}"
            )));
        }
    }
    Ok(values)
}

fn empty_delta() -> DeltaStat {
    DeltaStat {
        max_abs: 0.0,
        max_normalized: 0.0,
        normalized_applicable: true,
        exact_changes: 0,
        max_group: 0,
        max_row: 0,
    }
}

fn normalized_applicable(column: usize, name: &str) -> bool {
    if column == 0 {
        return false;
    }
    !matches!(
        name,
        "v(q)"
            | "v(en)"
            | "v(fault)"
            | "v(xu.raw)"
            | "v(xu.pwm_hold)"
            | "v(pwm)"
            | "v(pwm_input)"
            | "v(xdriver.driver_req)"
            | "v(xu.ov)"
            | "v(xu.fault)"
            | "v(xu.pcl_hold)"
            | "v(xu.pcl_request)"
    )
}

fn empty_energy(def: EnergyDef) -> EnergyStat {
    EnergyStat {
        name: def.name,
        coefficient: def.coefficient,
        signed_sum_j: 0.0,
        absolute_sum_j: 0.0,
        max_absolute_j: 0.0,
        pairs: 0,
    }
}

fn emit_event<W: Write>(writer: &mut W, role: &str, group: u64, row: &Row) -> Result<(), AuditError> {
    write!(writer, "{role}\t{group}\t{}", row.number).map_err(|error| AuditError(error.to_string()))?;
    for value in row.values {
        write!(writer, "\t{value:.17e}").map_err(|error| AuditError(error.to_string()))?;
    }
    writeln!(writer).map_err(|error| AuditError(error.to_string()))?;
    Ok(())
}

fn state_value(values: &[f64; WIDTH], first: usize, second: Option<usize>) -> f64 {
    second.map_or(values[first], |index| values[first] - values[index])
}

pub fn analyze<R: BufRead, W: Write>(reader: R, mut events: W) -> Result<Summary, AuditError> {
    let mut lines = reader.lines();
    let header_line = lines
        .next()
        .ok_or_else(|| AuditError("missing header".to_string()))?
        .map_err(|error| AuditError(error.to_string()))?;
    let headers: Vec<String> = header_line.split_whitespace().map(str::to_string).collect();
    if headers.len() != WIDTH || headers.first().map(String::as_str) != Some("time") {
        return Err(AuditError(format!("expected 31-column header starting with time, got {} fields", headers.len())));
    }
    let mut unique = std::collections::HashSet::new();
    if headers.iter().any(|header| header.is_empty() || !unique.insert(header)) {
        return Err(AuditError("header names must be non-empty and unique".to_string()));
    }
    let index_of = |name: &str| headers.iter().position(|header| header == name);
    let mut energy_indices = Vec::with_capacity(ENERGY_DEFS.len());
    for def in ENERGY_DEFS {
        let first = index_of(def.first).ok_or_else(|| AuditError(format!("missing energy state {}", def.first)))?;
        let second = def.second.map(|name| index_of(name).ok_or_else(|| AuditError(format!("missing energy state {name}")))).transpose()?;
        energy_indices.push((first, second));
    }
    let mut event_header = String::from("role\tgroup_id\tsource_row");
    for header in &headers {
        event_header.push('\t');
        event_header.push_str(header);
    }
    writeln!(events, "{event_header}").map_err(|error| AuditError(error.to_string()))?;

    let mut rows = 0_u64;
    let mut previous: Option<Row> = None;
    let mut before_previous: Option<Row> = None;
    let mut active_group: Option<(u64, f64, u64)> = None;
    let mut group_id = 0_u64;
    let mut equal_groups = 0_u64;
    let mut equal_repeats = 0_u64;
    let mut first_equal_time = None;
    let mut last_equal_time = None;
    let mut max_group_rows = 0_u64;
    let mut right_context_missing = 0_u64;
    let mut deltas = std::array::from_fn(|column| DeltaStat {
        normalized_applicable: normalized_applicable(column, &headers[column]),
        ..empty_delta()
    });
    let mut energies: [EnergyStat; ENERGY_DEFS.len()] = std::array::from_fn(|index| empty_energy(ENERGY_DEFS[index]));

    for (line_offset, line) in lines.enumerate() {
        let line_number = line_offset + 2;
        let line = line.map_err(|error| AuditError(error.to_string()))?;
        if line.trim().is_empty() {
            continue;
        }
        let values = parse_row(&line, line_number)?;
        let row = Row { number: rows + 1, time: values[0], values };
        if let Some(previous_row) = previous.as_ref() {
            if row.time < previous_row.time {
                return Err(AuditError(format!("backward time at row {}", row.number)));
            }
            if row.time == previous_row.time {
                if active_group.is_none() {
                    group_id += 1;
                    active_group = Some((group_id, row.time, 2));
                    equal_groups += 1;
                    first_equal_time.get_or_insert(row.time);
                    last_equal_time = Some(row.time);
                    max_group_rows = max_group_rows.max(2);
                    if let Some(left) = before_previous.as_ref() {
                        emit_event(&mut events, "LEFT", group_id, left)?;
                    }
                    emit_event(&mut events, "GROUP", group_id, previous_row)?;
                    emit_event(&mut events, "GROUP", group_id, &row)?;
                } else {
                    let (active_id, active_time, count) = active_group.as_mut().expect("active group");
                    debug_assert_eq!(*active_time, row.time);
                    *count += 1;
                    max_group_rows = max_group_rows.max(*count);
                    last_equal_time = Some(row.time);
                    emit_event(&mut events, "GROUP", *active_id, &row)?;
                }
                equal_repeats += 1;
                for column in 0..WIDTH {
                    let absolute = (row.values[column] - previous_row.values[column]).abs();
                    let scale = RELTOL * row.values[column].abs().max(previous_row.values[column].abs());
                    let tolerance = scale + if headers[column].starts_with("i(") { ABSTOL } else { VNTOL };
                    if absolute != 0.0 {
                        deltas[column].exact_changes += 1;
                    }
                    if absolute > deltas[column].max_abs {
                        deltas[column].max_abs = absolute;
                        deltas[column].max_group = group_id;
                        deltas[column].max_row = row.number;
                    }
                    if deltas[column].normalized_applicable {
                        let normalized = absolute / tolerance;
                        deltas[column].max_normalized = deltas[column].max_normalized.max(normalized);
                    }
                }
                for (index, &(first, second)) in energy_indices.iter().enumerate() {
                    let a = state_value(&previous_row.values, first, second);
                    let b = state_value(&row.values, first, second);
                    let delta = 0.5 * energies[index].coefficient * (b - a) * (b + a);
                    energies[index].signed_sum_j += delta;
                    energies[index].absolute_sum_j += delta.abs();
                    energies[index].max_absolute_j = energies[index].max_absolute_j.max(delta.abs());
                    energies[index].pairs += 1;
                }
                previous = Some(row);
                rows += 1;
                continue;
            }
            if let Some((active_id, active_time, _)) = active_group.take() {
                debug_assert!(row.time > active_time);
                emit_event(&mut events, "RIGHT", active_id, &row)?;
                before_previous = previous.clone();
            } else {
                before_previous = previous.clone();
            }
        }
        previous = Some(row);
        rows += 1;
    }
    if let Some((active_id, _, _)) = active_group.take() {
        right_context_missing += 1;
        let _ = active_id;
    }
    if rows == 0 {
        return Err(AuditError("trace has no data rows".to_string()));
    }
    events.flush().map_err(|error| AuditError(error.to_string()))?;
    let selected_energy_absolute_sum_j = energies.iter().map(|energy| energy.absolute_sum_j).sum();
    Ok(Summary {
        rows,
        equal_groups,
        equal_repeats,
        first_equal_time,
        last_equal_time,
        max_group_rows,
        right_context_missing,
        deltas,
        energies: energies.into_iter().collect(),
        selected_energy_absolute_sum_j,
    })
}

#[cfg_attr(test, allow(dead_code))]
fn print_summary(summary: &Summary, headers: &[String]) {
    println!("rows={}", summary.rows);
    println!("equal_groups={}", summary.equal_groups);
    println!("equal_repeats={}", summary.equal_repeats);
    println!("first_equal_time_s={:?}", summary.first_equal_time);
    println!("last_equal_time_s={:?}", summary.last_equal_time);
    println!("max_group_rows={}", summary.max_group_rows);
    println!("right_context_missing_groups={}", summary.right_context_missing);
    println!("solver_options=reltol:{RELTOL:.1e},vntol:{VNTOL:.1e},abstol:{ABSTOL:.1e}");
    println!("parameter_spec_sha256={PARAMETER_SPEC_SHA256}");
    println!("max_adjacent_delta_by_column:");
    for column in 0..WIDTH {
        println!(
            "  column={} name={} max_abs={:.18e} max_normalized={} exact_changes={} group={} row={} within_solver_tolerance={}",
            column,
            headers[column],
            summary.deltas[column].max_abs,
            if summary.deltas[column].normalized_applicable {
                format!("{:.18e}", summary.deltas[column].max_normalized)
            } else {
                "N/A".to_string()
            },
            summary.deltas[column].exact_changes,
            summary.deltas[column].max_group,
            summary.deltas[column].max_row,
            if summary.deltas[column].normalized_applicable {
                summary.deltas[column].max_normalized <= 1.0
            } else {
                false
            },
        );
    }
    println!("selected_state_energy_changes:");
    for energy in &summary.energies {
        println!(
            "  state={} coefficient={:.18e} signed_sum_j={:.18e} absolute_sum_j={:.18e} max_absolute_j={:.18e} pairs={}",
            energy.name, energy.coefficient, energy.signed_sum_j, energy.absolute_sum_j, energy.max_absolute_j, energy.pairs
        );
    }
    println!("selected_states_sum_absolute_j={:.18e} (upper contribution bound for selected pairs only)", summary.selected_energy_absolute_sum_j);
    println!("diagnostic_only=within_solver_tolerance_is_not_acceptance_or_physical_proof");
}

#[cfg(not(test))]
fn main() {
    let mut args = std::env::args().skip(1);
    let mut event_path = String::from("equal-time-events.tsv");
    while let Some(arg) = args.next() {
        if arg == "--events" {
            event_path = args.next().unwrap_or_else(|| {
                eprintln!("--events requires a path");
                std::process::exit(2);
            });
        } else {
            eprintln!("unknown argument {arg}");
            std::process::exit(2);
        }
    }
    let file = File::create(&event_path).unwrap_or_else(|error| {
        eprintln!("cannot create {event_path}: {error}");
        std::process::exit(2);
    });
    let mut events = BufWriter::new(file);
    let result = analyze(io::BufReader::new(io::stdin().lock()), &mut events);
    match result {
        Ok(summary) => {
            // Header names are fixed by the analyze contract; recover them from
            // the event artifact's header for stable output labels.
            let headers: Vec<String> = File::open(&event_path)
                .ok()
                .and_then(|file| {
                    let mut reader = BufReader::new(file);
                    let mut line = String::new();
                    reader.read_line(&mut line).ok().map(|_| line.trim_end().split('\t').skip(3).map(str::to_string).collect())
                })
                .unwrap_or_else(|| (0..WIDTH).map(|index| format!("column{index}")).collect());
            print_summary(&summary, &headers);
            println!("event_artifact={event_path}");
        }
        Err(error) => {
            eprintln!("REJECTED: {error}");
            std::process::exit(1);
        }
    }
}
