use std::fmt::Write;

const BUS_V: f64 = 389.615;
const LINE_V: [f64; 3] = [108.0, 120.0, 132.0];
const LOAD_FRACTIONS: [f64; 3] = [0.25, 0.50, 0.90];

fn main() {
    let mut json = String::from(
        "{\n  \"status\": \"planned_unexecuted\",\n  \"source_identity\": {\"deck\": \"PENDING_ACCEPTED_COLD_SOURCE\", \"sha256\": \"PENDING\", \"includes_sha256\": \"PENDING\"},\n  \"assumptions\": {\"bus_v\": 389.615, \"line_hz\": 60.0, \"line_current_limit_a\": 15.0, \"cap_w\": 1800.0, \"pf_for_load_choice\": 1.0, \"efficiency_for_load_choice\": 0.9},\n  \"points\": [\n",
    );
    let mut first = true;
    let mut id = 0;
    for line_v in LINE_V {
        let cap = (1800.0_f64).min(15.0 * line_v) * 0.9;
        for fraction in LOAD_FRACTIONS {
            let target_w = cap * fraction;
            let rload = BUS_V * BUS_V / target_w;
            id += 1;
            if !first { json.push_str(",\n"); }
            first = false;
            write!(
                json,
                "    {{\"id\":\"LL{id:02}\",\"line_v_rms\":{line_v:.3},\"load_fraction\":{fraction:.2},\"conditional_cap_w\":{cap:.6},\"target_load_w\":{target_w:.6},\"rload_ohm\":{rload:.9},\"status\":\"planned_unexecuted\"}}"
            ).unwrap();
        }
    }
    let baseline_w = BUS_V * BUS_V / 190.0;
    write!(json, "\n  ],\n  \"nominal_baseline\": {{\"line_v_rms\": 120.0, \"rload_ohm\": 190.0, \"ideal_bus_load_w\": {baseline_w:.9}, \"status\": \"reference_only_not_grid_point\"}}\n}}\n").unwrap();
    print!("{json}");
}
