# Source and assumption ledger — 2026-10-04

| Source | What it supports | What it does not establish |
|---|---|---|
| Frozen R2 source at `badce74c44a598da4096dffe2e1f7fe4f779bc5d` | Existing CAD, contact force CSV, material proxies, M222/copper candidates and prior measurements of model geometry | Physical performance or qualification |
| [Omega single-wire sheet](https://assets.dwyeromega.com/spec/OE_DS-TFIR-CH-CI-CC-CY-AL.pdf) | TFCP-003 copper and TFCC-003 constantan,40AWG/Ø0.08 mm, PFA insulation wall0.076 mm, spool ordering suffix | Hot material curves, installed thermal conductance, bond compatibility or stock commitment |
| [Omega insulation guide](https://www.dwyeromega.com/en-us/resources/thermocouple-wire) | PFA temperature range to260°C for specified constructions; thermocouple alloy/insulation distinctions | Lifetime of the proposed anchored jacket or completed250°C cartridge |
| [Keithley low-level handbook](https://www.tek.com/en/documents/product-article/keithley-low-level-measurements-handbook---7th-edition) | Thermoelectric errors, four-wire resistance measurement, current reversal and limitations when offsets change during the cycle | Reversal support in existing Temper electronics, immunity to induction pickup or a measured Seebeck coefficient for the proposed welds |
| [ADI excitation techniques](https://www.analog.com/en/resources/analog-dialogue/articles/transducer-sensor-excitation-and-measurement-techniques.html) | Reversed RTD excitation can remove stable DC offsets; excitation also causes self-heating | A completed bidirectional frontend design here |
| [NASA thermal-control guide](https://ntrs.nasa.gov/api/citations/20230013900/downloads/NASA%20Thermal%20Control%20Engineering%20Guidebook%20v4.pdf) | Contact conductance depends on pressure, surfaces, flatness, gas and interface construction | Any numerical cookware conductance or appliance certification limit |
| [IST RTD application note](https://www.ist-ag.com/sites/default/files/downloads/ATP_E.pdf) | Sensor response depends on thermal contact and installation; mounting can alter accuracy and material compatibility | That a catalog response time transfers to this cartridge |

All calculations are Rust-owned. Python generates/checks CAD and renders recorded results. CAD overlap0.720 mm² and anchor-pad volume0.565360 mm³ are geometric outputs, not experimental measurements.

Inherited proxy values:316L k15 W/mK and Cv4 MJ/m³K; copper k401, resistivity1.69e−8Ωm; constantan k19.5, resistivity4.9e−7; nickel k90.9; chip Cv3.12 MJ/m³K; bond k2.163418635 and Cv2 MJ/m³K; PFA k0.25 as an assumption. Refer to [R2 sources](../revision2/bond_leads/SOURCES.md) for their manufacturer provenance and qualification limits.

New explicit hypotheses: k_air0.04 W/mK; hook-gap radiation coefficient6 W/m²K; three equal straight-path steel hook resistances of length3.6 mm+clearance;0.003 W/K anchor conductance;1.2 mJ/K effective anchored wire/PFA capacity;10µm micro-gap floor in macro geometry screening. Free-wire cooling h5–15 W/m²K is a combined distributed-loss sensitivity. All gas surroundings/lead anchors use the specified body temperature, not a solved air field.

R3 keeps the existing0.00065 W/K main support link,0.26 J/K support capacity and0.001 W/K support-to-body link. Adding a resolved hook path refines that approximate model, but cannot prove how much an earlier aggregate loss parameter already represented. Anchor direct losses and hook sidewall/radiative contributions are not fully resolved. Extra seal G is a heat-loss budget only; added seal heat capacity, force, hysteresis and wetting are outside this thermal calculation and can worsen the result.

The crowned/tilted pan screen is an equal-area polar integration of dry gas conduction. It does not solve elastic contact, asperity pressure, macro deformation or boiling. Near-area fraction is a geometrical proximity measure. Its output is never substituted into the independent pressure-based contact law without calibration.

Macro-gap sign convention: pan height is bowl×(r/R)² + x×tan(tilt); cap height is crown×(1−(r/R)²). Positive bowl raises the pan edge relative to its center. The pan is translated until its minimum macro clearance is zero, then the10µm assumed roughness floor is added only for the gas-conduction integral. No elastic force equilibrium is solved by this screen.
