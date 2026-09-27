# Tank-CT detector: trip model

The detector on this board is a port of the reviewed standalone design in
`zapote/current-sense/circuit/current_sense_unit.ato`:

- a floating 1.50 Ω burden across T1's secondary, around a 1.65 V midpoint
  bypassed by 100 nF
- a 1 kΩ series input with BAT54H clamps to the rails
- one TLV3201 per polarity
- 3.3 V from J4.3

It is instantiated at the end of `PowerStage120V` in
`elec/src/power_stage_120v.ato`.

`ct_detector_model.rs` is that unit's Rust model with three changes:

| Change | Standalone unit | This board |
| --- | --- | --- |
| Reference dividers | 3.74 kΩ / 10 kΩ | **3.32 kΩ / 10 kΩ**: the trip rises above this stage's 37 A normal tank peak |
| Trip requirement window | 45–55 A | **50–60 A**: ≥ 1.35 × normal peak, well below T1's 88 A |
| SENSE_MON input bias | Two comparator inputs | **Three** (positive, negative, zero-cross), ±15 nA |

Replay:

```sh
rustc -O ct_detector_model.rs -o /tmp/ctdet && /tmp/ctdet > model_output.json
rustc --test ct_detector_model.rs -o /tmp/ctdet_t && /tmp/ctdet_t   # 6 tests
```

## Result (`model_output.json`)

- **Nominal trip:** 55.17 A for each polarity.
- **Bounded DC corner band:** 50.93–59.51 A. It enumerates 65,536 corners of:
  - resistor tolerances
  - ±5 % rail
  - BAT54H leakage at 25 °C
  - host-monitor load
  - comparator input bias, offset and CMRR

  The band is inside the 50–60 A window.
- **Sense voltage at ±88 A:** 2.97 V and 0.33 V, inside the rails.

This is a bounded DC calculation, not a qualification. Several things are
outside it:

- CT ratio vs frequency, and magnetizing current
- hot clamp leakage
- comparator hysteresis
- trip timing
- zero-cross behaviour with no tank current

Those remain bench items (task 02 and the current-sense unit's own
qualification list).
