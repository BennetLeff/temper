# Shared heatsink and interface screen

The calculated numbers are **requirements on a hypothetical isothermal 153 mm
heatsink**, not a selected part or an airflow qualification. All four
IPW65R018CFD7 packages and BR1 are assumed to deliver all modeled heat to
the sink. Lead-to-board heat and spreading resistance are omitted. The
read-only native-15 board is SHA-256
`a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
The exact arithmetic and source hashes are in `scripts/losses.py`,
`outputs/heatsink_requirement.json` and `outputs/provenance.json`.

## Interface geometry and source qualification

[Infineon Rev 2 p. 12](sources/ipw65r018cfd7.pdf) gives the PG-TO247-3
back metal E1 = 12.38–14.15 mm and D1 = 13.08–17.65 mm. I subtracted a
3.5–3.7 mm diameter mounting hole from those rectangular bounds: **151.2–240.1
mm²**. The true overlap with a die-cut pad and sink may be smaller. [Henkel's
guide](sources/henkel-tim-guide.pdf) gives the following *typical* ASTM D5470
area-normalized impedances at 50 psi, inclusive of fixture contact resistance.
Dividing by this package area is an engineering transfer estimate, not a
published TO-247 thermal resistance.

| Pad | Thickness | 50 psi impedance | Estimated TO-247 RθCS | Tab-to-PE capacitance |
| --- | ---: | ---: | ---: | ---: |
| SIL PAD 400, printed p. 63 | 0.229 mm | 1.45 °C·in²/W | 6.19 °C/W | 32–51 pF |
| SIL PAD K-10, printed p. 75 | 0.152 mm | 0.41 °C·in²/W | 1.75 °C/W | 33–52 pF |

Capacitance is ε₀εᵣA/d with εᵣ = 5.5 or 3.7 **at 1 kHz**. The range is
solely the package-area bound, not dielectric or EMI-frequency uncertainty.
A7 must sweep it; the selected pad and actual RF permittivity are still open.
The 0.229 mm SIL PAD 400 impedance is **1.45**, not the 1.13 value for the
0.178 mm variant.

For BR1, [Diodes Rev. 11 p. 2](sources/gbj2510.pdf) specifies RθJC = 1.0
°C/W **per diode element**. Its four symmetric elements each receive one
quarter of the total rectifier heat in this screen. The case-to-sink transfer
assumes the *entire* 29.7 × 19.7 mm rear outline (p. 4) makes contact, yielding
RθCS = 1.60 °C/W (400) or 0.45 °C/W (K-10). That is optimistic; the actual
metallized contact, hole and clamp geometry require measurement.

## Conditional steady requirement

The selected 120 V, 1,710 W cast-iron/high case has 21.47 A tank RMS.
Using **typical** RDS(on) linearly interpolated from Infineon's 25 °C and
150 °C points to the 125 °C design junction gives 6.78 W conduction per MOS.
Covered A1 turn-off events add 0.26 W/high-side and 0.33 W/low-side device
at the 27 °C model condition;
11/546 events fall outside its 1–37 A current grid and 262 events below
120 V use the 120 V curve. BR1 is 28.36 W under an assumed sinusoidal 15 A
RMS input and the datasheet's 1.05 V maximum **at one 12.5 A, 25 °C point**.
This is a 56.63 W **partial, optimistic** sink load, not an upper loss bound.
It excludes diode dead time/recovery, lost-ZVS turn-on, hot bridge VF and
all unmodeled switching events.

For each device, `Ts,max = 125°C − Pdevice·(RθJC+RθCS)`; for BR1 the
`RθJC` term uses *one quarter* of package power. The lower of those
temperatures limits the common sink. `RθSA ≤ (Ts,max − Tamb)/P_sink`.
Internal air at 50/65 °C and Tj ≤125 °C are design assumptions, not enclosure
measurements.

| Case | Pad | Ts,max | RθSA at 50 °C | RθSA at 65 °C |
| --- | --- | ---: | ---: | ---: |
| 120 V full-power example | SIL PAD 400 0.229 mm | 72.57 °C | ≤0.399 °C/W | ≤0.134 °C/W |
| 120 V full-power example | SIL PAD K-10 | 105.09 °C | ≤0.973 °C/W | ≤0.708 °C/W |
| 108 V low-R stress, 44.70 A RMS | SIL PAD 400 0.229 mm | −65.43 °C | **impossible, ideal sink** | **impossible** |
| 108 V low-R stress, 44.70 A RMS | SIL PAD K-10 | 65.24 °C | ≤0.104 °C/W | ≤0.002 °C/W |

The stress waveform reaches 89.8 A tank peak and would exceed the protection
threshold, so it is **not a sustainable thermal operating point**. It is
also above R5's 1 W rating if maintained. The negative/near-zero sink
resistances make the screen useful as a fault warning but not a fan target.
There is no guaranteed hot RDS(on) maximum, no qualified bridge VF curve over
the waveform, no measured contact pressure, and no full switching-loss grid;
consequently none of these four RθSA numbers is a procurement limit.

## Airflow comparison and open D2 decision

[Aavid Thermalloy extrusion 63730, Nov. 2016 p. 1–2](sources/aavid-63730.pdf)
is 76.2 mm wide and 57.15 mm high, so its profile could be cut to the
specified 153 mm length. It quotes **1.88 °C/W natural convection** at a
70 °C rise. Its forced-air graph covers 1–5 m/s but was measured with
**one centered 25.4 mm heat source at 10 W**; it is not validated for five
spread-out parts and 57 W at a specific 153 mm cut length. Natural
convection misses both nominal pad requirements. None of its airflow
points is promoted to a numerical design claim without a reproducible
digitization and transfer qualification. The actual airflow requirement is
**BLOCKED** pending a chosen 153 mm sink and its multi-source thermal curve
or an enclosure test. Convert velocity to fan flow only after duct
cross-section and bypass leakage are known.

The physical confirmation is thermocouples on BR1 case, each MOS case, sink
under each package and inlet air, plus actual line-cycle current and hot5
load at full power inside the enclosure. Compare the installed pad's clamp
pressure and dielectric response with these assumed values.
