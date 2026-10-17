# S12: JLC laminate answer, public-source research (2026-10-17, done through the owner's Chrome and web search; nothing sent to JLC)

**Question (OPEN-ITEMS S12):** which recognised JLC 4-layer construction covers 4 L, 2 oz inner copper, 1.6 mm, CTI >= 175 V, and what
do we write in the order remark and `stackup.json`?

## What the public sources establish
| Fact | Source (read 2026-10-17) |
|---|---|
| JLCPCB's UL file is **E479892**, with 8 board classes, each with its own marking | https://jlcpcb.com/help/article/ul-certification (screenshot `shots/jlc-ul-table-2026-10-17.jpg`) |
| **JLC-4 = "FR-4 Multi-layer (4-32 layers)"**, marking "94V-0 E479892 JLC-4", lists **KB-6164 TG135**, S1141 TG140, KB-6165 TG155, S1000H TG155 and Shengyi S1000-2M TG170 | same page |
| JLC-1 (multi-layer 4-32) lists Nan Ya NP-140F and NP-155F; JLC-3 (single/two-layer) lists KB-6164-TG135, S1141 TG140, S1000H TG155 | same page |
| For JLC to add the UL marking the Material Type must be specified on the order; markings already in the Gerbers must match the type number | same page |
| The page gives **no board thickness, copper weights, or CTI** per class; the "Type Number" column is only the marking image | same page, text and screenshot |
| JLC's quote form offers Material Type "FR4 TG135", "FR4 TG155", "Nan Ya NP-140F", **"KB6164 - TG135"**, "Nan Ya NP-155F", "KB-6165 TG155", "S1141 TG140", "S1000H TG155"; multi-layer outer copper 1 / 2 oz, **inner 0.5 / 1 / 2 oz** (0.5 default) | JLC quote page and https://jlcpcb.com/capabilities/pcb-capabilities |
| Kingboard KB-6164: UL file **E123995** (the laminate maker's own listing, not JLC's), prepreg KB-6064, Tg 140 C, UL 94 V-0, CTI **175 V**, copper cladding offered up to 70 / 105 um | third-party hosted data sheets: https://www.mclpcb.com/wp-content/uploads/2021/05/king-board-KB-616420201117.pdf and https://a-contract.ru/fileadmin/datasheets/base-material/KB-6164.pdf (not re-read in full) |

## What is still not established (needs JLC or UL Product iQ, which needs a login)
1. Whether UL **E479892 JLC-4** with **KB-6164 TG135** is recognised for **2 oz (70 um) inner copper** at 4 layers, 1.6 mm. The earlier gap (S12) was
   that the laminate maker's rows list 35 / 54 um, with 102 um on the "F" grades. Nothing public here changes that.
2. Which CTI / PLC JLC's own UL listing states for JLC-4 with KB-6164 (the 175 V above is the laminate data sheet's).
3. Whether the same recognition holds for the ordering configuration (POFV via filling, ENIG, 2 oz outer).

## Where this leaves the order remark
The order remark we already use ("KB6164 - TG135", KB-6164 core with KB-6064 prepreg) names a material JLC lists in a 4-32 layer class and offers on its form with 2 oz inner
copper. It is the right choice to carry forward. What a JLC answer can still change is whether that class's UL recognition covers 2 oz inner copper; if not, the fallback
candidates in the same class are KB-6165 TG155, S1141 TG140 and S1000H TG155 (CTI of each is not established here).
