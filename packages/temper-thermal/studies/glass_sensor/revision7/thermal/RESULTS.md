# R7 thermal results

All rows are offline predictions from the CAD-coupled lumped/radial model. Physical status is `NOT_RUN`.

| Geometry | Pan-relative t90 | Own-final t90 | Steady underread at pan 200°C | Finite 5°C/s ramp error at 200°C |
|---|---:|---:|---:|---:|
| Frozen R5 D6 reference | 2.94 s | 2.69 s | 2.474231°C | 9.784272°C |
| R7 M222 clearance-corrected control, 0.10 mm bond | 2.91 s | 2.67 s | 2.474231°C | 9.746388°C |
| R7 M222 matched thin-bond coupon, 0.075 mm bond | 2.78 s | 2.55 s | 2.440587°C | 9.448343°C |
| R7 IST308, 0.075 mm bond and complete revised geometry | **2.05 s** | **1.84 s** | **2.576544°C** | **8.109891°C** |

These comparisons use uniform contact, nominal loss assumptions and reference h = 2,000 W/m²K. The corrected M222 control has lighter clearance-relieved covers than the frozen R5 design, so it intentionally responds slightly faster; R5 remains an independently reproduced historical baseline. The M222 A/B pair uses matched cover relief, isolating bond changes in the thermal network.

The IST308 speed improvement survives the complete modeled cover, anchor, lead and wire geometry. Its nominal steady error is slightly worse than M222 thin-bond: the smaller sensor footprint raises the bond's through-thickness thermal resistance, and the installed lead route changes heat leakage. Smaller chip mass is not an accuracy fix.

## What changes the conclusion

- IST308 rim contact predicts **5.47 s and 6.081631°C underread**, versus 2.05 s and 2.576544°C with uniform contact. Center contact gives 2.17 s and 2.820040°C. The actual contact distribution must be established experimentally.
- Raising assumed reference h from 2,000 to 4,000 W/m²K, at the same nominal force and uniform contact, predicts **1.31 s and 1.549717°C** for IST308. This is a contact-conductance hypothesis, not a surface finish, pressure or manufacturing process that has been demonstrated.
- The conservative maximum-envelope ceramic-mass plus full maximum-height film-path scenario gives **3.04 s and 2.733717°C** for IST308. The corresponding M222 thin-bond scenario is 3.98 s and 2.529000°C. Unknown package fill, actual film position and material properties therefore still matter. These scenarios retain nominal footprint area and are not statistical limits or fully redrawn maximum-package thermal solutions.
- Three weak rim-contact/high-loss cases do not reach the pan-relative 90% threshold within the 60 s test window. They are reported as NaN; own-final timing cannot substitute for the failed pan threshold.

None of these results establishes a complete ±2°C product error bound. The steady figures exclude RTD calibration/readout, induction pickup, cookware spatial gradients and control-loop behavior. Even the assumed improved-contact case leaves less than 0.46°C for all other error sources if a 2°C maximum target is used.

## Resolution

Refining all three variants from 24 radial rings / 12 cold-wire cells / 10 ms timestep to 48 rings / 24 cold-wire cells / 5 ms changed pan-relative t90 by at most **0.025 s** and steady underread by at most **0.019278°C** in the nominal/rim checks. These are numerical discretization comparisons, not physical validation. The model's geometric and interface assumptions dominate this numerical resolution.
