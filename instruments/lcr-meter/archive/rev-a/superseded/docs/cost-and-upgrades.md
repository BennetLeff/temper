# Cost and useful upgrades

## One usable instrument

The complete instrument occupies **one PCB**. JLCPCB's prototype service currently advertises a minimum of2 assembled boards; bare-board orders normally begin at5. A desire to use one instrument does not eliminate those manufacturing minimums. No quote, order or checkout was submitted.

The actual51-component BOM totals **$38.14 per populated board** at the saved catalog unit prices.45 top-side assembly placements total **$36.34**, and six hand-fitted headers add **$1.80**. The three main ICs account for approximately$34.05. Catalog stock/prices are snapshots, not guaranteed procurement offers. Small-part purchasing minimums, feeder losses and distributor pack sizes increase the cash purchase above the arithmetic BOM.

| Route | Rough cash budget in USD | What it includes |
|---|---:|---|
| Buy a bare-board batch, hand assemble one | $60–110 | One set of parts, typical small4-layer fabrication and shipping; assumes you already have soldering/reflow tools |
| JLCPCB assemble the smallest batch, finish headers yourself | $160–240 | Approximately$72.67 SMT parts for2 boards, fabrication, setup/stencil, extended-part feeder fees and ordinary shipping allowance |
| Accessories/calibration setup | Add$20–80+ | Cable, short fixture, jumper, precision resistors; excludes a calibrated reference meter or oscilloscope |

These are engineering allowances, not a live quote. Taxes/import charges, remote shipping, special procurement and qualification equipment are excluded. The fresh catalog has 11 basic and 15 extended SMT part lines, with no preferred classification. At the published economic rates, 15×$3.07 feeder loading + $8.18 setup + $1.53 stencil + $72.67 for two sets of SMT parts = $128.43 before PCB fabrication, placement, headers, shipping or tax. Classification and stock must be refreshed before ordering. A standard-assembly tier or special source can raise the estimate. There is no claim that JLC will assemble exactly one board.

[JLC's assembly FAQ](https://jlcpcb.com/help/article/pcb-assembly-faqs) describes setup and per-extended-part feeder fees, with preferred extended parts exempt in economic assembly. [Prototype assembly](https://jlcpcb.com/solutions/pcb-prototype-assembly) advertises2-board minimum. [Current assembly pricing](https://jlcpcb.com/help/article/pcb-assembly-price) is the authority for the actual transaction. Checked 2026-10-20.

## What additional spending would buy

| Upgrade | Benefit | Why it is not in revision A |
|---|---|---|
| Better characterized standards and a repeatable shielded fixture | Directly improves calibration transfer and repeatability; best first investment | External accessories, not extra PCB electronics |
| Selectable lower master clock | More DFT cycles at1–3 kHz; more credible bulk-capacitance tests | Requires oscillator switching, clock-aware host metadata and fresh qualification |
| Separate voltage/current sensing with simultaneous ADCs | Measures source droop directly and can extend useful impedance/bandwidth range | A substantially larger AFE, converter and firmware redesign |
| Dedicated four-wire DC current source and differential readout | Enables1 mΩ shunt/DC winding resistance measurements | Different measurement architecture and thermal-offset calibration |
| USB isolation with isolated power | Breaks computer-ground paths | Adds cost/noise/space and still does not make the DUT input mains safe |
| Relay ranges and terminal-voltage detection | More convenient range changes and better misuse handling | Additional leakage/parasitics and protection design; current version uses a manual jumper |
| Screen and local controls | Standalone user interface | Does not improve measurement accuracy; computer CLI already supplies sweeps |

None of these upgrades gives an automatic accuracy number. Characterization of the first board comes before component upgrades. Revision A's scope is practical component diagnosis, not a replacement for a qualified laboratory impedance analyzer.
