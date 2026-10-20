# Audit pass 4: contradiction register, third batch (2026-10-20)

Same rules as passes 1 and 2: verdicts rest on source lines read in this pass; no source document edited. SR3 = `output/temper-sensor-r3` (main checkout, untracked). CJ = controller worktree `zapote/controller`.

| # | Verdict | Basis | Fix still to make |
|---|---|---|---|
| C23 rim cross-check threshold | **25 K.** The pcb DECISIONS (file time 2026-10-15 00:48) says 15 K would trip D1 probes on a correct pan; HANDOFF (2026-10-14 23:16) with 15 K is the older text | SR3/pcb/DECISIONS.md:170-171; SR3/HANDOFF.md:339-340 | Correct HANDOFF.md. Dates here are file modification times, not decision dates |
| C24 rim ADC | **GPIO9 on the captured design; ADS1115 rejected.** The same pcb DECISIONS (D5) says ADC1 is no longer full, 0.057 K worst-case error over 100–280 °C, and an ADS1115 would not move the 10.2 K sensor-tolerance error | SR3/pcb/DECISIONS.md:150-162; HANDOFF.md:230-232 | Correct HANDOFF.md. Note the design saturates below 93 °C by intent, so the rim reading is blind below that |
| C27 inlet fuse | **No inlet fuse (R28).** The same file says so at line 10 and calls the MDA-30-R questions obsolete at line 80. Lines 17 and 40 are leftover text | R43/design/r32/CERTIFICATION-QUESTIONS.md:9-10, 17, 40, 80 | Delete lines 17 and 40 when R44 opens. The certifier packet must not quote them |
| C28 coil spec rows | **Internal contradiction in the spec.** Line 59 says rows 1–7 are stale (88 µH), but rows 1 and 7 now say 70 µH and 76 A | docs/hardware/TANK_COIL_SPECIFICATION.md:36, 43, 59 | Reword line 59 to name the rows that are still stale. I did not check rows 2–6 |
| C29 coil README on the spec | **README is stale.** Line 253 says this branch's committed copy is the stale 88 µH version, but commits dd8e7962d and 93b9ea185 put the corrected spec on this branch | COIL/README.md:253; `git log` on the spec file | Edit line 253 |
| C18 J4 Molex drawing | **Partly both.** LAYOUT.md records the header drawing (430451600_sd.pdf) as owner-supplied and read 2026-10-12, not committed. ORDER.md:108 says the "sales drawing" is still unread and refers to molex.com refusing the network; LAYOUT.md also says the plug's product drawing (430251600_sd) is still needed | CJ/ORDER.md:108; CJ/LAYOUT.md:245-254 | Commit the header drawing (it was owner-supplied) or record its hash; fix ORDER.md to say which drawing is unread |
| C19 J4 mating side | **Not settled.** ENCLOSURE-HANDOFF.md:27 says "mating +X"; LAYOUT.md:227 says "mating −X at the left edge". The courtyard is at X −38 to −24 and the two files may use different frames, which I did not resolve. JLC's viewer (2026-10-19) showed the J4 body inside the outline at KiCad's rotation | CJ/ENCLOSURE-HANDOFF.md:27; CJ/LAYOUT.md:227; PREVIEW-2026-10-19.md | Resolve against the 3D model and the CPL rotation before the enclosure cutout for the plug is drawn. This is a mechanical-interface item: the plug must be reachable |
| C25 CR-5 resistor | **Could not verify.** `grep` of SR3/firmware/DECISIONS.md finds neither "76.8" nor "86.6" in this checkout, so the {OM} (origin/main) cite is to a different version of that file | SR3/firmware/DECISIONS.md | Read the origin/main copy, or drop the entry |

## Still not re-checked after four passes
C1 (needs bench), C8, C11, C17, C26, C30, C31, C32, C34, C35.

## Running tally (24 of 35 looked at)
- Stale documentation with a known answer: C3, C6, C7, C9, C12, C13, C16, C21, C23, C24, C27, C28, C29, C33 (14).
- Not a contradiction: C10. Cosmetic: C20. Deliberate hold: C22.
- Real engineering gaps: C2, C4/C5, C15 (4 entries).
- Open and needing a check or a decision: C18, C19, C25.
