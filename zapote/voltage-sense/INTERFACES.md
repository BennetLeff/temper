# Interfaces

| Connector/pin | Net | Contract |
|---|---|---|
| J1.1 | BUS_PLUS | Positive half-bus, 170 V nominal, 0–250 V analytical envelope |
| J1.2 | BUS_RETURN | Measurement return; common with all local and host ground |
| J2.1 | +3V3 | Host supply, modeled 3.3 V ±5% |
| J2.2 | BUS_RETURN | Common return; no galvanic isolation |
| J2.3 | OVP_FAULT | TLV3201 push-pull, active high above about 200 V; low below falling threshold |
| J2.4 | BUS_MON | Analog output, nominal Vbus/91; nominal 9.89 kΩ source resistance with 100 nF filter |

J1 is Würth 691253500002, 5.08 mm two-position terminal. J2 is JST B4B-XH-A(LF)(SN), four-position 2.5 mm vertical header. Numbered pads are the wiring authority; use the native PCB to orient the mating harness.

The OVP output is a detector signal, not an implemented shutdown chain. The receiving interlock, host ADC attenuation/calibration/acquisition, power sequencing and pull states require integration work. The circuit observes only the positive half-bus; it cannot establish negative-half balance.

Do not equate BUS_RETURN with PE, mains neutral or the complete DC link's negative terminal without the integration schematic. Reconcile the doubler midpoint and return architecture explicitly. No SELV, reinforced insulation or fault-safe claim is made by this unit.
