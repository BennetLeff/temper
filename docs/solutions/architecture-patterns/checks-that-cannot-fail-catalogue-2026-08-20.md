---
title: "Checks that cannot fail — a catalogue of ten instances found on 2026-08-19/20"
date: "2026-08-20"
category: architecture-patterns
module: temper
problem_type: architecture_pattern
component: tooling
severity: critical
applies_when:
  - "a gate, parser, or metric has been green/silent for a long time on a board known to have real defects"
  - "reviewing a check that reads only part of a tool's output (one key of a JSON blob, one column of a table)"
  - "a percentage-typed field is suspiciously always 0.x or always exactly 0/100"
  - "a script's own manifest or docstring claims it is a 'CI tripwire' — verify it is actually invoked"
  - "a classifier keys on a hardcoded net/component name list instead of deriving membership from the schematic"
  - "a freshness/staleness gate reports PASS immediately after a build — verify it checked the right axis (symbols, not just timestamps)"
tags:
  - checks-that-cannot-fail
  - silent-failure
  - vacuous-gate
  - dark-metric
  - drc-parser
  - completion-percent
  - unwired-gate
  - hardcoded-classification
  - fail-closed
  - temper-pcb
---

# Checks that cannot fail — a catalogue of ten instances found on 2026-08-19/20

## The unifying defect

Every instance below measured something real, was true in its own terms, and
was structurally incapable of failing. None is a logic bug in the sense of
"computes the wrong answer" — each computes an answer that is correct for the
narrow, accidental scope it actually covers, while being read by everyone
else as a claim about the whole system. The board this project measures is,
and was throughout, further from done than any of these checks reported.

This document catalogues ten instances found in one session. Each row is
independently reproducible from a committed branch or commit; commands are
given so a reader in three months does not have to re-derive them.

## The catalogue

| # | Check | What it actually measured | What it silently missed | Measured effect | Evidence |
|---|---|---|---|---:|---|
| 1 | `_parse_drc_json` (DRC result parser) | 1 of kicad-cli's 10 top-level JSON keys (`violations`) | `unconnected_items` and 3 other arrays | 339 `unconnected_items` invisible; reported error count **379** vs true **718** | PR #1390, `fix/drc-parser-unconnected-items` |
| 2 | `completion_pct` metric | A fraction (0.0–1.0), stored into a field the renderer formats as `{:.1}%` | The seam between "fraction" and "percent" — no consumer scaled it | A 90%-routed board printed **"Router completion: 0.9%"** | PR #1393, `fix/completion-pct-metric-chain` |
| 3 | Blocking SLO `completion_pct >= 95.0` | Nothing — the `slo` CLI subcommand did not exist; the invoking step exited non-zero and was swallowed by `\|\| SLO_EXIT=$?`, then grepped for a key (`any_block`) nothing emits | Every one of 135 metric records | The SLO **never evaluated a single record** in its history | PR #1393 |
| 4 | `drc_errors` field in the metrics pipeline | Whatever the closure stage happened to write, which was always `0` | DRC was never executed as part of that stage | `drc_errors: 0` across **all 135** recorded runs, on a board whose true DRC error count is 718 (row 1) | PR #1393 |
| 5 | `sync_kicad_netclass_assignments.py` | Its own `--check` mode, when actually run | It was never invoked by any workflow, and from 2026-08-12 its `PROTECTED_NETS` tripwire made `--check` exit 5 unconditionally, before computing any diff | Called itself **"the CI tripwire against future drift"** in `manifest.yaml` since PR #1025; two independently-derived netclass tables (`TEMPER_NET_ASSIGNMENTS` and `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`) drifted freely for **34–35 days**, leaving 7 HV-domain nets at KiCad's `Default` class (0.2 mm clearance, no creepage rule) on the fab-authoritative path | PR #1391, commit `6f9aa0f63`, `fix/netclass-tables-reconcile` |
| 6 | `main.ato`'s 86 electrical assertions | 12 assertions that are genuinely coupled to circuit values | 74 assertions comparing hand-typed literals to other hand-typed literals — no circuit value could ever make them fail | **74 of 86** electrical assertions could not be falsified by any circuit change; `main.ato` contains no derived quantities at all | PR #1392, `gate/ato-assertion-vacuity` |
| 7 | `check_placement_roundtrip` | Pad positions in whatever coordinate frame its only production caller (`cli/__init__.py:760`) actually passes | Its own docstring says positions are in *file* coordinates; the caller passes the `normalize=True` frame instead — offset by `board.origin` = (8, 20) mm | Every one of **689** pad comparisons displaced by the same constant offset; reported, still unfixed | Commit `bc3a19b06`, `agent/per-pairing-placement-route`, `docs/evidence/2026-08-19-per-pairing-placement-routed.md` |
| 8 | `IECCreepageGate._is_hv_net` | Exact string membership in a 7-entry hardcoded list | The 27-net HV domain declared in `elec/domain_manifest.yaml` | Recognised **1 of 27** HV nets; 6 of its 7 hardcoded names (`DC_BUS+`, `DC_BUS-`, `SW_NODE_DC+`, `SW_NODE_DC-`, `AC_L`, `AC_N`) **do not exist** on this board — only `SW_NODE` does | Commit `d59fb0caf` (merged to main), `docs/evidence/2026-08-19-is-hv-net-blast-radius.md` |
| 9 | Ampacity net-current table | Current ratings keyed on `DC_BUS+`, a net name that has never existed on this board | Every real net that carries the DC bus current | `+170V_BUS` and `DC_BUS_RTN` (the real net names) fell through to a default and were rated **0.1 A instead of 16 A** | Commit `aba40630b`, `fix/net-current-table-fail-closed` (no PR opened) |
| 10 | `check_stale_extensions.py` | Whether a compiled `.so`'s content hash matches its Rust source, when the module both exists and imports cleanly | Multiple axes at once (see below) | Shown insufficient on at least 2–3 distinct axes in this session (see §"The fourth way, honestly") | PR #1395 (`docs/agents-instrument-notes`); commit `9fd4aa50c` |

## Detail: rows that need more than one line

### Row 1 — the DRC parser's blind 9/10

`_parse_drc_json` read `violations` and dropped `unconnected_items`,
`schematic_parity`, and the rest of kicad-cli's top-level JSON keys. Every
ratchet number this project recorded against DRC output was silently
computed against 1/10 of what kicad-cli actually reported.

```
gh pr diff 1390
git show <fix/drc-parser-unconnected-items HEAD>:docs/evidence/2026-08-19-drc-parser-unconnected-items-blindness.md
```

### Row 2/3/4 — one metric chain, four defects

PR #1393 found these together, in the same field and its immediate
neighbours:

1. **Unit mismatch at the seam.** The producer wrote a 0.0–1.0 fraction; the
   schema (`unit: percent, max: 100.0`), the pinned oracle, the differential
   generator (`uniform(0, 100)`), and the SLO threshold (`95.0`) all assumed
   0–100. Four places had written down the correct answer; none of them
   compensated at the point the fraction was actually stored.
2. **The SLO's join key never matched.** SLOs were keyed on stages
   `routing`/`drc`/`placement`; the only producer wrote one record per run
   with `stage: "closure"`. The blocking gate had a 0% join rate against its
   own data for its entire history.
3. **The CI step invoked a subcommand that did not exist.** `pipeline_metrics.py
   slo` was never a registered subcommand; the step's own exit code was
   captured into `SLO_EXIT` by `\|\| SLO_EXIT=$?` and never re-raised. Eight
   tests calling `cmd_slo`/`cmd_spc` were already failing with
   `AttributeError` before this PR — eight reds went green with no test
   modified, because the tests were correct and the production code was
   simply missing the functions they called.
4. **`spc` was phantom too**, for the same reason as (3); the trend-drift
   gate read the exit status of a bare `true`.

```
gh pr diff 1393
git show <fix/completion-pct-metric-chain HEAD>:power_pcb_dataset/metrics/slo_definitions.yaml
```

### Row 5 — a tripwire that was never wired

`scripts/sync_kicad_netclass_assignments.py`'s own `manifest.yaml` entry has
called it "the CI tripwire against future drift" since PR #1025. Two facts,
independent of each other, made it inert:

- **No workflow ever invoked it.** Grep any `.github/workflows/*.yml` for the
  script name — nothing calls it.
- **Even run by hand, `--check` exited 5 unconditionally from 2026-08-12.**
  Commit `322cbf5b0` (#1092) moved `PWR_RTN` to `HighVoltage` and, the same
  day, `kicad_pro` gained a declared `"GND"` class — so both of the script's
  `PROTECTED_NETS` became "declared" in both tables simultaneously, and the
  tripwire's own guard condition (meant to catch an *undeclared* protected
  net) fired on every invocation, before it ever computed a diff.

The two independently-derived net→netclass tables (`TEMPER_NET_ASSIGNMENTS`
in `core/design_rules.py`, read by router/placer/zone-pour; and
`pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`, read by
`generate_kicad_dru.py` → kicad-cli DRC, the fab-authoritative path) drifted
freely. Measured reconciliation: 7 HV-domain nets had **no netclass in
either table** and fell to KiCad's `Default` (0.2 mm clearance, no creepage
constraint at all) on the fab-authoritative path — for 34–35 days on some
nets. DRC total after reconciliation: 776 → 883 (+107); creepage 106 → 150
(+44).

```
git show 6f9aa0f63
```

### Row 6 — see the companion document

Row 6 (the 74/86 vacuous-assertion finding, PR #1392) and its remediation
(the 12 → 27 circuit-coupled paydown) is large enough to warrant its own
document: `docs/solutions/best-practices/ato-assertion-vacuity-paydown-2026-08-20.md`.

### Row 7 — a judgement, not a mistake, on the wrong axis

`BACKBONE_LAYER = "F.Cu"` (Section 4's subject,
`docs/solutions/architecture-patterns/stale-backbone-layer-workaround-2026-08-20.md`)
belongs partly in this catalogue too, as a variant of the pattern: commit
`dabbeaf73` (2026-08-16) explicitly re-examined the constant and *correctly*
concluded, on the axis it checked (does `pad_connectivity_audit.py`'s via
union still work?), that nothing needed to change — its own evidence-doc
diff says so in as many words: *"the backbone layer itself is unchanged —
F.Cu is one of the via's declared layers and still unions correctly."* That
conclusion was right about audit correctness and never checked the other
axis: F.Cu's own congestion (652 routed segments, a 27,499 mm² HV keepout),
which silently fail-closed 83 of 87 ground-plane MST edges. A check can
reason correctly about the question it asks and still be wrong about the
system, if the question it asks is not the one that matters.

### Row 10 — the fourth way, honestly

The session summary that seeded this document claimed `check_stale_extensions.py`
was shown insufficient **four** distinct ways in one session. Verification
found solid evidence for two, corroborating evidence for a third framed
slightly differently than claimed, and no independent evidence for a
fourth as a distinct incident:

1. **Timestamps, not symbols (confirmed).** The gate historically compared
   mtimes; a `.so` newer than its source but missing a function the source
   now registers still reports fresh. PR #1395's `AGENTS.md` diff: *"reported
   `stale=0` against a `.so` that was missing a function its own Rust source
   registers."*
2. **Poisoned shared cargo target (confirmed, but the gate caught it, not
   missed it).** Commit `9fd4aa50c` (2026-08-20): concurrent `cargo test` on
   one crate can poison another crate's shared `target-shared` directory,
   after which `check_stale_extensions.py` correctly reports `[UNLOADABLE]`
   for the poisoned module — this is the gate doing its job under a hostile
   shared-cache condition, not an instance of the gate being fooled. Listed
   here because it is a real way the *instrument* misleads an operator (who
   sees a failure and blames their own change), even though the gate itself
   is not silently passing.
3. **"Unimportable module reported fresh" — not independently confirmed.**
   The closest matching incident (a shared `.venv` reverted mid-session by a
   concurrent `uv sync`, described in PR #1395 as "one genuinely
   un-importable venv") does not implicate `check_stale_extensions.py`
   specifically in the committed record found. Treat this as **unverified**,
   not as a fourth confirmed instance, unless a more specific citation
   surfaces.
4. **"Importable but missing symbol"** is the same incident as (1) —
   collapsing the claimed four into two-to-three distinct, evidenced
   mechanisms.

```
git show 9fd4aa50c
gh pr diff 1395
```

## Why this matters

None of these ten checks were negligently written. Each is a small, locally
correct piece of code: a parser that reads a key that exists, a percent
formatter applied to a field, a script that does exactly what its `--check`
flag says, a classifier that matches the names it was given, a table lookup
keyed on a net name someone typed once. The failure is not in any single
line — it is that **nothing verified the check was looking at the thing its
name and its consumers believed it was looking at.** A DRC parser that reads
1 of 10 keys is not "slightly incomplete" from the point of view of anyone
reading its error count; it is silently reporting a different, smaller
question than the one asked.

## Guidance

1. **A parser that reads a structured format from an external tool should
   assert it consumed the format's full schema**, or at minimum log which
   top-level keys it read against which keys were present — silently
   dropping unread keys is exactly how row 1 stayed invisible for as long as
   the format existed.
2. **A percent-typed field should be asserted in range near where it is
   produced, not only where it is rendered.** A fraction stored where a
   percent belongs will pass every downstream consumer that renders naively.
3. **A script that calls itself a "CI tripwire" in a manifest needs a test
   that actually runs it inside CI and asserts a nonzero exit on a known-bad
   input** — a manifest entry is a claim, not a wire.
4. **A hardcoded name list standing in for a derived domain (net class, HV
   membership) will silently under-cover the moment the schematic changes.**
   Prefer deriving membership from the same source of truth
   (`elec/domain_manifest.yaml`) that everything else reads.
5. **A blocking gate's join key (stage name, record type) should be asserted
   to actually match at least one record in CI**, not just declared —
   row 3's SLO matched zero records for its entire history and nothing
   noticed because "evaluates nothing" and "evaluates everything and passes"
   render identically: green.
6. **When a subcommand is invoked from a shell step, check the step fails
   loudly on a missing subcommand.** `\|\| VAR=$?` patterns that capture and
   silently continue are exactly how row 3's nonexistent `slo` subcommand
   stayed uncaught.

## Related

- `docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md` — the sibling pattern from an earlier session: guard conditions that evaluate `True` but whose block is unreachable. This catalogue's instances are checks that *run* and *report*, but report on the wrong scope.
- `docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md` — a related but distinct failure: a threshold correct when written, stale by the time it gated anything.
- `docs/solutions/best-practices/ato-assertion-vacuity-paydown-2026-08-20.md` — full detail on row 6.
- `docs/solutions/architecture-patterns/stale-backbone-layer-workaround-2026-08-20.md` — full detail on the row-7-adjacent `BACKBONE_LAYER` finding.
- `docs/solutions/logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md` — a specification-level instance of the same shape: `p_output_max = 1800W` passed its own assertion band for as long as nothing in the firmware, placer, or any gate read the field at all.

## Verification notes

All ten rows were checked read-only against `origin/` branches (`git show`,
`git log --all`, `gh pr view`/`gh pr diff`) — no branch was checked out, no
file in this worktree was modified, `pcb/temper.kicad_pcb` sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` unchanged.
Row 7 (`check_placement_roundtrip`) was not found on first search and was
located on a second pass via `agent/per-pairing-placement-route`; row 10's
"four distinct ways" framing did not fully reproduce and is reported above
as found (two confirmed, one reframed, one unconfirmed), not as claimed.
