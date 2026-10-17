# S12 patch plan (NOT applied)

`native-21/stackup.json` still names Nan Ya NP-155F (OPEN-ITEMS S12); the order remark (FAB-NOTE, PROTOTYPE-LOT, ORDER-PACKAGE) names KB-6164 TG135 with KB-6064 prepreg.
- **If JLC confirms JLC-4 / KB6164 - TG135 covers 2 oz inner copper:** change `stackup.json` laminate to KB-6164 (core) / KB-6064 (prepreg), keep the order remark, close S12 and B4.
- **If JLC says KB-6164 does not cover 2 oz inner:** take the class member JLC names (KB-6165 TG155, S1141 TG140 or S1000H TG155, all in JLC-4), re-check its CTI against the >= 175 V
  condition (DECISIONS 41, CTI-RESEARCH-2026-10-14.md), then change `stackup.json`, the FAB-NOTE laminate row, the PROTOTYPE-LOT laminate row and the order remark together.
- **If JLC will not state coverage:** the laminate stays a recorded open point for the lab (S12) and the order proceeds on KB6164 - TG135 as the best-evidenced choice.
