use std::fs;
fn main() {
    for n in [
        "open_lead10_corner0",
        "open_lead20_corner0",
        "open_lead50_corner0",
    ] {
        let t = fs::read_to_string(format!("{n}_tran.dat")).unwrap();
        let d: Vec<Vec<f64>> = t
            .lines()
            .skip(1)
            .map(|l| l.split_whitespace().map(|x| x.parse().unwrap()).collect())
            .collect();
        let b = d
            .iter()
            .min_by(|a, b| (a[0] - 0.9e-6).abs().total_cmp(&(b[0] - 0.9e-6).abs()))
            .unwrap()[3];
        let r = d
            .iter()
            .max_by(|a, c| (a[3] - b).abs().total_cmp(&(c[3] - b).abs()))
            .unwrap();
        println!("{n} peak t={}ns delta={}uV", r[0] * 1e9, (r[3] - b) * 1e6);
        let pre = d
            .iter()
            .filter(|r| r[0] < 0.99e-6)
            .map(|r| (r[3] - b).abs())
            .fold(0., f64::max);
        println!("pre-edgechange {}uV", pre * 1e6);
    }
}
