# Standalone current-sense interface

This board senses alternating primary current and asserts an active-high overcurrent signal for either polarity. It contains the transformer, floating burden, bias/filter network, two comparators and an OR gate. It does not contain the host latch, gate shutdown, power stage or firmware. Build and qualify this unit separately before cooker integration.

| Interface | Native pin | Net / role |
|---|---|---|
| Primary input | J1.1 | PRIMARY_IN → T1.1 |
| Primary output | J1.2 | PRIMARY_OUT → T1.2 |
| Host supply | J2.1 | +3V3, nominal 3.3 V ±5% |
| Host return | J2.2 | gnd, isolated low-voltage domain |
| Host fault | J2.3 | OCP_FAULT, active high; output of U3.9 |
| Analog monitor | J2.4 | SENSE_MON, biased bipolar current waveform |

J1 consists of bare solder lands, not a purchased or rated connector. The 8 mm wide primary tracks and 70 µm copper are an authored prototype construction, not evidence of continuous-current or termination qualification. J2 is JST B4B-XH-A(LF)(SN). Pin numbers in the native board, rather than viewing direction, govern cable construction.

T1.3 (CT_SENSE) and T1.4 (VBIAS) have the 1.50 Ω burden and 100 nF C0G capacitor in parallel. VBIAS comes from a separately bypassed 1 kΩ / 1 kΩ divider. R4 is the 1 kΩ series input resistor. Do not connect the burden's VBIAS end directly to ground or hang the bias divider across the burden; either change invalidates the model and topology checks.

The model assumes a host monitor resistance of at least 10 MΩ and bounded loading. A direct MCU ADC sampling input is not automatically equivalent to this load. Qualify its input capacitance, acquisition transients and common-mode range before connection. The host must inhibit the power stage during rail/bias startup, loss of power and unqualified conditions; this board alone is not a fail-safe shutdown chain.

Current cooker operation is approximately 44–50 kHz, with a 47 kHz nominal point. The model's wider 20–100 kHz analysis envelope is not a claim about the firmware's operating range. The system requirement is 45–55 A peak trip and a complete shutdown response under 1 µs. A conditional DC corner calculation does not establish either requirement over all operating conditions.

## Independent unit qualification

1. Inspect part identities, transformer pin orientation, burden continuity and domain separation against the native schematic and frozen manifest.
2. With no primary excitation, power only the isolated low-voltage side from a current-limited 3.3 V supply. Record VBIAS, both reference voltages, SENSE_MON and FAULT. Set the current limit from the assembled component budget before applying power.
3. Use a separately reviewed isolated low-energy AC current-injection fixture. Verify polarity, gain, waveform and both fault crossings across the actual operating frequencies. Retain stimulus, loading, probe configuration and uncertainty.
4. Characterize startup/brownout, clamp leakage versus temperature, comparator hysteresis/offset, transformer transfer and the complete comparator → OR → host shutdown path. Specify overdrive and load for timing measurements.
5. Qualify primary copper, solder/busbar construction, transformer temperature and insulation for the eventual operating environment before any cooker connection.

All physical steps are NOT RUN. There is no assembled hardware or approved energized-power test procedure in this deliverable.
