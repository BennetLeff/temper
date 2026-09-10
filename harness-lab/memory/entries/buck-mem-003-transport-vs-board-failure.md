# buck-mem-003 — Distinguish a transport failure from a failed board

- **Claim / procedure:** When a run lacks a complete audit, check the
  transport record (HTTP status, read gaps, retry/concurrency flags)
  before concluding anything about the board: an incomplete response,
  non-200 status, transport error, or unexpected retry makes the trial
  indeterminate, not a board failure. Silent read gaps alone do not
  identify an upstream cause (provider delay, congestion, and unreported
  throttling remain possible). The timeout-correction itself (revised
  relay policy) remains code — this entry records only the diagnostic
  guidance.
- **Applicability:**
  portable diagnostic guidance, board-independent. Required
  capabilities: run-audit reading, transport-vs-board diagnosis.
  The 60-second cutoff history and observed gaps (53.39 s / 64.48 s /
  77.00 s) are fixture context, not MCU transport thresholds (R3).
- **Evidence:**
  `harness-lab/STREAM-DIAGNOSTIC.md`
  (`sha256:dd67ed72…e0befd00`) — batch-1 trial 2 (HTTP 200, reasoning
  events, then local relay 60 s read-timeout) kept as indeterminate;
  fresh batch under the revised policy passed 3/3 with gaps above the
  old cutoff completing successfully; absence-of-429 explicitly not
  ruling throttling out; three trials explicitly not a reliability
  estimate.
- **Provenance class:** expert-curated (manual curation 2026-09-10; not
  automatic learning — the full-buck pilot has not run).
- **Validation state:** source-reviewed. No live full-buck inheritance
  result claimed.
