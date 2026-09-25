use std::{env,fs};

fn main() {
    let p = env::args().nth(1).expect("raw path");
    let b = fs::read(&p).expect("raw");
    let h = String::from_utf8_lossy(&b[..b.len().min(4096)]);
    let nvars: usize = h.lines().find_map(|l| l.strip_prefix("No. Variables:")?.trim().parse().ok()).expect("variables");
    let npoints: usize = h.lines().find_map(|l| l.strip_prefix("No. Points:")?.trim().parse().ok()).expect("points");
    let marker = b.windows(7).position(|w| w == b"Binary:").expect("binary marker");
    let start = marker + 7;
    let start = start + if b.get(start) == Some(&b'\n') { 1 } else { 0 };
    let end = start + (npoints - 1) * nvars * 8;
    let raw = &b[end..end + 8];
    let t = f64::from_le_bytes(raw.try_into().unwrap());
    println!("path={} bytes={} nvars={} npoints={} binary_offset={} last_time={:.17e} finite={}", p, b.len(), nvars, npoints, start, t, t.is_finite());
}
