# Round 4 quality record

Full integration review is complete; its original findings are retained in [review-full/review.json](review-full/review.json). The closure record below distinguishes replay-integrity fixes from the physical validation work that remains blocked.

## Coordinator curve extractor

Applied `ce-simplify-code` to `extract_loss_curves.py`. The reuse, quality and efficiency prompt assets were read and applied inline because all five worker slots are occupied and the native thread limit had already rejected additional launches. No separate review agents or independent-review coverage are claimed for this pass.

- Reuse: replaced two adjacent-pair `zip` expressions with the standard `itertools.pairwise` iterator, preserving iteration and avoiding sliced copies.
- Quality: formatted the script; no further behavior-preserving findings retained.
- Efficiency: no material additional inefficiency in the bounded 24-current / 406-voltage graph extraction.
- Validation: scoped `ruff check --no-cache` passed. Re-extraction produced byte-identical SHA-256s for both CSVs and the provenance JSON. Monotonicity, curve count, domain and independent tabulated-value checks passed.

The script reads a pinned source PDF, creates numerical evidence and does not import or change the production software. Repository-wide runtime tests are not evidence for this extraction; its numerical and artifact checks are scoped accordingly. Other worker scripts remain under active development and have not been covered by this simplification pass.

Dedicated focused ce-code-review completed for the four curve-extraction files; [receipt](review-curves/review.json). A separate Sol adversarial read returned no findings; coordinator correctness review found one voltage-axis calibration error. The tick-centered origin is now 80.8706 PDF points. Every numeric tick on both graphs and the independent Eoss curve origin are checked. Mutation replay with the former 81.0706 origin fails on both pages. Re-extraction and scoped ruff checks pass. Corrected 10 V Eoss is 3.6230 uJ. C2 received the corrected files and hashes. This closes the scoped finding; remaining worker outputs still require review.

## A current-limited grid

Independent read-only Sol review checked ROUND-4 A requirements, all 270 rows/statuses and hashes, frequency bisection/60 kHz cap, power split, trip source, numerical checks, and two decompressed raw waves. No material defect was found. A representative 42 A low/140 V/1710 W raw replay gave 41.8564528 A peak against 41.85645 reported and 661/661 events; sampled event current/time/bus matched exactly. The closest static-shunt case remains above its threshold at both nominal and half step. The README now labels its 50 ns capacitor maxima and provides the slightly higher 12.5 ns extrema. This engineering review does not replace the pending complete integration review.

## C1 reference map

An independent read-only Sol review verified TI page 10 timing data, all 15 source hashes, the 140-row grid, 20 supplemental signed 10 V brackets, all 82 numerical checks and two raw waveform examples. No demonstrated calculation defect was found. The coordinator copied the packet and reran its audit successfully. The signed 10 V criterion establishes discharge, not continuous diode conduction; the separate physical diode probe is mandatory for dwell energy. This constraint was sent to C2. No board-dependent rerun is claimed.

## D2 diagnostic replay

A separate Sol worker hardened run status, finite vectors, log/raw completeness, frozen input identity and full-window peak checks. Failed/aborted/nonzero status, NaN, an abort log, short vectors, truncated raw and a wrong input hash were rejected in failure injection; a mocked failed run also removed its vendor copy. Coordinator replay of all five saved waves reproduces the hardened summary byte-for-byte. Full post-turn-off peaks equal the original window peaks. Four historical process exit codes were not retained; complete logs and raw waves are checked, and that provenance limit remains explicit. The physical D1-dependent matrix grid remains unrun.

## Settled A/C1/D2 script simplification

Applied ce-simplify-code with separate Sol reuse, quality and efficiency reads, queued on the existing worker slots. Applied two quality findings: removed three unused imports from A numerical-check scripts and collected extremum keys directly as a set. All nine frozen A outputs remain byte-identical after 270 cached half-step checks, two nominal ngspice replays and 133 cached quarter-step checks. Scoped ruff checks pass. Three suggestions were skipped: importing a four-line RMS helper from a frozen older round adds coupling; replacing C1 dynamic loaders alters module identity/cache semantics without a demonstrated need; streaming the fixed 190,336-event aggregation is a possible future optimization but does not justify changing the pinned simulation producer for this bounded run. No reuse or efficiency edits were applied. C2, D1 and the later snubber-support script were not part of this settled-unit pass.

A full scoped ruff run additionally found explicit-zip-default and import-layout issues. C1 now spells out `strict=False` (the existing default); AST comparison after removing those explicit defaults is identical to the saved original source. Original C1 scripts/manifest remain in ignored `outputs/runs/source-before-lint/`; the current source manifest records the cleanup, and all frozen numerical outputs are unchanged. D2 received an intentional dynamic-import annotation and import whitespace; A replay preserves its deliberate import ordering with a lint annotation. Full scoped ruff and the 15-source C1 audit pass.

## Corrected C2 engineering review

Independent read-only Sol review reproduced off-command-to-gate-qualified-onset diode charge from the raw 120 V waveform and typical diode heat within 0.001%. All six corners use the same event subset; all 810 comparison differences reproduce 51 kΩ minus 39 kΩ. Continuing post-onset channel/diode sharing is separately reported and no longer censors the known commutation interval. The coordinator checked the rewritten README against the corrected summary: 105/110/118 higher cases, 76.64/76.93% aggregate coverage, and explicit withdrawal of the earlier result. Total/hot/recovery/board losses remain unqualified.

## D1 and repository checks

All 114 original D1 manifest entries (91 raw plus 23 compact source/report entries) verified after integration. Independent physical wire resistance and two-plate checks are dimensionally consistent; no board matrix is accepted. The coordinator retained pre-lint sources and manifest, applied import/unused-variable/default-zip cleanup, reran the wire fixture successfully, and recorded 109 ignored files in the updated D1 manifest. D1 and snubber scoped ruff checks pass.

The import-boundary gate passes with five contracts kept, zero broken and zero new violations. `make regen-check` passes, including repo state, WASM registries, oracle hashes, hash ordering, script manifest, kernel ledger and wire-format helpers. Logs are [import-linter.txt](import-linter.txt) and [regen-check.txt](regen-check.txt). An isolated temporary environment supplied the repository-pinned tooling; no shared runtime was changed. No PCB, firmware, Rust extension or workflow changes require those domains' build/DRC checks.

Final C2 lint cleanup preserved original sources under ignored `outputs/runs/source-before-lint/`, organized imports, used `collections.abc.Sequence`, and made existing `zip(strict=False)` defaults explicit. Primitive self-tests pass and both 810-pair comparison outputs remain byte-identical. `make regen` also completed successfully with no derived-artifact changes. The raw-handback verifier checked all 12,011 files before the five pre-lint C2 sources were added; the final manifest is regenerated and checked below before commit.

## Full packet review and replay fixes

The full ce-code-review covered the frozen 139-file staged packet using eight lenses: correctness, adversarial, project standards, testing, maintainability, reliability, performance and institutional learnings. A separate Sol validator confirmed six distinct findings. All reviewers used Sol as requested; no cross-provider independence is claimed. The original receipt is preserved unchanged, so its open findings and pre-fix raw-count wording describe the reviewed snapshot rather than the final handback.

1. C2 now verifies each selected raw wave against the independently frozen C1 SHA map before creating catalog output. The loss join pins that map and the catalog provenance.
2. C1 rejects saved search rows when the runner identity, timing, expected specification or unique ID differs.
3. C2 comparison requires exactly the frozen 270 A cases times three timing corners, with both resistor values. Removing an entire pair now fails instead of reporting 809 pairs as a pass.
4. Snubber cache reuse verifies the source waveform, onset and simulator identity before publishing current provenance.
5. A refinement caches verify the pinned deck, options, runner, vendor model and simulator identity. Relocated common-kit paths are normalized without weakening the deck comparison.
6. A raw gzip is checked through EOF/CRC and atomically installed before its completion marker. Truncated cached gzip streams are rejected.

Verification: all 1,226 C2 waves and 190,336 events were reprocessed; catalog and loss CSVs remain byte-identical. The 810-pair comparison remains byte-identical. Valid C1 cached rows pass; changed timing, duplicate IDs and changed runner identity fail. The integrated 140-row resume and 15-source audit pass. A checks covered 314 half-step caches, 133 quarter-step caches and one relocated nominal cache; changed decks and truncated gzip fail. All 20 snubber caches pass; source-wave, onset and simulator mutations fail. All 5,468 pre-existing A/snubber output files remain unchanged. Nine frozen A outputs and every one of the 15 staged numerical CSVs remain byte-identical after integration. Scoped ruff passes.

The final raw manifest includes pre-review source snapshots and verifies **12,027/12,027 files, 5,923,554,281 bytes**; see [raw-verification.txt](raw-verification.txt). These files remain local and ignored, and no remote raw archive is claimed. The verifier itself rejected corrupted, missing, traversal and count-mismatch fixtures. Original producer sources are preserved under ignored `source-before-lint` and `source-before-review` directories; source-manifest changes document guard/lint changes, not newly simulated physics.

An independent Sol validator inspected the six repair deltas and bounded saved proofs; [closure.json](review-full/closure.json) closes all six. This closure did not rerun the simulation grids. The new C1 raw-wave pin is included in the final Git packet. Gzip CRC checks detect interrupted compression; they do not independently establish waveform point-count correctness. D1 and the physical qualification gaps remain open as described in the monitoring handoff.
