#!/usr/bin/env python3
"""Transition-table generator for state machine validation.

Usage:
  python3 gen_transition_table.py --generate   # Write generated C file
  python3 gen_transition_table.py --check      # Validate table only (no output)
"""

import re
import sys
import os

import yaml

# ---------------------------------------------------------------------------
# Transition Table (loaded from YAML manifest)
# ---------------------------------------------------------------------------

def load_transitions_from_yaml(repo_root):
    """Load transition rows from firmware/transition_table.yaml.
    Returns a list of (from_state_enum, event_name_str, expected_to_enum,
    expected_fault_or_None, needs_fault_setup) tuples."""
    manifest_path = os.path.join(repo_root, "transition_table.yaml")

    with open(manifest_path, 'r') as f:
        manifest = yaml.safe_load(f)

    transitions = []
    for row in manifest.get('transitions', []):
        from_s = row['from']
        event = row['event']
        to_s = row['to']
        fault = row.get('fault') or None
        # needs_fault_setup is True for rows where from_state is STATE_FAULT
        needs_fault_setup = (from_s == 'STATE_FAULT')

        # Convert EVENT_* name to the event string name used in EVENT_STUBS
        # (e.g. EVENT_PAN_DETECTED -> PAN_DETECTED)
        event_name = event.replace('EVENT_', '')
        transitions.append((from_s, event_name, to_s, fault, needs_fault_setup))

    return transitions


def parse_event_list_from_header(header_path):
    """Extract EVENT_* members from state_machine.h for --check mode."""
    with open(header_path, 'r') as f:
        content = f.read()
    event_members = set()
    m = re.search(
        r'#define\s+EVENT_LIST\(X\)(.*?)(?:#define\s+EXPAND_EVENT_ENUM|\Z)',
        content, re.DOTALL)
    if m:
        for name in re.findall(r'\b(EVENT_\w+)', m.group(1)):
            event_members.add(name)
    return event_members

# ---------------------------------------------------------------------------
# Event-to-stub mapping
# ---------------------------------------------------------------------------
# Each event is a list of C statement strings (without trailing semicolons).

EVENT_STUBS = {
    "SELFTEST_PASS": "",
    "SELFTEST_FAIL": "mock_sm_fail_selftest_adc();",
    "START_BUTTON": "mock_sm_press_button(BUTTON_START);",
    "PAN_DETECTED": "mock_sm_set_pan_status(MOCK_PAN_PRESENT);",
    "PAN_TIMEOUT": "mock_sm_advance_time(6000);",
    "NEAR_TARGET": "mock_sm_set_pan_temperature(92.0f);",
    "PREHEAT_TIMEOUT": "mock_sm_advance_time(600001);",
    "OVER_TEMP": "mock_sm_set_heatsink_temperature(105.0f);",
    "OVER_CURRENT": "mock_sm_set_dc_bus_current(40.0f);",
    "FAN_FAILURE": "mock_sm_set_fan_running(false);",
    "PROBE_OPEN": "mock_sm_set_rtd_resistance(15000.0f);",
    "PROBE_SHORT": "mock_sm_set_rtd_resistance(5.0f);",
    "THERMAL_RUNAWAY": "mock_sm_set_pan_temperature(115.0f);",
    "PAN_REMOVED": (
        "mock_sm_set_pan_status(MOCK_PAN_ABSENT);\n"
        "    mock_sm_set_pan_temperature(25.0f);"
    ),
    "STOP_BUTTON": "mock_sm_press_button(BUTTON_STOP);",
    "TIMER_EXPIRED": (
        "state_machine_set_timer(true, 1000);\n"
        "    mock_sm_advance_time(2500);"
    ),
    "PAN_REPLACED_SAME": (
        "mock_sm_set_pan_status(MOCK_PAN_PRESENT);\n"
        "    mock_sm_set_pan_impedance(5.0f);"
    ),
    "PAN_REPLACED_DIFFERENT": (
        "mock_sm_set_pan_status(MOCK_PAN_PRESENT);\n"
        "    mock_sm_set_pan_impedance(5.0f);"
    ),
    "NO_PAN_TIMEOUT": "mock_sm_advance_time(4000);",
    "COOLED_DOWN": "mock_sm_set_heatsink_temperature(45.0f);",
    "COOLDOWN_OVERHEAT": "mock_sm_set_heatsink_temperature(105.0f);",
    "FAULT_RESET_CLEARED": (
        "mock_sm_set_heatsink_temperature(65.0f);\n"
        "    mock_sm_press_button(BUTTON_RESET);"
    ),
    "FAULT_RESET_PERSISTS": (
        "mock_sm_set_heatsink_temperature(105.0f);\n"
        "    mock_sm_press_button(BUTTON_RESET);"
    ),
}

# Pan detection is handled by a CONFIDENCE counter. For PAN_DETECTED,
# we need multiple updates or we pre-set the confidence counter.
# Since we can't set sm_ctx.pan_detect_confidence directly, we handle
# this in the generated C by calling update in a loop for PAN_DET rows.

# States that need a confidence-loop update for PAN_DETECTED to fire:
NEEDS_CONFIDENCE_LOOP = {"PAN_DETECTED"}

# ---------------------------------------------------------------------------
# Enum parsing
# ---------------------------------------------------------------------------

def parse_state_machine_header(header_path):
    """Extract STATE_* and FAULT_* members from state_machine.h X-macros."""
    with open(header_path, 'r') as f:
        content = f.read()

    state_members = set()
    fault_members = set()

    # Parse STATE_LIST X-macro entries
    m = re.search(
        r'#define\s+STATE_LIST\(X\)(.*?)(?:#define\s+EXPAND_STATE_ENUM|\Z)',
        content, re.DOTALL)
    if m:
        for name in re.findall(r'\b(STATE_\w+)', m.group(1)):
            state_members.add(name)

    # Parse FAULT_LIST X-macro entries
    m = re.search(
        r'#define\s+FAULT_LIST\(X\)(.*?)(?:#define\s+EXPAND_FAULT_ENUM|\Z)',
        content, re.DOTALL)
    if m:
        for name in re.findall(r'\b(FAULT_\w+)', m.group(1)):
            fault_members.add(name)

    return state_members, fault_members


def validate_table(transitions, states, faults, events=None):
    """Check every state, fault, and event in the table exists in the header."""
    table_states = set()
    table_faults = set()
    table_events = set()

    for from_s, event, to_s, fault, _ in transitions:
        table_states.add(from_s)
        table_states.add(to_s)
        if fault:
            table_faults.add(fault)
        # event names in the table are like "PAN_DETECTED", need "EVENT_PAN_DETECTED"
        table_event_enum = "EVENT_" + event
        table_events.add(table_event_enum)

    errors = []
    for s in table_states:
        if s not in states:
            errors.append(f"ERROR: '{s}' referenced in table but not found in state_machine.h")

    for f in table_faults:
        if f not in faults:
            errors.append(f"ERROR: '{f}' referenced in table but not found in state_machine.h")

    if events:
        for e in table_events:
            if e not in events:
                errors.append(f"ERROR: '{e}' referenced in table but not found in state_machine.h EVENT_LIST")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    for s in sorted(states - table_states):
        print(f"WARNING: {s} has zero transition rows in table", file=sys.stderr)

    for f in sorted(faults - table_faults):
        print(f"INFO: {f} has zero transition rows in table (not an error)", file=sys.stderr)

    if events:
        for e in sorted(events - table_events):
            print(f"WARNING: {e} has zero transition rows in table", file=sys.stderr)


# ---------------------------------------------------------------------------
# C code generation
# ---------------------------------------------------------------------------

def _c_event_stubs(transitions):
    """Generate the apply_event_stubs() function body (deduplicated)."""
    lines = []
    lines.append("static void apply_event_stubs(const char *event) {")
    seen = set()
    for row in transitions:
        event = row[1]
        if event in seen:
            continue
        seen.add(event)
        if event not in EVENT_STUBS:
            continue
        stub = EVENT_STUBS[event]
        if not stub:
            continue
        lines.append(f'    if (strcmp(event, "{event}") == 0) {{')
        for s in stub.split('\n'):
            s = s.strip()
            if s:
                lines.append(f"        {s}")
        lines.append("        return;")
        lines.append("    }")
    lines.append("}")
    return lines


def _c_preconditions():
    """Generate the apply_preconditions() function body."""
    lines = []
    lines.append("static void apply_preconditions(const transition_row_t *row) {")
    lines.append("    switch (row->from) {")

    # INIT: default (all tests pass) — nothing extra
    lines.append("    case STATE_INIT:")
    lines.append("        break;")

    # IDLE: requires target_temp > 0 (baseline already sets it to 100.0f)
    lines.append("    case STATE_IDLE:")
    lines.append("        break;")

    # PAN_DET: default pan_status is ABSENT, which works for timeout tests;
    # for PAN_DETECTED we set PAN_PRESENT in event stubs
    lines.append("    case STATE_PAN_DET:")
    lines.append("        break;")

    # PREHEAT / HEATING: must set pan PRESENT to avoid immediate pan-removal transition;
    # also set pan temp just below target to avoid immediate thermal-runaway
    lines.append("    case STATE_PREHEAT:")
    lines.append("    case STATE_HEATING:")
    lines.append("        mock_sm_set_pan_status(MOCK_PAN_PRESENT);")
    lines.append("        mock_sm_set_pan_temperature(92.0f);")
    lines.append("        break;")

    # NO_PAN: set pan status absent so the state logic sees no pan
    lines.append("    case STATE_NO_PAN:")
    lines.append("        mock_sm_set_pan_status(MOCK_PAN_ABSENT);")
    lines.append("        break;")

    # COOLDOWN: heatsink above SAFE_IDLE_TEMP so normal cooldown logic runs
    lines.append("    case STATE_COOLDOWN:")
    lines.append("        mock_sm_set_heatsink_temperature(65.0f);")
    lines.append("        break;")

    # FAULT: handled specially in the test runner (two-step pattern)
    lines.append("    case STATE_FAULT:")
    lines.append("        break;")
    lines.append("    }")
    lines.append("}")
    return lines


def _c_fault_setup():
    """Generate code to trigger a fault transition (for FAULT-from tests).
    Safe defaults prevent unwanted secondary transitions after safety
    interlocks fire (e.g., PAN_REMOVED after CHECK_SAFETY in PREHEAT)."""
    return [
        "static void trigger_fault_entry(fault_code_t code) {",
        "    /* Prevent secondary transitions: pan present, sensors nominal.",
        "       Keep pan_temp far from target so NEAR_TARGET doesn't fire",
        "       before check_safety_interlocks() in PREHEAT. */",
        "    mock_sm_set_pan_status(MOCK_PAN_PRESENT);",
        "    mock_sm_set_pan_temperature(25.0f);",
        "    mock_sm_set_fan_running(true);",
        "    mock_sm_set_dc_bus_current(0.0f);",
        "    mock_sm_set_rtd_resistance(100.0f);",
        "    switch (code) {",
        "    case FAULT_OVER_TEMP:",
        "        mock_sm_set_heatsink_temperature(105.0f);",
        "        state_machine_force_state(STATE_PREHEAT);",
        "        state_machine_update();",
        "        break;",
        "    case FAULT_SELF_TEST_FAILED:",
        "        mock_sm_fail_selftest_adc();",
        "        state_machine_force_state(STATE_INIT);",
        "        state_machine_update();",
        "        break;",
        "    default:",
        "        break;",
        "    }",
        "}",
    ]


def _c_table_rows(transitions):
    """Generate the transition_table[] array entries."""
    lines = []
    for from_s, event, to_s, fault, _ in transitions:
        has_fault = "true" if fault else "false"
        fault_val = fault if fault else "FAULT_NONE"
        extra = ""
        if event == "PAN_REPLACED_SAME":
            extra = "  /* same impedance -> resumes PREHEAT */"
        elif event == "PAN_REPLACED_DIFFERENT":
            extra = "  /* different impedance -> COOLDOWN */"
        elif event == "NEAR_TARGET" and from_s == "STATE_HEATING":
            extra = "  /* self-loop (PID control continues) */"
        lines.append(
            f'    {{ {from_s}, "{event}", {to_s}, {fault_val}, {has_fault} }},{extra}'
        )
    return lines


def _c_test_function():
    """Generate the test_transition_table() function."""
    return [
        "/* Events using show_message_then_transition() need a second update pass.",
        "   MESSAGE_DISPLAY_TIME_MS = 2000 from state_machine.c */",
        "#define MESSAGE_DRAIN_TIME_MS 2001",
        "",
        "/* Drain any pending non-blocking message and return the settled state */",
        "static system_state_t drain_message(void) {",
        "    state_machine_update();",
        "    return state_machine_get_state();",
        "}",
        "",
        "void test_transition_table(void) {",
        "    for (size_t i = 0; i < test_row_count; i++) {",
        "        const transition_row_t *row = &test_rows[i];",
        "        char msg[128];",
        '        snprintf(msg, sizeof(msg), "Row %zu: %s + %s", i,',
        '                 state_machine_get_state_string(row->from), row->event);',
        "",
        "        /* Reset mock state to safe defaults */",
        "        mock_sm_reset();",
        "",
        "        /* Initialize state machine (sets last_update_time_ms = 0) */",
        "        state_machine_init();",
        "",
        "        /* Baseline: keep target > 0 so START_BUTTON fires in IDLE */",
        "        state_machine_set_target_temp(100.0f);",
        "",
        "        /* Prime the update cycle so last_update_time_ms is non-zero.",
        "           Needed for dt_ms calculation in timer-expiry tests. */",
        "        mock_sm_advance_time(1);",
        "        state_machine_update();  /* INIT -> IDLE (self-tests pass) */",
        "",
        "        /* ============================================================",
        "         * Special case: FAULT-from tests (two-step: trigger fault, then",
        "         * test reset behaviour).",
        "         * ============================================================ */",
        "        if (row->from == STATE_FAULT) {",
        "            /* Step 1: trigger a known fault (OVER_TEMP) to reach FAULT */",
        "            trigger_fault_entry(FAULT_OVER_TEMP);",
        "",
        "            /* Step 2: set up reset conditions and test */",
        "            apply_event_stubs(row->event);",
        "            system_state_t result = drain_message();",
        "",
        "            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to, result, msg);",
        "            if (row->has_fault) {",
        "                TEST_ASSERT_EQUAL_INT_MESSAGE(",
        "                    row->expected_fault, state_machine_get_fault(), msg);",
        "            }",
        "            continue;",
        "        }",
        "",
        "        /* ============================================================",
        "         * Standard single-update pattern for most transitions.",
        "         * ============================================================ */",
        "",
        "        /* Apply per-state preconditions (pan present, etc.) */",
        "        apply_preconditions(row);",
        "",
        "        /* Force to the starting state */",
        "        state_machine_force_state(row->from);",
        "",
        "        /* Apply event-specific stubs (button presses, sensor values) */",
        "        apply_event_stubs(row->event);",
        "",
        "        /* PAN_REPLACED_DIFFERENT: needs initial_pan_impedance set",
        "           (normally set during PAN_DET). Go through PAN_DET first,",
        "           then force to NO_PAN and re-apply the event stubs. */",
        "        if (strcmp(row->event, \"PAN_REPLACED_DIFFERENT\") == 0) {",
        "            /* First go through PAN_DET to establish initial impedance */",
        "            state_machine_force_state(STATE_PAN_DET);",
        "            mock_sm_set_pan_status(MOCK_PAN_PRESENT);",
        "            for (int j = 0; j < 4; j++) {",
        "                state_machine_update(); /* PAN_DET -> PREHEAT */",
        "            }",
        "            /* initial_pan_impedance is now set to get_pan_impedance() */",
        "            /* Now transition to NO_PAN with a different impedance */",
        "            state_machine_force_state(STATE_NO_PAN);",
        "            mock_sm_set_pan_status(MOCK_PAN_PRESENT);",
        "            mock_sm_set_pan_impedance(10.0f);  /* 100% error vs 5.0 */",
        "            state_machine_update();  /* triggers show_message */",
        "            mock_sm_advance_time(MESSAGE_DRAIN_TIME_MS);",
        "            state_machine_update();",
        "            system_state_t result2 = state_machine_get_state();",
        "            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to, result2, msg);",
        "            if (row->has_fault) {",
        "                TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_fault,",
        "                    state_machine_get_fault(), msg);",
        "            }",
        "            continue;",
        "        }",
        "",
        "        /* PAN_DETECTED: the confidence counter needs multiple updates. */",
        "        if (strcmp(row->event, \"PAN_DETECTED\") == 0) {",
        "            for (int j = 0; j < 4; j++) {",
        "                state_machine_update();",
        "            }",
        "            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to,",
        "                state_machine_get_state(), msg);",
        "            continue;",
        "        }",
        "",
        "        /* PAN_REMOVED: needs temp reset (avoid near-target steal)",
        "           and in HEATING multiple updates to clear debounce. */",
        "        if (strcmp(row->event, \"PAN_REMOVED\") == 0) {",
        "            for (int j = 0; j < 12; j++) {",
        "                state_machine_update();",
        "            }",
        "            system_state_t result3 = state_machine_get_state();",
        "            /* If we ended up in a message-pending state, drain it */",
        "            if (result3 != row->expected_to) {",
        "                mock_sm_advance_time(MESSAGE_DRAIN_TIME_MS);",
        "                result3 = drain_message();",
        "            }",
        "            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to, result3, msg);",
        "            if (row->has_fault) {",
        "                TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_fault,",
        "                    state_machine_get_fault(), msg);",
        "            }",
        "            continue;",
        "        }",
        "",
        "        /* Run the state update once */",
        "        state_machine_update();",
        "",
        "        /* Events that use show_message_then_transition() need a second",
        "           update to drain the pending message and reach the target. */",
        "        system_state_t actual = state_machine_get_state();",
        "        if (actual != row->expected_to) {",
        "            /* Advance time past the non-blocking message period */",
        "            mock_sm_advance_time(MESSAGE_DRAIN_TIME_MS);",
        "            actual = drain_message();",
        "        }",
        "",
        "        /* Assertions */",
        "        TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to, actual, msg);",
        "        if (row->has_fault) {",
        "            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_fault,",
        "                state_machine_get_fault(), msg);",
        "        }",
        "    }",
        "}",
    ]


def _c_cross_check():
    """Generate a function that cross-checks the test table against the
    official transition_table[][] from transition_table.h."""
    return [
        "/* Cross-check: verify the official transition_table.h matches our test rows */",
        "static event_t event_enum_from_string(const char *name) {",
        "    for (size_t i = 0; i < EVENT_COUNT; i++) {",
        '        if (strcmp(name, event_name_table[i].name) == 0)',
        "            return event_name_table[i].value;",
        "    }",
        "    return EVENT_COUNT;",
        "}",
        "",
        "void test_transition_table_cross_check(void) {",
        "    for (size_t i = 0; i < test_row_count; i++) {",
        "        const transition_row_t *row = &test_rows[i];",
        "        event_t ev = event_enum_from_string(row->event);",
        '        char msg[128];',
        '        snprintf(msg, sizeof(msg), "Cross-check row %zu: %s + %s",',
        '                 i, state_machine_get_state_string(row->from), row->event);',
        "",
        '        TEST_ASSERT_NOT_EQUAL(EVENT_COUNT, ev);',
        "",
        "        system_state_t official = transition_table[row->from][ev];",
        '        TEST_ASSERT_NOT_EQUAL(TRANSITION_INVALID, official);',
        '        TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_to, official, msg);',
        "",
        "        if (row->has_fault) {",
        "            fault_code_t official_fault = transition_fault[row->from][ev];",
        '            TEST_ASSERT_EQUAL_INT_MESSAGE(row->expected_fault, official_fault, msg);',
        "        }",
        "    }",
        "}",
    ]


def generate_c_output(transitions, output_path):
    """Write the generated C file."""
    header_path = os.path.join(os.path.dirname(__file__), "..", "main", "state_machine.h")
    states, faults = parse_state_machine_header(header_path)
    validate_table(transitions, states, faults)

    lines = [
        "/**",
        " * @file test_transition_table_generated.c",
        " * @brief AUTO-GENERATED by firmware/test/gen_transition_table.py",
        " * ",
        " * Transition-table-driven state machine validation.",
        " * DO NOT EDIT BY HAND — edit gen_transition_table.py and regenerate.",
        " */",
        "",
        '#include "test_common.h"',
        '#include "../main/state_machine.h"',
        '#include "../main/transition_table.h"',
        '#include <string.h>',
        '#include <stdio.h>',
        "",
        "/* Mock control functions from state_machine_stubs.c */",
        "extern void mock_sm_reset(void);",
        "extern void mock_sm_advance_time(uint32_t ms);",
        "extern void mock_sm_set_pan_temperature(float temp_c);",
        "extern void mock_sm_set_heatsink_temperature(float temp_c);",
        "extern void mock_sm_set_dc_bus_current(float amps);",
        "extern void mock_sm_set_rtd_resistance(float ohms);",
        "extern void mock_sm_set_pan_status(int status);",
        "extern void mock_sm_set_pan_impedance(float impedance);",
        "extern void mock_sm_set_fan_running(bool running);",
        "extern void mock_sm_press_button(button_id_t button);",
        "extern void mock_sm_fail_selftest_adc(void);",
        "",
        "#define MOCK_PAN_ABSENT  0",
        "#define MOCK_PAN_PRESENT 1",
        "",
        "/* Transition descriptor */",
        "typedef struct {",
        "    system_state_t from;",
        "    const char *event;",
        "    system_state_t expected_to;",
        "    fault_code_t expected_fault;",
        "    bool has_fault;",
        "} transition_row_t;",
        "",
        "/* The test transition rows (generated from transition_table.yaml) */",
        "static const transition_row_t test_rows[] = {",
    ]

    for l in _c_table_rows(transitions):
        lines.append(l)

    lines.extend([
        "};",
        "static const size_t test_row_count = "
        "sizeof(test_rows) / sizeof(test_rows[0]);",
        "",
    ])

    lines.extend(_c_event_stubs(transitions))
    lines.append("")

    lines.extend(_c_fault_setup())
    lines.append("")

    lines.extend(_c_preconditions())
    lines.append("")

    lines.extend(_c_test_function())
    lines.append("")
    lines.extend(_c_cross_check())

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"Generated {output_path} ({len(transitions)} transition rows)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.join(script_dir, "..")
    header_path = os.path.join(script_dir, "..", "main", "state_machine.h")
    output_path = os.path.join(script_dir, "test_transition_table_generated.c")

    if len(sys.argv) < 2:
        print("Usage: gen_transition_table.py --generate | --check", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    # Load transitions from the YAML manifest
    transitions = load_transitions_from_yaml(repo_root)

    states, faults = parse_state_machine_header(header_path)
    events = parse_event_list_from_header(header_path)

    if cmd == "--check":
        validate_table(transitions, states, faults, events)
        print(f"Validated {len(transitions)} transition rows against {header_path}")
        return

    if cmd == "--generate":
        generate_c_output(transitions, output_path)
        return

    print(f"Unknown command: {cmd}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
