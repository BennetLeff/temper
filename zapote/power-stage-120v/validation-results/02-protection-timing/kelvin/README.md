# Kelvin-return error at the shunt-OCP threshold (native-20)

**Answer:** the HOT-side supply current returning on `ocp_kelvin_p` raises the
threshold divider's ground (R35.2) by up to **2.13 mV** above the shunt's sense
terminal (R5.2). That lowers the trip by up to **2.19 A**, so the native-20 band
becomes **47.54–97.98 A**. It still meets the ≥ 44 A minimum, with 3.5 A to
spare. (The old 10.5 kΩ R34 would have fallen to about 36.3 A.)

- [`kelvin_plane.py`](kelvin_plane.py) solves the whole net (tracks, vias,
  pads and the In1 zone fill) with the committed kit sheet solver at 125 °C. It
  uses the committed native-19 copper export, which is copper-identical to
  native-20. It injects 1 A at R35.2 with R5.2 as the sink. By reciprocity, each
  pad's potential is then the mΩ that current returned at that pad raises at
  R35.2 ([plane-native20.json](plane-native20.json)). Every pad sits 93–125 mΩ
  above R5.2, and about 90 mΩ of that is the **single shared lead from R5.2 to
  the HOT island**.
- [`kelvin_budget.py`](kelvin_budget.py) is the census of currents returned at
  each pad, at datasheet maxima with HOT5 = 5.25 V. It totals 21.1 mA, dominated
  by the AMC1311 (9.7 mA), the MC78L05 ground pin (7.6 mA) and the ISO7710
  (2.4 mA). The table is in [budget-native20.md](budget-native20.md). Charging
  every milliamp at the largest transfer gives a 2.71 A bound.
- Sensitivity: trip = [2.5 + e_ref − 2 e_th − 2k(2.5 + e_ref − e_th)]/Rs, so
  dI/de_th = −1.03 A/mV and dI/de_ref = +0.03 A/mV.
- [`kelvin_track_bound.py`](kelvin_track_bound.py) is an independent check with
  KiCad's Python. A network of tracks and vias only (plane omitted, 50 µm
  copper) gives 156 mΩ for R35.2. By Rayleigh monotonicity that is an upper
  bound, and it is consistent with 125 mΩ once the plane is included.

**Layout guidance for the enclosure-driven re-layout:** the error is set by the
R5.2 → HOT-island lead. Halving that lead's resistance (wider, or paralleled on
two layers) halves the shift. Alternatively, return the AMC1311, the LDO and the
ISO7710 to R5.2 on a path separate from the threshold divider and reference. A
star at R5.2 would remove most of the shift. Re-run both scripts on any new
board export.

Limits: DC only. The OCP node's 0.5 µs RC filters supply ripple, but transient
return currents are not bounded here. Copper thickness is the kit's 70/61 µm
(the stackup specifies 2 oz), and pads are injected at their centres.
