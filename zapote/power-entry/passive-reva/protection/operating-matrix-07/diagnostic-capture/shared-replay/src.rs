//! Shared-lib diagnostic transport for the unchanged 340--400 ms cold-start deck.
//! Electrical behavior is owned by the SPICE deck; this program only controls
//! ngspice, exports finite traces, and records the state at the known stall.
use std::ffi::{CStr, CString};
use std::fs;
use std::os::raw::{c_char, c_int, c_void};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant};

#[repr(C)] struct VecValues { _private: [u8; 0] }
#[repr(C)] struct VecInfoAll { _private: [u8; 0] }

extern "C" {
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
// ngspice-45.2 reports false when a background run starts and true when it is
// stopped/ready; completion also requires ngSpice_running()==false.
extern "C" fn bg_running(running: bool, _ident: c_int, _user: *mut c_void) -> c_int {
    eprintln!("[bg_callback] bool={running}");
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
        if !running && (saw_running || BG_TRUE_EVENTS.load(Ordering::Acquire) > true_before) {
            eprintln!("{label}: stopped after {:.3}s", start.elapsed().as_secs_f64());
            return Ok(());
        }
        if start.elapsed() > timeout { return Err(format!("timeout waiting for {label}")); }
        thread::sleep(Duration::from_millis(10));
    }
}

const SIGNALS: &str = "v(acsrc) v(acn) v(acp) i(Vac) v(rectp) v(vd) v(vb) v(load) i(Lboost) i(Vchannel) i(Vbody) v(sw) v(gate) v(isense) v(vsense) v(vcomp) v(vcomp_s) v(icomp) v(pwm) v(q) v(en) v(fault) v(xu.pcl_hold) v(xu.ss_done) v(arm) v(permit) v(standby_req) v(f2ctl) v(loadctl) v(bypass_ctl) v(xu.raw) v(xu.pwm_hold) v(xu.phase) v(xu.m1) v(xu.m2) v(xu.blank) v(xu.fault) v(xu.icomp_reset) v(xu.ov) v(xu.ss_done_raw) v(xu.pcl_request) v(ltimer) v(atimer) v(fault_raw)";

fn check_trace(path: &str, expected_end: Option<f64>) -> Result<(usize, f64, usize), String> {
    let data = fs::read_to_string(path).map_err(|e| format!("read {path}: {e}"))?;
    let mut lines = data.lines();
    let header = lines.next().unwrap_or("").split_whitespace().collect::<Vec<_>>();
    if header.len() < 3 || header[0] != "time" { return Err(format!("bad multi-trace header: {header:?}")); }
    let mut prev = None;
    let mut count = 0usize;
    let mut last = 0.0f64;
    for line in lines {
        let mut fields = line.split_whitespace();
        let t = fields.next().ok_or("empty data row")?.parse::<f64>().map_err(|_| "bad time")?;
        if !t.is_finite() { return Err("non-finite time".into()); }
        if let Some(p) = prev { if t <= p { return Err(format!("non-monotone row {count}: {p:.17e} -> {t:.17e}")); } }
        prev = Some(t); last = t; count += 1;
        for field in fields {
            let x = field.parse::<f64>().map_err(|_| "bad numeric field")?;
            if !x.is_finite() { return Err(format!("non-finite field row {count}")); }
        }
    }
    if count == 0 { return Err("no data rows".into()); }
    if let Some(expected) = expected_end {
        if (last - expected).abs() > 2e-9 { return Err(format!("end {last:.17e} != {expected:.17e}")); }
    }
    Ok((count, last, header.len()))
}

fn export_trace(capture_dir: &std::path::Path, name: &str, expected_end: Option<f64>) -> Result<(), String> {
    let path = capture_dir.join(name);
    command(&format!("wrdata {} {SIGNALS}", path.display()))?;
    let (rows, end, columns) = check_trace(&path.to_string_lossy(), expected_end)?;
    eprintln!("export {name}: rows={rows} columns={columns} end={end:.17e}");
    Ok(())
}

fn print_latest() -> Result<(), String> {
    command("rusage tranpoints traniter rejected trancuriters trantime")?;
    command("let idx = length(time)-1")?;
    command("print time[$&idx] v(vb)[$&idx] v(vcomp)[$&idx] v(icomp)[$&idx] v(xu.raw)[$&idx] v(xu.pwm_hold)[$&idx] v(xu.phase)[$&idx] v(xu.m1)[$&idx] v(xu.m2)[$&idx] v(xu.blank)[$&idx] v(xu.fault)[$&idx] v(xu.icomp_reset)[$&idx] v(xu.ov)[$&idx] v(xu.ss_done_raw)[$&idx] v(xu.ss_done)[$&idx] v(xu.pcl_request)[$&idx] v(ltimer)[$&idx] v(atimer)[$&idx] v(fault_raw)[$&idx]")
}

fn main() -> Result<(), String> {
    let root = std::env::current_dir().map_err(|e| e.to_string())?;
    let capture_dir = root.join("output/shared-diagnostic");
    let deck = capture_dir.join("before-stall-shared.cir");
    eprintln!("deck_sha256=e9a9cb849b92513665ad7852ccafcea867a1094b664d4e48458f4ff5f8f4257b (canonical; shared deck hash is recorded separately)");
    eprintln!("before init");
    unsafe {
        let rc = ngSpice_Init(Some(send_char), Some(send_stat), Some(controlled_exit), None, None, Some(bg_running), std::ptr::null_mut());
        eprintln!("after init rc={rc}");
        if rc != 0 { return Err(format!("ngSpice_Init returned {rc}")); }
    }
    let mut lines = Vec::<CString>::new();
    for raw in fs::read_to_string(&deck).map_err(|e| e.to_string())?.lines() {
        lines.push(CString::new(raw).map_err(|e| e.to_string())?);
    }
    let mut ptrs = lines.iter_mut().map(|x| x.as_ptr() as *mut c_char).collect::<Vec<_>>();
    ptrs.push(std::ptr::null_mut());
    let circ_rc = unsafe { ngSpice_Circ(ptrs.as_mut_ptr()) };
    eprintln!("ngSpice_Circ rc={circ_rc}");
    if circ_rc != 0 { return Err(format!("ngSpice_Circ returned {circ_rc}")); }
    command("set wr_singlescale")?;
    command("set wr_vecnames")?;
    command("set numdgt=17")?;

    command("stop when time = 351.49m")?;
    let before_run = BG_TRUE_EVENTS.load(Ordering::Acquire);
    command("bg_run")?;
    wait_idle("pre-stall checkpoint", Duration::from_secs(1800), before_run)?;
    print_latest()?;
    export_trace(&capture_dir, "before-stall-shared.tsv", Some(0.35149))?;
    fs::write(capture_dir.join("before-stall.ready"), b"pre-stall export complete; process resumed below\n").map_err(|e| e.to_string())?;

    let before_resume = BG_TRUE_EVENTS.load(Ordering::Acquire);
    command("bg_resume")?;
    let resume_start = Instant::now();
    let mut saw_running = false;
    while resume_start.elapsed() < Duration::from_secs(60) {
        if unsafe { ngSpice_running() } { saw_running = true; }
        if saw_running && !unsafe { ngSpice_running() } { break; }
        thread::sleep(Duration::from_millis(20));
    }
    if unsafe { ngSpice_running() } {
        eprintln!("post-resume still running after {:.3}s; issuing bg_halt", resume_start.elapsed().as_secs_f64());
        command("bg_halt")?;
        wait_idle("post-resume bg_halt", Duration::from_secs(60), before_resume)?;
        print_latest()?;
        export_trace(&capture_dir, "post-stall-halt.tsv", None)?;
        fs::write(capture_dir.join("post-stall.ready"), b"post-resume bg_halt export complete; process remains paused for inspection\n").map_err(|e| e.to_string())?;
        // Keep the shared ngspice process alive and paused for parent inspection.
        eprintln!("PAUSED_FOR_INSPECTION sleep=300s");
        thread::sleep(Duration::from_secs(300));
    } else {
        eprintln!("post-resume completed before 60s");
        print_latest()?;
        export_trace(&capture_dir, "post-resume-final.tsv", Some(0.4))?;
    }

    if let Err(err) = command("quit") {
        if CONTROLLED_EXIT_STATUS.load(Ordering::Acquire) != 0 { return Err(err); }
    }
    Ok(())
}
