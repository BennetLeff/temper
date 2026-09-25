# Rev38 F1 inlet coordination worksheet

Status: **engineering screen, no installed fault or thermal qualification**.
Use this with [F1-SCREEN.md](F1-SCREEN.md). The proposed installation is
single-phase 108–132 Vac, 60 Hz, 15 Arms normal inlet current, a dedicated
20 A upstream branch, at most 10 kA prospective RMS symmetrical current at
the equipment inlet, and 40 °C local air at the F1 assembly. These are
review assumptions; the actual inlet, source impedance, breaker, wiring,
enclosure and product approval basis are still undefined. The PCB receives
*post-F1* L at `1714984` pin 1. The proposed `LP-CC-20`, `BCM603-1P` and
`CVR-CCM` are off-board assembly parts.

## Confirmed manufacturer boundaries

| Exact part | Published boundary | What it does not establish |
| --- | --- | --- |
| Eaton [`LP-CC-20`](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/bussmann-series-branch-circuit-fuses/class-cc/bus-ele-ds-1023-lp-cc.pdf) | 20 A Class CC time-delay, 600 Vac, 200 kA RMS symmetrical AC interruption; **12 s minimum at 200%**. The 10 kA/20 A current-limiting table gives 700 A *apparent RMS symmetrical* let-through. | No maximum 40 A clearing time, guaranteed minimum-melt I²t for start pulses, guaranteed peak or total-clearing I²t at each installed fault, or complete-assembly SCCR. Its time-current plot is average-melt, not maximum total clearing; the 700 A table entry is not a peak or an installed fault-fixture acceptance limit. |
| Eaton [`BCM603-1P` with `CVR-CCM`](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/data-sheets/bus-ele-ds-10241-bcm-bmm-blocks.pdf) | Listed Class CC block, 30 A/600 V, SCCR up to 200 kA **limited by the fuse**; LP-CC is recommended, the non-indicating cover is matched. Pressure-plate terminals accept 75/90 °C Cu AWG 10–18 at 20 lb-in (2.3 N·m). | No 200 kA rating for the inlet harness, terminal or PCB; no installed conductor, clip-temperature, cover-access or touch-temperature pass. |
| TDK [`B82726S2163N030`](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf) | 16 A at rated temperature 60 °C, 250 Vac, two windings in the common inlet path. | No 20–40 A transient withstand or fault-current bypass of either winding. The 15 A nominal operation uses 93.75% of the 16 A nameplate. |
| TE [`RT33K012`](https://www.te.com/en/product-2-1393240-3.html) | 16 A limiting continuous and breaking current, **30 A limiting making current**. It bypasses the NTC after precharge. | No automatic permission to close onto an incompletely charged bank, no 40 A fault-current withstand, and no protection against welded or stuck-open contacts. |
| Ametherm [`SL32 10015`](https://www.ametherm.com/datasheetspdf/SL3210015.pdf) | 15 A maximum steady current up to 65 °C, 10 Ω ±20% at 25 °C, 0.05 Ω and 228 °C body at 15 A, 150 J maximum recommended energy, 232 s thermal time constant. | No hot-restart current limit, permissible adjacent-material temperature, or proof that the bypass may remain open at full load. |
| Littelfuse [`V150LA10AP`](https://www.littelfuse.com/assetdocs/littelfuse-varistor-la-datasheet?assetguid=f7c547ce-c2fa-4789-86cc-ec39a5060afb) | 150 Vac maximum continuous rating; connected across fused L/N. | No assurance that a limited-current degraded MOV makes 20 A F1 open before thermal damage. |

## Fault-location and protection ownership

For each physical fault, establish *prospective current and power factor at
that location* using the chosen source, upstream breaker and installed wire
impedance. The proposed 10 kA inlet ceiling does not mean 10 kA at every PCB
node. F1's component interrupt rating does not protect the segment before
its input terminal, and its let-through is relevant only to a fault whose
current actually passes through it.

| Fault or operation location | Current path and exposed items | Devices that may act; still required |
| --- | --- | --- |
| Inlet to F1 input, or PE/chassis miswire | Inlet conductor and upstream wiring before F1 | Upstream 20 A device only. Select inlet, conductor, PE bond, strain relief and an evaluated access arrangement; record the upstream clearing envelope. |
| After F1, before or within the CMC, including MOV/X2 failure | F1, block, post-F1 harness, `1714984`, both CMC windings as appropriate; MOV is across post-F1 L/N | F1 and upstream device may both act. F2, the AUX 2 A cartridge and PFC gate shutdown do **not** clear a hard short here. Check MOV limited-current end-of-life separately. |
| Post-CMC AUX branch send/return before its 2 A cartridge | F1 and CMC, then the off-board AUX loop until its block | F1/upstream only for the pre-2 A portion. The 2 A cartridge cannot protect upstream loop wiring or the CMC. Its block and send/return polarity must be built and inspected. |
| AUX branch after its 2 A cartridge | F1, CMC, branch block/wiring, `1714971`, IRM AC input | Both Class CC cartridges may act; selectivity is **unproved**. Compare 2 A fuse minimum-melt against measured IRM start pulse, and both fuses' total-clearing limits against branch withstand. |
| Main bridge through NTC, relay open | F1, CMC, NTC, bridge and charging path | F1/upstream for hard short; a 15–20 A overload may leave F1 intact. NTC is at its 15 A steady maximum at the proposed normal-current ceiling, so require independent safe-limit evidence if bypass fails open. |
| Main bridge with relay closed or welded | F1, CMC, relay contacts, bridge and PFC | Check the relay's 16 A continuous and 30 A making limits. Gate shutdown may remove controlled PFC input but cannot clear a welded relay, failed-short switch/diode or line fault. F2 is DC-bank protection, not an AC input fuse. |

## Closure data and comparison

For every permitted line voltage, line phase and source-impedance corner,
capture inlet/F1/CMC current, AUX branch current, bridge and bank voltage,
relay-contact state, and NTC resistance/body temperature for cold start,
hot restart, retained bank charge, repeated start and relay-welded cases.
Integrate each fuse's measured `∫i²dt`; compare against **manufacturer
guaranteed minimum-melt** limits for nuisance survival at the initial fuse
temperature. Compare measured relay-closing current with the TE 30 A making
limit and NTC pulse energy/body temperature with a qualified installed limit.
Nominal bank energy alone does not supply these waveforms.

For overload and destructive fault cases, obtain the actual upstream-device
maximum clearing curve and Eaton's applicable maximum *total-clearing*
time/I²t and maximum peak let-through at the fault current and power factor.
Obtain transient withstand of the CMC windings, relay, NTC, terminal, wire,
solder joints and copper. The decision test is, for each exposed item, either
`worst protective-device clearing exposure <= proved item withstand` or a
separately evaluated safe failure result. At 40 A, Eaton's published
**minimum** 12 s delay points in the opposite direction from a clearing
guarantee. At 15–20 A, define an independent shutdown/current or thermal
limit where needed; do not rely on the nominal 20 A F1 to act.

Record the actual fuse manufacturer lot, upstream breaker model and setting,
inlet/harness wire size and insulation, block mounting/torque, enclosure
airflow, current probe bandwidth, calibrated voltage/current traces, local
temperatures, and post-test damage/access outcome. MOV abnormal-overvoltage
and short-circuit fault tests require the qualified safety fixture. Every
physical comparison here is **NOT RUN**; the digital netlist and candidate
KiCad board do not close it.
