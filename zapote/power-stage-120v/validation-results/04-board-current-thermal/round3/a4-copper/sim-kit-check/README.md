# Simulation starter kit

Tested decks and helpers for the power-stage simulation tasks. The procedure
is in [SIMULATION-RUNBOOK.md](../../../../../validation-plan/SIMULATION-RUNBOOK.md).

| Path | What |
| --- | --- |
| `models/fetch_models.sh` | Downloads Infineon's CFD7 650 V SPICE library and checks its SHA-256. `models/vendor/` is not committed |
| `common/run_ngspice.py` | Runs a deck with `NAME=VALUE` parameters. Returns `.meas` results as JSON; `--raw` saves waveforms; `read_raw()` parses them |
| `common/options.inc` | Solver options that converge with the Infineon models |
| `01-switching/leg.cir` | Half-bridge leg, clamped-inductive turn-off / hard turn-on, board L as parameters, die-level measures |
| `02-chain/ct_frontend.cir` | Tank-CT detector front end (native-13 values), trip and zero-cross timing |
| `02-chain/ocp_frontend.cir` | DC-bus shunt OCP front end (U6), detection delay vs current slope |
| `05-tank/tank.cir` | Series-resonant tank over a rectified-line half-cycle |
| `07-emi/emi_transfer.cir`, `post_emi.py` | LISN + input-filter DM/CM transfer functions (FILL_ME parameters from datasheets) |
| `04-current/sheet_solver.py` | Multi-layer DC copper resistance network with analytic self-tests |
| `smoke_test.py` | Runs everything against reference values; must print `SMOKE PASS` |

Reference results come from placeholder inputs. They check the setup; they
are not design results.
