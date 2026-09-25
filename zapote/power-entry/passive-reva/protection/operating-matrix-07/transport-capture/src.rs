//! Headless transport harness for libngspice shared API.
//! This only drives commands/callbacks and checks exported time ordering.
use std::ffi::{CStr, CString};
use std::fs;
use std::os::raw::{c_char, c_int, c_void};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant};

#[repr(C)]
struct VecValues { _private: [u8; 0] }
#[repr(C)]
struct VecInfoAll { _private: [u8; 0] }

extern "C" {
    fn ngSpice_nospinit() -> c_int;
    fn ngSpice_nospiceinit() -> c_int;
    fn ngSpice_Init(
        printfcn: Option<extern "C" fn(*mut c_char, c_int, *mut c_void) -> c_int>,
        statfcn: Option<extern "C" fn(*mut c_char, c_int, *mut c_void) -> c_int>,
        ngexit: Option<extern "C" fn(c_int, bool, bool, c_int, *mut c_void) -> c_int>,
        sdata: Option<extern "C" fn(*mut VecValues, c_int, c_int, *mut c_void) -> c_int>,
        sinitdata: Option<extern "C" fn(*mut VecInfoAll, c_int, *mut c_void) -> c_int>,
        bgtrun: Option<extern "C" fn(bool, c_int, *mut c_void) -> c_int>,
        userdata: *mut c_void,
    ) -> c_int;
    fn ngSpice_Command(command: *mut c_char) -> c_int;
    fn ngSpice_Circ(lines: *mut *mut c_char) -> c_int;
    fn ngSpice_running() -> bool;
}

static BG_RAW: AtomicBool = AtomicBool::new(false);
static BG_TRUE_EVENTS: AtomicUsize = AtomicUsize::new(0);
static CALLBACK_CHARS: AtomicUsize = AtomicUsize::new(0);
static CONTROLLED_EXIT_STATUS: AtomicUsize = AtomicUsize::new(usize::MAX);

extern "C" fn send_char(s: *mut c_char, _ident: c_int, _user: *mut c_void) -> c_int {
    if !s.is_null() {
        let text = unsafe { CStr::from_ptr(s) }.to_string_lossy();
        CALLBACK_CHARS.fetch_add(text.len(), Ordering::Relaxed);
        print!("{text}");
    }
    0
}
extern "C" fn send_stat(s: *mut c_char, _ident: c_int, _user: *mut c_void) -> c_int {
    if !s.is_null() {
        let text = unsafe { CStr::from_ptr(s) }.to_string_lossy();
        if !text.trim().is_empty() { eprintln!("[status] {}", text.trim()); }
    }
    0
}
extern "C" fn controlled_exit(status: c_int, _immediate: bool, _exit_on_quit: bool, _ident: c_int, _user: *mut c_void) -> c_int {
    eprintln!("[ngexit] status={status}");
    CONTROLLED_EXIT_STATUS.store(status.max(0) as usize, Ordering::Release);
    0
}
extern "C" fn bg_running(running: bool, _ident: c_int, _user: *mut c_void) -> c_int {
    eprintln!("[bg_callback] bool={running}");
    BG_RAW.store(running, Ordering::Release);
    if running { BG_TRUE_EVENTS.fetch_add(1, Ordering::AcqRel); }
    0
}

fn command(text: &str) -> Result<(), String> {
    let mut c = CString::new(text).map_err(|e| e.to_string())?.into_bytes_with_nul();
    let rc = unsafe { ngSpice_Command(c.as_mut_ptr() as *mut c_char) };
    if rc != 0 { return Err(format!("command `{text}` returned {rc}")); }
    Ok(())
}
fn wait_idle(label: &str, timeout: Duration, true_before: usize) -> Result<(), String> {
    let start = Instant::now();
    let mut saw_running = false;
    loop {
        let running = unsafe { ngSpice_running() };
        if running { saw_running = true; }
        // In ngspice-45.2 this callback's true value is the stopped/ready
        // notification (observed empirically); ngSpice_running is the source
        // of truth while the background solver is active.
        if !running && (saw_running || BG_TRUE_EVENTS.load(Ordering::Acquire) > true_before) {
            return Ok(());
        }
        if start.elapsed() > timeout { return Err(format!("timeout waiting for {label}")); }
        thread::sleep(Duration::from_millis(2));
    }
}
fn check_trace(path: &str, signal: &str, expected_end: Option<f64>) -> Result<usize, String> {
    let data = fs::read_to_string(path).map_err(|e| format!("read {path}: {e}"))?;
    let mut lines = data.lines();
    let header = lines.next().unwrap_or("").split_whitespace().collect::<Vec<_>>();
    if header != ["time", signal] { return Err(format!("bad header for {signal}: {header:?}")); }
    let mut prev = None;
    let mut count = 0;
    let mut last = 0.0;
    for line in lines {
        let xs = line.split_whitespace().map(|x| x.parse::<f64>()).collect::<Result<Vec<_>, _>>().map_err(|_| "bad numeric row".to_string())?;
        if xs.len() != 2 || xs.iter().any(|x| !x.is_finite()) { return Err("malformed row".into()); }
        if let Some(p) = prev { if xs[0] <= p { return Err(format!("non-monotone at row {count}: {p} -> {}", xs[0])); } }
        prev = Some(xs[0]); last = xs[0]; count += 1;
    }
    if let Some(expected) = expected_end { if (last - expected).abs() > 2e-12 { return Err(format!("end {last:.17e} != {expected:.17e}")); } }
    Ok(count)
}

fn main() -> Result<(), String> {
    let root = std::env::current_dir().map_err(|e| e.to_string())?;
    let capture_dir = root.join("output/shared-capture");
    eprintln!("before init");
    unsafe {
        let rc = ngSpice_Init(Some(send_char), Some(send_stat), Some(controlled_exit), None, None, Some(bg_running), std::ptr::null_mut());
        eprintln!("after init rc={rc}");
        if rc != 0 { return Err(format!("ngSpice_Init returned {rc}")); }
    }
    let halt_mode = std::env::args().nth(1).as_deref() == Some("halt");
    let deck = capture_dir.join(if halt_mode { "rc-halt.cir" } else { "pwm-hold-capture.cir" });
    eprintln!("before circ build");
    let mut lines = Vec::<CString>::new();
    for raw in fs::read_to_string(&deck).map_err(|e| e.to_string())?.lines() {
        let line = raw.replace("../ucc28180-pwm-latch.inc", "/private/tmp/temper07-normal/output/ucc28180-pwm-latch.inc");
        lines.push(CString::new(line).map_err(|e| e.to_string())?);
    }
    let mut ptrs = lines.iter_mut().map(|x| x.as_ptr() as *mut c_char).collect::<Vec<_>>();
    ptrs.push(std::ptr::null_mut());
    eprintln!("before circ");
    let circ_rc = unsafe { ngSpice_Circ(ptrs.as_mut_ptr()) };
    eprintln!("after circ rc={circ_rc}");
    if circ_rc != 0 { return Err(format!("ngSpice_Circ returned {circ_rc}")); }
    command("set wr_singlescale")?;
    command("set wr_vecnames")?;
    command("set numdgt=17")?;
    if halt_mode {
        let before = BG_TRUE_EVENTS.load(Ordering::Acquire);
        command("bg_run")?;
        thread::sleep(Duration::from_millis(5));
        command("bg_halt")?;
        wait_idle("RC bg_halt", Duration::from_secs(30), before)?;
        command(&format!("wrdata {}/rc-paused.tsv v(out)", capture_dir.display()))?;
        let paused_rows = check_trace(&capture_dir.join("rc-paused.tsv").to_string_lossy(), "v(out)", None)?;
        eprintln!("HALT_PAUSED rows={paused_rows} callbacks={}", CALLBACK_CHARS.load(Ordering::Relaxed));
        let before_resume = BG_TRUE_EVENTS.load(Ordering::Acquire);
        command("bg_resume")?;
        wait_idle("RC resume", Duration::from_secs(30), before_resume)?;
        command(&format!("wrdata {}/rc-resumed.tsv v(out)", capture_dir.display()))?;
        let resumed_rows = check_trace(&capture_dir.join("rc-resumed.tsv").to_string_lossy(), "v(out)", Some(10.0))?;
        eprintln!("HALT_RESUMED rows={resumed_rows} end=10s callbacks={}", CALLBACK_CHARS.load(Ordering::Relaxed));
    } else {
        command("stop when time = 10u")?;
        let before_run = BG_TRUE_EVENTS.load(Ordering::Acquire);
        command("bg_run")?;
        wait_idle("10us breakpoint", Duration::from_secs(30), before_run)?;
        command("where")?;
        command(&format!("wrdata {}/hold-paused.tsv v(gate)", capture_dir.display()))?;
        let paused_rows = check_trace(&capture_dir.join("hold-paused.tsv").to_string_lossy(), "v(gate)", Some(10e-6))?;
        eprintln!("PAUSED rows={paused_rows} end=10us callbacks={} ", CALLBACK_CHARS.load(Ordering::Relaxed));
        let before_resume = BG_TRUE_EVENTS.load(Ordering::Acquire);
        command("bg_resume")?;
        wait_idle("resume to 20us", Duration::from_secs(30), before_resume)?;
        command(&format!("wrdata {}/hold-resumed.tsv v(gate)", capture_dir.display()))?;
        let resumed_rows = check_trace(&capture_dir.join("hold-resumed.tsv").to_string_lossy(), "v(gate)", Some(20e-6))?;
        eprintln!("RESUMED rows={resumed_rows} end=20us callbacks={}", CALLBACK_CHARS.load(Ordering::Relaxed));
    }
    // ngSpice reports controlled exit status 0, while `quit` itself commonly
    // returns 1 after requesting the detach.  Treat that exact controlled
    // shutdown as success; propagate any other command failure.
    if let Err(err) = command("quit") {
        if CONTROLLED_EXIT_STATUS.load(Ordering::Acquire) != 0 { return Err(err); }
    }
    Ok(())
}
