# UCC27624 ENA corner review — OPEN

This is a selection constraint for the joined U4 circuit, not a passing
electrical analysis. The proposed driver is a production
`UCC27624DDAR` (DDA 8-pin PowerPAD); its pin 1 ENA, pin 2 INA, pin 3 GND,
pin 6 VDD, pin 7 OUTA, pin 8 ENB, and pin 4 INB follow the
[TI UCC27624 data sheet](https://www.ti.com/lit/ds/symlink/ucc27624.pdf).
The inactive channel's ENB and INB require local low connections, while
OUTB remains unconnected. The DDA thermal pad requires its own GND land
review.

TI specifies an ENA output-low threshold range of 0.8–1.2 V and an
output-high threshold range of 1.8–2.3 V. Design against **ENA ≤0.8 V**
for guaranteed disable and **ENA ≥2.3 V** for guaranteed enable, at the
applicable operating corners. TI gives the internal EN pull-up as
**200 kΩ typical only**, without a minimum resistance in the electrical
table. A floating ENA enables the channel. A passive 10 kΩ or 1 kΩ
pull-down on an unpowered logic-gate output is therefore not, on its own,
a source-backed worst-case OFF proof. The nominal divider estimate cannot
be promoted to a guarantee:

```text
V_ENA(max) = V_AUX(max) * R_PD(max) / (R_PD(max) + R_EN_internal(min))
```

`R_EN_internal(min)` is not specified. The joined design needs a separate
source-backed low clamp or verified bounded current over the actual AUX
range, including HOT logic5 absent or between guaranteed operating levels.
An AUX-powered, normally-on shunt is a candidate, but it needs its own
guaranteed bias, transistor saturation/on resistance, leakage, temperature,
startup crossover, and turn-off/turn-on delay analysis. The available
[AO3400A data sheet](https://aosmd.com/res/data_sheets/AO3400A.pdf)
specifies a 2.5 V RDS(on) point at 25 °C and an absolute ±12 V VGS limit;
those two facts alone do not establish a cold/hot rail-order guarantee.

For an actively driven high state, check the preceding gate's VOH at the
worst pull-down and EN input load against 2.3 V. For the low state, check
its VOL and leakage against 0.8 V, and check that an unpowered gate cannot
back-power HOT logic5. The UCC27624's listed 17–27 ns enable/disable
propagation assumes its data-sheet fixture and is only one term in the
detector-to-sustained-current-cessation path. Loaded STW gate discharge,
commutation, and the independent hazard-derived allowable time remain OPEN.

Do not connect the UCC27624 ENA to an HCS latch Q or a named `DRIVER_ENABLE`
net and infer a safe power-off default without the actual drive/clamp parts
and the above corners. Native board approval needs the exact pin and
footprint implementation, then low-voltage captures with AUX present and
HOT logic absent, present, falling, and recovering.
