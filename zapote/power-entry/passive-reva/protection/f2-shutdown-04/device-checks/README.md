# Independent DC anchor check

`dc.cir` runs the actual ngspice equations rather than reimplementing their law.
The selected MOS surrogate produces30A atVGS10V/VDS1.486774V, or49.559mΩ,
close to the STW65N65DM2AG50mΩ maximum anchor. This is a nominal fitted
surrogate, not a worst-case temperature model. The actual SiC equation gives
1.45068V at10A/27°C, near the C3D20065D1.5V typical25°C datum per diode leg.

Setting the MOS intrinsic junction `IS=1e-40` makes its reverse current at
VDS−0.8V/VGS0 negligible (0.8pA including numerical conductance), allowing the
explicit external body diode to own that current path. This prevents the
accidental doubled body diode and makes the series MOS source probe useful
for controlled channel-current timing.

These checks do not validate nonlinear switching charge, avalanche, hot-state
resistance, body-diode recovery, or a full manufacturer transistor model.
The plant's extra gate load and declared capacitance approximation retain those
limitations. Datasheets are retained under the campaign sources and04/sources.

Reproduce: run ngspice in batch on`dc.cir`, compile`check.rs` with rustc, then
pass the log filename to the resulting executable. Missing/duplicate/nonfinite
measurements and failed anchors return an error.

ST Table6 defines456pF Coss(eq) by charging time over0–520V, not
by stored energy. The plant uses it only to construct a constant-capacitance
surrogate; it does not claim exact ST Eoss. The120nC total charge datum is
atVDD520V,ID60A,VGS10V. The source data must not be transferred silently
to other currents, voltages or temperatures.
