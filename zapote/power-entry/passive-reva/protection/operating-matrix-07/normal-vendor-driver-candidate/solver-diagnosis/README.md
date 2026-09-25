# UCC27511A full-plant solver-stall diagnosis

The retained full-plant vendor candidate stopped in ngspice 45.2 at
`t=0.0973456252139008882 s` after 292.259 s wall time:

```
Timestep too small; time = 0.0973456, timestep = 6.25e-19:
trouble with node "e.xdriver.e_u1_u1_e1#branch"
```

The run is retained under `../tracked/run/`. Its producer and gzip consumer
completed, and the exported trace has 4,353,208 finite, strictly increasing
rows. The endpoint is incomplete by construction (`0.0973 s` of the requested
`0.5 s`), so it is diagnostic only.

The reported branch is the voltage source at lines 52–53 of the unchanged TI
model:

```
E_U1_U1_E1 U1_U1_N16684643 OUTH VALUE { IF(V(U1_U1_N16687249, 0) > 0.5,
+ 5, -5) }
```

This is a hard ±5 V behavioral predriver source. It is distinct from the
input comparator; the model's `BUF_DELAY_BASIC_GEN` path has a documented
9 ns parameter at lines 58–59. The full trace gives a bounded correlation:

* controller `v(xu.raw)` falls at `0.09734561255392814 s`;
* isolated `v(pwm_input)` crosses 2.2 V at
  `0.09734561503547613 s`;
* the solver stops `~10.18 ns` later, at the model's 9 ns delayed predriver
  transition, while `v(outh)=14.9994 V`, `v(outl)=14.9845 V`, and
  `v(gate)=14.9845 V`.

This timing and node identity support a coupled hard-source event at the E1
predriver boundary. They do not prove that the TI model is electrically wrong:
the standalone model and the complete normal-tracked power stage create a
different Newton system, and the vendor model itself remains byte-identical.

## Bounded reduced tests

All decks use the unchanged copied model (`../vendor/UCC27511A.lib`) and a
local `.spiceinit` containing `set ngbehavior=ps`; this is required before
parsing the PSpice `IF(...)` expressions. The in-deck command is retained as
well, but cannot establish compatibility for parse-time model expressions.

* `pwm-edge.cir` exercises a 16.2 kHz PULSE with the 10 Ω split outputs and
  12 nF gate load; it completes with 13,688 rows.
* `pwm-edge-129k.cir` exercises the approximately 129.1 kHz full-plant PWM
  period; it completes with 126,576 rows.
* `input-fall.cir` replays the full-plant 13.5827 V input fall through 2.2 V
  in 1 ns with 10 Ω outputs; it completes with 20,071 rows.
* `input-fall-gear2.cir` repeats that boundary with Gear integration; it
  completes with 20,122 rows.
* `input-fall-plantload.cir` adds the normal 112 pF gate-drain and 344 pF
  switch-node parasitics at 77 mV; it completes with 20,071 rows.
* `input-fall-100r.cir` is a resistor sensitivity probe only; changing both
  output resistors to 100 Ω also completes. This is evidence that a larger
  resistor is a possible numerical damping experiment, not a qualified value.
* `late-edge-trap.cir` and `late-edge-gear2.cir` use an approximate translated
  fast input edge near `0.09734561255392814 s` and integrate through the
  reported `0.0973456252139008882 s` neighborhood with a 500 ns coarse step.
  Trap completes with 200,179 rows and Gear-2 with 200,265 rows.

These tests do not reproduce the full-plant stall. They bound the conclusion:
the omitted controller/power-stage coupling, state history, or absolute-time
context may still matter. Changing integration method or output resistance in
a reduced deck is therefore not a demonstrated remedy.

## Remedy boundary

The existing normal-tracked authored surrogate also has a separate numerical
stall and is not an accepted fallback. Keep both models diagnostic while
running one bounded full-plant candidate experiment that changes one physically
explicit interface element at a time. Do not edit or smooth the vendor
`E_U1_U1_E1` source: that would cease to be the manufacturer model. A future
candidate may evaluate finite input conditioning or a larger split-output
damping resistor, but it must first pass a full-plant run and timing/drive-
current checks; the reduced sensitivity probes here do not justify adopting
either value. The prior full-plant 0.2 V authored-driver probe stopped at about
66 ms and did not reach the original authored-driver failure at 256.99 ms,
so it remains untested as a repair for that separate failure. The next proposed
vendor-model test instead changes only the numerical integration method to
Gear with maximum order two and stops at 110 ms. Neither is an adopted repair.
