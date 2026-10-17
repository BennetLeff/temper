# Standalone isolated dual gate drive

This unit is source-owned by `elec/src/gate_drive_unit.ato` and is compiled
through Atopile 0.2.69. The selected driver is TI UCC21550BDWKR, the
orderable tape-and-reel suffix for the verified DWK 14-pin package. Its
physical pins are 1–11 and 14–16; pins 12 and 13 are absent.

The control boundary is J1 (PWM_H, PWM_L, PERMIT, CTRL_GND). J2 is the one
externally provided isolated 15 V low-side supply and HV_RETURN boundary.
The high-side supply is a bootstrap from that floating rail through D1 and
C4, referenced to the high-side Kelvin return. J3 and J4 expose gate/Kelvin-
return pairs; HV_RETURN is carried by J2 and J4. Q1 (AO3400A, exact
1=G/2=S/3=D map) is the source-level PERMIT inverter, with a 100 kΩ gate
pulldown and 10 kΩ DIS pullup.
No control return is tied to HV_RETURN, and no local transformer or DC/DC is
claimed.

`source-build-09/` is the current successful source compile/export. The final
routed board is `candidate/section.kicad_pcb`, with route08, native extraction,
Rust construction checks, and native ERC/DRC receipts retained under
`evidence/`. The Edge.Cuts centreline is exactly 100 mm by 80 mm; its 0.10 mm
stroke makes the measured outer bounding box 100.10 mm by 80.10 mm. D1 is the
exact Vishay UF4007-E3/54 DO-41 through-hole
part. U1 uses a labeled, low-fidelity 14-lead DWK visualization; its physical
pins are 1–11 and 14–16. This is not a mechanical qualification model.

The validated construction contract uses one externally provided isolated
15 V low-side supply at J2 and a bootstrap high-side supply. The 39 kOhm DT
resistor is a conditional interpolation envelope, not a published TI timing
guarantee. Bootstrap startup, loaded switching, thermal behavior, and timing
measurement remain unrun.

Selected memory notes used: `rtd-mem-001`, `current-sense-mem-001`,
`voltage-sense-mem-001`, `thermal-sense-mem-001`, `thermal-sense-mem-002`,
and `interlock-mem-001`. Their procedural effect was to keep model claims
separate from physical qualification, verify exact package geometry and pin
names, preserve domain-specific returns, and read nested native ERC findings.

Source SHA-256 and compiled artifact hashes are recorded in
`source-build-09/build-receipt.json` and `evidence/native-09.json`.
