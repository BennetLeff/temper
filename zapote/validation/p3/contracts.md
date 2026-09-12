# P3 contract schema

The coordinator owns transport and unit applicability. The Rust APIs below
are the rule boundary and have no donor runtime dependency.

`SwitchingBoard` contains native `SwitchingTrace { id, net, points_mm }`
and `SwitchingVia { id, net, position_mm }` records. `SwitchingContract.paths`
contains `CommutationPath { name, current_nets, return_net,
max_bbox_area_mm2, required_return_stitches }`; `noise_pairs` contains
`NoisePair { aggressor_net, victim_net, max_parallel_mm }`.

`DeviceOperatingPoint` contains `device, loss_w, theta_jc_c_per_w,
theta_cs_c_per_w, theta_sa_c_per_w, ambient_c, max_junction_c`.
`ShutdownTimingBound` contains `path, detection_ms, actuation_ms,
switching_off_ms, max_response_ms`. All delay fields are worst-case bounds;
nominal values are not accepted as guarantees.
