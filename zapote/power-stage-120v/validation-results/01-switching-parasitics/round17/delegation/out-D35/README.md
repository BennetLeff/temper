# D-35 — 120 V / 60 Hz numerical flickermeter

**The 20 s default and the existing analytical period rule pass the tested synthetic burst cases; all 22 selected IEC performance points pass their stated tolerances.** This validates the numerical modulation response and classifier used here, not a complete Class F1 instrument or an installation.

## Method and external validation

`validation-results/07-conducted-emi/flicker/flickermeter.py` implements blocks 1–5: half-cycle RMS input adaptation, square-law demodulation, high-pass/carrier-rejection/lamp weighting filters, squaring and 300 ms smoothing, then the smoothed exceedance-percentile Pst formula. Plt uses the cubic mean of twelve consecutive Pst values. The input is instantaneous uniformly sampled voltage, with at least 180 s of settling before a 600 s observation. The digital filter coefficients are derived from the continuous transfer functions with the bilinear transform.

Reference: [IEC 61000-4-15:2010](https://webstore.iec.ch/en/publication/4173), with the [2010 text consulted here](https://previewnorm.com/iec/IEC%2061000-4-15-2010%20PDF.pdf). Clause 5.3 specifies input adaptation; Table 3 the 120 V lamp constants; clauses 5.4–5.7 the filters and statistics. The committed test vectors are the 120 V / 60 Hz points identified in Annex C from Tables 1a, 2a and 5. Clauses 6.2 and 6.3 supply the ±8% instantaneous-response and ±5% classifier tolerances. `performance.json` records each vector, tolerance and result. The scale is calibrated analytically at the 8.8 Hz sinusoidal point; that one point is a calibration check, while the other frequencies and rectangular/classifier inputs are independent checks.

Tests also cover constant-input residual, amplitude scaling, direct percentile arithmetic, invalid input and the cubic mean. Finite carrier rejection leaves a small nonzero constant-input residual; the implementation does not hide it with a notch or clamp. This is not the complete standard test suite: frequency variation, distorted carrier, hardware anti-aliasing, metrology and Class F1 conformity are outside this implementation's validated envelope.

## Burst result

The synthetic source is 120 V, 60 Hz, PF 0.95. Burst current changes the source voltage through R+jX using the same small-signal projection as `burst_flicker.py`. Duty is rounded down to whole half-cycles. Duties tested are 5, 10, 25, 50, 75, 90 and 95 percent. Search is restricted to the approved slow-burst domain, period ≥2 s; it does not claim a global minimum over rapid modulation or all continuous duty values.

| Burst W | IEC proxy: failing / passing adjacent periods, s | Analytical rule, rounded display, s | 20 s Pst, IEC proxy at 4800 Hz | NA illustrative: passing lower search boundary, s |
| ---: | --- | ---: | ---: | ---: |
| 160 | lower search boundary / 2.0 | 2.48 | 0.3080 | 2.0 |
| 200 | 4.6 / 4.7 | 5.06 | 0.3858 | 2.0 |
| 250 | 9.2 / 9.3 | 10.34 | 0.4833 | 2.0 |
| 300 | 14.9 / 15.0 | 18.52 | 0.5813 | 2.0 |

`burst-sweep.json` contains the coarse period/duty grid and sample-rate refinement. `refined-burst.json` contains the 0.1 s refinement and **actual two-hour records evaluated in twelve windows**, for every duty at the accepted period, its tested lower neighbor, and the analytical rule rounded upward to a half-cycle. The acceptance is Pst≤1 and Plt≤0.65. The 300 W 14.8 s candidate passes one short window but fails the two-hour test; the 14.9 s neighbor also fails. This is why the table uses the longer-record result. The reported adjacent intervals are tested brackets, not mathematical minima over phase, duty and impedance.

The IEC impedance is the existing 0.4+j0.25 Ω proxy. The North American example is explicitly a circuit scenario: a 30 m copper loop, 3.31 mm² conductor area, assumed resistivity 1.7241e−8 Ωm at 20°C, 0.03 Ω upstream resistance, and assumed total reactance 0.03 Ω. This gives about 0.1863+j0.03 Ω. It is not a measured service, a population percentile, or a regulatory North American reference impedance. The results depend on these assumptions and ignore regulator, load and grid dynamics beyond the voltage-step model.

No corrected rule is proposed: the current rule is conservative for the tested points. The 20 s default is supported within this envelope. This result does not enable burst mode on native-20; B2 and hardware commissioning remain required.

## Reproduce

From the repository root, with Miniforge Python 3.12 (NumPy and SciPy):

```sh
P=zapote/power-stage-120v/validation-results/07-conducted-emi/flicker
/Users/bennet/Miniforge3/bin/python3 -m unittest discover -s "$P" -p test_flickermeter.py -v
/Users/bennet/Miniforge3/bin/python3 "$P/burst_meter_sweep.py"
/Users/bennet/Miniforge3/bin/python3 "$P/refine_burst.py"
PYTHONPATH=packages/temper-placer/src uv run --no-sync python scripts/import_linter_gate.py
make regen
make regen-check
```

The standalone CLI accepts a NumPy voltage array with `--fs` and `--warmup`; it requires exactly one 600 s evaluation interval. Evidence files are regenerated by the commands above. See `tests.txt`, `environment.json`, `import-check.txt` and `regen-check.txt` for the recorded run.
