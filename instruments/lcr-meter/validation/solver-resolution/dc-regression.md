# True-DC regression guard

The guard parses every value, requires exactly one operating point, checks both FDA internal MID references against the DC divider equation and checks the DC-blocked source input. It does not accept ngspice exit code or transient fallback as sufficient evidence.

- `strict-good.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `100r_cap100n_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `100r_cap500n_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `100r_cap9u_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `100r_coil50u_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `5k_resistor_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V
- `100k_resistor_op.raw`: PASS MID_A=2.499998751V MID_B=2.499998751V source_AC=-1.999986731278e-7V

Negative regression: `target-base.raw` REJECTED: xa.MID=9.711286829785e-10V; expected 2.499998750001e0V; false DC state.

This preserved log says `Transient op finished successfully`; it must not be treated as a true DC operating point. Initial guesses are never accepted without checking the resulting final DC state.
