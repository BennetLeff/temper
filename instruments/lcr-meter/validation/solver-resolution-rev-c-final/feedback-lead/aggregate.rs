use std::fs;
fn main() {
    let t = fs::read_to_string("current-windows.csv").unwrap();
    let rows: Vec<Vec<&str>> = t.lines().skip(1).map(|l| l.split(',').collect()).collect();
    assert_eq!(rows.len(), 18);
    let mut out=String::from("# Current and ADC windows across the paired corners\n\nRanges include the nominal and both paired corners for each row. Current sign follows the saved deck: negative amplifier output current means sinking.\n\n| Load / lead | ADC pins V | RG µA | Feedback lead µA | DUT µA | HIGH output mA | LOW output mA | TIA output mA |\n|---|---|---|---|---|---|---|---|\n");
    for load in ["open", "coil"] {
        for lead in [10, 20, 50] {
            let prefix = format!("{load}_lead{lead}_");
            let r: Vec<_> = rows.iter().filter(|r| r[0].starts_with(&prefix)).collect();
            assert_eq!(r.len(), 3);
            let range = |lo: usize, hi: usize| {
                let a = r
                    .iter()
                    .map(|r| r[lo].parse::<f64>().unwrap())
                    .fold(f64::INFINITY, f64::min);
                let b = r
                    .iter()
                    .map(|r| r[hi].parse::<f64>().unwrap())
                    .fold(f64::NEG_INFINITY, f64::max);
                format!("{a:.6} to {b:.6}")
            };
            out += &format!(
                "|{load} / {lead}nH|{}|{}|{}|{}|{}|{}|{}|\n",
                range(8, 9),
                range(10, 11),
                range(12, 13),
                range(14, 15),
                range(16, 17),
                range(18, 19),
                range(20, 21)
            );
        }
    }
    fs::write("current-summary.md", out).unwrap();
}
