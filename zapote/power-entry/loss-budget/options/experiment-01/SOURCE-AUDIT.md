# Input review before implementation results

The coordinator checked the retained PDFs independently of the Luna experiment
implementation. `pdftotext -layout` was used to inspect the electrical tables.
These are source-parameter checks, not measurements of the proposed assembly.

| Retained document | Source identity | Checked facts |
| --- | --- | --- |
| `../../sources/STW65N65DM2AG.pdf` | ST DocID028164 Rev 1; static/dynamic tables, p. 4; Eoss figure p. 7 | Rds maximum 50 mΩ at gate 10 V/drain 30 A; typical Qg 120 nC and Qgd 58 nC at 520 V/60 A/10 V; intrinsic Rg 3.3 Ω. The 17.5 µJ point at 400 V uses the previously reviewed Figure 12 extraction; 6.2 V plateau remains assumed. |
| `../replacement-fet/sources/IPW65R045C7.pdf` | Infineon Rev 2.1, 2013-04-30; p. 1 and p. 6 | Rds maximum 45 mΩ at 10 V/24.9 A/25°C; Qg 93 nC, Qgd 30 nC and plateau 5.4 V at 400 V/24.9 A/0–10 V; typical intrinsic Rg 0.85 Ω; typical Eoss 11.7 µJ at 400 V. |
| `../replacement-fet/sources/IPW65R041CFD7.pdf` | Infineon Rev 2.1, 2020-08-12; p. 1 and p. 5 | Rds maximum 41 mΩ at 10 V/24.8 A/25°C; Qg 102 nC, Qgd 31 nC and plateau 5.7 V at 400 V/24.8 A/0–10 V; typical intrinsic Rg 3.8 Ω; typical Eoss 14 µJ at 400 V. |

Hashes, in the same order:

```text
6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322
7ef568434c6325a919ac38fdf998b60d71e8078cce1ed384e82ee09fdc40911a
414a154a79ad7560104db7ef1061bce3e93878b2417d1468695e20e383889fe3
```

The 400 V comparison is a deliberate model operating point; it does not change
the source circuit's bus target. ST's charge test current/voltage differ from
the replacements'. None describes gate charge at every instantaneous PFC
current. The hypothetical Qgd/plateau sweeps must remain labeled sensitivities,
not bounds derived from these tables. Likewise Rds ×2 is not a promised hot
resistance, and a typical Eoss point is not a guaranteed maximum.

The independent Rust audit was authored before reviewing the experiment's
output. It integrates sinusoidal CCM branch-current moments in closed form and
computes the area under separate current-transfer and voltage-transfer stages.
It imports neither production moment functions nor the switching solver. This
is an independent check of the conditional arithmetic, not validation of the
underlying device assumptions. Corrupted-output and asymmetric gate-current
tests accompany it.
