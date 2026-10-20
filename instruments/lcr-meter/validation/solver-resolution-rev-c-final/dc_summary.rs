mod strict_order;
fn main() {
    let r = strict_order::true_op("revc_100r_cap100n_op.raw").unwrap();
    for node in [
        "aop", "aom", "afbp", "afbm", "bop", "bom", "bfbp", "bfbm", "highbuf", "lowbuf", "tia",
        "aip", "aim", "bip", "bim",
    ] {
        println!("{node}: {:.12} V", r[&format!("v({node})")]);
    }
    let v = |n: &str| r[&format!("v({n})")];
    println!(
        "highbuf FDA load={:.9} mA; lowbuf FDA load={:.9} mA; TIA FDA load={:.9} mA",
        (v("highbuf") - v("aip")),
        (v("lowbuf") - v("aim")) + (v("lowbuf") - v("bip")),
        v("tia") - v("bim")
    );
}
