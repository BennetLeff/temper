//! Exact-network declaration-order conditioning for ngspice/KLU. No component edits.
//! optran 1 0 0 0 0 0 permits Newton only; no gmin/source/transient fallback.
use std::{
    collections::BTreeMap,
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
pub fn reorder(deck: &str, order: u64) -> String {
    let (h, c) = deck.split_once(".control").expect("control block");
    let mut pre = String::new();
    let mut parts = Vec::new();
    for (i, l) in h.lines().enumerate() {
        if i == 0 || l.trim().is_empty() || l.starts_with(['.', '*']) {
            pre += l;
            pre.push('\n')
        } else {
            assert!(!l.starts_with('+'), "continuations require grouping");
            parts.push(l.to_string())
        }
    }
    if order == 1 {
        parts.reverse()
    } else if order >= 2 {
        parts.sort_by_key(|l| {
            let mut h = 14695981039346656037u64 ^ (order - 1);
            for b in l.bytes() {
                h = (h ^ b as u64).wrapping_mul(1099511628211)
            }
            h
        });
    }
    format!("{pre}{}\n.control{c}", parts.join("\n"))
}
pub fn true_op(path: &str) -> Result<BTreeMap<String, f64>, String> {
    let t = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if !t.contains("No. Points: 1\n") || !t.contains("Plotname: Operating Point\n") {
        return Err("not exactly one OP".into());
    }
    let (h, v) = t.split_once("Values:\n").ok_or("missing values")?;
    let names: Vec<_> = h
        .split_once("Variables:\n")
        .ok_or("missing variables")?
        .1
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().nth(1).unwrap().to_string())
        .collect();
    let vals = v
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .last()
                .unwrap()
                .parse::<f64>()
                .map_err(|e| e.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if names.len() != vals.len() || vals.iter().any(|v| !v.is_finite()) {
        return Err("invalid values".into());
    }
    let r: BTreeMap<_, _> = names.into_iter().zip(vals).collect();
    let rail = *r.get("v(v5)").ok_or("missing v5")?;
    for a in ["xa", "xb"] {
        let mid = *r.get(&format!("v({a}.mid)")).ok_or("missing MID")?;
        if (mid - rail / (2. + 1e-6)).abs() > 1e-6 {
            return Err(format!("false {a}.MID {mid}"));
        }
    }
    if r.get("v(acin)").ok_or("missing acin")?.abs() > 1e-4 {
        return Err("AC input DC invalid".into());
    }
    Ok(r)
}
pub fn find_order(tag: &str, deck: &str, max_orders: u64) -> Result<(u64, String), String> {
    for order in 0..max_orders {
        let d = reorder(deck, order);
        let h = d.split_once(".control").unwrap().0;
        let stem = format!("{tag}-order{order}");
        let raw = format!("{stem}.raw");
        let _ = fs::remove_file(&raw);
        let op=format!("{h}.control\nset klu\noptran 1 0 0 0 0 0\nset filetype=ascii\nset numdgt=17\nop\nwrite {raw} all\nquit\n.endc\n.end\n");
        fs::write(format!("{stem}.cir"), op).map_err(|e| e.to_string())?;
        let f = fs::File::create(format!("{stem}.log")).map_err(|e| e.to_string())?;
        let mut child =
            Command::new(std::env::var("NGSPICE").unwrap_or("/opt/homebrew/bin/ngspice".into()))
                .args(["-b", &format!("{stem}.cir")])
                .stdout(Stdio::from(f.try_clone().unwrap()))
                .stderr(Stdio::from(f))
                .spawn()
                .map_err(|e| e.to_string())?;
        let start = Instant::now();
        while child.try_wait().map_err(|e| e.to_string())?.is_none() {
            if start.elapsed() > Duration::from_secs(3) {
                child.kill().map_err(|e| e.to_string())?;
                child.wait().map_err(|e| e.to_string())?;
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
        let log = fs::read_to_string(format!("{stem}.log")).unwrap();
        if !log.contains("Error") && !log.contains("aborted") && true_op(&raw).is_ok() {
            let result = d.replace("set klu\n", "set klu\noptran 1 0 0 0 0 0\n");
            fs::write(format!("{tag}-selected-order.txt"), format!("{order}\n")).unwrap();
            return Ok((order, result));
        }
    }
    Err(format!(
        "no true strict Newton solution in {max_orders} exact-network declaration orders"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn permutations_preserve_every_component_exactly() {
        let deck = fs::read_to_string("tests/partition.cir").unwrap();
        let lines = |d: &str| {
            let mut out: Vec<String> = d
                .split_once(".control")
                .unwrap()
                .0
                .lines()
                .skip(1)
                .filter(|l| !l.trim().is_empty() && !l.starts_with(['.', '*']))
                .map(str::to_owned)
                .collect();
            out.sort();
            out
        };
        let expected = lines(&deck);
        for order in 0..48 {
            let result = reorder(&deck, order);
            assert_eq!(lines(&result), expected);
            assert_eq!(result, reorder(&deck, order));
        }
    }
    #[test]
    fn false_transient_operating_point_is_rejected() {
        let error = true_op("tests/false-op-negative.raw").unwrap_err();
        assert!(error.contains("false xa.MID"));
    }
    #[test]
    fn complete_true_final_operating_point_is_accepted() {
        let r = true_op("tests/order0.raw").unwrap();
        assert!((r["v(aop)"] - 2.047899436647).abs() < 1e-8);
    }
}
