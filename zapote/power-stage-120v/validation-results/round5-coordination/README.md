# Round 5 execution and monitoring handoff

Execution base: `91888bb29e318eef09c0a292245de88b9016d250` on PR #1615. Follow [ROUND-5.md](../../validation-plan/ROUND-5.md), the [master](../../validation-plan/00-MASTER-PLAN.md) and [round-4 evidence](../round4-coordination/README.md). Native-17 active board SHA-256 is `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`. No PCB, source, component or firmware changes are authorized by this validation run. B stays held; C remains evaluation only.

## Dispatch

- R5-D1: Sol worker in `worktrees/ps-r5-d1`, owns only `01-switching-parasitics/round5/d1-extraction/`. [D1 handback](../01-switching-parasitics/round5/d1-extraction/README.md) is BLOCKED: corrected-unit fixtures and native-17 export pass, but native-contained link/barrel meshing fails acceptance. No accepted matrix or fallback exists; dependent D2/C1/C2 remain held.
- R5-B: [bench procedure](../../validation-plan/BENCH-SWITCHING.md) delivered by the Sol worker in `worktrees/ps-r5-bench`; eight source PDF hashes verified. Required matrix is both leg-A switches at 50/100/170 V up to 37 A. Leg B requires a separately reviewed direct SW_B fixture. No powered tests were performed.
- D2 and C1 wait for a qualified D1 model. C2 then depends on the board-model switching evidence. A worker's completed report does not qualify its numerical model.
- Round-4 archive: separately authorized Sol worker in `worktrees/ps-r5-archive`, owns only the new round-4 `raw-evidence/` transport tools and manifests. Coordinator publishes and owns all commits.

[Quality checks and independent review](QUALITY.md) record the transport fixes, input checks and limits.

Coordinator checkout remains `/Users/bennet/.codex/worktrees/ps-r4-integration/temper` to retain the raw evidence; its current branch is `codex/ps-r5-integration`.

### Port contract awaiting clarification

The plan describes four power ports plus one gate-drive and gate-return pair, but each leg has both high-side and low-side gate circuits. The coordinator asked the owner to choose eight ports per leg (recommended: four power ports and both gate drive/return pairs) or separate six-port models for each switch. Geometry/fixture checks continue; dependent model acceptance must wait for this answer. The native extraction retains the more detailed copper branches rather than silently dropping a gate circuit.

Narrowing a conductor can raise an isolated self inductance, but this does not establish a rigorous worst-case bound on every coupled matrix quantity or switching waveform. Geometry approximation and numerical convergence must remain explicit.

## Owner items

**O10, raw evidence:** The owner authorized publication of round 3 and GitHub split assets for round 4 during this run. [Round 3 is published](https://github.com/BennetLeff/temper/releases/tag/ps120-validation-round3-raw-v1): 3,327 files, archive SHA-256 `a4690f17bb2e4ccf4d9527bc3c114b0447a21d54375a7dd601de7c5be9eccd10`, GitHub asset digest verified. Round-4 packaging and full restore verification passed: five deterministic independent tar files, all below 1.5 billion bytes. Upload/publication status is recorded in the [round-4 archive README](../round4-coordination/raw-evidence/README.md). Neither evidence release authorizes fabrication or energization. Vendor models stay excluded.

**O11, related-board rebuilds:** Do not rebuild solely from the inherited flag claim. The current canonical candidates have no missing outer lands: RTD 0/14, thermal-sense 0/10, current-sense 0/6 PTH pads. [Native census](related-board-outer-lands.json) records exact hashes. [The script](check_related_lands.py) calls KiCad's `FlashLayer` and reproduces native-15's 88/116 affected pads as a negative control; native-17 has 0/116. [Run log](related-board-outer-lands.log) includes KiCad's GUI-initialization warnings and the completed counts. This checks outer-land presence only; it does not requalify those boards' geometry, electronics or fabrication. If another candidate revision was intended, audit that exact file before deciding to rebuild.

Run the census from any checkout with KiCad's bundled Python:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 zapote/power-stage-120v/validation-results/round5-coordination/check_related_lands.py
```

**O4, CTI:** An order-specific laminate guarantee remains missing. [FAB-JLCPCB.md](../../FAB-JLCPCB.md) contains the question ready to send. JLCPCB hosts a [KB-6165F datasheet](https://rs.jlcpcb.com/static/file/kb-6165f-datasheet.pdf) with typical CTI >175 V; that does not identify or guarantee the material supplied on this order. Obtain the laminate identity, guaranteed CTI ≥175 V and certificate traceability for the chosen four-layer 2 oz stackup. No message has been sent to JLCPCB by this run; public product data does not close O4.

**O9, assembly sourcing:** The native-17 export has 57 BOM groups: 36 SMD groups/98 components, 20 through-hole groups/36 components, and one transformer classified as other. All 57 exported `LCSC Part #` fields are empty; manufacturer part numbers are in their own column. The incorrectly named field is in the frozen source CSV, not a verified supplier match. A [catalog investigation](sourcing/README.md) now records 50 exact manufacturer/MPN candidates, including nine showing zero stock, plus seven unmatched lines. Package/land pattern, assembly process and rotations remain unqualified. F1 also lacks separately checked clip purchasing/assembly entries. Qualify candidates and agree consignment or hand assembly for unavailable parts. No substitute, consignment purchase, assembly order or part-field change is approved or performed here.

**Fab package detail:** Its own [independent review](../08-manufacturing-package/native-17/README.md) reports 353/354 via sides tented. Do not summarize that as every via side being tented. The package remains a candidate under [DECISIONS.md](../../DECISIONS.md).
