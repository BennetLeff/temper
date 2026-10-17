# Timing source

Texas Instruments, *UCC21550x 4A, 6A, Reinforced Isolation Dual-Channel Gate Driver*, SLUSE89C, Rev. C (revised August 2024), [official PDF](https://www.ti.com/lit/ds/symlink/ucc21550.pdf). Local `ucc21550-revc.pdf` SHA-256: `5f80a86ae72418d7d538067f3f0438907b9692b74554a8d7aa6866c2f6ffc7ba`.

Page 10, §5.8, “DEADTIME AND OVERLAP PROGRAMMING” gives `DT(ns) = 8.6 × RDT(kΩ) + 13`, with characterized min/typ/max of 86/99/112 ns at 10 kΩ, 167/185/203 ns at 20 kΩ, and **399/443/487 ns at 50 kΩ**. It does not tabulate 39 kΩ or 51 kΩ. The C1 six timing values use the formula for nominal and **ASSUME** that the 50 kΩ min/typ/max ratios transfer to 39 kΩ and 51 kΩ. This is an extrapolation, not a specified bound. Resistor tolerance and controller-imposed dead time are separate from this six-point sweep.

Page 33, §8.2.2.8 warns that driver-output dead time differs from power-stage effective dead time due to external gate resistors, switching voltage/current, and transistor input capacitance. C1 uses the A1 MOSFET/driver approximation and evaluates the die waveform rather than subtracting a fixed turn-off delay.
