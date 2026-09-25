//! First-invalid-time diagnostic capture for the unchanged cold-start deck.
//!
//! The callback copies only scalar values for the first non-increasing
//! accepted time. It never retains ngspice pointers, allocates strings, or
//! sends commands. The main thread observes the flag, halts ngspice, and
//! exports the retained full trace through the caller-provided path (normally
//! a FIFO consumed by gzip).

use std::ffi::{CStr, CString};
use std::collections::HashSet;
use std::fs;
use std::io::{self, Write};
use std::os::raw::{c_char, c_int, c_void};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

#[repr(C)]
struct Value { name: *mut c_char, real: f64, imag: f64, scale: bool, complex: bool }
#[repr(C)]
struct Values { count: c_int, index: c_int, values: *mut *mut Value }
#[repr(C)]
struct InitValues { _private: [u8; 0] }

extern "C" {
    fn ngSpice_Init(
        text: Option<extern "C" fn(*mut c_char, c_int, *mut c_void) -> c_int>,
        status: Option<extern "C" fn(*mut c_char, c_int, *mut c_void) -> c_int>,
        exit: Option<extern "C" fn(c_int, bool, bool, c_int, *mut c_void) -> c_int>,
        data: Option<extern "C" fn(*mut Values, c_int, c_int, *mut c_void) -> c_int>,
        init: Option<extern "C" fn(*mut InitValues, c_int, *mut c_void) -> c_int>,
        bg: Option<extern "C" fn(bool, c_int, *mut c_void) -> c_int>,
        user: *mut c_void,
    ) -> c_int;
    fn ngSpice_Circ(lines: *mut *mut c_char) -> c_int;
    fn ngSpice_Command(command: *mut c_char) -> c_int;
    fn ngSpice_running() -> bool;
}

const DIAG_NAMES: [&[u8]; 16] = [
    b"xu.raw", b"xu.pwm_hold", b"pwm", b"pwm_input", b"xdriver.driver_req", b"xdriver.drv_delay",
    b"xu.phase", b"xu.blank", b"isense", b"xu.ov", b"xu.fault", b"xu.pcl_hold",
    b"xu.pcl_request", b"disable", b"xu.m1", b"xu.m2",
];

#[derive(Clone, Copy)]
struct Snapshot {
    previous_time_s: f64,
    current_time_s: f64,
    previous_index: u64,
    current_index: u64,
    diagnostics: [f64; DIAG_NAMES.len()],
    missing_mask: u32,
}

static HAVE_TIME: AtomicBool = AtomicBool::new(false);
static LAST_TIME_BITS: AtomicU64 = AtomicU64::new(0);
static POINTS: AtomicU64 = AtomicU64::new(0);
static FIRST_INVALID: AtomicBool = AtomicBool::new(false);
static NAMES_SEEN: AtomicBool = AtomicBool::new(false);
static SEEN_NAMES_MASK: AtomicU64 = AtomicU64::new(0);
static DUPLICATE_COUNT: AtomicU64 = AtomicU64::new(0);
static BACKWARDS_COUNT: AtomicU64 = AtomicU64::new(0);
static NONFINITE_TIME: AtomicBool = AtomicBool::new(false);
static SNAPSHOT: Mutex<Option<Snapshot>> = Mutex::new(None);
static STOPPED_EVENTS: AtomicUsize = AtomicUsize::new(0);

fn detect_nonincreasing(previous: Option<f64>, current: f64) -> bool {
    !current.is_finite() || previous.is_some_and(|p| current <= p)
}

fn name_index(name: &[u8]) -> Option<usize> {
    DIAG_NAMES.iter().position(|candidate| *candidate == name)
}

/// The prepared fault deck deliberately contains two `.save` lines: the
/// first is the normal-capture inventory, and the second is the exact
/// fault-checker interface (17 canonical vectors plus four evidence
/// vectors).  Export their ordered union once: this retains the complete
/// normal vector set for prefault checks while avoiding repeated names that
/// would make the independent normalizer reject the trace as ambiguous.
fn fault_export_signals(deck: &str) -> Result<String, String> {
    let saves: Vec<Vec<&str>> = deck
        .lines()
        .filter_map(|line| line.trim().strip_prefix(".save "))
        .map(|line| line.split_whitespace().collect())
        .collect();
    if saves.len() != 2 {
        return Err(format!("fault deck must contain exactly two .save lines, found {}", saves.len()));
    }
    let expected = [
        "time", "v(acsrc,acn)", "v(vd)", "v(vb)", "v(sw)", "v(gate)",
        "i(Lboost)", "i(Vchannel)", "i(Vbody)", "i(Vac)", "v(q)", "v(en)",
        "v(fault)", "v(f2ctl)", "v(standby_req)", "v(arm)", "v(permit)",
        "i(Vf2sense)", "i(Vdboost1sense)", "i(Vdboost2sense)", "v(fault_inject)",
    ];
    if saves[1] != expected {
        return Err(format!("fault .save schema mismatch: expected {:?}, got {:?}", expected, saves[1]));
    }
    if saves[0].first() != Some(&"time") {
        return Err("normal .save inventory must begin with time".into());
    }
    if saves[0].len() != 31 {
        return Err(format!("normal .save inventory must contain 30 signals, found {}", saves[0].len() - 1));
    }
    let mut seen = HashSet::new();
    let mut union = Vec::with_capacity(saves[0].len() + saves[1].len());
    for name in saves[0].iter().chain(saves[1].iter().skip(1)) {
        if *name == "time" {
            continue;
        }
        if seen.insert(*name) {
            union.push(*name);
        }
    }
    // The materialized deck carries 30 normal vectors and 11 fault-only
    // vectors after the shared names are deduplicated.
    if union.len() != 41 {
        return Err(format!("unexpected normal+fault union width: {}", union.len()));
    }
    Ok(union.join(" "))
}

extern "C" fn init_data(_: *mut InitValues, _: c_int, _: *mut c_void) -> c_int { 0 }

extern "C" fn text(s: *mut c_char, _: c_int, _: *mut c_void) -> c_int {
    if !s.is_null() {
        let text = unsafe { CStr::from_ptr(s) }.to_string_lossy();
        let _ = writeln!(io::stderr().lock(), "{text}");
    }
    0
}

extern "C" fn exit(status: c_int, _: bool, _: bool, _: c_int, _: *mut c_void) -> c_int {
    let _ = writeln!(io::stderr().lock(), "ngspice_exit={status}");
    0
}

extern "C" fn bg(stopped: bool, _: c_int, _: *mut c_void) -> c_int {
    if stopped { STOPPED_EVENTS.fetch_add(1, Ordering::Release); }
    0
}

extern "C" fn data(p: *mut Values, _: c_int, _: c_int, _: *mut c_void) -> c_int {
    if p.is_null() { return 0; }
    let p = unsafe { &*p };
    if p.count <= 0 || p.values.is_null() { return 0; }
    let values = unsafe { std::slice::from_raw_parts(p.values, p.count as usize) };
    let mut time = None;
    for &raw in values {
        if raw.is_null() { continue; }
        let value = unsafe { &*raw };
        if value.complex { continue; }
        let name = if value.name.is_null() { &[][..] } else { unsafe { CStr::from_ptr(value.name) }.to_bytes() };
        if value.scale || name == b"time" {
            if time.is_none() { time = Some(value.real); }
        }
    }
    if !NAMES_SEEN.load(Ordering::Acquire) {
        let mut seen_mask = 0u64;
        for &raw in values {
            if raw.is_null() { continue; }
            let value = unsafe { &*raw };
            if value.name.is_null() { continue; }
            if let Some(index) = name_index(unsafe { CStr::from_ptr(value.name) }.to_bytes()) {
                seen_mask |= 1u64 << index;
            }
        }
        SEEN_NAMES_MASK.store(seen_mask, Ordering::Release);
        NAMES_SEEN.store(true, Ordering::Release);
    }
    let Some(current_time) = time else { return 0; };
    let current_index = POINTS.fetch_add(1, Ordering::AcqRel);
    let previous = if HAVE_TIME.load(Ordering::Acquire) {
        Some(f64::from_bits(LAST_TIME_BITS.load(Ordering::Acquire)))
    } else { None };
    if !current_time.is_finite() {
        NONFINITE_TIME.store(true, Ordering::Release);
    } else if let Some(previous) = previous {
        if current_time < previous {
            BACKWARDS_COUNT.fetch_add(1, Ordering::AcqRel);
        } else if current_time == previous {
            DUPLICATE_COUNT.fetch_add(1, Ordering::AcqRel);
        }
    }
    if !FIRST_INVALID.load(Ordering::Acquire) && detect_nonincreasing(previous, current_time) {
        if let Ok(mut guard) = SNAPSHOT.try_lock() {
            if guard.is_none() {
                // Only the first invalid callback scans the named analog
                // vectors. Normal accepted points never pay this cost.
                let mut diagnostics = [f64::NAN; DIAG_NAMES.len()];
                for &raw in values {
                    if raw.is_null() { continue; }
                    let value = unsafe { &*raw };
                    if value.complex || !value.real.is_finite() || value.name.is_null() { continue; }
                    let name = unsafe { CStr::from_ptr(value.name) }.to_bytes();
                    if let Some(index) = name_index(name) { diagnostics[index] = value.real; }
                }
                let missing_mask = diagnostics.iter().enumerate().fold(0u32, |mask, (i, v)| {
                    if v.is_finite() { mask } else { mask | (1u32 << i) }
                });
                *guard = Some(Snapshot {
                    previous_time_s: previous.unwrap_or(f64::NAN),
                    current_time_s: current_time,
                    previous_index: current_index.saturating_sub(1),
                    current_index,
                    diagnostics,
                    missing_mask,
                });
                // Publish only after the owned snapshot is complete.
                FIRST_INVALID.store(true, Ordering::Release);
            }
        }
    }
    LAST_TIME_BITS.store(current_time.to_bits(), Ordering::Release);
    HAVE_TIME.store(true, Ordering::Release);
    0
}

fn command(s: &str) -> Result<(), String> {
    let mut c = CString::new(s).map_err(|e| e.to_string())?.into_bytes_with_nul();
    let rc = unsafe { ngSpice_Command(c.as_mut_ptr().cast()) };
    if rc == 0 { Ok(()) } else { Err(format!("command `{s}` returned {rc}")) }
}

fn wait_idle(label: &str, timeout: Duration, before_stopped: usize) -> Result<(), String> {
    let start = Instant::now();
    let mut saw_running = false;
    loop {
        let running = unsafe { ngSpice_running() };
        if running { saw_running = true; }
        if !running && (saw_running || STOPPED_EVENTS.load(Ordering::Acquire) > before_stopped) { return Ok(()); }
        if start.elapsed() > timeout { return Err(format!("timeout waiting for {label}")); }
        thread::sleep(Duration::from_millis(2));
    }
}

fn write_snapshot(path: &str) -> Result<(), String> {
    let guard = SNAPSHOT.lock().map_err(|_| "snapshot mutex poisoned".to_string())?;
    let Some(snapshot) = *guard else { return Err("first-invalid flag set without snapshot".into()); };
    let mut file = fs::File::create(path).map_err(|e| e.to_string())?;
    writeln!(file, "previous_time_s\t{:.17e}", snapshot.previous_time_s).map_err(|e| e.to_string())?;
    writeln!(file, "current_time_s\t{:.17e}", snapshot.current_time_s).map_err(|e| e.to_string())?;
    writeln!(file, "previous_index\t{}", snapshot.previous_index).map_err(|e| e.to_string())?;
    writeln!(file, "current_index\t{}", snapshot.current_index).map_err(|e| e.to_string())?;
    writeln!(file, "missing_mask\t{}", snapshot.missing_mask).map_err(|e| e.to_string())?;
    for (name, value) in DIAG_NAMES.iter().zip(snapshot.diagnostics) {
        writeln!(file, "{}\t{:.17e}", std::str::from_utf8(name).unwrap(), value).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if !cfg!(target_endian = "little") { return Err("native export requires a little-endian writer; byte-order metadata must not be guessed".into()); }
    if args.len() != 6 { return Err("usage: progress DECK WALL_SECONDS TARGET_SECONDS EXPORT_PATH SNAPSHOT_PATH".into()); }
    if args[4].chars().any(char::is_whitespace) || args[4].contains([';', '\n', '"']) { return Err("simple export path required".into()); }
    let limit: f64 = args[2].parse().map_err(|_| "invalid wall seconds")?;
    let target: f64 = args[3].parse().map_err(|_| "invalid target seconds")?;
    if !limit.is_finite() || !target.is_finite() || limit <= 0.0 || target <= 0.0 { return Err("positive finite limits required".into()); }
    let rc = unsafe { ngSpice_Init(Some(text), None, Some(exit), Some(data), Some(init_data), Some(bg), std::ptr::null_mut()) };
    if rc != 0 { return Err(format!("init={rc}")); }
    let deck = fs::read_to_string(&args[1]).map_err(|e| e.to_string())?;
    let signals = fault_export_signals(&deck)?;
    let lines: Vec<_> = deck.lines().map(CString::new).collect::<Result<_, _>>().map_err(|e| e.to_string())?;
    let mut ptrs: Vec<_> = lines.iter().map(|s| s.as_ptr().cast_mut()).collect();
    ptrs.push(std::ptr::null_mut());
    if unsafe { ngSpice_Circ(ptrs.as_mut_ptr()) } != 0 { return Err("circuit load failed".into()); }
    let mut progress = fs::File::create("progress.tsv").map_err(|e| e.to_string())?;
    writeln!(progress, "wall_s\tsim_s\tpercent\trecent_sim_s_per_wall_s\tcallbacks\tfirst_invalid\tduplicate_count\tbackwards_count\tnonfinite_time").map_err(|e| e.to_string())?;
    let start = Instant::now();
    let before_stopped = STOPPED_EVENTS.load(Ordering::Acquire);
    command("bg_run")?;
    let mut last_wall = 0.0;
    let mut last_sim = 0.0;
    let mut progress_anchor = 0.0;
    let mut advanced_at = Instant::now();
    let stop_reason: &str;
    loop {
        thread::sleep(Duration::from_millis(100));
        let wall = start.elapsed().as_secs_f64();
        let sim = if HAVE_TIME.load(Ordering::Acquire) { f64::from_bits(LAST_TIME_BITS.load(Ordering::Acquire)) } else { 0.0 };
        if sim >= progress_anchor + 1e-6 { progress_anchor = sim; advanced_at = Instant::now(); }
        let stalled = advanced_at.elapsed() >= Duration::from_secs(120);
        let done = !unsafe { ngSpice_running() } && STOPPED_EVENTS.load(Ordering::Acquire) > before_stopped;
        let first_invalid = FIRST_INVALID.load(Ordering::Acquire);
        if wall - last_wall >= 10.0 || wall >= limit || done || stalled || first_invalid {
            let rate = if wall > last_wall { (sim - last_sim) / (wall - last_wall) } else { 0.0 };
            let row = format!("{wall:.6}\t{sim:.17e}\t{:.6}\t{rate:.12e}\t{}\t{}\t{}\t{}\t{}", 100.0 * sim / target, POINTS.load(Ordering::Acquire), first_invalid, DUPLICATE_COUNT.load(Ordering::Acquire), BACKWARDS_COUNT.load(Ordering::Acquire), NONFINITE_TIME.load(Ordering::Acquire));
            println!("{row}"); writeln!(progress, "{row}").map_err(|e| e.to_string())?; progress.flush().map_err(|e| e.to_string())?;
            last_wall = wall; last_sim = sim;
        }
        if NONFINITE_TIME.load(Ordering::Acquire) { stop_reason = "nonfinite_time"; break; }
        if BACKWARDS_COUNT.load(Ordering::Acquire) != 0 { stop_reason = "negative_time_step"; break; }
        if done { stop_reason = "solver_stopped"; break; }
        if stalled { stop_reason = "less_than_1us_progress_in_120s"; break; }
        if wall >= limit { stop_reason = "wall_limit"; break; }
    }
    if unsafe { ngSpice_running() } {
        command("bg_halt")?;
        wait_idle("diagnostic halt", Duration::from_secs(30), before_stopped)?;
    }
    command("rusage tranpoints traniter rejected trancuriters trantime")?;
    command("set wr_singlescale")?; command("set wr_vecnames")?; command("set numdgt=17")?;
    fs::write("stop.txt", format!("reason={stop_reason}\nwall_s={:.6}\nsim_s={:.17e}\npoints={}\nfirst_invalid={}\nduplicate_count={}\nbackwards_count={}\nnonfinite_time={}\ncontinue_after_duplicate=true\n", start.elapsed().as_secs_f64(), if HAVE_TIME.load(Ordering::Acquire) { f64::from_bits(LAST_TIME_BITS.load(Ordering::Acquire)) } else { 0.0 }, POINTS.load(Ordering::Acquire), FIRST_INVALID.load(Ordering::Acquire), DUPLICATE_COUNT.load(Ordering::Acquire), BACKWARDS_COUNT.load(Ordering::Acquire), NONFINITE_TIME.load(Ordering::Acquire))).map_err(|e| e.to_string())?;
    write_snapshot(&args[5]).or_else(|e| if FIRST_INVALID.load(Ordering::Acquire) { Err(e) } else { fs::write(&args[5], "first_invalid=false\n").map_err(|x| x.to_string()) })?;
    fs::write("capture-metadata.json", format!("{{\n  \"stop_reason\": \"{stop_reason}\",\n  \"points\": {},\n  \"first_invalid\": {},\n  \"seen_names_mask\": {},\n  \"expected_names_mask\": {},\n  \"duplicate_count\": {},\n  \"backwards_count\": {},\n  \"nonfinite_time\": {},\n  \"continue_after_duplicate\": true,\n  \"export_mode\": \"full_trace_path_or_fifo\",\n  \"vector_slicing_smoke\": \"rejected_full_length\",\n  \"diagnostic_only\": true,\n  \"accepted\": false,\n  \"export_format\": \"ngspice-real-native\",\n  \"byte_order\": \"little\",\n  \"writer_platform\": \"{}-{}\",\n  \"schema\": \"fault42\",\n  \"fault_schema_columns\": 17,\n  \"fault_extra_columns\": 4,\n  \"validation_policy\": \"fault-transport-only-v1\"\n}}\n", POINTS.load(Ordering::Acquire), FIRST_INVALID.load(Ordering::Acquire), SEEN_NAMES_MASK.load(Ordering::Acquire), (1u64 << DIAG_NAMES.len()) - 1, DUPLICATE_COUNT.load(Ordering::Acquire), BACKWARDS_COUNT.load(Ordering::Acquire), NONFINITE_TIME.load(Ordering::Acquire), std::env::consts::ARCH, std::env::consts::OS)).map_err(|e| e.to_string())?;
    command("set filetype=binary")?;
    command(&format!("write {} time {signals}", args[4]))?;
    println!("DIAGNOSTIC_ONLY reason={stop_reason} last_callback_time_s={:.17e}", if HAVE_TIME.load(Ordering::Acquire) { f64::from_bits(LAST_TIME_BITS.load(Ordering::Acquire)) } else { 0.0 });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;
    static TEST_LOCK: Mutex<()> = Mutex::new(());
    #[test]
    fn detects_first_nonincreasing_sample() {
        assert!(!detect_nonincreasing(None, 0.0));
        assert!(!detect_nonincreasing(Some(0.1), 0.1000001));
        assert!(detect_nonincreasing(Some(0.1), 0.1));
        assert!(detect_nonincreasing(Some(0.1), 0.099));
        assert!(detect_nonincreasing(Some(0.1), f64::NAN));
    }
    #[test]
    fn maps_only_declared_diagnostics() {
        assert_eq!(name_index(b"xu.raw"), Some(0));
        assert_eq!(name_index(b"xu.m2"), Some(15));
        assert_eq!(name_index(b"not_saved"), None);
    }

    #[test]
    fn selects_fault_save_and_rejects_ambiguous_inventory() {
        let deck = ".save time v(acsrc) v(acn) i(Vac) v(load) v(vb) i(Lboost) v(vd) v(sw) v(gate) v(q) v(en) v(fault) v(vcomp) v(icomp) v(xu.raw) v(xu.pwm_hold) v(pwm) v(pwm_input) v(xdriver.driver_req) v(xdriver.drv_delay) v(xu.phase) v(xu.blank) v(isense) v(xu.ov) v(xu.fault) v(xu.pcl_hold) v(xu.pcl_request) v(disable) v(xu.m1) v(xu.m2)\n.save time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject)\n";
        let signals = fault_export_signals(deck).expect("fault schema");
        assert!(signals.starts_with("v(acsrc) v(acn) i(Vac)"));
        assert!(signals.ends_with("v(fault_inject)"));
        assert_eq!(signals.split_whitespace().count(), 41);
        assert!(fault_export_signals(".save time v(normal)\n").is_err());
    }

    fn invoke_point(time_s: f64, offset: f64) {
        let mut names: Vec<CString> = vec![CString::new("time").unwrap()];
        names.extend(DIAG_NAMES.iter().map(|name| CString::new(*name).unwrap()));
        let mut values: Vec<Value> = names.iter().enumerate().map(|(i, name)| Value {
            name: name.as_ptr() as *mut c_char,
            real: if i == 0 { time_s } else { offset + i as f64 },
            imag: 0.0,
            scale: i == 0,
            complex: false,
        }).collect();
        let mut pointers: Vec<*mut Value> = values.iter_mut().map(|value| value as *mut Value).collect();
        let mut packet = Values { count: pointers.len() as c_int, index: 0, values: pointers.as_mut_ptr() };
        assert_eq!(data(&mut packet, 0, 0, std::ptr::null_mut()), 0);
    }

    #[test]
    fn callback_captures_named_values_only_on_first_bad_time() {
        let _serial = TEST_LOCK.lock().unwrap();
        HAVE_TIME.store(false, Ordering::Release);
        LAST_TIME_BITS.store(0, Ordering::Release);
        POINTS.store(0, Ordering::Release);
        FIRST_INVALID.store(false, Ordering::Release);
        NAMES_SEEN.store(false, Ordering::Release);
        SEEN_NAMES_MASK.store(0, Ordering::Release);
        DUPLICATE_COUNT.store(0, Ordering::Release);
        BACKWARDS_COUNT.store(0, Ordering::Release);
        NONFINITE_TIME.store(false, Ordering::Release);
        *SNAPSHOT.lock().unwrap() = None;
        invoke_point(0.1, 10.0);
        assert!(!FIRST_INVALID.load(Ordering::Acquire));
        invoke_point(0.1, 20.0);
        assert!(FIRST_INVALID.load(Ordering::Acquire));
        assert_eq!(DUPLICATE_COUNT.load(Ordering::Acquire), 1);
        assert_eq!(POINTS.load(Ordering::Acquire), 2);
        // A repeated timestamp is retained; the callback does not stop the
        // solver.  A later forward point must still be observed.
        invoke_point(0.2, 30.0);
        assert_eq!(POINTS.load(Ordering::Acquire), 3);
        assert_eq!(DUPLICATE_COUNT.load(Ordering::Acquire), 1);
        assert_eq!(BACKWARDS_COUNT.load(Ordering::Acquire), 0);
        assert!(!NONFINITE_TIME.load(Ordering::Acquire));
        let snapshot = SNAPSHOT.lock().unwrap().expect("snapshot");
        assert_eq!(snapshot.previous_index, 0);
        assert_eq!(snapshot.current_index, 1);
        assert_eq!(snapshot.previous_time_s, 0.1);
        assert_eq!(snapshot.current_time_s, 0.1);
        assert_eq!(snapshot.diagnostics[0], 21.0);
        assert_eq!(snapshot.diagnostics[15], 36.0);
        assert_eq!(snapshot.missing_mask, 0);
        assert_eq!(SEEN_NAMES_MASK.load(Ordering::Acquire), (1u64 << DIAG_NAMES.len()) - 1);
    }

    #[test]
    fn backward_time_is_counted_for_main_loop_stop() {
        let _serial = TEST_LOCK.lock().unwrap();
        HAVE_TIME.store(false, Ordering::Release);
        LAST_TIME_BITS.store(0, Ordering::Release);
        POINTS.store(0, Ordering::Release);
        FIRST_INVALID.store(false, Ordering::Release);
        NAMES_SEEN.store(false, Ordering::Release);
        SEEN_NAMES_MASK.store(0, Ordering::Release);
        DUPLICATE_COUNT.store(0, Ordering::Release);
        BACKWARDS_COUNT.store(0, Ordering::Release);
        NONFINITE_TIME.store(false, Ordering::Release);
        *SNAPSHOT.lock().unwrap() = None;
        invoke_point(0.2, 10.0);
        invoke_point(0.1, 20.0);
        assert_eq!(BACKWARDS_COUNT.load(Ordering::Acquire), 1);
        assert!(FIRST_INVALID.load(Ordering::Acquire));
        assert_eq!(DUPLICATE_COUNT.load(Ordering::Acquire), 0);
        assert!(!NONFINITE_TIME.load(Ordering::Acquire));
    }
}
