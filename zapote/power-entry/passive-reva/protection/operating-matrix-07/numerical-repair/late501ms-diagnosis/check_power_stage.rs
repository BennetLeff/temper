use std::fs;

fn main() {
    let text = fs::read_to_string("recorded-power-stage.tsv").expect("trace");
    let mut rows = 0_u64;
    let mut previous = None;
    let mut last = 0.0_f64;
    let mut max_gate = f64::NEG_INFINITY;
    let mut min_gate = f64::INFINITY;
    let mut max_sw = f64::NEG_INFINITY;
    let mut min_sw = f64::INFINITY;
    let mut max_driver = f64::NEG_INFINITY;
    for line in text.lines().skip(1).filter(|line| !line.trim().is_empty()) {
        let values: Vec<f64> = line
            .split_whitespace()
            .map(|value| value.parse().expect("numeric row"))
            .collect();
        assert!(values.len() >= 9, "short row");
        assert!(values.iter().all(|value| value.is_finite()), "nonfinite row");
        let time = values[0];
        if rows == 0 {
            assert!((values[4] - 378.1957698276312).abs() < 1.0, "bad initial switch node: {}", values[4]);
            assert!((values[6] - 4.1047796553663).abs() < 1e-3, "bad initial inductor current: {}", values[6]);
        }
        if let Some(old) = previous {
            assert!(time > old, "non-increasing time: {old:.18e} -> {time:.18e}");
        }
        previous = Some(time);
        last = time;
        max_gate = max_gate.max(values[3]);
        min_gate = min_gate.min(values[3]);
        max_sw = max_sw.max(values[4]);
        min_sw = min_sw.min(values[4]);
        max_driver = max_driver.max(values[7]);
        rows += 1;
    }
    assert!(rows > 100, "too few rows: {rows}");
    assert!(last >= 199.9e-9, "did not reach post-edge window: {last:.18e}");
    assert!(max_gate > 4.0, "driver did not charge the Miller-loaded gate: {max_gate:.6e}");
    assert!(min_sw < 5.0, "switch node did not fall after the gate transition: {min_sw:.6e}");
    assert!(max_driver > 14.9, "driver request did not reach aux rail: {max_driver:.6e}");
    println!(
        "rows={rows} final={last:.18e} gate_min={min_gate:.9e} gate_max={max_gate:.9e} sw_min={min_sw:.9e} sw_max={max_sw:.9e} driver_req_max={max_driver:.9e}"
    );
}
