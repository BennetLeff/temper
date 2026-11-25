# JLC laminate UL scope question (OPEN-ITEMS S12), 2026-10-18

Status: **sent 2026-11-24** to support@jlcpcb.com (owner-approved; text as below, signed, no customer ID). **Reply received 2026-11-25: partial** (see the end). It replaces the CTI-only drafts `../sourcing/inquiries/CTI-JLC.md` and
`CTI-JLC-6L.md`, which were never sent (DECISIONS 41 settled CTI from public records). This one asks about UL scope for
2 oz inner copper, which public records do not settle. Certifier side of the same question: `CERTIFIER-PACKET.md` A3 #25.

Paths are relative to PS = `zapote/power-stage-120v`, except `fab/` and `../sourcing/`, which are under
`validation-results/08-manufacturing-package/native-21/`.

## Why we ask

- The board is 4 layers, 1.6 mm, **2 oz outer and 2 oz inner**, JLC stack JLC041622-7628. `native-21/stackup.json` gives
  F.Cu / B.Cu 0.070 mm and In1 / In2 0.061 mm, a 0.5 mm core and 7628 + 2116 + 2116 prepregs.
- The order names Kingboard **KB-6164** core with **KB-6064** prepreg (JLC "KB6164 - TG135", +$0.28 per board at 500), for
  CTI ≥ 175 V (DECISIONS 41; `fab/FAB-NOTE.md` Laminate row; `stackup.json` layer materials).
- Kingboard's UL file E123995 lists a maximum internal copper of **35 µm** for KB-616(X) (KB-6160 / KB-6164) multilayer
  boards. Our inner copper is 61 µm. KB-6164F and KB-6165F list 102 µm (DECISIONS 51; re-read below).
- So the laminate we named for CTI may be outside its UL multilayer scope with our inner copper. Only JLC knows which
  recognised construction its JLC-4 board type (UL E479892) uses for this build.

## Message (paste into JLC's PCB inquiry form or support@jlcpcb.com; ask for a written reply)

**Subject:** Pre-order: UL-recognised laminate for 4-layer 1.6 mm, 2 oz outer and 2 oz inner, CTI ≥ 175 V

> Hello JLCPCB team,
>
> We will order a 4-layer FR-4 board: 1.6 mm, **2 oz outer and 2 oz inner copper**, stackup **JLC041622-7628**,
> 290 × 190 mm, ENIG, epoxy-filled and capped vias. It carries 120 V mains. We need the laminate to be UL-recognised
> for this construction and to have **CTI ≥ 175 V (UL PLC 3 or better)**.
>
> We planned to select Material Type "KB6164 - TG135" (Kingboard KB-6164 core, KB-6064 prepreg). Kingboard's UL file
> **E123995** (Product iQ reprint, last updated 2026-02-20) lists, for multilayer boards:
> - KB-616(X) (KB-6160 / KB-6164, prepreg KB-6060 / KB-6064): max internal copper **35 µm**; CTI PLC 3 at 1.40 mm;
> - KB-6165 (prepreg KB-6065): max internal copper **54 µm**; CTI PLC 3 at 1.40 mm;
> - KB-6164F (prepreg KB-6064F): max internal copper **102 µm**; CTI PLC 3 at 1.40 mm;
> - KB-6165F (prepreg KB-6065F): max internal copper **102 µm**; CTI PLC 3 at 1.40 mm.
>
> Our inner copper is 2 oz (about 61 µm finished in your stack data), which is above the 35 µm and 54 µm rows.
>
> Please answer in writing:
> 1. For this build (4 layers, 1.6 mm, 2 oz / 2 oz, JLC041622-7628), which laminate and prepreg do you use, and under
>    which UL-recognised construction? Please give the **UL file number** and the board type (for example JLC-4 under
>    E479892), and confirm that its recognition covers **2 oz inner copper**.
> 2. If "KB6164 - TG135" does not cover 2 oz inner copper, which Material Type option does (for example KB-6164F or
>    KB-6165F, or your "TG155" option), and at what extra cost?
> 3. What is the **maximum operating temperature (MOT)** of that recognised board construction?
> 4. What is its **CTI** (IEC 60112) or UL PLC? We need 175 V / PLC 3 or better.
> 5. Is the prepreg in this stack from the same laminate family (for example KB-6064 or KB-6064F with KB-6164 / KB-6164F)?
> 6. Can the laminate, prepreg and UL file be stated on the shipping documents or a certificate for our order?
>
> Thank you.
> [Name], [Company] · [email] · [JLC customer ID]

## After the reply

- Record the reply (date, agent, ticket) here and in `fab/FAB-NOTE.md`.
- If the material type changes: change the FAB-NOTE Laminate row, the order remark and `native-21/stackup.json` together
  (OPEN-ITEMS S12, B4). A different core changes dielectric data only if JLC says so; re-run the thickness-dependent
  chain if the stack changes.
- Send the answer to the certifier with packet A3 #25.

## Web research, 2026-10-18 (what public sources say)

| # | Finding | Source (read 2026-10-18) | Confidence |
|---|---|---|---|
| 1 | JLC's UL identification number is **E479892**. Board type **JLC-4** (FR-4 multilayer, 4–32 layers) lists "KB-6164 TG135", "S1141 TG140", "KB-6165 TG155", "S1000H TG155", "Shengyi S1000-2M - TG170". **JLC-1** (FR-4 multilayer) lists Nan Ya NP-140F and NP-155F. The page gives **no copper limits, no MOT and no CTI**. "Last updated on Sep 09, 2026" | https://jlcpcb.com/help/article/ul-certification | Confirmed (JLC page) |
| 2 | Kingboard UL reprint, E123995, "Last Updated on 2026-02-20". **Max internal copper (µm), multilayer metal-clad rows:** KB-616(X) (laminate KB-6160 / KB-6164, prepreg KB-6060 / KB-6064) **35**; KB-6165 / KB-6065 **54**; KB-6164F / KB-6064F **102**; KB-6165F / KB-6065F **102** (204 at 0.63 mm build-up); KB-6167F / KB-6067F **102**. Max external copper 102 µm on each. Max operating temperature **130 °C** on each. Footnote "X - may be 0, 4" | https://www.kblaminates.com/upload/portal/20260224/202602241024184756.pdf (US reprint; linked from https://www.kblaminates.com/list/28.html as "E123995 UL Certified for America 2026-02-20"). Read with `pdftotext -layout`; local copy sha256 4f1908004928cc95… (not committed) | Confirmed (Kingboard-published UL reprint) |
| 3 | Same reprint, industrial-laminate table (columns HWI / HAI / HVTR / **CTI**): at 1.40 mm, **CTI 3** (PLC 3) for KB-616(X), KB-6164F, KB-6165 and KB-6165F. At 0.38 mm and 0.63 mm the CTI column is blank for all four | same PDF | Confirmed for 1.40 mm; no CTI rating at 0.38 / 0.63 mm |
| 4 | Kingboard TDS "KB-616XF (Lead Free Series)": Tg 140 °C (KB-6164F), 150 °C (KB-6165F), 170 °C (KB-6167F) by DSC; purchasing table "CTI Value 175V"; copper cladding offered 18 / 35 / 70 µm | distributor-hosted copy https://www.intectiv.si/wp-content/uploads/2023/08/Technical-data-sheet-KB-6165F-min.pdf (undated; uploaded 2023-08 per URL) | Manufacturer document via a distributor; revision not stated |
| 5 | JLC capabilities page: inner copper "0.5 oz / 1 oz / 2 oz"; FR-4 "Grade A laminates from suppliers including Nan Ya, KB, Shengyi and etc."; thickness ± 10 % for ≥ 1.0 mm. No CTI, UL or certificate statement | https://jlcpcb.com/capabilities/pcb-capabilities | Confirmed (JLC page) |
| 6 | JLC base-material article names no laminate brand, gives TG130 and TG155 only, and says nothing about CTI or UL. "Last updated on Sep 09, 2026" | https://jlcpcb.com/help/article/jlcpcb-base-material | Confirmed (JLC page) |
| 7 | **Unconfirmed:** that JLC's "TG155" Material Type links the KB-6165F datasheet (DECISIONS 51). No JLC page found today states which laminate the TG155 option uses; one forum post ties TG155 to NP-155F for impedance | DECISIONS.md:1749; web search 2026-10-18 | Unconfirmed |
| 8 | **Unconfirmed:** whether JLC's own board recognition (E479892) carries a copper limit of its own for JLC-4. UL Product iQ needs a login and was not read | — | Unconfirmed: this is question 1 |

What this means, in one line each:
- The 35 µm limit on KB-616(X) is confirmed on the current UL reprint, so "KB6164 - TG135" with 2 oz inner copper is
  outside the laminate file's multilayer row as published.
- KB-6164F and KB-6165F cover 102 µm with the same PLC 3 and 130 °C MOT, so they would fix the scope without changing CTI
  or the thermal limit B3 uses (`b3-ratings` laminate row, MOT 130 °C, DECISIONS 46).
- Whether JLC can supply either, under which Material Type, is the open question.

## Reply, 2026-11-25 (summary)

| Question | Answer |
| --- | --- |
| 1 Laminate, prepreg, UL file / type, 2 oz inner | **Not answered**; points to JLC's UL page and a stackup image |
| 2 Which option covers 2 oz inner | "KB-6164 TG135": the option we asked about, with no statement on copper weight |
| 3 MOT | 130 °C |
| 4 CTI / PLC | 175–250 V, PLC 3 |
| 5 Prepreg family | **Not answered** ("select the stackup on the website") |
| 6 Documents | UL marking can be ordered; documents **not answered** |

JLC's UL page (last updated 2026-11-10) lists KB-6164 TG135 and KB-6165 TG155 under JLC-4 (E479892, 4–32 layers). It states no copper weight, MOT or CTI,
and does not list KB-6164F or KB-6165F. The marking may be left off "without prior notice" if there is no room (choose Specify Position).

## Follow-up draft (NOT sent)

> Thank you. Two points are still open for our 4-layer, 1.6 mm, 2 oz outer / 2 oz inner board (JLC041622-7628):
> 1. Kingboard's UL file E123995 limits KB-6164 / KB-6064 multilayer internal copper to 35 µm. Our inner copper is about 61 µm. Does your UL recognition
>    E479892, type JLC-4, cover KB-6164 TG135 with 2 oz inner copper? Please answer yes or no, and state the maximum inner copper weight.
> 2. If no: which Material Type that you can supply (for example KB-6165 TG155, KB-6164F, KB-6165F, S1000H) is recognised with 2 oz inner copper
>    and CTI PLC 3 or better, with which prepreg, and at what extra cost?
