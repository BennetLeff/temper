//! Reject incomplete catch geometry before a misleading field solve.
use std::{env, fs, process};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2);
    let s = fs::read_to_string(&a[1]).unwrap();
    let complete = s.contains("\"status\": \"COMPLETE_PHYSICAL_FIELD_GEOMETRY\"")
        && !s.contains("UNKNOWN")
        && !s.contains("APPROXIMATION")
        && !s.contains("UNRESOLVED")
        && !s.contains("PORT_CLOSURE_ONLY");
    println!("{{\"complete_physical_geometry\":{complete},\"field_solve_authorized\":{complete},\"reason\":\"holder/fuse internal path, diode die/bond, capacitor distribution and native-return closure must be physical geometry before complete installed inductance can be claimed\"}}");
    if !complete {
        process::exit(3);
    }
}
