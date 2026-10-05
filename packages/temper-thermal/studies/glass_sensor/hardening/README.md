# Glass-sensor hardening handoff

**Simulation and test preparation only. Physical validation: NOT_RUN.**

Open [the consolidated report](report.html). Four Astra workstreams were reviewed and integrated into the local `codex/glass-sensor-simulation` branch. No parts were ordered, hardware energized, firmware flashed or repository changes published.

| Workstream | Concrete output | Remaining boundary |
|---|---|---|
| [Parts/CAD](../parts_revision/README.md) | Exact M222 Pt100 and catalog spring, sourced 316L/bond candidates, updated four-position STEP assemblies, 28,188 mechanics/thermal/material cases | Seal does not support the proposed 250°C envelope; cap retention, wire/lead forming, bond process and mechanical durability unresolved |
| [Contact detection](../contact_detection/README.md) | Fail-closed production state-machine entry/update guards; stable persisted fault IDs; real-guard host tests | No qualified detector or hardware backend; cooking is intentionally inhibited by default |
| [Cartridge validation](../bench_validation/README.md) | Field-free fixture snapshot, acquisition protocol, empty real templates, strict importer, uncertainty budget, mechanics and thermal reduction, independent dynamic holdout calibration | No measured data; synthetic fits do not calibrate the physical cartridge |
| [Induction validation](../induction_validation/README.md) | Full-skirt eddy-current/lead sensitivity, paired acquisition evaluator, hotspot mapping and leakage/cleaning/endurance preparation | Field, self-heating, EMI, local temperatures and physical lifetime unmeasured; analytic cap estimate outside conservative validity at normal frequencies |

## Engineering decision

Do not qualify this cartridge for closed-loop temperature control from these simulations. For the same selected parts, conditional t90 of the sensor's own final rise ranges from 2.185 s (favorable contact/loss assumptions) to 6.460 s (middle) and 16.775 s (weak partial contact). Corresponding local-pan error at 200°C is −0.640, −5.924 and −14.712°C. The weak case never reaches 90% of the imposed pan step in 120 s. These examples are not uncertainty intervals or reliability percentages.

A spring-seat load sensor plus position does not establish continuing pan contact: a jam can preserve both signals after pan removal. The new firmware accepts only a future qualified detector's evidence; no existing RTD or induction-presence signal substitutes for it. A missing backend therefore prevents PAN_DET, PREHEAT and HEATING excitation. A latched contact fault requires the existing hardware-reset/power-cycle policy plus new release/acquisition and explicit START; recovering a sample does not resume cooking.

The custom silicone candidate's 210°C published range is insufficient for a 250°C pan envelope because its inner lip contacts the hot cap. There is no measured seal-temperature bound. Positive cap retention and a force path isolated from guide/seal/stop reactions still need mechanical design work before prototype release. The proposed 0.10 mm ceramic bond requires supplier/process confirmation and coupons; CAD fit does not establish dielectric or fatigue performance.

## Review changes that matter

- Included full skirt mass and conductive geometry instead of crediting roof thinning alone.
- Corrected the real PT100 body and maximum-size fit; changed spring seats and wire envelope to clear the selected spring.
- Added direct state-entry inhibition as well as the periodic control check; preserved runaway priority and persisted fault IDs.
- Made contradictory same-timestamp contact samples revoke permission and required continuous release/load acquisition.
- Strengthened calibration validation against a long steady tail hiding bad dynamics: a synthetic holdout with 0.191°C overall RMSE but 1.811°C transient peak is rejected.
- Kept all missing physical measurements and unapproved limits from becoming passing results.

## Verification and next use

[Verification record](verification.md) names the reproducible commands, integrated results and pre-existing all-target build limitation. [Content provenance](source-provenance.json) hashes the integrated sources, artifacts and logs. The [original study](../report.html) remains a preserved baseline; its PID-only hypothetical gate is separate from this new state-machine implementation.

The next engineering decisions are the high-temperature seal/load-path/retention revision and contact modality. After those are resolved, use the prepared field-free fixture and predeclared fit/holdout runs to calibrate force/contact/thermal behavior, then proceed to instrumented induction and combined endurance testing under approved limits. Nothing in this package is a measured hardware pass or authorization to heat the current assembly to 250°C.
