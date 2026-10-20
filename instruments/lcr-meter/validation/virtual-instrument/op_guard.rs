//! Thin CLI around the committed strict-order/true-OP helper, so the Python
//! transfer harness uses exactly the same conditioning and false-OP rejection.
//!
//!   op_guard order TAG DECK.cir OUT.cir   -> search declaration orders, write the accepted deck
//!   op_guard check OP.raw                 -> exit 0 only for a true operating point
#[path = "../solver-resolution-rev-c-final/strict_order.rs"]
#[allow(dead_code)]
mod strict_order;
use std::{env, fs, process};

fn main() {
    let a: Vec<String> = env::args().collect();
    let result = match a.get(1).map(String::as_str) {
        Some("order") if a.len() == 5 => fs::read_to_string(&a[3])
            .map_err(|e| e.to_string())
            .and_then(|deck| strict_order::find_order(&a[2], &deck, 12))
            .and_then(|(order, deck)| {
                fs::write(&a[4], deck).map_err(|e| e.to_string())?;
                println!("order {order}");
                Ok(())
            }),
        Some("check") if a.len() == 3 => strict_order::true_op(&a[2]).map(|r| {
            println!(
                "true OP: xa.MID {:.9} xb.MID {:.9} acin {:.3e}",
                r["v(xa.mid)"], r["v(xb.mid)"], r["v(acin)"]
            )
        }),
        _ => Err("usage: op_guard order TAG DECK OUT | op_guard check OP.raw".into()),
    };
    if let Err(e) = result {
        eprintln!("{e}");
        process::exit(1);
    }
}
