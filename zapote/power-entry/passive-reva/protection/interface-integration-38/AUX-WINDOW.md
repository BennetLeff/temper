# Rev38 AUX fast-dip and overvoltage candidate

Status: **compiled pin topology; thresholds and response acceptance OPEN**.
The independent [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
monitors AUX undervoltage with a 100 pF CT capacitor. This module uses a
[TLV3202](https://www.ti.com/lit/ds/symlink/tlv3202.pdf) powered from HOT
logic5 to detect an AUX dip without that CT delay, and its spare channel to
detect AUX overvoltage. Both outputs feed a
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf). Its high
output is a necessary condition at the second HCS21 gate in the VD/VB
detector. That gate's output drives receiver `HOT_FAULT_N` and the retained
trip fan-in. A local 10 kΩ pull-down at `AUX_WINDOW_OK` holds the condition
low if its producer is absent. The LM4040 reference is shared by physical
pin with the VD/VB detector, and the AUX divider input is joined to the
protected driver supply.

| Channel | Divider, input isolation | Comparator polarity | Nominal crossing |
| --- | --- | --- | --- |
| Fast dip | 430 kΩ / 100 kΩ, then 22 kΩ to IN1_P | IN1_P against REF25 at IN1_N; high when AUX is above threshold | 2.5 × (1 + 430/100) = 13.25 V |
| Overvoltage | 560 kΩ / 100 kΩ, then 22 kΩ to IN2_N; 22 kΩ between REF25 and IN2_P | High when AUX is below threshold | 2.5 × (1 + 560/100) = 16.50 V |

The selected Yageo 430 kΩ and 560 kΩ parts are 1% 0603 candidates. Their
nominal crossings do not establish an allowed AUX operating window. Verify
the protected AUX source's low/high/ripple/overshoot envelope, both resistor
corners, LM4040 reference current and tolerance, comparator input offset and
hysteresis, common-mode range, 22 kΩ input-injection current, LVC and HCS
logic levels, supply collapse, and fault pulse width. A fast comparator is
not proof of sub-microsecond fault-to-retained-clear timing. The VD/VB
detector, rail supervisors, retained clear, ENA shunt, loaded gate and switch
current must be included in a worst-case physical response bound.

The standalone and joined Atopile builds pass. `audit.rs` checks both
dividers, comparator polarity, reference join, AUX supply join, separate
push-pull outputs and the HCS21 fan-in; deliberate opens and swaps fail.
The AUX source itself is still an external port, and no native footprint or
powered result is approved.
