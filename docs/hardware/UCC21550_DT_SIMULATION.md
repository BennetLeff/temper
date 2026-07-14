# UCC21550 DT in-box simulation

The repository now has a small analytical model at
`elec/validation/ucc21550_dt_sim.py`. It is intentionally independent of the
Atopile netlist so it can be run in CI and property-tested without requiring a
SPICE installation:

```bash
PYTHONPATH=elec python3 -m pytest -q elec/validation/test_ucc21550_dt_sim.py
```

The legacy `components/UCC21550/UCC21550.lib` is useful for rough output-stage
experiments, but its current behavioral channel does not consume the DT pin;
`components/UCC21550/UCC21550_test.cir` therefore cannot validate an RDT value
(and its old test intentionally uses a 1-MΩ DT resistor). Do not treat that
waveform as DT evidence until the model is replaced with a vendor model or a
reviewed, edge-accurate behavioral model.

TI lists an official UCC21550B-Q1 PSpice model (SLUM881) on the
[UCC21550-Q1 product page](https://www.ti.com/product/UCC21550-Q1). Importing
that model is a separate evidence task: retain its provenance/license, check
whether it runs under ngspice, and compare its 90%/10% DT measurement against
the analytical corner sweep below.

## Model

The model evaluates TI's published relationship

```text
tDT(ns) ≈ 8.6 × RDT(kΩ) + 13
```

and sweeps these explicit assumptions:

| Variable | Sweep |
|---|---:|
| RDT nominal | 34 kΩ (candidate), ±1% |
| Resistor TCR | 100 ppm/°C magnitude (board assumption) |
| Temperature | −40 °C, 25 °C, 150 °C |
| Driver characterization scale | 0.90× … 1.10× |

The ±10% scale is derived from the min/typ/max table entries at 20 kΩ and
50 kΩ in the [TI UCC21550-Q1 datasheet](https://www.ti.com/lit/ds/symlink/ucc21550-q1.pdf);
it is an explicit modeling envelope, not a replacement for a guaranteed
continuous-range IC limit.

## Result

| RDT | Nominal | Modelled programmed-DT range | 300 ns corner result |
|---:|---:|---:|---|
| 34 kΩ | 305.4 ns | 270.5–343.2 ns | Fails under stated IC/temperature envelope |
| 39 kΩ | 348.4 ns | 308.6–391.6 ns | Passes under stated envelope |

The firmware's complementary PWM input dead time is 300 ns. TI specifies that
the driver uses the longer of the programmed DT and the input signal's own
dead time, so the in-box model also checks that the effective system interval
never falls below 300 ns even at the 34-kΩ low corner. That is a system-level
timing result; it does not turn 34 kΩ into a 300-ns hardware-only guarantee.

The resistor recommendation is solved against the minimum resistance in the
complete temperature envelope, including tolerance and TCR. With the stated
positive 100-ppm/°C assumption, −40 °C is the minimum-resistance corner; using
150 °C as the sole "worst" temperature would be optimistic. The calculated
minimum nominal value is 37.87 kΩ, so 39 kΩ is the next reviewed candidate.

This simulation proves the arithmetic, monotonicity, and sensitivity of the
chosen assumptions. It does not prove the real gate-to-gate interval. TI
explicitly notes that system dead time also depends on gate resistors, switch
capacitance, DC-link voltage/current, propagation asymmetry, PCB parasitics,
and the 90%/10% measurement definition. The release gate therefore remains a
scope capture of OUTA/OUTB (and preferably both transistor VGS waveforms) over
temperature and representative load conditions.
