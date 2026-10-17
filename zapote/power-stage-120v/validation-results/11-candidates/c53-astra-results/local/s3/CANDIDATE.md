# Item 3: a differential-mode inductor for the D-22 inlet module (>= 100 uH per line at 21 A): candidate found, marginal pass

2026-10-17. The "module" in MODULE-REQUEST.md item 3 is the board's own off-board D-22 inlet filter design, not a catalogue IEC inlet filter, so the open part is a **single
discrete DM inductor per line** (one in L, one in N): >= 100 uH per line at 21 A, with both inductors inside the module's 3.6 W allowance (about 4 mohm each at 21 A, or
about 8 mohm each at the 15 A RMS cap, so 3.6 W / 2 = 1.8 W each).
(The cloud brief's item 3 text, "catalogue inlet filter modules", was wrong on this point.)

## Candidate: Wurth Elektronik WE-HCFT **74437636351012** (flat-wire metal-alloy THT, size 3635)
From the datasheet (Wurth, rev 001.000 2024-11-06, p.1-2; the PDF is not committed; page 2 curves saved here as `hcft-74437636351012-L-vs-I-p2.png`):
| Property | Value |
|---|---|
| Inductance | 110 uH +/-20 % (at 0 A) |
| DC resistance | **6.28 mohm +/-10 %** at 20 C |
| Rated current (IEC 62024-2, Class D test board, 1000 um Cu, 40 mm wide) | IRP,40K = **23.7 A** typ at dT = 40 K (ambient limit +115 C) |
| Saturation current | **27.2 A** at a 30 % inductance drop |
| Operating voltage / temperature | 400 V; -55 to +155 C |
| SRF | 5.11 MHz |
| Body | about 36.0 x 35.7 max x (34.2 max) mm, 2 pins 24.3 mm apart (hole pattern on p.1) |
| Inductance vs current (typical curve, read by eye) | 110 uH at 0 A, ~105 at 10 A, ~98 at 15 A, ~90 at 20 A, **~88 at 21 A**, ~81 at 25 A, ~72 at 30 A |
| Temperature rise (typical, IEC board) | ~15 K at 15 A, ~28 K at 20 A |
Stock / price (RS UK, read 2026-10-17, https://uk.rs-online.com/web/p/leaded-inductors/0697766): in stock, 24 more from 19 Oct; GBP 18.49 at 1-4, **GBP 17.94 at 5+** (exc. VAT; two parts per board). DigiKey / Mouser not read.

## EMI result (committed tool, unchanged: `run_emi_l1.py B82726S2243A020_moduleDM<N>u`, s19b model, PASS if nominal and every sensitivity >= 6 dB; `emi-sweep.json`)
| Module DM per line | nominal | worst sensitivity (all) | verdict |
|---|---:|---:|---|
| 110 uH (zero bias) | 11.15 dB | 6.96 dB | PASS |
| **88 uH (this part's typical value at 21 A)** | 10.51 dB | **6.12 dB** | **PASS** |
| 77 uH | 9.66 dB | 5.25 dB | INCONCLUSIVE |
| 65 uH | 8.62 dB | 4.19 dB | INCONCLUSIVE |
The model's sensitivity set already takes the module DM 24 % below nominal, which covers this part's -20 % tolerance (88 -> 70 uH vs the model's 88 -> 67 uH). So **the candidate passes, with 0.12 dB to spare on the
worst sensitivity**: that is a pass on the model's own criterion, not a comfortable one. The 70 uH low corner alone (without the further -24 % stack) is between the 77 and 65 uH rows (INCONCLUSIVE).

## Heat against the module's 3.6 W allowance
RDC 6.28 mohm at 20 C; hot copper (about 100 C, +31 %) is about 8.2 mohm. At the 15 A cap: 1.41 W each at 20 C, about 1.85 W each hot = **2.8-3.7 W for the pair**. At the 13.5 A regulated hold:
1.14 W / 1.50 W each, **2.3-3.0 W for the pair**. So the pair fits the 3.6 W allowance at the hold and at 15 A cold; **at 15 A with hot copper it is at the limit (3.7 W)**. The datasheet's own 40 K rise (23.7 A) is on a good
copper test board; in an enclosure verify on the bench.

## What this does not settle
1. L(21 A) is read from the typical curve by eye (about 88 uH), not from a table; the margin is 0.12 dB, so a sample must be measured at 21 A.
2. The module's mechanical fit for two 36 x 36 mm bodies, and whether the module owner accepts a flat-wire THT choke: not checked (the module design is `out-D22/`, outside this tree).
3. Cost: GBP 18-19 each x 2 per board is the largest single module part; DigiKey / Mouser pricing and stock not read.
4. Two parts are needed per system (one per line); the EMI model assumes both.

## Recommendation
Use 74437636351012 for the prototype module (two per board) and treat the EMI result as "model passes, 0.12 dB margin": **pre-compliance on the bench decides**, as MODULE-REQUEST.md already allows. If the bench shows margin below 6 dB, fall back
to the recorded EMI deviation or the 2203 L1 (12.37 dB). A draft sample/stock request to Wurth is in `MESSAGE-FOR-WURTH.md` (not sent).
