---
title: X-Macro Single-Source-of-Truth Pattern for Firmware
date: 2026-06-22
category: architecture-patterns
module: firmware
problem_type: architecture_pattern
component: build-system
severity: medium
applies_when:
  - "Adding or removing a state machine state, fault code, or event"
  - "Changing a board-level config constant that has multiple consumers"
  - "Updating a transition in the (state, event) -> next_state table"
  - "Onboarding new developers to the firmware codegen pipeline"
tags: [x-macro, ssot, codegen, state-machine, transition-table, config, yaml, c-preprocessor]
---

# X-Macro Single-Source-of-Truth Pattern for Firmware

## Context

The Temper firmware contains many enumerations and lookup tables that must stay synchronized: state names, fault codes, event types, board-level config constants, and the complete 8-state x 22-event transition table. Keeping these consistent by hand across multiple files is error-prone and creates drift over time.

The project uses two complementary SSOT strategies to eliminate this problem:

1. **X-macros** (C preprocessor) — for enum/string-table synchronization within a single `.h` file
2. **YAML + Python codegen** — for cross-file synchronization where data originates in a human-editable manifest and emits C headers

## Guidance

### Strategy 1: X-Macro for In-File Enum-String Synchronization

Define the list once with `#define LIST_NAME(X)`, then expand it through disposable expander macros to produce the enum, a COUNT sentinel, and a name lookup table — all from the same single-source list.

**Pattern skeleton:**

```c
/* 1. Define the single-source list */
#define STATE_LIST(X) \
    X(STATE_A, "A")  \
    X(STATE_B, "B")  \
    X(STATE_C, "C")

/* 2. Generate the enum + COUNT sentinel */
#define EXPAND_STATE_ENUM(sym, str) sym,
typedef enum {
    STATE_LIST(EXPAND_STATE_ENUM)
    STATE_COUNT
} state_t;
#undef EXPAND_STATE_ENUM

/* 3. Generate the name lookup table */
#define EXPAND_STATE_NAME(sym, str) { sym, str },
typedef struct { state_t value; const char *name; } name_entry_t;
static const name_entry_t name_table[] = {
    STATE_LIST(EXPAND_STATE_NAME)
};
#undef EXPAND_STATE_NAME
```

**Rules:**
- Add/remove entries in one place only: the `X(...)` list
- The enum numbering, `COUNT`, and string table all update automatically
- Undefine each expander macro after its single use to avoid namespace pollution
- Use `_Static_assert` where dimensions depend on the sentinel (see Strategy 2)

### Strategy 2: YAML Manifest + Python Codegen for Cross-File SSOT

When the source data spans multiple generated outputs, define it in a YAML manifest and regenerate C headers deterministically.

**Workflow:**
1. Edit the YAML manifest
2. Run the codegen script
3. Stage both files together in a single commit

The codegen scripts are idempotent — they compare against the current file and only overwrite if content differs. This keeps `git diff --exit-code` usable in CI to validate that generated files match committed state.

## Why This Matters

**Without SSOT**, changing a single state name requires editing 3+ places (enum, switch-case labels, debug string table). Inevitably one drifts, and the compiler gives no warning — you get a runtime bug.

**With SSOT**, the same change is one line in the manifest or X-macro list, and every consumer picks it up automatically.

The `_Static_assert` guards at compile time catch dimension mismatches. With `TRANSITION_INVALID` sentinels, accessing an illegal (state, event) cell is a deliberate runtime check rather than undefined behavior reading uninitialized memory.

## When to Apply

- When any enum needs a companion string-name table for debugging, logging, or display
- When configuration constants are consumed by multiple compilation units
- When a table is too large to maintain manually (8 x 22 = 176 cells, plus a parallel fault-code table of equal size)
- When you want CI enforcement that generated files match their manifests

## Examples

### Example 1: STATE_LIST X-Macro (`firmware/main/state_machine.h`)

The state machine header defines three X-macro lists — states, faults, events. Each one generates an enum, a COUNT sentinel, and a name table.

**Single-source list** (`state_machine.h:30-38`):

```c
#define STATE_LIST(X) \
    X(STATE_INIT,     "INIT") \
    X(STATE_IDLE,     "IDLE") \
    X(STATE_PAN_DET,  "PAN_DET") \
    X(STATE_PREHEAT,  "PREHEAT") \
    X(STATE_HEATING,  "HEATING") \
    X(STATE_NO_PAN,   "NO_PAN") \
    X(STATE_COOLDOWN, "COOLDOWN") \
    X(STATE_FAULT,    "FAULT")
```

**Generated enum** (`state_machine.h:40-45`):

```c
#define EXPAND_STATE_ENUM(sym, str)  sym,
typedef enum {
    STATE_LIST(EXPAND_STATE_ENUM)
    STATE_COUNT           /* Sentinal auto-tracks list size */
} system_state_t;
#undef EXPAND_STATE_ENUM
```

**Generated name table** (`state_machine.h:47-52`):

```c
#define EXPAND_STATE_NAME(sym, str)  { sym, str },
typedef struct { system_state_t value; const char *name; } state_name_entry_t;
static const state_name_entry_t state_name_table[] = {
    STATE_LIST(EXPAND_STATE_NAME)
};
#undef EXPAND_STATE_NAME
```

The same pattern repeats for `FAULT_LIST` (13 entries, `state_machine.h:61-88`) and `EVENT_LIST` (22 entries, `state_machine.h:97-134`).

### Example 2: YAML Config Manifest → C Struct (`firmware/config.yaml` → `firmware/config.h`)

Board-level parameters (temperature limits, timeouts, ADC thresholds) are declared in a structured YAML manifest.

**Manifest snippet** (`config.yaml:14-21`):

```yaml
temperatures:
  - c_symbol: SAFE_IDLE_TEMP
    field: safe_idle_temp
    value: 50.0
    c_type: float
    units: "°C"
    env_var: TEMP_SAFE_IDLE_C
    doc: "Safe temperature to return to IDLE"
```

**Codegen script** (`firmware/tools/gen_config.py:20-54`):

```python
def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "config.yaml"
    template_path = Path(__file__).resolve().parent / "config.h.j2"
    output_path = repo_root / "config.h"

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)
    rendered = template.render(**manifest)

    # Idempotent: only overwrite if content differs
    tmp_path = output_path.with_suffix(".h.tmp")
    with open(tmp_path, "w") as f:
        f.write(rendered)

    if output_path.exists():
        with open(output_path) as f:
            existing = f.read()
        if existing == rendered:
            tmp_path.unlink()
            print("config.h up to date")
            return

    tmp_path.rename(output_path)
    print("config.h regenerated")
```

The script uses Jinja2 to render `config.h` from `config.yaml`. The manifest supports `legacy_define` fields for gradual migration from bare `#define`s to struct-based configuration, and `legacy_define_only` for values that need a `#define` but no struct field.

### Example 3: Transition Table YAML → C 2D Array (`firmware/transition_table.yaml` → `firmware/main/transition_table.h`)

The 8-state x 22-event transition table is defined as a sparse YAML list and codegen expands it into a complete C 2D designated-initializer array. Every cell is explicitly set — valid transitions get a next-state, invalid ones get `TRANSITION_INVALID`.

**Manifest snippet** (`transition_table.yaml:14-16`):

```yaml
transitions:
  # INIT
  - { from: STATE_INIT, event: EVENT_SELFTEST_PASS,  to: STATE_IDLE }
  - { from: STATE_INIT, event: EVENT_SELFTEST_FAIL,  to: STATE_FAULT, fault: FAULT_SELF_TEST_FAILED }
```

**Generated C** (`transition_table.h:25-50`, showing the `STATE_INIT` row):

```c
static const system_state_t transition_table[STATE_COUNT][EVENT_COUNT] = {
    [STATE_INIT] = {
        [EVENT_SELFTEST_PASS] = STATE_IDLE,
        [EVENT_SELFTEST_FAIL] = STATE_FAULT,
        [EVENT_START_BUTTON] = TRANSITION_INVALID,
        /* ... 19 more cells explicitly set to TRANSITION_INVALID ... */
    },
    /* ... 7 more state rows ... */
};
```

**Compile-time guards** (`transition_table.h:434-440`):

```c
_Static_assert(
    sizeof(transition_table) == STATE_COUNT * EVENT_COUNT * sizeof(system_state_t),
    "transition_table dimensions must equal STATE_COUNT * EVENT_COUNT");

_Static_assert(
    sizeof(transition_fault) == STATE_COUNT * EVENT_COUNT * sizeof(fault_code_t),
    "transition_fault dimensions must equal STATE_COUNT * EVENT_COUNT");
```

These guards catch the case where STATE_COUNT or EVENT_COUNT changes (from the X-macro lists) but the generated table is not regenerated — a dimension mismatch becomes a compile error.

## Related

- `firmware/main/state_machine.h` — X-macro definitions for STATE_LIST, FAULT_LIST, EVENT_LIST
- `firmware/config.yaml` — board config manifest
- `firmware/tools/gen_config.py` — YAML-to-C config codegen
- `firmware/transition_table.yaml` — transition table manifest
- `firmware/main/transition_table.h` — generated transition table
- `firmware/tools/gen_transition_table.py` — YAML-to-C transition table codegen
- `AGENTS.md` — Transition Table Regeneration and Firmware Config Codegen sections
