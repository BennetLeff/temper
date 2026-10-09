# Native-21 prototype lot: order plan (prepared, NOT ordered)

A first build to answer the bench questions simulation cannot: S4 commutation (F2 / D-24), Vgs
ringing and `ocp_node` (D4 conditions 2–3), the F6 negative rail at the edge, and IR thermal at
nominal power (task 04). **Ordering is a purchase and needs the owner's approval.** This file is
the ready-to-place plan.

## What to order

| Item | Choice | Why |
| --- | --- | --- |
| Bare PCBs | **5** from `fab/native-21-gerbers.zip` | 2 assembled, 1 for rework or partial bring-up, 2 spare |
| PCB options | 4 layers, 1.6 mm, JLC041622-7628, **2 oz outer and inner**, green / white, **ENIG** | ENIG: flat pads for the fine-pitch parts and the capped vias, and a durable finish for probed test pads |
| Via covering | **Epoxy-filled and capped for every 0.3 mm via**; 0.8 mm vias tented | every 0.3 mm via; 79 drills fully inside SMD pads and 63 overlapping (stage 11, FAB-NOTE.md) |
| Laminate | Ask JLC to confirm CTI ≥ 175 V (IIIa) before payment | D5 / FAB-JLCPCB.md open question |
| SMT assembly | **2 boards**, top side, from `fab/bom-jlcpcb.csv` + `fab/cpl-jlcpcb.csv` | 88 of 95 source lines with checked LCSC numbers (stock re-check: `owner-items/order/`); check every CPL rotation in JLC's preview |
| THT and consigned parts | Hand-solder in house | TO-247s, BR1, film caps, terminals, magnetics, PS1/PS2: heavy copper needs a hot iron or selective solder |

## Parts to buy before ordering (from `sourcing/README.md`)

- **Consign / buy from distributors:**
  - C5/C6 B32656G0275J000;
  - U1/U2 UCC21550BDWKR (the DWK package, not DW);
  - T1 CST3015-100ED; T2/T3 Würth 750320775;
  - R34 RT0603BRD0710K6L.
- **Zero JLC stock at survey (buy-plan or consign):**
  - R463N410000N1M; B82726S2203A020;
  - WSK25121L000FEA (R5); 74650074R terminals;
  - 942C12P22K-F / 942C12P1K-F; ISO7710DWR;
  - Molex 0430451612; MRT130KP295CV; Phoenix 1704004;
  - SN6507DGQR; VOL628A-3X001T;
  - RT0603BRD076K12L; RT0603BRD07133KL.
- **Thin stock:** IPW65R018CFD7 (6 against 8 for two boards): buy 10 from a distributor, from one recorded lot (D-8 asks for lot traceability).
- **Fixings:** M3 nylon (UL94 V-0) screws, washers and standoffs for H2–H7, with the whole chain insulating (BRINGUP-PROBES.md); one metal M3 for H1 (chassis/PE).

## Gates before placing the order

1. Independent design review (in progress): every BLOCKER / MAJOR closed.
2. Enclosure bosses agreed for H1–H8 (D5-AUDIT.md), or the holes moved to match.
3. JLC's CTI answer.
4. Owner approval of the spend.

Insulation qualification (PD3, IEC 60664-4, hipot) does **not** gate a bench prototype run on a
current-limited, isolated supply. It gates any mains-connected or unattended operation.

## Bring-up sequence (summary; full procedures in D-8 and BRINGUP-PROBES.md)

1. Bare board: continuity and isolation spot checks across the barrier (megger at a low voltage),
   no copper shorts on the rails.
2. Logic and bias only (no bus): SELV 15 V / 3.3 V, then the bias supplies. Check +15 / −2 V on every
   domain at the TP pairs; BIAS_BAD and DIS behaviour; the monitor windows (−2.206 / −1.799 V).
3. Gate drive with no bus: PWM in, driver outputs at the TP pairs; dead time (R9/R17 49.9 kΩ).
4. Bus from a current-limited isolated supply, rising in steps: Vgs ringing on all four FETs at the
   leads (D4 condition 3), `ocp_node` during hard switching (D4 condition 2), the S4 commutation shot (D-24).
5. Resonant operation at reduced power, then nominal, with IR thermal (task 04: hottest copper ≤ 20 K
   above ambient, SW_A / SW_B tank strips first). The tank RMS ceiling of 22 A applies from the first
   powered test.
