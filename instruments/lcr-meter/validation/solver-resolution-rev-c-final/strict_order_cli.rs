mod strict_order;
use std::{env, fs};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 3, "usage: strict_order_cli deck.cir output-stem");
    let d = fs::read_to_string(&a[1]).unwrap();
    let (n, s) = strict_order::find_order(&a[2], &d, 48).unwrap();
    fs::write(format!("{}-selected.cir", a[2]), s).unwrap();
    println!("PASS order {n}; exact circuit preserved; strict Newton true-DC guard passed");
}
