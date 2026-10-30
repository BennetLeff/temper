# Datasheet audit brief: Temper LCR meter Rev F (shared by every audit agent)

You are auditing one subsystem of a 4-layer, 216-part PCB (an LCR meter derived from TI TIDA-060029) against the
manufacturer datasheets of its parts, before the first fabrication order. Nothing has been built yet; this is the
last desk check. Be a skeptical senior hardware engineer: the goal is to find real violations and missing
requirements, not to restate that things are fine.

## Where things are (all paths under /Users/bennet/Desktop/temper/worktrees/lcr-in-box/instruments/lcr-meter)

- `validation/datasheet-audit-rev-f/parts.txt`: every part with MPN, LCSC code, footprint and pin -> net.
- `validation/datasheet-audit-rev-f/nets.txt`: every net and its members (ref.pin).
- `cad/design.json`: the source the schematic is generated from (`parts[]` with values and notes, `notes`, `ranges`).
- `previews/schematic.pdf`: the schematic (Read can render PDF pages).
- Design docs explaining past decisions: `docs/rev-e-plan.md`, `docs/rev-e-front-end.md`, `docs/rev-e-range-switching.md`,
  `docs/rev-f-plan.md`, `docs/bring-up-rev-e.md`, `validation/power-spurs/README-rev-e.md`,
  `validation/power-spurs/regulator_check.json`, `validation/README.md` (verification receipt).
- Datasheet text already extracted (plain text, grep them): `sources/ti/*.txt` (OPA197, OPA2810, TPS2553, TPS65131,
  TPS7A30, TPS7A49, TIDUEU6 = the TI reference design guide), `sources/rev-e/TAC5112.txt`, `sources/rev-e/TQ2SA.txt`,
  `sources/new/*.txt` (AP2112, GD25Q16E, RP2040-datasheet, RP2040-hardware design guide, SS14), `sources/rev-f/*.txt`
  (BNC, LTST-S270KFKT).
- For parts without a local text: fetch the datasheet. LCSC product pages are https://www.lcsc.com/product-detail/<LCSC code>.html
  and carry a datasheet PDF link; manufacturer sites are fine too. Save any PDF you download under
  `/private/tmp/claude-501/-Users-bennet-Desktop-temper/786b719e-4ace-4e01-b253-18bb13157e8f/scratchpad/datasheet-audit/pdfs/`
  (its own directory; read PDFs with the Read tool or `pdftotext` if installed). Do not write into the repository.

## Rules

- Read-only on the repository. Do not edit, build, commit, run cargo or run KiCad. Do not use `git stash`.
- Cite every requirement: datasheet name + revision/date if shown + section/table/page, and quote the requirement verbatim
  (short). Compute numbers explicitly (show the arithmetic) and use worst-case corners (tolerance, temperature, DC bias on
  ceramics, input-voltage range: USB VBUS 4.40-5.5 V at the connector).
- Distinguish: VIOLATION (the board breaks a datasheet limit or requirement), RISK (within limits but marginal or depends on
  an unverified assumption), MISSING (the datasheet requires/recommends something the board lacks), OK-NOTE (checked, fine,
  only if it was non-obvious). Before reporting a VIOLATION, check the design docs above: if a past decision already
  argues it, say so and judge whether the argument holds against the datasheet text.
- Check for each part, as applicable: absolute maximum ratings vs worst-case board conditions; recommended operating
  conditions; every pin's connection (unused pins, strapping, pull-ups, enables, exposed pad); required/recommended external
  components and their values, types, voltage ratings and placement; power sequencing and start-up; clock/crystal load
  capacitance; thermal dissipation; footprint vs the datasheet land pattern (footprint files: `cad/LCR.pretty/*.kicad_mod`);
  ESD/protection; the part's role in the circuit making sense.
- Also list, separately, **debug/bring-up features worth adding** in your subsystem (test points, jumpers/0 ohm links,
  current-sense points, signal access), each with why and its cost/risk (for analog nodes, added capacitance matters: the
  loop-stability margin is tight).

## Output

Write your full report to
`/private/tmp/claude-501/-Users-bennet-Desktop-temper/786b719e-4ace-4e01-b253-18bb13157e8f/scratchpad/datasheet-audit/<GROUP>.md`
with: a table of findings (id, severity, ref(s), requirement with citation, board fact, why it matters, suggested fix),
then the debug-feature list, then a list of every part you checked with the datasheet you used (title, revision, URL or
local path). Your final message: the findings table and the debug list (keep it under ~1200 words).
