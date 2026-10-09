# Fab-house limits in KiCad's own DRC (fab pass)

> **For agentic workers:** superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** The vendor fab profile also drives KiCad's native DRC for the limits KiCad measures better than our P2 geometry: copper-to-copper spacing, hole-to-copper clearance per hole type, and silkscreen text size. `zapote-check` reports each violation as a located `FAB.<type>` finding.

**Measured facts (KiCad 10.0.4, probe boards in the session scratchpad):**
1. When several custom rules match, the **last one wins**, even if it is looser. Appending a 0.16 mm vendor clearance after a board's 1.0 mm safety rule replaced it. Appending vendor rules to a board's `.kicad_dru` could therefore silently weaken a safety rule.
2. A custom `clearance` rule overrides the netclass value; KiCad does not take the stricter of the two.
3. These rules are verified to fire, attributed as `(rule '<name>' …)`:
   - `hole_clearance` with `A.Type == 'Via'`, `A.Type == 'Pad' && A.Pad_Type == 'Through-hole'`, and `A.Pad_Type == 'NPTH, mechanical'`.
   - `text_height` and `text_thickness` on `F.SilkS`.
   - `clearance`.

**Design:**
- A **separate fab-only pass**. Copy the board and its `.kicad_pro` into the output directory, write a `.kicad_dru` containing only the vendor rules, and run `kicad-cli pcb drc` on the copy. The input board is never modified, and its own rules keep being checked in the native pass.
- Only violations whose description names a `zapote fab` rule become findings. Netclass and board-setup findings stay with the native pass.
- Limits already checked by P2 geometry (track width, drill size, ring, hole-to-hole, edge, board size) are **not** duplicated here.

**JLCPCB quotes (capabilities page, read 2026-10-08):**
- "Min. track width and spacing" (per profile, the second number)
- "Via hole to Track: 0.2mm"
- "PTH to Track: 0.28mm (0.35mm is recommended, minimum 0.28mm)"
- "NPTH to Track: 0.2mm"
- Legend: "Minimum Line Width: ≥0.15mm"
- Legend: "Minimum text height: 40 mil (1.0mm)"

Not covered: "Pad To Silkscreen 0.15mm" (no verified KiCad constraint) and the solder-mask bridge (no verified custom-rule constraint). The profile notes record both.

## Tasks
- [x] **T1** Profile limits:
  - New optional fields: `minimum_copper_clearance_mm`, `minimum_{via,pth,npth}_hole_to_copper_mm`, `minimum_silk_text_height_mm`, `minimum_silk_line_width_mm`.
  - Add quotes to the three JLC profiles.
  - The quote check stays strict. Text height is a derivation from "40 mil", because the quote puts 1.0 mm in parentheses.
  - Loader tests.
- [x] **T2** `zapote_drc::fab_rules::kicad_rules(&FabricationLimits) -> Option<String>`. It emits one `zapote fab …` rule per limit that is set, and `None` when none are. Unit tests cover the text and that unset limits are omitted.
- [x] **T3** `native_reports::drc_violations(drc)`, which parses a DRC report on its own. The existing `violations()` is reused.
- [x] **T4** `board_check`:
  - New `fab` check: copy board and project, write the rules, run `kicad-cli`, and turn each `zapote fab` violation into a `FAB.<type>` finding with actual/required values.
  - Record the rules file's hash in `report.json`.
  - Live test on committed probe fixtures (via, PTH, NPTH, silk) and on native-17.
- [x] **T5** Run on native-17, native-20 and the five units. Update `CHECKS.md`, then PR, CI and merge.

## Review focus
1. **Never touch the input board:** the copy goes in the new output directory, and the board hash is re-checked afterwards.
2. **No double-counting:** board or netclass violations must not be attributed to the fab pass (match on the rule-name prefix).
3. **Profile without native limits:** the fab check is absent, not passed.
4. **Missing `.kicad_pro`:** still run, using KiCad's defaults, and record that.

## Results (2026-10-08, KiCad 10.0.4, `zapote-check --assembly "THT wave and hand solder"`)

Rulings made during execution:
- A malformed `.kicad_dru` is skipped with exit 0, with no error (measured). The pass therefore runs the same rules first on a committed self-test board that breaks each rule (`zapote/tools/make_fab_selftest_board.py`). Any rule that does not fire there is a coverage gap.
- The board's project may switch off a check (`ignored_checks`). A fab rule depending on that check is then a coverage gap, not a pass.

Results:
- native-17 and native-20 (4-layer 2 oz): `fab` PASS on all 8 rules. All 137 visible silk texts are exactly 1.0 mm / 0.15 mm.
- The units fail on silk legend text of 0.8–0.9 mm, against the 1.0 mm minimum:
  - rtd: 40
  - current-sense: 21 height, 21 stroke
  - thermal-sense: 35
  - interlock: 29
  - gate-drive: 19 height, 26 stroke
- The interlock also fails on U4 pad-to-pad 0.15 mm, against the 2-layer 2 oz 0.16 mm spacing.
- These are design findings for the unit owners; the boards are unchanged here.

Reproduce a row: `make -C zapote check-board BOARD=$PWD/zapote/<unit>/candidate/section.kicad_pcb PROFILE=fab-profiles/<profile>.json ASSEMBLY="THT wave and hand solder"`, then read `[fab]` in `summary.txt`.

## Final review (fresh reviewer) and fix pass

- **I-1, regraded to Critical:** a pad or footprint local clearance overrides every custom rule (measured: a 0.05 mm pad override hid a 0.10 mm gap from the 0.16 mm rule).
  - The fab copy is now written by `tools/fab_board_copy.py` without those overrides. `report.json` lists what was cleared.
  - Zone clearance does not mask the rule (measured: a fill 0.05 mm from a track was reported with the zone at 0.05 mm), so zones are kept.
  - Test: `live_local_clearance_override_does_not_hide_a_fab_violation`. It was proven by mutation, not by a RED run: it fails when clearing is disabled.
  - None of the boards in the results carries such an override, so their results stand.
- **I-2:** the legend line width only reaches text strokes (KiCad has no constraint for silkscreen graphics). This is now stated in the profile notes, in `CHECKS.md` and in `report.json` `not_covered`.
- **Ruling (M-1):** hole rules are emitted loosest first. A via beside a PTH pad matches both rules and KiCad keeps the last, so the pair is judged at the stricter limit. Cost if wrong: occasional over-strict via findings near PTH pads, never a masked one.
- **M-2 and M-3:** attribution needs KiCad's leading `(rule '…'` clause and a matching type, and a mismatch is `FAB.REPORT_CONTRACT`. `fab_rules::rules` returns the rules as data instead of re-parsing text.
- **M-4:** the gap text names the limit-below-self-test cause.
- **M-5:** board bytes are passed in, and the fab pass's project hash must equal the native DRC's.
- **M-6:** tool and report failures are findings, not a lost run.
- **M-7:** the scope text is conditional, and the summary notes a missing project.
- **M-8:** added tests for the B-side thickness rule, impersonation, type mismatch and the fixture board hash.
- **M-9:** dates corrected.
- **M-10:** long lines wrapped.
- Two tests passed on first run, because the code existed before them: `a_profile_without_fab_pass_limits_has_no_fab_check` and `summary_says_when_the_fab_pass_ran_without_a_project`.
- Declined to judge, left as is: whether a board-setup minimum clearance floors the custom rules (only stricter, so it cannot mask), TrueType text thickness, and whether 4-layer inner layers deserve a separate spacing figure (the outer figure is conservative).
