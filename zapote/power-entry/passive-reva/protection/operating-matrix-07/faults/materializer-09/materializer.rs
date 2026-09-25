//! Preparation-only materializer for matrix-07 mechanical fault decks.
//!
//! This binary copies the reviewed hysteretic-driver source closure, applies
//! only case-specific graph/control edits, adds receipt-bound diagnostics, and
//! writes a fresh unexecuted output directory.  It deliberately never starts
//! ngspice or creates an accepted operating-point receipt.

use std::{
    collections::BTreeSet,
    env,
    fmt::Write as _,
    fs,
    io::Write as IoWrite,
    path::{Path, PathBuf},
    process::{Command, ExitCode, Stdio},
};

const CLOSURE: [&str; 6] = [
    "cold.cir",
    "ucc28180-pwm-latch.inc",
    "protection.inc",
    "standby.inc",
    "clamp.inc",
    "authored_logic_hysteretic.inc",
];
const MAX_PACING_POINTS: u64 = 2_000_000;
const PACING_STEP: f64 = 25e-9;
const MIN_PREFAULT_WINDOW: f64 = 1e-6;
const EVENT_EDGE: f64 = 1e-9;

const TSTOP_PREFIX: &str = ".param RLOAD=190 TSTOP=";
const TSTOP_SUFFIX: &str = " STEP=500n";
const F2_CONTROL_LINE: &str = "Vf2ctl f2ctl 0 5";
const F2_PATH_LINE: &str = "Sf2 vd vb f2ctl 0 SWF2";
const D1_PATH_LINE: &str = "Dboost1 sw vd DBOOST";
const D2_PATH_LINE: &str = "Dboost2 sw vd DBOOST";
const BYPASS_PARAM_LINE: &str = ".param FAULT_TAU=79.3n EN_TAU=18.75n BYPASS=0";
const ORIGINAL_SAVE_PREFIX: &str = ".save time ";

const FAULT_SAVE: &str = ".save time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject)";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CaseKind {
    F2Crest,
    F2Zero,
    F2Start,
    SwitchShort,
    DiodeShort,
    BothShort,
    BypassNeg,
}

impl CaseKind {
    fn parse(value: &str) -> Result<Self, String> {
        let key = value.to_ascii_uppercase().replace('-', "").replace('_', "");
        match key.as_str() {
            "F2CREST" => Ok(Self::F2Crest),
            "F2ZERO" => Ok(Self::F2Zero),
            "F2START" => Ok(Self::F2Start),
            "SWSHORT" => Ok(Self::SwitchShort),
            "DIODESHORT" => Ok(Self::DiodeShort),
            "BOTHSHORT" => Ok(Self::BothShort),
            "BYPASSNEG" => Ok(Self::BypassNeg),
            _ => Err(format!("unknown case kind: {value}")),
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::F2Crest => "F2-CREST",
            Self::F2Zero => "F2-ZERO",
            Self::F2Start => "F2-START",
            Self::SwitchShort => "SW-SHORT",
            Self::DiodeShort => "DIODE-SHORT",
            Self::BothShort => "BOTH-SHORT",
            Self::BypassNeg => "BYPASS-NEG",
        }
    }

    fn needs_f2(self) -> bool {
        matches!(
            self,
            Self::F2Crest | Self::F2Zero | Self::F2Start | Self::BypassNeg
        )
    }

    fn needs_switch_short(self) -> bool {
        matches!(self, Self::SwitchShort | Self::BothShort)
    }

    fn needs_diode_short(self) -> bool {
        matches!(self, Self::DiodeShort | Self::BothShort)
    }

    fn bypass(self) -> bool {
        matches!(self, Self::BypassNeg)
    }
}

#[derive(Clone, Copy, Debug)]
struct Params {
    fault: f64,
    stop: f64,
    prefault_window: f64,
}

impl Params {
    fn parse(fault: &str, stop: &str, prefault_window: &str) -> Result<Self, String> {
        let fault = fault
            .parse::<f64>()
            .map_err(|_| "T_FAULT is not a number".to_string())?;
        let stop = stop
            .parse::<f64>()
            .map_err(|_| "TSTOP is not a number".to_string())?;
        let prefault_window = prefault_window
            .parse::<f64>()
            .map_err(|_| "PREFAULT_WINDOW is not a number".to_string())?;
        if !fault.is_finite()
            || !stop.is_finite()
            || !prefault_window.is_finite()
            || fault <= 0.0
            || stop <= 0.0
            || prefault_window <= 0.0
        {
            return Err("T_FAULT, TSTOP, and PREFAULT_WINDOW must be finite and positive".into());
        }
        if prefault_window < MIN_PREFAULT_WINDOW {
            return Err("PREFAULT_WINDOW must be at least 1 us".into());
        }
        if stop <= fault {
            return Err("TSTOP must be strictly greater than T_FAULT".into());
        }
        let pacing_start = fault - prefault_window - PACING_STEP;
        if pacing_start <= 0.0 {
            return Err("T_FAULT must exceed PREFAULT_WINDOW plus the 25 ns boundary lead".into());
        }
        let points = pacing_point_count(pacing_start, stop);
        if points > MAX_PACING_POINTS {
            return Err(format!(
                "pacing window requires {points} points, above safety limit {MAX_PACING_POINTS}"
            ));
        }
        Ok(Self {
            fault,
            stop,
            prefault_window,
        })
    }
}

fn spice_time(value: f64) -> String {
    format!("{value:.12e}")
}

/// Number of source points in the paced interval, including both boundaries.
///
/// Floating point division can turn an exactly integral interval count into
/// `N + epsilon`; blindly using `ceil` then emits the stop time twice.  Treat
/// values within a small relative tolerance of an integer as integral so the
/// generated PWL remains strictly increasing.
fn pacing_point_count(start: f64, stop: f64) -> u64 {
    let ratio = (stop - start) / PACING_STEP;
    let nearest = ratio.round();
    let intervals = if (ratio - nearest).abs() <= 1e-12 * ratio.abs().max(1.0) {
        nearest as u64
    } else {
        ratio.floor() as u64 + 1
    };
    intervals + 1
}

fn replace_exact(text: &str, needle: &str, replacement: &str) -> Result<String, String> {
    let count = text.match_indices(needle).count();
    if count != 1 {
        return Err(format!(
            "expected exactly one occurrence of {:?}, found {count}",
            needle
        ));
    }
    Ok(text.replacen(needle, replacement, 1))
}

/// Return the one narrowly supported RLOAD/TSTOP/STEP parameter line.
///
/// This intentionally accepts only the source form used by the reviewed
/// decks.  TSTOP may be a finite positive plain-seconds value or a finite
/// positive value with the SPICE `m` suffix (milli), but RLOAD and STEP remain
/// exact literals.  We inspect every matching line so duplicate, malformed,
/// or ambiguous source contracts fail closed.
fn source_tstop_line(text: &str) -> Result<String, String> {
    let candidates: Vec<&str> = text
        .lines()
        .filter(|line| line.starts_with(TSTOP_PREFIX))
        .collect();
    if candidates.len() != 1 {
        return Err(format!(
            "expected exactly one RLOAD/TSTOP/STEP line, found {}",
            candidates.len()
        ));
    }
    let line = candidates[0];
    if !line.ends_with(TSTOP_SUFFIX) {
        return Err("RLOAD/TSTOP/STEP line has an unsupported suffix".into());
    }
    let value = &line[TSTOP_PREFIX.len()..line.len() - TSTOP_SUFFIX.len()];
    let seconds = if let Some(milli) = value.strip_suffix('m') {
        milli
            .parse::<f64>()
            .map(|value| value * 1e-3)
            .map_err(|_| "TSTOP milli value is not a number".to_string())?
    } else {
        value
            .parse::<f64>()
            .map_err(|_| "TSTOP seconds value is not a number".to_string())?
    };
    if !seconds.is_finite() || seconds <= 0.0 {
        return Err("TSTOP must be finite and positive".into());
    }
    Ok(line.to_string())
}

fn pacing_block(params: Params) -> Result<(String, u64), String> {
    let start = params.fault - params.prefault_window - PACING_STEP;
    let points = pacing_point_count(start, params.stop);
    if points > MAX_PACING_POINTS {
        return Err(format!("pacing window requires {points} points"));
    }
    let mut out = String::from(
        "* Isolated timing instrument: alternating 25 ns corners from T_FAULT-PREFAULT_WINDOW-25ns to TSTOP.\n* This source is not a fault marker and its 1 Gohm load requires production revalidation.\nVschedule schedule_probe 0 PWL(\n",
    );
    for i in 0..points {
        let time = if i + 1 == points {
            params.stop
        } else {
            start + i as f64 * PACING_STEP
        };
        let value = i % 2;
        writeln!(out, "+ {} {value}", spice_time(time)).expect("String write cannot fail");
    }
    out.push_str("+ )\nRschedule_probe schedule_probe 0 1G\n");
    Ok((out, points))
}

fn marker_line(case: CaseKind) -> &'static str {
    match case {
        CaseKind::F2Crest | CaseKind::F2Zero | CaseKind::F2Start | CaseKind::BypassNeg => {
            "Bfault_inject fault_inject 0 V=5-V(f2ctl)"
        }
        CaseKind::SwitchShort => "Bfault_inject fault_inject 0 V=V(swfail_ctl)",
        CaseKind::DiodeShort => "Bfault_inject fault_inject 0 V=V(dshort_ctl)",
        CaseKind::BothShort => "Bfault_inject fault_inject 0 V=max(V(swfail_ctl),V(dshort_ctl))",
    }
}

fn f2_control(params: Params) -> String {
    let f = spice_time(params.fault);
    let stop = spice_time(params.stop);
    let before = spice_time(params.fault - EVENT_EDGE);
    format!("Vf2ctl f2ctl 0 PWL(0 5 {{{before}}} 5 {{{f}}} 0 {{{stop}}} 0)")
}

fn event_controls(case: CaseKind, params: Params) -> String {
    let f = spice_time(params.fault);
    let stop = spice_time(params.stop);
    let before = spice_time(params.fault - EVENT_EDGE);
    let mut out = String::new();
    if case.needs_switch_short() {
        writeln!(
            out,
            "Vswfail_ctl swfail_ctl 0 PWL(0 0 {{{before}}} 0 {{{f}}} 5 {{{stop}}} 5)"
        )
        .unwrap();
    }
    if case.needs_diode_short() {
        writeln!(
            out,
            "Vdshort_ctl dshort_ctl 0 PWL(0 0 {{{before}}} 0 {{{f}}} 5 {{{stop}}} 5)"
        )
        .unwrap();
    }
    out
}

fn topology_additions(case: CaseKind) -> String {
    let mut out = String::new();
    if case.needs_switch_short() {
        out.push_str(
            "* Failed-short surrogate; gate-off cannot interrupt this parallel branch.\nSswfail sw channel_source swfail_ctl 0 SWFAIL\n.model SWFAIL SW(Ron=1m Roff=1e12 Vt=2.5 Vh=.1)\n",
        );
    }
    if case.needs_diode_short() {
        out.push_str(
            "* One boost leg shorted in parallel with Dboost1; its sense source captures the full leg.\nSdiodeshort sw d1_path dshort_ctl 0 SWDIODESHORT\n.model SWDIODESHORT SW(Ron=1m Roff=1e12 Vt=2.5 Vh=.1)\n",
        );
    }
    out
}

fn injected_block(case: CaseKind, params: Params) -> Result<String, String> {
    let controls = event_controls(case, params);
    let additions = topology_additions(case);
    let (pacing, _) = pacing_block(params)?;
    let marker = marker_line(case);
    Ok(format!(
        "* Prepared case {} at T_FAULT={} TSTOP={}.\n* The marker is derived from the actual control waveform, never from hard time.\n* SW Vt=2.5 V with Vh=.1 V means nominal rising/falling thresholds are about 2.6/2.4 V; the marker threshold is 2.5 V.\n* The 1 ns finite PWL edge bounds source-command ambiguity to 1 ns plus accepted solver sampling.\n{}{}{}\n{}\n",
        case.name(),
        spice_time(params.fault),
        spice_time(params.stop),
        controls,
        additions,
        marker,
        pacing
    ))
}

fn save_addition() -> String {
    format!(
        "* Original normal diagnostics remain above. Fault checker schema plus four branch/marker extras follow.\n{}\n",
        FAULT_SAVE
    )
}

fn materialize_text(mut cold: String, case: CaseKind, params: Params) -> Result<String, String> {
    let original_tstop_line = source_tstop_line(&cold)?;
    cold = replace_exact(
        &cold,
        &original_tstop_line,
        &format!(
            ".param RLOAD=190 TSTOP={} STEP=500n\n.param T_FAULT={}",
            spice_time(params.stop),
            spice_time(params.fault)
        ),
    )?;
    cold = replace_exact(
        &cold,
        F2_PATH_LINE,
        "Sf2 vd f2_path f2ctl 0 SWF2\nVf2sense f2_path vb 0",
    )?;
    cold = replace_exact(
        &cold,
        D1_PATH_LINE,
        "Dboost1 sw d1_path DBOOST\nVdboost1sense d1_path vd 0",
    )?;
    cold = replace_exact(
        &cold,
        D2_PATH_LINE,
        "Dboost2 sw d2_path DBOOST\nVdboost2sense d2_path vd 0",
    )?;
    if case.needs_f2() {
        cold = replace_exact(&cold, F2_CONTROL_LINE, &f2_control(params))?;
    }
    let fault_comment = injected_block(case, params)?;
    let save_anchor = cold
        .lines()
        .find(|line| line.starts_with(ORIGINAL_SAVE_PREFIX))
        .map(str::to_owned)
        .ok_or_else(|| "original .save line is missing".to_string())?;
    let save_add = save_addition();
    cold = replace_exact(&cold, &save_anchor, &format!("{save_anchor}\n{save_add}"))?;
    let options_anchor = ".options method=trap";
    cold = replace_exact(
        &cold,
        options_anchor,
        &format!("{fault_comment}{options_anchor}"),
    )?;
    Ok(cold)
}

#[cfg(test)]
fn reverse_materialized(
    mut deck: String,
    case: CaseKind,
    params: Params,
    original_tstop_line: &str,
) -> Result<String, String> {
    let options_anchor = ".options method=trap";
    let block = injected_block(case, params)?;
    let block_with_options = format!("{block}{options_anchor}");
    deck = replace_exact(&deck, &block_with_options, options_anchor)?;
    let save_add = save_addition();
    // materialize_text inserts a separator newline before the diagnostic
    // comment. Remove that separator together with the comment so the
    // original .save line's single trailing newline is restored exactly.
    deck = replace_exact(&deck, &format!("\n{save_add}"), "")?;
    if case.needs_f2() {
        deck = replace_exact(&deck, &f2_control(params), F2_CONTROL_LINE)?;
    }
    deck = replace_exact(
        &deck,
        "Dboost1 sw d1_path DBOOST\nVdboost1sense d1_path vd 0",
        D1_PATH_LINE,
    )?;
    deck = replace_exact(
        &deck,
        "Dboost2 sw d2_path DBOOST\nVdboost2sense d2_path vd 0",
        D2_PATH_LINE,
    )?;
    deck = replace_exact(
        &deck,
        "Sf2 vd f2_path f2ctl 0 SWF2\nVf2sense f2_path vb 0",
        F2_PATH_LINE,
    )?;
    deck = replace_exact(
        &deck,
        &format!(
            ".param RLOAD=190 TSTOP={} STEP=500n\n.param T_FAULT={}",
            spice_time(params.stop),
            spice_time(params.fault)
        ),
        original_tstop_line,
    )?;
    Ok(deck)
}

fn locate_source(source: &Path) -> Result<PathBuf, String> {
    let canonical = source
        .canonicalize()
        .map_err(|e| format!("source directory: {e}"))?;
    if !canonical.is_dir() {
        return Err("source path is not a directory".into());
    }
    for name in CLOSURE {
        let metadata = fs::symlink_metadata(canonical.join(name))
            .map_err(|e| format!("source closure {name}: {e}"))?;
        if metadata.file_type().is_symlink() {
            return Err(format!("source closure rejects symlink {name}"));
        }
        if !metadata.is_file() {
            return Err(format!("source closure missing {name}"));
        }
    }
    let expected: BTreeSet<String> = CLOSURE.iter().map(|name| (*name).to_string()).collect();
    let mut discovered = BTreeSet::new();
    let mut pending = vec!["cold.cir".to_string()];
    while let Some(name) = pending.pop() {
        if !discovered.insert(name.clone()) {
            continue;
        }
        let text = fs::read_to_string(canonical.join(&name))
            .map_err(|e| format!("read included source {name}: {e}"))?;
        for line in text.lines() {
            let fields: Vec<_> = line.split_whitespace().collect();
            if fields.first() == Some(&".include") {
                let include = fields
                    .get(1)
                    .ok_or_else(|| format!("include in {name} has no path"))?;
                if include.contains('/') || include.contains('\\') {
                    return Err(format!("source include path is not local: {include}"));
                }
                if !expected.contains(*include) {
                    return Err(format!("unexpected source include {include}"));
                }
                pending.push((*include).to_string());
            }
        }
    }
    if discovered != expected {
        return Err(format!(
            "source include closure mismatch: discovered {:?}, expected {:?}",
            discovered, expected
        ));
    }
    Ok(canonical)
}

fn materialize(source: &Path, case: CaseKind, params: Params, output: &Path) -> Result<(), String> {
    if output.exists() {
        return Err("output directory already exists; use a fresh directory".into());
    }
    let source = locate_source(source)?;
    fs::create_dir_all(output).map_err(|e| format!("create output: {e}"))?;
    let mut hashes = Vec::new();
    for name in CLOSURE {
        let bytes = fs::read(source.join(name)).map_err(|e| format!("read {name}: {e}"))?;
        let mut output_bytes = bytes.clone();
        if case.bypass() && name == "protection.inc" {
            let protection = String::from_utf8(bytes.clone())
                .map_err(|e| format!("decode protection.inc: {e}"))?;
            output_bytes = replace_exact(
                &protection,
                BYPASS_PARAM_LINE,
                ".param FAULT_TAU=79.3n EN_TAU=18.75n BYPASS=1",
            )?
            .into_bytes();
        }
        fs::write(output.join(name), &output_bytes).map_err(|e| format!("write {name}: {e}"))?;
        hashes.push((name, sha256_hex(&bytes)?));
    }
    let cold =
        fs::read_to_string(source.join("cold.cir")).map_err(|e| format!("read cold.cir: {e}"))?;
    let deck = materialize_text(cold, case, params)?;
    fs::write(output.join("case.cir"), deck).map_err(|e| format!("write case.cir: {e}"))?;
    let mut output_hashes = Vec::new();
    for name in CLOSURE.iter().chain(["case.cir"].iter()) {
        let bytes = fs::read(output.join(name)).map_err(|e| format!("read output {name}: {e}"))?;
        output_hashes.push((*name, sha256_hex(&bytes)?));
    }
    let (_, pacing_points) = pacing_block(params)?;
    let mut manifest = String::from("{\n");
    writeln!(manifest, "  \"status\": \"PREPARED_UNEXECUTED\",").unwrap();
    writeln!(manifest, "  \"case\": \"{}\",", case.name()).unwrap();
    writeln!(manifest, "  \"t_fault_s\": {:.17e},", params.fault).unwrap();
    writeln!(manifest, "  \"tstop_s\": {:.17e},", params.stop).unwrap();
    writeln!(
        manifest,
        "  \"prefault_window_s\": {:.17e},",
        params.prefault_window
    )
    .unwrap();
    writeln!(manifest, "  \"pacing_step_s\": {:.17e},", PACING_STEP).unwrap();
    writeln!(manifest, "  \"pacing_points\": {pacing_points},").unwrap();
    manifest.push_str("  \"fault_schema_columns\": 17,\n  \"branch_marker_extra_columns\": 4,\n");
    manifest.push_str("  \"source_closure_sha256\": {\n");
    for (i, (name, hash)) in hashes.iter().enumerate() {
        let comma = if i + 1 == hashes.len() { "" } else { "," };
        writeln!(manifest, "    \"{name}\": \"{hash}\"{comma}").unwrap();
    }
    manifest.push_str("  },\n  \"output_sha256\": {\n");
    for (i, (name, hash)) in output_hashes.iter().enumerate() {
        let comma = if i + 1 == output_hashes.len() {
            ""
        } else {
            ","
        };
        writeln!(manifest, "    \"{name}\": \"{hash}\"{comma}").unwrap();
    }
    manifest.push_str("  },\n  \"execution\": \"blocked until accepted source, event selection, and prefix instrumentation review\"\n}\n");
    fs::write(output.join("manifest.json"), manifest)
        .map_err(|e| format!("write manifest: {e}"))?;
    let readme = format!(
        "# {} prepared fault deck\n\nStatus: **PREPARED_UNEXECUTED**.\n\nThis directory was mechanically copied from the hysteretic-driver candidate and rewritten for T_FAULT={} s, TSTOP={} s, and the explicitly supplied PREFAULT_WINDOW={} s. It has not been simulated and carries no accepted operating-point claim.\n\nThe original normal `.save` diagnostics remain, followed by the exact 17-column fault schema and four branch/marker extras. F2 and both boost diode legs have ideal 0-V sense sources. The pacing source is isolated, alternates at 25 ns corners from T_FAULT-PREFAULT_WINDOW-25 ns through TSTOP, and is instrumentation that requires production revalidation.\n\nThe `fault_inject` marker is the actual control voltage continuously (`5-V(f2ctl)` for an F2 open, the switch-control voltage for a short, and the maximum of both for BOTH-SHORT); acceptance can threshold that marker at 2.5 V. SW models use approximately 2.6 V rising and 2.4 V falling thresholds around Vt=2.5 V, so marker/source timing is bounded by the 1 ns finite PWL edge plus accepted solver sampling, not an arbitrary hard-time marker.\n\nExecution remains blocked until the accepted normal source, event selection, and prefault instrumentation are reviewed.\n",
        case.name(),
        spice_time(params.fault),
        spice_time(params.stop),
        spice_time(params.prefault_window)
    );
    fs::write(output.join("README.md"), readme).map_err(|e| format!("write README: {e}"))?;
    Ok(())
}

fn usage() {
    eprintln!("usage: materializer SOURCE_DIR CASE T_FAULT_S TSTOP_S PREFAULT_WINDOW_S OUTPUT_DIR");
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args().collect();
    if args.len() != 7 {
        usage();
        return ExitCode::FAILURE;
    }
    let case = match CaseKind::parse(&args[2]) {
        Ok(case) => case,
        Err(e) => {
            eprintln!("REJECTED {e}");
            return ExitCode::FAILURE;
        }
    };
    let params = match Params::parse(&args[3], &args[4], &args[5]) {
        Ok(params) => params,
        Err(e) => {
            eprintln!("REJECTED {e}");
            return ExitCode::FAILURE;
        }
    };
    match materialize(Path::new(&args[1]), case, params, Path::new(&args[6])) {
        Ok(()) => {
            println!("PREPARED_UNEXECUTED {} -> {}", case.name(), args[6]);
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("REJECTED {e}");
            ExitCode::FAILURE
        }
    }
}

fn sha256_hex(input: &[u8]) -> Result<String, String> {
    let mut child = Command::new("shasum")
        .args(["-a", "256"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|e| format!("start shasum -a 256: {e}"))?;
    child
        .stdin
        .take()
        .ok_or_else(|| "shasum stdin unavailable".to_string())?
        .write_all(input)
        .map_err(|e| format!("write shasum input: {e}"))?;
    let output = child
        .wait_with_output()
        .map_err(|e| format!("wait for shasum: {e}"))?;
    if !output.status.success() {
        return Err(format!("shasum failed with {}", output.status));
    }
    let hash = String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .next()
        .unwrap_or_default()
        .to_string();
    if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("shasum returned an invalid 256-bit digest".into());
    }
    Ok(hash)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn actual_source() -> PathBuf {
        let mut dir = env::current_dir().unwrap();
        loop {
            let candidate = dir.join("zapote/power-entry/passive-reva/protection/operating-matrix-07/normal-hysteretic-driver-candidate");
            if candidate.join("cold.cir").is_file() {
                return candidate;
            }
            if !dir.pop() {
                panic!("candidate source not found from current directory");
            }
        }
    }

    #[test]
    fn actual_source_inverse_proof_and_graph_paths() {
        let source = actual_source();
        let cold = fs::read_to_string(source.join("cold.cir")).unwrap();
        let original = cold.clone();
        let original_tstop_line = source_tstop_line(&cold).unwrap();
        assert_eq!(cold.matches(F2_PATH_LINE).count(), 1);
        assert_eq!(cold.matches(D1_PATH_LINE).count(), 1);
        assert_eq!(cold.matches(D2_PATH_LINE).count(), 1);
        assert_eq!(original_tstop_line, ".param RLOAD=190 TSTOP=500m STEP=500n");
        let params = Params::parse("0.000010", "0.000020", "0.000001").unwrap();
        let deck = materialize_text(cold, CaseKind::BothShort, params).unwrap();
        assert_eq!(original.matches(F2_PATH_LINE).count(), 1);
        assert!(deck.contains("Sf2 vd f2_path f2ctl 0 SWF2\nVf2sense f2_path vb 0"));
        assert!(deck.contains("Dboost1 sw d1_path DBOOST\nVdboost1sense d1_path vd 0"));
        assert!(deck.contains("Sdiodeshort sw d1_path dshort_ctl 0 SWDIODESHORT"));
        assert!(deck.contains("Sswfail sw channel_source swfail_ctl 0 SWFAIL"));
        assert!(!deck.contains("Sf2 vd vb f2ctl 0 SWF2"));
        assert!(!deck.contains("Dboost1 sw vd DBOOST"));
        assert!(deck.contains(FAULT_SAVE));
        assert!(deck.contains("Bfault_inject fault_inject 0 V=max(V(swfail_ctl),V(dshort_ctl))"));
        assert_eq!(deck.matches("Vf2ctl f2ctl 0 5").count(), 1);
        assert!(deck.contains("Vschedule schedule_probe 0 PWL("));
        assert_eq!(
            reverse_materialized(deck, CaseKind::BothShort, params, &original_tstop_line).unwrap(),
            original
        );
    }

    #[test]
    fn settling_extension_tstop_650m_preserves_exact_electrical_source_on_inverse() {
        let source = actual_source();
        let cold = fs::read_to_string(source.join("cold.cir")).unwrap();
        let extension = cold.replacen(
            ".param RLOAD=190 TSTOP=500m STEP=500n",
            ".param RLOAD=190 TSTOP=650m STEP=500n",
            1,
        );
        assert_eq!(
            source_tstop_line(&extension).unwrap(),
            ".param RLOAD=190 TSTOP=650m STEP=500n"
        );
        let params = Params::parse("0.000010", "0.000020", "0.000001").unwrap();
        let deck = materialize_text(extension.clone(), CaseKind::F2Start, params).unwrap();
        assert_eq!(
            reverse_materialized(
                deck,
                CaseKind::F2Start,
                params,
                ".param RLOAD=190 TSTOP=650m STEP=500n"
            )
            .unwrap(),
            extension
        );
    }

    #[test]
    fn source_tstop_contract_rejects_duplicate_malformed_and_nonpositive_values() {
        let source = actual_source();
        let cold = fs::read_to_string(source.join("cold.cir")).unwrap();
        let line = source_tstop_line(&cold).unwrap();
        assert_eq!(line, ".param RLOAD=190 TSTOP=500m STEP=500n");
        assert!(source_tstop_line(&format!("{cold}{line}\n")).is_err());
        assert!(
            source_tstop_line(&cold.replace(&line, ".param RLOAD=190 TSTOP=NaN STEP=500n"))
                .is_err()
        );
        assert!(
            source_tstop_line(&cold.replace(&line, ".param RLOAD=190 TSTOP=0m STEP=500n")).is_err()
        );
        assert!(source_tstop_line(
            &cold.replace(&line, ".param RLOAD=190 TSTOP=650m STEP=500n # extra")
        )
        .is_err());
    }

    #[test]
    fn every_named_case_has_an_independently_parseable_prepared_deck() {
        let source = actual_source();
        let cold = fs::read_to_string(source.join("cold.cir")).unwrap();
        let original_tstop_line = source_tstop_line(&cold).unwrap();
        let params = Params::parse("0.000010", "0.000020", "0.000001").unwrap();
        let cases = [
            CaseKind::F2Crest,
            CaseKind::F2Zero,
            CaseKind::F2Start,
            CaseKind::SwitchShort,
            CaseKind::DiodeShort,
            CaseKind::BothShort,
            CaseKind::BypassNeg,
        ];
        for case in cases {
            let deck = materialize_text(cold.clone(), case, params).unwrap();
            let reversed =
                reverse_materialized(deck.clone(), case, params, &original_tstop_line).unwrap();
            assert_eq!(
                reversed,
                cold,
                "inverse reconstruction failed for {}",
                case.name()
            );
            assert!(deck.contains(".param T_FAULT="));
            assert!(deck.contains(".param RLOAD=190 TSTOP="));
            assert!(deck.contains(".tran {STEP} {TSTOP} 0 {STEP} uic"));
            assert_eq!(deck.matches(FAULT_SAVE).count(), 1);
            assert_eq!(deck.matches("Bfault_inject fault_inject 0 V=").count(), 1);
            let marker_line = deck
                .lines()
                .find(|line| line.starts_with("Bfault_inject fault_inject"))
                .unwrap();
            assert!(!marker_line.contains('*'));
            assert!(
                marker_line.contains("V=5-V(f2ctl)")
                    || marker_line.contains("V=V(swfail_ctl)")
                    || marker_line.contains("V=V(dshort_ctl)")
                    || marker_line.contains("V=max(V(swfail_ctl),V(dshort_ctl))")
            );
            assert!(deck.contains("+ )\nRschedule_probe schedule_probe 0 1G"));
            let mut schedule_times = Vec::new();
            let mut in_schedule = false;
            for line in deck.lines() {
                if line.starts_with("Vschedule schedule_probe 0 PWL(") {
                    in_schedule = true;
                    continue;
                }
                if in_schedule && line == "+ )" {
                    in_schedule = false;
                    continue;
                }
                if in_schedule {
                    let mut fields = line.split_whitespace();
                    assert_eq!(fields.next(), Some("+"));
                    schedule_times.push(fields.next().unwrap().parse::<f64>().unwrap());
                }
            }
            assert!(schedule_times.windows(2).all(|pair| pair[0] < pair[1]));
            assert_eq!(
                schedule_times.first().copied(),
                Some(params.fault - params.prefault_window - PACING_STEP)
            );
            assert_eq!(schedule_times.last().copied(), Some(params.stop));
            if case.needs_f2() {
                assert_eq!(deck.matches("Vf2ctl f2ctl 0 PWL(").count(), 1);
                assert!(deck.contains(" 0)\nSf2 vd f2_path"));
            } else {
                assert_eq!(deck.matches("Vf2ctl f2ctl 0 5").count(), 1);
            }
            if case.needs_switch_short() {
                assert_eq!(
                    deck.matches("Sswfail sw channel_source swfail_ctl").count(),
                    1
                );
            }
            if case.needs_diode_short() {
                assert_eq!(deck.matches("Sdiodeshort sw d1_path dshort_ctl").count(), 1);
            }
        }
    }

    #[test]
    fn case_and_parameter_validation_fail_closed() {
        assert!(CaseKind::parse("unknown").is_err());
        assert!(Params::parse("NaN", "1", "1e-6").is_err());
        assert!(Params::parse("0", "1", "1e-6").is_err());
        assert!(Params::parse("2", "1", "1e-6").is_err());
        assert!(Params::parse("1e-6", "2e-6", "1e-6").is_err());
        assert!(Params::parse("2e-6", "3e-6", "NaN").is_err());
    }

    #[test]
    fn output_exists_is_rejected() {
        let source = actual_source();
        let dir =
            env::temp_dir().join(format!("matrix07-materializer-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let result = materialize(
            &source,
            CaseKind::F2Crest,
            Params::parse("2e-6", "3e-6", "1e-6").unwrap(),
            &dir,
        );
        assert!(result.is_err());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn bypass_output_rewrites_only_protection_parameter() {
        let source = actual_source();
        let dir = env::temp_dir().join(format!(
            "matrix07-materializer-bypass-test-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);
        materialize(
            &source,
            CaseKind::BypassNeg,
            Params::parse("2e-6", "3e-6", "1e-6").unwrap(),
            &dir,
        )
        .unwrap();
        let protection = fs::read_to_string(dir.join("protection.inc")).unwrap();
        assert_eq!(protection.matches(BYPASS_PARAM_LINE).count(), 0);
        assert_eq!(
            protection
                .matches(".param FAULT_TAU=79.3n EN_TAU=18.75n BYPASS=1")
                .count(),
            1
        );
        let original_protection = fs::read_to_string(source.join("protection.inc")).unwrap();
        let restored_protection = protection.replace(
            ".param FAULT_TAU=79.3n EN_TAU=18.75n BYPASS=1",
            BYPASS_PARAM_LINE,
        );
        assert_eq!(restored_protection, original_protection);
        let cold = fs::read_to_string(dir.join("cold.cir")).unwrap();
        assert_eq!(
            source_tstop_line(&cold).unwrap(),
            ".param RLOAD=190 TSTOP=500m STEP=500n"
        );
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn sha256_known_vector() {
        assert_eq!(
            sha256_hex(b"abc").unwrap(),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
}
