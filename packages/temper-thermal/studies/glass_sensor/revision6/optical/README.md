# R6 optical feasibility screen

**HYPOTHETICAL_OPTICS, not predicted product accuracy.** No final glass, coating, filter, detector, optical throughput or noise spectrum has been selected or measured. Every transmission curve in this executable is invented for sensitivity analysis. There is no installed response-time prediction or pass/fail product result.

The Rust model integrates Planck spectral radiance over 3–5 µm. Units are W m⁻² sr⁻¹ after wavelength integration. An opaque gray pan emits εB(Tpan) and reflects (1−ε)B(Tbackground). Nonreflecting glass and filter layers transmit τL and emit (1−τ)B(Tlayer). Net signal subtracts blackbody radiance at the detector-can temperature. This is an idealized diffuse background and absorptive stack: specular cookware, angular Fresnel reflection, multiple reflections, window optics, amplifier responsivity and actual detector geometry are outside the model. Energy-consistent emissivity/transmission replaces any unsupported claim of a spectrally selective real coating.

Synthetic glass transmission falls linearly from 0.75 at 3µm to 0.15 at 5µm. Three comparisons use no additional filter, a gray 50% filter, and an invented shaped filter with the same curve as the synthetic glass. The shaped option is not a reconstruction of the published paper's filter. It can attenuate signal; it must not be interpreted as a free reduction in error or measured benefit of spectral matching.

The nominal inversion assumes ε=0.6, glass80°C, filter/can40°C and reflected background25°C. Actual emissivity, glass/filter/can temperature and transmission vary independently. Inversion reports out-of-range instead of clamping an invalid reading to a plausible pan temperature. Matched-parameter round trips check numerical correctness only. They are not independent validation.

`results/sensitivity.csv` contains 84 cases. `radiance_sensitivity.csv` contains 45 conversion sensitivities for hypothetical absolute radiance offsets of0.001/0.01/0.1 W m⁻² sr⁻¹. These are NOT detector NETD, noise measurements or probabilities. `field_of_view.csv` contains six geometric cone footprints without refraction; the20°/90° examples are not a finished optical design. Keeping a cone inside the pan does not establish uniform temperature in its footprint.

## Literature correction and reproducibility limits

The 2025 paper's1.183/1.074/1.315°C RMSE compares a forward radiation model with thermopile readings while using measured pan AND glass temperatures as inputs (§3.2–3.4, Figure22). The authors report approximately±3°C maximum pan error in their experiments. No blind unknown-cookware <2°C guarantee or full-system t90 is established. The detector's20ms time constant is a different quantity. The additional10×10×0.5mm filter and unnamed sensor do not supply orderable specifications sufficient to reproduce the result.

- [2025 primary article](https://www.mdpi.com/1424-8220/25/1/235)
- [Full-text XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC11723203/fullTextXML)
- [2026 emissivity-estimation paper](https://doi.org/10.1016/j.sna.2025.117407): accessible abstract reports average error2.73°C; this is not a maximum bound.
- [SCHOTT glass families](https://www.schott.com/en-us/products/ceran-p1000315/downloads): an exact lot/thickness/coating spectrum remains missing.
- [Hamamatsu T11361-01](https://www.hamamatsu.com/us/en/product/optical-sensors/infrared-detector/thermopile-detector/T11361-01.html): possible bench detector, not the paper's identified sensor or a qualified replacement.

## Required next evidence

Obtain transmission/reflectance versus wavelength and temperature for the exact unperforated glass/coatings and filter. Include field of view, detector noise/responsivity, filter/can temperatures and their transient behavior. Then use independently heated pan/glass coupons and entire held-out cookware specimens. Include oil/water/residue, oxidation, tilt, cold pan on hot glass and thermal soak. The present R5 glass-hole CAD is not an intact-glass optical assembly.

Run `./run.sh`. All physical tests remain NOT_RUN.
