# Gemini Agent Instructions for Temper Project

This file establishes the context and best practices for Gemini agents working on the Temper project. It synthesizes instructions from `AGENTS.md` and `AGENT_INSTRUCTIONS.md` while emphasizing Python TDD and Electrical Engineering standards.

## 1. Project Overview

**Temper** is a high-power induction heating system consisting of:
- **Hardware**: Half-bridge topology (IGBTs), ESP32-S3 MCU, resonant tank, and safety interlocks.
- **Firmware**: Safety-critical C code (ESP-IDF) driven by an 8-state state machine.
- **Software**: `temper-placer`, a JAX-based PCB placement optimizer using differentiable physics and curriculum learning.

## 2. General Coding Principles

*   **DRY (Don't Repeat Yourself)**: Avoid duplication. Extract shared logic into reusable components or utilities, especially for geometric transforms and loss calculations.
*   **YAGNI (You Ain't Gonna Need It)**: Do not over-engineer. Implement only what is required for the current task. Avoid speculative features or complex abstractions until they are demonstrably necessary.
*   **Readability Over Cleverness**: Code is read more often than it is written. Use clear variable names, maintain consistent formatting (Ruff), and document *why* complex math or safety logic is implemented.
*   **Safety First**: In firmware and power electronics, "clever" shortcuts can lead to physical hardware failure. Stick to proven, verifiable patterns.

## 3. Core Workflows

### 🧠 ECO Integration (MANDATORY)
ECO is our project's long-term cognitive layer. Use it to bridge context across sessions. The ECO memory server runs remotely at **https://eco.bennetleff.workers.dev**.

**1. Context Retrieval (Session Start)**
Before starting any task, you MUST query ECO:
- Search for the issue ID: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<ISSUE_ID>", "userId": "temper-agent"}`
- Search for related documentation: `POST https://eco.bennetleff.workers.dev/memories/search` with body `{"query": "<TOPIC>", "userId": "temper-agent"}` (e.g., "thermal budget", "resonant tank tuning")
- Review any **Reflections** left by previous agents on related components.

**2. Reflection (Session Wrap-up)**
After completing a task or ending a session, you MUST post a reflection:
- Summarize what you learned, architectural decisions made, and hurdles encountered.
- Use the memory endpoint: `POST https://eco.bennetleff.workers.dev/memories` with body `{"content": "REFLECTION: <summary>", "userId": "temper-agent", "tags": ["reflection", "architecture"]}`
- This ensures other agents (Claude, OpenCode) can benefit from your findings.

### Issue Tracking & Management

*   **Granularity is Critical**: Bias towards small, iterative tasks.
    *   **Epics**: Large features should be broken into 5-15 subtasks.
    *   **Tasks**: Each task should be completable in 30-60 minutes. If it takes longer, split it.
*   **Discovery**: Link new findings immediately.

### Agentic Workflows (Tiered Delegation)
We use a multi-agent system where a **Master Agent** delegates to specialized **Worker Agents**.

*   **Delegation Methods**:
    *   **Label-Driven**: Add label `agent:<role>` to an issue, then run `python3 tools/agents/auto_assign.py`.
*   **Review Cycle**: Worker agents write to `agent_outputs/`. You must review their proposed resolutions before merging into the codebase.

### Landing the Plane (Session Completion)
The session is **not** over until the plane has landed. You must execute this protocol before stopping:

1.  **Post Reflection**: Call `POST /memories` (with tag "reflection") to ECO.
2.  **File Follow-ups**: Create issues for any work left unfinished or discovered.
3.  **Verify Quality**: Run tests (`pytest`, `ctest`) and linters (`ruff`, `golangci-lint`).
4.  **Update Issue State**: Close completed tasks and update progress on active ones.
5.  **Sync & Push (MANDATORY)**:
    ```bash
    git pull --rebase
    git push
    git status  # Must show "up to date with origin"
    ```

## 4. Python TDD Best Practices (temper-placer)

**Tooling**: `uv` (dependency management), `pytest` (testing), `ruff` (linting), `ty` (type checking).
**Python Version**: 3.11+ (Required)

### The TDD Cycle
1.  **Red**: Write a failing test in `tests/`.
2.  **Green**: Implement the minimum code in `src/` to pass the test.
3.  **Refactor**: Improve code quality while keeping tests green. Run `ruff check` and `ty`.

## 5. Electrical Engineering Best Practices

### PCB Design (KiCad)
*   **Hierarchy**: Respect the hierarchical sheet structure.
*   **Library**: Use local `components/` for symbols/footprints. **Do not rely on global libraries.**
*   **Documentation**:
    *   New component? Create `components/<PART>/<PART>_Documentation.md`.
    *   Design decision? Create `docs/<DECISION>_DESIGN.md`.

## 6. Firmware Development (ESP32-S3)

*   **Framework**: ESP-IDF.
*   **Architecture**: State Machine (`main/state_machine.c`).
*   **Testing**:
    *   **Unity Framework**: Used for both unit (host-based) and integration tests.
    *   **Run Tests**: `cd firmware/test/build && make && ctest`.

## 7. Operational Rules

*   **No "Ready when you are"**: You must push your changes (`git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.
