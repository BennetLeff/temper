Buck engineering validation: blocked

Hardware validation: unverified (stage 5 has not run).

requirements: blocked
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
- mandatory_load_profile_missing: continuous_50mA_to_500mA
- mandatory_load_profile_missing: pulse_50mA_to_1A
- scenario_coverage_missing: adopted protocol requires six startup, six load, and one input case
- load_matrix_missing: VIN 13500 mV, continuous_50mA_to_500mA
- load_matrix_missing: VIN 13500 mV, pulse_50mA_to_1A
- startup_matrix_missing: VIN 13500 mV, load 0 mA
- startup_matrix_missing: VIN 13500 mV, load 500 mA
- load_matrix_missing: VIN 15000 mV, continuous_50mA_to_500mA
- load_matrix_missing: VIN 15000 mV, pulse_50mA_to_1A
- startup_matrix_missing: VIN 15000 mV, load 0 mA
- startup_matrix_missing: VIN 15000 mV, load 500 mA
- load_matrix_missing: VIN 16500 mV, continuous_50mA_to_500mA
- load_matrix_missing: VIN 16500 mV, pulse_50mA_to_1A
- startup_matrix_missing: VIN 16500 mV, load 0 mA
- startup_matrix_missing: VIN 16500 mV, load 500 mA
- circuit_not_qualified: circuit qualification is required for stage admission

layout: blocked
- circuit_not_qualified: circuit qualification is required for stage admission

physical: not_run
- hardware_unverified: hardware validation is deferred in this milestone
