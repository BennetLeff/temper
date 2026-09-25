# Working power target: Control Freak comparison

User clarification: Temper is intended to match the Breville Control Freak; the user did not specify 1.8 kW of DC output or heat delivered to a pan.

The Breville/PolyScience CMC850 US specification sheet gives an appliance electrical rating of **120 V AC, 60 Hz, 1800 W** and a power range of 100–1800 W. Primary manufacturer-authored source, hosted by a distributor: https://savagebros.com/wp-content/uploads/2024/10/Breville-ControlFreak-CMC850_USA.pdf (retrieved through web on 2026-09-22 UTC). This supports interpreting 1.8 kW as the nominal maximum mains-input benchmark. The sheet does not establish pan-heating power, internal DC output, efficiency, power factor, current waveform, or low-line control behavior.

## Working interpretation for the next design comparison

Target the nominal 120 V, approximately 1800 W appliance-input class. Do not require 1800 W DC output or 1800 W delivered to the pan. Allocate conversion losses and auxiliary consumption before selecting a DC-bus power target; those allocations are not yet validated. No PMP10948 efficiency figure is inherited by Temper.

Retain the existing campaign's 15 A modeled input-current screen. If 15 A RMS is also retained as a whole-appliance design constraint, real input power is bounded by voltage × current × power factor: at 108 V its ideal upper bound is 1620 W, and at 120 V its ideal upper bound is 1800 W. Nonunity power factor lowers those bounds. Thus low-line power derating remains necessary under that constraint. This is arithmetic, not a claim about branch-circuit rules or Breville's low-line implementation.

The campaign prescribes ideal auxiliary rails; its measured mains current does not qualify the entire appliance including physical auxiliary power, fans and inverter. The grid's 359–1392 W resistive outputs remain the only accepted modeled load points. No existing pass, criterion or source deck is changed by this clarification.

## Performance parity remains a separate requirement

Matching an electrical nameplate alone does not prove matching cooking performance. Later comparisons must define cookware and contents, heat-up time, temperature accuracy/stability, disturbance recovery, low-power modulation and sustained operation. Those measurements require hardware and lie beyond this PFC-only simulation evidence. The working input-power interpretation resolves the earlier ambiguity without claiming any performance parity.
