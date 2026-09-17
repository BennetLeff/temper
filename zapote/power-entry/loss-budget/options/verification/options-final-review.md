# Final canonical PFC options review

Read-only recheck of `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan/zapote/power-entry/loss-budget/options` after the requested fixes. No builds or edits.

Status: **PASS for the three previously reported findings.**

- `replacement-fet/sources/NVHL040N65S3F.pdf` is now a valid 11-page PDF. Its SHA-256 is `98711c246a814ab3687be0805af93130ff01f7a2474af83fbabd513d5edd820b`, matching `replacement-fet/candidates.json`. `pdftotext` identifies onsemi NVHL040N65S3F Rev. 1 (July 2019), and the reported 650 V, 65 A, 40 mΩ/32.5 A/10 V, Qg 153 nC, Qgd 61 nC, 159 ns/840 nC values match the retained PDF.
- Pair-driver source identity is corrected: `replacement-pair/sources/UCC27624-RevE.pdf` is SLUSE44E, revised March 2026; report and candidate metadata now say Rev E and point to that filename. The recorded hash matches the file.
- Pair B now labels 15 V as `screen_vgs_v_testpoint`, explicitly says it is the RDS(on) test point rather than a recommended turn-on voltage, and keeps the specified operating range −5 V to +18 V. RESULTS.md carries the same qualification.
- The Miller receipt now distinguishes turn-on/turn-off times and states the 0 V turn-off assumption. Pair B records actual AUX sufficiency as unknown (`null`) while marking only nominal 15 V compatibility as true. Existing-drive 132 V uses approximately 13.645 Arms.

No new high-confidence technical false claim or arithmetic mismatch found within this bounded recheck.
