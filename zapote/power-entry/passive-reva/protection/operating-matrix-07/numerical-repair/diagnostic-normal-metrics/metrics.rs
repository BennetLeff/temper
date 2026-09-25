#[cfg(not(test))]
use std::io;
use std::io::BufRead;

const WIDTH: usize = 31;
const WINDOW_START: f64 = 0.6;
const WINDOW_END: f64 = 0.65;
const CYCLES: usize = 3;

#[derive(Clone, Debug)]
pub struct Extreme {
    pub min: f64,
    pub min_row: u64,
    pub min_time: f64,
    pub max: f64,
    pub max_row: u64,
    pub max_time: f64,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Cycle {
    pub start: f64,
    pub end: f64,
    pub mean_vb: f64,
    pub min_vb: f64,
    pub max_vb: f64,
    pub covered: bool,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Metrics {
    pub rows: u64,
    pub first_time: f64,
    pub last_time: f64,
    pub duplicate_groups: u64,
    pub duplicate_rows: u64,
    pub max_positive_gap: f64,
    pub cycles: Vec<Cycle>,
    pub cycle_mean_range_over_first_mean: Option<f64>,
    pub il: Extreme,
    pub vd: Extreme,
    pub vb: Extreme,
    pub vds_sw_ground: Extreme,
    pub abs_gate: Extreme,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MetricsError(pub String);

impl std::fmt::Display for MetricsError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for MetricsError {}

#[derive(Clone, Copy)]
struct Indices {
    time: usize,
    vb: usize,
    il: usize,
    vd: usize,
    sw: usize,
    gate: usize,
}

fn required_indices(headers: &[String]) -> Result<Indices, MetricsError> {
    if headers.len() != WIDTH {
        return Err(MetricsError(format!(
            "header has {} columns; expected {WIDTH}",
            headers.len()
        )));
    }
    if headers[0] != "time" {
        return Err(MetricsError(format!("column 0 must be time, got {:?}", headers[0])));
    }
    let mut unique_headers = std::collections::HashSet::new();
    if headers.iter().any(|header| header.is_empty() || !unique_headers.insert(header)) {
        return Err(MetricsError("header column names must be non-empty and unique".to_string()));
    }
    let find = |name: &str| {
        headers
            .iter()
            .position(|header| header == name)
            .ok_or_else(|| MetricsError(format!("missing required column {name:?}")))
    };
    Ok(Indices {
        time: 0,
        vb: find("v(vb)")?,
        il: find("i(Lboost)")?,
        vd: find("v(vd)")?,
        sw: find("v(sw)")?,
        gate: find("v(gate)")?,
    })
}

fn parse_row(line: &str, line_number: usize) -> Result<[f64; WIDTH], MetricsError> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != WIDTH {
        return Err(MetricsError(format!(
            "line {line_number}: expected {WIDTH} columns, got {}",
            fields.len()
        )));
    }
    let mut values = [0.0_f64; WIDTH];
    for (column, field) in fields.iter().enumerate() {
        values[column] = field.parse().map_err(|error| {
            MetricsError(format!("line {line_number}, column {column}: invalid number {field:?}: {error}"))
        })?;
        if !values[column].is_finite() {
            return Err(MetricsError(format!(
                "line {line_number}, column {column}: non-finite value {field}"
            )));
        }
    }
    Ok(values)
}

fn update_extreme(extreme: &mut Option<Extreme>, value: f64, row: u64, time: f64) {
    match extreme {
        None => {
            *extreme = Some(Extreme {
                min: value,
                min_row: row,
                min_time: time,
                max: value,
                max_row: row,
                max_time: time,
            });
        }
        Some(current) => {
            if value < current.min {
                current.min = value;
                current.min_row = row;
                current.min_time = time;
            }
            if value > current.max {
                current.max = value;
                current.max_row = row;
                current.max_time = time;
            }
        }
    }
}

fn interval_bounds(index: usize) -> (f64, f64) {
    let targets = [WINDOW_START, 37.0 / 60.0, 19.0 / 30.0, WINDOW_END];
    (targets[index], targets[index + 1])
}

fn clipped_trapezoid(
    t0: f64,
    v0: f64,
    t1: f64,
    v1: f64,
    start: f64,
    end: f64,
) -> Option<(f64, f64, f64)> {
    if t1 <= t0 {
        return None;
    }
    let left = t0.max(start);
    let right = t1.min(end);
    if right <= left {
        return None;
    }
    let slope = (v1 - v0) / (t1 - t0);
    let left_value = v0 + slope * (left - t0);
    let right_value = v0 + slope * (right - t0);
    Some((right - left, left_value, right_value))
}

pub fn analyze<R: BufRead>(reader: R) -> Result<Metrics, MetricsError> {
    let mut lines = reader.lines();
    let header = lines
        .next()
        .ok_or_else(|| MetricsError("missing header".to_string()))?
        .map_err(|error| MetricsError(format!("reading header: {error}")))?;
    let headers: Vec<String> = header.split_whitespace().map(str::to_string).collect();
    let indices = required_indices(&headers)?;
    let mut rows = 0_u64;
    let mut previous: Option<(f64, [f64; WIDTH])> = None;
    let mut first_time = 0.0;
    let mut last_time = 0.0;
    let mut duplicate_groups = 0_u64;
    let mut duplicate_rows = 0_u64;
    let mut max_positive_gap = 0.0_f64;
    let mut il = None;
    let mut vd = None;
    let mut vb = None;
    let mut vds_sw_ground = None;
    let mut abs_gate = None;
    let mut previous_duplicate = false;
    let mut cycle_area = [0.0; CYCLES];
    let mut cycle_duration = [0.0; CYCLES];
    let mut cycle_min = [f64::INFINITY; CYCLES];
    let mut cycle_max = [f64::NEG_INFINITY; CYCLES];
    let mut cycle_covered = [false; CYCLES];

    for (line_offset, line) in lines.enumerate() {
        let line_number = line_offset + 2;
        let line = line.map_err(|error| MetricsError(format!("reading line {line_number}: {error}")))?;
        if line.trim().is_empty() {
            continue;
        }
        let values = parse_row(&line, line_number)?;
        let row = rows + 1;
        let time = values[indices.time];
        if rows == 0 {
            first_time = time;
        }
        if let Some((previous_time, previous_values)) = previous {
            let dt = time - previous_time;
            if dt < 0.0 {
                return Err(MetricsError(format!(
                    "backward time at row {row}: {time:.18e} < {previous_time:.18e}"
                )));
            }
            if dt == 0.0 {
                duplicate_rows += 1;
                if !previous_duplicate {
                    duplicate_groups += 1;
                }
                previous_duplicate = true;
            } else {
                previous_duplicate = false;
                max_positive_gap = max_positive_gap.max(dt);
                for cycle in 0..CYCLES {
                    let (start, end) = interval_bounds(cycle);
                    if let Some((duration, left_value, right_value)) = clipped_trapezoid(
                        previous_time,
                        previous_values[indices.vb],
                        time,
                        values[indices.vb],
                        start,
                        end,
                    ) {
                        cycle_area[cycle] += duration * (left_value + right_value) / 2.0;
                        cycle_duration[cycle] += duration;
                        cycle_min[cycle] = cycle_min[cycle].min(left_value).min(right_value);
                        cycle_max[cycle] = cycle_max[cycle].max(left_value).max(right_value);
                        cycle_covered[cycle] = true;
                    }
                }
            }
        }
        update_extreme(&mut il, values[indices.il], row, time);
        update_extreme(&mut vd, values[indices.vd], row, time);
        update_extreme(&mut vb, values[indices.vb], row, time);
        update_extreme(&mut vds_sw_ground, values[indices.sw], row, time);
        update_extreme(&mut abs_gate, values[indices.gate].abs(), row, time);
        for cycle in 0..CYCLES {
            let (start, end) = interval_bounds(cycle);
            if time >= start && time <= end {
                cycle_min[cycle] = cycle_min[cycle].min(values[indices.vb]);
                cycle_max[cycle] = cycle_max[cycle].max(values[indices.vb]);
            }
        }
        previous = Some((time, values));
        last_time = time;
        rows += 1;
    }
    if rows == 0 {
        return Err(MetricsError("trace has no data rows".to_string()));
    }
    if last_time < WINDOW_END {
        return Err(MetricsError(format!(
            "incomplete requested window: last_time={last_time:.18e}, required_end={WINDOW_END:.18e}"
        )));
    }
    let mut cycles = Vec::with_capacity(CYCLES);
    for cycle in 0..CYCLES {
        let (start, end) = interval_bounds(cycle);
        let duration = end - start;
        if !cycle_covered[cycle] || (cycle_duration[cycle] - duration).abs() > duration * 1e-12 {
            return Err(MetricsError(format!(
                "cycle {cycle} not fully covered: integrated={:.18e}, required={duration:.18e}",
                cycle_duration[cycle]
            )));
        }
        cycles.push(Cycle {
            start,
            end,
            mean_vb: cycle_area[cycle] / cycle_duration[cycle],
            min_vb: cycle_min[cycle],
            max_vb: cycle_max[cycle],
            covered: cycle_covered[cycle],
        });
    }
    let first_mean = cycles[0].mean_vb;
    let cycle_mean_range = cycles
        .iter()
        .map(|cycle| cycle.mean_vb)
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(min, max), mean| {
            (min.min(mean), max.max(mean))
        });
    let cycle_mean_range_over_first_mean = if first_mean > 0.0 {
        Some((cycle_mean_range.1 - cycle_mean_range.0) / first_mean)
    } else {
        None
    };
    Ok(Metrics {
        rows,
        first_time,
        last_time,
        duplicate_groups,
        duplicate_rows,
        max_positive_gap,
        cycles,
        cycle_mean_range_over_first_mean,
        il: il.expect("rows imply IL extrema"),
        vd: vd.expect("rows imply VD extrema"),
        vb: vb.expect("rows imply VB extrema"),
        vds_sw_ground: vds_sw_ground.expect("rows imply SW extrema"),
        abs_gate: abs_gate.expect("rows imply gate extrema"),
    })
}

#[cfg_attr(test, allow(dead_code))]
fn print_extreme(name: &str, extreme: &Extreme) {
    println!(
        "prefix_{name}_min={:.18e}@row{}@{:.18e}s prefix_{name}_max={:.18e}@row{}@{:.18e}s",
        extreme.min,
        extreme.min_row,
        extreme.min_time,
        extreme.max,
        extreme.max_row,
        extreme.max_time,
    );
}

#[cfg_attr(test, allow(dead_code))]
pub fn print_metrics(metrics: &Metrics) {
    println!("rows={}", metrics.rows);
    println!("first_time_s={:.18e}", metrics.first_time);
    println!("last_time_s={:.18e}", metrics.last_time);
    println!("duplicate_groups={}", metrics.duplicate_groups);
    println!("duplicate_rows_after_first={}", metrics.duplicate_rows);
    println!("max_positive_gap_s={:.18e}", metrics.max_positive_gap);
    for (index, cycle) in metrics.cycles.iter().enumerate() {
        println!(
            "cycle_{index}_start_s={:.18e} end_s={:.18e} covered={} mean_vb_v={:.18e} min_vb_v={:.18e} max_vb_v={:.18e}",
            cycle.start, cycle.end, cycle.covered, cycle.mean_vb, cycle.min_vb, cycle.max_vb
        );
    }
    match metrics.cycle_mean_range_over_first_mean {
        Some(ratio) => println!("cycle_mean_range_over_first_mean={ratio:.18e} (diagnostic)"),
        None => println!("cycle_mean_range_over_first_mean=undefined (first mean is non-positive; diagnostic)"),
    }
    print_extreme("il_a", &metrics.il);
    print_extreme("vd_v", &metrics.vd);
    print_extreme("vb_v", &metrics.vb);
    print_extreme("sw_ground_vds_v", &metrics.vds_sw_ground);
    print_extreme("abs_gate_v", &metrics.abs_gate);
    println!("diagnostic_only=no acceptance or qualification verdict is applied");
}

#[cfg(not(test))]
fn main() {
    match analyze(io::BufReader::new(io::stdin().lock())) {
        Ok(metrics) => print_metrics(&metrics),
        Err(error) => {
            eprintln!("REJECTED: {error}");
            std::process::exit(1);
        }
    }
}
