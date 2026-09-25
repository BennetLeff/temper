# DIODE-SHORT post-capture electrical interpretation

This review covers the completed `full-DIODE-SHORT` capture only. It does not
accept the case, alter checker criteria, read raw/FIFO data, or make a
hardware claim.

The capture retained 32,309,024 rows through 0.662 s and all pipeline exits
were zero. That transport success does not overcome the validator result:
`Fail("no detector fault rising edge in event window")`. The declared fault
mutation is 0.6541666666667 s; the observed injection was
0.6541666661706754 s, while the adapter's detector rise was
0.65728792700183 s. The 3.121260831 ms separation exceeds the declared 2 ms
event window. This is a detector timing/event-contract failure and must remain
separate from the waveform observations.

The adapter recorded a sampled `latch_off_s` at 0.6572886916667 s. Its latch
field means the first retained row after a detected fault where
`q <= 2.5 V`, `en <= 2.5 V`, and `abs(gate) <= 0.20 V`; it is not an
independent hardware latch witness. Channel peak was 354.14 A after injection
and 231.16 A after the observed detector edge, with the last sample above
0.10 A at 0.6572882374739012 s. The reported post-latch channel peak was
approximately 1.43e-10 A with no above-threshold post-latch timestamp. These
are adapter summaries conditioned on a detector edge that arrived outside the
declared event window, so they cannot establish protection acceptance or
continuous current cessation.

The large `dboost1_branch_peak_after_injection_a` value (326,500.48 A) is a
modeled branch-current result, not a diode-die current. In the exact deck,
`Dboost1` connects `sw` to `d1_path`; the zero-volt `Vdboost1sense` source
forces `d1_path == vd`; and `Sdiodeshort` connects `sw` to `d1_path` through
an idealized 1 mOhm switch. The sense-source current therefore includes the
terminal/KCL current of the shorted ideal network and can contain very large
circulating or constrained-source current. It cannot be interpreted as A1
current, package current sharing, thermal stress, SOA, or a physical
short-circuit current. The second modeled branch (`dboost2_branch_peak` about
9.10 kA) has the same non-physical die-allocation limitation.

Other adapter peaks—body 162.05 A, boost inductor 78.52 A, and F2 branch
229.13 A—are likewise model currents for this idealized graph. F2 is held
closed at constant 5 V in the deck; no F2 opening or clearing occurred in the
stimulus. The result remains a graph experiment with a failed event-window
contract, not a claim about a physical component or protection behavior.

The exact prepared source is bound by case SHA-256
`d5a78e2c878447110a13c54cc3052b3dff7e862dc3e79a5fbd8e973257ac5f78` and
manifest SHA-256
`fd5c7f9e9703a5d0004bcd523798644068d0b378081361580bcda5c29b67baa9`.
