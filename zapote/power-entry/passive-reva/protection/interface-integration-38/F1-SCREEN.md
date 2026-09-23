# Rev38 F1 cartridge and holder screen

Status: **no cartridge selected; fault interruption and inrush acceptance
OPEN**. This screen compares published variants at the 15 Arms requirement
and identifies the data needed to select a cartridge. A holder drawn in the
Atopile series path does not specify a fuse element.

| Pair screened | Manufacturer evidence | Candidate consequence |
| --- | --- | --- |
| Current `FUP 0031.2510` 5×20 holder + retained `FST 0034.3129` 16 A time-lag | [FUP holder](https://www.schurter.com/en/datasheet/typ_FUP.pdf) lists FST 5×20 as a reference. [FST sheet](https://www.schurter.com/en/datasheet/typ_FST_5x20.pdf) gives the 16 A link 10×In, or 160 A, at 250 VAC. | Retains the existing mechanical concept, but 160 A cannot be accepted without an installation fault-current bound. |
| Same holder + `SP 0001.1016` 16 A quick-acting | FUP lists SP 5×20 as a reference. The [exact SP variant](https://www.schurter.com/en/part/0001.1003) has 1,000 A IEC and 500 A UL breaking-capacity entries at 250 VAC (footnote 2), plus a 120 mV typical voltage drop at rated current. | A stronger screened interruption entry than FST, but quick-acting inrush survival and approval basis are unknown; 1,000 A must not be substituted for the 500 A UL entry. |
| Same holder + `SPT 0001.2516` 16 A time-lag | The [SPT 5×20 sheet](https://www.schurter.com/en/datasheet/typ_spt_5x20.pdf) gives 500 A at 250 VAC for the 16 A variant, and its corresponding-holder list omits FUP. | Do not infer an approved FUP/SPT pair from matching cartridge dimensions. The 500 A entry still needs available-fault-current evidence. |
| `FUP 0031.2520` 6.3×32 holder + `SHF 8020.5080` 16 A quick-acting | [FUP](https://www.schurter.com/en/datasheet/typ_FUP.pdf) lists SHF 6.3×32 as a reference. The [SHF 16 A row](https://www.schurter.com/en/datasheet/typ_SHF_6.3x32.pdf) lists 1,500 A at 250 VAC under footnote 3, 130 mV maximum drop at 1×In, and 760 A²s **typical** melting I²t at 10×In. | Changes the holder size and layout. The 1,500 A figure may still be below the site fault current, and a typical melting I²t is not a guaranteed inrush/coordination limit. |

The FUP holder accepts 4 W at 16 A and 23 °C, with a separate ambient
derating curve. This is a holder thermal rating, not proof of 15 Arms at
40 °C inlet inside this assembly. At 16 A, the SHF's specified 130 mV
maximum voltage drop corresponds to 2.08 W at that operating point; it
does not establish the fuse's maximum dissipation at 15 A, nor the holder's
allowable power at its actual local ambient.

## Selection inputs and stop rule

1. Specify the **maximum prospective RMS fault current** and power factor
   at the cooker inlet, including the upstream protective-device arrangement
   and wiring impedance. Compare at the applicable AC voltage and the
   particular approval/certification basis. If that current exceeds the
   cartridge's corresponding breaking capacity, reject the pair.
2. Bound normal 15 Arms current waveform and worst permitted inrush,
   precharge duration, relay failure-open, repeated starts, and ambient
   temperature. Compare the cartridge's guaranteed time/current and energy
   behavior, not its typical I²t alone, to the required no-nuisance-trip
   envelope and to F2/MOV/interconnect withstand.
3. Check holder/cartridge dimensional and approval pairing, fuse and holder
   temperatures at 40 °C inlet, conductor/trace ratings, and field
   replacement conditions. The 16 A nameplate leaves little continuous
   current margin and does not replace assembly thermal evidence.

No screened option can pass all three steps from the current inputs. Keep
the Atopile holder path a provisional topology and leave F1 unselected.
If prospective fault current exceeds the screened cartridge capacities,
revise the fuse/holder architecture or establish an appropriately reviewed
upstream protection contract; do not raise a fault-current allowance to fit
one of these parts.
