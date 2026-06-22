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

## 5. LOC Cap Gate

A 1000-line ceiling is enforced on source `.py` and `.c` files by CI.

**Gate command:** `uv run python tools/loc_cap_check.py`

**Allowlist:** `.loc-allowlist.txt` at repo root. Format:
```
# Format: <repo-relative-path> <baseline_lines> <ticket-id> # <description>
```

**Strict-shrink policy:** The allowlist must shrink monotonically. Adding a new entry requires removing a larger/comparable one. The gate's `NEW_ENTRY_NO_REMOVAL` check rejects new entries without corresponding removals.

**Exemption globs:**
- Include: `packages/*/src/temper_*/**/*.py`, `firmware/**/*.c`
- Exclude: `packages/*/tests/**`, `firmware/test/**`, `firmware/test/build/**`, `**/__pycache__/**`, `**/build/**`

When growing a file past 1000 lines, see the gate's failure message for the specific violation class.

## 6. Operational Rules

*   **No "Ready when you are"**: You must push your changes (`bd sync && git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.
