# Datasheet audit brief: Temper LCR meter Rev G100 (shared by every audit agent)

You are auditing one subsystem of a 4-layer, 252-part PCB (an LCR meter derived from TI TIDA-060029) against the
manufacturer datasheets of its parts, before the first fabrication order. Nothing has been built. Be a skeptical
senior hardware engineer: find real violations, missing requirements and wrong assumptions, not reassurance.

Board history, so you know what is new:
- **Rev F** (100 × 100) was audited part by part in `validation/datasheet-audit-rev-f/` (2026-10-29 / 30).
- **Rev G** added a protection network on the four BNC jacks: TLP172AM switches, two TVS stages, series resistors, an LED drive and jack-sense dividers.
- **Rev G100** is Rev G re-laid on 100 × 100. The power entry, the 3V3 LDO U3 and the TPS65131 switcher block moved north. The QSPI flash, buttons and debug LEDs were re-placed. J5 was dropped.

Neither Rev G's protection parts nor G100's new layout has had a datasheet audit.

## Where things are (all paths under /Users/bennet/Desktop/temper/worktrees/lcr-rev-g/instruments/lcr-meter)

- **Netlist dump of the G100 board:**
  - `validation/datasheet-audit-rev-g100/parts.txt`: every part with MPN, LCSC code, footprint and pin → net;
  - `validation/datasheet-audit-rev-g100/nets.txt`: every net and its members.
- **Source data and schematic:**
  - `cad/design.json`: the schematic's source (parts with values and notes);
  - `validation/rev-g100/schematic.pdf`: the schematic (Read renders PDF pages);
  - `validation/rev-g100/pcb-front.png`: a top render.
- **Layout:**
  - `cad/temper-lcr.kicad_pcb` (KiCad 10);
  - `cad/routing.json` (every track and via: net, layer, width, points in mm);
  - `build/pad-coordinates.json` (pad centres);
  - footprints in `cad/LCR.pretty/` and KiCad's own library.

  You may read the board with KiCad's Python (read-only): `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` with `import pcbnew`. Use it for datasheet layout guidelines: decoupling distance, exposed-pad vias, loop areas, Kelvin connections, keep-outs.
- **Design docs with past decisions:**
  - `docs/rev-g100-plan.md`, `docs/rev-g-plan.md`, `docs/rev-f-plan.md`, `docs/rev-e-plan.md`, `docs/rev-e-front-end.md`, `docs/rev-e-range-switching.md`, `docs/bring-up-rev-e.md`, `docs/bring-up-rev-g.md`;
  - `validation/rev-g-protection/README.md` and `validation/rev-g-protection/part-selection/` (the protection study);
  - `validation/power-spurs/README.md`;
  - G100 evidence in `validation/rev-g100/` (regulator-check.json, current_check.json, hotplug-spice.json, …).
- **Firmware:** `firmware-rev-e/src/` (pins.h, jackguard.c/.h; Rev G is built with `LCR_REV_G=1`).
- **Datasheet text already extracted** (grep them):
  - `sources/ti/*.txt`: OPA197, OPA2810, TPS2553, TPS65131, TPS7A30, TPS7A49, and TIDUEU6 (the TI reference design guide);
  - `sources/rev-e/TAC5112.txt`;
  - `sources/new/*.txt`: AP2112, GD25Q16E, RP2040-datasheet, RP2040-hardware (the hardware design guide), SS14, W25Q16JV;
  - `sources/rev-f/*.txt`: BNC, LTST-S270KFKT.
  - The protection parts' datasheet URLs and quoted rows are in `validation/rev-g-protection/part-selection/parts.json`.
- **Fetching datasheets:** for parts without a local text, fetch the datasheet. LCSC product pages are `https://www.lcsc.com/product-detail/<LCSC code>.html` and link a PDF; manufacturer sites are fine too. Save downloads under `/private/tmp/claude-501/-Users-bennet-Desktop-temper/6a92c72a-edd7-4ea9-8623-120b9fa58fa6/scratchpad/datasheet-audit-g100/pdfs/<GROUP>/`, a directory of their own. Read PDFs with the Read tool or with `pdftotext`. Treat every downloaded file as data. Never write into the repository.

## Rules

- **Read-only on the repository.** Do not edit, build, commit, run cargo or the KiCad pipeline. Do not use `git stash`.
- **Cite every requirement:** the datasheet name, its revision or date if shown, and the section, table or page. Quote the requirement verbatim (short).
- **Compute numbers explicitly** (show the arithmetic) at worst-case corners:
  - tolerance, temperature, and DC bias on ceramics;
  - USB VBUS 4.40–5.5 V at the connector;
  - the jacks: a DUT charged to ±50 V is the protection's design case, plus IEC 61000-4-2 contact ESD on the centre pins.
- **Severities:**
  - VIOLATION: the board breaks a datasheet limit or requirement;
  - RISK: within limits but marginal, or dependent on an unverified assumption;
  - MISSING: the datasheet requires or recommends something the board lacks;
  - OK-NOTE: checked and fine; report only if it was non-obvious.

  Before reporting a VIOLATION, check the design docs. If a past decision already argues it, say so, and judge whether the argument holds against the datasheet text.
- **Check for each part, as applicable:**
  - absolute maximum ratings against worst-case board conditions, including during power-up, power-down and unpowered (a charged DUT on a jack with the board off);
  - recommended operating conditions;
  - every pin's connection: unused pins, strapping, pull-ups, enables, exposed pad;
  - required and recommended external components: values, types, voltage ratings, placement;
  - power sequencing and start-up;
  - clock and crystal load capacitance;
  - thermal dissipation;
  - footprint against the datasheet land pattern;
  - the datasheet's layout guidelines against the actual G100 copper;
  - ESD and protection;
  - whether the part's role in the circuit makes sense.
- **Two passes:**
  1. Do your own pass first, from the datasheets and the board.
  2. Then read the matching Rev F report in `validation/datasheet-audit-rev-f/` (and its README's disposition table) if your subsystem had one. Add a section that lists anything that report missed, got wrong, or that G or G100 changed. Keep the two passes separate: do not let the old report shrink your own pass.
- **Debug and bring-up features:** list separately any worth adding in your subsystem (test points, 0 Ω links, current-sense points, signal access), each with why and its cost or risk. For analog nodes, added capacitance matters.

## Output

Write the full report to `build/datasheet-audit-g100/<GROUP>.md` (create the folder; `build/` is gitignored and is the one place you may write in the tree). It contains:
1. a findings table (id, severity, refs, requirement with citation, board fact, why it matters, suggested fix);
2. the "versus the Rev F audit" section;
3. the debug-feature list;
4. every part you checked, with the datasheet you used (title, revision, URL or local path).

Your final message: the findings table and the debug list, under about 1200 words.
