# Source04 standalone BOM

`pcb-bom.csv` contains 36 PCB components in 20 exact-MPN groups. The complete
source instance, native designator, footprint and MPN mapping is in
`source-inventory.json`; its manifest and board hashes bind this inventory to
source04. `catalog-crosswalk.json` retains matching manufacturer audit fields
with provenance. The independent grouped-BOM comparison is
`../evidence/root-source04-identity/bom-check.json`.

The source04 RREF is Susumu **RG2012V-431-W-T1**, 430 Ω, ±0.05%, ±5 ppm/°C,
0805. It replaces the historical Panasonic reference resistor. The supervisor
is **TPS389001DSER**, with the six-pin DSE custom land pattern qualified in
`../evidence/library-01/`. The additional host connector is
**FTSH-105-01-F-D**, unkeyed 2×5, 1.27 mm through-hole; mating orientation must
follow the numbered host pin contract.

The four **RC0603FR-0733RL** SPI resistors are now declared ±1%, matching the
exact MPN. The two **RC0603JR-071ML** diagnostic pullups are 1 MΩ, ±5%,
100 ppm/°C. Their loading contributes to connected-probe accuracy as well as
open-conductor timing. The 100 kΩ protected window branch also contributes
input-bias/leakage error and transient current limits.

**C0603C102J5GACTU** is the 1 nF, ±5%, C0G differential filter. The eight
**C0603C104K5RACTU** bypasses are 100 nF, ±10%, X7R, 50 V catalog parts;
the source's 10 V declaration is a minimum requirement. The analog model's
minimum effective capacitance must be retained as a procurement/assembly
acceptance condition, including bias, temperature, and aging. It is not a
measured capacitance result.

This is the PCB assembly BOM. The external PT100 probe, cable, mating contacts,
host cable and host board are interfaces, not silently included purchases.
No availability, quotation, substitute-part approval, fabrication order, or
physical assembly is claimed. Physical tests are **NOT RUN**.
