# Coil and tank evidence — U1 in progress

The historical full-board `elec/src/main.ato` sets a 47 kHz switching point and documents dependence on a loaded inductance around 59.8 µH. Its former 150 µH free-air assumption and coupling estimate can numerically cancel to a similar loaded resonance. The project learning `docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md` shows why checking only the free-air coil value gives a misleading verdict.

| Quantity | Current status | Required evidence |
| --- | --- | --- |
| Physical cooker coil geometry and build | `CUSTOM_LITZ_COIL` is a placeholder in historical source. | Winding, material, ferrite, dimensions, resistance and thermal limits for an actual part or build drawing. |
| Unloaded inductance | Historical source and research cite differing assumed/candidate values. | Measurement versus frequency and temperature for the selected coil. |
| Loaded inductance | ~59.8–59.9 µH is a consistency calculation for two historical parameter sets, not a guaranteed cooker range. | Measurements/models across approved pan materials, sizes, positions and temperature; include no-pan state. |
| Coupling and loss | Historical coupling fits are not an accepted 20–50 kHz product envelope. | Pan-dependent loss and phase data at the intended frequency/current range. |
| Tank capacitance and stress | Historical example uses 300 nF in a resonance calculation. | Exact part tolerance, RMS/pulse current, voltage and temperature at all selected points. |
| Control frequency | Historical 47 kHz is contingent on loaded-coil assumptions. | Selected operating window, start/stop behavior, ZVS margin and controller capability on the real coil/pan envelope. |

U2 can compare a modeled candidate only after these inputs are bounded. A simulation using a labeled provisional coil can explore sensitivities but cannot accept the standalone inverter's operating range.
