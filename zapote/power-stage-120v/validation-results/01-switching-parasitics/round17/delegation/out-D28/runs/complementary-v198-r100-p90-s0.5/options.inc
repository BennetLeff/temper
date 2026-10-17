* Solver settings that converge with the Infineon CFD7 L1 models in ngspice 45
* (verified 2026-09-27). Without them ngspice stops at t=0 with
* "Timestep too small ... trouble with node x..g_g_rd_int1".
.options method=gear reltol=1e-3 abstol=1e-9 vntol=1e-6 itl1=500 itl4=200 gmin=1e-10
