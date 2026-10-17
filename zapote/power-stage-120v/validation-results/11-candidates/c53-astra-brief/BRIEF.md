# Brief for Astra agents (remote box): clear the open items before the prototype order

2026-10-16. Owner: Bennet. Repo base: `codex/power-stage-integration` at the commit named in the workspace's base commit. This brief
covers OPEN items 2-5 and 8-10 of the order checklist (`08-manufacturing-package/native-21/PROTOTYPE-LOT.md`, "Gates before
placing the order"). The ceiling question (item 11) is explained to the owner separately and is not an agent task.

Nothing in this brief authorises spending money, contacting a supplier, lab or JLC, or placing an order. See "Hard limits".

## Hard limits (apply to every agent, every item)

1. **No outreach, no order, no spend.** Do not send email, submit a quote or contact form, open a support ticket, add to a cart,
   check out, pay, create an account, or accept terms on any site. Research, reading, price and stock look-ups, and drafting text
   are allowed. A message that is ready to send is a deliverable (a file); the owner sends it.
2. **No credentials.** Never type, store or request a password, token or card number. If a site needs a login, stop and write
   "needs owner login" in the item's result. The owner logs in first (item 8 precondition below).
3. **Evidence, not claims.** Every number in a deliverable cites a file, URL, datasheet page or a re-runnable script in the
   workspace, with the read date. Anything read from a search snippet is labelled `SNIPPET, unverified`. If a page is blocked,
   say so; do not fill the gap from memory.
4. **Do not edit the design.** No change to `elec/`, copper, `fab/`, `DECISIONS.md` or `OPEN-ITEMS.md` in the owner's tree. Work in
   your own clone under `~/WS/<agent>`; propose changes as files under `results/<item>/` and as a patch (`git format-patch`).
   Never `git stash`; never rewrite history; never push.
5. **Box etiquette.** The box is shared and has frozen twice under heavy load (see `reference_remote_fem_box.md`). A 10-rank
   Elmer job (about 22 GB, 10 threads) is running for the S3 FEM and must not be disturbed. Before starting: `free -g` shows at
   least 25 GB available; `uptime` load below 14. Do not start any job above 4 GB or 4 threads. Never `pkill -f`; never kill a
   process you did not start. Pin to `taskset -c 6-11,18-23`. Stop after about 4 h or when an item is done.
6. **Computer use is allowed** for items 8 and 9 (browser only), within limits 1-3: take a screenshot before and after each
   state change, store them under `results/<item>/shots/`, and stop at any login wall, captcha, payment page or terms dialog.
7. **Stop and report** if two attempts at a step fail, if a tool is blocked, or if the evidence contradicts the repo. Do not
   work around a block.

## Agent split (one workspace each, at most two agents at once)

| Agent | Items | Needs |
|---|---|---|
| A | 2, 3, 4, 5 | repo files only, plus public web reading for 2 and 3 |
| B | 8, 9, 10 | browser (computer use) for 8 and 9; repo files for 10 |

## Item 2: JLC laminate answer (S12)

**Problem.** Kingboard KB-6164 (35 µm) and KB-6165 (54 µm) UL rows do not cover our 61 µm (2 oz) inner copper; KB-6164F / 6165F /
6167F list 102 µm; JLC's "TG155" option links KB-6165F. `native-21/stackup.json` still names Nan Ya NP-155F. DECISIONS 41 named
KB-6164 for CTI >= 175 V. (OPEN-ITEMS S12, B4.)

**Do.** Read JLC's public stackup, material and capability pages and the UL / CTI evidence already in the repo
(`08-manufacturing-package/native-21/sourcing/inquiries/CTI-RESEARCH-2026-10-14.md`). UL Product iQ needs a login: do not use it;
list exactly which lookups the owner must do and with which file numbers.

**Acceptance.** All of:
1. `results/s12/OPTIONS.md`: a table of every JLC 4-layer construction that could carry 2 oz outer + 2 oz inner copper and CTI >= 175 V
   (laminate name as JLC's order form words it, JLC stack code, board thickness, UL file, UL copper-weight scope, CTI value and
   its source), each row marked CITED or SNIPPET, with the gap that remains for each.
2. `results/s12/QUESTION-FOR-JLC.md`: a message ready to send, self-contained (board spec, the exact gap, what we need back in
   writing: laminate name, UL scope covering 61 µm inner copper, CTI statement), short enough to be answered in one reply.
3. `results/s12/STACKUP-PATCH-PLAN.md`: for each plausible answer, the exact edits to `stackup.json`, the FAB-NOTE laminate row,
   the PROTOTYPE-LOT laminate row and the order remark, written as diffs against the current text but **not applied**.
4. Nothing was sent to JLC.

## Item 3: inlet module with >= 100 µH differential-mode inductance per line

**Problem.** With L1 = B82726S2243A020 (8 µH stray) the s19b EMI model gives 6.03 / 1.57 dB (INCONCLUSIVE) with today's 2 x 41 µH
module and 11.14 / 6.95 dB (PASS) with >= 100 µH DM per line at 21 A. (OPEN-ITEMS B15, `MODULE-REQUEST.md` item 3.)

**Do.** Find catalogue inlet filter modules (IEC inlet with filter, 120 V, >= 15 A rating, UL / CSA recognised) whose DM
inductance per line can be established from a datasheet (leakage inductance of the CM choke or separate DM chokes). Use
`11-candidates/b15-proto-alternates/scripts/run_emi_l1.py` unchanged to compute the margins for each candidate's DM value.

**Acceptance.** All of:
1. `results/s3/SHORTLIST.md`: at least 3 candidates, or an explicit statement that fewer exist, each with maker, MPN, datasheet
   URL and page for the DM inductance (or the datasheet's silence on it), current rating, UL file, footprint fit against J1 /
   the inlet corner (x 213-289, y 0-58) and stock at two distributors read on the day.
2. For each candidate with a cited DM value: the margins from `run_emi_l1.py` (command line, output, and the script's own PASS
   rule quoted, not re-invented).
3. `results/s3/EMI-DEVIATION.md`: the written deviation the owner can sign if no module qualifies (what is not met, the s19b
   result with today's module, the fallback of fitting the 2203 L1 (12.37 dB) with its 29-week lead, and the bench
   pre-compliance step that decides).
4. A supplier message ready to send, in a file. Nothing was sent.

## Item 4: enclosure bosses H1-H8 against the enclosure revision in use

**Do.** The enclosure revision is R43 (`output/temper-manufacturing-r43`, handoff `design/r43/HANDOFF.md`; the fit-gate catalogue
is `validation-plan/enclosure-fit/r43-catalog-bboxes.json`, pose in `board_in_r43.py`). The board holes are in
`native-21/layout/board_only21.json` and `native-21/verification/D5-AUDIT.md`. The fit gate already maps board to world
(board x 91 = world x -50.0 at the tongue edge); reuse its transform.

**Acceptance.** All of:
1. `results/bosses/TABLE.md`: for every board mounting hole (FAB-NOTE says 7 M3 holes, H1-H7; the order checklist says H1-H8: report whether an H8 exists), the hole
   centre and diameter on the board, the matching R43 boss centre and screw size in the same frame, the planar offset, and the
   result against the repo's own tolerance. If the repo has none, state the offsets and flag any > 0.5 mm.
2. Every hole with no boss, or a boss with no hole, is listed.
3. The insulating-chain rule: FAB-NOTE says H2-H7 are fully insulating (nylon screw, washer, standoff; no metal within 10 mm)
   and H1 may take metal, but the chain's own hole list marks H2 as `metal`. Report the discrepancy, which source is current,
   and pass or fail per hole with the source line.
4. If anything fails: two options each with the edit (move the hole, or move the boss) and its consequence, not applied.
5. Every number is produced by a committed script under `results/bosses/`.

## Item 5: controller side (J13 rail merge, J4.1 dropped)

**Problem.** `11-candidates/c23-supply-topology/CONTROLLER-REQUEST.md` asks the controller owner to join J13 pin 1 (V15_BLW)
to the logic 15 V rail with a Schottky or ferrite bead plus bulk capacitance, and to remove the J4.1 15 V input path (J4.1 is
a single-pin SELV net on the power board). These must be in before any stage-38+ board is powered.

**Do.** Read `zapote/controller` (schematic source, firmware, docs) and report the state of each numbered request item.

**Acceptance.** All of:
1. `results/controller/STATUS.md`: one row per numbered item of the request: DONE (file and line, or commit), NOT DONE, or
   UNCLEAR (what is missing), plus the J13 loading re-check the request asks for (2.72 -> 2.97 A, 44.5 W at 15 V, JST VH on
   18 AWG) recomputed with the numbers shown.
2. For each NOT DONE item, a patch in your clone (not applied to the owner's tree) and the test or build that exercises it,
   run and its output pasted. If the controller repo area cannot be built on the box, say which check was not run.
3. A single verdict line: "controller ready to power a stage-38+ board: YES / NO, because ...".

## Item 8: the 23-part CPL preview in JLC's viewer (computer use)

**Precondition (owner).** The owner is logged in to JLCPCB in the browser the agent uses. If not, stop: "needs owner login".
Uploading the gerbers, BOM and CPL to JLC's quote / SMT order flow shares the design files with a third party and creates a
draft on the owner's account: the owner has asked for this check (2026-10-16) and nothing else.

**Do.** Use the s53 package: `fab/native-21-gerbers.zip` (SHA-256 `a6afd37a4f4e0039de8de7fd86755ff65328f21e43501a23d0904e78ffbd4ddc`),
`fab/bom-jlcpcb.csv`, `fab/cpl-jlcpcb.csv` and `owner-items/order/CPL-PREVIEW-CHECKLIST.md` (23 parts). Reach JLC's component
placement preview, and stop there: **no cart, no checkout, no payment.** Prefer the corrected CPL
(`cpl-rotation-audit/cpl-jlcpcb.corrected.csv`) only if the checklist says so.

**Acceptance.** All of:
1. `results/cpl/PREVIEW-RESULTS.md`: for each of the 23 refdes, a screenshot of JLC's preview with the part outlined, the
   observed rotation / pin-1 / polarity, and a verdict OK, WRONG (with the rotation JLC needs) or CANNOT SEE (why).
2. A proposed CPL correction file for every WRONG row (not applied), with the rotation arithmetic shown.
3. The 17 consigned designators are checked for the one thing JLC's tool shows about them (they should be absent from placement);
   report what JLC shows.
4. The draft the upload created is named in the report (title, date) so the owner can delete it; the agent does not delete
   anything on the account.
5. No order, cart or payment step was taken: state it explicitly.

## Item 9: M11 heatsink HOT-PE insulation stack parts sourced (computer use for the live checks)

**Basis.** `owner-items/m11-sourcing/M11-SOURCING.md` (research done on 2026-10-08, several rows `SNIPPET, unverified`, "the browser
agent must confirm them (§9)"), spec `owner-items/m11/RECOMMENDATION.md`, lot of 7 stacks (the lot is now 10-20 boards, so
recompute the quantities from the owner's figure of 20 boards plus spares; state the assumption).

**Acceptance.** All of:
1. `results/m11/CONFIRMED.md`: every row of the sourcing table re-read on the live site (stock, price at the quantity, lead time,
   MPN), each marked CONFIRMED with a screenshot and date, CHANGED (old and new), or UNAVAILABLE.
2. A recommended buy list (part, quantity for 20 boards plus a stated spare count, supplier, unit and total price, lead time),
   with the AlN plate, the thermal compound, the gap pad, the spreader bar, the comb spring and the FR-4/G-10 strip each
   either sourced or flagged as "needs an RFQ" with the RFQ text drafted. **No RFQ is sent.**
3. Total cost for the lot and the longest lead time, so the owner can see the critical path.
4. Anything in the stack that cannot be bought off a public page is listed with the reason.

## Item 10: bank pre-lot gate S25 on C22 (B32643H)

This gate is a **physical test**: OPEN-ITEMS S25 asks for a thermocouple on the hottest face of the hottest interior cap (C22)
in still air, passing at dT <= 20 K x F_T(T_A)^2 and T_A + dT <= 125 C. Agents cannot run it, and nothing in the repo
resolves it. What the agents can do is make the bench test fast and unambiguous, and re-check the model it checks.

**Acceptance.** All of:
1. `results/s25/BENCH-PROTOCOL.md`: the test as a procedure for one board: parts and fixtures needed (thermocouple type and
   placement on C22, still-air enclosure, 6.2 A / 35 kHz or the bench equivalent), the step ladder, the stop criteria, and a
   one-page data sheet with the pass numbers pre-computed for the measured T_A.
2. The model numbers reproduced by the committed tool: `11-candidates/bank28-air/scripts/bank_air_metric.py` and
   `s52-proto-bom/scripts/bank_voltage52.py`, run unchanged on the s53 board's copper, with the output pasted and any
   difference from the s52 figures (0.871 with radiation, 1.133 without; dT 17.62 / 29.58 K) explained.
3. A plain-language statement of what the model cannot tell us, and what result sends the lot back to the KNSCHA bank on the
   27.5 mm hole.
4. The verdict "S25: bench-gated; model supports / does not support proceeding to the order", never "closed".

## Report format

Each agent ends with `results/SUMMARY.md`: per item, DONE / PARTIAL / BLOCKED, what is in `results/`, what the owner must do
next (login, send a message, buy, run the bench test), and anything surprising. Commit often with the item number in the
message; keep `NOTES.md` current (dead ends included).
