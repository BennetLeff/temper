# Existing loop CSV inspection

Read-only evaluation of existing return-ratio arrays. The real DC limit is estimated from the lowest-frequency real value. The high-frequency arc is approximated by F→1. Open-loop RHP pole count is UNKNOWN, so the winding below is conditional and no closed-loop stability verdict is issued. Refinement and limit/pole verification remain necessary.

## rev_c_r100k_coil50u_stray0_corner0_tia_return.csv

Sampled winding result: Err("Nyquist segments too coarse; refine frequency samples")

| Frequency MHz | Direction | Unwrapped phase | Principal phase | Signed local separation from −1 |
|---:|---|---:|---:|---:|
| 14.665574 | Down | -97.750° | -97.750° | 82.250° |
| 16.434632 | Up | -274.400° | 85.600° | -94.400° |
| 33.587485 | Down | -109.908° | -109.908° | 70.092° |

Largest adjacent F=1+T phase step: 123.303179° between 17.113283042 and 17.444826990 MHz. Refine this band before accepting a winding.

## rev_c_r100k_coil50u_stray100_corner0_tia_return.csv

Sampled winding result: Err("Nyquist segments too coarse; refine frequency samples")

| Frequency MHz | Direction | Unwrapped phase | Principal phase | Signed local separation from −1 |
|---:|---|---:|---:|---:|
| 1.332925 | Down | -103.286° | -103.286° | 76.714° |
| 2.655607 | Up | 79.763° | 79.763° | -100.237° |
| 4.510745 | Down | -96.303° | -96.303° | 83.697° |

Largest adjacent F=1+T phase step: 131.040987° between 3.043219887 and 3.102177665 MHz. Refine this band before accepting a winding.

## rev_c_r5k_coil50u_stray100_corner0_tia_return.csv

Sampled winding result: Ok(Nyquist { ccw_winding: 0, closed_rhp_poles: None, minimum_sampled_return_difference: 0.9420399561165337, maximum_segment_angle_deg: 20.26701886375667 })

| Frequency MHz | Direction | Unwrapped phase | Principal phase | Signed local separation from −1 |
|---:|---|---:|---:|---:|
| 2.062495 | Down | -104.640° | -104.640° | 75.360° |
| 2.344746 | Up | -22.566° | -22.566° | 157.434° |
| 7.252556 | Down | -115.447° | -115.447° | 64.553° |

Largest adjacent F=1+T phase step: 20.267019° between 3.043219887 and 3.102177665 MHz. Refine this band before accepting a winding.

