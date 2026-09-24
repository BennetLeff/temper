# Rev38 F1 cartridge and holder screen

Status: **Class CC cartridge and block nominated; PCB fused-input boundary
compiled, off-board harness and electrical acceptance OPEN**. The user
selected a general residential installation scope for review. The Rev38
Atopile PCB section no longer contains the old 5×20 holder. Its terminal
pin 1 is explicitly the **post-F1** line input; the off-board fuse/block and
inlet wiring are separate assembly work, not represented by a PCB footprint.

## Proposed residential installation envelope (review target)

- Single-phase 108–132 Vac, 60 Hz, protective earth, 15 Arms maximum normal
  input, on a dedicated 20 A branch protected by a 20 A upstream device.
  The 20 A branch is a product proposal, not an established appliance rating;
  the final plug/inlet, cord or fixed wiring, instructions, and applicable
  product standard still need review.
- Local air at the F1 assembly up to 40 °C in the installed enclosure. The
  nominal 15/20 = 75% load fraction leaves room for review, but does not
  establish fuse carry, terminal temperature, or nuisance-trip performance
  at 40 °C.
- Target a maximum 10 kA prospective RMS symmetrical fault current at the
  equipment inlet for the first product safety evaluation. Determine or bound
  the actual installation value and fault power factor. Above that target is
  outside this proposed envelope until the **whole assembly** is evaluated;
  the fuse's 200 kA interrupt rating alone does not assign a 200 kA rating
  to the cooker. Upstream-breaker selectivity is not assumed.
- The single-pole F1 is in L only. Select a polarized inlet or fixed-wiring
  arrangement that preserves L/N identity, and evaluate reversed or miswired
  connections explicitly. The present source does not show a two-pole
  disconnect or a fuse in N.

## Nominated F1 pair

| Function | Exact part | Published basis | Current decision |
| --- | --- | --- | --- |
| F1 cartridge | Eaton Bussmann [`LP-CC-20`](https://www.eaton.com/us/en-us/skuPage.LP-CC-20.html) | UL Listed/CSA Class CC, 20 A time-delay, 600 Vac, 200 kA AC interrupt rating. [Technical Data 1023](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/bussmann-series-branch-circuit-fuses/class-cc/bus-ele-ds-1023-lp-cc.pdf) specifies **at least** 12 s at 200% rated current; that point does not establish a maximum clearing time or inrush endurance for this circuit. | Preferred engineering cartridge for the proposed envelope; not released for mains build. |
| F1 mounting block | Eaton Bussmann [`BCM603-1P`](https://www.eaton.com/us/en-us/skuPage.BCM603-1P.html), with non-indicating `CVR-CCM` cover | [Technical Data 10241](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/data-sheets/bus-ele-ds-10241-bcm-bmm-blocks.pdf) explicitly lists LP-CC as a recommended Class CC fuse, 30 A/600 V block rating, SCCR up to 200 kA limited by the fuse, pressure-plate terminals, and optional cover. | Exact block and cover nominated. It mounts off the PCB; the inlet harness, mounting, access and segregation design remain open. |

The Class CC rejection interface helps prevent insertion of lower-rated
supplemental cartridges. The 20 A fuse is intended to protect the inlet path
against faults, not to serve as a 15 A electronic current limiter. The
block's 30 A rating and 200 kA SCCR are component ratings. Qualification must
cover incoming wiring before F1, block and terminal torque, internal
connections to the PCB, enclosure access, and the 15 Arms/40 °C temperature
rise. The 20 A upstream device and 20 A F1 are not a selective pair by
assumption. F2, MOV, CMC, relay, NTC, traces, and other downstream components
need their own withstand or coordinated-clearing evidence. In particular,
the retained CMC and relay contact are rated 16 A and the NTC is rated 15 A
in steady state. A sustained 15–20 A overload, especially with the bypass
relay stuck open, is not shown to clear by a 20 A fuse. That fault needs an
independent current/temperature limit or an evaluated protective response.

### Continuous-current decision for the nominated 20 A cartridge

The rating margins below use the proposed **15 Arms maximum normal inlet
current**, not a measured load profile. They are arithmetic screens only;
ambient conditions, waveform and device heating still have to be qualified.

| Part in the line path | Published continuous rating | 15 Arms as a share of that rating | Decision consequence |
| --- | --- | --- | --- |
| `LP-CC-20` | [20 A](https://www.eaton.com/us/en-us/skuPage.LP-CC-20.html) | 75% | Candidate size for no-nuisance operation; 40 °C installed fuse/clip temperature and start cycles remain unproved. |
| `BCM603-1P` pressure-plate block | [30 A](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/data-sheets/bus-ele-ds-10241-bcm-bmm-blocks.pdf) | 50% | Block rating does not cover the selected wire, terminal or enclosure thermal path. |
| TDK `B82726S2163N030` CMC | [16 A at its 60 °C rated temperature](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf) | 93.75% | Little nominal current headroom; verify winding/housing temperature and fault survival. |
| TE `RT33K012` bypass contact | [16 A limiting continuous contact current](https://www.te.com/en/product-2-1393240-3.html) | 93.75% | Verify actual contact duty, relay state and make/break heating. |
| Ametherm `SL32 10015` before bypass | [15 A maximum steady current up to 65 °C](https://www.ametherm.com/datasheetspdf/SL3210015.pdf) | 100% | A stuck-open bypass leaves no current-rating margin and makes installed body/adjacent-material temperature decisive. |

**Choice at this gate:** retain `LP-CC-20` only as an engineering candidate
while obtaining an independent overload limit or demonstrated safe response
for the CMC, relay and NTC, including bypass faults. A smaller fuse would
change no-nuisance and inrush behavior and cannot be adopted merely because
its nameplate is closer to 15 A. A larger downstream part likewise requires
new startup and fault qualification. None of these changes can be inferred
from the present component ratings.

The slow-overload region is a specific **part-coordination mismatch to
close**, not a marginal derating question. Eaton guarantees the `LP-CC-20`
will remain intact for **at least 12 seconds at 40 A** (200% of its rating);
its published curves are average-melt curves, not maximum total-clearing
times. The actual CMC is TDK `B82726S2163N030`, rated [16 A at its 60 °C
rated temperature](https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s2163.pdf).
The bypass relay is TE `RT33K012`, with a [16 A limiting continuous contact
current](https://www.te.com/en/product-2-1393240-3.html), and the NTC is
Ametherm `SL32 10015`, with a [15 A maximum steady current up to
65 °C](https://www.ametherm.com/datasheetspdf/SL3210015.pdf). Those ratings
do not specify survival at 40 A for 12 seconds. If the upstream breaker does
not open sooner, F1 cannot be credited with limiting that exposure. A fault
that leaves the bypass relay open forces the NTC to carry the full line
current; the manufacturer also lists 228 °C body temperature at 15 A. Obtain
transient withstand or demonstrate another independently evaluated clearing
or current-limiting path for each affected element. Do not infer that the
PFC's gate shutdown removes a hard AC-line, MOV, or CMC fault.

**PCB source boundary now compiled:** `elec/src/ac_input.ato` assigns
`1714984` pin 1 to `FUSED_L`, pin 2 to N, and pin 3 to PE. `FUSED_L` feeds
CMC line input, X2, and MOV directly; there is no board-mounted holder or
unfused-line net in this module. The 12-part board section and its joined
route pass the exact-pin audit, including a mutation that disconnects fused
L at pin 1. This establishes only the PCB-side interface.

**Proposed off-board assembly, not yet installed or native-verified:**

| Conductor segment | Proposed physical connection | Open evidence |
| --- | --- | --- |
| Unfused L | Equipment line inlet → `BCM603-1P` input pressure-plate terminal | Inlet/cord or fixed-wiring selection, conductor gauge, protection before F1, routing and strain relief. |
| Fused L | `BCM603-1P` output terminal, with `LP-CC-20` installed and `CVR-CCM` cover → `1714984` PCB pin 1 | Block mounting, terminal torque, accessible replacement policy, fuse presence, wire/PCB terminal temperature and fault withstand. |
| N | Equipment neutral inlet → `1714984` PCB pin 2 | Wiring and terminal ratings; no fuse or switch is drawn in this segment. |
| PE | Equipment protective-earth inlet → `1714984` PCB pin 3 and independently qualified chassis bond | Earth continuity, bond construction and Y1 leakage. The Y1 capacitor is not the chassis bond. |

The off-board block, cartridge and cover are separate BOM/assembly items.
There is no assigned PCB footprint for them, and the Atopile PCB netlist
cannot prove that a cartridge is installed or that the inlet harness follows
this table. Keep that evidence OPEN through native and assembly review. The
5×20 options below remain a historical rejection record.

The [AUX source decision](AUX-SOURCE-CANDIDATE.md) now nominates a separate
off-board `LP-CC-2`/`BCM603-1P`/`CVR-CCM` branch loop after the board CMC.
Its proposed `1714971` send and return pins must not be bridged on copper.
The terminal and IRM-20-24 raw-source pins are now in the joined netlist,
and the audit rejects a copper bridge or direct pre-fuse feed; the fuse and
wiring remain off-board and unbuilt.
This branch is a second assembly fuse, not a substitute for F1. Its 20 A
published IRM cold-start inrush lacks
duration/I²t evidence for the 2 A cartridge; add its waveform, selectivity
and fault withstand to the qualification records below.

## Published limits and their application boundary

| Item | Manufacturer evidence | Rev38 interpretation |
| --- | --- | --- |
| Block wiring | [Eaton Technical Data 10241](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/data-sheets/bus-ele-ds-10241-bcm-bmm-blocks.pdf) lists the `BCM603-1P` pressure plate for 75/90 °C copper AWG 10–18, tightened to 20 lb-in (2.3 N·m). Its non-indicating `CVR-CCM` cover is the listed match; the block and cover operating range is −40 to +120 °C. | Select the actual conductor size and insulation temperature against the product wiring and 20 A protection requirements. Record torque and strain relief. The +120 °C component limit is not an acceptable enclosure or touch temperature by itself. |
| PCB terminal | [Phoenix Contact 1714984](https://www.phoenixcontact.com/en-gb/products/printed-circuit-board-terminal-mkds-5-3-95-1714984) lists 0.2–4 mm² flexible wire and a separate AWG 24–10 range, 8 mm strip and 0.5–0.6 N·m torque. Its cULus recognition lists **300 V/30 A** for B/C use and **600 V/5 A** for D use; the separate IEC nominal entry is 32 A. Phoenix says to support this three-position terminal while tightening, because each contact has one solder pin. | The proposed 132 Vac/15 Arms use may fit the published B/C entry, but the required approval category, exact wire/termination, solder joint, copper and enclosure temperature must be decided for the end product. Do not use the 32 A IEC number as a blanket cULus 600 V/32 A approval. |
| Fuse fault-current data | [Eaton Technical Data 1023](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/bussmann-series-branch-circuit-fuses/class-cc/bus-ele-ds-1023-lp-cc.pdf) rates `LP-CC-20` at 200 kA RMS symmetrical AC interruption. Its current-limiting table gives **700 A apparent RMS symmetrical let-through** for a 20 A fuse at 10 kA prospective; the plotted time/current curves are **average melt**. | The 700 A figure is neither a peak-current limit nor a total-clearing I²t or clearing-time guarantee. Obtain the fault-specific peak and total-clearing data, then evaluate the wiring, terminal, PCB copper, MOV, CMC and bridge. The 200 kA fuse and block ratings do not transfer to the complete cooker. |
| Inrush limiter | [Ametherm `SL32 10015`](https://www.ametherm.com/datasheets/sl3210015) lists 10 Ω ±20% at 25 °C, 0.05 Ω and **228 °C body temperature** at its 15 A maximum steady current, 150 J maximum recommended energy and a 232 s thermal time constant. | A cold-start calculation cannot cover a hot restart: the thermistor may have little limiting resistance. Its 15 A rating equals the required input current if the bypass relay remains open. Treat stuck-open bypass at full input as a critical installed thermal case; measure NTC and adjacent-material temperatures, relay-open duty and repeated starts before setting a retry/cooldown policy. |
| MOV | [Littelfuse `V150LA10AP`](https://www.littelfuse.com/assetdocs/littelfuse-varistor-la-datasheet?assetguid=f7c547ce-c2fa-4789-86cc-ec39a5060afb) lists 150 Vac maximum continuous voltage and 45 J for a 10×1000 µs transient. [Littelfuse's AC-line application note](https://www.littelfuse.com/~/media/electronics_technical/application_notes/varistors/littelfuse_designing_with_thermally_protected_tmov_varistors_in_spd_and_ac_line_application_note.pdf) explains that sustained abnormal overvoltage at limited current can overheat an ordinary MOV without opening a line fuse. | 132 Vac lies below the continuous nameplate, but 45 J is a specified pulse rating, not an abnormal-overvoltage or end-of-life clearance. Evaluate thermal disconnection or another demonstrated safe failure path; do not assume the 20 A F1 clears every MOV failure. |

The compiled **VB bank** is four 560 µF capacitors, or 2,240 µF nominal.
A **separate 22 µF local film reservoir on VD** sits across F2 from that
bank. Their nominal sum is 2,262 µF only when evaluating a path that charges
both sides with F2 closed. If both start at zero and only reach the 132 Vac
crest, `½ C V²` for that conditional sum is about 39.4 J. This is a
**calculation**, not measured NTC absorption: it omits capacitor tolerances,
F2 state, source/inductor/diode dynamics, the 400 V boost trajectory, charge
retained across retries, and energy delivered after the relay closes. The
Ametherm 150 J entry cannot release the precharge design on this calculation
alone.

## Fault location and coordination matrix

Use the installed inlet, two fuse blocks, PCB terminals, wiring, and final
board for these reviews. The proposed 10 kA limit is at the **equipment
inlet**; record the lower or higher prospective current at each fault
location after actual cable and source impedance. `F2` is on the DC bank
path and cannot be credited for an AC input or MOV fault. The separate 2 A
AUX cartridge lies **after** the CMC; it cannot protect an upstream CMC
fault or the unfused portion of its own send/return harness.

| Case and current region | Components exposed and required evidence | Release criterion | State |
| --- | --- | --- | --- |
| Inlet assembly, normal and reversed/miswired L/N | Confirm exact polarized inlet or fixed-wiring connections, pre-F1 line routing, strain relief, PE-to-chassis bond and continuity, three-position PCB terminal conductor size/strip/torque, both fuse-block pressure-plate torques, cover retention and access. | The final assembly preserves the defined line-only fuse path, maintains protective earth under the applicable mechanical/electrical tests, and cannot expose an energized replaceable cartridge under the approved access procedure. | NOT RUN |
| Sustained 15 Arms at 108 and 132 Vac, 40 °C inlet local air | Record true-RMS and crest factor at the inlet, both CMC windings, relay contact when bypassed, F1 clips/cover, wires and PCB input solder joints. Measure each component's **own** local air and body temperature after equilibrium, including AUX running. | Each exact part, termination, wire, copper path and adjacent material remains within its applicable installed rating and end-product temperature limit. F1 neither opens nor degrades. | NOT RUN |
| 15–20 A sustained overload; bypass both normal and stuck open | Sweep the current region where F1 is at or below its nominal rating and obtain upstream-device time/current limits. Measure CMC, relay and NTC temperatures and any independent overload shutdown response. | No component relies on F1 opening in this region; a documented current limiter or shutdown keeps all temperatures and durations within proven limits. | NOT RUN |
| 20–40 A abnormal load, including 40 A for 12 s | Obtain Eaton **maximum total-clearing** time and its tolerance at the actual ambient, plus upstream breaker limits. Obtain CMC, relay and NTC transient thermal withstand. Evaluate relay-open and relay-welded states separately. | The fastest credible independent protection clears before the weakest component's proved transient limit, or the components survive the worst combined clearing envelope. Eaton's 12 s minimum at 40 A cannot be used as a clearing guarantee. | NOT RUN |
| Cold start, hot restart, retained bank charge, relay welded closed, and AUX module startup | Capture inlet and F1 current versus time, line phase, source impedance, capacitor voltage, NTC resistance/temperature, relay position, and AUX branch current. Integrate **measured** F1 and AUX-cartridge I²t and compare with manufacturer-provided minimum-melt bounds at the initial fuse temperature. | No nuisance opening under the permitted start/retry sequence; NTC energy, peak, temperature and relay make current stay within proven limits. Set the retry and precharge timeout from the worst measured case. | NOT RUN |
| Line–neutral or line–PE short at each inlet and PCB segment, through 10 kA inlet prospective | Map fault points before F1, after F1/before CMC, after CMC/before AUX 2 A branch fuse, after AUX fuse, and after the bypass/rectifier. Obtain `LP-CC-20` and upstream peak let-through, total-clearing I²t and time at each prospective current and power factor; include F1 and 2 A fuse selectivity where both carry the fault. | The inlet wiring before F1 has its own upstream protection; every downstream terminal, wire, copper section and component withstands the actual clearing envelope without an unsafe outcome. Do not transfer the fuse/block's 200 kA component ratings to the assembly. | NOT RUN |
| MOV degradation or abnormal overvoltage, including limited-current thermal runaway | Test the retained non-thermally-protected `V150LA10AP` with the final enclosure and any proposed thermal disconnect. Include faults that draw too little current to open a 20 A fuse and locate the disconnect relative to the MOV. | Demonstrated safe end-of-life response at the specified abnormal voltage and source impedance; F1 only credited where its measured/guaranteed clearing actually applies. | NOT RUN |
| F2 bank or boost fault and AUX branch fault | Carry the F1 waveform and common CMC/PCB exposure into the F2 and AUX qualification. Treat F2's DC bank cartridge and the AUX 2 A cartridge as separate protection with separate clearing data. | Proven coordination for all shared upstream elements; no assumed selectivity between F1, F2, AUX fuse and the upstream 20 A device. | NOT RUN |

Before an energized qualification, freeze the inlet/cord or fixed-wiring
parts, wire gauge and insulation, block mounts and cover access, fuse
replacement procedure, PCB terminal termination, enclosure airflow, and
upstream breaker model. Record instrument bandwidth and calibration for
peak-current/I²t captures. Do not turn the nominal 75% loading fraction or
the 700 A apparent-RMS 10 kA let-through table entry into a thermal or
peak-current pass.

Request the following exact data from Eaton or generate it with the qualified
fault fixture before making a coordination verdict: `LP-CC-20` minimum-melt
and **maximum total-clearing** envelopes versus current, initial fuse
temperature and power factor; peak let-through and total-clearing I²t at
each actual prospective current; and repeated-pulse no-opening limits for
the measured cold/hot-restart waveform. The published 12-second minimum at
40 A and average-melt curves provide none of those upper bounds. Obtain the
upstream **specific 20 A device** clearing envelope on the same basis and
compare both devices at each fault location, including impedances that put
the fault in the slow-overload region. Do not label either device
"selective" without that comparison.

For each matrix row, keep the exact sample and revision identity, fixture,
source voltage/impedance and prospective current, component initial
temperature, upstream device, waveforms, calibrated instrument settings,
measured peaks/I²t, thermal locations, acceptance limits, and outcome.
Only a qualified electrical-safety lab should run destructive fault and MOV
end-of-life tests. Every matrix row remains **NOT RUN**; the table is a
qualification specification, not an assembly acceptance claim.

## Previous 5×20 and 6.3×32 screen

| Pair screened | Manufacturer evidence | Candidate consequence |
| --- | --- | --- |
| Former Rev38 `FUP 0031.2510` 5×20 holder + retained `FST 0034.3129` 16 A time-lag | [FUP holder](https://www.schurter.com/en/datasheet/typ_FUP.pdf) lists FST 5×20 as a reference. [FST sheet](https://www.schurter.com/en/datasheet/typ_FST_5x20.pdf) gives the 16 A link 10×In, or 160 A, at 250 VAC. | Retains the existing mechanical concept, but 160 A cannot be accepted without an installation fault-current bound. |
| Same holder + `SP 0001.1016` 16 A quick-acting | FUP lists SP 5×20 as a reference. The [SP data-sheet row for 0001.1016](https://www.schurter.com/en/datasheet/typ_sp_5x20.pdf) has 1,000 A IEC and 500 A UL breaking-capacity entries at 250 VAC (footnote 2), plus a 120 mV typical voltage drop at rated current. | A stronger screened interruption entry than FST, but quick-acting inrush survival and approval basis are unknown; 1,000 A must not be substituted for the 500 A UL entry. |
| Same holder + `SPT 0001.2516` 16 A time-lag | The [SPT 5×20 sheet](https://www.schurter.com/en/datasheet/typ_spt_5x20.pdf) gives 500 A at 250 VAC for the 16 A variant, and its corresponding-holder list omits FUP. | Do not infer an approved FUP/SPT pair from matching cartridge dimensions. The 500 A entry still needs available-fault-current evidence. |
| `FUP 0031.2520` 6.3×32 holder + `SHF 8020.5080` 16 A quick-acting | [FUP](https://www.schurter.com/en/datasheet/typ_FUP.pdf) lists SHF 6.3×32 as a reference. The [SHF 16 A row](https://www.schurter.com/en/datasheet/typ_SHF_6.3x32.pdf) lists 1,500 A at 250 VAC under footnote 3, 130 mV maximum drop at 1×In, and 760 A²s **typical** melting I²t at 10×In. | Changes the holder size and layout. The 1,500 A figure may still be below the site fault current, and a typical melting I²t is not a guaranteed inrush/coordination limit. |

The FUP holder accepts 4 W at 16 A and 23 °C, with a separate ambient
derating curve. This is a holder thermal rating, not proof of 15 Arms at
40 °C inlet inside this assembly. At 16 A, the SHF's specified 130 mV
maximum voltage drop corresponds to 2.08 W at that operating point; it
does not establish the fuse's maximum dissipation at 15 A, nor the holder's
allowable power at its actual local ambient.

## Selection inputs and stop rule

1. Confirm the proposed dedicated-20 A/10 kA installation envelope, actual
   prospective RMS fault current and power factor, upstream device, and
   applicable product standard. Compare the complete assembly's withstand
   and clearing path against it. If the installation exceeds the evaluated
   envelope, reject the installation or revise the architecture.
2. Bound normal 15 Arms current waveform and worst permitted inrush,
   precharge duration, relay failure-open, repeated starts, and ambient
   temperature. Compare the cartridge's guaranteed time/current and energy
   behavior, not its typical I²t alone, to the required no-nuisance-trip
   envelope and to F2/MOV/interconnect withstand.
3. Check holder/cartridge dimensional and approval pairing, fuse and holder
   temperatures at 40 °C inlet, conductor/trace ratings, and field
   replacement conditions. Nominal ratings do not replace assembly thermal
   evidence. Include
   sustained overloads below the proposed 20 A F1 rating and the relay-open
   NTC path.

The LP-CC-20/BCM603-1P nomination addresses part identity and published
interrupt/block ratings only. It does not pass steps 1–3 yet. The compiled
board boundary is fused L, but the external harness, whole-assembly fault
rating and thermal coordination remain open before any mains build.
