# F6 / AOE-29: CMTI table for every isolation crossing

Desk calculation. Rerun: `python3 -I validation-results/06-controller-interface/cmti/cmti_table.py`
(from `zapote/power-stage-120v`). It reads the crossing counts and the monitor filter R/C from
`elec/src/*.ato`, prints PASS / FAIL / OPEN per row, rewrites `cmti.csv`, and exits non-zero if the
control row stops failing. No PDFs are stored; the datasheets were read in a scratch directory.

Rule (RESOLUTION-PLAN F6): CMTI >= 1.5 x dv/dt for every crossing whose upset gives a gate command (95 V/ns
hard -> 142.5 kV/us); time-filtered crossings (>= 10 us) may pass on the filter. dv/dt: 10 V/ns ZVS, up to
95 V/ns hard edges S4/S5 (ALT-BIAS.md R10 line 49; native-21/ECO.md:72; 01-switching-parasitics/FINDINGS.md F2/F11).
1 V/ns = 1 kV/us. The 95 V/ns is a model figure, not a measurement. Where a crossing is not on a switch node
(LS monitor, bus-fault isolator, AMC1311) the 95 V/ns is applied anyway as a conservative bound.

## Result

| Ref | MPN | Straddles | Datasheet CMTI (page) | hard x | ZVS x | Upset does | Verdict |
|---|---|---|---|---|---|---|---|
| U1, U2 | UCC21550BDWKR | SW_A / SW_B | 125 V/ns min, VCM 1500 V (SLUSE89C p.10 Table 5.9 \|CMH\|,\|CML\|; p.1) | 1.32 | 12.5 | **false gate command** on INA/INB | **FAIL** (needs 142.5) |
| U32, U33, U34 | ISO7710DWR | N_LS, SW_A, SW_B | 85 min / 100 typ kV/us, VCM 1200 V (SLLSER9E p.11, p.12) | 0.89 | 8.5 | HIGH glitch -> BIAS_BAD -> DIS (off, safe) via 10k x 1nF | PASS on filter |
| U9 | ISO7710DWR | OCP_KELVIN_P | same | 0.89 | 8.5 | BUS_FAULT to J4, unfiltered on board; false HIGH = nuisance trip | OPEN |
| U4 | AMC1311BDWVR | OCP_KELVIN_P | 100 min / 150 typ, B grade (SBAS786C p.10 Table 7.9; p.4) | 1.05 | 10.0 | spurious VBUS sample, no gate command | OPEN |
| U36 | VOL628A-3X001T | mains L/N | none given (Vishay 82401 r1.9, p.1 feature bullet only) | n/a | n/a | false zero-cross edge to firmware | OPEN |
| U41, U42 | R24C2T25/R-R | SW_A / SW_B | +/-150 V/ns (RECOM Rev.1-2024 p.7); Cio 3.5 pF p.8 | 1.58 | 15.0 | regulation upset, reservoir holds | PASS |
| T1 | CST3015-100ED | SW_A (P1) | no CMTI, no Cww (Coilcraft 1608-1) | n/a | n/a | injection into CT burden | OPEN |
| PS1, PS2 | IRM-20-15, IRM-20-24 | mains | none | n/a | n/a | supply, not a signal path | OPEN |
| CTRL | hypothetical 50 kV/us | gate path | - | 0.53 | 5.0 | - | FAIL (as required) |

Count: 5 PASS, 2 FAIL (U1, U2), 6 OPEN lines (U9, U4, U36, T1, PS1, PS2). `VO617A` (BiasOpto) is defined in
`f6_parts.ato` but never instantiated, so it is not a crossing. PS3 (IRM-60-15ST) is off-board.

## Verdict

**F6 does not close.** Both UCC21550 gate drivers are rated 125 V/ns against 95 V/ns, which is 1.32x, short of
1.5x by 17.5 kV/us. At ZVS (10 V/ns) they have 12.5x. This is a margin shortfall against a modelled edge, not a
predicted upset: 125 > 95. The ISO7710 rail monitors pass only through the 10 us filter (tau 10.0 us,
SN74LVC1G17 VT+ min 1.48 V at VCC 3 V, SCES351Y p.6): a 1 us glitch reaches 0.31 V, 5 us reaches 1.30 V, and the
longest rejected glitch is 5.95 us. TI gives no upset-duration figure, so that pass assumes an upset shorter
than 5.95 us. A 520 V swing at 95 V/ns lasts only 5.47 ns. This is a bench item.

Barrier injection (Cio x 95 V/ns, simple model): UCC21550 114 mA / 0.62 nC, ISO7710 38 mA, AMC1311 142 mA,
R24C2T25 332 mA / 1.82 nC. ALT-BIAS section 2 simulates the module case (369 mA, 192 mV at LS VSS at 3.5 pF),
and that is the number to trust for the bias rails.

## Remedies for the FAIL

1. **Cap the hard-edge dv/dt at 83.3 V/ns (= 125/1.5)**, a 12.3 % cut from 95, or show by bench measurement that
   the real S4/S5 edge is already below it. The gate resistors are 3.9 ohm (R10/R12/R18/R20), so Rg is the
   first knob, but the F6 discharge network and S4 die-VDS limits constrain it (not evaluated here).
2. **Firmware ZVS-only** (no hard switching) removes the problem (12.5x). It conflicts with the line-synchronous
   burst mode: FINDINGS F11 says the first turn-on after idle is a hard S5 edge, so ZVS-only means no burst
   starts unless the first edge is soft (ramped start / frequency ahead of resonance). That is a firmware
   decision for the owner.
3. **Higher-CMTI driver at the re-spin.** No verified drop-in exists:
   - UCC21520 (TI, same family) is 100 V/ns, worse; UCC21550 is already TI's pin-for-pin upgrade of it.
   - ADuM4223: published CMTI "> 25 kV/us"; Si8233 family about 45 kV/us (one listing 20); both worse.
   - Novosense NSi6602: 150 kV/us **typical** only (a minimum was not found); SOW16 variant, pinout vs the
     UCC21550 DWK footprint unverified.
   - onsemi NCP51561: "CMTI > 200 V/ns" per a search snippet; 5 kVrms; package and pinout unverified and the
     datasheet could not be downloaded here. This is the one candidate worth a pinout check (it would give
     2.1x), then availability.
   None is recommended for a swap on this evidence; a pinout and availability check is the next step.
4. Bench (adds to BRINGUP-PROBES.md): probe INA/INB at the driver and each driver output during S4/S5 edges; probe
   BIAS_BAD_RAW and BUS_FAULT at U9 for glitch width; measure the S4/S5 dv/dt on SW_A and SW_B.

## OPEN items

- U9 BUS_FAULT and U4 VBUS leave the board unfiltered; the controller needs a debounce (2 consecutive samples or
  about 10 us RC) before acting. The controller side is not in this repo.
- U36 VOL628A has no CMTI number; firmware should validate zero-cross period (50/60 Hz window) before using it.
- T1: Cww is unspecified. With the 1.5 ohm / 100 nF burden, each pF of Cww moves the burden node 5.2 mV for a 520 V
  swing; the OCP trip level is 0.968 V, so break-even is 186 pF. My judgment (not sourced) is that a 3015 package
  is far below that, but ask Coilcraft (cst@coilcraft.com) for the number.
- RECOM p.7 lists one CMTI value in a Min/Typ/Max table and the column is not recoverable from the PDF text; it is
  treated as the rating (150 V/ns), as ALT-BIAS does.

## Sources

UCC21550 SLUSE89C: https://www.ti.com/lit/ds/symlink/ucc21550.pdf; ISO7710 SLLSER9E: https://www.ti.com/lit/ds/symlink/iso7710.pdf;
AMC1311 SBAS786C: https://www.ti.com/lit/ds/symlink/amc1311.pdf; VOL628A: https://www.vishay.com/docs/82401/vol628a.pdf;
R24C2T25/R: https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf; CST3015: https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf;
SN74LVC1G17 SCES351Y: https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf. Alternatives came from search snippets only
(TI product pages, analog.com ADuM4223 page, onsemi NCP51561 search result, Novosense NSi6602 listings).
