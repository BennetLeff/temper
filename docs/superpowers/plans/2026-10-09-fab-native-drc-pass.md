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

**JLCPCB quotes (capabilities page, read 2026-10-09):**
- "Min. track width and spacing" (per profile, the second number)
- "Via hole to Track: 0.2mm"
- "PTH to Track: 0.28mm (0.35mm is recommended, minimum 0.28mm)"
- "NPTH to Track: 0.2mm"
- Legend: "Minimum Line Width: ≥0.15mm"
- Legend: "Minimum text height: 40 mil (1.0mm)"

Not covered: "Pad To Silkscreen 0.15mm" (no verified KiCad constraint) and the solder-mask bridge (no verified custom-rule constraint). The profile notes record both.

## Tasks
- [ ] **T1** Profile limits:
  - New optional fields: `minimum_copper_clearance_mm`, `minimum_{via,pth,npth}_hole_to_copper_mm`, `minimum_silk_text_height_mm`, `minimum_silk_line_width_mm`.
  - Add quotes to the three JLC profiles.
  - The quote check stays strict. Text height is a derivation from "40 mil", because the quote puts 1.0 mm in parentheses.
  - Loader tests.
- [ ] **T2** `zapote_drc::fab_rules::kicad_rules(&FabricationLimits) -> Option<String>`. It emits one `zapote fab …` rule per limit that is set, and `None` when none are. Unit tests cover the text and that unset limits are omitted.
- [ ] **T3** `native_reports::drc_violations(drc)`, which parses a DRC report on its own. The existing `violations()` is reused.
- [ ] **T4** `board_check`:
  - New `fab` check: copy board and project, write the rules, run `kicad-cli`, and turn each `zapote fab` violation into a `FAB.<type>` finding with actual/required values.
  - Record the rules file's hash in `report.json`.
  - Live test on committed probe fixtures (via, PTH, NPTH, silk) and on native-17.
- [ ] **T5** Run on native-17, native-20 and the five units. Update `CHECKS.md`, then PR, CI and merge.

## Review focus
1. **Never touch the input board:** the copy goes in the new output directory, and the board hash is re-checked afterwards.
2. **No double-counting:** board or netclass violations must not be attributed to the fab pass (match on the rule-name prefix).
3. **Profile without native limits:** the fab check is absent, not passed.
4. **Missing `.kicad_pro`:** still run, using KiCad's defaults, and record that.
