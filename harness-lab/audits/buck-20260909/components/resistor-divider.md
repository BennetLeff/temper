# Feedback divider audit

Source declarations:

* R16 `RC0603FR-07100KL`, 100 kΩ ±1% (`elec/src/modules.ato:1490-1493`).
* R17 `RC0603FR-0722K1L`, 22.1 kΩ ±1% (`elec/src/modules.ato:1495-1498`).
* TI VFB limits 0.591/0.609 V are recorded at `modules.ato:1426-1430`.

Using `Vout = VFB * (1 + Rtop/Rbottom)` and independent corners:

* nominal at 0.600 V: 3.3149 V;
* minimum (0.591 V, 99 kΩ, 22.321 kΩ): 3.2123 V;
* maximum (0.609 V, 101 kΩ, 21.879 kΩ): 3.4203 V.

The resulting 3.212–3.420 V range is inside the existing 3.135–3.465 V
assertion. The circuit receipt must preserve this tolerance calculation and
must not claim that the 100 kΩ/22.1 kΩ nominal ratio alone proves ±5%.
