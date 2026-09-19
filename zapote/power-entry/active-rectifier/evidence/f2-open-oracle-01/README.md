# Independent immediate-off numerical check

Date: 2026-09-19. **Illustrative numerical oracle, not a physical protection
result.** ngspice 45.2 checks the lossless LC calculation used by the bounded
F2-open investigation. This does not model the UCC28180, fuse opening, MOSFET
turn-off delay, startup, saturation, component tolerances, or an actual surge.

The assumed initial conditions are constant input 186.676190233 V, local
capacitor 400 V, inductor current 20 A, 180 uH and 470 nF. The switch is already
off; the diode transfers inductor and continuing source energy into the local
capacitor until current decays. The selected current and voltage are numerical
test inputs, not a demonstrated joint operating corner.

The diode is synthetic: `IS=1e-12 N=1 RS=0.001 CJO=10p TT=0`. It is deliberately
not called a C3D20065D device model. Its small junction capacitance regularizes
the open-circuit transition; its forward loss explains most of the difference
from the ideal result. The 1e12-ohm output resistance is a numerical leakage
path, not a board bleeder.

| Quantity | Result |
|---|---:|
| Ideal lossless peak, including source work | 632.432331 V |
| ngspice peak, 10 ns maximum step | 632.018074 V |
| ngspice peak, 5 ns maximum step | 632.018077 V |
| Difference between step refinements | 0.000003 V |
| Source work up to peak, 5 ns run | 0.020356573 J |
| Series diode energy, 5 ns run | 0.000086747 J |
| LC energy change, 5 ns run | 0.020269824 J |
| Energy residual, 5 ns run | -0.00000000173 J |

Energy is integrated from the first retained raw sample to its voltage maximum,
using trapezoidal integration of line current and diode terminal power.
Residual = change in LC energy + diode terminal energy - source work. The tiny
nonlinear junction stored energy and output leakage are not separately modeled
in this balance; this is a convergence check, not a claimed physical error bar.

Reproduce from this directory:

```sh
ngspice -b regularized-10ns.cir > regularized-10ns.log 2>&1
ngspice -b regularized-5ns.cir > regularized-5ns.log 2>&1
```

Raw traces, decks and solver logs are retained and hashed in `result.json`.
Check the logs for successful completion, not only the process exit code:
ngspice returned zero for the two rejected initial decks as well. Those decks
used zero junction capacitance with very small ideality factors and aborted
with a timestep-too-small diagnostic near current extinction. Their original
logs and decks are retained as failures; their absolute temporary output paths
are historical. They were not accepted or treated as physical instability.

This independent numerical agreement supports the LC algebra and source-energy
accounting only. It cannot certify the real capacitor, switch, diode, controller
or fault arrangement, and no harness threshold has been changed.
# Retained nominal-current cross-check

`nominal-model-5ns.cir` uses the same synthetic numerical diode with the
retained CCM model's simultaneous 120 Vrms line-crest and switching-ripple
peak: Vin=169.705627485 V, V0=389.615384615 V, I0=23.231838319 A.
It completed with 6047 raw samples and a 674.288936 V peak; the ideal equation
gives 674.741202 V. Energy balance to the peak closes to about 1.7 nJ after
including source work and synthetic-diode terminal energy. Raw deck, log,
samples and hashes are in `result.json`. This is another numerical equation
check, not a controller model or a hardware stress bound.
