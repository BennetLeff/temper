# D-34 — offline bench verdict tool

**Implemented B0–B4 numeric screens with fail-closed capture validation; the real D2 software fixture correctly fails B2's partner-gate screen.**

Use [bench-verdict.md](../../../../../validation-plan/bench-verdict.md) for channel names, units, metadata, probe-delay sign, threshold definitions and limitations. The program is `validation-plan/bench_verdict.py`; it never controls hardware.

## Evidence and reproduction

From the repository root:

```sh
zsh zapote/power-stage-120v/validation-plan/sim-kit/models/fetch_models.sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/sim-kit/smoke_test.py
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-plan/make_bench_fixture.py
python3 -m unittest discover -s zapote/power-stage-120v/validation-plan -p test_bench_verdict.py -v
python3 zapote/power-stage-120v/validation-plan/bench_verdict.py zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D34/d2.csv zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D34/d2.json
```

The last command intentionally exits 1. `d2-verdict.json` records the simulated partner-gate peak, limit and FAIL. `d2.json` binds deck/vendor hashes and parameters; `ngspice.log` and `ngspice-version.txt` identify the actual run. Licensed models remain ignored and are not committed. The fixture uses D2's default inductances, zero load current, 50 V bus and the Infineon die-gate waveform. It exercises the parser and detector on real solver output; it is not a native-20 hardware result or a board-matrix validation.

`test_bench_verdict.py` independently supplies piecewise-linear timing and triangular charge oracles. Every emitted acceptance criterion has passing and failing inputs. Tests also cover ringing/noise, deskew sign, absent edges, incomplete windows, invalid metadata and wrong VDS reference plane. See `tests.txt` and `smoke.txt`.

## Limits

The tool checks numerical screens, not fixture readiness. B3 recovery quantities have no fabricated pass limit at native S4 conditions. B4's addendum/ledger endpoint mismatch is made explicit in the tool documentation. No bench capture, instrument qualification or physical gate-off guarantee was produced.
