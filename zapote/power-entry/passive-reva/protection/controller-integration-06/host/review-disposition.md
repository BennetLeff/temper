# Host disposition of Luna model review

The original read-only report is retained as `luna-model-review.md`; it describes
the pre-correction model. The accepted sources and their checks supersede it.

| Finding | Disposition and evidence |
|---|---|
| Missing ICOMP short protection | Fixed: ICOMP <0.2 V inhibits PWM. Functional trace tests a pin short. |
| EDR incorrectly limited to +40 uA | Fixed: separate normal/soft-start and EDR limits; +275 uA measured after soft-start. Fixed the simultaneous soft-start set/reset edge as well. |
| Unsupported common 40 ohm VCOMP discharge | Replaced with distinct nominal powered OLP (80 ohm) and bias-absent (5.405 kohm) paths from the corresponding datasheet test conditions. These are explicit nominal approximations, not guaranteed dynamic resistance or delay. |
| Reversed/missing negative ISENSE clamp | Confirmed source defect; TI reference-based candidate patch and qualification requirements retained. Frozen source and accepted warm trace are not silently changed. Negative inrush/short qualification remains open. |
| SOC measured only against an ideal VCOMP source | Added actual 40.2 kohm/4.7 uF/220 nF compensation-network trace. SOC discharges it; recovery, standby and repeated soft-start are checked. |
| M1/M2 lack integrated numerical assertions | Added the independent TI worked-point SPICE fixture, current-loop pole/DC response and oscillator check. Full piecewise boundary/temperature coverage remains open. |
| Dead GATE_TAU and incomplete driver current model | Removed dead parameter. Inherited finite RC/Miller model is explicitly nominal; actual loaded current-cessation maxima remain open. |

Additional host fixes: ngspice `limit()` is a random-distribution function, not
an arithmetic clamp. Replaced it with explicit min/max in `clip()`, retained the
rejected source, and reran all fixtures. Current-sense polarity uses the bridge
return, AC-source current is a real branch current, and PCL blanking starts at
the leading gate request rather than an unrelated clock reset.

The final checker requires exact probe names/order, finite data, strictly
increasing time, bounded sample gaps and the declared end time before applying
behavior checks. Expected negatives must fail for the intended behavior, not a
truncated or malformed run. Three checker unit tests and every retained positive
and negative trace were rerun after the parser hardening without altering the
SPICE model or reusing stale source-dependent results.

B2 is a checked nominal behavioral implementation. It is not full controller
qualification; controller maxima, exact vendor macro-model agreement, cold power
startup and the physical standby/isolated ARM producers remain unresolved.
