# PWM DAC unknown-state safety probe

This standalone fixture tests the XSPICE undefined path that is otherwise
hidden by the DFF's `ic=0` initialization. It does not modify the canonical
experiment.

The analog input is held at 2.5 V and the ADC bridge is deliberately widened
to `in_low=2`, `in_high=3`, so the digital `data` node becomes undefined. Three
DAC/gate combinations are evaluated in parallel:

| combination | DAC `out_undef` | Bgate transfer | final gate |
|---|---:|---|---:|
| old | 2.5 V | `(hold > 2.5) ? 15 : 0` | 0 V |
| unsafe finite | 2.5 V | `3*hold` | 7.5 V |
| safe finite | 0 V | `3*hold` | 0 V |

The simulation completed with exit code 0 and 28 rows. The analog export is
`unknown-analog.tsv`; digital `v(data)` was intentionally excluded from that
export because XSPICE event vectors do not have the same sampled length as
analog vectors. The final rows are stable at:

```text
raw=2.5 V, hold_old=2.5 V, hold_bad=2.5 V, hold_safe=0 V,
gate_old=0 V, gate_bad=7.5 V, gate_safe=0 V
```

This confirms that changing `UPWM_DAC out_undef` from 2.5 V to 0 V is required
when Bgate uses the finite proportional transfer. The old hard threshold is
safe by coincidence at exactly 2.5 V; the finite transfer is unsafe unless its
undefined code is explicitly mapped to zero.

Hashes:

```text
unknown.cir         234f595e3ab267a168235d9664b4cf5ea7d9b1618d0f1106c4fb077ed60e0832
unknown.log         639626bdbffb1d677c7cb9d8a96e39e8647176bedaeb87c71bd88437d1ff5fa1
unknown-analog.tsv  829f7b9d8041d00a46be82f3b2870b481d2c4485cf292ff3bd67c4bf5463285b
```

