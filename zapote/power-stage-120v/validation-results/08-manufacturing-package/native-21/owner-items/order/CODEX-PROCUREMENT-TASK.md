# Browser task: stock and price check for the native-21 prototype lot

**For:** a browser-use agent (Codex). **Owner:** Temper hardware. **Date written:** 2026-10-08.

## Goal

Find a real, in-stock source for every part below, for a prototype lot of **5 boards**. Report part, distributor, stock, price at quantity, lead time and the exact product page.

The earlier automated check could not read Digi-Key or Mouser (bot-blocked), so these lines are unconfirmed.

## Hard rules

- **Read-only. Do not purchase, add to cart, request quotes, create accounts, log in or submit any form.** If a site needs a login to show stock, say so and move on.
- **Exact part numbers only.** A listing counts only if its manufacturer part number matches the MPN below exactly, or differs only by a packaging suffix (tape/reel/cut tape). Write the full MPN you saw.
- **Never substitute on your own.** If an exact part has no stock anywhere, you may list up to two *candidate* equivalents in the notes column. A candidate must match every listed attribute (value, tolerance, voltage rating, dielectric/technology, package/footprint, temperature rating), and you must name the attribute you checked on its datasheet. Mark it `CANDIDATE — needs engineer approval`.
- Record the **date and time** you read each page. Stock changes quickly.
- When a part is sold only by the manufacturer (direct store or samples), check the manufacturer site (TI store, Coilcraft, Würth Elektronik, Eaton, Littelfuse, JST, TDK) and say "direct only".

## Where to look, in this order

1. Digi-Key (digikey.com)
2. Mouser (mouser.com)
3. Newark/Farnell, Arrow, TTI (tti.com, strong for passives and film caps), Avnet
4. Manufacturer direct: TI store (ti.com), Coilcraft (coilcraft.com, samples), Würth (we-online.com), and the others above
5. Findchips or Octopart as a cross-check only, never as the cited source

## Quantity to price

`buy qty` = 5 boards × qty per board, plus spares:
- **resistors, capacitors:** +20 %, minimum +2;
- **ICs, transistors, magnetics, connectors:** +1 per board type, minimum +2.

Price at the buy qty; if a minimum order is higher, give the minimum and its price.

## Parts

| # | Designators | Manufacturer | MPN | Qty/board | Key attributes (for equivalence) | Note |
| --- | --- | --- | --- | ---: | --- | --- |
| 1 | U1, U2 | Texas Instruments | UCC21550BDWKR | 2 | Dual isolated gate driver, SOIC-16 DWK (14-pin-wide body, pins 12–13 removed), reinforced, 4 A/6 A | TI direct showed none. Try the "DWK" vs "DW" package carefully: only **DWK** fits |
| 2 | U9, U32, U33, U34 | Texas Instruments | ISO7710DWR | 4 | Single-channel digital isolator, SOIC-16 wide (DW), reinforced | Brokers only seen; avoid brokers unless the owner agrees, and mark them BROKER |
| 3 | T1 | Coilcraft | CST3015-100ED | 1 | Current sense transformer 1:100, SMD, 5 kVrms reinforced | Samples / direct |
| 4 | T2, T3 | Würth Elektronik | 750320775 | 2 | Isolation transformer for SN6507 push-pull | Direct / samples |
| 5 | C5, C6 | TDK (EPCOS) | B32656G0275J000 | 2 | Film cap 2.7 µF, 5 %, PP, DC-link | TDK MOQ 360. Find any distributor stocking it |
| 6 | C21–C23, C151, C152 | TDK (EPCOS) | B32654A1104K000 (±5 % alternate B32654A1104J000) | 5 | MKP film 0.10 µF, 1600 Vdc / 500 Vac, radial 27.5 mm pitch, 0.8 mm leads, 14 × 24.5 × 31.5 mm, 7.3 A at 85 °C / 100 kHz | Changed 2026-10-09 (stage 13): replaces the 942C bank. DigiKey showed 2,669 (K000) |
| 7 | — | — | (row retired: 942C12P1K-F is no longer used) | 0 | | |
| 8 | L1 | TDK (EPCOS) | B82726S2203A020 | 1 | Current-compensated choke, 20 A, 1.6 mH | |
| 9 | C1, C2 | KEMET | R463N410050N1K (changed 2026-10-09 from R463N410000N1M, 24-38 wk) | 2 | X2 film 1 µF ±10 %, 310 Vac, 22.5 mm, N1 body; 25 mm leads | Digi-Key showed 955 |
| 10 | C3, C4 | Murata | DE1E3RA222MA4BP01F | 2 | Y1 ceramic 2200 pF | |
| 11 | J2, J5, J7–J10 | Würth Elektronik | 74650074 (LCSC lists 74650074R) | 6 | REDCUBE THR press-fit power terminal, M4 | Report both suffixes if seen |
| 12 | Q2, Q3, Q5, Q6 | Infineon | IPW65R018CFD7 (IPW65R018CFD7XKSA1) | 4 | 650 V CoolMOS CFD7, TO-247-3 | JLC had 6, need 20 + spares; Newark seen earlier |
| 13 | R5 | Vishay | WSK25121L000FEA | 1 | 1 mΩ 2512 4-terminal shunt | |
| 14 | R34, R35 | Yageo / Vishay | RT0603BRD0712K4L (R34), TNPW060311K7BEEA (R35) | 1 + 1 | 12.4 kΩ / 11.7 kΩ 0.1 % 25 ppm 0603 thin film | Changed 2026-10-09 (BOM simplification): 10.6 k had no stock; JLC C861102 / C4553285 |
| 15 | R77, R95, R110 | Yageo | RT0603BRD076K2L | 3 | 6.2 kΩ 0.1 % 25 ppm 0603 thin film | Changed 2026-10-09: 6.12 k had no stock; JLC C136960 |
| 16 | R87, R105, R120 | Viking Tech | ARG03BTC1333 | 3 | 133 kΩ 0.1 % 25 ppm 0603 thin film | Changed 2026-10-09: now the source part; JLC C1509631 |
| 17 | U35 | Texas Instruments | SN6507DGQR | 1 | Push-pull transformer driver, HVSSOP-10 (DGQ) | Candidate: SN6507DGQRQ1 (automotive grade) |
| 18 | U36 | Vishay | VOL628A-3X001T | 1 | Optocoupler | |
| 19 | D3 | Littelfuse | MRT130KP295CV | 1 | TVS | |
| 20 | J6 | Phoenix Contact | 1704004 | 1 | PE branch terminal | |
| 21 | C126–C129 | Panasonic | 6SVPC220M | 4 | OS-CON 220 µF 6.3 V | |
| 22 | J3 | JST | B2P3-VH(LF)(SN) | 1 | VH header, 7.92 mm pitch (post 2 omitted), vertical | |
| 23 | J3 mate | JST | VHR-3M + SVH-21T-P1.1 (or SVH-41T-P1.1) | 1 housing + 2 crimps | VH housing, contacts in positions 1 and 3 | |
| 24 | J4 mate | Molex | 43025-1600 + 43030-0007 | 1 housing + 16 crimps | Micro-Fit 3.0 2×8 receptacle, crimps 20–24 AWG tin | |
| 25 | F1 | Littelfuse | KLDR025.TXP (alternate Eaton Bussmann LP-CC-25) | 1 | UL Class CC, 25 A time-delay, 600 Vac, 200 kA, 10.3 × 38.1 mm | Changed 2026-10-09 for Mexico (120–127 V) |
| 26 | F1 clips | Littelfuse | 01250003H | 2 | 125-series PCB clip for 13/32" (10.3 mm) midget / Class CC fuses, 30 A | LCSC C223911 had only 1 in stock |
| 27 | Controller U14 | Analog Devices | AD8436BRQZ | 1 per controller | True-RMS-to-DC converter, QSOP-20 | Zero JLC stock; check ADI direct |
| 28 | Controller U15 | Microchip | MCP3202-CI/SN (confirm the exact suffix in zapote/controller/bom/controller-parts.json) | 1 per controller | 12-bit 2-channel SPI ADC | Thin JLC stock |
| 29 | Controller | Texas Instruments | TPS3703A4330DSERQ1 | 1 per controller | Window voltage supervisor, automotive grade | JLC had 18 |

## Output

Return **one CSV**, one row per part above, with these columns in this order:

```
row,designators,mpn_requested,mpn_seen,distributor,product_url,stock,moq,buy_qty,unit_price_usd,ext_price_usd,lead_time,read_utc,status,notes
```

- **`status`** is one of `IN_STOCK`, `PARTIAL` (less stock than buy qty), `LEAD_TIME` (orderable, not in stock), `DIRECT_ONLY`, `BROKER`, `NOT_FOUND`.
- **Rows:** give the best source per part. Add a second row for the same part if a second source is materially better (price, stock or lead time).
- **After the CSV:** a short summary with the parts that are `NOT_FOUND` or `LEAD_TIME` over 8 weeks, and the total of `ext_price_usd` for the in-stock rows.
