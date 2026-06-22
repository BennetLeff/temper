# Claude Agent Instructions for Temper Project

This file establishes the context and best practices for Claude agents working on the Temper project. It focuses on UI/UX standards, frontend development, and integration with the Temper cognitive stack.

## 1. Project Overview

**Temper** is a high-power induction heating system. While most of the project is hardware and firmware, your role often involves:
- **Dashboard**: The Next.js based UI for monitoring and managing memories.
- **Documentation**: Maintaining the "agent hive mind" through clear architectural docs.
- **Integration**: Ensuring the UI correctly reflects the state of the cognitive engine.

## 2. General Coding Principles

*   **DRY (Don't Repeat Yourself)**: Especially in React components and Tailwind styling.
*   **Accessibility (A11y)**: Ensure the Dashboard is usable and informative.
*   **Performance**: Optimize data fetching and rendering in the memory timeline.

## 3. Core Workflows

### 🧠 Eco Integration (MANDATORY)
Eco is our project's long-term cognitive layer. Use it to bridge context across sessions. The ECO memory server runs remotely at **https://eco.bennetleff.workers.dev**.

**1. Context Retrieval (Session Start)**
Before starting any task, you MUST query Eco:
- Search for the issue ID: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<ISSUE_ID>", "userId": "temper-agent"}`
- Search for related documentation: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<TOPIC>", "userId": "temper-agent"}` (e.g., "thermal budget", "resonant tank tuning")
- Review any **Reflections** left by previous agents on related components.

**2. Reflection (Session Wrap-up)**
After completing a task or ending a session, you MUST post a reflection:
- Summarize what you learned, architectural decisions made, and hurdles encountered.
- Use the memory endpoint: `POST https://eco.bennetleff.workers.dev/memories` with body `{"content": "REFLECTION: <summary>", "userId": "temper-agent"}`
- This ensures other agents (Claude, OpenCode) can benefit from your findings.

### Issue Tracking & Management
We use **beads (`bd`)** for all task tracking. **Do not use markdown TODOs.**

*   **Granularity is Critical**: Bias towards small, iterative tasks.
*   **Dependency-First Planning**: Use `bd dep add` to manage task ordering.

### Landing the Plane (Session Completion)
The session is **not** over until the plane has landed. You must execute this protocol before stopping:

1.  **Post Reflection**: Call `POST /memories` (with tag "reflection") to ECO.
2.  **File Follow-ups**: Create issues for any work left unfinished or discovered.
3.  **Verify Quality**: Run linting (`npm run lint`) and tests.
4.  **Sync & Push (MANDATORY)**:
    ```bash
    git pull --rebase
    bd sync
    git push
    git status  # Must show "up to date with origin"
    ```

## 4. Frontend Best Practices (Dashboard)

**Tooling**: `npm` (dependency management), `Next.js` (framework), `Tailwind CSS` (styling), `Chart.js` (visualization).

*   **Components**: Keep components small and focused.
*   **State Management**: Use React hooks efficiently.
*   **Styling**: Adhere to the established Tailwind palette in `lib/colors.ts`.

## 5. NetClassRules Fields (N4 — Single Source of Truth)

Every `NetClassRules` instance in `TEMPER_NET_CLASSES` must set:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `dru_priority` | `int` | **Yes** | DRU emission order (lower = earlier). Derived via `sorted(keys, key=lambda k: (dru_priority, k))`. Ties break lexicographically. |
| `required_layer` | `str \| None` | No | KiCad layer name constraint (e.g., `"B.Cu"` for HighVoltage). `None` = no constraint. |
| `safety_category` | `"HV" \| "LV" \| "AC" \| "iso" \| None` | No | Safety classification. `"AC"` is treated as HV-side in separation checks. |

**DRC integration**: `packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py` exports a shared `resolve_safety_category(net_class_str)` used by all three safety checks. When a net class is in `TEMPER_NET_CLASSES` with a non-`None` `safety_category`, the category is used directly. Otherwise a keyword-scan fallback fires with a **stderr warning** (grep-visible in CI logs). The warning convention: `"[temper-drc] safety_category fallback: ... Declare safety_category on net class '...' or add net to TEMPER_NET_ASSIGNMENTS."`

**Regression note**: `HighCurrent` was reclassified from *neither HV nor LV* to `"HV"` in this changeset. Existing boards with `HighCurrent`-classed components will now trigger HV/LV separation checks.

## 6. Operational Rules

*   **No "Ready when you are"**: You must push your changes (`bd sync && git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.
