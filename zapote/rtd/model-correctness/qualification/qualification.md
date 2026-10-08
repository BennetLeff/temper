# RTDIN full-network transient qualification

This standalone artifact audits the accepted passive RTDIN network. It does not
change Atopile, PCB, Rust policy, or frozen evidence. The model has the two
actual MAX31865 input states (`sensep`, `sensem`) and solves the other seven
nodes algebraically from the complete resistor graph. It covers continuous
healthy RTD 100..194.1 ohm, shorts 0..10 ohm, four independent 1..50 ohm
conductor resistances, four single conductor opens, independent diagnostic
resistor ranges, R13 range, reference range, leakage, offsets, and capacitor
ranges.

The resistor intervals use multiplicative tolerance and TCR with outward
rounding. The principal ranges are RREF 430 ohm +/-0.05% and 5 ppm/C,
R13 98..102 kohm (1%, 100 ppm/C), each diagnostic resistor 944..1057 kohm,
Cdiff 0.94..1.10 nF (1 nF C0G including tolerance/TCR rounding), and each
pin-to-ground capacitance 0..200 pF. The latter is a conservative independent
pin superset of the declared <=200 pF total parasitic allowance. The reference
range is the outward-rounded 1.24869..1.25131 V contract, reflecting the
corrected 35 ppm/V line and 20 ppm/mA load limits around the 5 V
initial-accuracy condition; it is a model input, not a new datasheet claim.

## Continuous bound

For a fixed passive target network, Schur reduction gives
`C dx/dt + G x = q`. With `e=x-x_final`, `E=e^T G e` decays at least as
`exp(-2 lambda t)`, where `lambda` is the least generalized eigenvalue of
`(G,C)`. For a comparator margin `m=m_final+w^T e`, the bound is
`|w^T e| <= sqrt(E0 * w^T G^-1 w) exp(-lambda t)`.

The runner uses the exact post-fault Schur `Gmin` at the maximum passive
resistance box (and 10 ohm for the short decay box), conservative diagonal
lower boxes for the isolated SENSE opens, an incident-conductance `Gmax` box,
and analytic state/margin enclosures. Isolated SENSE+ and SENSE- opens use the
removed-edge current bound, including the approximately 5.8 mV SENSE-
displacement from the LOW-divider current; FORCE opens and shorts use the
global 2.1 V state envelope. The output coefficient is `[1, alpha_max]` for
LOW and `[1, 0]` for HIGH. Exact zero ohm is an ideal node merge in the
independent SPICE deck; the Python solver uses only its finite conductance
limit to avoid a singular matrix.

The derived final-overdrive reserves are FORCE+ 0.140404 V, FORCE- 1.129465 V,
SENSE+ 1.099557 V, SENSE- 0.475438 V, and short 0.067827 V. The generated
five-record certificate has a passive-network bound of **0.971395 ms** and a
bound of **0.971460 ms** after the separately allocated 55 ns comparator and
10 ns logic delays; the slowest record is SENSE+. This is a conditional
mathematical certificate for the stated passive-network inequalities.
Comparator effective offset/common-mode applicability, the MAX internal
FORCE/ISENSOR behavior, harness/transient envelope, rail sequencing, and
physical validation remain separate boundaries. It does not claim PVT or
physical proof.

Run the certificate with:

```sh
python3 zapote/rtd/model-correctness/qualification/full_network_bound.py > /tmp/rtd-full-network-bound.out
python3 -m json.tool zapote/rtd/model-correctness/qualification/full_network_bound.json >/dev/null
```

## Independent ngspice checks

`spice_cases.py` writes five independently authored decks. Open decks start
healthy with all conductors closed, then fall from control 5 V to 0 V at 10 us;
there are no parallel resistor paths across the switched conductor. The exact
short deck uses `VSHORT sensorp sensorn 0`, an ideal zero-ohm node merge.
Each open deck is compared with the Python model using the same nominal
parameters, 1-ohm leads, 100-ohm RTD, 1.1 nF differential capacitor, and
100 pF per-pin capacitance. The retained `ngspice_*.out` files contain the raw
runs and `ngspice_cases.json` records the parsed values.

The representative Python/SPICE crossing differences are below 1 us for the
four opens and 1.1 ns for the exact-short transient. The exact-short SPICE run
uses the ngspice healthy operating point as its initial state, then merges the
remote nodes and crosses the required -20 mV overdrive after 1.926 ns; the
Python merged-node replay crosses at 3 ns with its 1 ns timestep. These checks
validate the network equations, switch polarity, and exact-short dynamic
setup for representative points; they are not substitutes for the continuous
G-energy certificate.

The seven static nodes are an external passive abstraction. MAX31865
ISENSOR/FORCE internal paths, comparator effective offset/common-mode behavior,
and rail or host partial-power behavior are outside this model and remain
indeterminate at the device-applicability boundary.

Run them with:

```sh
python3 zapote/rtd/model-correctness/qualification/spice_cases.py
python3 -m json.tool zapote/rtd/model-correctness/qualification/ngspice_cases.json >/dev/null
```
