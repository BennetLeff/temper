# Return-ratio oracle and interpretation

The independent matrix-inversion method and the simple bilateral SPICE fixture verify the formula in `loop_matrix.rs`. Across 1, 10, 100 and 1000 Ω bridges and 1441 frequencies, the worst relative disagreement with the analytic circuit is **1.57×10⁻¹⁰**. The fixture has loading on both ports and reverse transmission; it is not an ideal unilateral op-amp test. Nine Rust regression tests pass.

## Algebra and sign convention

Let both test currents enter the two cut ports. Their measured voltage responses form columns of Zb. If the test bridge has conductance g=1/Rb, its admittance is g·[[1,−1],[−1,1]]. Therefore the unbridged network is

```
Y = inverse(Zb) − g·[[1,−1],[−1,1]]
T = (Y12 + Y21)/(Y11 + Y22)
F = 1 + T
```

Reconnecting the original wire sets both port voltages equal and the sum of entering port currents to zero. Its characteristic factor is the sum of all four Y entries. Normalizing by the diagonal sum gives F above. With D=Z11·Z22−Z12·Z21, substitution gives exactly

```
T = (2gD − Z12 − Z21)/(Z11 + Z22 − 2gD)
```

`deembedded_return()` computes the actual inverse and subtraction. `determinant_return()` separately implements the shortcut. The analytic fixture and ngspice supply external answers rather than comparing two copies of the same expression.

This is consistent with the bilateral return-loop model in Tian, Visvanathan, Hantgan and Kundert, [“Loop-Based and Device-Based Algorithms for Stability Analysis of Linear Analog Circuits in the Frequency Domain,” equation 20](https://kenkundert.com/docs/cd2001-01.pdf). That work requires a suitable critical wire for the loop-based interpretation; a local result is not automatically a certificate for every loop in an active multiloop circuit.

For a nonlinear model, de-embedding is an AC operation around the simulated DC point. A finite bridge must not appreciably change that operating point. Bridge invariance on this linear fixture does not establish bias or numerical invariance for every TI macro-model circuit.

## Crossing interpretation

Report every crossing with its direction, continuously unwrapped phase, principal phase in [−180°,180°), and signed local angular separation from −1. That separation is `wrap180(phase+180°)` and is invariant to adding 360° to a phase branch. Its sign alone is not a general stability decision.

Do not label all crossings “phase margin” and take the most negative value. In particular, an upward crossing can have negative signed separation in a stable loop. Even a downward crossing can acquire an arbitrary −360° offset in a nonminimum-phase loop. The stable three-crossing oracle demonstrates both failures. Conventional single-crossing phase-margin interpretation requires the relevant assumptions, including the reference-loop pole count and adequate frequency coverage.

`nyquist()` constructs the conjugate full-frequency contour of F=1+T. For its explicitly defined traversal from negative to positive frequency, counterclockwise winding W satisfies **W=P−Z**, so **Z=P−W**. P is the independently established count of open/reference-loop right-half-plane poles. When P is unknown the API returns no Z or stability verdict. It also rejects missing DC limits, insufficient high-frequency decay, a contour touching the origin, and adjacent phase steps over 90°.

The last guard detects obvious under-resolution, not every possible missed excursion. Sampled curves cannot exclude narrow loops between samples. Refine adaptively around poles, zeros, near-origin passages and rapid phase changes; verify low/high limits and convergence of the winding under further refinement. Imaginary-axis poles need indented-contour treatment not implemented here. Hidden unstable modes or pole-zero cancellations need a fuller determinant/pole analysis.

## Application to the existing coil data

`case-inspection.md` reads the existing CSV files without modifying them. It explicitly estimates the DC endpoint and leaves P unknown.

- The 100 kΩ coil / no added stray case has a **123.30°** adjacent F phase step between **17.113283 and 17.444827 MHz**.
- The 100 kΩ coil / 100 pF stray case has a **131.04°** step between **3.043220 and 3.102178 MHz**.
- The oracle refuses to assign a winding to those under-resolved arrays. Their printed upward-crossing “negative PM” does not independently establish instability.
- The sampled 5 kΩ coil / 100 pF case has W=0 with a 20.27° maximum step. Its reference pole count remains unknown, so this is conditional contour information, not a standalone stability proof.

The bounded and decaying transient results are useful corroboration. They do not replace sufficient frequency resolution, the reference pole count, or excitation of every possible mode.

## Replay and reuse

From this directory, run `./run.sh`. It compiles tests and fixtures with Rust edition 2021, executes ngspice, and writes only these standalone oracle outputs. `NGSPICE` may override the executable path. Pass existing return CSV paths relative to the parent directory to add a read-only inspection, for example:

```
./run.sh rev_c_r100k_coil50u_stray0_corner0_tia_return.csv
```

The pure public functions in `../return_ratio_oracle.rs` can be reused independently: `deembedded_return`, `determinant_return`, `crossings`, and `nyquist`. `report.md` records the analytic and SPICE checks; `.cir`, `.log`, `.dat` and analytic `.csv` files preserve their inputs and results.
