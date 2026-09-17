# Extract the independent-audit TSV contract from the retained report.
# Keep identity fields alongside every numeric row so the standalone audit can
# enforce the canonical 2,916-case grid before checking its equations.
.scenarios[] |
[
  (.index | tostring),
  .device,
  .input.driver_profile,
  .device_source_sha256,
  (.input.line_rms_v | tostring),
  (.simulation_inputs.switching_hz | tostring),
  (.input.driver_v | tostring),
  (.simulation_inputs.rds_on_ohm | tostring),
  (.simulation_inputs.qg_c | tostring),
  (.simulation_inputs.qgd_c | tostring),
  (.simulation_inputs.gate_plateau_v | tostring),
  (.applied_gate_path.turn_on_external_r_ohm | tostring),
  (.applied_gate_path.turn_off_external_r_ohm | tostring),
  (.simulation_inputs.intrinsic_gate_r_ohm | tostring),
  (.simulation_inputs.current_transfer_charge_c | tostring),
  (.simulation_inputs.coss_energy_j | tostring),
  (.turn_on_current_a | tostring),
  (.turn_off_current_a | tostring),
  (.switch_rms_a | tostring),
  (.input_power_w | tostring),
  (.overlap_w | tostring),
  (.eoss_w | tostring),
  (.conduction_w | tostring),
  (.gate_network_w | tostring),
  (.total_w | tostring)
] | @tsv
