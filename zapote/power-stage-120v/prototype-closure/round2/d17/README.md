# D17 round 2: native geometry and finite-energy shutdown

**Digital progress, not D17 closure.** This packet replaces guessed geometry
with fresh native19 copper/port inputs and adds a finite-energy
full-bridge topology model to the previous imposed-current commutation experiment.
No coil/pan measurements or physical qualification exist. No current limit,
fabrication release, energization permission or fault-survival pass is implied.

## Board extraction

The [adapter](extract.py) imports the SHA-pinned upstream KiCad exporter after
validating its hash and the native19 board identity. It delegates all pad
positions and flashed copper to pcbnew 10.0.4. The result has 2,102 copper
primitives, 308 physical barrels and 180 suppressed pad-layer instances.
The adapter updates every closure endpoint from real pads, including R5:
`(127.135,10.120)` → `(125.865,15.080)` mm. The old endpoints were at
Y9.615 and15.585 mm. The gate-resistor endpoints also retain actual0.5 µm
coordinates rather than rounding them prematurely.

[mesh.py](mesh.py) delegates to the qualified upstream mesher, includes both
Kelvin nets as passive copper, and uses 20 mm crop margin, 1 mm closure
height and 1 mm edge setting. Fresh meshes contain 3,542,432 tetrahedra
for A and 4,207,066 for B. For both: zero zero-volume tetrahedra; four
closed ports; zero port divergence/leakage; no spurious inner far-field
columns. These are mesh/topology checks, **not solved inductance matrices**.
The upstream mesher still defeatures narrow copper and omits unrelated nets;
adding the Kelvin copper does not create a Kelvin-reference impedance port.

Full field solves, convergence and zero-height extrapolation are not run.
The prior fine campaign used roughly47 GB and multi-hour solves per port;
this host has32 GiB. A local Elmer installation was located, but availability
alone is not solver qualification. The generated coarse meshes are local
outputs, not source-controlled deliverables. A four-port solution also does
not resolve bulk-current, cross-leg, Kelvin-current or installed common-mode
coupling by itself. Keep every unperformed field result `NOT_SOLVED`.

## Finite-energy full-bridge shutdown circuit

The [ngspice template](shutdown-template.cir) contains a5.8 µF floating DC
bus, four controlled switch conductances, four passive diode paths, four1 nF
snubbers, a series L/R/0.54 µF tank and the1.88 MΩ resonant-capacitor bleed.
The active diagonal turns off after a specified delay; stored energy then
flows through the available diode paths. There is no stiff voltage source
holding the bus down and no imposed current maintaining the fault.

The 180-case set uses170/280 V bus; initial current−85.551,−60.014,+38.438,
+60.014,+85.551 A; initial capacitor voltage−640/0/+640 V;0.25/5 µs shutdown
delay; and three **unmeasured diagnostic** L/R pairs:70 µH/2 Ω,35 µH/0.2 Ω,
140 µH/10 Ω. These independent combinations are deliberately not labelled a
reachable operating envelope. The0.25 µs corner is an illustrative fast
all-off command, not a bound on the existing complete protection path.

Across those conditions, the separate maxima are428.342 V bus,136.149 A
current and1320.767 V resonant-capacitor voltage. The maximum energy-balance
residual is0.003494%; every case satisfies the passive total-energy bus bound.
Two20→10→5 ns timestep refinements of the stressed170 V/+85.551 A/−640 V,
35 µH/0.2 Ω,5 µs case agree on bus/current/capacitor peaks within0.001%.
However its small residual ring current at200 µs varies with timestep;
**current extinction is not established**. Up to357.78 V remains across the
resonant capacitor at200 µs in another diagnostic case.

The switching elements are intentionally idealized:18 mΩ commanded switches
with1 ns conductance ramp and piecewise-linear20 mΩ diodes. These are not
Infineon models. No Qrr, nonlinear Coss, avalanche, junction temperature,
parasitic coupling, line recharge, TVS absorption, fuse or semiconductor SOA
is qualified. The waveform peaks cannot be joined to the previous device
commutation result as if they were one simultaneous simulation. Initial tank
states must come from a matched nonlinear operating/fault model or measurement.

## Loaded PERMIT and shunt filter

The [receiver circuit](permit-template.cir) has both100 Ω gate branches,
both100 kΩ pulldowns, both1 kΩ DIS pullups and shared cable/output loading.
Its96 diagnostic cases sweep gate capacitance300/630/1200 pF, drain/input
capacitance20/200 pF, cable50/500 pF, latch-output resistance10/50 Ω,
rail3.0/3.6 V and a simplified channel knee0.65/1.45 V. Command-edge to DIS
2.3 V is55.46–716.99 ns. All those parasitic values and the channel law are
assumptions; this is **not a guaranteed receiver timing interval**. In
particular the gate threshold test is not the receiver's drain-current test.
Floating/unpowered PERMIT and arbitrary rail collapse are not simulated.

The shunt-ramp calculation uses the actual nominal divider/filter topology:
500 ns time constant,0.5 mV/A gain. The20 mV comparator timing-test overdrive
corresponds to an additional40 A in the input. The generated table separates
filter threshold crossing, time to that overdrive and actual ramp current;
it does not assign a guaranteed comparator delay to slow ramps.
The Kelvin table evaluates `Verror=Ireturn*Rshared+Lshared*dIreturn/dt`, with
trip displacement `−Verror/1mΩ`. Its impedances and waveforms are sensitivity
inputs, not native19 extracted values.

## Reproduce

From the integration checkout, with `oracle` pointing at the pinned ps-oracle
checkout and `fem_python` at the existing environment containing gmsh/shapely:

```sh
src=zapote/power-stage-120v/prototype-closure/round2/d17
out=output/temper-prototype-closure/round2/d17
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 "$src/extract.py" --oracle "$oracle" --out "$out/extraction"
"$fem_python" "$src/mesh.py" --oracle "$oracle" --extraction "$out/extraction" --leg A --out "$out/mesh-A.msh"
"$fem_python" "$src/mesh.py" --oracle "$oracle" --extraction "$out/extraction" --leg B --out "$out/mesh-B.msh"
rustc --edition=2021 --test "$src/run.rs" -o /private/tmp/temper-d17-tests
/private/tmp/temper-d17-tests
rustc --edition=2021 -O "$src/run.rs" -o /private/tmp/temper-d17-round2
/private/tmp/temper-d17-round2 "$src" "$out/simulations"
```

The runner requires ngspice45.2, writes `INCOMPLETE` before work, refuses
unexpanded parameters, aborts on failed/missing/nonfinite measurements,
and rejects energy residuals above0.5% or violation of the passive-energy
bound. A successful record says `SIMULATED_CONDITIONAL`; it is not a hardware
pass. Review [ECO.md](ECO.md) for exact integration actions and primary sources.


## Retained evidence

The `evidence/` directory retains all182 shutdown and96 PERMIT decks/logs
in `simulations.tar.gz`, compact CSV results, the flashed-copper export,
actual pad/closure inputs and all six external mesh-gate logs. `results.json`
records the large local mesh hashes, numerical checks and unclosed gates.
Verify source/evidence bytes with `shasum -a 256 -c evidence.sha256` from
this directory before reproducing. Negative input controls reject a changed
upstream exporter, a changed extraction file a wrong-board receipt, a printed failure despite diagnostic exit0, and a missing result.


Gmsh meshing is not byte-deterministic: the first geometry-equivalent run had
3,542,399/4,203,235 tetrahedra. The final retained logs and mesh hashes identify
the later3,542,432/4,207,066 run; all six topology checks were rerun on those
exact outputs. The diagnostic tools themselves do not fail their exit codes
on bad topology, so [check-gates.sh](check-gates.sh) asserts numerical results
and refuses missing results. Run it on the output directory after executing
upstream `pec_columns.py`, `port_divergence.py` and `port_loops.py` for each leg.
