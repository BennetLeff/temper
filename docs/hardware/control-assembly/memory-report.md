# MCU memory closeout (P2 U4)

First cross-unit memory package for the MCU construction task, produced
under `docs/plans/2026-09-10-1322-feat-engineering-agent-memory-plan.md`
(P2: reusable engineering memory).

## Selected input (buck seed, expert-curated)

All five `harness-lab/memory/` entries validated against live evidence
hashes and selected for the MCU task on 2026-09-10 in this worktree.
Priority is catalog order; the selection is deterministic over
`(priority, entry ID)`.

- `buck-mem-001` — Inspect exact findings, edit the affected connection,
  then independently check. Content `sha256:feb5a98f…ec94091`.
- `buck-mem-002` — Track placement findings separately from incomplete
  routing. Content `sha256:eea09592…4810`.
- `buck-mem-003` — Distinguish a transport failure from a failed board.
  Content `sha256:e50a3232…13a7ba`.
- `buck-mem-004` — A plausible simulation is evidence only inside its
  declared model boundary. Content `sha256:12c3eacc…55f2`.
- `buck-mem-005` — Verify raw pin/part identity independently of aliases
  (bridge cross-check against P1's current bridge outstanding, recorded in
  the entry — not assumed). Content `sha256:9908a4ac…7537`.

Selection receipt: `selection_sha256`
`c4c31c10710dd85a96c2e07c6083f818e959a0a7394953d039bac32f24bce1e5`,
zero exclusions, materialized notes 8981 bytes of the 64-KiB pair cap. This
receipt is the accepted assisted-attempt selection bound to the current source
identities; the earlier `bd3c56ff…`/8243-byte figures in this section matched
no retained receipt and were reconciled by the coordinator
(`harness-report.md` §1.5, §8). The **unassisted** attempt, bound to the
pre-fix source identities, recorded a different content-bound selection hash
(`7073c176…`) over the same five entry bytes.
Evidence hashes verified live against `harness-lab/REPAIR-RESULTS.md`,
`harness-lab/COMBINED-RESULTS.md`, `harness-lab/STREAM-DIAGNOSTIC.md`,
`docs/solutions/best-practices/behavioral-model-evidence-boundary.md`,
and
`docs/solutions/tooling-decisions/generated-schematics-from-atopile-netlist-2026-07-15.md`.

Provenance: expert-curated manual review (2026-09-10). Nothing here is
automatic learning — the full-buck learning pilot has not run, and no
entry claims a live full-buck inheritance result.

## Delivered

Notes-only delivery path implemented (`harness-lab/memory.py`:
`materialize_selection` through the existing `artifacts.Store`, atomic
`memory-selection.json` receipt via `publish_receipt`). The seed package
ships no executable helpers, so delivery is recorded as delivered, never
as executed. Helper-call provenance stays empty until a verified helper
exists; reading notes is never recorded as causing a decision.

Live MCU-attempt delivery receipts are retained per attempt by the
construction runner (P1 integration, interface in
`memory.p1_interface()`); no live attempt has run in this session, so no
delivery acknowledgement exists yet. A missing live-delivery record keeps
any future memory-reuse claim indeterminate — a control run cannot stand
in for it.

## Executed

None. No executable helpers are selected (seed is notes-only), so there
is no helper execution to attribute. This is the expected state, not a
gap.

## Proposed

None yet. Automatic extraction runs as a bounded post-attempt step after
the first MCU attempt ends (plan KTD5); that attempt has not run, so
there is nothing to extract from. No proposal was fabricated to make the
count positive.

## Promoted

None. Promotion has three outcomes (candidate / verified-selectable /
rejected) gated by `src/memory.rs::promotion`: a timeout alone cannot
support a circuit-performance claim, a complete valid failing attempt may
support a diagnostic lesson only with independent evidence, source facts
require a matching current compiled artifact, and executable procedures
require a passing native behavioral test. With no MCU attempt trace,
"no new valid lesson" is the correct, recorded result — a failed board,
had there been one, could support a diagnostic lesson without becoming a
passing design.

## Remaining for the next cooker unit

- P1 registers `mod memory` (schema `memory/v1`) in the main dispatcher
  and wires `p1_interface()` hooks into the development runner; the
  standalone `memory_judge` bridge is then the test path, not the
  authority.
- First live MCU attempt loads this selection before construction and
  retains its model-input payload bound to the selection receipt.
- Post-attempt extraction proposes MCU lessons; a reviewer validates
  evidence and applicability before next-run selection.
