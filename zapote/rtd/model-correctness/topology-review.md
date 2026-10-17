# RTD model-correctness review

**Scope:** standalone RTD unit, current canonical Atopile topology, and retained static/transient model artifacts.  This review does not change `elec/src`, PCB files, accepted model receipts, or frozen evidence.  The corrected REF copy and its regression are under `model-correctness/`; scratch reproductions are under `/private/tmp/rtd-model-correctness-luna/`.

The nominal topology mapping is independently reproduced: the Python revised model and an independently written ngspice netlist agree at the healthy 194.1 Ω point within `4.84e-8 V` after ngspice's printed-value rounding. The runnable deck, comparison script, and receipt are under [`evidence/`](./evidence/). This supports the resistor topology mapping only; it does not establish PVT, MAX macro-model, or physical proof.

## Prioritized findings

### 1. Incorrect: frozen REF2025 corner envelope is below its declared source limits

`zapote/rtd/circuit/rtdin_comparator_model.py` uses 3 ppm/V and 8 ppm/mA with a ±0.165 V line/load delta around 3.3 V. The declared supply is 3.135..3.465 V, while the REF2025 initial-accuracy test point is VIN=5 V and the applicable maximums are 35 ppm/V and 20 ppm/mA. The corrected proof computes the divider load at the corrected maximum VBIAS as `0.096346840145 mA` and rounds it upward to `0.096350 mA`; this includes both +5 nA comparator-input sinks at their divider-weighted source-current contribution and assumes `sensem >= 0 V` (the maximum-loading endpoint). It yields the old envelope `1.24877341883..1.25122658117 V` and corrected envelope `1.24869099750..1.25130900250 V`. Each side of the old envelope is underbounded by about `82.42 µV`.

This is a model-envelope error, not a circuit-intent change. The corrected copy is [`revised/rtdin_comparator_model.py`](./revised/rtdin_comparator_model.py). The focused regression is [`ref2025_envelope_regression.py`](./ref2025_envelope_regression.py), and its generated receipt is [`ref2025_envelope_regression.json`](./ref2025_envelope_regression.json). The regression asserts that the old envelope fails the corrected requirement, the revised envelope passes, and representative healthy/open comparator polarities remain unchanged.

Reproduction:

```sh
python3 zapote/rtd/model-correctness/ref2025_envelope_regression.py
```

Result: `old_underbound_lower_v=true`, `old_underbound_upper_v=true`, `revised_meets_lower_v=true`, `revised_meets_upper_v=true`; all representative polarity checks passed.

**Action:** regenerate the static model receipt from the revised copy after the parent datasheet audit accepts the same load convention. Do not treat the corrected copy as whole-unit acceptance or as PVT proof.

### 2. Incorrect claim: the scalar timing calculation does not establish its maximum

The retained transient model hardcodes one healthy/fault margin pair per
conductor. Its FORCE+ pair produces 1.323511 ms, but a larger starting healthy
margin increases scalar crossing time for a fixed final negative margin.
Mixing independent extrema can be conservative when their directions are
chosen correctly; the defect is the endpoint maximization, not mixing alone.

[evidence/analytic_pairing_repro.py](evidence/analytic_pairing_repro.py) loads
the old static model and evaluates healthy and FORCE+ at the same parameter
combination and RTD=194.1 ohm. The resulting margins, +0.446956004 V and
-0.173305557 V, produce **2.105927 ms** with the retained scalar tau=1.5067 ms
and 20 mV overdrive. This exceeds both the claimed scalar maximum and its
2 ms allocation.

This is a reproducible counterexample to the scalar calculation's claimed
maximum. It is not a full-network transient demonstrating a physical 2 ms
violation. The one-pole envelope's relationship to the two-node network still
requires proof; neither number qualifies the complete transient response.

**Action:** replace the claimed bound with a validated full-network timing
analysis, maximizing over applicable initial conditions and parameter ranges.
If a scalar envelope is retained, prove both its endpoint extremization and
its dominance over the modeled network. Keep the timing allocation unqualified
until that evidence exists.

### 3. Limited evidence, currently overstated by adjacent receipts: transient corner coverage is not a corner sweep

The retained ngspice decks do run, but they are isolated diagnostic checks. `rtd_sense_open_rc.cir` holds `sensem` at a fixed `0.3773585 V` and sweeps only `RDIAG`, `CDIFF`, `CPAR`, and one leakage source; it does not solve the canonical RTD/force/sense network or comparator threshold. The Python transient generator evaluates 8 open transitions and 4 short transitions at one `Params()` corner; it has no resistor/capacitance/leakage corner loop. Reproduction:

```sh
python3 zapote/rtd/circuit/rtdin_transient_model.py > /private/tmp/rtd-model-correctness-luna/transient-rerun.txt
rg -c '^RTD=' /private/tmp/rtd-model-correctness-luna/transient-rerun.txt   # 8
rg -c '^SHORT_INIT=' /private/tmp/rtd-model-correctness-luna/transient-rerun.txt  # 4
ngspice -b zapote/rtd/circuit/rtd_sense_open_rc.cir > /private/tmp/rtd-model-correctness-luna/ngspice-senseplus-rerun.txt 2>&1
rg -c '^v_diff_' /private/tmp/rtd-model-correctness-luna/ngspice-senseplus-rerun.txt  # 108 measurements
python3 zapote/rtd/model-correctness/evidence/timestep_convergence.py
```

The selected SENSE+ / 100 Ω case at `RDIAG=1.057 MΩ`, `RWIN=102 kΩ` crosses at `0.370000`, `0.369500`, and `0.369250 ms` for 1, 0.5, and 0.25 µs implicit-Euler steps (spread `0.000750 ms`). This is a discretization check for one case, not a corner-sweep result. The timing and ngspice receipts are retained under [`evidence/`](./evidence/).

The current canonical Atopile network does match the modeled resistor branches: `RREF → FORCE_P → RTD → FORCE_N → return`, separate `RTDIN_P/RTDIN_N` sense leads, 1 MΩ pullups to BIAS, a differential capacitor at the MAX pins, a 100 kΩ protected RTDIN_P comparator branch, and the LOW divider bottom returned to RTDIN_N. The limitation is coverage and model scope, not a discovered source-topology mismatch. The ngspice deck's fixed endpoint is useful as an independent R-C sanity check, but it cannot substantiate the full-corner or full-network wording in adjacent contract text.

**Action:** either narrow the receipt/contract wording to “nominal Python network plus isolated R-C checks,” or add an executable parameterized ngspice/full-network sweep before claiming transient corner coverage. Preserve the historical SINC artifact as conditional and separate.

## Receipts and hashes

- `python3 -m py_compile zapote/rtd/model-correctness/revised/rtdin_comparator_model.py`: passed.
- `python3 -m json.tool zapote/rtd/model-correctness/ref2025_envelope_regression.json`: passed.
- `ngspice -b zapote/rtd/model-correctness/evidence/independent_static_corrected.cir`: exit 0; Python/ngspice max absolute printed-value difference `4.8301887e-8 V`.
- `python3 zapote/rtd/model-correctness/evidence/analytic_pairing_repro.py`: passed; same-RTD 194.1 Ω scalar case `2.105927 ms` versus frozen cross-pair `1.323511 ms`.
- `python3 zapote/rtd/model-correctness/evidence/timestep_convergence.py`: passed; selected-case crossing spread `0.000750 ms`.
- `python3 zapote/rtd/circuit/rtdin_transient_model.py`: exit 0.
- `ngspice -b zapote/rtd/circuit/rtd_sense_open_rc.cir`: exit 0.
- Root independently replayed all four retained proof scripts successfully. Input and artifact hashes are retained in `root-verification.json`.

Physical wiring, EMC, MAX internal behavior, and PVT remain outside this bounded model review.
