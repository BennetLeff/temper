# Buck Rev A — equipment, wiring, and probing

## Required capabilities

| Instrument | Capability | Why |
|---|---|---|
| DC supply | Isolated, adjustable **13.5–16.5 V**, current-limited; settable 0.10/0.30/0.50 A limits | Staged first power (§2–§5 of runbook); a supply in current limit invalidates results |
| DMM | DC volts/amps at board terminals | VIN/VOUT/IIN/IOUT at every point |
| Electronic load | 3.3 V operation, CC mode, **programmed pulses 0.05↔0.5/1.0 A** with 0.1 A/µs slew and 10 ms plateaus | Steps/pulses per definitions; resistors cover staged DC only |
| Oscilloscope | ≥100 MS/s, deep enough memory for **100 ms steady** captures; 20 MHz bandwidth limit; pretrigger | Startup (t0+20 ms), ripple windows, transient edges |
| Voltage probing | Short ground spring / low-inductance return; differential probe or appropriate setup for non-ground nodes | Ripple integrity; ground-referenced clips only on verified GND |
| Current verification | Means to verify **measured load current** slew/plateau (load monitor output, current probe, or equivalent) | Front-panel setting alone is not evidence |
| Temperature | Thermocouple or adequately characterized setup on U3 case + L2 surface, placement/emissivity recorded | Thermal screen + 80 °C protective stop |

## Bench wiring

```
SUPPLY+ ──→ J1.1 VIN        J2.1 3V3 ──→ LOAD+
SUPPLY− ──→ J1.2 GND        J2.2 GND ──→ LOAD−
              TP1/TP2 = board VIN     TP3/TP4 = VOUT
              (measure AT the board)  (ripple: prefer C11/C12 pads)
```

See `images/bench-wiring-provisional.svg` (provisional until freeze).
Keep power leads short and twisted; sense VIN/VOUT at the board terminals, not at the
supply/load front panels. Assess supply/load/scope earth connections before probing.
Ground-referenced scope clips connect **only** to verified circuit GND. Where a
ground-referenced connection would short a node, use a differential probe or otherwise
appropriate setup.

## Probing rules

- Ripple: short ground spring or equivalent directly at C11/C12; 20 MHz limit.
  TP3/TP4 only if proven equivalent pickup (see measurement definitions).
- Startup/transient: single-ended probes on VIN (TP1) and VOUT (TP3) with common board
  GND (TP2/TP4); retain pretrigger and full t0+20 ms / edge-to-plateau windows.
- SW access (if the final board provides it): **optional diagnostic only**, not a
  first-power connection; never a permanent shunt or long wiring in the switching path.
- Do not add a permanent shunt or long wiring in the buck switching path just to
  measure current.

## Capability gaps — what becomes unavailable

| Missing capability | Consequence |
|---|---|
| No programmable/CC load (resistors only) | Staged DC regulation: runnable. Formal startup compliance (0.5 A `clamp(VOUT/0.1 V)` law), slew-controlled steps, and 1 A pulses: **NOT RUN** (exploratory smoke checks only, labeled as such). |
| No verified current measurement (slew/plateau) | Steps/pulses: **INDETERMINATE** even if voltage looks fine. |
| Scope without 20 MHz limit or 100 MS/s / 100 ms memory | Ripple comparison: **NOT RUN/INDETERMINATE**; retain a labeled exploratory capture. |
| No short-return probing (long ground clip only) | Ripple result: **INDETERMINATE** (loop pickup dominates). |
| No temperature measurement | Thermal screen: **NOT RUN**; the 80 °C protective stop cannot be enforced — do not advance past no-load checks. |
| Cannot establish 25 °C ambient | Efficiency values retained as observations; threshold comparison: **NOT RUN/INDETERMINATE**. |

Instrument limitations and results near measurement uncertainty must remain visible in
the run record. A missing capability never becomes a pass.
