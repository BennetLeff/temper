# fmea_p.py output

Chain RWL 13.0 FIT x rails (c24 P2H rows, base).

| row | mode | RWL | s48 as built | S | P (G) | P (E) |
|---|---|---:|:-:|:-:|:-:|:-:|
| ISO6721FB (HA) | OUTB stuck high (= good) | 0.5 | 0 | 0 | 0 | 0 |
| ISO6721FB (HA) | OUTB undetermined | 1.75 | 0 | 0 | 0 | 0 |
| ISO6721FB (HA) | out of V/t spec | 0.0 | 0 | 0 | 0 | 0 |
| U38/U39 TPS70950 (HA) | output to input: ISO6721 side 1 damaged, state unknown | 1.0 | 0 | 0 | 0 | 0 |
| ISO6721FB (HB) | OUTB stuck high (= good) | 0.5 | 0 | 0 | 0 | 0 |
| ISO6721FB (HB) | OUTB undetermined | 1.75 | 0 | 0 | 0 | 0 |
| ISO6721FB (HB) | out of V/t spec | 0.0 | 0 | 0 | 0 | 0 |
| U38/U39 TPS70950 (HB) | output to input: ISO6721 side 1 damaged, state unknown | 1.0 | 0 | 0 | 0 | 0 |
| D_and BAT54A (per HS rail) | open: that HS rail's veto lost | 0.6 | 0 | 0 | 0 | 0 |
| D_and BAT54A (per HS rail) | short: ISO6721 OUTB fights LM339B on the LS node | 0.5 | 0 | 0 | 0 | 0 |
| U_osc SN74LVC1G132 | out of spec (input threshold corrupted) | 0.0 | 0 | 0 | 0 | 0 |
| C_pump 2 x 100 nF series | one short: DC block degraded to one cap (dormant, needs a 2nd fault) | 0.0 | 0 | 0 | 0 | 0 |
| R_bleed 100k | open: hold keeps its charge when the wave stops | 0.6 | 0 | 0 | 0 | 1 |
| U40 SN74LVC1G17 (non-inverting) | Y stuck high (BIAS_GOOD = 1) | 1.8 | 0 | 1 | 1 | 1 |
| U40 SN74LVC1G17 (non-inverting) | Y open (U22/U23 inputs float) | 1.8 | 1 | 1 | 1 | 1 |
| U40 SN74LVC1G17 (non-inverting) | out of spec | 0.0 | 0 | 0 | 0 | 0 |
| U40 SN74LVC1G17 (non-inverting) | adjacent-pin short (Y-VCC) | 1.2 | 0 | 1 | 1 | 1 |

| field DC of the chain | % |
|---|---:|
| s48 as built (boot race lost, c49) | 13.85 |
| S (TPS3808 delay, boot POST) | 36.92 |
| P (PERMIT-gated heartbeat), guaranteed | 36.92 |
| P, typical hold-node leakage (E) | 41.54 |

| sensitivity | chain RWL | as built | S | P (G) | P (E) |
|---|---:|---:|---:|---:|---:|
| base | 13.0 | 13.8 | 36.9 | 36.9 | 41.5 |
| k_u = 0 | 5.1 | 0.0 | 58.8 | 58.8 | 58.8 |
| k_u = 1 | 20.9 | 17.2 | 31.6 | 31.6 | 37.3 |
| k_o = 0.5 | 23.2 | 7.8 | 20.7 | 20.7 | 23.3 |
| passives x5 | 19.8 | 9.1 | 24.2 | 24.2 | 39.4 |
