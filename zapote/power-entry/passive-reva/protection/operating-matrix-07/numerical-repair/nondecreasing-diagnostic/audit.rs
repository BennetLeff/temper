#[cfg(not(test))]
use std::io;
use std::io::BufRead;

pub const WIDTH: usize = 31;

#[derive(Clone, Debug, PartialEq)]
pub struct Extreme {
    pub value: f64,
    pub row: u64,
    pub time: f64,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Group {
    pub index: u64,
    pub start_row: u64,
    pub end_row: u64,
    pub rows: u64,
    pub time: f64,
    pub next_dt: f64,
    pub max_delta: f64,
    pub max_delta_col: usize,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Delta {
    pub value: f64,
    pub group_index: u64,
    pub time: f64,
    pub start_row: u64,
    pub end_row: u64,
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct Summary {
    pub headers: Vec<String>,
    pub rows: u64,
    pub equal_groups: u64,
    pub equal_rows: u64,
    pub equal_repeats: u64,
    pub first_equal_time: Option<f64>,
    pub last_equal_time: Option<f64>,
    pub max_group_rows: u64,
    pub max_group: Option<Group>,
    pub first_groups: Vec<Group>,
    pub last_groups: Vec<Group>,
    pub max_equal_delta: [Delta; WIDTH],
    pub min: [Extreme; WIDTH],
    pub max: [Extreme; WIDTH],
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct PartialSummary {
    pub rows: u64,
    pub active_equal_rows: u64,
    pub active_equal_time: Option<f64>,
    pub min: [Extreme; WIDTH],
    pub max: [Extreme; WIDTH],
}

#[cfg_attr(test, allow(dead_code))]
#[derive(Clone, Debug)]
pub struct AuditError(pub String, pub Option<PartialSummary>);

impl std::fmt::Display for AuditError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for AuditError {}

#[derive(Clone)]
struct ActiveGroup {
    time: f64,
    start_row: u64,
    end_row: u64,
    rows: u64,
    last: [f64; WIDTH],
    max_delta: [f64; WIDTH],
}

impl ActiveGroup {
    fn new(row: u64, values: [f64; WIDTH]) -> Self {
        Self {
            time: values[0],
            start_row: row,
            end_row: row,
            rows: 1,
            last: values,
            max_delta: [0.0; WIDTH],
        }
    }

    fn push_equal(&mut self, row: u64, values: [f64; WIDTH]) {
        for (index, value) in values.iter().enumerate() {
            self.max_delta[index] = self.max_delta[index].max((value - self.last[index]).abs());
        }
        self.last = values;
        self.end_row = row;
        self.rows += 1;
    }
}

fn parse_row(line: &str, line_number: usize) -> Result<[f64; WIDTH], AuditError> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    if fields.len() != WIDTH {
        return Err(AuditError(format!(
            "line {line_number}: expected {WIDTH} columns, got {}",
            fields.len()
        ), None));
    }
    let mut row = [0.0; WIDTH];
    for (index, field) in fields.iter().enumerate() {
        row[index] = field.parse::<f64>().map_err(|error| {
            AuditError(format!("line {line_number}, column {index}: invalid number {field:?}: {error}"), None)
        })?;
        if !row[index].is_finite() {
            return Err(AuditError(format!(
                "line {line_number}, column {index}: non-finite value {field}"
            ), None));
        }
    }
    Ok(row)
}

fn partial_error(
    message: String,
    rows: u64,
    active: Option<&ActiveGroup>,
    min: &[Extreme; WIDTH],
    max: &[Extreme; WIDTH],
) -> AuditError {
    AuditError(
        message,
        Some(PartialSummary {
            rows,
            active_equal_rows: active.map_or(0, |group| group.rows),
            active_equal_time: active.map(|group| group.time),
            min: min.clone(),
            max: max.clone(),
        }),
    )
}

fn empty_delta() -> Delta {
    Delta {
        value: 0.0,
        group_index: 0,
        time: 0.0,
        start_row: 0,
        end_row: 0,
    }
}

fn finish_group(
    active: ActiveGroup,
    next_dt: Option<f64>,
    group_index: &mut u64,
    equal_groups: &mut u64,
    equal_rows: &mut u64,
    equal_repeats: &mut u64,
    first_equal_time: &mut Option<f64>,
    last_equal_time: &mut Option<f64>,
    max_group_rows: &mut u64,
    max_group: &mut Option<Group>,
    first_groups: &mut Vec<Group>,
    last_groups: &mut Vec<Group>,
    max_equal_delta: &mut [Delta; WIDTH],
) -> Result<(), AuditError> {
    if active.rows == 1 {
        return Ok(());
    }
    let dt = next_dt.ok_or_else(|| {
        AuditError(format!(
            "equal timestamp group at EOF: time={:.18e}, rows={}, start_row={}, end_row={}",
            active.time, active.rows, active.start_row, active.end_row
        ), None)
    })?;
    if dt <= 0.0 {
        return Err(AuditError(format!(
            "equal timestamp group was not followed by positive progress: time={:.18e}, next_dt={dt:.18e}",
            active.time
        ), None));
    }
    *group_index += 1;
    let index = *group_index;
    *equal_groups += 1;
    *equal_rows += active.rows;
    *equal_repeats += active.rows - 1;
    if first_equal_time.is_none() {
        *first_equal_time = Some(active.time);
    }
    *last_equal_time = Some(active.time);
    let (max_delta, max_delta_col) = active
        .max_delta
        .iter()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(right.1))
        .map(|(index, value)| (*value, index))
        .unwrap_or((0.0, 0));
    let group = Group {
        index,
        start_row: active.start_row,
        end_row: active.end_row,
        rows: active.rows,
        time: active.time,
        next_dt: dt,
        max_delta,
        max_delta_col,
    };
    if active.rows > *max_group_rows {
        *max_group_rows = active.rows;
        *max_group = Some(group.clone());
    }
    if first_groups.len() < 10 {
        first_groups.push(group.clone());
    }
    last_groups.push(group.clone());
    if last_groups.len() > 10 {
        last_groups.remove(0);
    }
    for (column, value) in active.max_delta.iter().enumerate() {
        if *value > max_equal_delta[column].value {
            max_equal_delta[column] = Delta {
                value: *value,
                group_index: index,
                time: active.time,
                start_row: active.start_row,
                end_row: active.end_row,
            };
        }
    }
    Ok(())
}

pub fn audit<R: BufRead>(reader: R) -> Result<Summary, AuditError> {
    let mut lines = reader.lines();
    let header_line = lines
        .next()
        .ok_or_else(|| AuditError("missing 31-column header".to_string(), None))?
        .map_err(|error| AuditError(format!("reading header: {error}"), None))?;
    let headers: Vec<String> = header_line.split_whitespace().map(str::to_string).collect();
    if headers.len() != WIDTH {
        return Err(AuditError(format!(
            "header has {} columns; expected {WIDTH}",
            headers.len()
        ), None));
    }
    if headers[0] != "time" {
        return Err(AuditError(format!("header column 0 must be named time, got {:?}", headers[0]), None));
    }
    let mut unique_headers = std::collections::HashSet::new();
    if headers.iter().any(|header| header.is_empty() || !unique_headers.insert(header)) {
        return Err(AuditError("header column names must be non-empty and unique".to_string(), None));
    }

    let mut rows = 0_u64;
    let mut active: Option<ActiveGroup> = None;
    let mut previous_time = None;
    let mut min = std::array::from_fn(|_| Extreme { value: f64::INFINITY, row: 0, time: 0.0 });
    let mut max = std::array::from_fn(|_| Extreme { value: f64::NEG_INFINITY, row: 0, time: 0.0 });
    let mut equal_groups = 0_u64;
    let mut equal_rows = 0_u64;
    let mut equal_repeats = 0_u64;
    let mut first_equal_time = None;
    let mut last_equal_time = None;
    let mut max_group_rows = 0_u64;
    let mut max_group = None;
    let mut first_groups = Vec::new();
    let mut last_groups = Vec::new();
    let mut group_index = 0_u64;
    let mut max_equal_delta = std::array::from_fn(|_| empty_delta());

    for (line_offset, line) in lines.enumerate() {
        let line_number = line_offset + 2;
        let line = line.map_err(|error| AuditError(format!("reading line {line_number}: {error}"), None))?;
        if line.trim().is_empty() {
            continue;
        }
        let values = match parse_row(&line, line_number) {
            Ok(values) => values,
            Err(error) => {
                return Err(partial_error(error.0, rows, active.as_ref(), &min, &max));
            }
        };
        let row = rows + 1;
        let time = values[0];
        if let Some(old_time) = previous_time {
            if time < old_time {
                return Err(partial_error(
                    format!("backward time at row {row}: {time:.18e} < {old_time:.18e}"),
                    rows,
                    active.as_ref(),
                    &min,
                    &max,
                ));
            }
        }
        for (column, value) in values.iter().enumerate() {
            if *value < min[column].value {
                min[column] = Extreme { value: *value, row, time };
            }
            if *value > max[column].value {
                max[column] = Extreme { value: *value, row, time };
            }
        }

        match active.as_mut() {
            None => active = Some(ActiveGroup::new(row, values)),
            Some(group) if time == group.time => group.push_equal(row, values),
            Some(group) => {
                let old = group.clone();
                finish_group(
                    old,
                    Some(time - group.time),
                    &mut group_index,
                    &mut equal_groups,
                    &mut equal_rows,
                    &mut equal_repeats,
                    &mut first_equal_time,
                    &mut last_equal_time,
                    &mut max_group_rows,
                    &mut max_group,
                    &mut first_groups,
                    &mut last_groups,
                    &mut max_equal_delta,
                )?;
                *group = ActiveGroup::new(row, values);
            }
        }
        previous_time = Some(time);
        rows += 1;
    }
    if let Some(group) = active {
        let group_for_error = group.clone();
        if let Err(error) = finish_group(
            group,
            None,
            &mut group_index,
            &mut equal_groups,
            &mut equal_rows,
            &mut equal_repeats,
            &mut first_equal_time,
            &mut last_equal_time,
            &mut max_group_rows,
            &mut max_group,
            &mut first_groups,
            &mut last_groups,
            &mut max_equal_delta,
        ) {
            return Err(partial_error(error.0, rows, Some(&group_for_error), &min, &max));
        }
    }
    if rows == 0 {
        return Err(AuditError("trace has no data rows".to_string(), None));
    }
    Ok(Summary {
        headers,
        rows,
        equal_groups,
        equal_rows,
        equal_repeats,
        first_equal_time,
        last_equal_time,
        max_group_rows,
        max_group,
        first_groups,
        last_groups,
        max_equal_delta,
        min,
        max,
    })
}

#[cfg_attr(test, allow(dead_code))]
fn print_group(prefix: &str, group: &Group, headers: &[String]) {
    println!(
        "{prefix} group={} time={:.18e} rows={} start_row={} end_row={} next_dt={:.18e} max_delta_col={}({}) max_delta={:.18e}",
        group.index,
        group.time,
        group.rows,
        group.start_row,
        group.end_row,
        group.next_dt,
        group.max_delta_col,
        headers[group.max_delta_col],
        group.max_delta,
    );
}

#[cfg_attr(test, allow(dead_code))]
pub fn print_summary(summary: &Summary) {
    println!("rows={}", summary.rows);
    println!("equal_timestamp_groups={}", summary.equal_groups);
    println!("equal_group_rows={}", summary.equal_rows);
    println!("equal_repeats={}", summary.equal_repeats);
    println!("first_equal_time_s={:?}", summary.first_equal_time);
    println!("last_equal_time_s={:?}", summary.last_equal_time);
    println!("max_equal_group_rows={}", summary.max_group_rows);
    if let Some(group) = &summary.max_group {
        print_group("max_equal_group", group, &summary.headers);
    }
    println!("first_equal_groups:");
    for group in &summary.first_groups {
        print_group("  ", group, &summary.headers);
    }
    println!("last_equal_groups:");
    for group in &summary.last_groups {
        print_group("  ", group, &summary.headers);
    }
    println!("max_adjacent_equal_group_delta_by_column:");
    for column in 0..WIDTH {
        let delta = &summary.max_equal_delta[column];
        println!(
            "  column={} name={} delta={:.18e} group={} time={:.18e} start_row={} end_row={}",
            column,
            summary.headers[column],
            delta.value,
            delta.group_index,
            delta.time,
            delta.start_row,
            delta.end_row,
        );
    }
    println!("per_column_extrema:");
    for column in 0..WIDTH {
        println!(
            "  column={} name={} min={:.18e}@row{}@{:.18e}s max={:.18e}@row{}@{:.18e}s",
            column,
            summary.headers[column],
            summary.min[column].value,
            summary.min[column].row,
            summary.min[column].time,
            summary.max[column].value,
            summary.max[column].row,
            summary.max[column].time,
        );
    }
    println!("diagnostic_only=no acceptance threshold or engineering qualification is applied");
}

#[cfg(not(test))]
fn print_partial(partial: &PartialSummary) {
    eprintln!("partial_rows={}", partial.rows);
    eprintln!("partial_active_equal_rows={}", partial.active_equal_rows);
    eprintln!("partial_active_equal_time_s={:?}", partial.active_equal_time);
    eprintln!("partial_per_column_extrema:");
    for column in 0..WIDTH {
        eprintln!(
            "  column={} min={:.18e}@row{}@{:.18e}s max={:.18e}@row{}@{:.18e}s",
            column,
            partial.min[column].value,
            partial.min[column].row,
            partial.min[column].time,
            partial.max[column].value,
            partial.max[column].row,
            partial.max[column].time,
        );
    }
}

#[cfg(not(test))]
fn main() {
    let result = audit(io::BufReader::new(io::stdin().lock()));
    match result {
        Ok(summary) => print_summary(&summary),
        Err(error) => {
            eprintln!("REJECTED: {error}");
            if let Some(partial) = error.1.as_ref() {
                print_partial(partial);
            }
            std::process::exit(1);
        }
    }
}
