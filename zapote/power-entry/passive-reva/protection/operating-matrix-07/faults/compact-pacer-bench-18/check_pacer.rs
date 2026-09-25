use std::{env,fs};

fn expected(t: f64, td: f64) -> f64 {
    let x = t - td;
    if x <= 0.0 { return 0.0; }
    let period = 50e-9;
    let phase = x - period * (x / period).floor();
    if phase <= 25e-9 { phase / 25e-9 } else { (period - phase) / 25e-9 }
}

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
    let td: f64 = 64.999975e-3; let end: f64 = 89e-3; let tol_t: f64 = 1e-14; let tol_v: f64 = 2e-8;
    let mut prev = None; let mut first = 0.0; let mut last = 0.0; let mut first_value = 0.0;
    let mut max_gap: f64 = 0.0; let mut max_active_gap: f64 = 0.0; let mut max_required_gap: f64 = 0.0;
    let mut max_pre = 0.0; let mut min_pre = 0.0; let mut max_active = f64::NEG_INFINITY; let mut min_active = f64::INFINITY;
    let mut active_gaps = 0usize; let mut active_oversize = 0usize; let mut required_gaps = 0usize; let mut required_oversize = 0usize; let mut first_corner_incoming_gap = None; let mut pre_delay_bad = 0usize;
    let mut near_zero = 0usize; let mut near_one = 0usize; let mut max_tri_error: f64 = 0.0;
    let expected_corners = ((end - td) / 25e-9).round() as usize + 1;
    let mut corner_seen = vec![false; expected_corners];
    for i in 0..np {
        let p = off + i * nv * 8;
        let t = f64::from_le_bytes(b[p..p+8].try_into().unwrap());
        let v = f64::from_le_bytes(b[p+8..p+16].try_into().unwrap());
        if !t.is_finite() || !v.is_finite() { return Err(format!("nonfinite row {i}")); }
        if i == 0 { first=t; first_value=v; max_pre=v; min_pre=v; }
        if let Some(old) = prev {
            if t < old { return Err(format!("backwards row {i}")); }
            let gap = t - old; max_gap = max_gap.max(gap);
            if first_corner_incoming_gap.is_none() && old < td && t >= td { first_corner_incoming_gap = Some(gap); }
            if old >= td - tol_t && t <= end + tol_t {
                active_gaps += 1; max_active_gap=max_active_gap.max(gap); if gap > 25e-9 + tol_t { active_oversize += 1; }
            }
            if old >= 65e-3 - tol_t && t <= end + tol_t {
                required_gaps += 1; max_required_gap=max_required_gap.max(gap); if gap > 25e-9 + tol_t { required_oversize += 1; }
            }
        }
        if t < td - tol_t {
            max_pre=max_pre.max(v); min_pre=min_pre.min(v); if v.abs() > tol_v { pre_delay_bad += 1; }
        }
        if t >= td - tol_t && t <= end + tol_t {
            max_active=max_active.max(v); min_active=min_active.min(v);
            let e=expected(t,td); max_tri_error=max_tri_error.max((v-e).abs());
            if v.abs() < 1e-8 { near_zero += 1; } if (v-1.0).abs() < 1e-8 { near_one += 1; }
            let k=((t-td)/25e-9).round();
            if k >= 0.0 && (k as usize) < expected_corners && (t-(td+k*25e-9)).abs() <= tol_t { corner_seen[k as usize] = true; }
        }
        prev=Some(t); last=t;
    }
    if rows_empty(np) || first > 500e-9 || (last-end).abs() > 1e-12 { return Err(format!("rows={np} first={first:.17e} endpoint={last:.17e} expected={end:.17e}")); }
    let corner_hits = corner_seen.iter().filter(|&&x| x).count(); let missing_corners = expected_corners - corner_hits;
    println!("rows={np} first={first:.17e} endpoint={last:.17e} first_value={first_value:.17e} pre_delay_range={min_pre:.17e}..{max_pre:.17e} active_range={min_active:.17e}..{max_active:.17e} max_gap={max_gap:.17e} first_corner_incoming_gap={:.17e} active_max_gap={max_active_gap:.17e} active_gaps={active_gaps} active_oversize={active_oversize} required_max_gap={max_required_gap:.17e} required_gaps={required_gaps} required_oversize={required_oversize} pre_delay_bad={pre_delay_bad} max_tri_error={max_tri_error:.17e} expected_corners={expected_corners} corner_hits={corner_hits} missing_corners={missing_corners} near_zero={near_zero} near_one={near_one}", first_corner_incoming_gap.unwrap_or(f64::NAN));
    if active_oversize != 0 || required_oversize != 0 || pre_delay_bad != 0 || max_tri_error > tol_v || missing_corners != 0 || near_zero == 0 || near_one == 0 { return Err("pacer checks failed".into()); }
    Ok(())
}
fn rows_empty(n: usize) -> bool { n == 0 }
