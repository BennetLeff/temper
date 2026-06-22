/**
 * @file test_sil_fault_injection.c
 * @brief SIL (Software-in-the-Loop) fault-injection test runner
 *
 * Reads traces/manifest.json, replays perturbed plant-model traces
 * against the real state_machine.c (compiled for HOST_BUILD), and
 * validates that safety faults cause correct state transitions at
 * correct latency.
 *
 * Uses the mock_sm_* API from state_machine_stubs.c.
 *
 * Build: part of CMake target test_sil_fault_injection
 * Run:   ./build/test_sil_fault_injection
 *        (working directory must contain traces/manifest.json)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
#include <ctype.h>
#include "unity/unity.h"
#include "../main/state_machine.h"

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
extern uint32_t     mock_sm_get_eeprom_log_count(void);
extern uint32_t     mock_sm_get_trigger_shutdown_count(void);
extern uint32_t     mock_sm_get_power_level(void);

#define MOCK_PAN_ABSENT  0
#define MOCK_PAN_PRESENT 1

/* ---------------------------------------------------------------------------
 * Constants
 * --------------------------------------------------------------------------- */

#define MAX_TICKS             1000
#define PAN_ABSENT_THRESHOLD  3.0f
#define PAN_CONFIDENCE_NEEDED 3
#define DT_MS                 100    /* 100 ms per tick (matches plant model dt) */
#define MAX_MANIFEST_ENTRIES  64
#define MAX_CSV_LINE_LEN      512
#define MANIFEST_PATH         "traces/manifest.json"

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
    return STATE_INIT;
}

/* Expected fault-code-string to enum mapping */
static fault_code_t parse_fault_code(const char *str) {
    if (!str || !strcmp(str, "FAULT_NONE"))            return FAULT_NONE;
    if (!strcmp(str, "FAULT_OVER_TEMP"))               return FAULT_OVER_TEMP;
    if (!strcmp(str, "FAULT_OVER_CURRENT"))            return FAULT_OVER_CURRENT;
    if (!strcmp(str, "FAULT_IGBT_SHORT"))              return FAULT_IGBT_SHORT;
    if (!strcmp(str, "FAULT_FAN_FAILURE"))             return FAULT_FAN_FAILURE;
    if (!strcmp(str, "FAULT_PROBE_OPEN"))              return FAULT_PROBE_OPEN;
    if (!strcmp(str, "FAULT_PROBE_SHORT"))             return FAULT_PROBE_SHORT;
    if (!strcmp(str, "FAULT_THERMAL_RUNAWAY"))         return FAULT_THERMAL_RUNAWAY;
    if (!strcmp(str, "FAULT_ADC_STUCK"))               return FAULT_ADC_STUCK;
    if (!strcmp(str, "FAULT_SELF_TEST_FAILED"))        return FAULT_SELF_TEST_FAILED;
    if (!strcmp(str, "FAULT_WATCHDOG_RESET"))          return FAULT_WATCHDOG_RESET;
    if (!strcmp(str, "FAULT_COOLDOWN_OVERHEAT"))       return FAULT_COOLDOWN_OVERHEAT;
    if (!strcmp(str, "FAULT_PAN_DETECT_HW"))           return FAULT_PAN_DETECT_HW;
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
            else if (*p == '"') { /* skip strings inside */ p++; while (*p && *p != '"') p++; }
            p++;
        }
    } else if (*p == '[') {
        /* array */
        int depth = 1; p++;
        while (*p && depth > 0) {
            if (*p == '[') depth++;
            else if (*p == ']') depth--;
            else if (*p == '"') { p++; while (*p && *p != '"') p++; }
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

/* Forward declaration for coverage tracking (defined later) */
static void coverage_record(fault_code_t fc, bool detected, int latency);

typedef struct {
    char name[128];
    char description[256];
    char trace_file[256];
    bool self_test_pass;     /* initial_conditions */
    int  perturbation_at_tick;
    int  perturbation_over_ticks; /* computed from sensors */
    system_state_t expected_state;
    fault_code_t   expected_fault;
    int  max_latency_ticks;
    /* soft assertions */
    bool soft_power_off;
    bool soft_eeprom_logged;
    fault_code_t soft_eeprom_fault;
} manifest_entry_t;

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
        e->self_test_pass = true; /* default */
        e->expected_state = STATE_INIT;
        e->expected_fault = FAULT_NONE;

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
                            p = skip_ws(p);
                            if (!strncmp(p, "true", 4)) { e->self_test_pass = true; p += 4; }
                            else if (!strncmp(p, "false", 5)) { e->self_test_pass = false; p += 5; }
                        } else {
                            skip_value(&p);
                        }
                        free(ik);
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
                        } else if (!strcmp(ek, "soft_assertions")) {
                            /* Array of soft assertion objects */
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
                                            if (!strcmp(sak, "power_off")) {
                                                p = skip_ws(p);
                                                if (!strncmp(p, "true", 4)) { e->soft_power_off = true; p += 4; }
                                            } else {
                                                char *sv = extract_string(&p);
                                                if (sv) {
                                                    if (!strcmp(sak, "eeprom_logged")) {
                                                        e->soft_eeprom_logged = true;
                                                        e->soft_eeprom_fault = parse_fault_code(sv);
                                                    }
                                                    free(sv);
                                                }
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

typedef float csvrow_t[7]; /* 0=tick, 1=hs_temp, 2=pan_temp, 3=dc_cur,
                              4=rtd, 5=pan_imp, 6=fan_run */

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
            "%f,%f,%f,%f,%f,%f,%f",
            &rows[count][0], &rows[count][1], &rows[count][2],
            &rows[count][3], &rows[count][4], &rows[count][5],
            &rows[count][6]);

        if (parsed >= 6) {
            if (parsed < 7) rows[count][6] = rows[count][3] > 0.1f ? 1.0f : 0.0f;
            count++;
        }
    }
    fclose(f);
    return count;
}

/* ---------------------------------------------------------------------------
 * State machine boilerplate: advance from INIT through to HEATING
 * --------------------------------------------------------------------------- */

static void sm_boilerplate_to_heating(bool self_test_pass) {
    /* INIT -> IDLE (self-test runs on first update) */
    if (!self_test_pass) {
        mock_sm_set_selftest_results(false, true, true, true, true, true, true);
    }
    mock_sm_advance_time(DT_MS);
    state_machine_update();

    /* Now in IDLE -- wait if self-test failed (already in FAULT) */

    if (state_machine_get_state() != STATE_FAULT) {
        /* IDLE -> PAN_DET */
        state_machine_set_target_temp(100.0f);
        mock_sm_press_button(BUTTON_START);
        mock_sm_advance_time(DT_MS);
        state_machine_update();
        mock_sm_release_button(BUTTON_START);

        /* PAN_DET -> PREHEAT (need pan present + confidence) */
        mock_sm_set_pan_status(MOCK_PAN_PRESENT);
        for (int i = 0; i < PAN_CONFIDENCE_NEEDED; i++) {
            mock_sm_advance_time(DT_MS);
            state_machine_update();
            if (state_machine_get_state() != STATE_PAN_DET) break;
        }

        /* PREHEAT -> HEATING (pan near target) */
        if (state_machine_get_state() == STATE_PREHEAT) {
            mock_sm_set_pan_temperature(92.0f);
            mock_sm_advance_time(DT_MS);
            state_machine_update();
        }
    }
}

/* ---------------------------------------------------------------------------
 * Run a single fault-injection test
 * --------------------------------------------------------------------------- */

static void run_sil_test(const manifest_entry_t *entry) {
    csvrow_t rows[MAX_TICKS];
    int row_count;

    printf("\n[SIL] %s\n", entry->name);

    /* Build full path to perturbed trace (relative to traces/ directory) */
    char trace_path[512];
    snprintf(trace_path, sizeof(trace_path), "traces/%s",
             entry->trace_file);

    row_count = load_csv(trace_path, rows, MAX_TICKS);
    if (row_count == 0) {
        TEST_FAIL_MESSAGE("Failed to load trace file");
        return;
    }

    /* Reset and initialize */
    mock_sm_reset();
    state_machine_init();

    /* Boilerplate: get to HEATING (or FAULT if self-test fails) */
    sm_boilerplate_to_heating(entry->self_test_pass);

    /* If self-test was set to fail, we should already be in FAULT */
    if (!entry->self_test_pass) {
        system_state_t st = state_machine_get_state();
        fault_code_t fc = state_machine_get_fault();

        if (st == STATE_FAULT && fc == FAULT_SELF_TEST_FAILED) {
            /* Expected outcome - test passes */
            TEST_ASSERT_EQUAL(STATE_FAULT, st);
            TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, fc);
            coverage_record(FAULT_SELF_TEST_FAILED, true, 0);
            printf("  [PASS] self_test_failed detected\n");
            return;
        }
    }

    /* Now replay the trace tick by tick */
    int perturbation_end_tick = entry->perturbation_at_tick +
                                entry->perturbation_over_ticks;
    int latency = 0;
    bool state_reached = false;
    int reached_tick = -1;
    fault_code_t captured_fault = FAULT_NONE;
    (void)mock_sm_get_eeprom_log_count(); /* capture baseline, unused for now */

    for (int t = 0; t < row_count && t < MAX_TICKS; t++) {
        /* Set sensor values from CSV */
        mock_sm_set_heatsink_temperature(rows[t][1]);
        mock_sm_set_pan_temperature(rows[t][2]);
        mock_sm_set_dc_bus_current(rows[t][3]);
        mock_sm_set_rtd_resistance(rows[t][4]);

        /* Derive pan status from pan_impedance */
        if (rows[t][5] < PAN_ABSENT_THRESHOLD) {
            mock_sm_set_pan_status(MOCK_PAN_ABSENT);
        } else {
            mock_sm_set_pan_status(MOCK_PAN_PRESENT);
        }
        mock_sm_set_pan_impedance(rows[t][5]);

        /* Derive fan running: fan_running column takes priority */
        bool fan = (rows[t][6] > 0.5f);
        mock_sm_set_fan_running(fan);

        /* Advance time */
        mock_sm_advance_time(DT_MS);

        /* Call state machine */
        state_machine_update();

        system_state_t st = state_machine_get_state();

        /* After perturbation end, monitor for expected state */
        if (t >= perturbation_end_tick && !state_reached) {
            if (st == entry->expected_state) {
                state_reached = true;
                reached_tick = t;
                latency = t - perturbation_end_tick + 1;
                captured_fault = state_machine_get_fault();
            }
        }
    }

    /* --- Assertions --- */

    /* State reached check */
    if (!state_reached) {
        system_state_t final_st = state_machine_get_state();
        char msg[256];
        snprintf(msg, sizeof(msg),
                 "Expected state %d, but trace ended in state %d (tick %d)",
                 (int)entry->expected_state, (int)final_st, row_count);
        TEST_FAIL_MESSAGE(msg);
        return;
    }

    /* Fault code check (captured at transition moment) */
    if (entry->expected_fault != FAULT_NONE || captured_fault != FAULT_NONE) {
        TEST_ASSERT_EQUAL(entry->expected_fault, captured_fault);
    }

    /* Latency check */
    if (latency > entry->max_latency_ticks) {
        char lat_msg[128];
        snprintf(lat_msg, sizeof(lat_msg),
                 "Latency %d ticks > max %d ticks",
                 latency, entry->max_latency_ticks);
        TEST_FAIL_MESSAGE(lat_msg);
    }

    printf("  [PASS] state=%d fault=%d latency=%d ticks (at tick %d)\n",
           (int)entry->expected_state, (int)captured_fault, latency, reached_tick);

    coverage_record(captured_fault, true, latency);

    /* --- Soft assertions (warnings only) --- */
    if (entry->soft_power_off) {
        if (mock_sm_get_power_level() != 0) {
            printf("  [WARN] soft_assertion: power_off expected but power_level=%u\n",
                   mock_sm_get_power_level());
        }
    }
    if (entry->soft_eeprom_logged) {
        fault_code_t logged = mock_sm_get_last_logged_fault();
        if (logged != entry->soft_eeprom_fault) {
            printf("  [WARN] soft_assertion: eeprom_logged expected %d, got %d\n",
                   (int)entry->soft_eeprom_fault, (int)logged);
        }
    }
}

/* ---------------------------------------------------------------------------
 * Fault coverage tracking
 * --------------------------------------------------------------------------- */

typedef struct {
    fault_code_t fault_code;
    bool tested;
    bool detected;
    int latency_ticks;
} fault_coverage_t;

static fault_coverage_t g_coverage[FAULT_COUNT];
static int g_coverage_count = 0;

static void coverage_record(fault_code_t fc, bool detected, int latency) {
    if (fc == FAULT_NONE) return;
    for (int i = 0; i < g_coverage_count; i++) {
        if (g_coverage[i].fault_code == fc) {
            if (detected) g_coverage[i].detected = true;
            g_coverage[i].latency_ticks = latency;
            return;
        }
    }
    if (g_coverage_count < FAULT_COUNT) {
        g_coverage[g_coverage_count].fault_code = fc;
        g_coverage[g_coverage_count].tested = true;
        g_coverage[g_coverage_count].detected = detected;
        g_coverage[g_coverage_count].latency_ticks = latency;
        g_coverage_count++;
    }
}

static void coverage_print_report(void) {
    printf("\n=== SIL Fault Coverage Report ===\n");
    printf("%-25s %-8s %-9s %s\n", "FAULT CODE", "TESTED", "DETECTED", "LATENCY (ms)");
    printf("-------------------------------------------------------\n");

    /* Build a set of fault codes we have coverage for */
    bool covered[FAULT_COUNT];
    bool detected[FAULT_COUNT];
    int latency_ms[FAULT_COUNT];
    memset(covered, 0, sizeof(covered));
    memset(detected, 0, sizeof(detected));
    memset(latency_ms, 0, sizeof(latency_ms));

    for (int i = 0; i < g_coverage_count; i++) {
        int idx = (int)g_coverage[i].fault_code;
        if (idx >= 0 && idx < FAULT_COUNT) {
            covered[idx] = true;
            detected[idx] = g_coverage[i].detected;
            latency_ms[idx] = g_coverage[i].latency_ticks * DT_MS;
        }
    }

    int total_tested = 0;
    int total_faults = 0;

    /* Iterate FAULT_LIST to print in definition order */
#define PRINT_COVERAGE_LINE(sym, str) \
    { \
        int idx = (int)(sym); \
        if (idx < FAULT_COUNT) { \
            total_faults++; \
            bool t = covered[idx]; \
            bool d = detected[idx]; \
            int lm = latency_ms[idx]; \
            if (t) total_tested++; \
            printf("%-25s %-8s %-9s ", str, t ? "YES" : "NO", t ? (d ? "YES" : "NO") : "-"); \
            if (t && lm > 0) printf("%d", lm); \
            else printf("-"); \
            printf("\n"); \
        } \
    }

    FAULT_LIST(PRINT_COVERAGE_LINE);

#undef PRINT_COVERAGE_LINE

    printf("-------------------------------------------------------\n");
    int pct = total_faults > 0 ? (total_tested * 100) / total_faults : 0;
    printf("Coverage: %d/%d faults tested (%d%%)\n", total_tested, total_faults, pct);
}

/* ---------------------------------------------------------------------------
 * Test runner entry point
 * --------------------------------------------------------------------------- */

void setUp(void) {}
void tearDown(void) {}

/* Dynamically-generated test functions */
static manifest_entry_t g_entries[MAX_MANIFEST_ENTRIES];
static int g_entry_count = 0;

#define DECLARE_SIL_TEST(n) \
    static void test_sil_##n(void) { run_sil_test(&g_entries[n]); }

/* Generate test functions for up to MAX_MANIFEST_ENTRIES */
DECLARE_SIL_TEST(0)
DECLARE_SIL_TEST(1)
DECLARE_SIL_TEST(2)
DECLARE_SIL_TEST(3)
DECLARE_SIL_TEST(4)
DECLARE_SIL_TEST(5)
DECLARE_SIL_TEST(6)
DECLARE_SIL_TEST(7)
DECLARE_SIL_TEST(8)
DECLARE_SIL_TEST(9)
DECLARE_SIL_TEST(10)
DECLARE_SIL_TEST(11)
DECLARE_SIL_TEST(12)
DECLARE_SIL_TEST(13)
DECLARE_SIL_TEST(14)
DECLARE_SIL_TEST(15)

int main(void) {
    g_entry_count = parse_manifest(g_entries, MAX_MANIFEST_ENTRIES);

    if (g_entry_count == 0) {
        printf("No SIL test cases found in manifest.json -- skipping\n");
        return 0;
    }

    printf("\n=== SIL Fault-Injection Tests ===\n");
    printf("Loaded %d test case(s) from manifest.json\n\n", g_entry_count);

    UnityBegin("test_sil_fault_injection.c");

    for (int i = 0; i < g_entry_count; i++) {
        switch (i) {
            case 0:  RUN_TEST(test_sil_0);  break;
            case 1:  RUN_TEST(test_sil_1);  break;
            case 2:  RUN_TEST(test_sil_2);  break;
            case 3:  RUN_TEST(test_sil_3);  break;
            case 4:  RUN_TEST(test_sil_4);  break;
            case 5:  RUN_TEST(test_sil_5);  break;
            case 6:  RUN_TEST(test_sil_6);  break;
            case 7:  RUN_TEST(test_sil_7);  break;
            case 8:  RUN_TEST(test_sil_8);  break;
            case 9:  RUN_TEST(test_sil_9);  break;
            case 10: RUN_TEST(test_sil_10); break;
            case 11: RUN_TEST(test_sil_11); break;
            case 12: RUN_TEST(test_sil_12); break;
            case 13: RUN_TEST(test_sil_13); break;
            case 14: RUN_TEST(test_sil_14); break;
            case 15: RUN_TEST(test_sil_15); break;
            default: break;
        }
    }

    int failures = UnityEnd();

    coverage_print_report();

    return failures;
}
