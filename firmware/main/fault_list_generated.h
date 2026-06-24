/**
 * @file fault_list_generated.h
 * @brief Fault code list — GENERATED from firmware/test/traces/manifest.json
 *
 * DO NOT EDIT BY HAND.
 * Regenerate: python3 firmware/tools/gen_fault_list.py
 *
 * This file is the single source of truth for fault codes.
 * Entries are derived from:
 *   1. firmware/test/traces/manifest.json (SIL fault-injection scenarios)
 *   2. firmware/tools/fault_list_supplemental.yaml (legacy entries without SIL scenarios)
 *
 * Add a fault:
 *   - With SIL scenario: add an entry to firmware/test/traces/manifest.json
 *   - Without SIL scenario: add to firmware/tools/fault_list_supplemental.yaml
 *
 * The FAULT_LIST(X) macro expands to the enum, FAULT_COUNT sentinel,
 * and string-name table via the macros defined in state_machine.h.
 */

#define FAULT_LIST(X) \
    X(FAULT_NONE, "NO FAULT") \
    X(FAULT_RUNAWAY_BOUNDARY, "RUNAWAY BOUNDARY") \
    X(FAULT_SELF_TEST_FAILED, "SELF TEST FAIL") \
    X(FAULT_WATCHDOG_RESET, "WATCHDOG RESET") \
    X(FAULT_PAN_DETECT_HW, "PAN DETECT HW") \
    X(FAULT_ADC_STUCK, "ADC STUCK") \
    X(FAULT_COOLDOWN_OVERHEAT, "COOLDOWN FAULT") \
    X(FAULT_FAN_FAILURE, "FAN FAILED") \
    X(FAULT_IGBT_SHORT, "IGBT SHORT") \
    X(FAULT_OVER_CURRENT, "OVER CURRENT") \
    X(FAULT_OVER_TEMP, "OVER TEMP") \
    X(FAULT_PROBE_OPEN, "PROBE OPEN") \
    X(FAULT_PROBE_SHORT, "PROBE SHORT") \
    X(FAULT_THERMAL_RUNAWAY, "THERMAL RUNAWAY") 

/* FAULT_COUNT is derived from the above list — see state_machine.h.
   After regeneration:  9 manifest + 5 supplemental = 14 total entries. */
