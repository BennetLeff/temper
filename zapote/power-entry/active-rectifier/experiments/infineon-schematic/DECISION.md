# Decision

**Decision: proceed to independent placement review as an experimental
construction candidate, with bootstrap and auxiliary-rail qualification as
gates.**

This schematic removes the email dependency for a concrete alternative: a
current orderable UCC21530BQDWKRQ1 drives four IPW60R017C7 devices, while IR11688S
and the required BSP300 800 V extensions provide the low-side sensing shown in
the Infineon reference. The retained GBJ2510-F remains in parallel for the
surge path. The bridge output is `PREBOOST_POS`, preserving the existing
UCC28180/F2 boundary rather than pretending this section is the 390 V bank.

The result is not qualified construction. The selected UCC21530BQDWKRQ1 is an
active 8-V UVLO grade. The design uses IRM-10-15's published ±2.5% rail
tolerance and 200 mVpp ripple, a 1000 uF/25 V bulk capacitor plus 220 nF HF
capacitor per bootstrap, and 47 ohm recharge resistors whose pulse capability
is still unverified. The Rust periodic charge screen leaves 5.010 V above the
8-V threshold (3.810 V above the 9.2-V design floor) at the stated corner;
resistor pulse behavior, driver high-state current, ESR/bias derating, diode
recharge waveform, and hardware UVLO margin remain physical qualification
checks.

Next steps are narrow: capture the exact IR11688S/BSP300/footprint sources,
freeze the auxiliary voltage envelope, source the resistor pulse curve and
capacitor/diode corners, then place and route with output-to-output spacing
treated separately from input-output isolation. No surge, fault,
thermal, or production claim follows from this schematic/ERC result.
