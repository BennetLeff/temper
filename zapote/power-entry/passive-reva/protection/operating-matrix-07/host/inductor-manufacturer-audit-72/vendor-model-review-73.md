# Würth LTspice model review: 760800301

The retained original `LTSpice_WE-TORPFC-rev25a.zip` contains exactly three entries: `Disclaimer_READ_ME.txt` (756 bytes), `WE-TORPFC.asy` (722 bytes), and `WE-TORPFC.lib` (3,729 bytes). The package SHA-256 is `bb43843ce5c69b99ae0f6686ad8d9467859f4075ea6a537101bd6ced903280b6`. Entries were read by exact name; nothing was executed, compiled, or simulated.

The exact 760800301 subcircuit is:

```spice
.subckt TOR75_760800301_180u 1 2
Rp 1 2 46.9k
Cp 1 2 11.58p
Rs 1 N3 18m
L1 N3 2 180u Rser = 0.00001
.ends TOR75_760800301_180u
```

This is a linear lumped equivalent: 18 mΩ series resistance, 180 µH ideal inductance with 10 µΩ `Rser`, and 46.9 kΩ/11.58 pF parallel loss/parasitic elements. It has no nonlinear DC-bias inductance, hysteresis/core-loss branch, temperature coefficients, thermal network, or saturation limit. It therefore does not model the datasheet’s current-dependent inductance or the 43 A typical saturation criterion.

The `.asy` symbol’s default `SYMATTR SpiceModel` is `TOR37_760800401_118u`, which is not the exact retained part. The symbol includes `ModelFile WE-TORPFC.lib`; exact part selection requires changing the symbol’s model attribute. This was inspected only; no model replacement was made.

Syntax is LTspice library syntax. The `.subckt`, resistor, capacitor, and inductor constructs are recognizable to ngspice, but the `Rser = ...` element parameter and complete model behavior were not tested. Compatibility is therefore “possible by inspection,” not verified.

The included disclaimer says Würth does not guarantee model error exemption or currentness and may adjust models without notice. The model is not a guaranteed substitute for the datasheet limits. In particular, it omits ±20% inductance tolerance, thermal current conditions, operating-temperature effects, and saturation behavior.
