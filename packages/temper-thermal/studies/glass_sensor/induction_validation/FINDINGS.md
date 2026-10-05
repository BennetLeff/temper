# Findings and remaining evidence

**Ready for instrumented prototype planning; physical tests NOT RUN.** The screening package is complete for simulation/test preparation. It does not support a claim that the sensor is induction-immune, sealed or endurance-qualified.

| Priority | Finding | Evidence class | Consequence / next evidence |
|---|---|---|---|
| 1 | Closed skirt contributes3.50× roof eddy power in the imposed axial-field integral for the0.15mm-roof316L candidate | Calculated sensitivity | Thinning only the roof does not remove most possible metal heating. Measure field and manufactured cap; validate full roof/skirt model |
| 1 | At40kHz/20°C, wall/skin-depth0.184 but sheet-reaction parameter0.842 | Calculated screening parameters | Thin through-wall current alone is insufficient to validate the unshielded formula. Normal operating range lies outside the combined small-parameter regime; no accepted heating bound |
| 1 | Actual coil/ferrite/pan geometry, local vector field and cap material magnetic response are missing | Observed artifact/evidence gap | Cannot convert the parametric field sweep into device self-heating or safety-margin claims |
| 1 | Plausible in-range temperature or contact signals may be wrong under switching interference | Hypothesis based on physical coupling; legacy converter identified | Test dummy resistor, independent references, raw RTD/contact channels and actual inhibition path under switching; no contact proof from RTD plausibility |
| 1 | Center temperature can miss off-axis peak in imposed-annulus model | Simulated prior kernel, not candidate hardware | Spatial thermal mapping and independent overtemperature strategy required; do not rely on calibration at center alone |
| 1 | Seal/hot-surface/accessible-electrical test limits and service profile unresolved | Missing approved requirements | Leakage/endurance evaluator refuses absent data; fixtures carry software-only limits |
| 2 | MAX31865 conversion/settling interval materially exceeds simple PWM blanking intervals | Datasheet | Synchronize at fresh settled conversions; measure added fault latency after changing analog filters |

For scale only, the unshielded selected-cap formula at40kHz gives:

| Assumed axial B RMS | Roof | Skirt | Total extrapolated sensitivity |
|---:|---:|---:|---:|
| 0.1mT | 0.031mW | 0.108mW | 0.139mW |
| 1mT | 3.101mW | 10.845mW | 13.946mW |
| 10mT | 0.310W | 1.085W | 1.395W |

**Every row above is outside the combined small-parameter regime. These are neither actual field estimates nor rigorous upper bounds.** They show why missing field/material data matter. At1mT, the conditional13.95mW divided by assumed thermal conductance0.01 or0.1W/K corresponds to1.39 or0.14K incremental rise; neither conductance was measured.

A1mm² effective uncompensated loop at40kHz/1mT has0.251mV RMS induced emf, equivalent to0.653K at1mA using the low-temperature0.385Ω/K slope before filtering. This does not predict MAX31865 error or include common-mode rectification.

The synthetic hotspot fixture at120s gives peak-minus-sensor gaps116.1K(steel proxy),50.4K(cast-iron proxy),19.6K(aluminum-core proxy). These arise from a deliberately imposed500W annular heating distribution with no food, the prior cap model and assumed boundary conductances. They are not Temper cookware forecasts; their purpose is to exercise acquisition/map analysis and illustrate observability. Eight azimuths are repeated axisymmetric samples, not evidence of actual rotational symmetry.

Verification:22 Rust unit/adversarial tests; executable raw-digest check; synthetic paired/endurance workflow succeeds with SYNTHETIC_ONLY_NO_HARDWARE_VERDICT; intentionally absent measurement rejected with exit2. Sweeps:540 cap cases,72 loop cases,840 synthetic hotspot rows. Nothing was acquired from real hardware.

Before a physical campaign, the minimum blockers are: built/traced cartridge and actual power/coil assembly; selected/certified instruments with calibrated dissimilar local references; approved accessible-part/insulation and leakage requirements; controlled cookware/force/contact fixture; material/cure/finish identity and cap magnetic characterization; service/cleaning/stress profile and approved thermal/force/error limits; a functioning independent contact-to-inhibit route with measured current-extinction timing. Hardware safety and manufacturing owners need to sign the future protocol before live testing. This is test preparation, not a request for permission to energize now.
