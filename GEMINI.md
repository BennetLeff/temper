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

### Issue Tracking & Management (Mandatory)
We use **beads (`bd`)** for all task tracking. **Do not use markdown TODOs.**

*   **Granularity is Critical**: Bias towards small, iterative tasks.
    *   **Epics**: Large features should be broken into 5-15 subtasks.
    *   **Tasks**: Each task should be completable in 30-60 minutes. If it takes longer, split it.
    *   **Actionable Titles**: Use verb-centric, specific titles (e.g., `Implement Gumbel-Softmax rotation` instead of `Fix rotation`).
    *   **Contextual Descriptions**: Always include *Why*, *What*, and *How* in the description.
*   **Dependency-First Planning**:
    *   Use `bd dep add <dependent> <prerequisite>` (X needs Y).
    *   Avoid "Phase" or "Step" naming; name tasks by what they deliver.
*   **Discovery**: Link new findings immediately with `discovered-from` dependencies.

### Agentic Workflows (Tiered Delegation)
We use a multi-agent system where a **Master Agent** delegates to specialized **Worker Agents**.

*   **Model Tiers**: 
    *   **Thinking (Pro)**: `architect`, `security`. Used for high-reasoning tasks.
    *   **Fast (Flash)**: `coder`, `tester`. Used for rapid execution.
*   **Delegation Methods**:
    *   **Label-Driven (Recommended)**: Add label `agent:<role>` to an issue, then run `python3 tools/agents/auto_assign.py`.
    *   **Direct Command**: `python3 tools/agents/assign.py <issue_id> <role>`.
*   **Review Cycle**: Worker agents write to `agent_outputs/`. You must review their proposed resolutions before merging into the codebase.

### Landing the Plane (Session Completion)
The session is **not** over until the plane has landed. You must execute this protocol before stopping:

1.  **File Follow-ups**: Create issues for any work left unfinished or discovered.
2.  **Verify Quality**: Run tests (`pytest`, `ctest`) and linters (`ruff`, `golangci-lint`) to ensure no regressions.
3.  **Update Issue State**: Close completed tasks and update progress on active ones.
4.  **Sync & Push (MANDATORY)**:
    ```bash
    git pull --rebase
    bd sync
    git push
    git status  # Must show "up to date with origin"
    ```
5.  **No Exceptions**: Never say "ready to push when you are." You are responsible for pushing all work to the remote repository.

### 3. Python TDD Best Practices (temper-placer)

**Tooling**: `uv` (dependency management), `pytest` (testing), `ruff` (linting), `ty` (type checking).
**Python Version**: 3.11+ (Required)

### The TDD Cycle
1.  **Red**: Write a failing test in `tests/`.
    *   Unit tests should be fast (<10ms).
    *   Use descriptive names: `test_overlap_loss_returns_positive_for_intersection`.
2.  **Green**: Implement the minimum code in `src/` to pass the test.
3.  **Refactor**: Improve code quality while keeping tests green. Run `ruff check` and `ty`.

### Testing Hierarchy
*   **Unit Tests** (`tests/losses/`, `tests/geometry/`): Isolate logic. Mock external dependencies.
*   **Integration Tests** (`tests/integration/`): Test full pipelines (e.g., KiCad roundtrip).
*   **Property-Based Tests**: Use `hypothesis` for geometry/math functions.
*   **Validation**: Verify against KiCad DRC where possible.

### Dependency Management
*   Use `uv venv` and `uv pip install -e ".[dev]"`.
*   Lock dependencies in `uv.lock`.

## 4. Electrical Engineering Best Practices

### PCB Design (KiCad)
*   **Hierarchy**: Respect the hierarchical sheet structure (`half_bridge`, `mcu`, etc.).
*   **Library**: Use local `components/` for symbols/footprints. **Do not rely on global libraries.**
*   **Documentation**:
    *   New component? Create `components/<PART>/<PART>_Documentation.md`.
    *   Design decision? Create `docs/<DECISION>_DESIGN.md`.

### Simulation (SPICE)
*   **Engine**: `ngspice`.
*   **Workflow**:
    1.  Create/Modify testbench in `simulation/testbenches/`.
    2.  Run: `ngspice -b sim_XX_name.cir`.
    3.  Analyze results and document in `simulation/results/sim_XX_name.md`.
*   **Models**: Store SPICE models in `simulation/models/`.

### Safety & Hardware
*   **Criticality**: Changes to `firmware/` or `pcb/half_bridge` can cause physical damage.
*   **Verification**:
    *   **Simulation First**: Verify power stage changes in SPICE before PCB updates.
    *   **Interlocks**: Never bypass safety checks in production firmware.

## 5. Firmware Development (ESP32-S3)

*   **Framework**: ESP-IDF.
*   **Architecture**: State Machine (`main/state_machine.c`).
*   **Testing**:
    *   **Unity Framework**: Used for both unit (host-based) and integration tests.
    *   **Run Tests**: `cd firmware/test/build && make && ctest`.
    *   **Coverage**: Maintain >80% coverage on safety-critical logic.

## 6. Operational Rules

*   **No "Ready when you are"**: You must push your changes (`bd sync && git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.
