# Audit pass 2: contradiction register, second batch (2026-10-19)

Same rules as pass 1: verdicts rest on source lines read in this pass; no source document edited. PS = `zapote/power-stage-120v`, FW = `firmware`.

| # | Verdict | Basis | Fix still to make |
|---|---|---|---|
| C9 BR1 gap pad | **1.0 mm (0.040") is the later decision.** PS/DECISIONS.md:421 says BR1's pad "becomes the 1.0 mm (0.040") grade" and :476 "keeps the 1.0 mm Gap Pad"; :275 and :301 are the earlier 0.5 mm text (part number GPHC3.0-0.020-02-0816 at :301). I did not read the item dates, so the order is inferred from the word "becomes" | PS/DECISIONS.md:275, 301, 421, 476 | Mark :275 and :301 superseded; the ordered part number must be the 0.040" grade. Check the stack height in SINK-DRAWING-NOTES |
| C10 clamp force | **Not a contradiction.** 60–80 N per device is the design target (:276); 45–102 N is the acceptance window (:474) | PS/DECISIONS.md:276, 474 (OI/m11/RECOMMENDATION.md:235 not re-read) | None; say "target" and "acceptance" in both places |
| C13 J13 merge | **Landed on `controller-j13-merge`, not on any other controller branch.** DECISIONS item 79 (2026-10-18) records it; PROTOTYPE-LOT item 8 ("not done on any controller branch") predates it. The controller worktree HEAD is e710d9d91 on that branch | PS/DECISIONS.md:3049-3050; PROTOTYPE-LOT.md:156-158; controller `git log` | Update PROTOTYPE-LOT item 8 |
| C15 IDF build as proof | **Real gap.** DECISIONS says the CI IDF build is the proof for the J13 ESP-IDF files, but `release-artifacts.yml` runs only on `release: published`, so no push or PR builds them | PS/DECISIONS.md:3051; .github/workflows/release-artifacts.yml:1-6 | Either add an IDF build to PR CI or run `build.sh` once and record it. Needs the owner's call on CI cost (CI is capacity-bound) |
| C16 IDF compile status | **Kconfig help is stale.** The build evidence records a clean configure, compile and strict link on 2026-10-12 (branch `fw/platform`, esp32s3, GCC 13.2.0, HW_BINDING=y). But that predates the J13 edits of 2026-10-18, so those files remain uncompiled (see C15) | FW/components/power/Kconfig:5-10; FW/build-evidence/esp-idf/README.md | Reword the Kconfig help; re-run the build after the J13 edits |
| C21 UI controls | **Owner decision of 2026-10-12: tact switches + magnetic knob on an SPI absolute-angle sensor.** The R43 BOM lines (APEM, Grayhill encoder) and the controller note "encoder and buzzer not chosen" are older | FW/main/platform/ui_board_map.h:32-36; FW/build-evidence/ui-board/README.md:4; controller DECISIONS.md:433 | Update the R43 BOM when R44 opens (R43 is frozen). Part selection rationale for the OLED, knob sensor and buzzer is still missing |
| C22 expander GP3–GP5 | **Deliberately left stale.** The header says the bits are pending the knob-sensor redesign and "do not extend encoder handling". One of them is probably the sensor chip select, per that comment | FW/main/platform/ui_board_map.h:32-36 | When the UI board is released, remap GP3–GP5 to the UIB README and delete the encoder handling |

## Not re-checked
C17 (ledger counts), C23–C25 (sensor rim threshold, rim ADC, CR-5), C26–C32, C34, C35, C8, C11, C18, C19. They remain as cited in the checklist.

## Net so far (passes 1 and 2)
Of 35 entries, 16 have been looked at. 9 are documentation staleness with a known answer (C3, C6, C7, C9, C12, C13, C16, C21, C33), 1 is not a contradiction (C10), 1 is cosmetic (C20), 1 is a deliberate hold (C22), and 4 are real engineering gaps: C2 (coil lug type), C4/C5 (MAX31865 driver), and C15 (J13 firmware files not compiled in CI).
