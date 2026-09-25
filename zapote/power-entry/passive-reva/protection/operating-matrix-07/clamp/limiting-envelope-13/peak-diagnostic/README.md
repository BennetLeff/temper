# Peak-current diagnostic

Date: 2026-09-21 (UTC)  
Purpose: determine whether the peak-current columns in the parent
`limiting-envelope-13/results.csv` are numerically converged. This is a
diagnostic only; it does not alter the parent fixtures or cap their values.

## Why the original peaks are not accepted

The parent fixture uses a 1 mOhm hard-clamp slope (`I = excess/RCL`) and a
1 nF ISENSE capacitor. With the original trapezoidal settings
(`reltol=1e-6`, `abstol=1e-12`, `vntol=1e-9`, 1 ns maximum step), a small
solver voltage excursion at the piecewise knee becomes a large current
excursion through 1 mOhm. The parent `results.csv` therefore retains its
measured peaks but they are **UNVALIDATED peak diagnostics** until a converged
solver/model is chosen. Flat DC values and pulse energy are checked separately.

The monotonic passive envelope for these finite-pulse controls is

```text
I_bound = max(0, (|VSHUNT| - VF) / (220.001 ohm))
```

because the passive first-order node equation approaches its instantaneous
equilibrium monotonically during the negative ramp and plateau. Starting at
zero, it cannot fall below the final clamp equilibrium
`-VF - I_bound * RCL`; on pulse release it rises back toward zero. This is an analytic comparison bound, not a new
acceptance limit for a real diode.

## Bounded comparison

Two source cases were replayed with the same 220 ohm / 1 nF topology and
piecewise clamp (`VF=0.350 V`, `RCL=1 mOhm`): `VSHUNT=-0.438 V` and `-5 V`.
Each case used five solver variants:

| variant | method | maximum step | tolerances |
| --- | --- | ---: | --- |
| `trap_1n_orig` | trapezoidal | 1 ns | parent settings |
| `trap_1n_tight` | trapezoidal | 1 ns | reltol 1e-9, abstol 1e-15, vntol 1e-12 |
| `trap_100p_tight` | trapezoidal | 100 ps | same tight settings |
| `gear2_1n_tight` | Gear order 2 | 1 ns | same tight settings |
| `gear2_100p_tight` | Gear order 2 | 100 ps | same tight settings |

| source | variant | analytic bound | clamp peak | peak / bound | clamp energy (0–8 us) |
| ---: | --- | ---: | ---: | ---: | ---: |
| -0.438 V | trap 1 ns, original | 0.4000 mA | **0.7572 mA** | **1.893** | 0.511410 nJ |
| -0.438 V | trap 1 ns, tight | 0.4000 mA | 0.4000 mA | 1.000004 | 0.511406 nJ |
| -0.438 V | trap 100 ps, tight | 0.4000 mA | 0.4000 mA | 1.000008 | 0.511406 nJ |
| -0.438 V | Gear2 1 ns, tight | 0.4000 mA | 0.4051 mA | 1.012735 | 0.511406 nJ |
| -0.438 V | Gear2 100 ps, tight | 0.4000 mA | 0.4038 mA | 1.009547 | 0.511406 nJ |
| -5 V | trap 1 ns, original | 21.1363 mA | **27.0948 mA** | **1.282** | 29.5457 nJ |
| -5 V | trap 1 ns, tight | 21.1363 mA | 21.1363 mA | 1.000001 | 29.5457 nJ |
| -5 V | trap 100 ps, tight | 21.1363 mA | 21.1363 mA | 1.000001 | 29.5457 nJ |
| -5 V | Gear2 1 ns, tight | 21.1363 mA | 21.1393 mA | 1.000143 | 29.5457 nJ |
| -5 V | Gear2 100 ps, tight | 21.1363 mA | 21.1395 mA | 1.000151 | 29.5457 nJ |

Every variant's late flat current agrees with the independent oracle. The
original-tolerance trapezoidal peaks exceed the monotonic bound, while tight
trapezoidal runs converge to the bound and Gear2 is within 1.3% in the
0.438-V case and 0.02% in the 5-V case. Full-window clamp energy changes by about 8 parts per million between the
original and tight settings in the 0.438-V case, and is unchanged at the
printed precision in the 5-V case. This is evidence of numerical stability
for these two energy integrals. It does show that instantaneous peaks are
solver/model-sensitive at the 1 mOhm knee.

`results.csv` contains all ten rows, including signed positive resistor-current peaks and energies. The
`resistor_positive_peak_a` column is MAX of signed current, not maximum
absolute resistor current; negative-pulse current dominates its magnitude.
The Rust checker prints:

```text
PASS diagnostic parsing: 10 finite results; flat currents agree with monotonic oracle
```

## Commands and source identity

```text
rustc --edition=2021 -D warnings -O generate.rs -o generate
./generate .
for cir in generated/*.cir; do
  perl -e 'alarm 30; exec @ARGV' ngspice -b -o "${cir%.cir}.log" "$cir"
done
rustc --edition=2021 -D warnings -O check.rs -o check
./check .
```

No full plant simulation was run. The generated decks/logs/raw files are
listed in `generated.sha256`. Keep the parent instantaneous peak columns
labelled **UNVALIDATED**; use the flat current and separately converged energy
results for this sensitivity experiment. A real diode's pulse SOA and
temperature behavior remain unqualified.
