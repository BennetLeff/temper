# Numerical initialization history

The following unsuccessful approaches are retained, not counted as passing validation:

- Direct old-topology seed: `final-cap`, `final-resistor`, `stage-3p3`.
- Analytically adjusted ADC/input guesses: `adc-only`, `dc22`.
- All-node guesses with a 1e30 Ω numerical shunt: `shunt30`.
- Independently solved FDA + loaded AFE seed with original declaration order: `partition`.
- Pivot, iteration, gmin and numerical shunt sweeps: `pivot*`, `itl`, `gmin*`, `shunt12`, `shunt18`, `loose`, `noop`.

The accepted path retains strict tolerances, unmodified models and the exact physical network. Reordering only top-level component declarations resolves the conditioned KLU solve. `verify_order.rs` demonstrates electrical identity of the smallest failing/passing pair. `strict_order.rs` retains every attempted ordering and accepts only a finite, true-DC Newton result. No fallback transient OP is accepted.

The final 100kΩ-range/50µH coil transient is particularly slow with strict tolerances. `c100k_coil_hi0_lo0-watch.log` streams progress for the original strict run. An early buffered attempt was interrupted to obtain this visible log. Two exploratory TRTOL=7 attempts were interrupted after they showed no useful speed improvement; neither is accepted evidence. The netlist-option attempt was overridden by ngspice's XSPICE default of1, as printed in its log; the control-option attempt changed only the integration error setting. Final results use the original strict setting.

A transient watchdog is a runtime limit, not an electrical failure criterion. Any timed-out corner is retained and must be rerun to completion with a longer limit before the complete-set checker can pass.

For the optional 100 µs LOW-only 100 pF tail extension, a 5 ns maximum-step comparison was also interrupted early: the solver was already taking substantially smaller adaptive steps, so changing the maximum offered no useful speed improvement. It is not included in the accepted case manifest. The completed 20 µs reference and the long-tail primary both retain a 1 ns maximum step.

The optional 100 µs LOW-only fixture extension was deliberately stopped after the required 75-case matrix completed. Its deck and interrupted log are retained as an uncompleted exploratory run; no 100 µs waveform or settling claim is included in the accepted results. The accepted high-range coil evidence is the complete 20 µs trace and its explicitly reported bounded, decaying, not-yet-settled response.
