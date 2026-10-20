> **Historical numerical diagnosis — preceding FDA network.** Superseded by revision C. Read the final coupled results in `validation/solver-resolution-rev-c-final/` and `docs/analog-validation-rev-c.md`; do not use this historical circuit as the manufacturing target.

# Solver resolution and full-chain transient evidence

This directory preserves the numerical diagnosis, the failed operating-point regression, and strict full-chain DC/AC/transient results. The circuit retains actual FDA common-mode bias and all analog loading. Read `solver-resolution.md`, `dc-regression.md`, `rev-c-regression.md`, `corner-summary.md` and `extended-pulse.md` together.

The copied vendor libraries are unmodified. In particular, `models/ths4551.lib` is TI's **2021-06-10 Rev A Green-Williams-Lis current-sense model**. All FDA output isolation resistors in this evidence are **4.02 Ω**. This evidence must not be transferred to another FDA model or changed resistor/capacitor network without rerunning it. The broader loop-gain and FDA cross-model audit lives outside this directory.

- `gear.cir` / `klu.cir`: exact one-line solver A/B, preserved failure/success logs.
- `target-base.raw`: preserved false operating point; the regression guard must reject it.
- `base-offset-op.raw`, `filter_seed.rs`, `offset-nodeset.inc`: checked true-DC seed and deterministic resistor-node selection. Initial guesses are released during solution; no forced initial conditions.
- `100r_*`, `5k_resistor*`, `100k_resistor*`: six original Revision B cases, retained for comparison.
- `revc_*`: six final Revision C cases with feedback capacitors 100 pF / 10 pF / 5 pF for 100 Ω / 5 kΩ / 100 kΩ.
- `pulse5k_*`: original compensation exploration; `corner_cf*`: all 54 strict supply/fixture disturbance cases.
- `cm*`: three common-mode steps. The 2021 model has about 54% CM overshoot and approximately 1.93 µs 1% settling for this stimulus; differential glitches remain below 0.53 µV. This is not power-up qualification.
- `c100_*`, `c100k_coil_*`: final-capacitor fast-disturbance checks, including explicit 1 TΩ open, 10 mΩ short, and node-to-ground fixture capacitance.

The measured arrays and logs are included, with Rust generators and guards. All model/deck includes are relative. `SHA256SUMS` pins the delivered text evidence and models; generated compiler executables are excluded.

## Replay

Prerequisites: Rust with edition 2021 support and ngspice 45.2 compiled with KLU. The local `.spiceinit` selects PSpice compatibility. The results were produced on macOS arm64; exact numerical text or convergence on another simulator build is not guaranteed.

```sh
./rerun.sh --check   # validate delivered arrays, DC state and negative regression
./rerun.sh --full    # regenerate all positive cases and validate; several minutes
```

Override `NGSPICE=/path/to/ngspice` if it is not on PATH. The full replay checks the initial seed's operating point before regenerating guesses. The failed SPARSE and false-OP examples remain preserved rather than being overwritten. Their deliberate failure is expected; the positive analyses must all pass.

The transient coverage is bounded: nominal macro-models at 27°C, ideal supply sources and lumped fixture capacitance. It does not qualify PCB parasitics, switched ADC kickback, device process/temperature variation, source startup, regulator behavior, calibration accuracy or hardware safety. These files do not establish a manufactured instrument's performance.

`long-tail.md` extends the low-terminal-only 100 pF high-range coil case to 100 µs. It distinguishes slow decay from rapid settling; use the 100 Ω range for the intended Stage 53 coil measurements.
