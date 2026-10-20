# Inquiry 2: F1 and overcurrent protection, to a certification lab (native-21, board of record s53)

Status: draft, **not sent**. Rewritten for s53 on 2026-10-18 (OPEN-ITEMS S11). The 2026-10-08 version asked about the
Eaton MDA-25-R and its 125 Vac interrupting rating. That fuse left the design when F1 became a Class CC fuse, so those
questions are moot. The old text, with its UL 248-1 / NEC 110.9 / NMX-J-098 research, is in git history (this file at
commit e60d227e4). This inquiry is items A2 #5–9 and A3 #11 of `../../owner-items/CERTIFIER-PACKET.md`. Send it with the
packet, as one email per lab.

Paths are relative to PS = `zapote/power-stage-120v`. `VR` = `PS/validation-results`.

## Facts of the design (s53)

| Item | Value | Source |
|---|---|---|
| Nameplate | 120–127 V~ 60 Hz, NEMA 5-15P cord and plug, US / Canada / Mexico (decided 2026-10-08) | DECISIONS 2026-10-08; old text of this file |
| F1 | Littelfuse **KLDR025.TXP**: UL 248-4 Class CC, 25 A time-delay, 600 Vac, 200 kA; UL Listed E81895, CSA Certified LR29862 | ledger entry KLDR025.TXP (`native-21/verification/datasheet-ledger/ledger.json`, KLDR datasheet p.2, p.5) |
| F1 holder | 2 × Littelfuse **01250003H** open PCB clips (125 series, 30 A, UL Recognized E14721), soldered into plated slots. **No voltage rating and no CSA file printed** | ledger entry KLDR025.TXP (clip sheet Rev 02/07/18 p.1); `VR/08-manufacturing-package/native-21/fab/FAB-NOTE.md` |
| Protection scheme | Branch-circuit breaker plus F1. **No inlet fuse** | DECISIONS.md:335 |
| Prospective fault current at F1 | 4.7–8.4 kA (1.8 m / 1.0 m 14 AWG cord, stiff source, 127 V + 10 %). F1's 200 kA covers it 23.8× | `../../owner-items/f1cc/F1-RECOMMENDATION.md` §2 |
| F1 continuous capacity | 16.0 A at the 61 °C release bay air (25 A × 0.75 repo rule × about 0.855 rerating, p.6 curve, digitised ±2 %). At the 15 A inlet trip that is 0.9375 of capacity | ledger entry KLDR025.TXP |
| Line-current limit | **Firmware only.** Inlet regulated to 13.5 A, firmware trip at 15 A; power-stage hold 11.47–12.04 A; estimate error e_est 10 % (provisional). F1 never opens at 15–25 A | `VR/11-candidates/c53-line-current-f1/README.md`; ledger entry 1714971 (J1) |
| Hardware line-current trip | Designed (R5 averager + comparator, trip 13.88 A RMS-equivalent), **not built**: deferred by the owner on 2026-10-16 | DECISIONS 75; `VR/11-candidates/c53-r5-trip/DESIGN.md` |
| Inlet terminal J1 | Phoenix MKDS 5/2-9,5 (1714971): cULus E60425 use group B 30 A / 300 V, CSA 13631 group B 30 A. At F1's 25 A: 0.83 of the UL rating | ledger entry 1714971 |
| F1 clearing I²t vs board copper | KLDR025 clears 1,710 A²s; the narrowest copper on the s53 board holds 0.993 of that (fails by 0.7 %). The conductor-only ratio is 1.021 | `VR/02-protection-timing/shoot-through-f1/s53_necks.json` |
| Alternative fuse (owner question) | Bel Fuse 0ADEC9250-BE: 6.3 × 32 mm ceramic, 25 A fast, 500 V, 30 kA AC, cURus E20624 (UL 248-14 supplemental). Clears 470 A²s, so the copper ratio is 3.61. Saves $18.86 per board at 500 | `VR/12-decisions/f1-data/SURVEY.md` §1a; `f1_decision.py` gate G6 |
| Tank working voltage (design envelope, 28 A) | Coil terminals 345–362 V rms (line-cycle RMS) with a pan, ≤ 732 V pk. No-pan 28 A fault point 409 V rms / 818 V pk; firmware holds a 22 A no-pan clamp. Carrier-crest RMS would be about 518–583 V rms | `../../owner-items/m6m10/coil-voltage-28a/`; DECISIONS.md:248, 257 |

## Draft message (ready to send)

**To:** UL Solutions, Intertek (ETL) or CSA Group: an engineering inquiry or preliminary-review contact. Pick the mark
first; do not send to all three at once.

**Subject:** Pre-submission questions: Class CC fuse in PCB clips and overload protection in a 120 V induction cooktop

> Hello,
>
> We are preparing a countertop, cord-and-plug induction cooktop for certification in the US, Canada and Mexico
> (rated 120–127 V~ 60 Hz, NEMA 5-15P, 15 A). We believe the standard is [UL 858 / UL 1026; CSA C22.2 No. 64;
> NMX-J-521]; please correct us if not.
>
> **Protection as designed**
> - F1 is a Littelfuse KLDR025.TXP: UL 248-4 Class CC, 25 A time-delay, 600 Vac, 200 kA, UL Listed E81895,
>   CSA LR29862. It is the first device after the cord terminal, ahead of the EMI filter and the bridge rectifier.
> - F1 sits in two Littelfuse 01250003H open PCB clips (125 series, 30 A, UL Recognized E14721). The clip datasheet
>   gives no voltage rating and no CSA file.
> - There is no other fuse at the inlet. Branch protection is the building's 15 A or 20 A breaker.
> - Our bound for the prospective fault current at F1 is 4.7–8.4 kA (stiff source, 1.0–1.8 m of 14 AWG cord, 140 V).
> - The 15 A input limit is enforced by firmware from an estimate of line current (about 10 % estimate error). F1 does
>   not open at overloads between 15 and 25 A.
>
> **Questions**
> 1. Are the 01250003H open PCB clips acceptable as the holder for a Class CC fuse in this product (agency category,
>    voltage rating, accessibility, marking of the fuse rating near the clips)? What tests will you run on the
>    fuse-in-clip combination?
> 2. Is "branch breaker plus an internal Class CC fuse, no inlet fuse" an acceptable protection scheme?
> 3. Will you run an abnormal-operation test with the firmware current limit defeated? If so, which temperatures are
>    judged (cord terminal, filter choke, cord), at what current, and for how long? Please cite the clause.
> 4. Would you accept a UL-Recognized UL 248-14 supplemental fuse instead of the Class CC fuse: Bel Fuse 0ADEC9250-BE
>    (6.3 × 32 mm, 25 A fast-acting, 500 V, 30 kA AC, cURus E20624), in PCB clips, with the same fault-current bound?
>    If yes, under which conditions of acceptability, and must the end-product short-circuit test be run with it, at
>    what available current? Does the answer differ for CSA and NOM?
> 5. The resonant tank is a 35–60 kHz carrier under a 60 Hz envelope. For creepage under IEC 60335-1 Table 18 /
>    IEC 60664-4, is the working voltage the line-cycle RMS (362 V rms at our 28 A design point, with a pan) or the
>    carrier-crest RMS (about 518–583 V rms)? Is it the normal-use value, or must it include a firmware-prevented
>    no-pan fault point (409 V rms / 818 V pk)?
> 6. Can these be answered as a free pre-submission question, or do they need a quoted preliminary-review project?
>
> Best regards,
> [Name], [Company]
> [email] · [phone]
> Attachments: KLDR datasheet; Littelfuse 105/106/125 clip sheet; one-page fault-current bound; one-page coil-voltage
> summary.

## Owner choices before sending
- The target mark and lab (cULus / UL Solutions, ETL / Intertek or cCSAus / CSA), and UL 858 or UL 1026.
- Whether to ask question 4 at all. It saves $18.86 per board but reverses the Class CC choice
  (`../../owner-items/f1cc/F1-RECOMMENDATION.md`).
- If the clips are refused: an off-board Class CC holder. The F1 wire-out tabs of `VR/11-candidates/c53-stuck-on/S53-SCOPE.md`
  item 4 were **not built** at s53 (DECISIONS 75), so that would be a layout change at the inlet.
