# Revision 19 — gate-network correction and reset scope

The supplied review identified a real reference-connection error. The new
[clamp schematic](clamp.kicad_sch) / [PDF](clamp.pdf) moves **R7 pin1 and D1
anode pin2 from Q_GATE to GATE_DRV**, on the controller side of R6. D1 cathode
pin1 remains on CG with C3. No diode reversal, capacitor enlargement or new
part is involved. The clamp still has14 components /39 pins. Revision18 and
the full revision11 /136-component candidate remain unchanged.

The service-reset note now states that **120ms is for TIMER RESET ONLY** and
requires SHDN≤0.4V with release slew≥10V/ms. It explicitly separates gate
turn-off and output discharge. It remains independent of source PERMIT.

## Reference and verification

The parent visually inspected manufacturer Figure5 in the retained older
[RevB PDF](sources/lt4363-revb-mirror.pdf), obtained from the
[RET mirror](https://www.ret.hu/media/product/32613/623865/4363fb.pdf).
In [the rendered page](sources/lt4363-revb-figure5-page.png), vertical R3 lies
between the upper MOSFET gate and the lower controller GATE node. The R1/D1/C1
branch joins the lower node. Our R6 corresponds to R3, R7 to R1, C3 to C1.
The [current ADI URL](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf)
serves RevC despite its filename. Its text was accessible, but a current PDF
image was not retrieved. The retained visual evidence is explicitly RevB;
its electrical tables must not be substituted for RevC's current limits.

The first Luna researcher obtained the image but misread its branch node.
The parent rejected that conclusion and a second Luna reviewer independently
confirmed the lower, controller-side junction. Raw handbacks are preserved;
[review-resolution.md](review-resolution.md) states which claims supersede them.
This corrects the claim in revision15 that our former connection followed
Figure5. It does not demonstrate that the former circuit necessarily failed
an actual surge or that the revised circuit passes one.

Before changing the schematic, the revised expected graph and Rust auditor
were run against the frozen revision18 netlist. They failed on the old D1
connection (`red-old-wiring.log`). After editing and native export:

- All39 clamp pins and106 unchanged reset-reference pins pass.
- Mutation checks reject the old branch, wrong diode endpoint and fixed-high
  HOT permission input; parser and manufacturer pin-function checks pass.
- The same seven clamp ERC findings remain; none has been waived.
- The generated review BOM is identical to revision18. All part identities
  and footprints are retained. The exported drawing was visually inspected.

## Bounded passive-network experiment

No usable LT4363-1/FDB33N25 model pair or LTspice runtime was located by the
bounded investigation. The official product page lists LTspice models and a
-2 example, but no runnable controller model was obtained. **No controller,
MOSFET, load, startup or surge-clamping simulation was performed.**

`probes/` compares only the passive R6/R7/C3 connection under imposed sources,
using ngspice45.2. There is no MOSFET gate capacitance or Miller effect, no
output rail or feedback, and no current-limited controller in the fast probe.
D1 is represented as open during monotonic discharge; reverse recovery,
leakage and parasitics are excluded. The experiment does not bind a hardware
response time or voltage peak. It explains the network difference.

| Imposed stimulus | Old branch | Reference branch | What this establishes |
|---|---|---|---|
| Drive node falls25→0V in10ns, sampled0.99us after fall ends; C3=1.30/1.70uF | Unloaded Q_GATE≈2.257/2.261V | Unloaded Q_GATE=0V | Old capacitor discharge crosses R6 and creates a gate/pin difference under this ideal forcing |
| Constant50uA sink, C3 initially10V to ground, sampled at120ms | Q_GATE≈5.380/6.466V | Same≈5.380/6.466V | Moving the branch does not eliminate charge-removal time under the assumed weak sink |

In the weak probe the maximum-C3 capacitor itself remains at6.470588V. The
old controller node is0.5mV below Q_GATE from50uA×10Ω; the reference branch
removes that drop. These are ground-referenced voltages, **not VGS** and not
safe-off thresholds. Under the fast ideal forcing, the reference source can
sink about250mA initially; no claim that LT4363 provides that current follows.

Both probes use both C3 allocation endpoints and were rerun at half the
maximum step: four simulator invocations, sixteen topology/capacitance/stimulus
instances across coarse/refined runs. The Rust checker matches22 measurements
to independent closed-form values and11 refinement comparisons within50uV.
Four failure-path tests pass. A corrupted real log is also rejected.

The timer screen gives105.26775ms from1s/uF×105.26775nF. That supports the
120ms timer-reset condition only. The separate C×ΔV/I example gives340ms for
1.70uF,10V and an assumed constant50uA; the published shutdown-current datum
at GATE=10V does not establish constant current throughout that discharge.
Neither340ms nor120ms becomes a hardware turn-off deadline.

## Next acceptance step

The [transient and bench matrix](transient-matrix.md) separates cold startup,
normal-operation SHDN, UV/brownout, timed fault reset and source overvoltage.
It requires actual driver-pin voltage and Q1 VDS/current/energy trajectories,
not just capacitor arithmetic. The <18V driver-supply objective remains.

A full comparison is blocked on a usable vendor model/runtime or physical
captures, together with source/load bounds. Model provenance does not supply
worst-case guarantees or hot SOA. Output discharge and permitted residual
charge must be specified independently; turning Q1 off does not discharge C4.
There is no new promise that every reset starts from zero charge.

Ride-through has not been established as a product requirement. The active
clamp stays the review baseline. A disconnect alternative remains possible,
but the earlier candidate lacked a guaranteed delivered-charge/turn-off bound;
changing architecture does not remove that acceptance requirement.

No PCB change, full-circuit adoption, order, commit or push was made. The
bounded correction and network experiment are complete; system startup,
surge protection, hot SOA and hardware qualification remain open.

## Reproduction

From this directory, compile `auditor.rs` with `rustc --edition=2021`, then run
its binary with `.` and with `. --self-test`. It uses the unchanged reset
netlist/expectation copied from revision16 solely as a reference fixture.
For each `probes/*.cir`, run `ngspice -n -b <deck>` from `probes/`, capturing
stdout/stderr to its matching `.log`, with a30-second process timeout. Compile
`probes/check.rs` normally and with `--test`; run the normal binary with
`probes` as its argument. Raw logs, trace files, and bounded run receipts are
retained. `artifact-hashes.json` binds the final retained bytes.
