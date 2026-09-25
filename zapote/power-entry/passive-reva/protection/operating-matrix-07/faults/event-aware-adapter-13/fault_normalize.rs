//! Fault-trace adapter for operating-matrix-07.
//!
//! This is transport/schema evidence, not a protection verdict. It converts
//! an ngspice `wrdata` table into the exact 17-column input accepted by
//! `fault_checks.rs`, retains the extra fault-path vectors, and writes a
//! receipt-style report with mutation, detector, latch, and current timing.
//! The CLI is streaming: it reads one row at a time through `BufRead`, writes
//! both retained outputs through `BufWriter`, and keeps only bounded state.
//! Equal-time raw groups are retained up to explicit group, per-group, and
//! total-row caps so every 42-field member can be audited without
//! deduplication.
//! The existing normalizer is intentionally not
//! reused: it emits the 12-column normal-operating schema.

use std::{
    collections::HashSet,
    env, fs,
    io::{self, BufRead, BufReader, BufWriter, Write},
    process::ExitCode,
};

const CHECKED_HEADER: &str = "time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit)";
const SUPP_HEADER: &str = "time i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject) v(fault) v(q) v(en) v(gate)";
const CHANNEL_OFF_A: f64 = 0.10;
const LOGIC_HIGH: f64 = 2.5;
const MAX_EQUAL_GROUPS: usize = 1024;
const MAX_EQUAL_ROWS: usize = 100_000;
const MAX_GROUP_ROWS: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    F2Crest,
    F2Zero,
    F2Start,
    SwitchShort,
    DiodeShort,
    BothShort,
    BypassNeg,
}

impl Kind {
    fn parse(s: &str) -> Result<Self, String> {
        match s.to_ascii_lowercase().as_str() {
            "f2-crest" => Ok(Self::F2Crest),
            "f2-zero" => Ok(Self::F2Zero),
            "f2-start" => Ok(Self::F2Start),
            "switch-short" | "sw-short" => Ok(Self::SwitchShort),
            "diode-short" => Ok(Self::DiodeShort),
            "both-short" => Ok(Self::BothShort),
            "bypass-neg" | "bypass" => Ok(Self::BypassNeg),
            _ => Err(format!("unknown planned fault kind: {s}")),
        }
    }

    fn needs_f2_transition(self) -> bool {
        matches!(
            self,
            Self::F2Crest | Self::F2Zero | Self::F2Start | Self::BypassNeg
        )
    }
}

#[derive(Clone, Copy, Debug)]
struct Config {
    tstop: f64,
    kind: Kind,
    mutation_time: f64,
    event_window: f64,
    max_gap: f64,
}

#[derive(Clone, Copy, Debug)]
struct Row {
    t: f64,
    ac: f64,
    vd: f64,
    vb: f64,
    sw: f64,
    gate: f64,
    il: f64,
    channel: f64,
    body: f64,
    vac: f64,
    q: f64,
    en: f64,
    fault: f64,
    f2ctl: f64,
    standby: f64,
    arm: f64,
    permit: f64,
    f2_current: f64,
    d1_current: f64,
    d2_current: f64,
    inject: f64,
}

#[derive(Debug)]
struct EqualGroup {
    time: f64,
    left: Option<(usize, Vec<f64>)>,
    group: Vec<(usize, Vec<f64>)>,
    right: Option<(usize, Vec<f64>)>,
    threshold_crossing: bool,
}

#[derive(Clone, Copy, Debug)]
struct Indices {
    time: usize,
    ac_direct: Option<usize>,
    acsrc: Option<usize>,
    acn: Option<usize>,
    vd: usize,
    vb: usize,
    sw: usize,
    gate: usize,
    il: usize,
    channel: usize,
    body: usize,
    vac: usize,
    q: usize,
    en: usize,
    fault: usize,
    f2ctl: usize,
    standby: usize,
    arm: usize,
    permit: usize,
    f2_current: usize,
    d1_current: usize,
    d2_current: usize,
    inject: usize,
}

fn find_one(columns: &[String], names: &[&str], label: &str) -> Result<usize, String> {
    let hits: Vec<usize> = columns
        .iter()
        .enumerate()
        .filter(|(_, c)| names.iter().any(|name| c.eq_ignore_ascii_case(name)))
        .map(|(i, _)| i)
        .collect();
    match hits.as_slice() {
        [one] => Ok(*one),
        [] => Err(format!("missing required column {label}")),
        _ => Err(format!("duplicate required column {label}")),
    }
}

fn indices(columns: &[String]) -> Result<Indices, String> {
    let mut seen = HashSet::new();
    for column in columns {
        let key = column.to_ascii_lowercase();
        if !seen.insert(key) {
            return Err(format!("duplicate trace header {column}"));
        }
    }
    let direct = columns
        .iter()
        .enumerate()
        .filter(|(_, c)| c.eq_ignore_ascii_case("v(acsrc,acn)"))
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    let ac_direct = match direct.as_slice() {
        [] => None,
        [one] => Some(*one),
        _ => return Err("duplicate required column v(acsrc,acn)".into()),
    };
    let acsrc = if ac_direct.is_none() {
        Some(find_one(columns, &["v(acsrc)"], "v(acsrc)")?)
    } else {
        None
    };
    let acn = if ac_direct.is_none() {
        Some(find_one(columns, &["v(acn)"], "v(acn)")?)
    } else {
        None
    };
    Ok(Indices {
        time: find_one(columns, &["time"], "time")?,
        ac_direct,
        acsrc,
        acn,
        vd: find_one(columns, &["v(vd)"], "v(vd)")?,
        vb: find_one(columns, &["v(vb)"], "v(vb)")?,
        sw: find_one(columns, &["v(sw)"], "v(sw)")?,
        gate: find_one(columns, &["v(gate)"], "v(gate)")?,
        il: find_one(columns, &["i(Lboost)", "lboost#branch"], "i(Lboost)")?,
        channel: find_one(columns, &["i(Vchannel)", "vchannel#branch"], "i(Vchannel)")?,
        body: find_one(columns, &["i(Vbody)", "vbody#branch"], "i(Vbody)")?,
        vac: find_one(columns, &["i(Vac)", "vac#branch"], "i(Vac)")?,
        q: find_one(columns, &["v(q)"], "v(q)")?,
        en: find_one(columns, &["v(en)"], "v(en)")?,
        fault: find_one(columns, &["v(fault)"], "v(fault)")?,
        f2ctl: find_one(columns, &["v(f2ctl)"], "v(f2ctl)")?,
        standby: find_one(columns, &["v(standby_req)"], "v(standby_req)")?,
        arm: find_one(columns, &["v(arm)"], "v(arm)")?,
        permit: find_one(columns, &["v(permit)"], "v(permit)")?,
        f2_current: find_one(columns, &["i(Vf2sense)", "vf2sense#branch"], "i(Vf2sense)")?,
        d1_current: find_one(
            columns,
            &["i(Vdboost1sense)", "vdboost1sense#branch"],
            "i(Vdboost1sense)",
        )?,
        d2_current: find_one(
            columns,
            &["i(Vdboost2sense)", "vdboost2sense#branch"],
            "i(Vdboost2sense)",
        )?,
        inject: find_one(columns, &["v(fault_inject)"], "v(fault_inject)")?,
    })
}

fn parse_number(fields: &[&str], index: usize, row: usize) -> Result<f64, String> {
    let value = fields
        .get(index)
        .ok_or_else(|| format!("row {row}: missing field {index}"))?
        .parse::<f64>()
        .map_err(|_| format!("row {row}: invalid number at field {index}"))?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err(format!("row {row}: nonfinite field {index}"))
    }
}

fn parse_row(fields: &[&str], row_no: usize, columns: usize, idx: &Indices) -> Result<Row, String> {
    if fields.len() != columns {
        return Err(format!(
            "row {row_no}: expected {columns} fields, got {}",
            fields.len()
        ));
    }
    for (index, field) in fields.iter().enumerate() {
        let value = field
            .parse::<f64>()
            .map_err(|_| format!("row {row_no}: invalid number at field {index}"))?;
        if !value.is_finite() {
            return Err(format!("row {row_no}: nonfinite field {index}"));
        }
    }
    let n = |i| parse_number(fields, i, row_no);
    let ac = match (idx.ac_direct, idx.acsrc, idx.acn) {
        (Some(i), _, _) => n(i)?,
        (None, Some(src), Some(neutral)) => {
            let value = n(src)? - n(neutral)?;
            if value.is_finite() {
                value
            } else {
                return Err(format!("row {row_no}: derived AC voltage overflow"));
            }
        }
        _ => return Err("line-voltage mapping is incomplete".into()),
    };
    Ok(Row {
        t: n(idx.time)?,
        ac,
        vd: n(idx.vd)?,
        vb: n(idx.vb)?,
        sw: n(idx.sw)?,
        gate: n(idx.gate)?,
        il: n(idx.il)?,
        channel: n(idx.channel)?,
        body: n(idx.body)?,
        vac: n(idx.vac)?,
        q: n(idx.q)?,
        en: n(idx.en)?,
        fault: n(idx.fault)?,
        f2ctl: n(idx.f2ctl)?,
        standby: n(idx.standby)?,
        arm: n(idx.arm)?,
        permit: n(idx.permit)?,
        f2_current: n(idx.f2_current)?,
        d1_current: n(idx.d1_current)?,
        d2_current: n(idx.d2_current)?,
        inject: n(idx.inject)?,
    })
}

/// The edge detectors in the checker treat injected/fault/F2 controls as
/// high at the inclusive 2.5 V boundary.  Other logic health checks use a
/// strict high predicate, while gate-off is inclusive and channel-current
/// retention is strict. Keep those predicates explicit so equal-time rows at
/// an authored boundary cannot be silently classified by the wrong rule.
fn crosses_gt(a: f64, b: f64, threshold: f64) -> bool {
    (a > threshold) != (b > threshold)
}
fn crosses_ge(a: f64, b: f64, threshold: f64) -> bool {
    (a >= threshold) != (b >= threshold)
}
fn crosses_le(a: f64, b: f64, threshold: f64) -> bool {
    (a <= threshold) != (b <= threshold)
}
fn threshold_crossing(a: Row, b: Row) -> bool {
    crosses_ge(a.inject, b.inject, LOGIC_HIGH)
        || crosses_ge(a.f2ctl, b.f2ctl, LOGIC_HIGH)
        || crosses_gt(a.q, b.q, LOGIC_HIGH)
        || crosses_gt(a.en, b.en, LOGIC_HIGH)
        || crosses_ge(a.fault, b.fault, LOGIC_HIGH)
        || crosses_gt(a.arm, b.arm, LOGIC_HIGH)
        || crosses_gt(a.permit, b.permit, LOGIC_HIGH)
        || crosses_le(a.gate.abs(), b.gate.abs(), 0.20)
        || crosses_gt(a.channel.abs(), b.channel.abs(), CHANNEL_OFF_A)
}

fn write_values<W: Write>(out: &mut W, values: &[f64]) -> io::Result<()> {
    for (i, value) in values.iter().enumerate() {
        if i > 0 {
            write!(out, " ")?;
        }
        write!(out, "{value:.17e}")?;
    }
    writeln!(out)
}

#[derive(Default)]
struct StreamState {
    count: usize,
    first_t: Option<f64>,
    last_t: Option<f64>,
    previous: Option<Row>,
    previous_raw: Option<Vec<f64>>,
    before_previous_raw: Option<Vec<f64>>,
    injection_edges: usize,
    injection_row: Option<usize>,
    injection_t: Option<f64>,
    f2_edges: usize,
    f2_row: Option<usize>,
    prefault_rows: usize,
    prefault_bad: bool,
    detector_t: Option<f64>,
    latch_t: Option<f64>,
    channel_peak: f64,
    channel_peak_after_detector: f64,
    channel_peak_after_latch: f64,
    body_peak: f64,
    il_peak: f64,
    f2_peak: f64,
    d1_peak: f64,
    d2_peak: f64,
    last_channel_above: Option<f64>,
    last_channel_above_after_detector: Option<f64>,
    last_channel_above_after_latch: Option<f64>,
    equal_groups: Vec<EqualGroup>,
    indeterminate_equal_threshold: bool,
    logic_changes: usize,
    equal_raw_rows: usize,
}

impl StreamState {
    fn observe<W1: Write, W2: Write>(
        &mut self,
        row: Row,
        raw: &[f64],
        cfg: Config,
        checked: &mut W1,
        supplemental: &mut W2,
    ) -> Result<(), String> {
        if let Some(previous) = self.previous {
            let dt = row.t - previous.t;
            if dt < 0.0 || dt > cfg.max_gap {
                return Err(format!(
                    "row {}: time moves backwards or gap exceeds max_gap",
                    self.count + 2
                ));
            }
            if dt == 0.0 {
                let crossing = threshold_crossing(self.previous.expect("previous row"), row);
                self.logic_changes += usize::from(crossing);
                if let Some(group_index) = self.equal_groups.iter().position(|group| group.time == row.t) {
                    if self.equal_groups[group_index].group.len() >= MAX_GROUP_ROWS
                        || self.equal_raw_rows >= MAX_EQUAL_ROWS
                    {
                        return Err(format!("equal-time raw-row cap {} exceeded", MAX_EQUAL_ROWS));
                    }
                    let group = &mut self.equal_groups[group_index];
                    group.group.push((self.count, raw.to_vec()));
                    self.equal_raw_rows += 1;
                    group.threshold_crossing |= crossing;
                } else {
                    let left = self.before_previous_raw.as_ref().map(|values| {
                        (self.count.saturating_sub(2), values.clone())
                    });
                    let context_rows = 2 + usize::from(left.is_some());
                    if self.equal_groups.len() >= MAX_EQUAL_GROUPS || self.equal_raw_rows + context_rows > MAX_EQUAL_ROWS {
                        return Err(format!("equal-time group/raw-row cap exceeded (groups {}, rows {})", MAX_EQUAL_GROUPS, MAX_EQUAL_ROWS));
                    }
                    let previous = self.previous_raw.clone().ok_or_else(|| "missing previous raw row".to_string())?;
                    let group = EqualGroup {
                        time: row.t,
                        left,
                        group: vec![(self.count - 1, previous), (self.count, raw.to_vec())],
                        right: None,
                        threshold_crossing: crossing,
                    };
                    self.equal_groups.push(group);
                    self.equal_raw_rows += context_rows;
                }
                if crossing { self.indeterminate_equal_threshold = true; }
            } else if let Some(group_index) = self.equal_groups.iter().rposition(|group| group.time < row.t) {
                if self.equal_groups[group_index].right.is_none() {
                    if self.equal_raw_rows >= MAX_EQUAL_ROWS {
                        return Err(format!("equal-time raw-row cap {} exceeded", MAX_EQUAL_ROWS));
                    }
                    self.equal_groups[group_index].right = Some((self.count, raw.to_vec()));
                    self.equal_raw_rows += 1;
                }
            }
        } else {
            if row.t < 0.0 || row.t > 1e-9 {
                return Err("trace does not start at zero".into());
            }
            self.first_t = Some(row.t);
        }
        let lo = cfg.mutation_time - cfg.event_window;
        let hi = cfg.mutation_time + cfg.event_window;
        let inject_rise = self
            .previous
            .map(|p| p.inject < LOGIC_HIGH && row.inject >= LOGIC_HIGH)
            .unwrap_or(false);
        if inject_rise && row.t >= lo && row.t <= hi {
            self.injection_edges += 1;
            self.injection_row = Some(self.count);
            self.injection_t = Some(row.t);
        }
        let f2_fall = self
            .previous
            .map(|p| p.f2ctl >= LOGIC_HIGH && row.f2ctl < LOGIC_HIGH)
            .unwrap_or(false);
        if f2_fall && row.t >= lo && row.t <= hi {
            self.f2_edges += 1;
            self.f2_row = Some(self.count);
        }
        if row.t >= lo && row.t < cfg.mutation_time {
            self.prefault_rows += 1;
            if row.arm <= LOGIC_HIGH
                || row.permit <= LOGIC_HIGH
                || row.q <= LOGIC_HIGH
                || row.en <= LOGIC_HIGH
                || row.fault >= LOGIC_HIGH
            {
                self.prefault_bad = true;
            }
        }
        if self.injection_t.is_some() {
            if self.detector_t.is_none() {
                if let Some(previous) = self.previous {
                    if previous.fault < LOGIC_HIGH && row.fault >= LOGIC_HIGH {
                        self.detector_t = Some(row.t);
                    }
                }
            }
            if self.detector_t.is_some()
                && self.latch_t.is_none()
                && row.q <= LOGIC_HIGH
                && row.en <= LOGIC_HIGH
                && row.gate.abs() <= 0.20
            {
                self.latch_t = Some(row.t);
            }
            self.channel_peak = self.channel_peak.max(row.channel.abs());
            self.body_peak = self.body_peak.max(row.body.abs());
            self.il_peak = self.il_peak.max(row.il.abs());
            self.f2_peak = self.f2_peak.max(row.f2_current.abs());
            self.d1_peak = self.d1_peak.max(row.d1_current.abs());
            self.d2_peak = self.d2_peak.max(row.d2_current.abs());
            if row.channel.abs() > CHANNEL_OFF_A {
                self.last_channel_above = Some(row.t);
            }
            if self.detector_t.is_some() {
                self.channel_peak_after_detector =
                    self.channel_peak_after_detector.max(row.channel.abs());
                if row.channel.abs() > CHANNEL_OFF_A {
                    self.last_channel_above_after_detector = Some(row.t);
                }
            }
            if self.latch_t.is_some() {
                self.channel_peak_after_latch =
                    self.channel_peak_after_latch.max(row.channel.abs());
                if row.channel.abs() > CHANNEL_OFF_A {
                    self.last_channel_above_after_latch = Some(row.t);
                }
            }
        }
        write_values(
            checked,
            &[
                row.t,
                row.ac,
                row.vd,
                row.vb,
                row.sw,
                row.gate,
                row.il,
                row.channel,
                row.body,
                row.vac,
                row.q,
                row.en,
                row.fault,
                row.f2ctl,
                row.standby,
                row.arm,
                row.permit,
            ],
        )
        .map_err(|e| format!("write checked row: {e}"))?;
        write_values(
            supplemental,
            &[
                row.t,
                row.f2_current,
                row.d1_current,
                row.d2_current,
                row.inject,
                row.fault,
                row.q,
                row.en,
                row.gate,
            ],
        )
        .map_err(|e| format!("write supplemental row: {e}"))?;
        self.count += 1;
        self.last_t = Some(row.t);
        self.previous = Some(row);
        self.before_previous_raw = self.previous_raw.clone();
        self.previous_raw = Some(raw.to_vec());
        Ok(())
    }

    fn finish(self, cfg: Config) -> Result<String, String> {
        if self.count < 2 {
            return Err("incomplete trace".into());
        }
        let last_t = self
            .last_t
            .ok_or_else(|| "missing final trace time".to_string())?;
        if (last_t - cfg.tstop).abs() > 1e-9 {
            return Err("trace does not end at declared TSTOP".into());
        }
        if self.injection_edges != 1 {
            return Err("fault_inject must have exactly one rising edge in mutation window".into());
        }
        if cfg.kind.needs_f2_transition() {
            if self.f2_edges != 1 {
                return Err(
                    "F2 kind must have exactly one f2ctl falling edge in mutation window".into(),
                );
            }
            let inject = self
                .injection_row
                .ok_or_else(|| "missing injection row".to_string())?;
            let f2 = self.f2_row.ok_or_else(|| "missing F2 row".to_string())?;
            if inject.abs_diff(f2) > 1 {
                return Err("F2 control and fault_inject edges do not coincide".into());
            }
        }
        if self.prefault_rows < 2 || self.prefault_bad {
            return Err("prefault arm/permit/q/en/fault healthy window is not valid".into());
        }
        let injection_t = self
            .injection_t
            .ok_or_else(|| "missing injection time".to_string())?;
        let status = if self.indeterminate_equal_threshold { "INDETERMINATE_EQUAL_TIME_THRESHOLD_CROSSING" } else { "SCHEMA_AND_EVIDENCE_OK" };
        let mut report = format!(
            "status={status}\nplanned_kind={:?}\ndeclared_mutation_s={:.17e}\nobserved_injection_s={:.17e}\nprefault_rows={}\noriginal_rows={}\nequal_time_groups={}\nequal_time_raw_rows={}\nlogic_changes={}\nequal_group_cap={}\nequal_group_row_cap={}\ndetector_rise_s={}\nlatch_off_s={}\nchannel_peak_after_injection_a={:.17e}\nchannel_last_above_{:.2}a_after_injection_s={}\nchannel_peak_after_detector_a={:.17e}\nchannel_last_above_{:.2}a_after_detector_s={}\nchannel_peak_after_latch_a={:.17e}\nchannel_last_above_{:.2}a_after_latch_s={}\nbody_peak_after_injection_a={:.17e}\nlboost_peak_after_injection_a={:.17e}\nf2_branch_peak_after_injection_a={:.17e}\ndboost1_branch_peak_after_injection_a={:.17e}\ndboost2_branch_peak_after_injection_a={}\n",
            cfg.kind, cfg.mutation_time, injection_t, self.prefault_rows,
            self.count, self.equal_groups.len(), self.equal_raw_rows, self.logic_changes,
            MAX_EQUAL_GROUPS, MAX_GROUP_ROWS,
            self.detector_t.map_or_else(|| "none".into(), |v| format!("{v:.17e}")),
            self.latch_t.map_or_else(|| "none".into(), |v| format!("{v:.17e}")),
            self.channel_peak, CHANNEL_OFF_A,
            self.last_channel_above.map_or_else(|| "none".into(), |v| format!("{v:.17e}")),
            self.channel_peak_after_detector, CHANNEL_OFF_A,
            self.last_channel_above_after_detector.map_or_else(|| "none".into(), |v| format!("{v:.17e}")),
            self.channel_peak_after_latch, CHANNEL_OFF_A,
            self.last_channel_above_after_latch.map_or_else(|| "none".into(), |v| format!("{v:.17e}")),
            self.body_peak, self.il_peak, self.f2_peak, self.d1_peak, format!("{:.17e}", self.d2_peak),
        );
        for group in self.equal_groups {
            report.push_str(&format!("equal_group_time_s={:.17e} threshold_crossing={} left=", group.time, group.threshold_crossing));
            if let Some((index, values)) = group.left {
                report.push_str(&format!("row_index={index}:{}", format_values(&values)));
            } else {
                report.push_str("none");
            }
            report.push_str(" group=");
            for (member, (index, row)) in group.group.iter().enumerate() {
                if member != 0 { report.push(';'); }
                report.push_str(&format!("row_index={index}:{}", format_values(row)));
            }
            report.push_str(" right=");
            if let Some((index, values)) = group.right {
                report.push_str(&format!("row_index={index}:{}", format_values(&values)));
            } else {
                report.push_str("none");
            }
            report.push('\n');
        }
        Ok(report)
    }
}

fn format_values(values: &[f64]) -> String { values.iter().map(|value| format!("{value:.17e}")).collect::<Vec<_>>().join(",") }

fn normalize_stream<R: BufRead, W1: Write, W2: Write>(
    mut input: R,
    checked: &mut W1,
    supplemental: &mut W2,
    cfg: Config,
) -> Result<String, String> {
    if !cfg.tstop.is_finite()
        || cfg.tstop <= 0.0
        || !cfg.mutation_time.is_finite()
        || cfg.mutation_time <= 0.0
        || !cfg.event_window.is_finite()
        || cfg.event_window <= 0.0
        || !cfg.max_gap.is_finite()
        || cfg.max_gap <= 0.0
    {
        return Err("invalid positive trace bounds".into());
    }
    let mut header = String::new();
    input
        .read_line(&mut header)
        .map_err(|e| format!("read header: {e}"))?;
    let columns: Vec<String> = header.split_whitespace().map(str::to_string).collect();
    if columns.is_empty() {
        return Err("missing trace header".into());
    }
    let idx = indices(&columns)?;
    writeln!(checked, "{CHECKED_HEADER}").map_err(|e| format!("write checked header: {e}"))?;
    writeln!(supplemental, "{SUPP_HEADER}")
        .map_err(|e| format!("write supplemental header: {e}"))?;
    let mut state = StreamState::default();
    let mut line = String::new();
    let mut line_no = 1usize;
    loop {
        line.clear();
        if input
            .read_line(&mut line)
            .map_err(|e| format!("read row: {e}"))?
            == 0
        {
            break;
        }
        line_no += 1;
        if line.trim().is_empty() {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        let row = parse_row(&fields, line_no, columns.len(), &idx)?;
        let raw = fields.iter().map(|field| field.parse::<f64>().map_err(|_| format!("row {line_no}: invalid raw field"))).collect::<Result<Vec<_>, _>>()?;
        state.observe(row, &raw, cfg, checked, supplemental)?;
    }
    let receipt = state.finish(cfg)?;
    checked.flush().map_err(|e| format!("flush checked: {e}"))?;
    supplemental
        .flush()
        .map_err(|e| format!("flush supplemental: {e}"))?;
    Ok(receipt)
}

fn parse_bound(args: &[String], index: usize, name: &str) -> Result<f64, String> {
    args.get(index)
        .ok_or_else(|| format!("missing {name}"))?
        .parse::<f64>()
        .map_err(|_| format!("invalid {name}"))
}

fn run_cli(args: &[String]) -> Result<(), String> {
    if args.len() != 10 {
        return Err("usage: fault_normalize RAW CHECKED SUPPLEMENT REPORT TSTOP KIND MUTATION_S EVENT_WINDOW MAX_GAP".into());
    }
    let cfg = Config {
        tstop: parse_bound(args, 5, "TSTOP")?,
        kind: Kind::parse(&args[6])?,
        mutation_time: parse_bound(args, 7, "MUTATION_S")?,
        event_window: parse_bound(args, 8, "EVENT_WINDOW")?,
        max_gap: parse_bound(args, 9, "MAX_GAP")?,
    };
    let input = fs::File::open(&args[1]).map_err(|e| format!("read input: {e}"))?;
    let checked_file = fs::File::create(&args[2]).map_err(|e| format!("write checked: {e}"))?;
    let supplemental_file =
        fs::File::create(&args[3]).map_err(|e| format!("write supplemental: {e}"))?;
    let mut checked = BufWriter::new(checked_file);
    let mut supplemental = BufWriter::new(supplemental_file);
    let report = normalize_stream(BufReader::new(input), &mut checked, &mut supplemental, cfg)?;
    let mut file = fs::File::create(&args[4]).map_err(|e| format!("write report: {e}"))?;
    file.write_all(report.as_bytes())
        .map_err(|e| format!("write report: {e}"))?;
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    match run_cli(&args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("REJECTED fault normalizer: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
fn normalize(input: &str, cfg: Config) -> Result<(String, String, String), String> {
    let mut checked = Vec::new();
    let mut supplemental = Vec::new();
    let report = normalize_stream(
        io::Cursor::new(input.as_bytes()),
        &mut checked,
        &mut supplemental,
        cfg,
    )?;
    Ok((
        String::from_utf8(checked).map_err(|e| e.to_string())?,
        String::from_utf8(supplemental).map_err(|e| e.to_string())?,
        report,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    struct FlushFailWriter(Vec<u8>);

    impl Write for FlushFailWriter {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Err(io::Error::other("synthetic flush failure"))
        }
    }

    const RAW_HEADER: &str = "time v(acsrc) v(acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject) extra";

    fn fixture() -> String {
        let mut out = format!("{RAW_HEADER}\n");
        for i in 0..20 {
            let t = i as f64 * 1e-9;
            let f2 = if i < 10 { 5.0 } else { 0.0 };
            let inject = if i < 10 { 0.0 } else { 5.0 };
            let fault = if i < 12 { 0.0 } else { 5.0 };
            let q = if i < 13 { 5.0 } else { 0.0 };
            let en = if i < 13 { 5.0 } else { 0.0 };
            out.push_str(&format!(
                "{t} 120 0 400 390 10 0 1 2 0 3 {q} {en} {fault} {f2} 0 5 5 0.1 0.2 0.3 {inject} 99\n"
            ));
        }
        out
    }

    fn cfg(kind: Kind) -> Config {
        Config {
            tstop: 19e-9,
            kind,
            mutation_time: 10e-9,
            event_window: 2e-9,
            max_gap: 2e-9,
        }
    }

    #[test]
    fn positive_exact_header_and_outputs() {
        let (checked, supplemental, receipt) = normalize(&fixture(), cfg(Kind::F2Crest)).unwrap();
        assert_eq!(checked.lines().next().unwrap(), CHECKED_HEADER);
        assert_eq!(supplemental.lines().next().unwrap(), SUPP_HEADER);
        assert!(receipt.contains("status=SCHEMA_AND_EVIDENCE_OK"));
        assert!(receipt.contains("detector_rise_s="));
        assert!(receipt.contains("channel_peak_after_detector_a=2.00000000000000000e0"));
        assert!(receipt.contains("channel_peak_after_latch_a=2.00000000000000000e0"));
        assert!(!receipt.contains("channel_last_above_0.10a_after_latch_s=none"));
        assert_eq!(checked.lines().count(), 21);
        assert_eq!(supplemental.lines().count(), 21);
    }

    #[test]
    fn f2_start_label_uses_the_same_transport_contract() {
        let (checked, supplemental, receipt) = normalize(&fixture(), cfg(Kind::F2Start)).unwrap();
        assert_eq!(checked.lines().count(), 21);
        assert_eq!(supplemental.lines().count(), 21);
        assert!(receipt.contains("status=SCHEMA_AND_EVIDENCE_OK"));
        assert!(receipt.contains("planned_kind=F2Start"));
    }

    #[test]
    fn f2_start_without_transition_is_rejected() {
        let text = fixture()
            .lines()
            .enumerate()
            .map(|(line_no, line)| {
                if line_no == 0 {
                    return line.to_string();
                }
                let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                fields[14] = "5".into();
                fields.join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(normalize(&text, cfg(Kind::F2Start)).is_err());
    }

    #[test]
    fn f2_start_with_unarmed_prefix_is_rejected() {
        let text = fixture()
            .lines()
            .enumerate()
            .map(|(line_no, line)| {
                if line_no == 0 {
                    return line.to_string();
                }
                let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                if line_no < 10 {
                    fields[16] = "0".into();
                }
                fields.join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(normalize(&text, cfg(Kind::F2Start)).is_err());
    }

    #[test]
    fn sw_short_alias_is_accepted() {
        assert_eq!(Kind::parse("sw-short"), Ok(Kind::SwitchShort));
        assert_eq!(Kind::parse("switch-short"), Ok(Kind::SwitchShort));
    }

    #[test]
    fn bypass_negative_still_requires_f2_transition() {
        let text = fixture()
            .lines()
            .enumerate()
            .map(|(line_no, line)| {
                if line_no == 0 {
                    return line.to_string();
                }
                let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                fields[14] = "5".into();
                fields.join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(normalize(&text, cfg(Kind::BypassNeg)).is_err());
    }

    #[test]
    fn streaming_positive_preserves_exact_headers() {
        let mut checked = Vec::new();
        let mut supplemental = Vec::new();
        let receipt = normalize_stream(
            std::io::Cursor::new(fixture().into_bytes()),
            &mut checked,
            &mut supplemental,
            cfg(Kind::F2Crest),
        )
        .unwrap();
        assert!(receipt.contains("status=SCHEMA_AND_EVIDENCE_OK"));
        assert_eq!(
            String::from_utf8(checked).unwrap().lines().next().unwrap(),
            CHECKED_HEADER
        );
        assert_eq!(
            String::from_utf8(supplemental)
                .unwrap()
                .lines()
                .next()
                .unwrap(),
            SUPP_HEADER
        );
    }

    #[test]
    fn ngspice_sensor_branch_headers_are_mapped() {
        let mut lines: Vec<String> = fixture().lines().map(str::to_string).collect();
        lines[0] = lines[0]
            .replace("v(acsrc) v(acn)", "v(acsrc,acn)")
            .replace("i(Vchannel)", "vchannel#branch")
            .replace("i(Vbody)", "vbody#branch")
            .replace("i(Vf2sense)", "vf2sense#branch")
            .replace("i(Vdboost1sense)", "vdboost1sense#branch")
            .replace("i(Vdboost2sense)", "vdboost2sense#branch");
        for line in lines.iter_mut().skip(1) {
            let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
            fields.remove(2); // remove v(acn); direct line voltage remains
            *line = fields.join(" ");
        }
        let (checked, _, _) = normalize(&lines.join("\n"), cfg(Kind::F2Crest)).unwrap();
        assert_eq!(checked.lines().count(), 21);
    }

    #[test]
    fn wrong_mutation_kind_is_rejected() {
        let text = fixture()
            .lines()
            .enumerate()
            .map(|(line_no, line)| {
                if line_no == 0 {
                    return line.to_string();
                }
                let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                fields[14] = "5".into();
                fields.join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(normalize(&text, cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn missing_required_column_is_rejected() {
        let text = fixture()
            .lines()
            .map(|line| {
                line.split_whitespace()
                    .filter(|field| *field != "i(Vbody)")
                    .collect::<Vec<_>>()
                    .join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        assert!(normalize(&text, cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn nonfinite_extra_column_is_rejected() {
        let text = fixture().replace(" 99\n", " NaN\n");
        assert!(normalize(&text, cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn derived_ac_overflow_is_rejected() {
        let text = fixture().replace("120 0 400", "1.7e308 -1.7e308 400");
        assert!(normalize(&text, cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn duplicate_header_is_rejected_globally() {
        let text = fixture().replace(" v(fault_inject) extra", " v(fault_inject) v(vd)");
        assert!(normalize(&text, cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn nonmonotone_time_is_rejected() {
        let mut lines: Vec<String> = fixture().lines().map(str::to_string).collect();
        let mut fields: Vec<_> = lines[11].split_whitespace().map(str::to_string).collect();
        fields[0] = "8.5e-9".into();
        lines[11] = fields.join(" ");
        assert!(normalize(&lines.join("\n"), cfg(Kind::F2Crest)).is_err());
    }

    #[test]
    fn benign_equal_time_group_is_preserved() {
        let mut lines: Vec<String> = fixture().lines().map(str::to_string).collect();
        lines.insert(12, lines[11].clone());
        let (_, _, report) = normalize(&lines.join("\n"), cfg(Kind::F2Crest)).unwrap();
        assert!(report.contains("status=SCHEMA_AND_EVIDENCE_OK"));
        assert!(report.contains("original_rows=21"));
        assert!(report.contains("equal_time_groups=1"));
        assert!(report.contains("equal_time_raw_rows=4"));
        assert!(report.contains("left=row_index=9:"));
        assert!(report.contains("group=row_index=10:"));
        assert!(report.contains("row_index=11:"));
        assert!(report.contains("right=row_index=12:"));
    }

    #[test]
    fn equal_time_threshold_crossing_is_indeterminate() {
        let mut lines: Vec<String> = fixture().lines().map(str::to_string).collect();
        let mut fields: Vec<_> = lines[11].split_whitespace().map(str::to_string).collect();
        fields[11] = "0".into();
        lines.insert(12, fields.join(" "));
        let (_, _, report) = normalize(&lines.join("\n"), cfg(Kind::F2Crest)).unwrap();
        assert!(report.contains("status=INDETERMINATE_EQUAL_TIME_THRESHOLD_CROSSING"));
        assert!(report.contains("threshold_crossing=true"));
    }

    #[test]
    fn exact_logic_threshold_to_high_is_indeterminate() {
        let mut lines: Vec<String> = fixture().lines().map(str::to_string).collect();
        let mut first: Vec<_> = lines[11].split_whitespace().map(str::to_string).collect();
        first[11] = "2.5".into();
        lines[11] = first.join(" ");
        let mut duplicate: Vec<_> = lines[11].split_whitespace().map(str::to_string).collect();
        duplicate[11] = "5".into();
        lines.insert(12, duplicate.join(" "));
        let (_, _, report) = normalize(&lines.join("\n"), cfg(Kind::F2Crest)).unwrap();
        assert!(report.contains("status=INDETERMINATE_EQUAL_TIME_THRESHOLD_CROSSING"));
        assert!(report.contains("threshold_crossing=true"));
    }

    #[test]
    fn boundary_predicates_match_edge_and_retention_semantics() {
        // Injection/F2/fault edges use >=: 0 -> 2.5 is a crossing.
        assert!(crosses_ge(0.0, 2.5, LOGIC_HIGH));
        // Health and channel retention use >: 2.5 -> 5 is a crossing, while
        // landing exactly on the channel threshold is not yet above it.
        assert!(crosses_gt(2.5, 5.0, LOGIC_HIGH));
        assert!(!crosses_gt(0.0, CHANNEL_OFF_A, CHANNEL_OFF_A));
        assert!(crosses_gt(CHANNEL_OFF_A, 0.11, CHANNEL_OFF_A));
        // Gate-off is inclusive, so the exact 0.20 boundary is the edge.
        assert!(crosses_le(0.20, 0.21, 0.20));
    }

    #[test]
    fn prefault_health_requires_strictly_above_2_5v() {
        for field_index in [11usize, 12, 16, 17] {
            let text = fixture()
                .lines()
                .enumerate()
                .map(|(line_no, line)| {
                    if line_no == 0 { return line.to_string(); }
                    let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                    if line_no == 9 { fields[field_index] = "2.5".into(); }
                    fields.join(" ")
                })
                .collect::<Vec<_>>()
                .join("\n");
            assert!(normalize(&text, cfg(Kind::F2Crest)).is_err(), "field {field_index} equality must fail prefault health");
        }
    }

    #[test]
    fn latch_off_accepts_q_and_en_at_the_2_5v_boundary() {
        let text = fixture()
            .lines()
            .enumerate()
            .map(|(line_no, line)| {
                if line_no == 0 { return line.to_string(); }
                let mut fields: Vec<_> = line.split_whitespace().map(str::to_string).collect();
                if line_no == 14 {
                    fields[11] = "2.5".into();
                    fields[12] = "2.5".into();
                }
                fields.join(" ")
            })
            .collect::<Vec<_>>()
            .join("\n");
        let (_, _, report) = normalize(&text, cfg(Kind::F2Crest)).unwrap();
        assert!(report.contains("latch_off_s=") && !report.contains("latch_off_s=none"));
    }

    #[test]
    fn equal_row_cap_includes_left_context_clone() {
        let row = Row {
            t: 1e-9, ac: 0.0, vd: 0.0, vb: 0.0, sw: 0.0, gate: 0.0,
            il: 0.0, channel: 0.0, body: 0.0, vac: 0.0, q: 5.0, en: 5.0,
            fault: 0.0, f2ctl: 5.0, standby: 0.0, arm: 5.0, permit: 5.0,
            f2_current: 0.0, d1_current: 0.0, d2_current: 0.0, inject: 0.0,
        };
        let raw = vec![0.0; 23];
        let mut state = StreamState {
            count: 2,
            previous: Some(row),
            previous_raw: Some(raw.clone()),
            before_previous_raw: Some(raw.clone()),
            equal_raw_rows: MAX_EQUAL_ROWS - 2,
            ..StreamState::default()
        };
        let mut checked = Vec::new();
        let mut supplemental = Vec::new();
        let error = state
            .observe(row, &raw, cfg(Kind::SwitchShort), &mut checked, &mut supplemental)
            .expect_err("left context must count against equal-row cap");
        assert!(error.contains("equal-time group/raw-row cap"));
    }

    #[test]
    fn output_flush_failure_is_reported() {
        let mut checked = FlushFailWriter(Vec::new());
        let mut supplemental = Vec::new();
        let error = normalize_stream(
            std::io::Cursor::new(fixture().into_bytes()),
            &mut checked,
            &mut supplemental,
            cfg(Kind::F2Crest),
        )
        .expect_err("synthetic checked-output flush must fail");
        assert!(error.contains("flush checked"));
    }
}
