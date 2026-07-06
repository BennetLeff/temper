---
date: 2026-07-01
topic: linear-integration
focus: connecting Linear for issue tracking and dispatching agents
mode: repo-grounded
---

# Ideation: Connecting Linear to Temper

## Grounding Context

**Codebase context:** Temper is ESP32-S3 firmware (C) + Python/JAX placer + KiCad PCB +
Rust DRC/router. Current issue tracking uses `bd` (beads CLI), not Linear.
`tools/agents/auto_assign.py` doesn't exist (aspirational). No webhook infra. 16
GitHub Actions workflows exist, some create GitHub issues. `opencode.json` defines
agent profiles. Multi-worktree sprint pipeline already dispatches agents to
worktrees.

**Past learnings:** (1) `infrastructure-components-unwired` -- #1 failure mode:
components tested but never wired to production; (2)
`integration-hunting-audit-before-build` -- check for existing code before building;
(3) `parallel-worktree-sprint-pipeline` -- existing agent dispatch pattern; (4)
`ci-gate-quality-enforcement` -- pattern for integration health gates; (5)
`declarative-stage-dag` -- YAML-driven pipeline architecture.

**External context:** Linear has official MCP server (`mcp.linear.app/mcp`), Agent-first
API (`agentSessionCreateOnIssue`, `agentActivityCreate`), official GitHub sync, and
webhooks with HMAC. No official Python SDK -- use direct GraphQL via `httpx` or
community `linear-python-client`. Webhook + polling reconciliation is standard.

## Topic Axes

1. Issue lifecycle bridge -- how issues flow between Linear and existing `bd` tooling
2. Agent dispatch and execution -- how a Linear issue triggers agent work
3. CI/CD and automation integration -- wiring Linear into existing CI gates
4. GitHub bidirectional sync -- Linear's native integration vs custom
5. Onboarding and workflow migration -- moving from bd to Linear

## Ranked Ideas

### 1. Linear MCP as agent's native tool surface
**Axis:** Agent dispatch and execution
**Description:** Configure Linear's official MCP server (`mcp.linear.app/mcp`) in
`opencode.json`. Every coding agent gets direct read/write access to Linear as
native tool calls -- query issues, update status, add comments, create sub-tasks.
Zero infrastructure: no server, no webhook endpoint, no GraphQL client code.
**Basis:** `external:` Linear ships an official MCP server; `direct:` `opencode.json`
already defines agent profiles; `reasoned:` skips the wiring problem entirely
because agents do the integration autonomously.
**Rationale:** Single most pragmatic entry point. Agents get Linear access with one
config change. Self-documenting audit trail via comments and status transitions.
**Downsides:** No centralized dispatch logic. Harder to enforce WIP limits. MCP server
becomes a dependency for agent sessions.
**Confidence:** 85%
**Complexity:** Low
**Status:** Unexplored

### 2. bd-as-Linear-cache with progressive migration
**Axis:** Issue lifecycle bridge + Onboarding and workflow migration
**Description:** Keep `bd` CLI with identical UX. Backend switches to Linear
GraphQL. Local SQLite cache for offline. Developers opt in individually via
`BD_LINEAR_TOKEN`. Gradual migration with no flag day.
**Basis:** `direct:` bd exists and is the current tracker; `reasoned:` past learnings
warn against big-bang migrations; `external:` Linear's GraphQL API supports all CRUD
operations.
**Rationale:** Migration without disruption. Cache/shim preserves workflow while
switching backend incrementally. Matches fail-soft default pattern from past
learnings.
**Downsides:** Shim maintenance cost. Eventual consistency. Dual-write sync bugs.
**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

### 3. CI-failure-to-Linear-issue pipeline
**Axis:** CI/CD and automation integration
**Description:** Extend the 16 existing GitHub Actions workflows to create or update
Linear issues on failure. Each CI gate posts a structured Linear issue with gate
name, commit SHA, error excerpt, and CI run link. Auto-closes when the same gate
passes on a subsequent commit. Labels like `ci:import-linter` make failures
discoverable by agents via MCP.
**Basis:** `direct:` 16 GitHub Actions workflows already exist, some create GitHub
issues programmatically; `direct:` CI-gate-quality-enforcement pattern is
established; `reasoned:` CI failures currently vanish into ephemeral workflow logs.
**Rationale:** Transforms CI from passive reporting to a closed loop. Every failure
becomes a trackable work item. Lowest-risk first integration (creates issues only).
**Downsides:** Flaky gates create noise (mitigated by auto-close on re-pass). Requires
Linear API token in GitHub secrets.
**Confidence:** 90%
**Complexity:** Low
**Status:** Explored

### 4. Commit-message trailer convention with CI enforcement gate
**Axis:** Issue lifecycle bridge + GitHub bidirectional sync
**Description:** Adopt `Linear-Issue: TEM-123` git trailer convention. CI gate
enforces every merged PR links to a valid Linear issue. Zero-friction bidirectional
traceability without any sync server.
**Basis:** `direct:` Project already uses `@req(plan-id, req-id)` traceability
annotations; `reasoned:` git trailers are a proven convention; `direct:` commit
skill already writes structured messages.
**Rationale:** After 100+ commits, you have a rich traceability graph without a sync
server. The CI gate converts convention into structural guarantee.
**Downsides:** Adds CI gate that blocks PRs. Requires team discipline on commit
messages.
**Confidence:** 80%
**Complexity:** Low
**Status:** Unexplored

### 5. Label -> agent profile dispatch convention
**Axis:** Agent dispatch and execution
**Description:** YAML mapping in `opencode.json` binding Linear labels to agent
profiles: `label:agent:firmware` -> agent profile `firmware-codegen`. Combined with
MCP, agents autonomously discover and claim work by label match. Extends the
Declarative-Stage-DAG philosophy to agent selection.
**Basis:** `direct:` `opencode.json` defines agent profiles; `reasoned:` extends DAG
philosophy from pipeline stages to agent selection; `direct:` GEMINI.md references
aspirational `agent:*` labels.
**Rationale:** Highest-leverage convention. One YAML block unlocks autonomous dispatch.
Every new agent profile is automatically dispatchable with zero wiring.
**Downsides:** Agents must be autonomous enough to self-select. No central WIP control.
Requires MCP foundation.
**Confidence:** 70%
**Complexity:** Low
**Status:** Unexplored

### 6. DAG-as-issue: YAML stage topology in Linear issue body
**Axis:** Agent dispatch and execution
**Description:** Issue body contains YAML block defining stage DAG (agents, order,
dependencies, skip conditions). Ports the project's Declarative-Stage-DAG pattern
from repo YAML files into Linear issue bodies for multi-agent pipelines.
**Basis:** `direct:` Declarative-Stage-DAG pattern is documented in AGENTS.md and past
learnings; `reasoned:` making the issue the execution manifest eliminates separate
config file maintenance.
**Rationale:** Unlocks multi-agent, multi-stage pipelines driven entirely from the
issue body. Evolution path after basic dispatch works.
**Downsides:** Makes issue bodies programs. Large validation surface. Tight coupling to
repo internals. Requires MCP + label dispatch foundations.
**Confidence:** 60%
**Complexity:** High
**Status:** Unexplored

## Rejection Summary

- **bd shim variants (7+ duplicates):** Merged into survivor #2
- **Webhook server / polling dispatcher / MES factory:** Rejected in favor of MCP self-orchestration (#1)
- **Ant colony stigmergy / SCADA load shedding:** Premature optimization -- capacity mgmt is post-dispatch concern
- **Reverse causality (agents create issues):** Scope drift from user's goal (issue->agent, not agent->issue)
- **Railway interlocking:** Too rigid; Linear's native blocker system sufficient
- **Quality-envelope closure / merge-queue-kanban:** Duplicates CI pipeline with more complexity
- **GitHub issue forwarder / inverse sync / label-routed sync / musical score:** Survivor #4 (commit trailers) achieves same traceability with zero infra
- **Local webhook relay daemon:** Too much infrastructure for project with no webhook surface
- **Agent staleness / triage board / issue-template pipeline:** Secondary concerns -- build after core loop
- **Hospital OR scheduling:** About sprint process, not Linear integration
