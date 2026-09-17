# DeepSeek PCB Harness Design

**Status:** approved design

**Date:** 2026-09-17

**Branch:** `codex/deepseek-pcb-harness` (from `origin/main` @ `fd1867d16`)

**Scope:** build a self-owned agent harness on the official DeepSeek API,
targeted at PCB design, following the architecture of *Prime Agent: A
Self-Improving RLM Harness* (arXiv:2608.23552v1). The harness's first
falsifiable job is to rebuild one existing Zapote unit, compared against a
direct-agent baseline at fixed expenditure.

---

## 1. Goal and success criteria

**Primary deliverable: a harness we own.** Not a finished board, not a
benchmark. Success is that the loop, its state, its memory, and its accounting
are ours — we can start it, watch it act, measure it, and change it — and it
does not route back through Codex or OpenCode.

**Proving ground:** rebuild one existing Zapote unit end to end, judged on
acceptance-check completion against a direct-agent baseline at fixed
expenditure.

**Success criteria, in order:**

1. The harness runs a real unit-rebuild attempt to completion with no
   third-party agent runtime in the loop.
2. Every claim it makes is backed by a recorded, schema'd trace and an exact
   cost ledger that includes descendant sessions.
3. The experiment reports a result — **including a null result** — with
   intervals, against a pre-registered decision rule.

**Explicit non-goal:** replacing the Temper placer/router. The harness exposes
edits and validators; it does not implement placement or routing algorithms.

---

## 2. Why this design exists (the evidence base)

The 2026-09-09 → 2026-09-17 "harness engineering" arc is the direct
predecessor. Measured from `~/.codex/state_5.sqlite`, `cwd =
/Users/bennet/Desktop/temper`:

| Role | Threads | Tokens | Share |
|---|---|---|---|
| User sessions | 6 | 331.9 M | 12.4 % |
| `luna_subagent` workers | 202 | 1,973.7 M | **73.7 %** |
| `codex-auto-review` guardians | 269 | 371.4 M | 13.9 % |
| **Total** | **477** | **2,676,994,364** | 100 % |

Three facts drive this design:

1. **The headline experiment was never run.** The roadmap deferred
   whole-board agent integration to milestone 7; it never arrived. All seven
   Zapote units terminate at `INDETERMINATE` / `NOT RUN`.
2. **The prior session said so itself.** Asked *"are we actually building a
   harness or is it performative"*, its answer was: *"we haven't yet shown that
   this approach beats directly asking an agent to route the whole board… the
   harness is real; its advantage is still unproven."* No post-mortem exists.
3. **The runtime was outsourced deliberately.** The refinement plan's R19 was
   *"Preserve OpenCode"*; its scope boundaries listed *"alternate agent
   runtimes"* as out of scope; the README said *"We reuse OpenCode as the
   general agent runtime."* The loop was therefore never ours to change.

So the failure was not a bad harness. It was that **the claim was never put at
risk**: 2.68 B tokens spent, and the falsifiable question still open.

Supporting sources: `harness-lab/CONTINUAL-HARNESS.md`,
`docs/plans/2026-09-09-1945-feat-buck-harness-refinement-plan.md`,
`zapote/README.md`, `zapote/ARCHITECTURE.md`, `zapote/AGENTS.md`
("Distilled Temper learnings").

---

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Fresh runtime; reuse domain tools.** New DeepSeek loop is the runtime. Zapote's Rust validators, the Python/KiCad adapter, and the acceptance-record format become tools. `harness-lab`'s Rust control plane is retired; its lessons carry over as requirements, not code. | The prior control plane was shaped around OpenCode relay interactions and would need reshaping anyway. Retiring it keeps runtime and judge in one language and avoids re-deriving the sandbox badly. |
| D2 | **L0 = `deepseek-v4.1-flash`**, behind S0's provider abstraction. | Cheaper, and consistent with the most recent prior session (`opencode-go/deepseek-v4.1-flash`). The paper found V4 Pro gained the *most* from an RLM harness, so Flash is the harder test of the design. Keeping it behind an abstraction makes Pro-vs-Flash an experiment, not a rewrite. |
| D3 | **Official DeepSeek platform API** (`api.deepseek.com`), direct key. Not the `litellm.yaml` aggregator aliases. | Known tool-calling behaviour; first-class cost accounting for the fixed-expenditure metric; no intermediary in possession of full board artifacts and raw conversations; no proxy sitting between us and a transport-fidelity bug. |
| D4 | **Sequencing B: build S0–S6, then measure (S7).** | User's explicit choice. The risk this carries is recorded in §8. |
| D5 | **Cross-cutting measurement contract**, not a measurement assembled at the end. | Under D4 the experiment is last, so every sub-project must emit cost, trace, per-check completion, validity evidence, and classification from day one. This is the specific gap the prior attempt had. |
| D6 | **Board and verifier are non-model-writable.** | See §5. |
| D7 | **Physical criteria are reported, never counted.** | All seven prior units are physically `NOT RUN`. Counting them would manufacture progress that does not exist. |

---

## 4. Architecture: the paper's L0–L3 mapped onto PCB

The paper's core move is a state hierarchy in which only L0 is fixed and each
other level changes through a *different mechanism*.

| | Paper | Generic mechanism | PCB-targeted |
|---|---|---|---|
| **L0** | weights | fine-tuning | `deepseek-v4.1-flash`, fixed — never fine-tuned |
| **L1** | active context | compaction rewrites it | assembled prompt: task, board digest, open findings, selected memory |
| **L2** | persistent REPL + subagent sessions | *agentic garbage collection* — create / retain / summarize / delete | one live Python kernel holding the board model, parsed DRC/ERC findings, geometry, FEM output, and prior attempts as values that do not enter L1 unless explicitly serialized |
| **L3** | history, memories, skills, subagent specs | refinement versions selected entries | append-only event log, compaction records, session tree, persistent message queues, versioned memory seeded from `zapote/skills/revisions/*-lessons-v1` |

**Information flow between levels** (paper §2.2): Python values and tool
outputs in L2 enter generation when serialized into L1. Compaction replaces a
conversational prefix with a summary and retains the original events in L3 for
L2 retrieval. L3 entries enter later prompts on selection or retrieval. L0
stays fixed.

**Recursive execution** (paper §2.4): the `rlm` primitive creates a subagent
session and returns a stable handle *before* the subagent completes; the parent
continues local computation. Sessions are `running` / `idle` / `inactive`, owned
by a daemon independent of the client, with agent-to-agent messages carried on
asynchronous queues addressed to parent, children, and siblings.

---

## 5. Trust boundary

Two things sit outside L0–L3 and must be non-model-writable:

- **The board.** KiCad files are environment state, content-hashed, distinct
  from harness memory. The paper's Factorio trace is the cautionary parallel:
  the agent discovered it could RCON resources directly into assembly machines,
  used the shortcut despite an anti-cheating heartbeat, **and then preserved it
  as a reusable skill**. The PCB analogue is an agent that satisfies DRC by
  editing the ceiling, the `.kicad_dru`, or a validator — and then writes that
  trick into L3, where it survives compaction and gets inherited.
- **The verifier.** The Rust validators and native KiCad checks run
  out-of-process, are never importable from the model's kernel, and return
  findings the model cannot author.

Concretely, the harness must be able to demonstrate: the agent cannot write a
validator, the generated `.kicad_dru`, `drc_ceiling.json`, any
`*_py_oracle.py`, or any acceptance record. Per the paper, safe deployment
requires *"least-privilege action interfaces, independent state validation, and
auditable rollback of contaminated refinements."* For a 1,800 W AC-input
board this is not a research nicety.

**Visibility rule:** *spec visible, solution hidden, verifier non-writable.*
The agent receives the unit's `INTERFACES` and its check list — the paper gives
its agents the verifier specification too. The sandbox denies the target unit's
existing routed PCB, evidence trees (`zapote/artifacts/`), and prior acceptance
records.

---

## 6. PCB-specific risks the architecture must answer for

None of these are shared by the paper's benchmarks.

1. **Verifier economics.** EmulatorBench supplies diagnostic tests; ARC-AGI-3
   supplies an action limit. Temper supplies ~250–400 s routing runs and DRC
   that requires ≥120 samples to be reproducible. If each verdict is that
   expensive, test-time scaling may not convert — and the paper's own nanoGPT
   result was that harness choice vanished into experiment noise.
   *Mitigation: start where the verifier is exhaustive and deterministic (§7,
   interlock), and treat verifier latency as a first-class measured quantity.*
2. **A digital-only ceiling.** 7 of 7 units are physically `NOT RUN`. The
   harness can only ever optimise a digital proxy — the exact Goodhart
   condition. *Mitigation: D7, plus the validity gate in §7.*
3. **Mains safety.** A self-improving harness can preserve a dangerous
   shortcut as a skill, and skills persist. *Mitigation: §5, plus mandatory
   rollback of any refinement that attempts to relax a physical or safety
   criterion.*

---

## 7. Sub-projects

Dependency chain: `S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7`, with S2 also feeding
S1 its tool surface, and S4 able to revise S6's dispatch policy.

| | Sub-project | Owns | Gate — how we know it is done | Paper §|
|---|---|---|---|---|
| **S0** | Provider transport | DeepSeek client, tool-call fidelity oracle, exact cost/token ledger, recorded-and-replayable responses | Fidelity tests pass against recorded responses; every call is costed; no intermediary in the path | — |
| **S1** | Loop + L2 kernel | L1 assembly, persistent Python kernel, budgets, failure taxonomy, compaction, record/replay | An attempt survives compaction *and* process restart with L2 intact; every outcome classified; never retries to success | 2.1–2.3 |
| **S2** | PCB surface | Board-as-state, explicit edit tools, findings-returning checks, non-writable verifier, validity gate | A finding reaches the agent and its correction is independently measured; the §5 prohibitions are mechanically demonstrated | — |
| **S3** | Recursive subagents | Session tree, daemon, direct agent-to-agent queues | Worker completion is not acceptance — integration authority stays with the root; dead-worker salvage; bounded delegation | 2.4 |
| **S4** | Continual Harness | Versioned prompts / memories / skills / subagent specs, boundary refinement, rollback | A revision demonstrably changes later behaviour; a contaminated revision rolls back; frozen and updating conditions both run | 2.5 |
| **S5** | Daemon + Agents View | Inspect, attach, intervene without stopping the session | Attach mid-run and intervene; detach does not kill the session | 2.4 |
| **S6** | Long-horizon controls | Autonomous mode + end-condition test, goals, heartbeats | Continues under budget until the end-condition test passes; accounting aggregates all descendants | 2.6 |
| **S7** | The experiment | Arms, scalar, analysis | Score at fixed expenditure reported with intervals; a null result is a valid, reportable outcome | 3 |

S0 and S2 are not in the paper. They are the apparatus, and this repo's own rule
applies: *verify the instrument before trusting the number.*

### 7.1 Cross-cutting measurement contract

Because S7 is last under D4, the following are requirements on **every**
sub-project, not outputs of S7:

- **Cost ledger** — USD and tokens per model call, aggregated across the root
  and *all* descendants.
- **Schema'd trace** — a real schema file, not inline constants. The prior
  attempt's `SCHEMA_VERSION = 2` lived inside `harness-lab/telemetry.py`, so no
  schema artefact existed to validate against.
- **Per-check completion** — which acceptance checks are satisfied, at what
  cost, with the verifier's identity recorded.
- **Validity evidence** — proof the artifact still conforms to the unit's
  source spec.
- **Outcome classification** — `pass` / `fail` / `blocked` / `indeterminate` /
  `missing` / `stale` / `invalid`, keeping harness failure distinct from model
  failure.

### 7.2 Definition of "stack complete"

Sequencing B requires this, because with measurement last, "done" is otherwise
a judgement call — which is how the prior attempt produced 202 worker threads
and no closed milestone.

**Stack complete = all eight gates green, and all five cross-cutting emissions
present and validated against their schema.**

---

## 8. The S7 experiment

### 8.1 Task

**Unit: `interlock`.** Chosen for one property: its acceptance checks are
*exhaustive and deterministic* — seven fault inputs, watchdog/liveness gating,
a stateful reset latch, and Rust checks evaluating **4,096 gate/state/clock
combinations** that reject connectivity and model mutations.

This is the closest available analogue to EmulatorBench's diagnostic verifier,
and it is what makes a fixed-expenditure comparison meaningful. Every other
unit's verdict is slow (routing), noisy (DRC), or partly unrun (thermal/FEM).
The interlock is also small enough for an attempt to finish.

### 8.2 Arms

| Arm | Configuration | Answers |
|---|---|---|
| **A — control** | Single agent, same tool surface, **no L2 persistence, no L3 memory, no subagents** | The question the prior attempt never asked: does the harness beat just asking an agent? |
| **B — treatment** | Full stack: L1–L3, subagents, refinement | The paper's claim |
| **C — ablation** | Full stack with **L3 refinement frozen** | Whether the continual-harness layer earns its place (paper RQ3), isolated from persistence |

All three receive the same spec, the same tools, the same verifier, and fresh
isolated state per attempt. A and B differ *only* in harness capability.

### 8.3 Scalar

- **Primary:** acceptance-check completion fraction (digital) as a function of
  **cumulative USD**; tokens and wall-clock as secondary axes.
- **Reported at:** a pre-registered fixed cost `C*`, *and* cost-to-plateau.
- **Never counted:** physical criteria. Reported as `NOT RUN`, identical in
  all arms, so they cannot flatter any arm.

**Accounting rule (load-bearing).** Spend aggregates the root *and every
descendant session*. Excluding descendants is precisely how a harness
manufactures a fake win: the prior attempt's totals were 6 root sessions at
331.9 M tokens but 2.68 B overall — 73.7 % in subagents. Scored on root-only
expenditure, 268 sessions would have been free.

### 8.4 Pre-registered decision rule

Before any scored run, commit a file fixing: the arms, `C*`, the seed count,
the aggregate statistic, and the rule for what counts as B beating A —
**including the null**. The margin is set from a pilot and then frozen; picking
it before the variance is known is how it ends up moving later.

"Advantage unproven" must be a writable, expected outcome. The prior attempt
ended with that sentence and no way to record it as a result.

### 8.5 Controls against the three ways this would lie

1. **The agent copies the answer.** "Rebuild the unit" is trivial if the routed
   board or prior acceptance record is readable. *Control: spec visible,
   solution hidden, verifier non-writable (§5), with mechanical denial tests.*
2. **The verifier drifts underneath the comparison.** *Control: set-diffs, not
   counts; sample where a category is nondeterministic; anything unresolvable
   becomes `indeterminate` and is retained, never silently re-run.* (Per
   `AGENTS.md`: a count of exactly 199 or 499 is a cap, not a count; creepage
   reports per net pair.)
3. **Pretraining leakage.** This repo is large and partly public. *Control:
   same as (1), plus recording what the model could plausibly have memorised.
   This is a limitation to state, not one to pretend away.*

### 8.6 Statistics

LLM builds are stochastic and DRC is stochastic on a byte-identical board.
**8–16 seeds per arm**, reporting intervals rather than point estimates.

Binding caution from the paper: harness choice disappeared into noise on
nanoGPT, and its ARC-AGI-3 numbers were explicitly labelled non-causal because
native-harness reruns fell below published scores. **If the intervals overlap,
the honest output is that the harness's advantage remains unproven.**

---

## 9. Known risk of the chosen sequencing

Sequencing B is retained by explicit decision (D4). Its risk is recorded here
so it is answered rather than forgotten:

> With measurement last, the prior attempt produced 2,676,994,364 tokens, 202
> worker threads, 19,306 files under `zapote/`, and an unrun headline
> experiment.

The two mitigations are structural, not attitudinal:

1. §7.1's cross-cutting contract, so no sub-project can be "done" without
   emitting the measurement it will later be judged on.
2. §7.2's definition of stack complete, so "done" is a list of gates rather
   than a judgement.

If those two are honoured, sequencing B is safe; if they are not, it repeats the
prior shape exactly.

---

## 10. Open questions and prerequisites

1. **Implementation base.** This branch is cut from `origin/main` (`fd1867d16`,
   2026-09-09). The Zapote Rust validators and the `harness-lab` history live on
   `codex/buck-harness-experiment-plan` (`c27abe974`, 2026-09-17) and ~20 other
   `codex/*` branches, none merged. **Decide before S2:** rebase onto that
   branch, merge it, or port the validators as content-hashed donors the way
   `zapote/ports.toml` already documents.
2. **Which acceptance checks are the scalar.** The interlock's
   `ACCEPTANCE.md` must be inventoried into a machine-readable checklist with a
   stable identity per check, before S1 can emit per-check completion.
3. **Verifier latency budget.** Measure the interlock's end-to-end verdict cost
   before fixing `C*`. If a single verdict costs more than the whole per-attempt
   budget, the task is infeasible and the unit choice must change.
4. **`C*` and the seed count** — set from a pilot, frozen in the
   pre-registration file (§8.4).
5. **Where the harness lives.** Proposed: a new top-level `harness/` (or
   `agent/`) directory in this repo, not inside `zapote/`. To be confirmed.

---

## 11. Falsification

This design is worth abandoning, or its scope worth cutting, if any of these
hold after S2:

- The interlock's verdict cost exceeds the per-attempt budget, making dense
  iteration impossible.
- The S0 fidelity oracle shows the official DeepSeek API cannot sustain the
  `rlm` primitive's nested-call pattern within budget.
- The validity gate cannot be enforced mechanically, so a trivialised board
  scores well and the scalar measures nothing.
- Arm A already reaches the unit's full digital acceptance set within `C*`,
  leaving no headroom for the harness to demonstrate anything — in which case
  the interesting question moves to a harder unit, and the paper's own
  "harness vs noise" caution becomes the headline finding.

Each of these is a legitimate, reportable result. None of them requires the
work to be reclassified as a failure.

---

## 12. What is explicitly not claimed

- No physical qualification. Nothing here advances, implies, or substitutes
  for the physically-`NOT RUN` status of any Zapote unit.
- No electrical or safety sign-off. A clean digital verdict on a 1,800 W
  AC-input board is not evidence the board is safe, manufacturable, or
  functional.
- No claim that the harness will outperform a direct agent. That is the open
  question the experiment exists to answer, and the prior attempt's own words —
  *"the harness is real; its advantage is still unproven"* — remain the honest
  starting position.