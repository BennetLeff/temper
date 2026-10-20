# Stage53 load equivalents on the final 100 Ω range

Exact final FDA and local 100 pF compensation; 100 nH RF path and 5 nH local CF path. Ideal isolated DUT equivalents, no fixture ground capacitors for these sine runs. DDS 0.3 V peak. All four strict OP/AC/transient runs pass finite/MID/KCL/endtime/headroom checks. 100 nF and 50 µH + 0.5 Ω use 50 kHz for 240 µs; 500 nF extends to 600 µs. All use maximum 10 ns steps. The 9 µF case uses 1 kHz for 12 ms, maximum 250 ns steps. The final four cycles are fit at actual solver timestamps, except 500 nF uses the final three cycles after its longer settling window. The original 240 µs capacitor record showed about 1% startup residual and is retained under startup-history, excluded from settled qualification. Strict rel 1e−5/abs 1e−12/V 1e−7 tolerances remain unchanged; the smooth 1 kHz drive uses a larger maximum step, with the solver retaining adaptive timesteps.

|DUT|Frequency|A peak(V)|B peak(V)|Uncalibrated fitted Z(Ω)|ADC pin window(V)|TIA outputcurrent(mA)|
|---|---:|---:|---:|---:|---:|---:|
|stage100n|50000|0.50361982|1.58216757|-0.028478 -31.830834j|1.179314–2.890688|-18.025793–17.389537|
|stage500n|50000|0.10547271|1.65677086|-0.005664 -6.366127j|1.164677–2.905649|-18.827975–17.708099|
|stage9u|1000|0.31075449|1.75727838|-0.000556 -17.683851j|1.088290–2.984012|-19.899205–19.362131|
|stagecoil|50000|0.25645689|1.63180984|0.514098 +15.707613j|1.197620–2.850176|-18.614598–16.528990|

The complex values use nominal 100 Ω ∥ 100 pF correction without fixture calibration; they demonstrate coherent sign/scale and signal headroom, not a promised component accuracy. The models include finite-amplifier phase/loading, while DUTs are ideal equivalents. Real stage53 coil resistance, capacitor ESR/tolerance and fixture parasitics require measurement and independent standards. These runs do not model switched ADC sampling, supply-ripple, thermal/noise distributions, turn-on DC transients, or powered/in-circuit stage53 operation.
