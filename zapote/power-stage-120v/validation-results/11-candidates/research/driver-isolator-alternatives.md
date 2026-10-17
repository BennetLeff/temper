# Gate-driver (U1/U2) and isolator (U9, U32-U34) alternatives, 2026-10-13

Read-only parts research for native-21 stage 19c. Table with every candidate: [`driver-isolator-alternatives.csv`](driver-isolator-alternatives.csv).
No datasheet is stored in the repo; they were read in a scratch directory. Stock and prices were read on 2026-10-13.

## Summary

1. **The "no stock until 2027-06" premise is wrong for TI direct.** The ti.com store inventory endpoint
   (`https://www.ti.com/storeservices/cart/opninventory?opn=<MPN>`, JSON) returned on 2026-10-13:
   UCC21550BDWKR **15,771**, UCC21550BDWR 24,073, UCC21550ADWKR 11,984, UCC21550CDWKR 12,142, ISO7710DWR **10,764**,
   ISO7710FDWR 10,090, ISO7810DWR 35,362. The STOCK-2026-10-13 survey checked Digi-Key/LCSC/JLC only. Buying the
   *existing* MPNs from TI.com closes the availability problem with zero design change. I did not complete a TI.com checkout
   or read TI.com price tiers, so lead time and price at TI are **unverified**.
2. **UCC21550 DW16 is already in stock elsewhere and is a true drop-in.** UCC21550BDWR (SOIC-16 DW): Digi-Key 3,505
   ($2.17 at 1, $1.192 at 500), LCSC C22445586 224 pcs ($1.79 at 1, $1.23 at 500). The STOCK doc's "different pinout/creepage"
   note is wrong: DW16 and DWK have the same pin numbers (TI SLUSE89C Table 4-1, Figures 4-1/4-2; pins 12/13 are NC),
   the same 8 mm creepage (>8 mm, CPG/CLR table) and the same HV land pattern (SLUSE89C p.50 shows 8.1 mm for both).
   It does **not** fix CMTI.
3. **CMTI fix for U1/U2: Infineon 2EDR8259HXUMA1** (SOIC-16 300 mil, pin numbers identical to UCC21550DW16).
   CMTI min **150 V/ns** (1.58x the 95 V/ns edge, passes the 142.5 rule), reinforced, 8 mm creepage, 8 V UVLO, DIS and
   dead-time pins, DK 2,406 pcs at $2.38 ($1.32 at 500). Runner-up: onsemi NCP51561BBDWR2G (CMTI 200 V/ns, but bench-verified only).
   Both change the output stage by a lot (see check 1), so this is a re-qualification, not a swap.
4. **ISO7710 slot:** do not switch to ISO7710FDWR (default LOW is fail-unsafe here and audit.rs deliberately rejects it).
   Either buy ISO7710DWR from TI.com, or use **ISO7810DWR** (same DW pinout, default HIGH, CMTI min 100 kV/us, DK 1,525 at
   $6.12; about 2.9x the price). No tested drop-in with CMTI at the F6 level exists; the monitors pass on the 10 us filter anyway.

## What the schematic uses (so pin-compatibility is judged against reality)

U1/U2 (`parts.ato` UCC21550BDWK, footprint `lib:SOIC16W_Isolated`, 14 pads 1-11, 14-16):
INA 1, INB 2, VCCI 3 and 8 (V3V3), GNDI 4 (SELV_GND), DIS 5 (driven by `driver_dis`, with a 10 k pull-up to V3V3 and
the permit/bias-bad OR), DT 6 (49.9 k to GND -> 442 ns by TI's `8.6*R+13`), NC 7 (unconnected), VSSB 9, OUTB 10,
VDDB 11, VSSA 14, OUTA 15, VDDA 16. Bias: HS and LS `VDD-VSS` regulated to 17.0 V (`f6_bias.ato:62,267`, RECOM 16.91 V),
VSS rides about -1.6 V below source (F6). Gate: 3.9 ohm series (`R3R9Gate`), turn-off through PMEG6030 + 1 ohm (does
not pass through Rg). audit.rs pins the MPN (`BARRIER_PARTS` lines 256-257), the DT resistor and a dead-time window
`DT_WINDOW_NS = (391, 498)` (audit.rs:597).

U9, U32, U33, U34 (`Iso7710`, footprint `lib:SOIC16W_DW0016B_HV`): GND1 1+7, VCC1 3, IN 4, GND2 9+16, OUT 13, VCC2 14,
all other pins NC. The role is fail-safe: "healthy = IN low = OUT low"; trip **or loss of side-1 power** gives OUT HIGH
= bad (`power_stage_120v.ato:636`, `f6_bias.ato:208-211`). So default-HIGH is load-bearing. audit.rs has
`default_low_isolator_fails` (line 1324).

## Slot A: U1/U2 gate drivers

Datasheet pages are of the document read (TI SLUSE89C Aug 2024; Infineon Rev. 1.7 2026-04-09; onsemi NCP51561 current rev;
Novosense NSi6602 Rev 1.8; ADI ADuM4221 Rev. 0).

| Rank | MPN | Package / pin compat | CMTI min | Isolation / creepage | UVLO vs 17 V rail | Stock 10-13 | Price 1 / 10 / 500 |
|---|---|---|---|---|---|---|---|
| 1 | UCC21550BDWR | SOIC-16 DW; same pin numbers, footprint works as is | 125 V/ns (fails) | 5 kVrms, VIORM 2121 Vpk, >8 mm | 8 V grade, same as now | DK 3,505; LCSC C22445586 224; TI 24,073 | $2.17 / 1.60 / 1.19 (DK); $1.79 / 1.58 / 1.23 (LCSC) |
| 1 | UCC21550BDWKR (current) from TI.com | same | 125 V/ns (fails) | same | same | TI 15,771; DK 0 | DK list $1.92 |
| 1 | UCC21550ADWKR / CDWKR | same; UVLO grade 5 V / 12 V | 125 | same | A: 5.7-6.3 V on; C: 11.7-13.3 V on | DK 714 / 1,729; TI 11,984 / 12,142 | $1.92 (DK) |
| 2 | **2EDR8259HXUMA1** | PG-DSO-16 300 mil; pin numbers equal to UCC21550DW (INA1 INB2 VDDI3,8 GNDI4 DIS5 STP/DTC6 NC7,12,13 GNDB9 OUTB10 VDDB11 GNDA14 OUTA15 VDDA16) | **150 V/ns** (Table 23 p.17) | 5.7 kVrms, VIORM 1767 Vpk, VIOTM 8 kVpk, 8 mm (Table 24); ch-ch 2.5 mm | 8 V grade: on typ 8.0 / max 8.5 V; operating 8.5-21 V | DK 2,406 (39 wk) | $2.38 / 1.76 / 1.32 |
| 2.5 | 2EDR8259XXUMA1 | DSO-14, same pad positions as DWK but pads numbered 1-14 (GNDA 12, OUTA 13, VDDA 14): needs a renamed footprint | 150 | same; ch-ch 3.3 mm | same | DK 1,043 | $2.38 / 1.76 / 1.32 |
| 2 | NCP51561BBDWR2G | SOIC-16 WB; pin 7 = ANB (UCC: NC) | **200 V/ns, bench-verified only** (p.11, note 19) | 5 kVrms, VIORM 1200, VIOTM 8000 Vpk, ECR/ECL 8.0 mm (p.6) | 8 V grade: on 8.3-9.2 V; rec VCC 9.5-30 V; abs 33 V | DK 878 (45 wk); Richardson 2,000 (MOQ 1,000) | $3.78 / 2.85 / 2.22 |
| 3 | NSI6602VB-DSWKR | SOW14, pinout equals DWK | **100** (150 typ) | 5.7 kVrms, 8 mm | 8 V | DK 403 | $2.31 |
| 3 | ADuM4221BRIZ | SOIC_IC 16, pins equal DW16 | +/-150 kV/us (operating-range table, not a labelled min) | reinforced VIORM 849 Vpk, certs pending (Rev 0), 8.3 mm | B: 7.5 V | DK unknown; ~$9.75 | $9.75 |
| reject | UCC21520/30/40, Si8233/Si8239x, 2EDS9265H (NFND), Broadcom ACFJ-302CT (SO-24, re-layout) | | 125 / 35-45 / 150 / 150 | | | | |

Notes:
- Digi-Key has no 5-piece break; use the 10-piece figure as the 5-piece price. LCSC/JLC have no listing for 2EDR8259, NCP51561 or ISO7810.
- NCP51561 must be the **B** (DISABLE) suffix; the A suffix is ENABLE (open = enabled, low = off), the wrong polarity.
- The repo's cmti README says UCC21520 is 100 V/ns and Novosense NSi6602 has no min. Current datasheets: UCC21520/30/40 are 125 V/ns min;
  NSi6602 Rev 1.8 says min 100 / typ 150 kV/us, which is worse than the UCC21550 (125). NSi6602M (claimed 150 min, SOIC-18) is from one reseller article only.

### Why 2EDR8259H over NCP51561

| | 2EDR8259H | NCP51561BBDWR2G |
|---|---|---|
| CMTI margin vs 142.5 | 150 (+5 %) | 200 (+40 %), but bench only |
| Pin 7 | NC | ANB, wants GND (copper edit) or float ("not recommended") |
| Dead-time tolerance | 85-115 ns at 10 k (about +/-15 %) | 145-255 ns at 20 k (+/-27 %), 800-1200 at 100 k |
| Price at 10 | $1.76 | $2.85 |
| Stock | 2,406 | 878 (45 wk) |
| Abs max VDD-VSS | 22 V (17 V now: 5 V margin) | 33 V |
| Output | 5 A / 9 A, Ron 0.95 / 0.39 ohm, active clamp in UVLO | 4.5 A / 9 A, Ron 1.4 / 0.5 ohm |

2EDR8259H wins on stock, price, dead-time spread and pinout. NCP51561 wins on CMTI margin and VDD headroom. If a bench
measurement shows the real hard edge is above 100 V/ns, NCP51561 is the fallback.

## Slot B: isolators (U9, U32, U33, U34)

| Rank | MPN | Pin compat | CMTI min | Default out | Stock 10-13 | Price 1 / 10 / 100 / 500 |
|---|---|---|---|---|---|---|
| 1 | ISO7710DWR from TI.com store | identical | 85 kV/us | HIGH | TI 10,764; DK 0 (2,000 due 12-15); LCSC C2859830 0 | DK $2.14 / 1.58 / 1.29 / 1.17; LCSC $2.50 |
| 1 | **ISO7810DWR** | identical DW pins (SLLSEP1C Fig 4-1) | **100 kV/us** (Section 5.9 p.8) | HIGH (non-F) | DK 1,525 (12 wk); TI 35,362 | $6.12 / 4.69 / 3.94 |
| 1? | ISO7710DW (tube) | identical | 85 | HIGH | DK page marks OBSOLETE, stock not shown | $3.12 / 2.34 |
| 3 | ISO7710FDWR | identical | 85 | **LOW** | DK 5,145; TI 10,090 | $2.25 / 1.66 / 1.36 / 1.24 |
| reject | NSi8120W1 | IN pin 4, OUT pin 13 match, INB pin 5 unused | 100 (150 typ) | HIGH | unverified | n/a |
| reject | Si8610BD, NSi8121W, ADuM1250 | wrong function or pinout | 35-50 / n/a / n/a | | | |

- **ISO7710FDWR is not usable as a swap.** After HOT5 loss it drives LOW, which U9 and the three rail monitors read as
  healthy. Making it work means inverting the polarity of the whole fault chain (NAND3 -> AND3, the NPN stage in
  `f6_bias.ato` RailMonitor, OR3 -> AND3, and the J4 BUS_FAULT sense), a tier-3 logic change with a controller-side
  interface change.
- **NSi8120W1 is not reinforced.** Its UL listing is "single protection, 5000 Vrms" and VDE basic 849 Vpk; reinforced
  appears only in the CQC row at 565 Vpk (Rev1.9 p.~12). It straddles the 8 mm reinforced barrier, so reject. NSi8121W's pin 13
  is a reverse input, so it is also the wrong pinout.
- ISO7810's CMTI (100) is only +18 % over ISO7710 (85). The monitors rely on the 10 us RC filter, not on CMTI
  (cmti README), so the extra cost buys little. U9 (BUS_FAULT) is unfiltered on board and listed OPEN; the real fix for that
  line is a controller-side debounce or a faster-CMTI isolator, and none was found in this survey.

## Ranking and recommendation

Tier 1, drop-in, no layout change, no schematic change:
- U1/U2: buy UCC21550BDWKR from TI.com (15,771), or switch to UCC21550BDWR (DK/LCSC/TI.com). Edit audit.rs MPN if DW.
- U9/U32-34: buy ISO7710DWR from TI.com (10,764), or ISO7810DWR (DK 1,525).

Tier 2, same footprint, schematic and parameter changes (the CMTI fix):
- U1/U2: **2EDR8259HXUMA1** (recommended), NCP51561BBDWR2G (fallback).

Tier 3, re-layout or logic redesign: 2EDR8259X (renumbered footprint), ISO7710FDWR (polarity inversion), ADuM4221 (cost),
Broadcom ACFJ-302CT.

**Recommendation per slot**
- **U1/U2:** place the order for UCC21550BDWKR on TI.com now to unblock the build (and DWR as a second source), and in
  parallel qualify **2EDR8259H** as the F6 CMTI close. It is the only candidate that clears 142.5 V/ns with a datasheet minimum, keeps pin numbers,
  is cheaper than the NCP, and is in stock. Do not adopt it before the checks below; the stronger pull-up is the real risk.
- **U9/U32-34:** keep ISO7710DWR (TI.com). Take ISO7810DWR only if TI.com cannot supply. Never ISO7710FDWR without redesign.

## Risks of the 2EDR8259H swap

- Output resistance: UCC21550 ROH is 5 ohm (Table 5.9) against 0.95 ohm; with the 3.9 ohm gate resistor, turn-on
  resistance falls from about 8.9 to about 4.9 ohm. That is a faster turn-on edge (higher dv/dt, which is also what
  CMTI must withstand, and higher di/dt through the 37.6 nH loop). Keep turn-on resistance by raising Rg to about 8.2 ohm
  (3.9 -> 8.2 gives 9.15 ohm). Turn-off goes through PMEG + 1 ohm and is unaffected apart from ROL (0.55 -> 0.39).
- 22 V abs max (current driver 30 V). The rail is 16.9-17.0 V; the TL431/regulator over-voltage and module start-up
  overshoot must stay under 21 V operating.
- Channel-to-channel creepage 2.5 mm (16-pin; 3.3 mm for the 14-pin X). Infineon gives no ch-ch working voltage; TI states 1850 V for DWK. The VSSA-VSSB
  pair sees the hard-switched node plus bus (S4 die VDS up to 520 V). Needs a measurement or an Infineon answer.
- DIS: UCC pulls DIS HIGH internally (90 k) and 2EDR/NCP pull LOW. The board's external 10 k + 330 ohm pull-ups to V3V3 hold
  DIS high either way, so the PERMIT fail-safe is preserved; the unpowered-controller state must be re-checked.
- DT dead-time pin: tdt = 10 ns/kohm. 44.2 k gives 442 ns nominal. The spread (+/-15 % at 30 k) exceeds the audit window (391-498 ns,
  +/-12.7 %), so widen the window with the datasheet tolerance table or choose the resistor to centre it.

## Design checks if adopted

1. Rerun the F6 decision matrix and the S4/S5 turn-on deck with the new driver model (ROH/ROL, tpd 36-38 ns vs 33 ns, clamp
   behaviour), including the Rg change. D-23/D-26 modelled the UCC21550; this is a new driver.
2. audit.rs: `BARRIER_PARTS` lines 256-257 and the part expectations (UCC21550BDWKR), `r_dt` expected MPN (307-308) and the dead-time
   window (597-610, formula `8.6*R+13`), the `r_gh`/`r_gl` value (3.9 ohm), and the ISO7710DWR entries (259-264, 313, 454, 495, 533).
   Add a negative control for the new part, as exists for ISO7710FDWR.
3. `parts.ato`: new component with the pin map (2EDR8259H: same pads, pin names INA, INB, VDDI, GNDI, DIS, STP_DTC, GNDB,
   OUTB, VDDB, GNDA, OUTA, VDDA), footprint pads 12/13 absent stays fine for NC but confirm the package outline and land pattern
   of the Infineon DSO16 against `lib:SOIC16W_Isolated` (8.1 mm pad-to-pad edge gap) and the FOOTPRINTS.md F8 row. F6 rail
   rider: VSS at -1.6 V is irrelevant to the driver's input-referenced pins, but re-confirm VDDA-VSSA 17 V and the monitor's upper edge against 22 V.
4. Dead-time resistor R(U1/U2 DT): 44.2 k (E96, 0.1 %) for 442 ns, checked against the window.
5. Leads 12/13 (UCC DW, 2EDR8259H, NCP) exist on a 16-pin body where the footprint has no pads. Routed board: the nearest F.Cu
   copper (v15_ls / n_hb) is about 1.07-1.12 mm from the centres of positions 12/13, and In1 nets run beneath; check
   solder-mask and lead-to-copper clearance for NC leads, and the creepage rules vs the 3.3 mm ch-ch gap.
6. NCP only: pin 7 to GND or float; DT tolerance; 200 V/ns is bench only.
7. Update the sourcing record: JLC/LCSC C-numbers (UCC21550BDWR is C22445586, extended), TI.com as a source, pricing.
8. Isolators: no schematic change for ISO7810DWR; only the MPN in audit.rs and `parts.ato`. Re-verify `lib:SOIC16W_DW0016B_HV`
   (same DW0016B land pattern per ISO7810 data sheet).
9. Firmware/controller: unchanged for 2EDR/UCC (logic thresholds: 2EDR VINH max 2.36 V, VINL min 0.9 V; UCC similar;
   3.3 V controller is fine). D-25 PWM pull-downs unaffected (2EDR INx pull-down 150 k).

## Unverified

- TI.com price and lead time; TI inventory is from the ti.com inventory endpoint only (no checkout).
- Infineon DSO16 package outline and land pattern (figures in the PDF are images). Digi-Key lists 2EDR8259H as "16-SOIC 0.154 in / 3.90 mm" while the
  datasheet says 300 mil; I believe Digi-Key is wrong but did not confirm.
- Infineon ch-ch working voltage; 2EDR8259H real over-voltage behaviour at 17 V.
- NCP51561 DIS internal pull-down resistance and ANB behavior floating; its CMTI is bench-only.
- ADuM4221 stock, whether the 150 kV/us is a guaranteed min, and Rev 0 certificates (pending).
- NSi6602M datasheet (only a reseller summary), 2EDS9265H pinout, Si82394 pinout, Broadcom ACFJ-302CT details.
- LCSC/JLC stock of the Infineon/onsemi/ISO7810 parts (not found); Mouser pages timed out.
- ISO7710DW (tube) stock: the keyword page listed it with 1,909 but the detail page shows OBSOLETE and no stock figure.

## Sources

- TI UCC21550: https://www.ti.com/lit/ds/symlink/ucc21550.pdf (SLUSE89C); UCC21520/30/40 same server.
- TI ISO7710: https://www.ti.com/lit/ds/symlink/iso7710.pdf; ISO7810: https://www.ti.com/lit/ds/symlink/iso7810.pdf
- Infineon 2EDR8259H/2EDRx259X: https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf
- onsemi NCP51561: https://www.onsemi.com/pdf/datasheet/ncp51561-d.pdf
- Novosense NSi6602 Rev 1.8: https://tellur-el.ru/upload/iblock/a8d/3nqji5m9tghailis2t3t5ejeh7th4y4n.pdf ; NSi812x Rev1.9 (mandieselturbo mirror)
- ADI ADuM4221 Rev 0: https://atta.szlcsc.com/upload/public/pdf/source/20210607/03A726DED3B1D7E6A39F12CA21026128.pdf
- Stock: ti.com `opninventory` endpoint; Digi-Key `https://www.digikey.com/en/products/result?keywords=<MPN>` pages (UCC21550BDWR/22147285,
  ISO7710DWR/6590803, ISO7710FDWR/6590804, ISO7810DWR, NCP51561BBDWR2G/16528555, 2EDR8259H/X, NSI6602 list);
  LCSC https://www.lcsc.com/product-detail/C22445586.html and /C2859830.html
