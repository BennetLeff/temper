# Laminate CTI from public sources (2026-10-14): name KB-6164 on the order

This replaces the CTI part of the JLC inquiry (`CTI-JLC.md`, `CTI-JLC-6L.md`). The CTI value does not need JLC: the
laminate maker and UL publish it. All sources were read on 2026-10-14. Datasheets are not committed (repo rule); the
URLs are.

## KB-6164 (JLC "Material Type: KB6164 - TG135") is CTI PLC 3, on three primary records

| Record | Value | Source |
|---|---|---|
| UL Product iQ reprint, published by Kingboard on its UL certificate page; QMTS2 "Polymeric Materials … for Use in Fabricating Recognized PWBs – Component", "Last Updated on 2026-02-20" | **KB-616(X)** (footnote "X - may be 0, 4", so KB-6160 and KB-6164), FR-4.0, **CTI PLC 3 at 1.40 mm**; no CTI rating at 0.38 and 0.63 mm. Same rows in the Canadian reprint | kblaminates.com/list/28.html → kblaminates.com/upload/portal/20260224/202602241024184756.pdf (and …024424430.pdf); UL file **E123995** |
| Official Kingboard TDS KB-6164 / KB-6064 (PDF of 2025-03-13) | "CTI IEC60112 Etched/0.1% NH4CL V ≥175"; UL E123995 | kblaminates.com/upload/ueditor/20250313/KB-6164,KB-6064.pdf |
| Kingboard product table ("常规刚性材料") | KB-6164 CTI 175V, Tg 140 | kblaminates.com/list/196.html |

KB-6165 (Tg 153) has identical evidence: the UL row gives PLC 3 at 1.40 mm, and the TDS (…/20250313/KB-6165,KB-6065.pdf)
gives ≥ 175 V. Both grades are in JLC's UL board type JLC-4 (file E479892; jlcpcb.com/help/article/ul-certification).

PLC 3 is 175 ≤ CTI < 250 V, material group IIIa. That is the D5-BASIS requirement, with no margin. UL rates the bulk
laminate at 1.40 mm and gives no rating for thin cores; the finished board is 1.6 mm.

## The other JLC options are weaker

| Laminate | Best evidence |
|---|---|
| Shengyi S1141 / S1000H / S1000-2M | Shengyi TDS "CTI IEC60112 … PLC 3" (manufacturer TDS); no public UL data found |
| Nan Ya NP-140F / NP-155F | Only a 2009 distributor table (PLC 3). Nan Ya's own TDSs (NP-155F rev. 2025-10-27; NP-140F hosted by JLC) and its UL 746E report (E98983, 2018) give no CTI |

No JLC-selectable laminate has public evidence of PLC 2 or better. Kingboard's PLC 0 grades (KB-6160C, KB-6165C)
are not on JLC's menu.

## Price (JLC quote form, 2026-10-14, 4 L, 500 boards)

Naming the laminate costs: KB6164 +$140.02 ($0.28 per board), NP-140F +$231.17 ($0.46), NP-155F +$371.19 ($0.74).
The unnamed "FR4 TG135" option carries no material statement at all.

## What JLC publishes on the rest

- **Thickness:** "± 10%" for boards ≥ 1.0 mm (jlcpcb.com/capabilities/pcb-capabilities), so 1.6 mm nominal can finish
  at 1.44 mm. JLC publishes no tighter option. The FAB-NOTE's 1.6 mm minimum (REDCUBE THR studs, review m7) is
  therefore **not** guaranteed at 1.6 mm nominal.
- **Certificates:** no per-order CoC or material certificate is offered on JLC's pages. The certifications page says
  base materials are "chosen at our discretion or specified by you during ordering".
- **"No requirement" stack:** not a fixed build. JLC's pages disagree with each other, and JLC's API data (as scraped by
  gsuberland, 2025-05-20) maps 4 L 2 / 2 oz NOREQ to the 3313 build and 6 L NOREQ to JLC061622-1080, not 1080A.
  Always name the stack.
- **JLC on CTI:** only a blog line, "standard FR4 (around 175V)" (jlcpcb.com/blog/cti-value-high-voltage-pcb).

## Still only JLC can answer (not blocking)

1. Whether naming KB-6164 also fixes the prepreg (Kingboard KB-6064) in the named JLC041622-7628 build. The outer
   dielectric is prepreg, and JLC's impedance data assumes NP-155F. Put it in the order remark: "Material KB-6164 core
   with KB-6064 prepreg throughout".
2. A per-order certificate naming the laminate. None is published; ask for it in the order remark.
