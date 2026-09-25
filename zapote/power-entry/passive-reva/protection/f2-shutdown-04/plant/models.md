# Device model sources and limitations

Exact parts are STW65N65DM2AG and C3D20065D (both diode legs in parallel).
The ST manufacturer SPICE download did not complete after bounded attempts;
`../sources/st-download.log` records the failure. The ST datasheet is retained
at `zapote/power-entry/loss-budget/sources/STW65N65DM2AG.pdf`, and the current
Wolfspeed datasheet at `../sources/C3D20065D.pdf`. No unrelated exact-part model
is substituted. The unchanged TI driver model is checked under `../vendor/`.

The MOS channel is ngspice level1, VTO4V/KP4.0, with1mΩ drain/source package
resistances. Its actual ngspice DC result is49.559mΩ atVGS10V/ID30A, close to
the selected part's50mΩ maximum25°C anchor. The finite channel replaces the
unlimited abrupt switch that contributed to old numerical current impulses.
This is a nominal fit, not a hot-state worst-case I/V envelope.

The intrinsic body diode is suppressed withIS1e-40. One explicit DBODY with
IS1e-14,N1.2,RS8mΩ,TT8ns models the body path. The8ns is an authored assumption,
not an ST recovery specification. Its current is saved separately. The independent
DC fixture verifies suppressed intrinsic current atVDS−0.8V/VGS0 is negligible.

ST lists456pF **charging-time-equivalent** Coss over0–520V, not an energy-
equivalent Eoss. The surrogate uses344pF Cds plus112pF Cgd, giving456pF with
gate held low; this avoids double-counting Cgd. Constant capacitances do not
reproduce the nonlinear C(V) or switching energy. The112pF derives from the
58nC gate-drain charge over520V. The12nF Cgs plus explicit Miller capacitance
is deliberately heavier than the120nC total-charge datum (520V/60A/10V gate).
It is an overload/sensitivity model, not an exact gate-charge reconstruction.

Each SiC leg usesIS1e-14,N1.4,RS20mΩ,CJO45pF,M0,TT0. Actual DC forward drop is
1.45068V at10A/27°C, near the1.5V typical25°C datum. Each constant45pF gives
3.6µJ at400V, matching the datasheet energy anchor; its18nC charge differs
from the24nC source datum and its45pF differs from40pF at400V. This deliberate
single-anchor approximation is not a full C(V) fit. TT0 removes the old
20ns minority-carrier storage term inappropriate for this SiC Schottky model.

The original impulse problem involved an abrupt unlimited switch, recovered
charge inserted by that diode TT and a nearly ideal1mΩ measurement branch.
The corrected finite channel and explicit charge paths avoid that construction;
raw currents are retained without clipping or coarse-step suppression.

Missing real-system bounds include hot I/V, L(I,T), loop inductance, fuse arc,
nonlinear device capacitance, avalanche, temperature, noise immunity and exact
BSS138 partial-power dynamics. The results establish a reproducible nominal
simulation experiment, not the assembled protection circuit's fault rating.
