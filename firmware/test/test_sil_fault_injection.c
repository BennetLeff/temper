/**
 * @file test_sil_fault_injection.c
 * @brief SIL (Software-in-the-Loop) fault-injection test runner
 *
 * Reads traces/manifest.json, replays perturbed plant-model traces
 * against the real state_machine.c (compiled for HOST_BUILD), and
 * validates that safety faults cause correct state transitions at
 * correct latency.
 *
 * Two configurations are built from this one file (firmware/test/
 * CMakeLists.txt):
 *
 *   test_sil_fault_injection     legacy loop (no TEMPER_PAN_CONTROL_C1):
 *                                every 100 ms trace row is one
 *                                state_machine_update(); sensors come from
 *                                the state_machine_stubs.c mocks.
 *   test_sil_fault_injection_c1  TEMPER_PAN_CONTROL_C1, as the ESP-IDF target
 *                                builds it: the C1 loop (pan_control.c, the
 *                                Kalman estimator, rate PID, D1 and
 *                                pan_supervisor R1/R2) and the real
 *                                MAX31865 service (rtd_service.c,
 *                                max31865.c) through the SPI mock. Each trace
 *                                row is 10 control ticks of 10 ms (main.c
 *                                control_task order: rtd_service_control_tick,
 *                                then state_machine_update). A register-level
 *                                MAX31865 model converts the trace into
 *                                RTD codes at 50 Hz with DRDY, applies the
 *                                threshold words the firmware programmed and
 *                                latches register 07h; the bus current follows
 *                                the commanded power unless the trace injects
 *                                a power-stage fault.
 *                                output/temper-sensor-r3/firmware/DECISIONS.md
 *                                D-SIL.
 *
 * Manifest fields read here (all optional except name/expected):
 *   modes                ["legacy","c1"] (default both): which targets run it
 *   origin_state         state the fault is injected from
 *   perturbation.at_tick / sensors[].over_ticks
 *   timing.advance_ms    timeout scenarios (single time jump)
 *   expected.final_state / fault_code / max_latency_ticks
 *   expected.max_latency_ticks_c1   C1 bound when it differs (the coverage
 *                        gate requires c1_later_than_legacy_reason if larger)
 *   expected.hold_state  true: the state must stay final_state from the
 *                        perturbation end to the end of the trace
 *   expected.hard_assertions  power_off, power_level_zero, eeprom_logged
 *                        (the first fault logged since reset)
 *   c1_mechanism         C1 rule expected to act; checked where the firmware
 *                        exposes it (R2-2a, R2-2b, R1, absolute-300,
 *                        rtd-07h, rtd-stale, rtd-frozen, isense-run,
 *                        isense-pulse)
 *   c1_escalates_to_runaway  true: in C1 the fault is followed by the
 *                        RUNAWAY_FAULT latch (a flagged but plausible
 *                        over-temperature: register 07h reports first, then
 *                        the 300 degC check latches; DECISIONS D-OPEN);
 *                        required, not allowed, so it is never silent
 *   expected.reset_accepted  true: the fault condition has gone by the end
 *                        of the trace (a healed sensor): a reset must be
 *                        accepted and the machine reach IDLE with the power
 *                        at 0 throughout, instead of being refused
 *   c1_bus_sense_dead    true (C1): the bus-current sense reads 0 A from
 *                        power-up, whatever the stage draws (a latent sense
 *                        failure; DECISIONS D-ISENSE)
 *   c1_idle_soak_s       C1: seconds the unit idles in IDLE, cycling the
 *                        trace's rows 0-4, between power-up and the start press (the
 *                        cold-soak check, DECISIONS D-SOAK, needs >= 30 min
 *                        of coil-off history)
 *   c1_pt100_leak_ohm    C1: a leak in parallel with the Pt100 element from
 *                        power-up, temperature-independent (D-LEAK, D-SOAK);
 *                        0 or absent: none
 *   xfail                {"c1": "reason"}: a known defect, reported as
 *                        XFAIL; an unexpected pass fails the run
 *
 * Checks applied to every scenario in both modes, in addition to the
 * manifest's: no fault before the perturbation starts; the machine is in
 * origin_state when the perturbation starts; the first latched fault stays
 * latched (no later report overwrites its code or re-enters the fault state
 * and logs again; the only allowed change is the declared RUNAWAY_FAULT
 * escalation); and a reset request with the fault condition still present is
 * refused. In C1 the state is observed after every 10 ms control tick, the
 * firmware's own cadence; legacy observes once per 100 ms row.
 *
 * Build: CMake targets test_sil_fault_injection, test_sil_fault_injection_c1
 * Run:   (working directory must contain traces/manifest.json)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
#include <ctype.h>
#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../config.h"

#ifdef TEMPER_PAN_CONTROL_C1
#include "../main/pan_control.h"
#include "../components/temper_hal/include/hal.h"
#include "../components/temper_hal/include/temper_pins.h"
#ifdef TEMPER_PAN_CONTROL_C1
#include "rim_ntc.h"
#endif
#include "../components/sensors/include/max31865.h"
#include "../components/sensors/include/rtd_service.h"
#define SIL_MODE "c1"
#else
#define SIL_MODE "legacy"
#endif

/* ---------------------------------------------------------------------------
 * Mock control functions (from state_machine_stubs.c)
 * --------------------------------------------------------------------------- */

extern void  mock_sm_reset(void);
extern void  mock_sm_advance_time(uint32_t ms);
extern void  mock_sm_set_pan_temperature(float temp_c);
extern void  mock_sm_set_heatsink_temperature(float temp_c);
extern void  mock_sm_set_dc_bus_current(float amps);
extern void  mock_sm_set_rtd_resistance(float ohms);
extern void  mock_sm_set_pan_status(int status);
extern void  mock_sm_set_fan_running(bool running);
extern void  mock_sm_set_pan_impedance(float impedance);
extern void  mock_sm_press_button(button_id_t button);
extern void  mock_sm_release_button(button_id_t button);
extern void  mock_sm_set_selftest_results(bool adc, bool pwm, bool fan,
                                          bool comp, bool rtd, bool disp,
                                          bool eeprom);
extern fault_code_t mock_sm_get_last_logged_fault(void);
extern fault_code_t mock_sm_get_first_logged_fault(void);
extern uint32_t     mock_sm_get_eeprom_log_count(void);
extern uint32_t     mock_sm_get_pwm_disable_count(void);
extern bool         mock_sm_get_pll_enabled(void);
extern uint32_t     mock_sm_get_power_level(void);
extern float        read_pan_temperature(void);   /* stub: the plant value */

#define MOCK_PAN_ABSENT  0
#define MOCK_PAN_PRESENT 1

/* ---------------------------------------------------------------------------
 * Constants
 * --------------------------------------------------------------------------- */

#define MAX_TICKS             2000  /* the D-LEAK trace needs ~1300 rows */
#define PAN_ABSENT_THRESHOLD  3.0f
#define PAN_CONFIDENCE_NEEDED 3
#define DT_MS                 100    /* 100 ms per tick (matches plant model dt) */
#define MAX_MANIFEST_ENTRIES  64
#define MAX_CSV_LINE_LEN      512
#define MANIFEST_PATH         "traces/manifest.json"
#define CSV_COLS              8

/* ---------------------------------------------------------------------------
 * JSON mini-parser (hand-rolled for the known manifest schema)
 * --------------------------------------------------------------------------- */

/* Expected state-string to enum mapping */
static system_state_t parse_state(const char *str) {
    if (!str) return STATE_INIT;
    if (!strcmp(str, "FAULT"))   return STATE_FAULT;
    if (!strcmp(str, "NO_PAN"))  return STATE_NO_PAN;
    if (!strcmp(str, "IDLE"))    return STATE_IDLE;
    if (!strcmp(str, "HEATING")) return STATE_HEATING;
    if (!strcmp(str, "PREHEAT")) return STATE_PREHEAT;
    if (!strcmp(str, "COOLDOWN")) return STATE_COOLDOWN;
    if (!strcmp(str, "PAN_DET")) return STATE_PAN_DET;
    if (!strcmp(str, "RUNAWAY_FAULT")) return STATE_RUNAWAY_FAULT;
    return STATE_INIT;
}

/* Expected fault-code-string to enum mapping */
static fault_code_t parse_fault_code(const char *str) {
    if (!str || !strcmp(str, "FAULT_NONE"))            return FAULT_NONE;
    if (!strcmp(str, "FAULT_OVER_TEMP"))               return FAULT_OVER_TEMP;
    if (!strcmp(str, "FAULT_OVER_CURRENT"))            return FAULT_OVER_CURRENT;
    if (!strcmp(str, "FAULT_RUNAWAY_BOUNDARY"))         return FAULT_RUNAWAY_BOUNDARY;
    if (!strcmp(str, "FAULT_FAN_FAILURE"))             return FAULT_FAN_FAILURE;
    if (!strcmp(str, "FAULT_PROBE_OPEN"))              return FAULT_PROBE_OPEN;
    if (!strcmp(str, "FAULT_PROBE_SHORT"))             return FAULT_PROBE_SHORT;
    if (!strcmp(str, "FAULT_IGBT_SHORT"))              return FAULT_IGBT_SHORT;
    if (!strcmp(str, "FAULT_THERMAL_RUNAWAY"))         return FAULT_THERMAL_RUNAWAY;
    if (!strcmp(str, "FAULT_ADC_STUCK"))               return FAULT_ADC_STUCK;
    if (!strcmp(str, "FAULT_COOLDOWN_OVERHEAT"))       return FAULT_COOLDOWN_OVERHEAT;
    if (!strcmp(str, "FAULT_SELF_TEST_FAILED"))        return FAULT_SELF_TEST_FAILED;
    if (!strcmp(str, "FAULT_WATCHDOG_RESET"))          return FAULT_WATCHDOG_RESET;
    if (!strcmp(str, "FAULT_PAN_DETECT_HW"))           return FAULT_PAN_DETECT_HW;
    if (!strcmp(str, "FAULT_CURRENT_SENSE"))           return FAULT_CURRENT_SENSE;
    if (!strcmp(str, "FAULT_PROBE_LEAKAGE"))           return FAULT_PROBE_LEAKAGE;
    return FAULT_NONE;
}

/* Read entire file into malloc'd string */
static char *read_file(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(sz + 1);
    if (buf) {
        size_t n = fread(buf, 1, sz, f);
        buf[n] = '\0';
    }
    fclose(f);
    return buf;
}

/* Skip whitespace */
static const char *skip_ws(const char *p) {
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    return p;
}

/* Extract a JSON string value (without quotes), advance *pp past it */
static char *extract_string(const char **pp) {
    const char *p = *pp;
    p = skip_ws(p);
    if (*p != '"') return NULL;
    p++;
    const char *start = p;
    while (*p && *p != '"') {
        if (*p == '\\') p++; /* skip escaped char */
        p++;
    }
    size_t len = p - start;
    char *val = malloc(len + 1);
    if (val) {
        memcpy(val, start, len);
        val[len] = '\0';
    }
    if (*p == '"') p++;
    *pp = p;
    return val;
}

/* Extract a JSON integer value, advance *pp past it */
static int extract_int(const char **pp) {
    const char *p = skip_ws(*pp);
    int val = (int)strtol(p, (char **)&p, 10);
    *pp = p;
    return val;
}

/* Extract a JSON number, advance *pp past it */
static double extract_number(const char **pp) {
    const char *p = skip_ws(*pp);
    double val = strtod(p, (char **)&p);
    *pp = p;
    return val;
}

/* Extract a JSON boolean, advance *pp past it (false on anything else) */
static bool extract_bool(const char **pp) {
    const char *p = skip_ws(*pp);
    if (!strncmp(p, "true", 4))  { *pp = p + 4; return true; }
    if (!strncmp(p, "false", 5)) { *pp = p + 5; return false; }
    return false;
}

/* Skip over a JSON value (string, number, object, array, bool, null) */
static void skip_value(const char **pp) {
    const char *p = skip_ws(*pp);
    if (!*p) return;

    if (*p == '"') {
        /* string */
        p++;
        while (*p && *p != '"') {
            if (*p == '\\') p++;
            p++;
        }
        if (*p == '"') p++;
    } else if (*p == '{') {
        /* object */
        int depth = 1; p++;
        while (*p && depth > 0) {
            if (*p == '{') depth++;
            else if (*p == '}') depth--;
            else if (*p == '"') { /* skip strings inside */ p++; while (*p && *p != '"') { if (*p == '\\') p++; p++; } }
            p++;
        }
    } else if (*p == '[') {
        /* array */
        int depth = 1; p++;
        while (*p && depth > 0) {
            if (*p == '[') depth++;
            else if (*p == ']') depth--;
            else if (*p == '"') { p++; while (*p && *p != '"') { if (*p == '\\') p++; p++; } }
            p++;
        }
    } else if (*p == 't' || *p == 'f' || *p == 'n') {
        /* true / false / null */
        while (*p && *p != ',' && *p != '}' && *p != ']') p++;
    } else {
        /* number */
        while (*p && (isdigit(*p) || *p == '-' || *p == '.' || *p == 'e' || *p == 'E' || *p == '+')) p++;
    }
    *pp = p;
}

/* ---------------------------------------------------------------------------
 * Manifest entry structure
 * --------------------------------------------------------------------------- */

typedef struct {
    char name[128];
    char description[256];
    char trace_file[256];
    char finding[512];        /* optional: printed prominently -- used for
                                  demonstrated-gap scenarios that are not
                                  expected to reach a safe state */
    char c1_mechanism[48];    /* C1 rule expected to act (coverage gate) */
    char xfail_reason[256];   /* non-empty: known defect in this mode */
    bool run_legacy;
    bool run_c1;
    bool self_test_pass;     /* initial_conditions */
    system_state_t origin_state; /* state the manifest defines this fault
                                     path from (INIT/IDLE/PAN_DET/PREHEAT/
                                     HEATING/COOLDOWN); defaults to HEATING */
    int  perturbation_at_tick;
    int  perturbation_over_ticks; /* computed from sensors */
    /* Timing/timeout injection (plan 031/U3): an alternative to trace-based
     * sensor perturbation for boundaries too large to replay tick-by-tick
     * (e.g. MAX_PREHEAT_TIME_MS = 600000ms, far beyond MAX_TICKS*DT_MS).
     * When set, the scenario advances time once by timing_advance_ms and
     * checks the outcome after a single state_machine_update(), instead of
     * replaying a CSV trace. */
    bool is_timing_scenario;
    long timing_advance_ms;
    system_state_t expected_state;
    fault_code_t   expected_fault;
    int  max_latency_ticks;
    int  max_latency_ticks_c1;    /* -1: same as max_latency_ticks */
    bool hold_state;
    bool reset_accepted;
    bool c1_escalates_to_runaway;
    bool c1_bus_sense_dead;
    int  c1_idle_soak_s;          /* C1: idle seconds before the start press */
    float c1_pt100_leak_ohm;      /* C1: element-parallel leak, 0 = none */
    /* hard assertions (KTD3): a scenario that reaches the right state but
     * misses these side effects fails the run, it does not warn. */
    bool require_power_off;
    bool require_power_level_zero;
    bool require_eeprom_logged;
    fault_code_t expected_eeprom_fault;
} manifest_entry_t;

/* Parse a JSON array of strings for the "modes" key. */
static void parse_modes(const char **pp, manifest_entry_t *e) {
    const char *p = skip_ws(*pp);
    if (*p != '[') { skip_value(&p); *pp = p; return; }
    e->run_legacy = false;
    e->run_c1 = false;
    p++;
    while (*p && *p != ']') {
        p = skip_ws(p);
        char *m = extract_string(&p);
        if (!m) break;
        if (!strcmp(m, "legacy")) e->run_legacy = true;
        if (!strcmp(m, "c1"))     e->run_c1 = true;
        free(m);
        p = skip_ws(p);
        if (*p == ',') p++;
    }
    if (*p == ']') p++;
    *pp = p;
}

/* Parse {"<mode>": "<reason>", ...}; keep the reason for this build's mode. */
static void parse_xfail(const char **pp, manifest_entry_t *e) {
    const char *p = skip_ws(*pp);
    if (*p != '{') { skip_value(&p); *pp = p; return; }
    p++;
    while (*p && *p != '}') {
        p = skip_ws(p);
        char *k = extract_string(&p);
        if (!k) break;
        p = skip_ws(p);
        if (*p == ':') p++;
        char *v = extract_string(&p);
        if (v) {
            if (!strcmp(k, SIL_MODE)) {
                strncpy(e->xfail_reason, v, sizeof(e->xfail_reason) - 1);
            }
            free(v);
        } else {
            skip_value(&p);
        }
        free(k);
        p = skip_ws(p);
        if (*p == ',') p++;
    }
    if (*p == '}') p++;
    *pp = p;
}

/* ---------------------------------------------------------------------------
 * Parse manifest.json into entries
 * --------------------------------------------------------------------------- */

static int parse_manifest(manifest_entry_t *entries, int max_entries) {
    char *json = read_file(MANIFEST_PATH);
    if (!json) {
        printf("WARNING: manifest.json not found at '%s' -- no SIL tests to run\n",
               MANIFEST_PATH);
        return 0;
    }

    const char *p = json;
    int count = 0;

    /* Find the opening '[' of the array */
    p = strchr(p, '[');
    if (!p) { free(json); return 0; }
    p++;

    while (count < max_entries) {
        p = skip_ws(p);
        if (*p == ']' || *p == '\0') break;

        /* Expect '{' */
        if (*p != '{') break;
        p++;

        manifest_entry_t *e = &entries[count];
        memset(e, 0, sizeof(*e));
        e->run_legacy = true;  /* default: both modes */
        e->run_c1 = true;
        e->self_test_pass = true; /* default */
        e->origin_state = STATE_HEATING; /* default: matches the legacy
                                             single-trajectory scenarios */
        e->expected_state = STATE_INIT;
        e->expected_fault = FAULT_NONE;
        e->max_latency_ticks_c1 = -1;

        while (*p && *p != '}') {
            p = skip_ws(p);
            if (*p == '}') break;

            char *key = extract_string(&p);
            if (!key) break;

            p = skip_ws(p);
            if (*p == ':') p++;

            if (!strcmp(key, "name")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->name, val, sizeof(e->name) - 1); free(val); }
            } else if (!strcmp(key, "description")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->description, val, sizeof(e->description) - 1); free(val); }
            } else if (!strcmp(key, "trace_file")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->trace_file, val, sizeof(e->trace_file) - 1); free(val); }
            } else if (!strcmp(key, "finding")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->finding, val, sizeof(e->finding) - 1); free(val); }
            } else if (!strcmp(key, "c1_mechanism")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->c1_mechanism, val, sizeof(e->c1_mechanism) - 1); free(val); }
            } else if (!strcmp(key, "c1_escalates_to_runaway")) {
                e->c1_escalates_to_runaway = extract_bool(&p);
            } else if (!strcmp(key, "c1_bus_sense_dead")) {
                e->c1_bus_sense_dead = extract_bool(&p);
            } else if (!strcmp(key, "c1_idle_soak_s")) {
                e->c1_idle_soak_s = extract_int(&p);
            } else if (!strcmp(key, "c1_pt100_leak_ohm")) {
                e->c1_pt100_leak_ohm = (float)extract_number(&p);
            } else if (!strcmp(key, "modes")) {
                parse_modes(&p, e);
            } else if (!strcmp(key, "xfail")) {
                parse_xfail(&p, e);
            } else if (!strcmp(key, "origin_state")) {
                char *val = extract_string(&p);
                if (val) { e->origin_state = parse_state(val); free(val); }
            } else if (!strcmp(key, "initial_conditions")) {
                /* Parse the initial_conditions object */
                p = skip_ws(p);
                if (*p == '{') {
                    p++;
                    while (*p && *p != '}') {
                        p = skip_ws(p);
                        char *ik = extract_string(&p);
                        if (!ik) break;
                        p = skip_ws(p);
                        if (*p == ':') p++;
                        if (!strcmp(ik, "self_test_pass")) {
                            e->self_test_pass = extract_bool(&p);
                        } else {
                            skip_value(&p);
                        }
                        free(ik);
                        p = skip_ws(p);
                        if (*p == ',') p++;
                    }
                    if (*p == '}') p++;
                }
            } else if (!strcmp(key, "timing")) {
                p = skip_ws(p);
                if (*p == '{') {
                    p++;
                    e->is_timing_scenario = true;
                    while (*p && *p != '}') {
                        p = skip_ws(p);
                        char *tk = extract_string(&p);
                        if (!tk) break;
                        p = skip_ws(p);
                        if (*p == ':') p++;
                        if (!strcmp(tk, "advance_ms")) {
                            e->timing_advance_ms = (long)extract_int(&p);
                        } else {
                            skip_value(&p);
                        }
                        free(tk);
                        p = skip_ws(p);
                        if (*p == ',') p++;
                    }
                    if (*p == '}') p++;
                }
            } else if (!strcmp(key, "perturbation")) {
                p = skip_ws(p);
                if (*p == '{') {
                    p++;
                    while (*p && *p != '}') {
                        p = skip_ws(p);
                        char *pk = extract_string(&p);
                        if (!pk) break;
                        p = skip_ws(p);
                        if (*p == ':') p++;
                        if (!strcmp(pk, "at_tick")) {
                            e->perturbation_at_tick = extract_int(&p);
                        } else if (!strcmp(pk, "sensors")) {
                            /* Array of sensors: find max over_ticks */
                            p = skip_ws(p);
                            if (*p == '[') {
                                p++;
                                int max_over = 0;
                                while (*p && *p != ']') {
                                    p = skip_ws(p);
                                    if (*p == '{') {
                                        p++;
                                        int over = 0;
                                        while (*p && *p != '}') {
                                            p = skip_ws(p);
                                            char *sk = extract_string(&p);
                                            if (!sk) break;
                                            p = skip_ws(p);
                                            if (*p == ':') p++;
                                            if (!strcmp(sk, "over_ticks")) {
                                                over = extract_int(&p);
                                            } else {
                                                skip_value(&p);
                                            }
                                            free(sk);
                                            p = skip_ws(p);
                                            if (*p == ',') p++;
                                        }
                                        if (*p == '}') p++;
                                        if (over > max_over) max_over = over;
                                    }
                                    p = skip_ws(p);
                                    if (*p == ',') p++;
                                }
                                if (*p == ']') p++;
                                e->perturbation_over_ticks = max_over;
                            }
                        } else {
                            skip_value(&p);
                        }
                        free(pk);
                        p = skip_ws(p);
                        if (*p == ',') p++;
                    }
                    if (*p == '}') p++;
                }
            } else if (!strcmp(key, "expected")) {
                p = skip_ws(p);
                if (*p == '{') {
                    p++;
                    while (*p && *p != '}') {
                        p = skip_ws(p);
                        char *ek = extract_string(&p);
                        if (!ek) break;
                        p = skip_ws(p);
                        if (*p == ':') p++;
                        if (!strcmp(ek, "final_state")) {
                            char *val = extract_string(&p);
                            e->expected_state = parse_state(val);
                            free(val);
                        } else if (!strcmp(ek, "fault_code")) {
                            char *val = extract_string(&p);
                            e->expected_fault = parse_fault_code(val);
                            free(val);
                        } else if (!strcmp(ek, "max_latency_ticks")) {
                            e->max_latency_ticks = extract_int(&p);
                        } else if (!strcmp(ek, "max_latency_ticks_c1")) {
                            e->max_latency_ticks_c1 = extract_int(&p);
                        } else if (!strcmp(ek, "hold_state")) {
                            e->hold_state = extract_bool(&p);
                        } else if (!strcmp(ek, "reset_accepted")) {
                            e->reset_accepted = extract_bool(&p);
                        } else if (!strcmp(ek, "hard_assertions")) {
                            /* Array of hard assertion objects (KTD3):
                             * power_off, power_level_zero and eeprom_logged
                             * fail the run when unmet, they do not warn. */
                            p = skip_ws(p);
                            if (*p == '[') {
                                p++;
                                while (*p && *p != ']') {
                                    p = skip_ws(p);
                                    if (*p == '{') {
                                        p++;
                                        while (*p && *p != '}') {
                                            p = skip_ws(p);
                                            char *sak = extract_string(&p);
                                            if (!sak) break;
                                            p = skip_ws(p);
                                            if (*p == ':') p++;
                                            p = skip_ws(p);
                                            if (!strcmp(sak, "power_off")) {
                                                e->require_power_off = extract_bool(&p);
                                            } else if (!strcmp(sak, "power_level_zero")) {
                                                e->require_power_level_zero = extract_bool(&p);
                                            } else if (*p == '"') {
                                                char *sv = extract_string(&p);
                                                if (sv) {
                                                    if (!strcmp(sak, "eeprom_logged")) {
                                                        e->require_eeprom_logged = true;
                                                        e->expected_eeprom_fault = parse_fault_code(sv);
                                                    }
                                                    free(sv);
                                                }
                                            } else {
                                                skip_value(&p);
                                            }
                                            free(sak);
                                            p = skip_ws(p);
                                            if (*p == ',') p++;
                                        }
                                        if (*p == '}') p++;
                                    }
                                    p = skip_ws(p);
                                    if (*p == ',') p++;
                                }
                                if (*p == ']') p++;
                            }
                        } else {
                            skip_value(&p);
                        }
                        free(ek);
                        p = skip_ws(p);
                        if (*p == ',') p++;
                    }
                    if (*p == '}') p++;
                }
            } else {
                skip_value(&p);
            }
            free(key);
            p = skip_ws(p);
            if (*p == ',') p++;
        }
        if (*p == '}') p++;
        /* Skip comma separator between array elements */
        p = skip_ws(p);
        if (*p == ',') p++;
        count++;
    }

    free(json);
    return count;
}

/* ---------------------------------------------------------------------------
 * CSV parsing
 * --------------------------------------------------------------------------- */

typedef float csvrow_t[CSV_COLS]; /* 0=tick, 1=hs_temp, 2=pan_temp, 3=dc_cur,
                                     4=rtd, 5=pan_imp, 6=fan_run,
                                     7=rtd_drdy (C1 only; default 1) */

static int load_csv(const char *path, csvrow_t *rows, int max_rows) {
    FILE *f = fopen(path, "r");
    if (!f) {
        printf("ERROR: cannot open trace file: %s\n", path);
        return 0;
    }

    char line[MAX_CSV_LINE_LEN];
    /* Skip header */
    if (!fgets(line, sizeof(line), f)) { fclose(f); return 0; }

    int count = 0;
    while (count < max_rows && fgets(line, sizeof(line), f)) {
        /* Remove trailing newline */
        size_t len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) {
            line[--len] = '\0';
        }

        int parsed = sscanf(line,
            "%f,%f,%f,%f,%f,%f,%f,%f",
            &rows[count][0], &rows[count][1], &rows[count][2],
            &rows[count][3], &rows[count][4], &rows[count][5],
            &rows[count][6], &rows[count][7]);

        if (parsed >= 6) {
            if (parsed < 7) rows[count][6] = rows[count][3] > 0.1f ? 1.0f : 0.0f;
            if (parsed < 8) rows[count][7] = 1.0f;
            count++;
        }
    }
    fclose(f);
    return count;
}

/* ---------------------------------------------------------------------------
 * Plant / converter model.
 *
 * Legacy: the trace values are the state machine's sensor reads (stubs).
 *
 * C1: the state machine reads the pan temperature and the Pt100 resistance
 * from the latest MAX31865 conversion, and the supervisor compares the bus
 * current with the commanded power. The model below sits behind the SPI and
 * GPIO mocks and behaves like the converter and the power stage:
 *
 *   MAX31865   the power-up automatic fault cycle completes on the first
 *              control tick; then, while CONFIG has VBIAS and auto-convert
 *              set and the trace's rtd_drdy column is 1, a conversion every
 *              2nd 10 ms tick (50 Hz): code = R / 430 ohm * 2^15 (clamped),
 *              compared with the threshold words the firmware programmed;
 *              a crossing latches register 07h bit 7/6 and sets the fault
 *              bit (RTD LSB D0); DRDY falls. CONFIG D1 clears 07h.
 *   R          the Pt100 at the trace pan temperature plus the CR-7 0.061 K
 *              self-heating (IEC 60751), in parallel with the manifest's
 *              c1_pt100_leak_ohm if set, unless the trace's rtd_resistance
 *              column departs from its row-0 placeholder: then that value
 *              is the element's resistance (an injected RTD fault).
 *   heatsink   the heatsink NTC driver VALID at the trace's hs_temp
 *              (state_machine_stubs.c read_heatsink_ntc).
 *   bus I      an obeying stage, P_cmd / 120 V (from the last power level;
 *              the supervisor allows down to 100 V), and 0 A with no pan
 *              (no coupling, so no real power), unless the trace's
 *              dc_current column departs from its row-0 placeholder: then
 *              that value (an injected power-stage or sense fault). A
 *              scenario with c1_bus_sense_dead reads 0 A throughout.
 *   rim NTC    the trace pan temperature (no cross-check suspicion).
 *
 * The legacy traces hold dc_current 5.0 A and rtd_resistance 100.0 ohm as
 * fixed placeholders whatever the pan does (100 ohm is a 0 degC Pt100 while
 * the pan reads 92 degC). Replayed verbatim into C1 they would be faults in
 * their own right: 5 A against a near-zero command is stage-2a evidence of a
 * disobeying power stage. DECISIONS.md D-SIL.
 * --------------------------------------------------------------------------- */

#ifdef TEMPER_PAN_CONTROL_C1
extern void mock_spi_reset(void);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg, uint8_t value);
extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_gpio_reset(void);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);
extern int mock_sm_get_pan_status(void);

#define C1_DEV            ((hal_spi_device_t)0)
#define C1_TICK_MS        10u
#define C1_TICKS_PER_ROW  (DT_MS / C1_TICK_MS)
#define C1_R_REF_OHM      430.0
#define C1_SELF_HEATING_K 0.061
#define C1_STAGE_V        120.0f

static struct {
    float r_override;     /* NAN: Pt100 follows the pan temperature */
    float i_override;     /* NAN: bus current follows the command   */
    bool sense_dead;      /* the bus-current sense reads 0 A        */
    float leak_ohm;       /* element-parallel leak, 0 = none        */
    bool drdy;
    uint32_t tick;
    uint32_t conversions;
} s_plant;

/* Rim NTC board HAL for pan_control.c's rim driver: the 104GT-2 node voltage
 * at the trace pan temperature under the 1.00 k pull-up and a 3300 mV rail,
 * clipped as the ADC clips and rounded to whole mV, as test_c1_runtime.c does.
 * The rim reads the pan, so the cross-check is never suspicious (D-SIL, D-RIM). */
static bool sil_rim_read_node(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    const float r = rim_ntc_c_to_r(read_pan_temperature());
    const float v = 3300.0f * r / (r + 1000.0f);
    const float clip = atten == RIM_ATTEN_0 ? 950.0f : (atten == RIM_ATTEN_2 ? 1700.0f : 3100.0f);
    *mv = roundf(v < clip ? v : clip);
    return true;
}

static bool sil_rim_read_rail(void *ctx, float *mv)
{
    (void)ctx;
    *mv = 3300.0f;
    return true;
}

static const rim_ntc_hal_t s_sil_rim_hal = {.read_node_mv = sil_rim_read_node, .read_v3v3_mv = sil_rim_read_rail, .ctx = NULL};
const rim_ntc_hal_t *rim_ntc_board_hal(void) { return &s_sil_rim_hal; }

static double pt100_ohm(double t_c) {
    const double a = 3.9083e-3, b = -5.775e-7, c = -4.183e-12;
    double r = 1.0 + a * t_c + b * t_c * t_c;
    if (t_c < 0.0) r += c * (t_c - 100.0) * t_c * t_c * t_c;
    return 100.0 * r;
}

static uint16_t reg_word(uint8_t msb_reg) {
    return (uint16_t)(((uint16_t)mock_spi_get_register(C1_DEV, msb_reg) << 8) |
                      mock_spi_get_register(C1_DEV, (uint8_t)(msb_reg + 1u)));
}

static uint8_t threshold_bits(uint16_t code) {
    const uint16_t hi = (uint16_t)(reg_word(MAX31865_REG_HIGH_THRESHOLD_MSB) >> 1);
    const uint16_t lo = (uint16_t)(reg_word(MAX31865_REG_LOW_THRESHOLD_MSB) >> 1);
    uint8_t bits = 0u;
    if (code > hi) bits |= MAX31865_FAULT_HIGH_THRESHOLD;
    if (code < lo) bits |= MAX31865_FAULT_LOW_THRESHOLD;
    return bits;
}

static uint16_t element_code(void) {
    double r = isnan(s_plant.r_override)
        ? pt100_ohm((double)read_pan_temperature() + C1_SELF_HEATING_K)
        : (double)s_plant.r_override;
    if (isnan(s_plant.r_override) && s_plant.leak_ohm > 0.0f) {
        r = r * (double)s_plant.leak_ohm / (r + (double)s_plant.leak_ohm);
    }
    long code = lround(r / C1_R_REF_OHM * 32768.0);
    if (code < 0) code = 0;
    if (code > 0x7FFF) code = 0x7FFF;
    return (uint16_t)code;
}

static void c1_converter_step(void) {
    uint8_t cfg = mock_spi_get_register(C1_DEV, MAX31865_REG_CONFIG);
    uint8_t status = mock_spi_get_register(C1_DEV, MAX31865_REG_FAULT_STATUS);
    if (cfg & MAX31865_CONFIG_FAULT_CLEAR) {
        status = 0u;
        cfg = (uint8_t)(cfg & (uint8_t)~MAX31865_CONFIG_FAULT_CLEAR);
        mock_spi_set_register(C1_DEV, MAX31865_REG_CONFIG, cfg);
    }
    if (cfg & MAX31865_CONFIG_FAULT_CYCLE_MASK) {
        /* power-up automatic fault-detection cycle: done within one tick */
        status |= threshold_bits(element_code());
        mock_spi_set_register(C1_DEV, MAX31865_REG_FAULT_STATUS, status);
        mock_spi_set_register(C1_DEV, MAX31865_REG_CONFIG,
                              (uint8_t)(cfg & (uint8_t)~MAX31865_CONFIG_FAULT_CYCLE_MASK));
        return;
    }
    const bool converting = (cfg & MAX31865_CONFIG_VBIAS) && (cfg & MAX31865_CONFIG_AUTO_CONVERT);
    if (!converting || !s_plant.drdy || (s_plant.tick % 2u) != 0u) {
        return;
    }
    const uint16_t code = element_code();
    status |= threshold_bits(code);
    const uint16_t word = (uint16_t)((code << 1) | (status != 0u ? 1u : 0u));
    mock_spi_set_register(C1_DEV, MAX31865_REG_RTD_MSB, (uint8_t)(word >> 8));
    mock_spi_set_register(C1_DEV, (uint8_t)(MAX31865_REG_RTD_MSB + 1u), (uint8_t)word);
    mock_spi_set_register(C1_DEV, MAX31865_REG_FAULT_STATUS, status);
    s_plant.conversions++;
    mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
}

static void c1_control_tick(void) {
    mock_sm_advance_time(C1_TICK_MS);
    s_plant.tick++;
    const bool coupled = mock_sm_get_pan_status() == MOCK_PAN_PRESENT;
    float i_bus = isnan(s_plant.i_override)
        ? (coupled ? (float)mock_sm_get_power_level() / 100.0f * PAN_CONTROL_P_MAX_W / C1_STAGE_V : 0.0f)
        : s_plant.i_override;
    if (s_plant.sense_dead) {
        i_bus = 0.0f;
    }
    mock_sm_set_dc_bus_current(i_bus);
    c1_converter_step();
    rtd_service_control_tick();   /* main.c control_task order */
    state_machine_update();
}

/* Power-up: HAL, MAX31865 bootstrap (main.c init_peripherals), then the
 * state machine. pan_control.c keeps its supervisor in statics; a fresh
 * process starts with R1 empty, so the runner clears R1 between scenarios. */
static void c1_reset(void) {
    (void)hal_deinit();
    mock_spi_reset();
    mock_gpio_reset();
    (void)hal_init_mock();
    s_plant.r_override = NAN;
    s_plant.i_override = NAN;
    s_plant.sense_dead = false;
    s_plant.leak_ohm = 0.0f;
    s_plant.drdy = true;
    s_plant.tick = 0u;
    s_plant.conversions = 0u;
    TEST_ASSERT_EQUAL(HAL_OK, rtd_service_bootstrap());
    pan_control_rate_reset();
}
#endif /* TEMPER_PAN_CONTROL_C1 */

/* Control steps per 100 ms trace row, and one control step: the state is
 * observed after each step. */
#ifdef TEMPER_PAN_CONTROL_C1
#define SIL_STEPS_PER_ROW ((int)C1_TICKS_PER_ROW)
static void sil_control_step(void) { c1_control_tick(); }
#else
#define SIL_STEPS_PER_ROW 1
static void sil_control_step(void) {
    mock_sm_advance_time(DT_MS);
    state_machine_update();
}
#endif

/* One 100 ms trace row of control time. */
static void sil_step_row(void) {
    for (int k = 0; k < SIL_STEPS_PER_ROW; k++) {
        sil_control_step();
    }
}

static void sil_reset(const manifest_entry_t *entry) {
    mock_sm_reset();
#ifdef TEMPER_PAN_CONTROL_C1
    c1_reset();
    s_plant.sense_dead = entry->c1_bus_sense_dead;
    s_plant.leak_ohm = entry->c1_pt100_leak_ohm;
#else
    (void)entry;
#endif
    state_machine_init();
}

/* Apply one trace row to the plant. rows[0] holds the placeholders. */
static void apply_row(const csvrow_t *rows, int t) {
    mock_sm_set_heatsink_temperature(rows[t][1]);
    mock_sm_set_pan_temperature(rows[t][2]);
    mock_sm_set_dc_bus_current(rows[t][3]);
    mock_sm_set_rtd_resistance(rows[t][4]);
#ifdef TEMPER_PAN_CONTROL_C1
    s_plant.i_override = (rows[t][3] != rows[0][3]) ? rows[t][3] : NAN;
    s_plant.r_override = (rows[t][4] != rows[0][4]) ? rows[t][4] : NAN;
    s_plant.drdy = rows[t][7] > 0.5f;
#endif

    /* Derive pan status from pan_impedance */
    if (rows[t][5] < PAN_ABSENT_THRESHOLD) {
        mock_sm_set_pan_status(MOCK_PAN_ABSENT);
    } else {
        mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    }
    mock_sm_set_pan_impedance(rows[t][5]);

    /* Derive fan running: fan_running column takes priority */
    mock_sm_set_fan_running(rows[t][6] > 0.5f);
}

/* ---------------------------------------------------------------------------
 * Scenario failure reporting. A scenario records its first failure here
 * instead of calling Unity directly, so a manifest-declared expected failure
 * (xfail) can be reported as such.
 * --------------------------------------------------------------------------- */

static char g_fail[512];

static bool sil_fail(const char *msg) {
    if (g_fail[0] == '\0') {
        strncpy(g_fail, msg, sizeof(g_fail) - 1);
    }
    return false;
}

/* ---------------------------------------------------------------------------
 * State machine boilerplate: advance from INIT to a chosen origin state
 *
 * Generalized (plan 031/U1) from the single HEATING-only helper so scenarios
 * can inject from every state the manifest defines a fault path from, not
 * only the end of one trajectory. Each stage returns as soon as the
 * requested origin is reached; falling off the end lands in HEATING, same
 * as the original helper.
 * --------------------------------------------------------------------------- */

/* C1 cold-soak scenarios: idle seconds in IDLE before the start press, at
 * the trace's row 0 (set by run_sil_scenario; 0 for every other caller). */
static int g_idle_soak_s;
static const csvrow_t *g_idle_rows;
static void apply_row(const csvrow_t *rows, int t);

static void sm_boilerplate_to_origin(system_state_t origin, bool self_test_pass,
                                     float trace_start_temp_c) {
    /* INIT -> IDLE (self-test runs on first update) */
    if (!self_test_pass) {
        mock_sm_set_selftest_results(false, true, true, true, true, true, true);
    }
#ifdef TEMPER_PAN_CONTROL_C1
    /* C1: the pan sits at the trace's starting temperature from power-up, so
     * the loop and R1 see one continuous reading. (Legacy jumps the mock
     * from 25 to 92 degC and resets the rate baseline; the C1 runner never
     * calls the reset hooks, which would blind R1.) */
    if (!isnan(trace_start_temp_c)) {
        mock_sm_set_pan_temperature(trace_start_temp_c);
    }
#else
    (void)trace_start_temp_c;
#endif
    sil_step_row();

    /* Self-test failure short-circuits every origin: already in FAULT. */
    if (state_machine_get_state() == STATE_FAULT) return;
    if (origin == STATE_INIT || origin == STATE_IDLE) return;

#ifdef TEMPER_PAN_CONTROL_C1
    /* Idle soak (D-SOAK): the unit sits in IDLE, cycling the trace's first
     * 5 rows (the live-sensor pattern: a converter returning one code for
     * 250 conversions is a frozen converter, D-OPEN). */
    if (g_idle_soak_s > 0 && g_idle_rows != NULL) {
        for (int i = 0; i < g_idle_soak_s * 10 && state_machine_get_state() == STATE_IDLE; i++) {
            apply_row(g_idle_rows, i % 5);
            sil_step_row();
        }
        if (state_machine_get_state() != STATE_IDLE) return;
    }
#endif

    /* IDLE -> PAN_DET */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    sil_step_row();
    mock_sm_release_button(BUTTON_START);
    if (origin == STATE_PAN_DET) return;

    /* PAN_DET -> PREHEAT (need pan present + confidence) */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < PAN_CONFIDENCE_NEEDED; i++) {
        sil_step_row();
        if (state_machine_get_state() != STATE_PAN_DET) break;
    }
    if (state_machine_get_state() != STATE_PREHEAT) return; /* didn't arrive; nothing more to do */
    if (origin == STATE_PREHEAT) return;

    /* PREHEAT -> HEATING (pan near target: temp_error <= 10 degrees) */
#ifdef TEMPER_PAN_CONTROL_C1
    /* C1 hands over on the estimate at T_hat >= target - 10 K; the reading
     * is already the trace's starting temperature. */
    for (int i = 0; i < 20 && state_machine_get_state() == STATE_PREHEAT; i++) {
        sil_step_row();
    }
#else
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(DT_MS);
    state_machine_update();
#endif
    /* origin == STATE_HEATING (or unrecognized) falls through here.
     * COOLDOWN-origin scenarios reach COOLDOWN via the replayed trace itself
     * (pan removal -> NO_PAN -> timeout -> COOLDOWN), not via boilerplate;
     * see trace_fault_cooldown_overheat.csv / trace_fault_relay_welded.csv. */
}

/* ---------------------------------------------------------------------------
 * Trace invariant checker — validates CSV traces against safety thresholds
 * before replay.  Each check is a base case; composing all checks is the
 * induction step that guarantees the trace won't trigger a spurious fault
 * during the boilerplate-to-perturbation window.
 *
 * The rate and RTD base cases are per mode: the legacy loop latches a 15 K/s
 * rise between two reads and checks the RTD against the legacy window; C1
 * latches only a sustained rise (R1: 1 s block means rising > 15 K/s for 5
 * blocks), checks the Pt100 against the C1 window (84.27 / 233.21 ohm), and
 * treats 250 identical conversions (50 rows) as a frozen converter.
 * --------------------------------------------------------------------------- */

/* Safety thresholds.  RTD boundaries deliberately use generated config.h
 * rather than local copies so the trace precondition matches the firmware's
 * staged MAX31865 guard window. */
#define INV_MAX_ABSOLUTE_TEMP_C    300.0f
#define INV_MAX_TEMP_RISE_RATE     15.0f   /* C/s */
#define INV_MAX_DC_CURRENT_40A     40.0f
#define INV_MAX_DC_CURRENT_50A     50.0f
#define INV_MAX_HEATSINK_TEMP      80.0f
#define INV_DT_MS                  100     /* DT_MS from SIL test */
#define INV_R1_BLOCK_ROWS          10      /* 1 s blocks */
#define INV_R1_BLOCKS              5
#define INV_FROZEN_ROWS            50      /* 250 conversions at 5 per row */

static int check_trace_invariants(const csvrow_t *rows, int row_count,
                                   const manifest_entry_t *entry) {
    int violations = 0;
    const int n = row_count < entry->perturbation_at_tick ? row_count : entry->perturbation_at_tick;

    for (int t = 0; t < n; t++) {
        float pan  = rows[t][2];
        float hs   = rows[t][1];
        float curr = rows[t][3];
        float rtd  = rows[t][4];
        bool  fan  = (rows[t][6] > 0.5f);

        /* Base case 1: absolute temperature */
        if (pan > INV_MAX_ABSOLUTE_TEMP_C) {
            printf("  [INV] tick %d: pan_temp %.1f > %.1f (abs)\n",
                   t, pan, INV_MAX_ABSOLUTE_TEMP_C);
            violations++;
        }

#ifndef TEMPER_PAN_CONTROL_C1
        /* Base case 2: rate-of-rise (skip t==0 — no prior reading) */
        if (t > 0) {
            float prev = rows[t-1][2];
            float dt_s = INV_DT_MS / 1000.0f;
            float rate = (pan - prev) / dt_s;
            if (rate > INV_MAX_TEMP_RISE_RATE) {
                printf("  [INV] tick %d: rate %.1f C/s > %.1f (%.1f->%.1f over %d ms)\n",
                       t, rate, INV_MAX_TEMP_RISE_RATE, prev, pan, INV_DT_MS);
                violations++;
            }
        }
#endif

        /* Base case 3: over-current (>50A = IGBT short, >40A = over-current) */
        if (curr > INV_MAX_DC_CURRENT_50A) {
            printf("  [INV] tick %d: current %.1f > %.1f (IGBT short)\n",
                   t, curr, INV_MAX_DC_CURRENT_50A);
            violations++;
        }
        if (curr > INV_MAX_DC_CURRENT_40A) {
            printf("  [INV] tick %d: current %.1f > %.1f (over-current)\n",
                   t, curr, INV_MAX_DC_CURRENT_40A);
            violations++;
        }

        /* Base case 4: heatsink over-temp */
        if (hs > INV_MAX_HEATSINK_TEMP) {
            printf("  [INV] tick %d: hs_temp %.1f > %.1f\n",
                   t, hs, INV_MAX_HEATSINK_TEMP);
            violations++;
        }

#ifdef TEMPER_PAN_CONTROL_C1
        /* Base case 5 (C1): no injected RTD, current or DRDY fault, and the
         * Pt100 at the pan temperature inside the C1 window. */
        if (rtd != rows[0][4]) {
            printf("  [INV] tick %d: rtd %.1f departs from placeholder %.1f (injected RTD fault)\n",
                   t, rtd, rows[0][4]);
            violations++;
        }
        if (curr != rows[0][3]) {
            printf("  [INV] tick %d: current %.1f departs from placeholder %.1f (injected stage fault)\n",
                   t, curr, rows[0][3]);
            violations++;
        }
        if (rows[t][7] < 0.5f) {
            printf("  [INV] tick %d: no DRDY\n", t);
            violations++;
        }
        {
            const double r = pt100_ohm((double)pan + C1_SELF_HEATING_K);
            if (r >= RTD_C1_OPEN_FAULT_OHM || r <= RTD_C1_SHORT_FAULT_OHM) {
                printf("  [INV] tick %d: Pt100 %.2f ohm at %.1f C outside the C1 window\n",
                       t, r, pan);
                violations++;
            }
        }
#else
        /* Base case 5: staged RTD policy.  The MAX31865 guard window is the
         * safety boundary; the larger legacy diagnostic remains represented
         * explicitly so fixtures cannot silently lose that condition. */
        if (rtd > RTD_GROSS_OPEN_DIAGNOSTIC_OHM) {
            printf("  [INV] tick %d: rtd %.1f > %.1f (legacy gross-open)\n",
                   t, rtd, RTD_GROSS_OPEN_DIAGNOSTIC_OHM);
            violations++;
        } else if (rtd >= RTD_OPEN_FAULT_OHM) {
            printf("  [INV] tick %d: rtd %.1f >= %.1f (MAX31865 open guard)\n",
                   t, rtd, RTD_OPEN_FAULT_OHM);
            violations++;
        }
        if (rtd <= RTD_SHORT_FAULT_OHM) {
            printf("  [INV] tick %d: rtd %.1f <= %.1f (MAX31865 short guard)\n",
                   t, rtd, RTD_SHORT_FAULT_OHM);
            violations++;
        }
#endif

        /* Base case 6: fan failure */
        if (!fan) {
            printf("  [INV] tick %d: fan not running\n", t);
            violations++;
        }
    }

#ifdef TEMPER_PAN_CONTROL_C1
    /* Base case 2 (C1, R1): sustained rise over 1 s block means. */
    {
        int rising = 0;
        float prev_mean = NAN;
        for (int b = 0; (b + 1) * INV_R1_BLOCK_ROWS <= n; b++) {
            float sum = 0.0f;
            for (int t = b * INV_R1_BLOCK_ROWS; t < (b + 1) * INV_R1_BLOCK_ROWS; t++) sum += rows[t][2];
            const float mean = sum / INV_R1_BLOCK_ROWS;
            if (!isnan(prev_mean)) {
                rising = (mean - prev_mean > INV_MAX_TEMP_RISE_RATE) ? rising + 1 : 0;
                if (rising >= INV_R1_BLOCKS) {
                    printf("  [INV] block %d: %d blocks rising > %.1f K/s (R1)\n",
                           b, rising, INV_MAX_TEMP_RISE_RATE);
                    violations++;
                }
            }
            prev_mean = mean;
        }
    }
    /* Base case 7 (C1): a value held for 50 rows is a frozen converter. */
    {
        int run = 1;
        for (int t = 1; t < n; t++) {
            run = (rows[t][2] == rows[t - 1][2]) ? run + 1 : 1;
            if (run == INV_FROZEN_ROWS) {
                printf("  [INV] tick %d: pan_temp held for %d rows (frozen code)\n", t, run);
                violations++;
            }
        }
    }
#endif

    if (violations > 0) {
        printf("  [INV] %s: %d pre-perturbation violations found "
               "(trace may need regeneration)\n",
               entry->trace_file, violations);
    }
    return violations;
}

/* ---------------------------------------------------------------------------
 * Hard safe-state assertions (plan 031/U2, KTD3)
 *
 * Promoted from warnings-only: a scenario that reaches the right (state,
 * fault) pair but misses the power-off or fault-logging side effect now
 * fails the run instead of printing [WARN]. Uses the probe API named by
 * KTD3 rather than mock_sm_get_trigger_shutdown_count(), because not every
 * designed fault path routes through the hardware-latch shortcut (e.g.
 * FAULT_SELF_TEST_FAILED fires before the power stage is ever enabled) --
 * pwm_disable_count / power_level / pll_enabled are asserted by
 * state_fault_entry()/state_runaway_fault_entry() on every route.
 * --------------------------------------------------------------------------- */

static bool assert_safe_state_side_effects(const manifest_entry_t *entry,
                                           uint32_t pwm_disable_baseline) {
    char msg[224];

    if (entry->require_power_off) {
        uint32_t pwm_calls = mock_sm_get_pwm_disable_count();
        uint32_t power_level = mock_sm_get_power_level();
        bool pll_enabled = mock_sm_get_pll_enabled();

        if (pwm_calls <= pwm_disable_baseline) {
            snprintf(msg, sizeof(msg),
                     "HARD ASSERTION FAILED: power_off expected but "
                     "pwm_disable_all() was never called (count=%u, "
                     "baseline=%u)", pwm_calls, pwm_disable_baseline);
            return sil_fail(msg);
        }
        if (power_level != 0) {
            snprintf(msg, sizeof(msg),
                     "HARD ASSERTION FAILED: power_off expected but "
                     "power_level=%u (expected 0)", power_level);
            return sil_fail(msg);
        }
        if (pll_enabled) {
            return sil_fail("HARD ASSERTION FAILED: power_off expected but PLL is "
                            "still enabled");
        }
    }

    if (entry->require_power_level_zero && mock_sm_get_power_level() != 0u) {
        snprintf(msg, sizeof(msg),
                 "HARD ASSERTION FAILED: power_level_zero expected but "
                 "power_level=%u", mock_sm_get_power_level());
        return sil_fail(msg);
    }

    if (entry->require_eeprom_logged) {
        /* The first fault logged since reset is the expected one. (The
         * premature-fault check guarantees nothing was logged before the
         * perturbation; a later escalation is checked by
         * assert_first_fault_latched.) */
        fault_code_t logged = mock_sm_get_first_logged_fault();
        if (mock_sm_get_eeprom_log_count() == 0u || logged != entry->expected_eeprom_fault) {
            snprintf(msg, sizeof(msg),
                     "HARD ASSERTION FAILED: eeprom_logged expected fault "
                     "%d, got %d (%u entries)", (int)entry->expected_eeprom_fault,
                     (int)logged, mock_sm_get_eeprom_log_count());
            return sil_fail(msg);
        }
    }
    return true;
}

/* The first latched fault stays latched: no later report overwrites the
 * fault code or re-enters the fault state (each entry logs to EEPROM). The
 * one allowed change is the RUNAWAY_FAULT escalation that the manifest
 * declares for C1 (c1_escalates_to_runaway): then exactly two entries, the
 * declared fault first (eeprom_logged) and FAULT_RUNAWAY_BOUNDARY. */
static bool assert_first_fault_latched(const manifest_entry_t *entry,
                                       system_state_t expected_state,
                                       fault_code_t captured, bool escalate) {
    char msg[256];
    if (captured == FAULT_NONE) {
        return true;
    }
    const system_state_t st = state_machine_get_state();
    const fault_code_t fc = state_machine_get_fault();
    const uint32_t logs = mock_sm_get_eeprom_log_count();
    const uint32_t want_logs = escalate ? 2u : 1u;
    if (st != expected_state || fc != captured || logs != want_logs) {
        snprintf(msg, sizeof(msg),
                 "LATCH FAILED: first fault %d (state %d) not kept: state %d fault %d at "
                 "the end, %u EEPROM entries (expected %u)",
                 (int)captured, (int)expected_state, (int)st, (int)fc, logs, want_logs);
        return sil_fail(msg);
    }
    if (escalate) {
        printf("  [PASS] %s logged first, then the RUNAWAY_FAULT latch\n",
               state_machine_get_fault_string(entry->expected_fault));
    }
    return true;
}

/* A latched fault whose condition is still present at the end of the
 * scenario must refuse a reset request (fault_cleared(); both modes). The
 * plant keeps the last trace row's values. */
static bool assert_reset_refused(const manifest_entry_t *entry) {
    const system_state_t st = state_machine_get_state();
    if (entry->expected_fault == FAULT_NONE ||
        (st != STATE_FAULT && st != STATE_RUNAWAY_FAULT)) {
        return true;
    }
    mock_sm_press_button(BUTTON_RESET);
    sil_step_row();
    mock_sm_release_button(BUTTON_RESET);
    const system_state_t after = state_machine_get_state();
    if (after != st) {
        char msg[200];
        snprintf(msg, sizeof(msg),
                 "SAFE-OFF FAILED: reset accepted with the fault condition "
                 "present (fault %d, state %d -> %d)",
                 (int)entry->expected_fault, (int)st, (int)after);
        return sil_fail(msg);
    }
    printf("  [PASS] reset refused while the fault persists\n");
    return true;
}

/* The fault condition has gone (a healed sensor): a reset must be accepted
 * and the machine reach IDLE through INIT, with the power at 0 at every
 * control step from the press to the end (the coil stays off throughout). */
static bool assert_reset_accepted(const manifest_entry_t *entry) {
    char msg[200];
    const system_state_t st = state_machine_get_state();
    if (st != STATE_FAULT) {
        snprintf(msg, sizeof(msg), "reset_accepted: expected FAULT before the reset, state %d",
                 (int)st);
        return sil_fail(msg);
    }
    mock_sm_press_button(BUTTON_RESET);
    for (int k = 0; k < SIL_STEPS_PER_ROW; k++) {
        sil_control_step();
        if (mock_sm_get_power_level() != 0u) {
            return sil_fail("reset_accepted: power on during the reset");
        }
    }
    mock_sm_release_button(BUTTON_RESET);
    for (int r = 0; r < 30 && state_machine_get_state() != STATE_IDLE; r++) {
        for (int k = 0; k < SIL_STEPS_PER_ROW; k++) {
            sil_control_step();
            if (mock_sm_get_power_level() != 0u) {
                return sil_fail("reset_accepted: power on after the reset");
            }
        }
    }
    if (state_machine_get_state() != STATE_IDLE || state_machine_get_fault() != FAULT_NONE) {
        snprintf(msg, sizeof(msg), "reset_accepted: state %d fault %d after the reset (fault %d)",
                 (int)state_machine_get_state(), (int)state_machine_get_fault(),
                 (int)entry->expected_fault);
        return sil_fail(msg);
    }
    printf("  [PASS] reset accepted once the sensor reads good; IDLE with the power at 0\n");
    return true;
}

/* C1 rule attribution where the firmware exposes it. */
static bool assert_c1_mechanism(const manifest_entry_t *entry, float reading_at_trip) {
#ifdef TEMPER_PAN_CONTROL_C1
    char msg[200];
    const char *m = entry->c1_mechanism;
    if (!strcmp(m, "R2-2a") || !strcmp(m, "R2-2b")) {
        const int want = !strcmp(m, "R2-2a") ? 1 : 2;
        const int got = pan_control_supervisor_latch();
        if (got != want) {
            snprintf(msg, sizeof(msg), "C1 mechanism %s expected: supervisor latch %d, got %d",
                     m, want, got);
            return sil_fail(msg);
        }
        printf("  [C1] supervisor latch %s\n", m);
    } else if (!strcmp(m, "isense-run") || !strcmp(m, "isense-pulse")) {
        const int want = !strcmp(m, "isense-run") ? 1 : 2;
        const int got = pan_control_current_sense_latch();
        if (got != want) {
            snprintf(msg, sizeof(msg), "C1 mechanism %s expected: current-sense latch %d, got %d",
                     m, want, got);
            return sil_fail(msg);
        }
        printf("  [C1] current-sense latch %s\n", m);
    } else if (!strcmp(m, "xchk-leak")) {
        if (!pan_control_leak_latched() || pan_control_rim_limit_latched()) {
            return sil_fail("C1 mechanism xchk-leak expected: the Pt100 leak check has not latched "
                            "(or the rim limit latched instead)");
        }
        printf("  [C1] Pt100 leak check latched after %u cross-check suspects\n",
               (unsigned)pan_control_xcheck_suspects());
    } else if (!strcmp(m, "cold-soak") || !strcmp(m, "cold-soak-pass") ||
               !strcmp(m, "cold-soak-skip")) {
        const pcs_result_t r = pan_control_cold_soak_result();
        const pcs_verdict_t want = !strcmp(m, "cold-soak") ? PCS_LEAK
                                 : (!strcmp(m, "cold-soak-pass") ? PCS_PASS : PCS_SKIP_NOT_SOAKED);
        if (r.verdict != want || pan_control_cold_soak_latched() != (want == PCS_LEAK)) {
            snprintf(msg, sizeof(msg), "C1 mechanism %s expected: cold-soak verdict '%s' "
                     "(latched %d), got '%s'", m, pcs_verdict_name(want),
                     (int)pan_control_cold_soak_latched(), pcs_verdict_name(r.verdict));
            return sil_fail(msg);
        }
        printf("  [C1] cold soak: %s (coil off %.0f s, heatsink %.2f C, Pt100 %.2f C, gap %.2f K)\n",
               pcs_verdict_name(r.verdict), (double)r.off_s, (double)r.hs_c, (double)r.pt_c,
               (double)r.gap_k);
    } else if (!strcmp(m, "rim-limit")) {
        if (!pan_control_rim_limit_latched()) {
            return sil_fail("C1 mechanism rim-limit expected: the setpoint-relative rim limit has not latched");
        }
        printf("  [C1] setpoint-relative rim limit latched (%u cross-check suspects before it)\n",
               (unsigned)pan_control_xcheck_suspects());
    } else if (!strcmp(m, "R1")) {
        if (!(reading_at_trip < g_config.runaway.max_absolute_temp_c)) {
            snprintf(msg, sizeof(msg), "C1 mechanism R1 expected: reading %.1f C at the trip "
                     "is above the absolute limit", reading_at_trip);
            return sil_fail(msg);
        }
        printf("  [C1] R1 tripped at reading %.1f C (below the absolute %.0f C)\n",
               reading_at_trip, g_config.runaway.max_absolute_temp_c);
    } else if (!strcmp(m, "absolute-300")) {
        if (!(reading_at_trip > g_config.runaway.max_absolute_temp_c)) {
            snprintf(msg, sizeof(msg), "C1 mechanism absolute-300 expected: reading %.1f C",
                     reading_at_trip);
            return sil_fail(msg);
        }
    } else if (!strcmp(m, "rtd-07h")) {
        rtd_sample_t smp;
        if (!rtd_service_latest_sample(&smp) || smp.fault_status == 0u) {
            return sil_fail("C1 mechanism rtd-07h expected: no register 07h fault in the "
                            "latest conversion");
        }
        printf("  [C1] register 07h = 0x%02X\n", smp.fault_status);
    } else if (!strcmp(m, "rtd-stale") || !strcmp(m, "rtd-frozen")) {
        if (rtd_service_is_ready()) {
            snprintf(msg, sizeof(msg), "C1 mechanism %s expected: the RTD service is "
                     "still running", m);
            return sil_fail(msg);
        }
        printf("  [C1] RTD service stopped (%s)\n", m);
    }
#else
    (void)entry;
    (void)reading_at_trip;
#endif
    return true;
}

/* ---------------------------------------------------------------------------
 * Timing/timeout injection (plan 031/U3)
 *
 * Advances time once across a manifest-derived boundary (e.g.
 * MAX_PREHEAT_TIME_MS) instead of replaying a CSV trace tick-by-tick --
 * timeouts on the order of minutes don't fit MAX_TICKS*DT_MS (100s).
 * --------------------------------------------------------------------------- */

static bool run_sil_timing_test(const manifest_entry_t *entry) {
    sil_reset(entry);
    uint32_t pwm_disable_baseline = mock_sm_get_pwm_disable_count();

    sm_boilerplate_to_origin(entry->origin_state, entry->self_test_pass, NAN);

    if (!entry->self_test_pass) {
        if (state_machine_get_state() != STATE_FAULT ||
            state_machine_get_fault() != entry->expected_fault) {
            return sil_fail("self-test failure not detected");
        }
        if (!assert_safe_state_side_effects(entry, pwm_disable_baseline)) return false;
        printf("  [PASS] self_test_failed detected\n");
        return assert_reset_refused(entry);
    }

    if (state_machine_get_state() != entry->origin_state) {
        char msg[128];
        snprintf(msg, sizeof(msg), "origin state %d not reached (state %d)",
                 (int)entry->origin_state, (int)state_machine_get_state());
        return sil_fail(msg);
    }

    /* Single large jump across the timeout boundary; the check fires on the
     * state's own next update() (state_duration is measured from
     * state_entry_time, not accumulated per-tick). */
    mock_sm_advance_time((uint32_t)entry->timing_advance_ms);
#ifdef TEMPER_PAN_CONTROL_C1
    c1_control_tick();
#else
    state_machine_update();
#endif

    /* Some timeout paths (e.g. PAN_TIMEOUT -> IDLE) go through
     * show_message_then_transition(): the first update() only arms
     * message_pending, the actual transition needs a second update() after
     * MESSAGE_DISPLAY_TIME_MS. Always run this second step; it is a no-op
     * for paths that already transitioned directly (e.g. FAULT via
     * enter_hardware_latched_fault()), since a second state_fault_update()
     * doesn't re-run state_fault_entry() or change the probe counters. */
    mock_sm_advance_time(MESSAGE_DISPLAY_TIME_MS + 100);
#ifdef TEMPER_PAN_CONTROL_C1
    c1_control_tick();
#else
    state_machine_update();
#endif

    system_state_t st = state_machine_get_state();
    fault_code_t fc = state_machine_get_fault();

    if (st != entry->expected_state) {
        char msg[256];
        snprintf(msg, sizeof(msg),
                 "Expected state %d after %ld ms advance from origin %d, got state %d",
                 (int)entry->expected_state, entry->timing_advance_ms,
                 (int)entry->origin_state, (int)st);
        return sil_fail(msg);
    }
    if (fc != entry->expected_fault) {
        char msg[128];
        snprintf(msg, sizeof(msg), "Expected fault %d, got %d",
                 (int)entry->expected_fault, (int)fc);
        return sil_fail(msg);
    }

    printf("  [PASS] state=%d fault=%d after %ld ms advance\n",
           (int)st, (int)fc, entry->timing_advance_ms);

    if (!assert_safe_state_side_effects(entry, pwm_disable_baseline)) return false;
    return assert_reset_refused(entry);
}

/* ---------------------------------------------------------------------------
 * Run a single fault-injection test
 * --------------------------------------------------------------------------- */

static csvrow_t g_rows[MAX_TICKS];

static bool run_sil_scenario(const manifest_entry_t *entry) {
    csvrow_t *rows = g_rows;
    int row_count;

    if (entry->is_timing_scenario) {
        return run_sil_timing_test(entry);
    }

    /* Build full path to perturbed trace (relative to traces/ directory) */
    char trace_path[512];
    snprintf(trace_path, sizeof(trace_path), "traces/%s",
             entry->trace_file);

    row_count = load_csv(trace_path, rows, MAX_TICKS);
    if (row_count == 0) {
        return sil_fail("Failed to load trace file");
    }

    /* Pre-flight: validate trace invariants before replay.
     * Catches traces that would trigger safety faults before the
     * injected perturbation — a common failure mode when safety
     * thresholds change.  Violations are logged but don't block
     * execution; the replay itself is the ground truth. */
    check_trace_invariants(rows, row_count, entry);

    /* Reset and initialize */
    sil_reset(entry);

    /* Baseline the power-disable probe before any boilerplate/replay runs,
     * so the hard power_off assertion measures an increment attributable to
     * this scenario rather than assuming a zero starting count. */
    uint32_t pwm_disable_baseline = mock_sm_get_pwm_disable_count();

    /* Boilerplate: get to the scenario's designed origin state (or FAULT if
     * self-test fails) */
    g_idle_soak_s = entry->c1_idle_soak_s;
    g_idle_rows = rows;
    sm_boilerplate_to_origin(entry->origin_state, entry->self_test_pass, rows[0][2]);
    g_idle_soak_s = 0;
    g_idle_rows = NULL;

    /* If self-test was set to fail, we should already be in FAULT */
    if (!entry->self_test_pass) {
        system_state_t st = state_machine_get_state();
        fault_code_t fc = state_machine_get_fault();

        if (st == STATE_FAULT && fc == FAULT_SELF_TEST_FAILED) {
            /* Expected outcome - test passes */
            if (!assert_safe_state_side_effects(entry, pwm_disable_baseline)) return false;
            printf("  [PASS] self_test_failed detected\n");
            return assert_reset_refused(entry);
        }
    }

    /* Now replay the trace tick by tick */
    system_state_t expected_state = entry->expected_state;
    fault_code_t expected_fault = entry->expected_fault;
    bool escalate = false;
#ifdef TEMPER_PAN_CONTROL_C1
    if (entry->c1_escalates_to_runaway) {
        escalate = true;
        expected_state = STATE_RUNAWAY_FAULT;
        expected_fault = FAULT_RUNAWAY_BOUNDARY;
    }
#endif
    const int max_latency =
#ifdef TEMPER_PAN_CONTROL_C1
        entry->max_latency_ticks_c1 >= 0 ? entry->max_latency_ticks_c1 :
#endif
        entry->max_latency_ticks;
    int perturbation_end_tick = entry->perturbation_at_tick +
                                entry->perturbation_over_ticks;
    int latency = 0;
    bool state_reached = false;
    int reached_tick = -1;
    fault_code_t captured_fault = FAULT_NONE;
    float reading_at_trip = NAN;
    char msg[256];

    for (int t = 0; t < row_count && t < MAX_TICKS; t++) {
        apply_row(rows, t);

#ifndef TEMPER_PAN_CONTROL_C1
        /* At tick 0: establish the trace's starting temperature as the
         * runaway rate-of-rise baseline.  The boilerplate phase ran at
         * the mock default (25 C); the CSV typically starts at ~92 C.
         * Without this reset, the apparent 67 C/s jump triggers a
         * spurious RUNAWAY_FAULT before the injected fault fires. */
        if (t == 0) {
            state_machine_reset_temp_baseline();
            state_machine_reset_stuck_tracking();
        }

        /* At perturbation start: reset the runaway baseline so the
         * injected sensor change (e.g., pan 92->115 C for thermal
         * runaway) doesn't trigger a spurious rate-of-rise before
         * the fault handler runs.  The perturbation itself is the
         * fault, not a real temperature ramp. */
        if (t == entry->perturbation_at_tick) {
            state_machine_reset_temp_baseline();
        }
#endif
        /* C1 needs neither hook: the boilerplate primed the trace's starting
         * temperature, and R1 does not trip on a single step. */

        /* Origin check: the fault is injected from the designed state. */
        if (t == entry->perturbation_at_tick && t > 0 &&
            entry->origin_state != STATE_INIT &&
            state_machine_get_state() != entry->origin_state) {
            snprintf(msg, sizeof(msg),
                     "origin state %d not reached at the perturbation (tick %d, state %d)",
                     (int)entry->origin_state, t, (int)state_machine_get_state());
            return sil_fail(msg);
        }

        for (int k = 0; k < SIL_STEPS_PER_ROW; k++) {
            sil_control_step();

            system_state_t st = state_machine_get_state();

            /* No fault before the perturbation starts. */
            if (t < entry->perturbation_at_tick &&
                (st == STATE_FAULT || st == STATE_RUNAWAY_FAULT)) {
                snprintf(msg, sizeof(msg),
                         "premature fault %d at tick %d, before the perturbation at tick %d",
                         (int)state_machine_get_fault(), t, entry->perturbation_at_tick);
                return sil_fail(msg);
            }

            /* After perturbation end, monitor for expected state */
            if (t >= perturbation_end_tick && !state_reached) {
                if (st == expected_state) {
                    state_reached = true;
                    reached_tick = t;
                    latency = t - perturbation_end_tick + 1;
                    captured_fault = state_machine_get_fault();
#ifdef TEMPER_PAN_CONTROL_C1
                    /* the firmware's reading: the latest conversion */
                    reading_at_trip = pan_control_reading_c();
#else
                    reading_at_trip = read_pan_temperature();
#endif
                }
            } else if (state_reached && entry->hold_state && st != expected_state) {
                snprintf(msg, sizeof(msg),
                         "state left %d at tick %d (state %d, fault %d); expected to hold",
                         (int)expected_state, t, (int)st, (int)state_machine_get_fault());
                return sil_fail(msg);
            }
        }
    }

    /* --- Assertions --- */

    /* State reached check */
    if (!state_reached) {
        snprintf(msg, sizeof(msg),
                 "Expected state %d, but trace ended in state %d (tick %d, fault %d)",
                 (int)expected_state, (int)state_machine_get_state(), row_count,
                 (int)state_machine_get_fault());
        return sil_fail(msg);
    }

    /* Fault code check (captured at transition moment) */
    if (captured_fault != expected_fault) {
        snprintf(msg, sizeof(msg), "Expected fault %d, got %d (tick %d)",
                 (int)expected_fault, (int)captured_fault, reached_tick);
        return sil_fail(msg);
    }
    if (entry->hold_state && state_machine_get_fault() != FAULT_NONE &&
        entry->expected_fault == FAULT_NONE) {
        snprintf(msg, sizeof(msg), "fault %d raised while holding state %d",
                 (int)state_machine_get_fault(), (int)entry->expected_state);
        return sil_fail(msg);
    }

    /* Latency check */
    if (latency > max_latency) {
        snprintf(msg, sizeof(msg),
                 "Latency %d ticks > max %d ticks", latency, max_latency);
        return sil_fail(msg);
    }

    printf("  [PASS] state=%d fault=%d latency=%d ticks (at tick %d, bound %d), "
           "reading %.1f C%s\n",
           (int)expected_state, (int)captured_fault, latency, reached_tick,
           max_latency, reading_at_trip, entry->hold_state ? ", held to the end" : "");

    /* --- Hard assertions (plan 031/U2): failing, not warning --- */
    if (!assert_safe_state_side_effects(entry, pwm_disable_baseline)) return false;
    if (entry->c1_mechanism[0] != '\0' && !assert_c1_mechanism(entry, reading_at_trip)) return false;
    if (!assert_first_fault_latched(entry, expected_state, captured_fault, escalate)) return false;
    if (entry->reset_accepted) return assert_reset_accepted(entry);
    return assert_reset_refused(entry);
}

/* ---------------------------------------------------------------------------
 * Test runner entry point
 * --------------------------------------------------------------------------- */

void setUp(void) {}
void tearDown(void) {}

static manifest_entry_t g_entries[MAX_MANIFEST_ENTRIES];
static const manifest_entry_t *g_current;

static void test_sil_scenario(void) {
    const manifest_entry_t *e = g_current;
    printf("\n[SIL/%s] %s\n", SIL_MODE, e->name);
    if (e->finding[0] != '\0') {
        printf("  [FINDING] %s\n", e->finding);
    }
#ifdef TEMPER_PAN_CONTROL_C1
    if (e->c1_mechanism[0] != '\0') {
        printf("  [C1] mechanism: %s\n", e->c1_mechanism);
    }
#endif
    g_fail[0] = '\0';
    const bool ok = run_sil_scenario(e);
    if (e->xfail_reason[0] != '\0') {
        if (ok) {
            char msg[400];
            snprintf(msg, sizeof(msg), "XPASS (expected failure now passes; remove the "
                     "xfail marker): %s", e->xfail_reason);
            TEST_FAIL_MESSAGE(msg);
        }
        printf("  [XFAIL] %s\n  [XFAIL] reason: %s\n", g_fail, e->xfail_reason);
        TEST_IGNORE_MESSAGE("XFAIL (known defect, see manifest xfail)");
    }
    if (!ok) {
        TEST_FAIL_MESSAGE(g_fail);
    }
}

int main(void) {
    const int total = parse_manifest(g_entries, MAX_MANIFEST_ENTRIES);

    if (total == 0) {
        printf("No SIL test cases found in manifest.json -- skipping\n");
        return 0;
    }

    printf("\n=== SIL Fault-Injection Tests (%s) ===\n", SIL_MODE);
    printf("Loaded %d test case(s) from manifest.json\n", total);

    UnityBegin("test_sil_fault_injection.c [" SIL_MODE "]");

    int run = 0;
    for (int i = 0; i < total; i++) {
        const manifest_entry_t *e = &g_entries[i];
#ifdef TEMPER_PAN_CONTROL_C1
        const bool applies = e->run_c1;
#else
        const bool applies = e->run_legacy;
#endif
        if (!applies) {
            printf("\n[SIL/%s] not in this mode: %s\n", SIL_MODE, e->name);
            continue;
        }
        g_current = e;
        UnityDefaultTestRun(test_sil_scenario, e->name, i);
        run++;
    }
    printf("\n%d of %d manifest scenarios apply to the %s target\n", run, total, SIL_MODE);

    return UnityEnd();
}
