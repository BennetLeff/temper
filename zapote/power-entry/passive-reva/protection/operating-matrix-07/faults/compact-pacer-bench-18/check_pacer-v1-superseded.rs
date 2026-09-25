use std::{env,fs};

fn main() -> Result<(), String> {
    let path = env::args().nth(1).ok_or("raw path")?;
    let b = fs::read(&path).map_err(|e| e.to_string())?;
    let h = String::from_utf8_lossy(&b[..b.len().min(4096)]);
    let nv: usize = h.lines().find_map(|l| l.strip_prefix("No. Variables:")?.trim().parse().ok()).ok_or("variables")?;
    let np: usize = h.lines().find_map(|l| l.strip_prefix("No. Points:")?.trim().parse().ok()).ok_or("points")?;
    if nv != 2 { return Err(format!("expected 2 variables, got {nv}")); }
    let marker = b.windows(7).position(|w| w == b"Binary:").ok_or("binary marker")?;
    let mut off = marker + 7; if b.get(off) == Some(&b'\n') { off += 1; }
    let need = off.checked_add(np.checked_mul(nv).ok_or("overflow")?.checked_mul(8).ok_or("overflow")?).ok_or("overflow")?;
    if need > b.len() { return Err(format!("truncated raw need={need} bytes={}", b.len())); }
    let mut prev = None; let mut first = 0.0; let mut last = 0.0; let mut first_value = 0.0;
    let mut max_gap: f64 = 0.0; let mut max_pre: f64 = 0.0; let mut min_pre: f64 = 0.0;
    let mut max_active = f64::NEG_INFINITY; let mut min_active = f64::INFINITY;
    let mut active_gaps = 0usize; let mut active_oversize = 0usize; let mut corners = 0usize;
    let mut near_one = 0usize; let mut near_zero = 0usize; let tol = 1e-12;
    for i in 0..np {
        let p = off + i * nv * 8;
        let t = f64::from_le_bytes(b[p..p+8].try_into().unwrap());
        let v = f64::from_le_bytes(b[p+8..p+16].try_into().unwrap());
        if !t.is_finite() || !v.is_finite() { return Err(format!("nonfinite row {i}")); }
        if i == 0 { first=t; first_value=v; max_pre=v; min_pre=v; }
        if let Some(old) = prev {
            if t < old { return Err(format!("backwards row {i}")); }
            let gap = t - old; max_gap = max_gap.max(gap);
            if t >= 0.065 - tol && t <= 0.089 + tol {
                active_gaps += 1; if gap > 25e-9 + 1e-14 { active_oversize += 1; }
            }
        }
        if t < 0.065 - tol { max_pre=max_pre.max(v); min_pre=min_pre.min(v); }
        if t >= 0.065 - tol && t <= 0.089 + tol {
            max_active=max_active.max(v); min_active=min_active.min(v);
            if (v - 1.0).abs() < 1e-8 { near_one += 1; }
            if v.abs() < 1e-8 { near_zero += 1; }
            if let Some(old) = prev { if (v-old).abs() > 0.5 { corners += 1; } }
        }
        prev=Some(t); last=t;
    }
    if (last - 0.089).abs() > 1e-12 { return Err(format!("endpoint={last:.17e}")); }
    println!("rows={np} first={first:.17e} endpoint={last:.17e} first_value={first_value:.17e} pre_range={min_pre:.17e}..{max_pre:.17e} active_range={min_active:.17e}..{max_active:.17e} max_gap={max_gap:.17e} active_gaps={active_gaps} active_oversize={active_oversize} corner_transitions={corners} near_zero={near_zero} near_one={near_one}");
    if first > 1e-9 || active_oversize != 0 || near_zero == 0 || near_one == 0 { return Err("pacer checks failed".into()); }
    Ok(())
}
