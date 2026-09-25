# Revision B named-node and margin contract

| Node | Producer / condition | Consumer / fail state |
|---|---|---|
| `health_ok` | Four bus-voltage TLV3202 outputs through HCS21 gate1 | HCS21 gate 2; low asserts asynchronous latch clear |
| `rails_ok` | TPS3890 RESET AND, 100 kOhm pulldown | HCS21 gate 2; low when either rail is below threshold or logic5 is absent |
| `clear_ok` | HCS21 gate 2: `health_ok & rails_ok & permit_safe & fast_aux_good` | HCS74 CLR and enable qualification |
| `run` | HCS74 Q after a fresh ARM rising edge | Enable AND input and test observation |
| `enable_good` | LVC AND of retained `run` Q and `clear_ok` | BSS138 gate; cannot rise without a qualified ARM edge and healthy clear |
| UCC27511A IN- | 1 kOhm aux15 pullup in a 1210 part, BSS138 sink only while `enable_good=1` | High disables output; low permits PWM |

Nominal supervisor calculations use the TPS3890 1.15 V falling threshold:

```text
logic5_trip = 1.15 V × (294 k + 100 k) / 100 k = 4.531 V
aux15_trip  = 1.15 V × (1.03 M + 100 k) / 100 k = 12.995 V
```

The values are nominal calculations pending a full resistor/reference corner
sweep. They do not claim production thresholds, hysteresis, or timing. The
100 pF CT capacitors add approximately 132 µs typical reset-release delay per the TI
TPS3890 timing equation; the minimum/maximum timing and rail ramps remain
inputs to host verification. LVC/buffer behavior below 1.65 V is modeled OFF
and is not a guaranteed partial-power transfer specification.
