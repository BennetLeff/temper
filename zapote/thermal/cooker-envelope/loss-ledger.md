# Cooker heat ledger — U1 in progress

Source snapshot: `06d9070c3` Rev38 candidate plus retained bridge studies. Every number below is tied to its original scenario; blank product terms remain **unknown**, not zero.

| Heat source | Existing number/evidence class | Inclusion rule for next model |
| --- | --- | --- |
| Passive GBJ bridge | 40 W allowance in `zapote/power-entry/passive-reva/cooling/thermal-budget.json`; not a measured loss. | Use only with the GBJ geometry and its stated 15 A RMS/temperature model boundary. |
| Other passive PFC components | 65 W allowance in the same cooling screen; `README.md` says the total loss budget remains null. | Split switch, boost diode, inductor, shunt, relay, clamps and auxiliary into source-bound terms before an installed sink result. |
| Passive STW switch-plus-gate | 112.90–157.44 W sensitivity at assumed 9–11 V gate points and 120 Vrms in passive cooling review. | Investigate; do not add as a qualified loss or use the old 65 W allowance as coverage. Rev38 gate network differs. |
| GBU bridge option | 40 W allowance in `zapote/thermal/cooling-options/envelope.json`, with an unverified whole-bridge `RθJC` screening assumption. | Keep GBU and GBJ packages/thermal paths distinct; choose matching bridge and exact source. |
| Rev38 GBJ2510-F bridge/PFC | Rev38 `pfc_power.ato` binds bridge, inductor, STW and diode, but no accepted whole-envelope losses. | Recalculate from Rev38's chosen devices and mains/load/fault envelope. Do not import a GBU result. |
| Inverter switch, tank and coil | No accepted standalone load/loss envelope. | Require pan-state and frequency-specific loss input from inverter U1/U2. |
| Auxiliary and fan electrical loads | HOT source not selected; old 5.6 W fan allowance belongs to a passive cooling screen. | Use selected source/fan, include startup and stall as fault cases. |

The next ranking needs simultaneous losses, inlet temperature and installed airflow. A model with missing sources is indeterminate; it is not a low-loss case.
