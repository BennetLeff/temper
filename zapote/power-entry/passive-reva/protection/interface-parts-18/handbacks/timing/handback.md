# Timing/gate capacitor screen — revision 18 handback

## C3 gate capacitor (CG to HOT_GND)

Best prototype candidate: **KEMET R82DC4150AA60J**, LCSC C6262911, metallized PET stacked film, 1.5 uF +/-5%, 63 VDC, radial through-hole, 5.0 mm lead pitch, body 7.2 x 6.0 x 11.1 mm max, -55..105 C, AEC-Q200. The source table gives 160 V/us maximum dV/dt and 40 VAC rating. With no ceramic DC-bias loss, the nominal tolerance screen is 1.425..1.575 uF, inside the 1.35..1.65 uF effective target. It is a review candidate, not a production all-corner guarantee: obtain KEMET delivery specification for capacitance-vs-temperature, endurance/aging, insulation/leakage, and pulse/ripple conditions at the actual gate waveform. Verify the radial body/height and through-hole land pattern against the fixture; it is not a drop-in SMD replacement.

Alternative KEMET/film search result **C280291 / C241J155J2SC000** (Xiamen Faratronic, 1.5 uF 63 V +/-5%, -55..125 C, 5 mm pitch) is electrically plausible but has less readily attributable manufacturer evidence and should remain a backup pending its datasheet. The Jimson C434137 is rejected for the provisional -40..105 C screen because its listed upper temperature is only 85 C.

Ceramic backup: TDK **C3225X7R2A155K200AB** family (EIA 1210, 1.5 uF +/-10%, 100 V, 2.0 mm thick) is listed in the TDK mid-voltage catalog and PCBParts results (LCSC C342711 variant). It must not be accepted from nameplate value: X7R DC-bias and temperature curves at roughly 16 V, plus tolerance/aging, must demonstrate >=1.35 uF and <=1.65 uF. The 1812 TDK C4532X7R2A155K230KA family is a larger alternative with the same qualification gap. Do not promote either ceramic part until those curves are checked.

## C2 timer capacitor (TMR to HOT_GND)

Recommended prototype candidate: TDK **C3216C0G2A104J160AC** (PCBParts model C3216C0G2A104JT000E, LCSC C338111 family), EIA 1206, 100 nF +/-5%, 100 VDC, C0G 0 +/-30 ppm/C, -55..125 C, 3.2 x 1.6 x 1.6 mm, insulation resistance >=5 Gohm. The TDK characterization sheet shows essentially flat capacitance versus temperature and DC bias through the rated range. The +/-5% nameplate gives 95..105 nF before any installation/measurement allowance, inside the 90..110 nF target. The IR minimum implies <=3.2 nA leakage at 16 V (conservative); actual LT4363 timer leakage and PCB contamination still need bench verification. A tighter +/-2% Murata GRM3195C2A104GA01D (LCSC C3906406) is another candidate, but its exact datasheet and footprint should be pulled before adoption.

## Evidence limits and next action

PCBParts results establish searchable identity, package, and current indexed stock only; they are not electrical guarantees. Exact MPN selection must record the manufacturer datasheet/delivery-spec revision and verify body/land pattern, voltage waveform, leakage, and endurance. For C3, the film candidate is the cleanest way to meet effective capacitance without MLCC bias derating, but the 1.5 uF value changes the LT4363 gate ramp and requires the existing fault-peak, turn-off, stability, and SOA bench tests. For C2, use the stable C0G candidate and preserve the 120 ms service-reset timing screen until LT4363 timer-current tolerances and the measured reset waveform are closed.
