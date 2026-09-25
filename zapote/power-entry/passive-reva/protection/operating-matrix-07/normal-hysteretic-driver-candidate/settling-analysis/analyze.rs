use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use std::process::{Command, Stdio};

const PERIOD: f64 = 1.0 / 60.0;

#[derive(Default, Clone)]
struct Cycle {
    n: i64,
    t0: f64,
    t1: f64,
    vb_int: f64,
    q_int: f64,
    en_int: f64,
    il_peak: f64,
    vd_peak: f64,
    vb_min: f64,
    vb_max: f64,
    gate_max: f64,
    rows: u64,
}
impl Cycle {
    fn new(n: i64) -> Self { Self { n, t0: n as f64 * PERIOD, t1: (n + 1) as f64 * PERIOD, vb_min: f64::INFINITY, ..Self::default() } }
    fn add(&mut self, a: [f64; 8], b: [f64; 8], ta: f64, tb: f64) {
        let dt = tb - ta;
        if !(dt > 0.0) { return; }
        let f = |x: f64, y: f64| 0.5 * (x + y) * dt;
        self.vb_int += f(a[0], b[0]);
        self.q_int += f(a[1], b[1]);
        self.en_int += f(a[2], b[2]);
        self.il_peak = self.il_peak.max(a[3].abs()).max(b[3].abs());
        self.vd_peak = self.vd_peak.max(a[4]).max(b[4]);
        self.vb_min = self.vb_min.min(a[0]).min(b[0]);
        self.vb_max = self.vb_max.max(a[0]).max(b[0]);
        self.gate_max = self.gate_max.max(a[5]).max(b[5]);
    }
    fn finish_line(&mut self, out: &mut impl Write) -> io::Result<()> {
        let span = self.t1 - self.t0;
        writeln!(out, "{}\t{:.12e}\t{:.9e}\t{:.9e}\t{:.9e}\t{:.9e}\t{:.9e}\t{:.9e}\t{:.9e}\t{:.9e}\t{}",
            self.n, self.vb_int / span, self.vb_min, self.vb_max, self.vb_max-self.vb_min,
            self.q_int/span, self.en_int/span, self.il_peak, self.vd_peak, self.gate_max, self.rows)?;
        Ok(())
    }
}

fn parse_fields(line: &str) -> Option<[f64; 8]> {
    let mut v = line.split_whitespace().map(|x| x.parse::<f64>().ok());
    let mut col = [0.0; 31];
    for x in col.iter_mut() { *x = v.next()??; }
    // t, VB, Q, EN, I(Lboost), VD, gate. Include time separately in caller.
    Some([col[5], col[10], col[11], col[6], col[7], col[9], col[8], col[18]])
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 { eprintln!("usage: settling_analysis TRACE.tsv.gz OUTPUT.tsv"); std::process::exit(2); }
    let trace = &args[1];
    let mut child = Command::new("gzip").args(["-dc", trace]).stdout(Stdio::piped()).spawn()?;
    let stdout = child.stdout.take().unwrap();
    let mut rd = BufReader::with_capacity(1024 * 1024, stdout);
    let mut line = String::new();
    rd.read_line(&mut line)?; // header
    let mut out = File::create(&args[2])?;
    writeln!(out, "# source={} period_s={:.15e}", trace, PERIOD)?;
    writeln!(out, "cycle\tmean_vb\tmin_vb\tmax_vb\tripple_pp\tq_mean_v\ten_mean_v\til_peak_abs_a\tvd_peak_v\tgate_peak_v\tsegment_rows")?;
    let mut prev_t: Option<f64> = None;
    let mut prev: [f64; 8] = [0.0; 8];
    let mut active: Option<Cycle> = None;
    let mut last_n: Option<i64> = None;
    let mut seen: u64 = 0;
    while rd.read_line(&mut line)? != 0 {
        let s = line.trim();
        if s.is_empty() { line.clear(); continue; }
        let mut split = s.split_whitespace();
        let t: f64 = match split.next().and_then(|x| x.parse().ok()) { Some(x) => x, None => { line.clear(); continue; } };
        let f = match parse_fields(s) { Some(x) => x, None => { line.clear(); continue; } };
        if let Some(ta) = prev_t {
            if t > ta {
                let mut left_t = ta;
                let mut left = prev;
                while left_t < t {
                    let n = (left_t / PERIOD).floor() as i64;
                    let end = (((n + 1) as f64) * PERIOD).min(t);
                    let frac = ((end - left_t) / (t - left_t)).clamp(0.0, 1.0);
                    let mut right = [0.0; 8];
                    for j in 0..8 { right[j] = left[j] + (f[j] - left[j]) * frac; }
                    if n < 15 || n > 30 { left_t = end; left = right; continue; }
                    if last_n != Some(n) {
                        if let Some(mut old) = active.take() { old.finish_line(&mut out)?; }
                        active = Some(Cycle::new(n)); last_n = Some(n);
                    }
                    let c = active.as_mut().unwrap(); c.add(left, right, left_t, end); c.rows += 1;
                    left_t = end; left = right;
                }
            }
        }
        prev_t = Some(t); prev = f; seen += 1; line.clear();
    }
    if let Some(mut old) = active.take() { old.finish_line(&mut out)?; }
    let status = child.wait()?;
    if !status.success() { return Err(format!("gzip failed: {status}").into()); }
    eprintln!("rows={seen} wrote={}", args[2]);
    Ok(())
}
