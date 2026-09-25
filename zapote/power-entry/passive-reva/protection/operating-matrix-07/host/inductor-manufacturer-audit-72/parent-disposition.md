# Parent disposition: selected boost inductor

The exact schematic part is Würth760800301. Parent verification of the
[official datasheet](https://www.we-online.com/components/products/datasheet/760800301.pdf),
revision001.001 dated2023-12-11, agrees with the worker's extracted ratings:
180µH±20% at100kHz/100mV;20mΩ maximum DCR at20°C;24.5A at40K temperature rise;
48A at that rise with4m/s airflow;43A **typical** saturation current under the
listed30% inductance-change criterion. The operating range is−40…155°C and
includes ambient plus self-heating. Those conditions matter;43A is not a
guaranteed all-temperature saturation limit.

The source-bound campaign model contains a fixed180µH inductor and fixed20mΩ
series resistor. Its nominal inductance matches the selected part; its resistor
matches the published room-temperature maximum, not a temperature-dependent
winding model. It contains no inductance-vs-current law, core losses, hysteresis,
or temperature feedback. The small-signal tolerance does not define an
inductance floor during a large-current short circuit.

The nine accepted normal traces report whole-startup-prefix inductor peaks
from25.067335A to36.870698A. These are report-only observations, not settled
inductor RMS or measured winding temperatures. Exceeding the24.5A thermal-rated
number with a brief peak does not by itself prove a thermal violation. Being
below the43A typical number does not establish a guaranteed saturation margin.
The pre-existing normal receipts are unchanged and remain exact nominal-model
screen results.

For the running short-circuit cases, retain every modeled current and node
excursion but do not translate a linear-inductor current peak into a selected-
part survival claim. An excursion into the region of significant DC-bias
inductance change would weaken even a quantitative fault-current prediction.
A retrieved vendor model may support a separate sensitivity case; it cannot
supply missing guaranteed temperature/lot bounds by itself. No model replacement
or additional simulation has been authorized by this receipt or performed here.

The absence of physical hardware still prevents magnetic-loss, winding-temperature
and fault-current correlation. Before hardware decisions, those questions need
appropriate waveform, frequency, airflow and temperature evidence rather than
comparison of an instantaneous peak with a continuous thermal rating.

Bindings and exact per-case peak references are in
[model inventory](../inductor-model-inventory-72.json) and the manufacturer's
[metadata](metadata.json). This review tightens an existing model limitation;
it does not accept or reject a new electrical case.
