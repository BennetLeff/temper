//! Tracked run; progress is diagnostic, waveform checker owns acceptance.
use std::ffi::{CStr, CString};
use std::fs;
use std::io::{self, Write};
use std::os::raw::{c_char, c_int, c_void};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant};

// Layouts from the installed ngspice 45.2 sharedspice.h (NG_BOOL is bool).
#[repr(C)]
struct Value { name: *mut c_char, real: f64, imag: f64, scale: bool, complex: bool }
#[repr(C)]
struct Values { count: c_int, index: c_int, values: *mut *mut Value }
#[repr(C)]
struct InitValues { _private: [u8; 0] }
extern "C" {
    fn ngSpice_Init(
        text: Option<extern "C" fn(*mut c_char,c_int,*mut c_void)->c_int>,
        status: Option<extern "C" fn(*mut c_char,c_int,*mut c_void)->c_int>,
        exit: Option<extern "C" fn(c_int,bool,bool,c_int,*mut c_void)->c_int>,
        data: Option<extern "C" fn(*mut Values,c_int,c_int,*mut c_void)->c_int>,
        init: Option<extern "C" fn(*mut InitValues,c_int,*mut c_void)->c_int>,
        bg: Option<extern "C" fn(bool,c_int,*mut c_void)->c_int>,
        user: *mut c_void,
    ) -> c_int;
    fn ngSpice_Circ(lines: *mut *mut c_char) -> c_int;
    fn ngSpice_Command(command: *mut c_char) -> c_int;
    fn ngSpice_running() -> bool;
}
static TIME: AtomicU64 = AtomicU64::new(0);
static POINTS: AtomicUsize = AtomicUsize::new(0);
static STOPPED: AtomicUsize = AtomicUsize::new(0);

extern "C" fn init_data(_: *mut InitValues, _: c_int, _: *mut c_void) -> c_int {
    // ngspice requires this callback to initialize the per-point transfer data.
    0
}

extern "C" fn text(s: *mut c_char, _: c_int, _: *mut c_void) -> c_int {
    if !s.is_null() {
        // ngspice owns a valid NUL-terminated string for the callback duration.
        let s = unsafe { CStr::from_ptr(s) }.to_string_lossy();
        let _ = writeln!(io::stderr().lock(), "{s}");
    }
    0
}
extern "C" fn exit(status: c_int, _: bool, _: bool, _: c_int, _: *mut c_void) -> c_int {
    let _ = writeln!(io::stderr().lock(), "ngspice_exit={status}");
    0
}
extern "C" fn bg(stopped: bool, _: c_int, _: *mut c_void) -> c_int {
    // Empirically verified ngspice45.2 semantics; also check running().
    if stopped { STOPPED.fetch_add(1, Ordering::Release); }
    0
}
extern "C" fn data(p: *mut Values, _: c_int, _: c_int, _: *mut c_void) -> c_int {
    if p.is_null() { return 0; }
    // All pointers are borrowed only during this callback; never retained.
    let p = unsafe { &*p };
    if p.count <= 0 || p.values.is_null() { return 0; }
    let values = unsafe { std::slice::from_raw_parts(p.values, p.count as usize) };
    for &v in values {
        if v.is_null() { continue; }
        let v = unsafe { &*v };
        if v.scale && !v.complex && v.real.is_finite() {
            TIME.store(v.real.to_bits(), Ordering::Relaxed);
            POINTS.fetch_add(1, Ordering::Relaxed);
            break;
        }
    }
    0
}
fn command(s: &str) -> Result<(), String> {
    let mut s = CString::new(s).map_err(|e|e.to_string())?.into_bytes_with_nul();
    let rc = unsafe { ngSpice_Command(s.as_mut_ptr().cast()) };
    if rc == 0 { Ok(()) } else { Err(format!("command returned {rc}")) }
}
fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args().collect();
    if args.len()!=5 { return Err("usage: progress DECK WALL_SECONDS TARGET_SECONDS EXPORT_PATH".into()); }
    if args[4].chars().any(char::is_whitespace) || args[4].contains([';', '\n', '"']) { return Err("simple export path required".into()); }
    let limit: f64 = args[2].parse().map_err(|_|"invalid wall seconds")?;
    let target: f64 = args[3].parse().map_err(|_|"invalid target seconds")?;
    if !limit.is_finite() || !target.is_finite() || limit<=0.0 || target<=0.0 { return Err("positive finite limits required".into()); }
    let rc=unsafe { ngSpice_Init(Some(text),None,Some(exit),Some(data),Some(init_data),Some(bg),std::ptr::null_mut()) };
    if rc!=0 { return Err(format!("init={rc}")); }
    let lines=fs::read_to_string(&args[1]).map_err(|e|e.to_string())?;
    let signals=lines.lines().filter_map(|s|s.trim().strip_prefix(".save "))
        .flat_map(str::split_whitespace).filter(|s| *s!="time").collect::<Vec<_>>().join(" ");
    if signals.is_empty() { return Err("explicit .save signals required".into()); }
    let lines:Vec<_>=lines.lines().map(CString::new).collect::<Result<_,_>>().map_err(|e|e.to_string())?;
    let mut ptrs:Vec<_>=lines.iter().map(|s|s.as_ptr().cast_mut()).collect();ptrs.push(std::ptr::null_mut());
    command("set ngbehavior=ps")?;
    if unsafe { ngSpice_Circ(ptrs.as_mut_ptr()) }!=0 { return Err("circuit load failed".into()); }
    let mut output=fs::File::create("progress.tsv").map_err(|e|e.to_string())?;
    writeln!(output,"wall_s\tsim_s\tpercent\trecent_sim_s_per_wall_s\tcallbacks").map_err(|e|e.to_string())?;
    let start=Instant::now(); let before=STOPPED.load(Ordering::Acquire);
    command("bg_run")?;
    let mut last_wall=0.0; let mut last_sim=0.0;
    let mut progress_anchor=0.0;
    let mut advanced_at=Instant::now();
    let stop_reason;
    loop {
        thread::sleep(Duration::from_millis(100));
        let wall=start.elapsed().as_secs_f64();
        let now_sim=f64::from_bits(TIME.load(Ordering::Relaxed));
        // Treat less than 1 us advancement over 120 wall seconds as stalled.
        // A halted partial trace remains diagnostic; never a circuit pass.
        if now_sim >= progress_anchor + 1e-6 {
            progress_anchor=now_sim; advanced_at=Instant::now();
        }
        let stalled=advanced_at.elapsed()>=Duration::from_secs(120);
        let done=!unsafe { ngSpice_running() } && STOPPED.load(Ordering::Acquire)>before;
        if wall-last_wall>=10.0 || wall>=limit || done || stalled {
            let sim=f64::from_bits(TIME.load(Ordering::Relaxed));
            let rate=(sim-last_sim)/(wall-last_wall);
            let n=POINTS.load(Ordering::Relaxed);
            let row=format!("{wall:.6}\t{sim:.17e}\t{:.6}\t{rate:.12e}\t{n}",100.0*sim/target);
            println!("{row}");writeln!(output,"{row}").map_err(|e|e.to_string())?;
            output.flush().map_err(|e|e.to_string())?;
            last_wall=wall;last_sim=sim;
        }
        if done { stop_reason="solver_stopped";break; }
        if stalled { stop_reason="less_than_1us_progress_in_120s";break; }
        if wall>=limit { stop_reason="wall_limit";break; }
    }
    if unsafe { ngSpice_running() } {
        command("bg_halt")?;
        let halt=Instant::now();
        while unsafe { ngSpice_running() } {
            if halt.elapsed()>Duration::from_secs(10) { return Err("halt timeout".into()); }
            thread::sleep(Duration::from_millis(10));
        }
    }
    command("rusage tranpoints traniter rejected trantime")?;
    command("set wr_singlescale")?; command("set wr_vecnames")?;command("set numdgt=17")?;
    // Publish stop status before potentially long waveform export.
    fs::write("stop.txt",format!("reason={stop_reason}\nwall_s={:.6}\nsim_s={:.17e}\n",start.elapsed().as_secs_f64(),f64::from_bits(TIME.load(Ordering::Relaxed)))).map_err(|e|e.to_string())?;
    command(&format!("wrdata {} {signals}",args[4]))?;
    command("let idx = length(time)-1")?;
    command("print time[$&idx] v(vb)[$&idx]")?;
    println!("DIAGNOSTIC_ONLY stopped_wall_s={:.6} last_callback_time_s={:.17e}",start.elapsed().as_secs_f64(),f64::from_bits(TIME.load(Ordering::Relaxed)));
    Ok(())
}
