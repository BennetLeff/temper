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
