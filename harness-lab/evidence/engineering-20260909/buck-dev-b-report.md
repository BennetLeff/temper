Buck engineering validation: blocked

Hardware validation: unverified (stage 5 has not run).

requirements: blocked
- mandatory_limit_unresolved (vin_min): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (vin_max): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (iout_continuous): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (iout_peak): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (iout_peak_duration): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (ripple_amplitude): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (ripple_bandwidth): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (startup_ramp): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (startup_overshoot): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (startup_settling): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (load_step_endpoints): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (load_step_slew): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (load_step_undershoot): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (load_step_overshoot): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (load_step_recovery): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (ambient_temperature): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (thermal_limit): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (efficiency_operating_points): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (capacitor_effective_value): mandatory acceptance limit remains unresolved
- mandatory_limit_unresolved (inductor_current_rating): mandatory acceptance limit remains unresolved

circuit: blocked
- component_qualification_missing: reviewed capacitor DC-bias derating and inductor saturation evidence is required
- unresolved_requirement: an owning requirement has no approved limit

simulation: blocked
- exact_model_missing: exact LMR51430XDDCR 500 kHz PFM, 0.6 V model identity is required
- qualification_not_approved: exact model receipt is absent from the trusted approval registry
- model_not_qualified: reviewed independent qualification evidence bound to the exact model is required
- unsupported_coverage: startup
- unsupported_coverage: input_variation
- unsupported_coverage: load_variation
- identity_missing: settings_sha256
- mandatory_scenario_missing: startup
- mandatory_scenario_missing: input_variation
- mandatory_scenario_missing: load_variation
- circuit_not_qualified: circuit qualification is required for stage admission
- unresolved_requirement: an owning requirement has no approved limit

layout: fail
- ground_return: {"id": "ground_return", "maximum_mm": 20.0, "path_length_mm": 43.66733586345292}
- labels_missing: {"id": "labels_missing"}
- circuit_not_qualified: circuit qualification is required for stage admission

physical: not_run
- hardware_unverified: hardware validation is deferred in this milestone
