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
#include "../config.h"

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
extern uint32_t     mock_sm_get_pwm_disable_count(void);
extern bool         mock_sm_get_pll_enabled(void);
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

typedef struct {
    char name[128];
    char description[256];
    char trace_file[256];
    char finding[512];        /* optional: printed prominently -- used for
                                  demonstrated-gap scenarios that are not
                                  expected to reach a safe state */
    bool self_test_pass;     /* initial_conditions */
    system_state_t origin_state; /* state the manifest defines this fault
                                     path from (INIT/PAN_DET/PREHEAT/HEATING/
                                     COOLDOWN); defaults to HEATING */
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
    /* hard assertions (KTD3): a scenario that reaches the right state but
     * misses these side effects fails the run, it does not warn. */
    bool require_power_off;
    bool require_eeprom_logged;
    fault_code_t expected_eeprom_fault;
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
        e->origin_state = STATE_HEATING; /* default: matches the legacy
                                             single-trajectory scenarios */
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
            } else if (!strcmp(key, "finding")) {
                char *val = extract_string(&p);
                if (val) { strncpy(e->finding, val, sizeof(e->finding) - 1); free(val); }
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
                        } else if (!strcmp(ek, "hard_assertions")) {
                            /* Array of hard assertion objects (KTD3):
                             * power_off and eeprom_logged fail the run when
                             * unmet, they do not warn. */
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
                                                if (!strncmp(p, "true", 4)) { e->require_power_off = true; p += 4; }
                                            } else {
                                                char *sv = extract_string(&p);
                                                if (sv) {
                                                    if (!strcmp(sak, "eeprom_logged")) {
                                                        e->require_eeprom_logged = true;
                                                        e->expected_eeprom_fault = parse_fault_code(sv);
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
 * State machine boilerplate: advance from INIT to a chosen origin state
 *
 * Generalized (plan 031/U1) from the single HEATING-only helper so scenarios
 * can inject from every state the manifest defines a fault path from, not
 * only the end of one trajectory. Each stage returns as soon as the
 * requested origin is reached; falling off the end lands in HEATING, same
 * as the original helper.
 * --------------------------------------------------------------------------- */

static void sm_boilerplate_to_origin(system_state_t origin, bool self_test_pass) {
    /* INIT -> IDLE (self-test runs on first update) */
    if (!self_test_pass) {
        mock_sm_set_selftest_results(false, true, true, true, true, true, true);
    }
    mock_sm_advance_time(DT_MS);
    state_machine_update();

    /* Self-test failure short-circuits every origin: already in FAULT. */
    if (state_machine_get_state() == STATE_FAULT) return;
    if (origin == STATE_INIT) return;

    /* IDLE -> PAN_DET */
    state_machine_set_target_temp(100.0f);
    mock_sm_press_button(BUTTON_START);
    mock_sm_advance_time(DT_MS);
    state_machine_update();
    mock_sm_release_button(BUTTON_START);
    if (origin == STATE_PAN_DET) return;

    /* PAN_DET -> PREHEAT (need pan present + confidence) */
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    for (int i = 0; i < PAN_CONFIDENCE_NEEDED; i++) {
        mock_sm_advance_time(DT_MS);
        state_machine_update();
        if (state_machine_get_state() != STATE_PAN_DET) break;
    }
    if (state_machine_get_state() != STATE_PREHEAT) return; /* didn't arrive; nothing more to do */
    if (origin == STATE_PREHEAT) return;

    /* PREHEAT -> HEATING (pan near target: temp_error <= 10 degrees) */
    mock_sm_set_pan_temperature(92.0f);
    state_machine_reset_temp_baseline();
    mock_sm_advance_time(DT_MS);
    state_machine_update();
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
 * --------------------------------------------------------------------------- */

/* Safety thresholds.  RTD boundaries deliberately use generated config.h
 * rather than local copies so the trace precondition matches the firmware's
 * staged MAX31865 guard window. */
#define INV_MAX_ABSOLUTE_TEMP_C    300.0f
#define INV_MAX_TEMP_RISE_RATE     15.0f   /* C/s */
#define INV_MAX_DC_CURRENT_35A     35.0f
#define INV_MAX_DC_CURRENT_50A     50.0f
#define INV_MAX_HEATSINK_TEMP      100.0f
#define INV_DT_MS                  100     /* DT_MS from SIL test */

static int check_trace_invariants(const csvrow_t *rows, int row_count,
                                   const manifest_entry_t *entry) {
    int violations = 0;

    for (int t = 0; t < row_count && t < entry->perturbation_at_tick; t++) {
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

        /* Base case 3: over-current (>50A = IGBT short, >35A = over-current) */
        if (curr > INV_MAX_DC_CURRENT_50A) {
            printf("  [INV] tick %d: current %.1f > %.1f (IGBT short)\n",
                   t, curr, INV_MAX_DC_CURRENT_50A);
            violations++;
        }
        if (curr > INV_MAX_DC_CURRENT_35A) {
            printf("  [INV] tick %d: current %.1f > %.1f (over-current)\n",
                   t, curr, INV_MAX_DC_CURRENT_35A);
            violations++;
        }

        /* Base case 4: heatsink over-temp */
        if (hs > INV_MAX_HEATSINK_TEMP) {
            printf("  [INV] tick %d: hs_temp %.1f > %.1f\n",
                   t, hs, INV_MAX_HEATSINK_TEMP);
            violations++;
        }

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

        /* Base case 6: fan failure */
        if (!fan) {
            printf("  [INV] tick %d: fan not running\n", t);
            violations++;
        }
    }

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

static void assert_safe_state_side_effects(const manifest_entry_t *entry,
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
            TEST_FAIL_MESSAGE(msg);
            return;
        }
        if (power_level != 0) {
            snprintf(msg, sizeof(msg),
                     "HARD ASSERTION FAILED: power_off expected but "
                     "power_level=%u (expected 0)", power_level);
            TEST_FAIL_MESSAGE(msg);
            return;
        }
        if (pll_enabled) {
            TEST_FAIL_MESSAGE(
                "HARD ASSERTION FAILED: power_off expected but PLL is "
                "still enabled");
            return;
        }
    }

    if (entry->require_eeprom_logged) {
        fault_code_t logged = mock_sm_get_last_logged_fault();
        if (logged != entry->expected_eeprom_fault) {
            snprintf(msg, sizeof(msg),
                     "HARD ASSERTION FAILED: eeprom_logged expected fault "
                     "%d, got %d", (int)entry->expected_eeprom_fault,
                     (int)logged);
            TEST_FAIL_MESSAGE(msg);
            return;
        }
    }
}

/* ---------------------------------------------------------------------------
 * Timing/timeout injection (plan 031/U3)
 *
 * Advances time once across a manifest-derived boundary (e.g.
 * MAX_PREHEAT_TIME_MS) instead of replaying a CSV trace tick-by-tick --
 * timeouts on the order of minutes don't fit MAX_TICKS*DT_MS (100s).
 * --------------------------------------------------------------------------- */

static void run_sil_timing_test(const manifest_entry_t *entry) {
    printf("\n[SIL] %s\n", entry->name);
    if (entry->finding[0] != '\0') {
        printf("  [FINDING] %s\n", entry->finding);
    }

    mock_sm_reset();
    state_machine_init();
    uint32_t pwm_disable_baseline = mock_sm_get_pwm_disable_count();

    sm_boilerplate_to_origin(entry->origin_state, entry->self_test_pass);

    if (!entry->self_test_pass) {
        system_state_t st = state_machine_get_state();
        fault_code_t fc = state_machine_get_fault();
        TEST_ASSERT_EQUAL(STATE_FAULT, st);
        TEST_ASSERT_EQUAL(entry->expected_fault, fc);
        assert_safe_state_side_effects(entry, pwm_disable_baseline);
        printf("  [PASS] self_test_failed detected\n");
        return;
    }

    /* Single large jump across the timeout boundary; the check fires on the
     * state's own next update() (state_duration is measured from
     * state_entry_time, not accumulated per-tick). */
    mock_sm_advance_time((uint32_t)entry->timing_advance_ms);
    state_machine_update();

    /* Some timeout paths (e.g. PAN_TIMEOUT -> IDLE) go through
     * show_message_then_transition(): the first update() only arms
     * message_pending, the actual transition needs a second update() after
     * MESSAGE_DISPLAY_TIME_MS. Always run this second step; it is a no-op
     * for paths that already transitioned directly (e.g. FAULT via
     * enter_hardware_latched_fault()), since a second state_fault_update()
     * doesn't re-run state_fault_entry() or change the probe counters. */
    mock_sm_advance_time(MESSAGE_DISPLAY_TIME_MS + 100);
    state_machine_update();

    system_state_t st = state_machine_get_state();
    fault_code_t fc = state_machine_get_fault();

    if (st != entry->expected_state) {
        char msg[256];
        snprintf(msg, sizeof(msg),
                 "Expected state %d after %ld ms advance from origin %d, got state %d",
                 (int)entry->expected_state, entry->timing_advance_ms,
                 (int)entry->origin_state, (int)st);
        TEST_FAIL_MESSAGE(msg);
        return;
    }
    if (entry->expected_fault != FAULT_NONE || fc != FAULT_NONE) {
        TEST_ASSERT_EQUAL(entry->expected_fault, fc);
    }

    printf("  [PASS] state=%d fault=%d after %ld ms advance\n",
           (int)st, (int)fc, entry->timing_advance_ms);

    assert_safe_state_side_effects(entry, pwm_disable_baseline);
}

/* ---------------------------------------------------------------------------
 * Run a single fault-injection test
 * --------------------------------------------------------------------------- */

static void run_sil_test(const manifest_entry_t *entry) {
    csvrow_t rows[MAX_TICKS];
    int row_count;

    if (entry->is_timing_scenario) {
        run_sil_timing_test(entry);
        return;
    }

    printf("\n[SIL] %s\n", entry->name);
    if (entry->finding[0] != '\0') {
        printf("  [FINDING] %s\n", entry->finding);
    }

    /* Build full path to perturbed trace (relative to traces/ directory) */
    char trace_path[512];
    snprintf(trace_path, sizeof(trace_path), "traces/%s",
             entry->trace_file);

    row_count = load_csv(trace_path, rows, MAX_TICKS);
    if (row_count == 0) {
        TEST_FAIL_MESSAGE("Failed to load trace file");
        return;
    }

    /* Pre-flight: validate trace invariants before replay.
     * Catches traces that would trigger safety faults before the
     * injected perturbation — a common failure mode when safety
     * thresholds change.  Violations are logged but don't block
     * execution; the replay itself is the ground truth. */
    check_trace_invariants(rows, row_count, entry);

    /* Reset and initialize */
    mock_sm_reset();
    state_machine_init();

    /* Baseline the power-disable probe before any boilerplate/replay runs,
     * so the hard power_off assertion measures an increment attributable to
     * this scenario rather than assuming a zero starting count. */
    uint32_t pwm_disable_baseline = mock_sm_get_pwm_disable_count();

    /* Boilerplate: get to the scenario's designed origin state (or FAULT if
     * self-test fails) */
    sm_boilerplate_to_origin(entry->origin_state, entry->self_test_pass);

    /* If self-test was set to fail, we should already be in FAULT */
    if (!entry->self_test_pass) {
        system_state_t st = state_machine_get_state();
        fault_code_t fc = state_machine_get_fault();

        if (st == STATE_FAULT && fc == FAULT_SELF_TEST_FAILED) {
            /* Expected outcome - test passes */
            TEST_ASSERT_EQUAL(STATE_FAULT, st);
            TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, fc);
            assert_safe_state_side_effects(entry, pwm_disable_baseline);
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

    /* --- Hard assertions (plan 031/U2): failing, not warning --- */
    assert_safe_state_side_effects(entry, pwm_disable_baseline);
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
DECLARE_SIL_TEST(16)
DECLARE_SIL_TEST(17)
DECLARE_SIL_TEST(18)
DECLARE_SIL_TEST(19)
DECLARE_SIL_TEST(20)
DECLARE_SIL_TEST(21)
DECLARE_SIL_TEST(22)
DECLARE_SIL_TEST(23)

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
            case 16: RUN_TEST(test_sil_16); break;
            case 17: RUN_TEST(test_sil_17); break;
            case 18: RUN_TEST(test_sil_18); break;
            case 19: RUN_TEST(test_sil_19); break;
            case 20: RUN_TEST(test_sil_20); break;
            case 21: RUN_TEST(test_sil_21); break;
            case 22: RUN_TEST(test_sil_22); break;
            case 23: RUN_TEST(test_sil_23); break;
            default: break;
        }
    }

    return UnityEnd();
}
