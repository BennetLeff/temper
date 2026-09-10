# Buck memory — expert-curated seed package

Small reviewed starting-knowledge package distilled from the buck harness
work for reuse by the MCU construction agent (P2 U1 of
`docs/plans/2026-09-10-1322-feat-engineering-agent-memory-plan.md`).

## Status

- **Provenance class:** expert-curated (manual review, 2026-09-10).
  Nothing here is automatic learning: the full-buck learning pilot has
  not run, and no entry claims a live full-buck inheritance result.
- **Validation state:** source-reviewed against the evidence cited in
  each entry. No executable helpers are included; content curation needs
  source review, not tests that repeat the text.
- **Selection/promotion policy:** not defined here (P2 U2, `src/memory.rs`).
  Until then these files are read-only reference, not selectable authority.

## Entries

| ID | Lesson | Evidence |
|---|---|---|
| `buck-mem-001` | Inspect exact findings, edit the affected connection, then independently check | `harness-lab/REPAIR-RESULTS.md` |
| `buck-mem-002` | Track placement findings separately from incomplete routing | `harness-lab/COMBINED-RESULTS.md` |
| `buck-mem-003` | Distinguish a transport failure from a failed board | `harness-lab/STREAM-DIAGNOSTIC.md` |
| `buck-mem-004` | A plausible simulation is evidence only inside its declared model boundary | `docs/solutions/best-practices/behavioral-model-evidence-boundary.md` |
| `buck-mem-005` | Verify raw pin/part identity independently of aliases | `docs/solutions/tooling-decisions/generated-schematics-from-atopile-netlist-2026-07-15.md` |

See `catalog.json` for the machine-readable index and `entries/*.md` for
claim, procedure, applicability, evidence refs/hashes, provenance, and
validation state per entry.

## Transfer rules (from the plan, R3/R4)

- General procedures transfer by matching required capabilities and
  declared applicability — never by assuming the MCU board is the buck board.
- Exact component/board facts transfer only when the relevant source
  identities match. Buck-specific numerical values (poses, voltages,
  timings, edit counts) are context, not MCU constraints.
- Acceptance rules and current compiler/manufacturer facts override memory.
  Conflicting or unverifiable entries are excluded with explicit reasons
  at selection time (U2), not silently.

## Deliberate exclusions

- Orientation-normalization bug: belongs in the native evaluator
  regression suite, not in memory as a compensating helper.
- Witness coordinates / prior solution copper, supplier stock counts,
  unqualified capacitor/inductor guarantees: no seed includes these.
- Timeout-correction code (revised relay policy): remains code, with only
  the diagnostic guidance (`buck-mem-003`) recorded here.

## Evidence hashes (sha256, worktree HEAD `6f9c62d50`)

| File | sha256 |
|---|---|
| `harness-lab/REPAIR-RESULTS.md` | `2711a964f765af95da535b399792366e251c9a1d8ddaca51f0850870e1d7aa42` |
| `harness-lab/COMBINED-RESULTS.md` | `199107c7d1d65bdaa55af388b4a5e4dcc467dd0408ed4d4defce457787071b04` |
| `harness-lab/STREAM-DIAGNOSTIC.md` | `dd67ed72a14c00e09b1c0b3aa39723ac01657209ba29a88998d13233e0befd00` |
| `docs/solutions/best-practices/behavioral-model-evidence-boundary.md` | `a7c95cd41248558cebc3b66a09f3ef53cd3448636cfc85ed891cc84d74c33c37` |
| `docs/solutions/tooling-decisions/generated-schematics-from-atopile-netlist-2026-07-15.md` | `152318304b60b3d07e214c684409032307c1237aab0fda270a5536e0de2e0090` |

Hashes are advisory provenance (KTD3); authoritative freshness is decided
by artifact hashes and declared compatibility at selection time.
