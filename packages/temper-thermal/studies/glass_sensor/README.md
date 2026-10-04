# In-glass PT100 contact and thermal study — 2026-10-04

**Status: simulation screening; ready to specify an instrumented engineering prototype, not a qualified sensor or a released control change.** Read [the illustrated report](report.html) first. All physical results remain unmeasured. The model tests passed; that establishes numerical behavior, not parameter truth.

This study implements the requested pan/probe mechanics and transient thermal simulations, plus a local pan/glass finite-volume sensitivity model and closed-loop tests of the unchanged production PID modules. Physics is implemented in Rust. Python only reads CSVs, checks output contracts, and plots. No pyo3 extension or shared Cargo artifact is involved.

## Reproduce

From this directory:

```sh
PYTHON_BIN=/path/to/python-with-numpy-and-matplotlib bash run.sh
```

Requires `rustc`, `rustfmt`, a C99 compiler, `ar`, Python, NumPy and Matplotlib. The run script builds into a temporary directory, verifies the captured CAD and firmware input hashes, runs tests and all sweeps, creates charts, and compresses large CSVs. It does not download dependencies, modify CAD, change controller tuning, or rebuild extensions. Tested with rustc 1.92.0, Python 3.12.12, NumPy 2.4.6, Matplotlib 3.10.8; see generated provenance for actual versions. Run the source against its recorded firmware hashes; review and regenerate the manifest deliberately if the firmware changes.

The source tree was isolated at `c601fab9f18532f548cada22d63b1c884199e27d`. The CAD and proposed acceptance screens came from untracked output artifacts in the user's primary checkout, whose HEAD was `84c5e5b61000d45eec09834cb23e6bba8fa51169`. They are preserved as **input snapshots**, with full SHA-256 hashes; neither Git SHA is claimed to identify those untracked CAD bytes. `inputs/mechanism.py.txt` is a read-only CAD source snapshot, not a second implementation to maintain. `input-provenance.json` maps every source file to its hash and origin.

## Input authority

| Quantity | Value | Evidence/status |
|---|---:|---|
| Cap rest height above glass | 0.6 mm | CAD source and cap bbox |
| Contact diameter / roof / skirt | 10 / 0.35 / 0.4 mm | CAD, skirt height 1.65 mm |
| Cap volume | 47.3941 mm³ | Calculated from that geometry; prior CAD study agrees |
| Bond footprint / thickness | 3.8 × 2.8 / 0.2 mm | CAD; material unspecified |
| RTD envelope | 3 × 2 × 0.4 mm | CAD; no selected supplier part |
| Effective bond contact area | 6 mm² | Smallest RTD face, not the larger glue footprint |
| Stem / guide bore | 6 / 6.4 mm | CAD |
| Diametral running clearance | 0.32–0.48 mm | CAD's proposed size tolerances, not process data |
| Guide length | 10.8 mm | CAD at nominal 1.2 mm stop travel |
| Stroke | 1.20 nominal, 1.05–1.35 mm | CAD's assumed tolerance stack |
| Glass / hole / neck | 4 / 18 / 17 mm | CAD; aperture manufacture unqualified |
| Spring and seals | Geometric envelopes | No purchased part, preload, force curve, fatigue or leakage result |
| S01 / S02 | ±2°C at 40–100°C / ±5°C above 100–250°C | Proposed installed-assembly screens, including expanded uncertainty |
| S03 / S04 / S05 | t90 ≤3 s / force trials 0.2, 0.4, 0.6 N / stop heat ≤1 s after confirmed loss | Proposed screens; no physical pass |

## Mechanics

Rigid pan, circular support radius `R=90 mm`, probe centered in that circle; the center-of-mass offset `e` includes handle/contents. Pan gap `g` is the height of the local bottom above the glass when normally supported. A negative gap represents a local dimple fitting inside the glass aperture, not a pan intersecting solid glass. Flatness at the tip is reduced to this gap; this is not shell FEA of arbitrary cookware.

Requested compression is `x_req=h-g`. The maximum probe reaction compatible with the glass support polygon is `F_limit=m*g0*(1-|e|/R)`, obtained by requiring the glass reaction resultant to remain within radius R. The net free-tip preload includes moving-part gravity; total downstroke resistance is `F0+(k_spring+k_seal)*x+F_drag`. Return is guaranteed only when `F0>F_drag` in this simplified Coulomb model. Wire drag belongs in F_drag, not an omitted allowance.

Compression is the minimum of the geometric request, lower-stop stroke, and compression permitted by F_limit. At a lower-stop-limited tilted equilibrium the rigid stop carries the remainder of the pan reaction; the reaction is not limited to the spring force. Tip lift `d=max(0,h-g-x)` gives a possible tilt `atan(d/R)` and an opposite-edge extra coil gap `2d`. These are a rigid-body rocking envelope; a perfectly centered pan might balance temporarily on the cap. The model does not assert a unique equilibrium orientation, pan rigidity, coil coupling, impact response, or frictional side-load behavior.

The exhaustive 97,200-case grid is deterministic, **not a probability distribution**:

* h: 0.3, 0.45, 0.6, 0.75, 0.9 mm; local gap: −0.2, 0, 0.3, 0.6, 0.9, 1.2 mm.
* stroke: 1.05, 1.2, 1.35 mm; net preload: 0.1, 0.25, 0.5 N.
* spring stiffness: 0.2, 1, 3, 8 N/mm; seal stiffness: 0, 0.5 N/mm; drag: 0, 0.1, 0.4 N.
* mass: 0.15, 0.3, 0.6, 1, 3 kg; COM eccentricity: 0, 30, 60 mm.

Case classifications are separate: reachable, return guaranteed, stroke insufficient, and lift. A non-returning case is history-dependent even if the initial downstroke solution has contact. Grid pass fractions must not be reported as cookware reliability.

## Thermal network

Three finite-capacity nodes represent metal cap, dielectric bond, and RTD. Boundaries are the undisturbed local pan, local glass, and body/lead anchor. Each node follows `C*dT/dt = sum G*(T_neighbor-T)+Q`. Cap/bond and bond/RTD resistances include half the bond on each side, the cap roof's through-thickness resistance over 6 mm², and half the ceramic element thickness. Bond capacitance includes its full CAD footprint. The actual RTD film location and adhesive fillets are unknown.

Cap capacitance uses the CAD volume and **assumed stainless-like** density 8000 kg/m³, heat capacity 500 J/kgK, conductivity 16 W/mK. Bond uses assumed density 1800 and cp 1000; chip uses ceramic-like density 3900, cp 800, conductivity 25. These are sensitivity proxies, not material selections. Increasing chip scale to 1.8 scales its heat capacity and half-thickness resistance while keeping contact area fixed; it is not a geometrically faithful M222 model.

`G_contact = h*A`; `h=h_ref*(F/A/5000 Pa)^0.7`. **This power law is an assumed sensitivity mapping, not a measured or supplier-validated pressure correlation.** h_ref values 250/1000/4000 W/m²K at 5 kPa deliberately span 16×. Area fractions 0.3 and 0.1 model degraded contact approximately; a lumped cap cannot resolve eccentric patch contact or local lateral temperature gradients. Added pan spreading resistance `1/(4*k_pan*a)` is a half-space approximation; the thin-pan/finite-radius error is unquantified. The radial model independently resolves radial pan conduction instead of adding this resistance.

Contact loss removes the solid-contact conductance and adds a weak gas/radiation-equivalent path. Steady examples exclude RTD self-heating; time traces include 1 mA and `P=I²R(T)`. Radiation, seal, plunger and glass leakage are combined into linear conductance ranges, not solved from unselected parts. Cap parasitic heating is injected as 0–1 W sensitivity; no magnetic-field solution predicts the real deposited power.

2,916 thermal cases sweep forces 0.2/0.4/0.6 N, h_ref 250/1000/4000, bond 0.05/0.2/0.4 mm, bond k 0.2/0.9/2 W/mK, cap roof 0.15/0.35 mm, cap leakage 0.0005/0.002/0.01 W/K, pan k 16/45/160 W/mK, and chip scale 1/1.8. Lead conductance defaults to 0.0003 W/K; separate sweeps cover 0.0001–0.002. Cap leakage splits 60% toward glass and 40% toward body. Thin-cap conductivity sensitivity changes k only, retaining stainless heat capacity; it does not represent a copper or aluminum material substitution.

The 432 additional candidate corners use roof 0.1/0.15/0.2 mm, bond 0.075/0.1/0.15 mm, h_ref 2500/4000, force 0.2/0.4 N, all three pan conductivities, two chip scales, and area fraction 0.3/1. Leakage is 0.0005 and lead conductance 0.0003 W/K. These assumptions are the condition on every candidate result.

The additional1,152 **coupled** cases use height0.45/0.6/0.75 mm, gap0/0.35/0.6 mm, net preload0.12/0.15 N, total stiffness0.2/0.3 N/mm, drag0/0.05 N, mass0.15/0.6 kg and COM offset0/60 mm, then run both CAD/middle and conditional-candidate thermal networks at area fraction0.3/1. Cases without supported, returning contact do not receive fictitious thermal scores. The thermal force is the lower static-friction bound `F_min=F0+k*x-F_drag`, not the higher force measured on the initial downstroke. Within the proposed recess≤0.35 mm subset, F_min reaches0.09 N; the candidate's worst response is3.40 s at full area and4.90 s at30% area. The proposed mechanical envelope therefore does **not** guarantee the proposed thermal screen. In particular, selecting a spring from the nominal0.4 N thermal example would miss this covariance. The coupled results hold chip size and pan conductivity at their middle assumptions; they are not an exhaustive joint uncertainty bound.

`t90_of_final` means 90% of the actual sensor's asymptotic rise, which can be substantially biased. `t90_of_pan_step` means 90% of the imposed pan rise; NaN means not reached within 120 s. Both are supplied to prevent a fast but thermally shorted sensor from appearing accurate. Step source is 25→100°C with glass/body at25°C. Error200 uses pan200/glass80/body60. Steady error is relative to the undisturbed local pan; a separate column subtracts the predicted local pan contact cooling. Ramp delay is the exact first moment of the linear network, after normalizing DC gain. This is not a calibration correction that remains valid across pans.

Heating ramps are 0.5/2/5°C/s. Cutoff tests continue heating until the sensor reads200°C, or pan reaches350°C. They are cutoff-only surrogates, with no stored-energy overshoot or controller dynamics. Cooling traces expose positive sensor-minus-pan error after cooling begins. A passive RC network with fixed boundaries does not intrinsically overshoot its step equilibrium.

## Pan/glass finite-volume study

Axisymmetric radius90 mm, homogeneous pan thickness3 mm, glass thickness4 mm, optionally an exact radius9 mm hole. Pan proxies `(k, rho*cp)` are steel `(16,4e6)`, cast iron `(45,3.6e6)`, and aluminum-core-like `(160,2.43e6)` in SI. The last is an effective conduction proxy; bare aluminum is not asserted to couple to the induction coil. Pan/glass h is50/200/1000 W/m²K. Glass k1.6 and density2600 are typical CERAN values; cp800 is assumed. Vertical coupling includes both half-thickness resistances. Linear environmental loss is15 W/m²K per exposed surface at25°C. Body boundary is60°C. The outer radial boundary is adiabatic.

Imposed input is exactly500 W uniformly over the radius30–75 mm annulus for120 s, with no food load. Annular edge cells receive exact overlap-area power, so mesh changes do not change applied watts. This is **an illustrative field shape, not Temper's solved coil field**. With the hole, the probe couples over radius5 mm, to the glass rim and body; without the hole, glass extends to the center and there is no probe. Thus this comparison combines aperture removal and probe insertion. It does not isolate machining damage or hole-only stress.

The model uses one temperature through each layer thickness. It resolves lateral heat flow but cannot establish top/bottom surface gradients, aperture edge stresses, cracks, seal temperatures, or certification. 20/40/80 radial cells and dt0.2/0.1/0.05 s check numerical refinement. The finite-volume findings are sensitivity evidence, not predictions for a selected pan.

## Controller-module SIL

`controller_bridge.c` compiles unchanged `pid_control.c` and `cascade_pid.c` from the recorded repository revision. Controller0 uses the PID source's default gains1/0.05/0.2; controller1 calls `cascade_pid_init_default`, then runs single-loop mode with no liquid probe. Calls occur every10 ms. The 60 cases cover pan mass0.3/1/2 kg, cp500, maximum absorbed power1500 W, loss2 W/K to25°C, and ideal/middle/poor/candidate sensor networks. The pan and probe form an energy-coupled four-node network.

Normal contact, contact lost at60 s, and an **ideal external contact signal** cutting command at61 s are compared. Loss changes contact to0.001 W/K. Tests stop at240 s or a deliberate model ceiling400°C. The latter is censorship, not a predicted physical maximum. No actual contact detector has been implemented. The main state machine, hardware cutoffs, ADC timing/filtering, power-stage delays, burst mode, food, and radial gradients are excluded. Consequently this is a module stress test, **not a demonstration that the complete appliance would reach those temperatures**. Ideal-sensor rows still retain the probe's tiny thermal loading, but controller measurement is the pan itself.

The default controllers also undershoot the setpoint in the ideal-sensor plant. Their integral-state clamp and chosen plant/load must be considered before drawing conclusions from positive overshoot alone. A zero overshoot cell is not a tracking-accuracy pass.

## Verification and limits

14 Rust tests cover reach, soft contact, eccentric tipping, hard-stop reaction, return failure, the proposed flat-pan force envelope, thermally invisible hot contact loss, an analytical one-pole RC transient, a separately reduced resistor network, closed-system energy conservation, monotone passive response, time-step refinement, exact annular input power and a uniform-temperature radial solution. Existing production cascade tests:25 passed. Existing probe-detection tests:4 passed (these test the **liquid probe**, not the in-glass contact condition). Output checks assert all module commands stay0–100% and the hypothetical contact gate commands zero from61 s.

Across the reported radial center/pan-peak/glass-peak quantities, 40→80 cells changed results by at most0.153°C; nominal dt0.1→0.05 s by at most0.010°C. Discrete energy residual is below1e-7 J. These are solver checks, not overall uncertainty bounds. Unknown contact conductance, cookware geometry, loss paths and field shape dominate those numerical differences. A physical calibration/validation run has not occurred. Mesh refinement cannot validate an assumed boundary condition.

## Primary external references

* [SCHOTT CERAN technical details](https://www.schott.com/en-us/products/ceran-p1000315/technical-details): typical conductivity1.6 W/mK at100°C and density2.6 g/cm³. Supplier values are not a Temper aperture-strength approval.
* [YAGEO Nexensos M222 datasheet](https://yageogroup.com/content/datasheet/asset/file/YAGEO_Nexensos_M222_Datasheet_EN): nominal2.3×2.1×0.9 mm, Class A order32208550, current0.3–1mA for Pt100. The CAD envelope is0.4 mm thick; M222 requires mechanical and thermal rework. Its quoted response in moving water/air does not predict bonded-cap response. Four-wire sensing requires appropriate Kelvin connections at the element leads.
* [EPO-TEK H70E datasheet](https://www.epotek.com/docs/en/Datasheet/H70E.pdf): typical k0.9 W/mK, filler≤50µm, Tg≥80°C, suggested<300°C **intermittent** operation. A50µm bond is a sensitivity lower bound, not a process recommendation. Neither this listing nor Tg establishes continuous250°C bond integrity, dielectric safety, cleaning resistance, or fatigue life.
* [EPO-TEK353ND datasheet](https://www.epotek.com/docs/en/Datasheet/353ND.pdf): thermal conductivity is listed N/A; it was not assigned a sourced conductivity in this model.

External data checked2026-10-04. Exact supplier selections remain open; no material or spring was ordered or approved.
