# Acceptance status

Source-build-18 compiles as a 53-component active-PFC candidate targeting 120 VAC / 1,800 W nominal input, 15 A RMS, PF 0.99, and 389.615 V bus.

The candidate is unrouted and not accepted. Native ERC/DRC, schematic parity, ampacity, inrush, ripple, thermal, EMI, isolation, active discharge timing, and low-line RMS foldback remain unproven. AUX, CONTROL, and PERMIT interfaces are HOT bus-minus referenced and require external isolated bias/sequencing; they are not MCU or SELV interfaces. Default permit state is off.
