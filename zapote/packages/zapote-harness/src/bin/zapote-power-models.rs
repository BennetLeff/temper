//! Repeatable analytical screen; no SPICE or measured hardware is implied.
use serde_json::json;
use zapote_erc::power_stage_models::{simulate_doubler, DoublerConfig, DoublerSummary};

fn row(c: DoublerConfig, r: DoublerSummary) -> serde_json::Value {
    json!({"line_rms_v":c.line_rms_v,"line_hz":c.line_hz,"load_dc_w":c.load_w,
      "series_r_ohm":c.series_r_ohm,"physical_capacitance_f":c.capacitance_per_physical_cap_f,
      "parallel_caps_per_half":c.parallel_caps_per_half,"timestep_requested_s":c.timestep_s,
      "cycles":c.cycles,"bus_mean_v":r.bus_mean_v,"bus_ripple_pp_v":r.bus_ripple_pp_v,
      "input_rms_a":r.input_rms_a,"input_real_power_w":r.input_real_power_w,
      "power_factor":r.power_factor,"physical_cap_rms_a":r.physical_cap_rms_a,
      "peak_input_a":r.peak_input_a,"energy_balance_error_w":r.energy_balance_error_w,
      "within_15a_input":r.input_rms_a<=15.0})
}
fn main() -> anyhow::Result<()> {
    let mut fixed_dc = vec![];
    let mut fixed_input = vec![];
    for resistance in [0.1, 0.5, 1.0] {
        let mut c = DoublerConfig {
            line_rms_v: 120.0,
            line_hz: 60.0,
            load_w: 1800.0,
            diode_drop_v: 1.2,
            series_r_ohm: resistance,
            capacitance_per_physical_cap_f: 1800e-6,
            parallel_caps_per_half: 2,
            timestep_s: 2e-6,
            cycles: 120,
            convergence_tolerance: 1e-3,
        };
        let simulate = |c| simulate_doubler(c).map_err(|e| anyhow::anyhow!("model failed: {e:?}"));
        fixed_dc.push(row(c, simulate(c)?));
        let (mut low, mut high) = (100.0, 1800.0);
        for _ in 0..18 {
            c.load_w = (low + high) / 2.0;
            let r = simulate(c)?;
            if r.input_real_power_w > 1800.0 {
                high = c.load_w;
            } else {
                low = c.load_w;
            }
        }
        fixed_input.push(row(c, simulate(c)?));
    }
    let dt = zapote_erc::gate_drive::dead_time_report().map_err(anyhow::Error::msg)?;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
          "schema":"zapote.power-model-screen.v1","method":"Rust time-domain capacitor energy integration; ideal equal parallel sharing; finite series resistance; constant DC power load",
          "physical_tests":"NOT RUN","diode_drop_v":1.2,
          "legacy_1800w_dc_load":fixed_dc,"1800w_ac_input_solved":fixed_input,
          "dead_time_39k_assumed_envelope_ns":{"nominal":dt.nominal_ns,"min":dt.min_ns,"max":dt.max_ns},
          "qualification":"conditional model only; no hot component or switching qualification"
        }))?
    );
    Ok(())
}
