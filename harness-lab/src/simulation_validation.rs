//! Measurements from retained ngspice ASCII rawfiles. No submitted scores are trusted.
use anyhow::{bail, ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};

const REQUIRED: [&str; 3] = ["startup", "input_variation", "load_variation"];
const STARTUP_LOAD_COMPLIANCE_V: f64 = 0.1;
const REQUIRED_LOAD_PROFILES: [&str; 2] = ["continuous_50mA_to_500mA", "pulse_50mA_to_1A"];
const LOAD_SLEW_A_PER_S: f64 = 100_000.0;
const LOAD_SLEW_FRACTION: f64 = 0.10;
const LOAD_PLATEAU_TOLERANCE: f64 = 0.02;
const EDGE_WINDOW_S: f64 = 0.001;

#[derive(Debug)]
struct AcceptanceFailure(&'static str);

impl std::fmt::Display for AcceptanceFailure {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.0)
    }
}

impl std::error::Error for AcceptanceFailure {}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(v: &Value) -> bool {
    v.as_str()
        .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn number(v: &Value, key: &str) -> Result<f64> {
    let n = v[key]
        .as_f64()
        .with_context(|| format!("missing numeric {key}"))?;
    ensure!(n.is_finite(), "nonfinite {key}");
    Ok(n)
}

fn interpolate(times: &[f64], values: &[f64], at: f64) -> Result<f64> {
    ensure!(
        at >= times[0] && at <= *times.last().unwrap(),
        "time outside waveform"
    );
    let i = times.partition_point(|t| *t < at);
    if i == 0 {
        return Ok(values[0]);
    }
    if i == times.len() {
        return Ok(*values.last().unwrap());
    }
    let fraction = (at - times[i - 1]) / (times[i] - times[i - 1]);
    Ok(values[i - 1] + fraction * (values[i] - values[i - 1]))
}

fn mean_window(times: &[f64], values: &[f64], start: f64, end: f64) -> Result<f64> {
    ensure!(end > start, "reversed measurement window");
    ensure!(
        start >= times[0] && end <= *times.last().unwrap(),
        "incomplete measurement window"
    );
    let mut area = 0.0;
    for i in 1..times.len() {
        let left = times[i - 1].max(start);
        let right = times[i].min(end);
        if right <= left {
            continue;
        }
        let slope = (values[i] - values[i - 1]) / (times[i] - times[i - 1]);
        let a = values[i - 1] + slope * (left - times[i - 1]);
        let b = values[i - 1] + slope * (right - times[i - 1]);
        area += (a + b) * 0.5 * (right - left);
    }
    Ok(area / (end - start))
}

fn within_band(
    times: &[f64],
    values: &[f64],
    start: f64,
    end: f64,
    target: f64,
    tolerance: f64,
) -> Result<()> {
    ensure!(end >= start, "reversed hold window");
    for value in [
        interpolate(times, values, start)?,
        interpolate(times, values, end)?,
    ] {
        ensure!(
            (value - target).abs() <= tolerance + 1e-12,
            "hold boundary outside tolerance"
        );
    }
    ensure!(
        times
            .iter()
            .zip(values)
            .filter(|(t, _)| **t >= start && **t <= end)
            .all(|(_, value)| (*value - target).abs() <= tolerance + 1e-12),
        "hold waveform outside tolerance"
    );
    Ok(())
}

fn protocol_number(value: &Value, key: &str) -> Result<f64> {
    let n = number(value, key)?;
    ensure!(n >= 0.0, "negative protocol value {key}");
    Ok(n)
}

fn validate_load_protocol(spec: &Value, wave: &Waveform, measured: &mut Value) -> Result<()> {
    let edges = spec["edges"]
        .as_array()
        .context("load edge schedule missing")?;
    ensure!(
        edges.len() == 6,
        "exactly three pulses require six load edges"
    );
    let low = number(spec, "load_low_a")?;
    let high = number(spec, "load_high_a")?;
    let capture_end = number(spec, "capture_end_s")?;
    let vin_corner = number(spec, "vin_corner_v")?;
    let actual_vin = mean_window(
        &wave.time,
        &wave.signals["v(in)"],
        wave.time[0],
        capture_end,
    )?;
    ensure!(
        (actual_vin - vin_corner).abs() <= 0.02 * vin_corner,
        "measured VIN does not match declared corner"
    );
    ensure!(
        *wave.time.last().unwrap() >= capture_end - 1e-12,
        "capture does not cover declared end"
    );
    let load = wave
        .signals
        .get("i(load)")
        .context("load waveform signal missing")?;
    let first_start = protocol_number(&edges[0], "start_s")?;
    let last_end = protocol_number(&edges[5], "end_s")?;
    ensure!(
        first_start - wave.time[0] >= 0.100 - 1e-9,
        "missing initial 100 ms low plateau"
    );
    ensure!(
        capture_end - last_end >= 0.100 - 1e-9,
        "missing final 100 ms low plateau"
    );
    within_band(
        &wave.time,
        load,
        first_start - 0.100,
        first_start,
        low,
        LOAD_PLATEAU_TOLERANCE * low,
    )?;
    within_band(
        &wave.time,
        &wave.signals["v(in)"],
        wave.time[0],
        capture_end,
        vin_corner,
        vin_corner * 0.02,
    )?;
    let mut edge_records = Vec::new();
    let mut rising_starts = Vec::new();
    for (index, edge) in edges.iter().enumerate() {
        let start = protocol_number(edge, "start_s")?;
        let end = protocol_number(edge, "end_s")?;
        let from = number(edge, "from_a")?;
        let to = number(edge, "to_a")?;
        let direction = edge["direction"]
            .as_str()
            .context("load edge direction missing")?;
        ensure!(
            direction == if index % 2 == 0 { "rising" } else { "falling" },
            "load edges must alternate rising and falling"
        );
        ensure!(
            end > start && (end - start) > 0.0,
            "invalid load edge interval"
        );
        ensure!(
            from == if direction == "rising" { low } else { high },
            "load edge start endpoint mismatch"
        );
        ensure!(
            to == if direction == "rising" { high } else { low },
            "load edge end endpoint mismatch"
        );
        let actual_from = interpolate(&wave.time, load, start)?;
        let actual_to = interpolate(&wave.time, load, end)?;
        ensure!(
            (actual_from - from).abs() <= LOAD_PLATEAU_TOLERANCE * from.abs().max(1e-9),
            "actual load edge start mismatch"
        );
        ensure!(
            (actual_to - to).abs() <= LOAD_PLATEAU_TOLERANCE * to.abs().max(1e-9),
            "actual load edge end mismatch"
        );
        let expected_slew = (to - from).abs() / (end - start);
        let actual_slew = (actual_to - actual_from).abs() / (end - start);
        ensure!(
            (direction == "rising" && actual_to > actual_from)
                || (direction == "falling" && actual_to < actual_from),
            "declared edge direction disagrees with measured load"
        );
        ensure!(
            (actual_slew - LOAD_SLEW_A_PER_S).abs() <= LOAD_SLEW_A_PER_S * LOAD_SLEW_FRACTION,
            "load edge slew outside 0.1 A/us +/-10%"
        );
        ensure!(
            (expected_slew - LOAD_SLEW_A_PER_S).abs() <= LOAD_SLEW_A_PER_S * LOAD_SLEW_FRACTION,
            "declared load edge slew outside 0.1 A/us +/-10%"
        );
        if direction == "rising" {
            rising_starts.push(start);
        } else {
            ensure!(direction == "falling", "unknown load edge direction");
        }
        let pre = mean_window(
            &wave.time,
            &wave.signals["v(out)"],
            start - EDGE_WINDOW_S,
            start,
        )?;
        let post = mean_window(
            &wave.time,
            &wave.signals["v(out)"],
            end,
            end + EDGE_WINDOW_S,
        )?;
        ensure!(
            (3.135..=3.465).contains(&pre) && (3.135..=3.465).contains(&post),
            "per-edge output mean outside 3.135..3.465 V"
        );
        let next = edges
            .get(index + 1)
            .and_then(|e| e["start_s"].as_f64())
            .unwrap_or(capture_end);
        ensure!(
            next >= end + EDGE_WINDOW_S,
            "load edge lacks post-edge observation window"
        );
        within_band(&wave.time, load, end, next, to, LOAD_PLATEAU_TOLERANCE * to)?;
        let final_mean = mean_window(
            &wave.time,
            &wave.signals["v(out)"],
            (next - EDGE_WINDOW_S).max(end),
            next,
        )?;
        within_band(
            &wave.time,
            &wave.signals["v(out)"],
            start - EDGE_WINDOW_S,
            start,
            pre,
            0.01 * pre,
        )?;
        within_band(
            &wave.time,
            &wave.signals["v(out)"],
            next - EDGE_WINDOW_S,
            next,
            final_mean,
            0.01 * final_mean,
        )?;
        within_band(
            &wave.time,
            &wave.signals["v(out)"],
            end + 0.001,
            next,
            final_mean,
            0.01 * final_mean,
        )
        .map_err(|_| AcceptanceFailure("load edge did not remain recovered within 1 ms"))?;
        let mut max_departure: f64 = 0.0;
        for (i, _t) in wave
            .time
            .iter()
            .enumerate()
            .filter(|(_, t)| **t >= start && **t <= next)
        {
            max_departure = max_departure.max((wave.signals["v(out)"][i] - pre).abs());
            ensure!(
                wave.signals["v(out)"][i] >= 3.135 && wave.signals["v(out)"][i] <= 3.465,
                AcceptanceFailure("post-edge output outside absolute regulation bounds")
            );
        }
        ensure!(
            max_departure <= 0.100,
            AcceptanceFailure("load edge departure exceeds 100 mV")
        );
        for (i, _t) in wave
            .time
            .iter()
            .enumerate()
            .filter(|(_, t)| **t >= end + 0.001 && **t <= next)
        {
            ensure!(
                (wave.signals["v(out)"][i] - final_mean).abs() <= 0.01 * final_mean.abs(),
                AcceptanceFailure("load edge did not remain recovered within 1 ms")
            );
        }
        edge_records.push(json!({"index":index,"direction":direction,"start_s":start,"end_s":end,"load_from_a":actual_from,"load_to_a":actual_to,"slew_a_per_s":actual_slew,"vout_pre_v":pre,"vout_post_v":post,"vout_final_v":final_mean,"max_departure_v":max_departure}));
    }
    ensure!(
        rising_starts.len() == 3,
        "three rising pulse starts are required"
    );
    for pulse in 0..3 {
        let rising = protocol_number(&edges[pulse * 2], "start_s")?;
        let falling = protocol_number(&edges[pulse * 2 + 1], "start_s")?;
        ensure!(
            (falling - rising - 0.010).abs() <= 2.0e-6,
            "each pulse must hold its high plateau for 10 ms"
        );
    }
    for pair in rising_starts.windows(2) {
        ensure!(
            pair[1] - pair[0] >= 0.100 - 1e-9,
            "pulse starts must be at least 100 ms apart"
        );
    }
    measured["edges"] = json!(edge_records);
    Ok(())
}

fn validate_startup_protocol(spec: &Value, wave: &Waveform, measured: &mut Value) -> Result<()> {
    ensure!(
        spec["en_tied_to_vin"] == true,
        "startup requires EN tied to VIN"
    );
    let ramp_start = protocol_number(spec, "vin_ramp_start_s")?;
    let ramp_end = protocol_number(spec, "vin_ramp_end_s")?;
    let target_vin = number(spec, "vin_corner_v")?;
    ensure!(
        (ramp_end - ramp_start - 0.001).abs() <= 1e-9,
        "VIN ramp must last exactly 1 ms"
    );
    let vin = &wave.signals["v(in)"];
    let out = &wave.signals["v(out)"];
    let crossing = number(spec, "vin_crossing_v")?;
    ensure!(
        (crossing - 13.5).abs() <= 1e-12,
        "startup reference crossing must be 13.5 V"
    );
    let cross_time = wave
        .time
        .iter()
        .zip(vin)
        .position(|(_, v)| *v >= crossing)
        .map(|i| wave.time[i])
        .context("VIN crossing not observed")?;
    ensure!(vin[0].abs() <= 0.05, "startup VIN must begin discharged");
    ensure!(out[0].abs() <= 0.05, "startup VOUT must begin discharged");
    ensure!(wave.time[0] <= ramp_start, "startup misses ramp beginning");
    within_band(&wave.time, vin, wave.time[0], ramp_start, 0.0, 0.05)?;
    within_band(&wave.time, out, wave.time[0], ramp_start, 0.0, 0.05)?;
    for (time, value) in wave
        .time
        .iter()
        .zip(vin)
        .filter(|(t, _)| **t >= ramp_start && **t <= ramp_end)
    {
        let expected = target_vin * (*time - ramp_start) / (ramp_end - ramp_start);
        ensure!(
            (*value - expected).abs() <= 0.02 * target_vin,
            "startup VIN does not follow the declared linear ramp"
        );
    }
    ensure!(
        vin.windows(2).all(|w| w[1] + 1e-9 >= w[0]),
        "startup VIN ramp is not monotonic"
    );
    ensure!(
        (cross_time - number(spec, "expected_crossing_s")?).abs()
            <= 2.0 * number(spec, "max_step_s")?,
        "VIN corner crossing timing mismatch"
    );
    ensure!(
        (interpolate(&wave.time, vin, ramp_end)? - target_vin).abs() <= 0.02 * target_vin,
        "VIN ramp target mismatch"
    );
    let capture_end = number(spec, "capture_end_s")?;
    within_band(
        &wave.time,
        vin,
        ramp_end,
        capture_end,
        target_vin,
        0.02 * target_vin,
    )?;
    let load = wave
        .signals
        .get("i(load)")
        .context("startup load waveform signal missing")?;
    let actual_load = mean_window(&wave.time, load, cross_time + 0.015, cross_time + 0.020)?;
    let requested_load = number(spec, "load_a")?;
    let load_tolerance = 0.02 * requested_load.max(0.05);
    for (time, (output, actual)) in wave.time.iter().zip(out.iter().zip(load)) {
        if *time < ramp_start || *time > capture_end {
            continue;
        }
        let expected = requested_load * (*output / STARTUP_LOAD_COMPLIANCE_V).clamp(0.0, 1.0);
        ensure!(
            (*actual - expected).abs() <= load_tolerance,
            "startup load does not follow the voltage-compliant load law"
        );
    }
    ensure!(
        (actual_load - requested_load).abs() <= 0.02 * requested_load.max(0.05),
        "startup load does not match declared operating point"
    );
    let final_mean = mean_window(&wave.time, out, cross_time + 0.015, cross_time + 0.020)?;
    ensure!(
        (3.135..=3.465).contains(&final_mean),
        AcceptanceFailure("startup final output outside regulation bounds")
    );
    let (mut t10, mut t90) = (None, None);
    for (i, value) in out
        .iter()
        .enumerate()
        .filter(|(i, _)| wave.time[*i] >= ramp_start && wave.time[*i] <= cross_time + 0.020)
    {
        if *value >= 0.1 * final_mean && t10.is_none() {
            t10 = Some(wave.time[i]);
        }
        if *value >= 0.9 * final_mean && t90.is_none() {
            t90 = Some(wave.time[i]);
        }
    }
    let rise = t90.context("startup 90% crossing missing")?
        - t10.context("startup 10% crossing missing")?;
    let max_out = out
        .iter()
        .zip(&wave.time)
        .filter(|(_, t)| **t <= cross_time + 0.020)
        .map(|(v, _)| *v)
        .fold(f64::NEG_INFINITY, f64::max);
    ensure!(
        rise <= 0.008,
        AcceptanceFailure("startup 10-90 rise time exceeds 8 ms")
    );
    ensure!(
        max_out - final_mean <= 0.100 && max_out <= 3.465,
        AcceptanceFailure("startup overshoot exceeds 100 mV or absolute bound")
    );
    for (i, _t) in wave
        .time
        .iter()
        .enumerate()
        .filter(|(_, t)| **t >= cross_time + 0.010 && **t <= cross_time + 0.020)
    {
        ensure!(
            (out[i] - final_mean).abs() <= 0.01 * final_mean.abs(),
            AcceptanceFailure("startup did not settle within 1% by 10 ms")
        );
    }
    ensure!(
        capture_end >= cross_time + 0.020,
        "startup capture must include 20 ms post-crossing"
    );
    measured["startup_final_v"] = json!(final_mean);
    measured["startup_rise_s"] = json!(rise);
    measured["startup_crossing_s"] = json!(cross_time);
    measured["startup_max_v"] = json!(max_out);
    Ok(())
}

struct Waveform {
    time: Vec<f64>,
    signals: BTreeMap<String, Vec<f64>>,
}
fn parse_raw(text: &str) -> Result<Waveform> {
    ensure!(text.len() <= 32 * 1024 * 1024, "rawfile exceeds limit");
    let (header, body) = text
        .split_once("Values:\n")
        .context("ASCII Values section missing")?;
    ensure!(
        header.lines().any(|l| l.trim() == "Flags: real"),
        "only real rawfiles supported"
    );
    let count = |key: &str| -> Result<usize> {
        header
            .lines()
            .find_map(|l| l.strip_prefix(key))
            .context("rawfile header count missing")?
            .trim()
            .parse()
            .context("invalid rawfile count")
    };
    let nv = count("No. Variables:")?;
    let np = count("No. Points:")?;
    ensure!(
        (4..=64).contains(&nv) && (3..=1_000_000).contains(&np),
        "unsupported waveform dimensions"
    );
    let variables = header
        .split_once("Variables:\n")
        .context("Variables section missing")?
        .1;
    let mut names = Vec::new();
    for (index, line) in variables
        .lines()
        .filter(|l| !l.trim().is_empty())
        .enumerate()
    {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(
            fields.len() == 3 && fields[0].parse::<usize>()? == index,
            "malformed variable index"
        );
        let name = fields[1].to_ascii_lowercase();
        let unit = match name.as_str() {
            "time" => "time",
            n if n.starts_with("v(") => "voltage",
            n if n.starts_with("i(") => "current",
            _ => bail!("unsupported variable name"),
        };
        ensure!(
            fields[2] == unit && !names.contains(&name),
            "wrong units or duplicate signal"
        );
        names.push(name);
    }
    ensure!(
        names.len() == nv && names[0] == "time",
        "variable census mismatch"
    );
    let tokens: Vec<_> = body.split_whitespace().collect();
    ensure!(
        tokens.len() == np * (nv + 1),
        "truncated or extra waveform data"
    );
    let mut columns = vec![Vec::with_capacity(np); nv];
    for (index, row) in tokens.chunks_exact(nv + 1).enumerate() {
        ensure!(row[0].parse::<usize>()? == index, "wrong sample index");
        for (col, token) in columns.iter_mut().zip(&row[1..]) {
            let value: f64 = token.parse()?;
            ensure!(value.is_finite(), "nonfinite waveform");
            col.push(value);
        }
    }
    let time = columns[0].clone();
    ensure!(
        time[0] >= 0.0 && time.windows(2).all(|w| w[1] > w[0]),
        "invalid timebase"
    );
    let signals = names.into_iter().zip(columns).collect::<BTreeMap<_, _>>();
    for name in ["v(out)", "v(in)", "i(vin)"] {
        ensure!(signals.contains_key(name), "missing signal {name}");
    }
    Ok(Waveform { time, signals })
}

const BINARY_MAX_BYTES: u64 = 8 * 1024 * 1024 * 1024;
const BINARY_MAX_ROWS: usize = 100_000_000;
const BINARY_MAX_COLUMNS: usize = 1024;

fn parse_binary(root: &Path, relative: &str, expected_hash: &str) -> Result<Waveform> {
    let relative_path = Path::new(relative);
    ensure!(
        !relative_path.is_absolute()
            && !relative_path
                .components()
                .any(|c| c == std::path::Component::ParentDir),
        "binary waveform path must be relative and contained"
    );
    let root = root
        .canonicalize()
        .context("binary waveform root missing")?;
    let path = root.join(relative_path);
    let canonical = path.canonicalize().context("binary waveform missing")?;
    canonical
        .strip_prefix(&root)
        .context("binary waveform escapes root")?;
    let file = File::open(&canonical)?;
    let metadata = file.metadata()?;
    ensure!(metadata.is_file(), "binary waveform is not a file");
    ensure!(
        metadata.len() <= BINARY_MAX_BYTES,
        "binary waveform exceeds byte limit"
    );
    let mut reader = BufReader::new(file);
    let mut header_bytes = Vec::new();
    let marker = b"Binary:\n";
    loop {
        ensure!(
            header_bytes.len() <= 64 * 1024,
            "binary header exceeds limit"
        );
        let mut byte = [0u8; 1];
        reader
            .read_exact(&mut byte)
            .context("binary marker missing")?;
        header_bytes.push(byte[0]);
        if header_bytes.ends_with(marker) {
            break;
        }
    }
    let header_len = header_bytes.len() - marker.len();
    let header =
        std::str::from_utf8(&header_bytes[..header_len]).context("binary header is not UTF-8")?;
    ensure!(
        header.lines().any(|line| line.trim() == "Flags: real"),
        "only real rawfiles supported"
    );
    let field = |prefix: &str| -> Result<usize> {
        header
            .lines()
            .find_map(|line| line.strip_prefix(prefix))
            .context("binary header count missing")?
            .trim()
            .parse()
            .context("invalid binary header count")
    };
    let columns = field("No. Variables:")?;
    let rows = field("No. Points:")?;
    ensure!(
        columns > 0 && columns <= BINARY_MAX_COLUMNS && (3..=BINARY_MAX_ROWS).contains(&rows),
        "unsupported binary dimensions"
    );
    let vars = header
        .split_once("Variables:\n")
        .context("binary variables section missing")?
        .1;
    let mut names = Vec::with_capacity(columns);
    for (index, line) in vars
        .lines()
        .filter(|line| !line.trim().is_empty())
        .enumerate()
    {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(
            fields.len() == 3 && fields[0].parse::<usize>()? == index,
            "malformed binary variable index"
        );
        let name = fields[1].to_ascii_lowercase();
        let unit = if name == "time" {
            "time"
        } else if name.starts_with("v(") {
            "voltage"
        } else if name.starts_with("i(") {
            "current"
        } else {
            bail!("unsupported variable name")
        };
        ensure!(
            fields[2] == unit && !names.contains(&name),
            "wrong binary units or duplicate signal"
        );
        names.push(name);
    }
    ensure!(
        names.len() == columns && names[0] == "time",
        "binary variable census mismatch"
    );
    let expected_len = rows
        .checked_mul(columns)
        .and_then(|n| n.checked_mul(8))
        .context("binary waveform size overflow")?;
    ensure!(
        header_bytes.len() as u64 + expected_len as u64 == metadata.len(),
        "truncated or extra binary waveform data"
    );
    let mut digest = Sha256::new();
    digest.update(&header_bytes);
    let row_bytes = columns.checked_mul(8).context("binary row size overflow")?;
    let mut row = Vec::new();
    row.try_reserve_exact(row_bytes)
        .context("binary row allocation exceeds limit")?;
    row.resize(row_bytes, 0);
    let mut retained = BTreeMap::new();
    let selected: Vec<_> = ["time", "v(out)", "v(in)", "i(vin)", "i(load)"]
        .iter()
        .filter_map(|required| {
            names
                .iter()
                .position(|name| name == required)
                .map(|index| (*required, index))
        })
        .collect();
    for (required, _) in &selected {
        {
            let mut values = Vec::new();
            values
                .try_reserve_exact(rows)
                .context("binary waveform allocation exceeds limit")?;
            retained.insert(required.to_string(), values);
        }
    }
    for _ in 0..rows {
        reader
            .read_exact(&mut row)
            .context("truncated binary waveform data")?;
        digest.update(&row);
        for index in 0..columns {
            let offset = index * 8;
            let value = f64::from_le_bytes(
                row[offset..offset + 8]
                    .try_into()
                    .context("invalid binary sample")?,
            );
            ensure!(value.is_finite(), "nonfinite binary waveform");
        }
        for (required, index) in &selected {
            let offset = index * 8;
            let value = f64::from_le_bytes(
                row[offset..offset + 8]
                    .try_into()
                    .context("invalid binary sample")?,
            );
            ensure!(value.is_finite(), "nonfinite binary waveform");
            retained
                .get_mut(*required)
                .context("missing retained binary signal")?
                .push(value);
        }
    }
    ensure!(
        reader.read(&mut [0u8; 1])? == 0,
        "trailing binary waveform data"
    );
    ensure!(
        format!("{:x}", digest.finalize()) == expected_hash,
        "waveform hash mismatch"
    );
    for required in ["time", "v(out)", "v(in)", "i(vin)"] {
        ensure!(retained.contains_key(required), "missing signal {required}");
    }
    let time = retained
        .remove("time")
        .context("missing retained time signal")?;
    ensure!(
        time[0] >= 0.0 && time.windows(2).all(|window| window[1] > window[0]),
        "invalid binary timebase"
    );
    Ok(Waveform {
        time,
        signals: retained,
    })
}

fn measure(scenario: &Value) -> Result<Value> {
    let format = match scenario.get("raw_format") {
        None => "ascii",
        Some(value) => value.as_str().context("waveform format must be a string")?,
    };
    ensure!(
        scenario["spec"]["raw_format"].as_str().unwrap_or("ascii") == format,
        "waveform format is not bound to scenario spec"
    );
    ensure!(
        format == "ascii" || format == "ngspice-binary-le64",
        "unsupported waveform format"
    );
    ensure!(
        !(scenario.get("raw_waveform").is_some() && scenario.get("raw_file").is_some()),
        "dual waveform inputs are forbidden"
    );
    let wave = if format == "ngspice-binary-le64" {
        ensure!(
            scenario.get("raw_waveform").is_none(),
            "binary waveform cannot embed ASCII data"
        );
        let root = PathBuf::from(
            std::env::var("TEMPER_SIMULATION_RAW_ROOT")
                .context("binary waveform root unavailable")?,
        );
        parse_binary(
            &root,
            scenario["raw_file"]
                .as_str()
                .context("binary waveform path missing")?,
            scenario["artifact_sha256"]
                .as_str()
                .context("binary waveform hash missing")?,
        )?
    } else {
        ensure!(
            scenario.get("raw_file").is_none(),
            "ASCII waveform cannot name a binary file"
        );
        let text = scenario["raw_waveform"]
            .as_str()
            .context("raw waveform missing")?;
        ensure!(
            scenario["artifact_sha256"] == hash(text.as_bytes()),
            "waveform hash mismatch"
        );
        parse_raw(text)?
    };
    let spec = &scenario["spec"];
    let start = number(spec, "window_start_s")?;
    let end = number(spec, "window_end_s")?;
    let step = number(spec, "max_step_s")?;
    let target = number(spec, "target_v")?;
    let band = number(spec, "settling_band_v")?;
    let event = number(spec, "event_s")?;
    ensure!(
        start >= 0.0
            && end > start
            && step > 0.0
            && target > 0.0
            && band > 0.0
            && event >= 0.0
            && event < end,
        "invalid scenario settings"
    );
    ensure!(
        wave.time[0] <= event && wave.time[0] <= start && *wave.time.last().unwrap() >= end,
        "truncated time coverage"
    );
    ensure!(
        wave.time
            .windows(2)
            .all(|w| w[1] - w[0] <= step * (1.0 + 1e-9)),
        "under-resolved waveform"
    );
    let times = &wave.time;
    let output = &wave.signals["v(out)"];
    let indexes: Vec<_> = times
        .iter()
        .enumerate()
        .filter_map(|(i, t)| (*t >= start && *t <= end).then_some(i))
        .collect();
    ensure!(indexes.len() >= 3, "too few window samples");
    let extrema = |signal: &[f64]| -> (f64, f64) {
        indexes
            .iter()
            .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), i| {
                (lo.min(signal[*i]), hi.max(signal[*i]))
            })
    };
    let average = |signal: &[f64]| -> f64 {
        let mut area = 0.0;
        for i in 1..times.len() {
            let left = times[i - 1].max(start);
            let right = times[i].min(end);
            if right <= left {
                continue;
            }
            let slope = (signal[i] - signal[i - 1]) / (times[i] - times[i - 1]);
            let a = signal[i - 1] + slope * (left - times[i - 1]);
            let b = signal[i - 1] + slope * (right - times[i - 1]);
            area += (a + b) * 0.5 * (right - left);
        }
        area / (end - start)
    };
    let (lo, hi) = extrema(output);
    let last_outside = times
        .iter()
        .enumerate()
        .filter(|(i, t)| **t >= event && **t <= end && (output[*i] - target).abs() > band)
        .map(|(i, _)| i)
        .next_back();
    let settling = match last_outside {
        None => 0.0,
        Some(i) => {
            *times
                .get(i + 1)
                .filter(|t| **t <= end)
                .context("output never settled")?
                - event
        }
    };
    let (vin_lo, vin_hi) = extrema(&wave.signals["v(in)"]);
    let mut measured = json!({"vout_avg":average(output),"vout_min":lo,"vout_max":hi,"vout_pp":hi-lo,
        "vin_avg":average(&wave.signals["v(in)"]),"iin_avg":average(&wave.signals["i(vin)"]),
        "vin_span":vin_hi-vin_lo,"overshoot_v":(hi-target).max(0.0),"undershoot_v":(target-lo).max(0.0),
        "settling_s":settling,"duration_s":end-start});
    if let Some(load) = wave.signals.get("i(load)") {
        let (a, b) = extrema(load);
        measured["load_span"] = json!(b - a);
        measured["load_min"] = json!(a);
        measured["load_max"] = json!(b);
    }
    let limits = spec["limits"]
        .as_object()
        .context("frozen limits missing")?;
    for key in ["vout_avg", "vout_pp", "overshoot_v", "settling_s"] {
        ensure!(limits.contains_key(key), "mandatory limit {key} missing");
    }
    let name = scenario["name"].as_str().context("scenario name missing")?;
    if name == "input_variation" {
        ensure!(
            limits
                .get("vin_span")
                .and_then(|v| v["min"].as_f64())
                .is_some_and(|v| v > 0.0),
            "input excitation limit missing"
        );
    }
    if name == "load_variation" {
        ensure!(
            limits
                .get("load_span")
                .and_then(|v| v["min"].as_f64())
                .is_some_and(|v| v > 0.0),
            "load excitation limit missing"
        );
        scenario["spec"]["profile_id"]
            .as_str()
            .context("load profile missing")?;
        let low_a = number(spec, "load_low_a")?;
        let high_a = number(spec, "load_high_a")?;
        let tolerance = number(spec, "load_tolerance_fraction")?;
        ensure!(
            (0.0..=0.02).contains(&tolerance),
            "load endpoint tolerance must be between zero and the adopted 2% maximum"
        );
        ensure!(
            low_a >= 0.0 && high_a > low_a,
            "load profile high current must exceed low current"
        );
        let load_min = measured["load_min"]
            .as_f64()
            .context("load waveform signal missing")?;
        let load_max = measured["load_max"]
            .as_f64()
            .context("load waveform signal missing")?;
        ensure!(
            (load_min - low_a).abs() <= tolerance * low_a,
            "load waveform low endpoint mismatch"
        );
        ensure!(
            (load_max - high_a).abs() <= tolerance * high_a,
            "load waveform high endpoint mismatch"
        );
        if spec.get("edges").is_some() {
            validate_load_protocol(spec, &wave, &mut measured)?;
        }
    } else if name == "startup" && spec.get("en_tied_to_vin").is_some() {
        validate_startup_protocol(spec, &wave, &mut measured)?;
    }
    let mut violations = Vec::new();
    for (key, limit) in limits {
        let value = measured[key]
            .as_f64()
            .with_context(|| format!("unsupported measurement {key}"))?;
        let min = number(limit, "min")?;
        let max = number(limit, "max")?;
        ensure!(min <= max, "reversed measurement limits");
        if value < min || value > max {
            violations.push(json!({"id":"measurement_out_of_limit","measurement":key,"actual":value,"min":min,"max":max}));
        }
    }
    Ok(
        json!({"name":name,"status":if violations.is_empty(){"pass"}else{"fail"},"measurements":measured,"findings":violations}),
    )
}

pub fn evaluate(input: Value) -> Result<Value> {
    ensure!(
        input["profile"] == "engineering-simulation",
        "unexpected simulation profile"
    );
    let mut findings = Vec::new();
    let mut block = |id: &str, message: &str| findings.push(json!({"id":id,"message":message}));
    let model = &input["model"];
    if model["mpn"] != "LMR51430XDDCR"
        || model["reference_voltage"] != json!(0.6)
        || model["frequency_hz"] != json!(500000)
        || model["mode"] != "PFM"
    {
        block(
            "exact_model_missing",
            "exact LMR51430XDDCR 500 kHz PFM, 0.6 V model identity is required",
        );
    }
    if model["legacy_negative_control"] == true || model["reference_voltage"] == json!(0.8) {
        block(
            "legacy_model_rejected",
            "legacy averaged 0.8 V model is inadmissible",
        );
    }
    let q = &model["qualification"];
    if !crate::qualification::approved("model", q) {
        block(
            "qualification_not_approved",
            "exact model receipt is absent from the trusted approval registry",
        );
    }
    if !digest(&model["sha256"])
        || q["model_sha256"] != model["sha256"]
        || !digest(&q["evidence_sha256"])
        || q["source"].as_str().is_none_or(str::is_empty)
        || q["license"].as_str().is_none_or(str::is_empty)
        || q["reviewed_by"].as_str().is_none_or(str::is_empty)
        || q["status"] != "pass"
        || input["qualification_verified"] != true
    {
        block(
            "model_not_qualified",
            "reviewed independent qualification evidence bound to the exact model is required",
        );
    }
    for behavior in REQUIRED {
        if !q["coverage"]
            .as_array()
            .is_some_and(|a| a.iter().any(|v| v == behavior))
        {
            block("unsupported_coverage", behavior);
        }
    }
    if input["synthetic"] == true || model["synthetic"] == true {
        block(
            "synthetic_evidence",
            "synthetic controls cannot qualify a live circuit",
        );
    }
    for key in ["circuit_sha256", "requirements_sha256", "settings_sha256"] {
        if !digest(&input[key]) {
            block("identity_missing", key);
        }
    }
    if input["reuse"]["requested"] == true {
        let prior = &input["reuse"]["prior_identity"];
        let current = &input["reuse"]["current_identity"];
        for key in [
            "circuit_sha256",
            "requirements_sha256",
            "settings_sha256",
            "model_sha256",
        ] {
            if !digest(&current[key]) || current[key] != prior[key] {
                block("stale_reuse", key);
            }
        }
        if input["reuse"]["parasitic"] == true
            && (!digest(&current["board_sha256"])
                || current["board_sha256"] != prior["board_sha256"])
        {
            block("stale_parasitics", "board changed since extraction");
        }
    }
    let scenarios = input["scenarios"].as_array().cloned().unwrap_or_default();
    let requirements_text = input["requirements_manifest"].as_str();
    let requirements = requirements_text
        .and_then(|text| {
            (hash(text.as_bytes()) == input["requirements_sha256"])
                .then(|| serde_json::from_str::<Value>(text).ok())
        })
        .flatten();
    if requirements_text.is_none() {
        findings.push(json!({"id":"requirements_manifest_missing","message":"requirements manifest is required"}));
    } else if requirements.is_none() {
        findings.push(json!({"id":"requirements_manifest_invalid","message":"requirements manifest hash or JSON is invalid"}));
    }
    let required_profiles = requirements
        .as_ref()
        .and_then(|manifest| manifest["requirements"].as_array())
        .and_then(|items| {
            let mut matches = items
                .iter()
                .filter(|item| item["id"] == "load_step_endpoints");
            let item = matches.next()?;
            if matches.next().is_some() {
                return None;
            }
            item["profiles"].as_array()
        });
    let mut profile_requirements = BTreeMap::new();
    match required_profiles {
        Some(profiles) => {
            for profile in profiles {
                let id = profile["id"].as_str().unwrap_or("").to_owned();
                let valid = match (profile["low_a"].as_f64(), profile["high_a"].as_f64()) {
                    (Some(low), Some(high)) if !id.is_empty() && low.is_finite()
                        && high.is_finite() && low >= 0.0 && high > low => {
                        profile_requirements.insert(id.clone(), (low, high)).is_none()
                    }
                    _ => false,
                };
                if !valid {
                    findings.push(json!({"id":"load_profile_invalid","message":id}));
                }
            }
            for id in REQUIRED_LOAD_PROFILES {
                if !profile_requirements.contains_key(id) {
                    findings.push(json!({"id":"load_profile_requirement_missing","message":id}));
                }
            }
            if profile_requirements.len() != REQUIRED_LOAD_PROFILES.len() {
                findings.push(json!({"id":"load_profile_requirements_invalid","message":"exactly two required load profiles are needed"}));
            }
        }
        None => findings.push(json!({"id":"load_profile_requirements_missing","message":"requirements-bound load profiles are required"})),
    }
    let protocol_required = requirements.as_ref().is_some_and(|manifest| {
        manifest["requirements"].as_array().is_some_and(|items| {
            items
                .iter()
                .any(|item| item["id"] == "load_step_slew" || item["id"] == "startup_ramp")
        })
    });
    if !scenarios.is_empty() {
        let specs: Vec<_> = scenarios.iter().map(|s| s["spec"].clone()).collect();
        let settings_match = if let Some(manifest) = input["settings_manifest"].as_str() {
            let declared: Value =
                serde_json::from_str(manifest).context("invalid settings manifest")?;
            declared == Value::Array(specs.clone())
                && input["settings_sha256"] == hash(manifest.as_bytes())
        } else {
            input["settings_sha256"] == hash(&serde_json::to_vec(&specs)?)
        };
        if !settings_match {
            findings.push(json!({"id":"settings_identity_mismatch","message":"scenario settings differ from their frozen identity"}));
        }
    }
    let mut seen = BTreeSet::new();
    let mut seen_names = BTreeSet::new();
    let mut seen_profiles = BTreeSet::new();
    let mut results = Vec::new();
    for scenario in &scenarios {
        let name = scenario["name"].as_str().unwrap_or("").to_owned();
        let profile_id = scenario["spec"]["profile_id"].as_str().unwrap_or("");
        let protocol_case = scenario["case_id"].as_str().unwrap_or("");
        let scenario_key = if !protocol_case.is_empty() {
            protocol_case.to_owned()
        } else if name == "load_variation" {
            format!("{name}:{profile_id}")
        } else {
            name.clone()
        };
        if !REQUIRED.contains(&name.as_str()) || !seen.insert(scenario_key) {
            findings.push(json!({"id":"scenario_identity_invalid","message":name}));
            continue;
        }
        seen_names.insert(name.clone());
        if name == "load_variation" {
            let profile = profile_id;
            if !REQUIRED_LOAD_PROFILES.contains(&profile)
                || profile_requirements.get(profile).is_none_or(|(low, high)| {
                    scenario["spec"]["load_low_a"].as_f64() != Some(*low)
                        || scenario["spec"]["load_high_a"].as_f64() != Some(*high)
                })
            {
                findings.push(json!({"id":"load_profile_mismatch","message":profile}));
            }
            seen_profiles.insert(profile.to_owned());
            if protocol_required
                && scenario["spec"]["edges"]
                    .as_array()
                    .is_none_or(|edges| edges.len() != 6)
            {
                findings.push(json!({"id":"load_protocol_missing","message":format!("{profile}: three-pulse bidirectional schedule required")}));
            }
            if protocol_required && scenario["spec"]["vin_corner_v"].as_f64().is_none() {
                findings.push(json!({"id":"load_corner_missing","message":format!("{profile}: explicit VIN corner required")}));
            }
        } else if protocol_required && name == "startup" {
            let spec = &scenario["spec"];
            for key in [
                "vin_corner_v",
                "vin_ramp_start_s",
                "vin_ramp_end_s",
                "vin_crossing_v",
                "expected_crossing_s",
                "capture_end_s",
                "load_a",
            ] {
                if spec[key].as_f64().is_none() {
                    findings.push(json!({"id":"startup_protocol_missing","message":key}));
                }
            }
            if spec["en_tied_to_vin"] != true {
                findings.push(json!({"id":"startup_protocol_missing","message":"en_tied_to_vin"}));
            }
        }
        if scenario["status"] != "pass"
            || scenario["synthetic"] == true
            || !digest(&scenario["deck_sha256"])
        {
            findings.push(json!({"id":"scenario_unavailable","message":format!("{name}: {}",scenario["status"])}));
            continue;
        }
        match measure(scenario) {
            Ok(result) => results.push(result),
            Err(error) if error.downcast_ref::<AcceptanceFailure>().is_some() => {
                results.push(json!({
                    "name": name, "case_id": scenario["case_id"], "status": "fail",
                    "findings": [{"id":"protocol_acceptance_failed", "message":error.to_string()}]
                }))
            }
            Err(error) => findings
                .push(json!({"id":"waveform_invalid","message":format!("{name}: {error:#}")})),
        }
    }
    for required in REQUIRED {
        if required != "load_variation" && !seen_names.contains(required) {
            findings.push(json!({"id":"mandatory_scenario_missing","message":required}));
        }
    }
    for profile in REQUIRED_LOAD_PROFILES {
        if !seen_profiles.contains(profile) {
            findings.push(json!({"id":"mandatory_load_profile_missing","message":profile}));
        }
    }
    if protocol_required {
        let startup_count = scenarios.iter().filter(|s| s["name"] == "startup").count();
        let load_count = scenarios
            .iter()
            .filter(|s| s["name"] == "load_variation")
            .count();
        let input_count = scenarios
            .iter()
            .filter(|s| s["name"] == "input_variation")
            .count();
        if startup_count < 6 || load_count < 6 || input_count < 1 {
            findings.push(json!({"id":"scenario_coverage_missing","message":"adopted protocol requires six startup, six load, and one input case"}));
        }
        let req_value = |id: &str| {
            requirements
                .as_ref()
                .and_then(|m| m["requirements"].as_array())
                .and_then(|items| items.iter().find(|i| i["id"] == id))
                .and_then(|i| i["value"].as_f64())
        };
        let corners: Vec<i64> = ["vin_min", "vin_nominal", "vin_max"]
            .iter()
            .filter_map(|id| req_value(id))
            .map(|v| (v * 1000.0).round() as i64)
            .collect();
        if corners.len() != 3
            || corners.iter().copied().collect::<BTreeSet<_>>().len() != 3
            || corners.iter().any(|v| *v <= 0)
        {
            findings.push(json!({"id":"requirements_corner_matrix_invalid","message":"requirements must define three distinct positive VIN corners"}));
        }
        let continuous = req_value("iout_continuous")
            .filter(|v| v.is_finite() && *v > 0.0)
            .map(|v| (v * 1000.0).round() as i64);
        if continuous.is_none() {
            findings.push(json!({"id":"requirements_startup_load_invalid","message":"positive continuous startup load must come from requirements"}));
        }
        let mut load_matrix = BTreeSet::new();
        let mut startup_matrix = BTreeSet::new();
        for scenario in &scenarios {
            let corner = scenario["spec"]["vin_corner_v"]
                .as_f64()
                .map(|v| (v * 1000.0).round() as i64);
            if let Some(corner) = corner {
                if scenario["name"] == "load_variation"
                    && !load_matrix.insert((
                        corner,
                        scenario["spec"]["profile_id"]
                            .as_str()
                            .unwrap_or("")
                            .to_owned(),
                    ))
                {
                    findings.push(json!({"id":"load_matrix_duplicate","message":"repeated VIN and load-profile pair"}));
                }
                if scenario["name"] == "startup"
                    && !startup_matrix.insert((
                        corner,
                        (scenario["spec"]["load_a"].as_f64().unwrap_or(-1.0) * 1000.0).round()
                            as i64,
                    ))
                {
                    findings.push(json!({"id":"startup_matrix_duplicate","message":"repeated VIN and startup-load pair"}));
                }
            }
        }
        for corner in &corners {
            for profile in REQUIRED_LOAD_PROFILES {
                if !load_matrix.contains(&(*corner, profile.to_owned())) {
                    findings.push(json!({"id":"load_matrix_missing","message":format!("VIN {} mV, {profile}", corner)}));
                }
            }
            for load in std::iter::once(0_i64).chain(continuous) {
                if !startup_matrix.contains(&(*corner, load)) {
                    findings.push(json!({"id":"startup_matrix_missing","message":format!("VIN {} mV, load {} mA", corner, load)}));
                }
            }
        }
    }
    let status = if !findings.is_empty() {
        "blocked"
    } else if results.iter().any(|r| r["status"] != "pass") {
        "fail"
    } else {
        "pass"
    };
    Ok(
        json!({"stage":"simulation","status":status,"findings":findings,"scenarios":results,"layout_sensitive":false,"hardware_validated":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_ngspice_rc_control_matches_analytic_response() {
        let w = parse_raw(include_str!(
            "../engineering/scenarios/controls/run/rc_control.raw"
        ))
        .unwrap();
        assert_eq!(w.time.len(), 69);
        let expected = 1.0 - (1.0 - (-1.0_f64).exp()) * (-2.0_f64).exp();
        assert!((w.signals["v(out)"].last().unwrap() - expected).abs() < 0.0001);
    }
    fn scenario() -> Value {
        scenario_with_load_range(0.2, 0.6)
    }
    fn scenario_with_load_range(low: f64, high: f64) -> Value {
        let mut raw=String::from("Title: software control only\nFlags: real\nNo. Variables: 5\nNo. Points: 5\nVariables:\n0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\nValues:\n");
        for i in 0..5 {
            raw.push_str(&format!(
                "{i} {}\n3.3\n{}\n-0.2\n{}\n",
                i as f64 * 0.001,
                14.0 + i as f64,
                low + (high - low) * i as f64 / 4.0
            ));
        }
        json!({"name":"startup","status":"pass","raw_waveform":raw,"artifact_sha256":hash(raw.as_bytes()),"deck_sha256":"a".repeat(64),"spec":{
            "window_start_s":0.0,"window_end_s":0.004,"max_step_s":0.0011,"target_v":3.3,"settling_band_v":0.1,"event_s":0.0,
            "limits":{"vout_avg":{"min":3.2,"max":3.4},"vout_pp":{"min":0.0,"max":0.1},"overshoot_v":{"min":0.0,"max":0.1},"settling_s":{"min":0.0,"max":0.002},"vin_span":{"min":1.0,"max":5.0},"load_span":{"min":0.1,"max":1.0}}}})
    }
    #[test]
    fn raw_measurements_pass_and_defect_fails() {
        let mut s = scenario();
        assert_eq!(measure(&s).unwrap()["status"], "pass");
        s["spec"]["limits"]["vout_avg"]["max"] = json!(3.25);
        assert_eq!(measure(&s).unwrap()["status"], "fail");
    }

    fn adopted_load_protocol(high: f64) -> (Value, Waveform) {
        let low = 0.05;
        let mut edges = Vec::new();
        for pulse in 0..3 {
            let rise = 0.100 + pulse as f64 * 0.100;
            let fall = rise + 0.010;
            let slew = (high - low) / LOAD_SLEW_A_PER_S;
            edges.push(json!({"start_s":rise,"end_s":rise+slew,"direction":"rising","from_a":low,"to_a":high}));
            edges.push(json!({"start_s":fall,"end_s":fall+slew,"direction":"falling","from_a":high,"to_a":low}));
        }
        let mut times: Vec<f64> = (0..=411).map(|i| i as f64 * 0.001).collect();
        for edge in &edges {
            times.push(edge["start_s"].as_f64().unwrap());
            times.push(edge["end_s"].as_f64().unwrap());
        }
        times.sort_by(|a, b| a.partial_cmp(b).unwrap());
        times.dedup();
        let load_at = |t: f64| {
            let mut value = low;
            for pulse in 0..3 {
                let rise = 0.100 + pulse as f64 * 0.100;
                let fall = rise + 0.010;
                let slew = (high - low) / LOAD_SLEW_A_PER_S;
                if t >= rise && t < rise + slew {
                    return low + (high - low) * (t - rise) / slew;
                }
                if t >= rise + slew && t < fall {
                    value = high;
                }
                if t >= fall && t < fall + slew {
                    return high - (high - low) * (t - fall) / slew;
                }
                if t >= fall + slew {
                    value = low;
                }
            }
            value
        };
        let wave = Waveform {
            time: times.clone(),
            signals: BTreeMap::from([
                ("v(out)".into(), vec![3.3; times.len()]),
                ("v(in)".into(), vec![15.0; times.len()]),
                ("i(vin)".into(), vec![0.1; times.len()]),
                (
                    "i(load)".into(),
                    times.iter().map(|t| load_at(*t)).collect(),
                ),
            ]),
        };
        (
            json!({"load_low_a":low,"load_high_a":high,"vin_corner_v":15.0,"capture_end_s":0.411,"edges":edges}),
            wave,
        )
    }

    fn raw_text(wave: &Waveform) -> String {
        let mut raw = format!("Title: matrix\nFlags: real\nNo. Variables: 5\nNo. Points: {}\nVariables:\n0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\nValues:\n", wave.time.len());
        for i in 0..wave.time.len() {
            raw.push_str(&format!(
                "{} {} {} {} {} {}\n",
                i,
                wave.time[i],
                wave.signals["v(out)"][i],
                wave.signals["v(in)"][i],
                wave.signals["i(vin)"][i],
                wave.signals["i(load)"][i]
            ));
        }
        raw
    }

    fn startup_wave(corner: f64, load: f64) -> Waveform {
        let time: Vec<f64> = (0..=30).map(|i| i as f64 * 0.001).collect();
        Waveform {
            time: time.clone(),
            signals: BTreeMap::from([
                (
                    "v(out)".into(),
                    time.iter()
                        .map(|t| if *t < 0.004 { 3.3 * *t / 0.004 } else { 3.3 })
                        .collect(),
                ),
                (
                    "v(in)".into(),
                    time.iter()
                        .map(|t| {
                            if *t < 0.001 {
                                corner * *t / 0.001
                            } else {
                                corner
                            }
                        })
                        .collect(),
                ),
                ("i(vin)".into(), vec![load; time.len()]),
                (
                    "i(load)".into(),
                    time.iter()
                        .map(|t| {
                            let output = if *t < 0.004 { 3.3 * *t / 0.004 } else { 3.3 };
                            load * (output / STARTUP_LOAD_COMPLIANCE_V).clamp(0.0, 1.0)
                        })
                        .collect(),
                ),
            ]),
        }
    }

    fn startup_spec(corner: f64, load: f64) -> Value {
        json!({"en_tied_to_vin":true,"vin_ramp_start_s":0.0,"vin_ramp_end_s":0.001,"vin_corner_v":corner,"vin_crossing_v":13.5,"expected_crossing_s":0.001,"max_step_s":0.0011,"capture_end_s":0.021,"load_a":load})
    }

    #[test]
    fn adopted_evaluate_accepts_thirteen_raw_waveform_cases() {
        let requirements_manifest = include_str!("../engineering/requirements.json");
        let requirements_sha256 = hash(requirements_manifest.as_bytes());
        let requirements_value: Value = serde_json::from_str(requirements_manifest).unwrap();
        let continuous_load = requirements_value["requirements"]
            .as_array()
            .unwrap()
            .iter()
            .find(|r| r["id"] == "load_step_endpoints")
            .unwrap()["profiles"]
            .as_array()
            .unwrap()
            .iter()
            .find(|p| p["id"] == "continuous_50mA_to_500mA")
            .unwrap()["high_a"]
            .as_f64()
            .unwrap();
        let d = "a".repeat(64);
        let mut scenarios = Vec::new();
        for corner in [13.5, 15.0, 16.5] {
            for (profile, high) in [("continuous_50mA_to_500mA", 0.5), ("pulse_50mA_to_1A", 1.0)] {
                let (mut spec, mut wave) = adopted_load_protocol(high);
                spec["vin_corner_v"] = json!(corner);
                wave.signals
                    .insert("v(in)".into(), vec![corner; wave.time.len()]);
                let raw = raw_text(&wave);
                spec["window_start_s"] = json!(0.0);
                spec["window_end_s"] = json!(0.411);
                spec["max_step_s"] = json!(0.0011);
                spec["target_v"] = json!(3.3);
                spec["settling_band_v"] = json!(0.033);
                spec["event_s"] = json!(0.1);
                spec["profile_id"] = json!(profile);
                spec["load_tolerance_fraction"] = json!(0.02);
                spec["limits"] = json!({"vout_avg":{"min":3.1,"max":3.5},"vout_pp":{"min":0.0,"max":0.2},"overshoot_v":{"min":0.0,"max":0.2},"settling_s":{"min":0.0,"max":0.001},"load_span":{"min":0.1,"max":2.0}});
                scenarios.push(json!({"name":"load_variation","case_id":format!("load-{corner}-{profile}"),"status":"pass","raw_waveform":raw,"artifact_sha256":hash(raw.as_bytes()),"deck_sha256":d,"spec":spec}));
            }
        }
        for corner in [13.5, 15.0, 16.5] {
            for load in [0.0, continuous_load] {
                let spec = json!({"window_start_s":0.0,"window_end_s":0.021,"max_step_s":0.0011,"target_v":3.3,"settling_band_v":0.033,"event_s":0.001,"en_tied_to_vin":true,"vin_ramp_start_s":0.0,"vin_ramp_end_s":0.001,"vin_corner_v":corner,"vin_crossing_v":13.5,"expected_crossing_s":0.001,"capture_end_s":0.021,"load_a":load,"limits":{"vout_avg":{"min":0.0,"max":3.5},"vout_pp":{"min":0.0,"max":4.0},"overshoot_v":{"min":0.0,"max":0.2},"settling_s":{"min":0.0,"max":0.01}}});
                let raw = raw_text(&startup_wave(corner, load));
                scenarios.push(json!({"name":"startup","case_id":format!("startup-{corner}-{load}"),"status":"pass","raw_waveform":raw,"artifact_sha256":hash(raw.as_bytes()),"deck_sha256":d,"spec":spec}));
            }
        }
        let mut input_spec = scenarios[0]["spec"].clone();
        input_spec["limits"] = json!({"vout_avg":{"min":0.0,"max":3.5},"vout_pp":{"min":0.0,"max":4.0},"overshoot_v":{"min":0.0,"max":0.2},"settling_s":{"min":0.0,"max":0.01},"vin_span":{"min":1.0,"max":20.0}});
        input_spec["window_end_s"] = json!(0.411);
        input_spec["event_s"] = json!(0.001);
        input_spec.as_object_mut().unwrap().remove("edges");
        let (_, mut input_wave) = adopted_load_protocol(0.5);
        input_wave.signals.insert(
            "v(in)".into(),
            input_wave
                .time
                .iter()
                .map(|t| 13.5 + 3.0 * (*t / 0.411).min(1.0))
                .collect(),
        );
        let input_raw = raw_text(&input_wave);
        scenarios.push(json!({"name":"input_variation","case_id":"input-13.5-16.5","status":"pass","raw_waveform":input_raw,"artifact_sha256":hash(input_raw.as_bytes()),"deck_sha256":d,"spec":input_spec}));
        let specs: Vec<_> = scenarios.iter().map(|s| s["spec"].clone()).collect();
        let input = json!({"profile":"engineering-simulation","model":{"mpn":"LMR51430XDDCR","reference_voltage":0.6,"frequency_hz":500000,"mode":"PFM","sha256":d,"requirements_sha256":requirements_sha256,"qualification":{"model_sha256":d,"evidence_sha256":d,"source":"test","license":"test","reviewed_by":"test","status":"pass","coverage":REQUIRED}},"requirements_manifest":requirements_manifest,"qualification_verified":true,"circuit_sha256":d,"requirements_sha256":requirements_sha256,"settings_sha256":hash(&serde_json::to_vec(&specs).unwrap()),"scenarios":scenarios});
        let result = evaluate(input.clone()).unwrap();
        assert_eq!(
            result["findings"]
                .as_array()
                .unwrap()
                .iter()
                .map(|f| f["id"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec!["qualification_not_approved"]
        );
        assert_eq!(result["scenarios"].as_array().unwrap().len(), 13);
        assert!(
            result["scenarios"]
                .as_array()
                .unwrap()
                .iter()
                .all(|s| s["status"] == "pass"),
            "statuses: {:?}",
            result["scenarios"]
                .as_array()
                .unwrap()
                .iter()
                .map(|s| (&s["name"], &s["status"], &s["findings"]))
                .collect::<Vec<_>>()
        );
        let mut bad_response = input.clone();
        let (_, mut wave) = adopted_load_protocol(0.5);
        wave.signals
            .insert("v(in)".into(), vec![13.5; wave.time.len()]);
        let peak = wave
            .time
            .iter()
            .position(|t| (*t - 0.1000045).abs() < 1e-9)
            .unwrap();
        wave.signals.get_mut("v(out)").unwrap()[peak] = 3.43;
        let raw = raw_text(&wave);
        bad_response["scenarios"][0]["artifact_sha256"] = json!(hash(raw.as_bytes()));
        bad_response["scenarios"][0]["raw_waveform"] = json!(raw);
        let bad_result = evaluate(bad_response).unwrap();
        assert_eq!(bad_result["scenarios"][0]["status"], "fail");
        assert_eq!(
            bad_result["scenarios"][0]["findings"][0]["id"],
            "protocol_acceptance_failed"
        );
        assert_eq!(bad_result["findings"].as_array().unwrap().len(), 1);

        let mut extra = input.clone();
        let mut repeated = extra["scenarios"][0].clone();
        repeated["case_id"] = json!("unique-id-same-operating-point");
        extra["scenarios"].as_array_mut().unwrap().push(repeated);
        let extra_specs: Vec<_> = extra["scenarios"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["spec"].clone())
            .collect();
        extra["settings_sha256"] = json!(hash(&serde_json::to_vec(&extra_specs).unwrap()));
        let extra_result = evaluate(extra).unwrap();
        assert_eq!(
            extra_result["findings"]
                .as_array()
                .unwrap()
                .iter()
                .map(|f| f["id"].as_str().unwrap())
                .collect::<Vec<_>>(),
            vec!["qualification_not_approved", "load_matrix_duplicate"]
        );

        let mut missing = input.clone();
        missing["scenarios"]
            .as_array_mut()
            .unwrap()
            .retain(|s| s["case_id"] != "load-13.5-continuous_50mA_to_500mA");
        let reduced: Vec<_> = missing["scenarios"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["spec"].clone())
            .collect();
        missing["settings_sha256"] = json!(hash(&serde_json::to_vec(&reduced).unwrap()));
        let missing_findings = evaluate(missing).unwrap()["findings"].clone();
        assert!(missing_findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "load_matrix_missing"));
        let mut duplicate = input;
        duplicate["scenarios"][2]["spec"]["vin_corner_v"] = json!(13.5);
        duplicate["scenarios"][2]["raw_waveform"] =
            duplicate["scenarios"][0]["raw_waveform"].clone();
        duplicate["scenarios"][2]["artifact_sha256"] =
            duplicate["scenarios"][0]["artifact_sha256"].clone();
        let duplicate_specs: Vec<_> = duplicate["scenarios"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["spec"].clone())
            .collect();
        duplicate["settings_sha256"] = json!(hash(&serde_json::to_vec(&duplicate_specs).unwrap()));
        let duplicate_findings = evaluate(duplicate).unwrap()["findings"].clone();
        assert!(duplicate_findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "load_matrix_missing"));
    }

    #[test]
    fn adopted_requirements_without_vin_max_cannot_fall_back_to_defaults() {
        let mut requirements: Value =
            serde_json::from_str(include_str!("../engineering/requirements.json")).unwrap();
        requirements["requirements"]
            .as_array_mut()
            .unwrap()
            .retain(|item| item["id"] != "vin_max");
        let text = serde_json::to_string(&requirements).unwrap();
        let digest = hash(text.as_bytes());
        let input = json!({"profile":"engineering-simulation","model":{},"requirements_manifest":text,"requirements_sha256":digest,"settings_sha256":"a".repeat(64),"circuit_sha256":"a".repeat(64),"scenarios":[]});
        let findings = evaluate(input).unwrap()["findings"].clone();
        assert!(findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "requirements_corner_matrix_invalid"));
    }

    #[test]
    fn adopted_startup_matrix_uses_requirements_continuous_load() {
        let mut requirements: Value =
            serde_json::from_str(include_str!("../engineering/requirements.json")).unwrap();
        requirements["requirements"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["id"] == "iout_continuous")
            .unwrap()["value"] = json!(0.25);
        let text = serde_json::to_string(&requirements).unwrap();
        let digest = hash(text.as_bytes());
        let input = json!({"profile":"engineering-simulation","model":{},"requirements_manifest":text,"requirements_sha256":digest,"settings_sha256":"a".repeat(64),"circuit_sha256":"a".repeat(64),"scenarios":[]});
        let findings = evaluate(input).unwrap()["findings"].clone();
        assert!(findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "startup_matrix_missing"
                && f["message"].as_str().unwrap().contains("250 mA")));
    }

    #[test]
    fn prebiased_startup_and_false_zero_load_are_rejected() {
        let mut wave = startup_wave(13.5, 0.0);
        wave.signals.get_mut("v(out)").unwrap()[0] = 3.3;
        let spec = json!({"en_tied_to_vin":true,"vin_ramp_start_s":0.0,"vin_ramp_end_s":0.001,"vin_corner_v":13.5,"vin_crossing_v":13.5,"expected_crossing_s":0.001,"max_step_s":0.0011,"capture_end_s":0.021,"load_a":0.0});
        assert!(validate_startup_protocol(&spec, &wave, &mut json!({})).is_err());
        let wave = startup_wave(13.5, 0.25);
        let mut false_zero = spec.clone();
        false_zero["load_a"] = json!(0.0);
        assert!(validate_startup_protocol(&false_zero, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn compliant_startup_load_law_is_accepted_from_discharged_output() {
        let mut wave = startup_wave(13.5, 0.5);
        let out = wave.signals["v(out)"].clone();
        wave.signals.insert(
            "i(load)".into(),
            out.iter()
                .map(|v| 0.5 * (v / 0.1).clamp(0.0, 1.0))
                .collect(),
        );
        let spec = startup_spec(13.5, 0.5);
        validate_startup_protocol(&spec, &wave, &mut json!({})).unwrap();
    }

    #[test]
    fn compliant_startup_load_law_checks_intermediate_voltage() {
        let mut wave = startup_wave(13.5, 0.5);
        wave.signals.get_mut("v(out)").unwrap()[1] = 0.05;
        wave.signals.get_mut("i(load)").unwrap()[1] = 0.25;
        let spec = startup_spec(13.5, 0.5);
        validate_startup_protocol(&spec, &wave, &mut json!({})).unwrap();
    }

    #[test]
    fn ideal_constant_startup_load_at_discharged_output_is_rejected() {
        let mut wave = startup_wave(13.5, 0.5);
        wave.signals
            .insert("i(load)".into(), vec![0.5; wave.time.len()]);
        let spec = startup_spec(13.5, 0.5);
        assert!(validate_startup_protocol(&spec, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn startup_load_below_rating_after_compliance_is_rejected() {
        let mut wave = startup_wave(13.5, 0.5);
        wave.signals.get_mut("i(load)").unwrap()[5] = 0.48;
        let spec = startup_spec(13.5, 0.5);
        assert!(validate_startup_protocol(&spec, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn startup_load_removed_after_compliance_is_rejected() {
        let mut wave = startup_wave(13.5, 0.5);
        wave.signals.get_mut("i(load)").unwrap()[5] = 0.0;
        let spec = startup_spec(13.5, 0.5);
        assert!(validate_startup_protocol(&spec, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn zero_load_startup_mismatch_is_rejected() {
        let mut wave = startup_wave(13.5, 0.0);
        wave.signals.get_mut("i(load)").unwrap()[5] = 0.01;
        let spec = startup_spec(13.5, 0.0);
        assert!(validate_startup_protocol(&spec, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn requirements_pin_startup_compliance_to_validator_constant() {
        let requirements: Value =
            serde_json::from_str(include_str!("../engineering/requirements.json")).unwrap();
        let value = requirements["requirements"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["id"] == "startup_load_compliance_voltage")
            .unwrap()["value"]
            .as_f64()
            .unwrap();
        assert!((value - STARTUP_LOAD_COMPLIANCE_V).abs() <= f64::EPSILON);
    }

    #[test]
    fn binary_waveform_matches_ascii_waveform() {
        let wave = startup_wave(13.5, 0.5);
        let root = std::env::temp_dir().join(format!("temper-binary-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("waveform.raw");
        let names = ["time", "v(out)", "v(in)", "i(vin)", "i(load)"];
        let units = ["time", "voltage", "voltage", "current", "current"];
        let mut bytes = format!(
            "Flags: real\nNo. Variables: 5\nNo. Points: {}\nVariables:\n",
            wave.time.len()
        )
        .into_bytes();
        for (index, (name, unit)) in names.iter().zip(units).enumerate() {
            bytes.extend_from_slice(format!("\t{}\t{}\t{}\n", index, name, unit).as_bytes());
        }
        bytes.extend_from_slice(b"Binary:\n");
        for row in 0..wave.time.len() {
            for name in names {
                let value = if name == "time" {
                    wave.time[row]
                } else {
                    wave.signals[name][row]
                };
                bytes.extend_from_slice(&value.to_le_bytes());
            }
        }
        let expected = hash(&bytes);
        std::fs::write(&path, bytes).unwrap();
        let decoded = parse_binary(&root, "waveform.raw", &expected).unwrap();
        assert_eq!(decoded.time, wave.time);
        assert_eq!(decoded.signals["v(out)"], wave.signals["v(out)"]);
        assert_eq!(decoded.signals["i(load)"], wave.signals["i(load)"]);
        assert!(parse_binary(&root, "../waveform.raw", &expected).is_err());
        assert!(parse_binary(&root, "waveform.raw", &"0".repeat(64)).is_err());
        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_dir(root);
    }

    #[test]
    fn binary_waveform_streams_more_than_one_million_rows() {
        let root = std::env::temp_dir().join(format!("temper-binary-large-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("waveform.raw");
        let rows = 1_000_001usize;
        let names = ["time", "v(out)", "v(in)", "i(vin)"];
        let units = ["time", "voltage", "voltage", "current"];
        let mut file = std::fs::File::create(&path).unwrap();
        use std::io::Write;
        write!(
            file,
            "Flags: real\nNo. Variables: 4\nNo. Points: {rows}\nVariables:\n"
        )
        .unwrap();
        for (index, (name, unit)) in names.iter().zip(units).enumerate() {
            writeln!(file, "\t{index}\t{name}\t{unit}").unwrap();
        }
        file.write_all(b"Binary:\n").unwrap();
        for row in 0..rows {
            for value in [row as f64 * 1e-6, 3.3, 15.0, 0.0] {
                file.write_all(&value.to_le_bytes()).unwrap();
            }
        }
        drop(file);
        let mut digest = Sha256::new();
        let mut source = std::fs::File::open(&path).unwrap();
        let mut chunk = [0u8; 1024 * 1024];
        loop {
            let count = source.read(&mut chunk).unwrap();
            if count == 0 {
                break;
            }
            digest.update(&chunk[..count]);
        }
        let decoded =
            parse_binary(&root, "waveform.raw", &format!("{:x}", digest.finalize())).unwrap();
        assert_eq!(decoded.time.len(), rows);
        assert_eq!(decoded.time[rows - 1], 1.000000);
        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_dir(root);
    }

    #[test]
    fn adopted_load_protocol_accepts_three_bidirectional_pulses() {
        let (spec, wave) = adopted_load_protocol(0.5);
        let mut measured = json!({});
        validate_load_protocol(&spec, &wave, &mut measured).unwrap();
        assert_eq!(measured["edges"].as_array().unwrap().len(), 6);
    }

    #[test]
    fn adopted_load_protocol_rejects_missing_falling_edge_and_wrong_slew() {
        let (mut spec, wave) = adopted_load_protocol(0.5);
        spec["edges"].as_array_mut().unwrap().pop();
        assert!(validate_load_protocol(&spec, &wave, &mut json!({})).is_err());
        let (mut spec, wave) = adopted_load_protocol(0.5);
        spec["edges"][0]["end_s"] = json!(0.0002);
        assert!(validate_load_protocol(&spec, &wave, &mut json!({})).is_err());
    }

    #[test]
    fn load_endpoints_reject_shifted_waveforms_and_relaxed_tolerances() {
        let mut s = scenario();
        s["name"] = json!("load_variation");
        s["spec"]["profile_id"] = json!("endpoint_measurement_control");
        s["spec"]["load_low_a"] = json!(0.2);
        s["spec"]["load_high_a"] = json!(0.6);
        s["spec"]["load_tolerance_fraction"] = json!(0.02);
        assert_eq!(measure(&s).unwrap()["status"], "pass");
        let mut shifted = s.clone();
        shifted["spec"]["load_low_a"] = json!(0.05);
        shifted["spec"]["load_high_a"] = json!(0.45);
        assert!(measure(&shifted)
            .unwrap_err()
            .to_string()
            .contains("low endpoint mismatch"));
        for tolerance in [json!(1.0), json!(-0.01), Value::Null] {
            let mut bad = s.clone();
            bad["spec"]["load_tolerance_fraction"] = tolerance;
            assert!(measure(&bad).is_err());
        }
    }
    #[test]
    fn bad_raw_and_missing_limits_are_rejected() {
        for mutation in ["hash", "units", "time", "resolution", "limits"] {
            let mut s = scenario();
            match mutation {
                "hash" => s["artifact_sha256"] = json!("0".repeat(64)),
                "units" | "time" => {
                    let raw = s["raw_waveform"].as_str().unwrap().replace(
                        if mutation == "units" {
                            "v(out) voltage"
                        } else {
                            "1 0.001"
                        },
                        if mutation == "units" {
                            "v(out) current"
                        } else {
                            "1 0"
                        },
                    );
                    s["artifact_sha256"] = json!(hash(raw.as_bytes()));
                    s["raw_waveform"] = json!(raw);
                }
                "resolution" => s["spec"]["max_step_s"] = json!(0.0001),
                _ => s["spec"]["limits"] = json!({}),
            }
            assert!(measure(&s).is_err(), "{mutation}");
        }
    }

    #[test]
    fn adopted_load_holds_and_transient_controls_reject_bad_measurements() {
        let (spec, wave) = adopted_load_protocol(0.5);
        validate_load_protocol(&spec, &wave, &mut json!({})).unwrap();
        for (signal, at, value, reason) in [
            ("i(load)", 0.050, 0.070, "hold waveform outside tolerance"),
            ("i(load)", 0.105, 0.450, "hold waveform outside tolerance"),
            ("v(out)", 0.1000045, 3.430, "departure exceeds 100 mV"),
            ("v(out)", 0.103, 3.360, "remain recovered"),
        ] {
            let (spec, mut bad) = adopted_load_protocol(0.5);
            let index = bad
                .time
                .iter()
                .position(|t| (*t - at).abs() < 1e-9)
                .unwrap();
            bad.signals.get_mut(signal).unwrap()[index] = value;
            let error = validate_load_protocol(&spec, &bad, &mut json!({})).unwrap_err();
            assert!(
                error.to_string().contains(reason),
                "{signal} at {at}: {error:#}"
            );
        }
        let mut truncated = spec.clone();
        truncated["capture_end_s"] = json!(0.400);
        assert!(validate_load_protocol(&truncated, &wave, &mut json!({}))
            .unwrap_err()
            .to_string()
            .contains("final 100 ms"));
        let mut late_start = wave;
        late_start.time[0] = 0.0005;
        assert!(validate_load_protocol(&spec, &late_start, &mut json!({}))
            .unwrap_err()
            .to_string()
            .contains("initial 100 ms"));
    }
    #[test]
    fn complete_software_chain_and_independent_negative_controls() {
        let d = "a".repeat(64);
        let scenarios: Vec<_> = REQUIRED
            .iter()
            .flat_map(|name| {
                let mut s = scenario();
                s["name"] = json!(name);
                if *name == "load_variation" {
                    [
                        {
                            let mut first = scenario_with_load_range(0.05, 0.5);
                            first["name"] = json!("load_variation");
                            first["spec"]["profile_id"] = json!("continuous_50mA_to_500mA");
                            first["spec"]["load_low_a"] = json!(0.05);
                            first["spec"]["load_high_a"] = json!(0.5);
                            first["spec"]["load_tolerance_fraction"] = json!(0.02);
                            first
                        },
                        {
                            let mut second = scenario_with_load_range(0.05, 1.0);
                            second["name"] = json!("load_variation");
                            second["spec"]["profile_id"] = json!("pulse_50mA_to_1A");
                            second["spec"]["load_low_a"] = json!(0.05);
                            second["spec"]["load_high_a"] = json!(1.0);
                            second["spec"]["load_tolerance_fraction"] = json!(0.02);
                            second
                        },
                    ]
                } else {
                    [s, Value::Null]
                }
            })
            .filter(|s| !s.is_null())
            .collect();
        let settings: Vec<_> = scenarios.iter().map(|s| s["spec"].clone()).collect();
        let requirements_manifest = serde_json::to_string(&json!({"requirements":[{"id":"load_step_endpoints","profiles":[{"id":"continuous_50mA_to_500mA","low_a":0.05,"high_a":0.5},{"id":"pulse_50mA_to_1A","low_a":0.05,"high_a":1.0}]}]})).unwrap();
        let requirements_sha256 = hash(requirements_manifest.as_bytes());
        let input = json!({"profile":"engineering-simulation","model":{
            "mpn":"LMR51430XDDCR","reference_voltage":0.6,"frequency_hz":500000,"mode":"PFM","sha256":d,
            "qualification":{"model_sha256":d,"evidence_sha256":d,"source":"software control only","license":"test","reviewed_by":"test","status":"pass","coverage":REQUIRED}},
            "requirements_manifest":requirements_manifest,
            "qualification_verified":true,"circuit_sha256":d,"requirements_sha256":requirements_sha256,"settings_sha256":hash(&serde_json::to_vec(&settings).unwrap()),"scenarios":scenarios});
        let baseline = evaluate(input.clone()).unwrap();
        assert_eq!(baseline["status"], "blocked");
        assert_eq!(baseline["findings"].as_array().unwrap().len(), 1);
        assert_eq!(baseline["findings"][0]["id"], "qualification_not_approved");
        assert!(baseline["scenarios"]
            .as_array()
            .unwrap()
            .iter()
            .all(|s| s["status"] == "pass"));
        for (manifest, expected) in [
            (Value::Null, "requirements_manifest_missing"),
            (json!("{}"), "requirements_manifest_invalid"),
        ] {
            let mut bad = input.clone();
            bad["requirements_manifest"] = manifest;
            assert!(evaluate(bad).unwrap()["findings"]
                .as_array()
                .unwrap()
                .iter()
                .any(|f| f["id"] == expected));
        }
        for defect in [
            "synthetic",
            "qualification",
            "coverage",
            "settings",
            "raw",
            "duplicate",
        ] {
            let mut bad = input.clone();
            match defect {
                "synthetic" => bad["synthetic"] = json!(true),
                "qualification" => bad["qualification_verified"] = json!(false),
                "coverage" => bad["model"]["qualification"]["coverage"] = json!([]),
                "settings" => bad["scenarios"][0]["spec"]["target_v"] = json!(5.0),
                "raw" => bad["scenarios"][0]["raw_waveform"] = json!(""),
                _ => bad["scenarios"][1]["name"] = json!("startup"),
            }
            assert_ne!(evaluate(bad).unwrap()["status"], "pass", "{defect}");
        }
        let mut missing_profile = input.clone();
        let missing_manifest = serde_json::to_string(&json!({"requirements":[{"id":"load_step_endpoints","profiles":[{"id":"continuous_50mA_to_500mA","low_a":0.05,"high_a":0.5},{"id":"other","low_a":0.05,"high_a":1.0}]}]})).unwrap();
        missing_profile["requirements_manifest"] = json!(missing_manifest);
        missing_profile["requirements_sha256"] = json!(hash(
            missing_profile["requirements_manifest"]
                .as_str()
                .unwrap()
                .as_bytes()
        ));
        let findings = evaluate(missing_profile).unwrap()["findings"].clone();
        assert!(findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "load_profile_requirement_missing"));

        let mut duplicate_profile = input.clone();
        duplicate_profile["scenarios"][3]["spec"]["profile_id"] = json!("continuous_50mA_to_500mA");
        let findings = evaluate(duplicate_profile).unwrap()["findings"].clone();
        assert!(findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "scenario_identity_invalid"));

        let mut wrong_profile = input;
        wrong_profile["scenarios"][2]["spec"]["load_high_a"] = json!(0.6);
        let findings = evaluate(wrong_profile).unwrap()["findings"].clone();
        assert!(findings
            .as_array()
            .unwrap()
            .iter()
            .any(|f| f["id"] == "load_profile_mismatch"));
    }
}
