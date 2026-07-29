/**
 * @file pll_control.c
 * @brief PLL implementation for ZVS frequency tracking
 * 
 * Uses ESP32-S3 MCPWM capture module to measure phase between
 * PWM output and current zero-crossing (ZCD) signal.
 * 
 * Architecture:
 * 1. PWM Output: Generates 30-50kHz square wave for gate driver
 * 2. Capture Input: Connected to Current Transformer -> Comparator (ZCD)
 * 3. Control Loop: PI controller adjusts frequency to maintain target phase
 * 
 * Phase Measurement:
 * - PWM edge (Low->High) at t=0
 * - Current ZCD (Low->High) at t_zcd
 * - Phase lag = t_zcd / T_sw * 360°
 * 
 * We control t_zcd directly (500ns - 1.5µs) to ensure ZVS.
 */

#include "pll_control.h"
#include <math.h>
#include <stddef.h>
#include <stdbool.h>

/* ESP-IDF includes (available when building with ESP-IDF) */
#ifdef ESP_PLATFORM
#include "driver/mcpwm_prelude.h"
#include "esp_timer.h"
#include "esp_log.h"
static const char *TAG = "pll_control";
#endif

/* Default tuning constants */
#define PLL_KP              2.0f
#define PLL_KI              50.0f
#define TARGET_PHASE_US     1.5f    /* Target lag in microseconds */
#define FREQ_HYSTERESIS_HZ  10.0f   /* Minimum change to apply */
#define LOCK_TOLERANCE_US   0.5f    /* Phase error tolerance for lock */
#define LOCK_HYSTERESIS_US  0.2f    /* Hysteresis to prevent lock flicker */

/* Enhanced lock detection (per ticket temper-1lj.3) */
#define LOCK_CYCLES_REQUIRED    10      /* Consecutive cycles for lock confirmation */
#define UNLOCK_CYCLES_REQUIRED  5       /* Consecutive cycles for unlock confirmation */
#define PHASE_ERROR_DEG_LOCK    15.0f   /* Phase error tolerance in degrees */
#define FREQ_TOLERANCE_HZ       2000.0f /* Frequency tolerance from resonant freq */

/* Frequency boundary checking (safety limits) */
/* NOTE (2026-07-29): FREQ_MARGIN_LOW_HZ is now UNREACHABLE, and that is
 * the intended outcome, not an oversight. It would allow 32.58kHz
 * (37580 - 5000) -- below the loaded resonance, i.e. capacitive-mode hard
 * switching. Since PLL_MIN_FREQ_HZ rose to 42000 (and, 2026-07-29, to
 * 43000 to also worst-case tank capacitor tolerance -- docs/evidence/
 * 2026-07-29-pll-floor-cap-tolerance.md) the frequency clamp in
 * pll_update_loop() is strictly tighter, so pll_is_frequency_safe()'s low
 * bound can no longer be approached. It is left in place rather than
 * retuned: changing this file's safety-window constants is a control-loop
 * decision (see DEFAULT_RESONANT_FREQ's KNOWN OPEN ISSUE below), and the
 * clamp already provides the protection. See docs/evidence/2026-07-29-
 * pll-floor-above-resonance.md. */
#define FREQ_MARGIN_LOW_HZ      5000.0f /* Below resonance limit: f_res - 5kHz */
#define FREQ_MARGIN_HIGH_HZ     10000.0f /* Above resonance limit: f_res + 10kHz */
/**
 * Default expected resonant frequency, for lock detection (line ~266) and
 * frequency-safety bounds checking (pll_is_frequency_safe()).
 *
 * RECONCILED 2026-07-28 (was 35800.0f "from RESONANT_TANK_DESIGN" -- a
 * stale doc reference with no loaded/unloaded qualifier; see
 * docs/evidence/2026-07-28-pll-defaults-and-range-gate.md and
 * docs/evidence/2026-07-28-pll-ratio-tracking-check.md Sec 4).
 *
 * This is the LOADED resonant frequency of the tank: 37.58 kHz, from
 * docs/evidence/2026-07-27-inductance-range-sweep.md Sec 2.1 (L=150 row,
 * "f_res,loaded"), cross-checked by docs/evidence/2026-07-27-zvs-
 * operating-point.md ("loaded (~1.6x) ~ 38 kHz" at the same L).
 *
 * STILL CORRECT AFTER THE 2026-07-29 COIL SPECIFICATION, and the reason
 * is worth stating: elec/src/main.ato's l_tank_assumed moved 150uH ->
 * 88uH and l_pan_loaded_ratio moved 0.399 -> 0.68 in the same commit, as
 * a matched pair. Only the LOADED inductance resonates, and
 * 150 x 0.399 = 59.850uH against 88 x 0.68 = 59.840uH, so the loaded
 * resonance moved from 37 560 Hz to 37 563 Hz -- 0.008%, four orders of
 * magnitude inside this constant's own FREQ_TOLERANCE_HZ. No firmware
 * constant changed. See docs/evidence/2026-07-29-tank-coil-
 * specification.md.
 *
 * Why LOADED and not UNLOADED (31.0 kHz at the declared 88uH/300nF;
 * main.ato's f_resonant_nominal=31kHz tracks that separately, and was
 * 25kHz until the coil was specified): verified against this file's own
 * asymmetric safety window,
 * not asserted from documentation alone. pll_is_frequency_safe() allows
 * -5kHz below resonant_freq but +10kHz ABOVE it -- an asymmetric margin
 * that only makes sense if resonant_freq is the frequency the converter
 * is expected to run ABOVE (the loop runs above resonance for ZVS, per
 * this file's own docstring). With the loaded value (37.58kHz), the
 * corrected default operating point (PLL_DEFAULT_FREQ_HZ=47000, ratio
 * ~1.25) sits +9.42kHz above resonant_freq -- inside the +10kHz margin.
 * Read as UNLOADED (31.0kHz at the declared coil, 23.7kHz under the
 * pre-2026-07-29 150uH assumption), the same 47kHz point would sit
 * +16.0kHz (or +23.3kHz) above resonant_freq, blowing straight through
 * the +10kHz safety ceiling and making pll_is_frequency_safe()
 * permanently false. Under EITHER unloaded reading. Only the
 * LOADED reading is consistent with this file's own already-committed
 * safety-margin constants.
 *
 * KNOWN OPEN ISSUE (not fixed here, out of this constant's scope): with
 * this corrected value, the default 47kHz operating point sits 9.42kHz
 * above resonant_freq, but FREQ_TOLERANCE_HZ (2000.0f, used only for LOCK
 * CONFIRMATION, not frequency-safety bounds) requires current_freq within
 * +-2kHz of resonant_freq to ever confirm lock. Steady-state operation at
 * the corrected ratio (~1.25) therefore cannot satisfy the lock-confirm
 * criterion as coded -- see docs/evidence/2026-07-28-pll-defaults-and-
 * range-gate.md for the firmware-test evidence and why re-tuning
 * FREQ_TOLERANCE_HZ/LOCK criteria is a control-loop decision left to a
 * human, not silently changed by this constant-reconciliation pass.
 */
/* Integer twin of DEFAULT_RESONANT_FREQ, used by the compile-time guard
 * below (an integer constant expression cannot contain float operands in
 * C99). DEFAULT_RESONANT_FREQ is derived from it rather than restated, so
 * the two cannot drift apart. */
#define DEFAULT_RESONANT_FREQ_HZ_INT 37580
#define DEFAULT_RESONANT_FREQ   ((float)DEFAULT_RESONANT_FREQ_HZ_INT)

/*
 * COMPILE-TIME ZVS FLOOR GUARD (2026-07-29, docs/evidence/2026-07-29-pll-
 * floor-above-resonance.md).
 *
 * This is a SERIES-resonant inverter: below the loaded resonance the tank
 * is capacitive and the half-bridge hard-switches -- turn-on loss plus
 * diode reverse recovery on a 1200V IGBT at the full 340V bus. Until
 * 2026-07-29 PLL_MIN_FREQ_HZ was 30000, i.e. 7.58kHz BELOW the resonance
 * declared two lines above, inside the same file. Nothing in the firmware
 * compared them.
 *
 * This assert makes that comparison structural and free. It is
 * deliberately the WEAKER of the two guards: it uses the NOMINAL
 * resonance, because the firmware does not know the coil's tolerance.
 * scripts/check_pll_range_consistency.py derives the same floor at the
 * WORST-CASE (minimum) inductance from elec/src/main.ato and is the
 * authority. Two independent paths, neither able to silently skip.
 *
 * Spelled as a negative-array-size typedef rather than _Static_assert
 * because firmware/test builds with CMAKE_C_STANDARD 99, where
 * _Static_assert is a C11 extension. The x100/x105 scaling keeps the
 * whole expression integral, as C99 requires.
 *
 * If this stops compiling: PLL_MIN_FREQ_HZ is below 1.05x the loaded
 * resonance, so the PLL's own legal range admits capacitive-mode hard
 * switching of the IGBT half-bridge. Raise PLL_MIN_FREQ_HZ (and
 * elec/src/main.ato's f_pll_tracking_min to match). Do not delete this.
 */
typedef char pll_min_freq_is_above_loaded_resonance_check[
    (PLL_MIN_FREQ_HZ * 100 >= DEFAULT_RESONANT_FREQ_HZ_INT * 105) ? 1 : -1
];

/* Loss of lock detection */
#define LOSS_OF_LOCK_COUNT  10      /* Consecutive out-of-range samples for unlock */
#define MIN_VALID_LAG_US    0.1f    /* Minimum valid phase lag */
#define MAX_VALID_LAG_US    20.0f   /* Maximum valid phase lag */

/* Global PLL context */
static pll_context_t pll_ctx = {
    .current_freq = PLL_DEFAULT_FREQ_HZ,
    .integrator = 0.0f,
    .target_phase_us = TARGET_PHASE_US,
    .kp = PLL_KP,
    .ki = PLL_KI,
    .min_freq = PLL_MIN_FREQ_HZ,
    .max_freq = PLL_MAX_FREQ_HZ,
    .locked = false,
    .lock_count = 0,
    .unlock_count = 0,
    .resonant_freq = DEFAULT_RESONANT_FREQ
};

static bool pll_enabled = false;
static uint32_t out_of_range_count = 0;
static uint64_t last_update_time_us = 0;
static float last_phase_error_us = 0.0f;  /* For detailed status reporting */

#ifdef ESP_PLATFORM
static mcpwm_timer_handle_t pll_timer = NULL;
static mcpwm_cap_channel_handle_t pll_cap_chan = NULL;
static volatile uint32_t last_pwm_edge_us = 0;
static volatile uint32_t last_zcd_edge_us = 0;
static volatile bool phase_measurement_ready = false;

/**
 * @brief PWM edge capture callback (ISR)
 */
static bool IRAM_ATTR pwm_edge_cb(mcpwm_cap_channel_handle_t cap_chan,
                                   const mcpwm_capture_event_data_t *edata,
                                   void *user_data) {
    last_pwm_edge_us = (uint32_t)(edata->cap_value / 80);  /* 80MHz clock -> us */
    return false;
}

/**
 * @brief ZCD edge capture callback (ISR)
 */
static bool IRAM_ATTR zcd_edge_cb(mcpwm_cap_channel_handle_t cap_chan,
                                   const mcpwm_capture_event_data_t *edata,
                                   void *user_data) {
    last_zcd_edge_us = (uint32_t)(edata->cap_value / 80);
    phase_measurement_ready = true;
    return false;
}
#endif

void pll_init(const pll_config_t *config) {
    if (config != NULL) {
        pll_ctx.kp = config->kp;
        pll_ctx.ki = config->ki;
        pll_ctx.target_phase_us = config->target_phase_us;
        pll_ctx.min_freq = config->min_freq_hz;
        pll_ctx.max_freq = config->max_freq_hz;
    } else {
        /* Use defaults */
        pll_ctx.kp = PLL_KP;
        pll_ctx.ki = PLL_KI;
        pll_ctx.target_phase_us = TARGET_PHASE_US;
        pll_ctx.min_freq = PLL_MIN_FREQ_HZ;
        pll_ctx.max_freq = PLL_MAX_FREQ_HZ;
    }
    
    pll_ctx.current_freq = (float)PLL_DEFAULT_FREQ_HZ;
    pll_ctx.integrator = 0.0f;
    pll_ctx.locked = false;
    out_of_range_count = 0;
    
#ifdef ESP_PLATFORM
    last_update_time_us = esp_timer_get_time();
    ESP_LOGI(TAG, "PLL initialized: Kp=%.1f Ki=%.1f target=%.1fus range=%lu-%luHz",
             pll_ctx.kp, pll_ctx.ki, pll_ctx.target_phase_us,
             pll_ctx.min_freq, pll_ctx.max_freq);
#endif
}

/**
 * @brief Set MCPWM timer handle for frequency control
 * 
 * Must be called before pll_enable() to allow hardware frequency updates.
 * 
 * @param timer_handle MCPWM timer handle
 */
#ifdef ESP_PLATFORM
void pll_set_timer(mcpwm_timer_handle_t timer_handle) {
    pll_timer = timer_handle;
    ESP_LOGI(TAG, "PLL timer handle set");
}
#endif

/**
 * @brief Set capture channel for phase measurement
 * 
 * @param cap_chan MCPWM capture channel handle for ZCD input
 */
#ifdef ESP_PLATFORM
void pll_set_capture_channel(mcpwm_cap_channel_handle_t cap_chan) {
    pll_cap_chan = cap_chan;
    ESP_LOGI(TAG, "PLL capture channel set");
}
#endif

void pll_enable(void) {
    pll_enabled = true;
    out_of_range_count = 0;
    
#ifdef ESP_PLATFORM
    last_update_time_us = esp_timer_get_time();
    if (pll_timer == NULL) {
        ESP_LOGW(TAG, "PLL enabled but timer not set - call pll_set_timer() first");
    }
    ESP_LOGI(TAG, "PLL tracking enabled");
#endif
}

void pll_disable(void) {
    pll_enabled = false;
    pll_ctx.locked = false;
    
#ifdef ESP_PLATFORM
    ESP_LOGI(TAG, "PLL tracking disabled");
#endif
}

void pll_update_loop(float measured_lag_us, float dt_sec) {
    if (!pll_enabled) {
        return;
    }
    
    /* Validate dt */
    if (dt_sec <= 0.0f || dt_sec > 1.0f) {
        dt_sec = 0.001f;  /* Default 1ms */
    }
    
    /* Check for valid measurement */
    if (measured_lag_us < MIN_VALID_LAG_US || measured_lag_us > MAX_VALID_LAG_US) {
        out_of_range_count++;
        if (out_of_range_count > LOSS_OF_LOCK_COUNT) {
            pll_ctx.locked = false;
#ifdef ESP_PLATFORM
            ESP_LOGW(TAG, "Loss of lock: invalid phase %.2fus", measured_lag_us);
#endif
        }
        return;
    }
    out_of_range_count = 0;
    
    /* Calculate phase error */
    float error = pll_ctx.target_phase_us - measured_lag_us;
    last_phase_error_us = error;  /* Store for status reporting */

    /* PI Control with proper dt scaling */
    float p_out = pll_ctx.kp * error;
    pll_ctx.integrator += pll_ctx.ki * error * dt_sec;

    /* Integrator anti-windup */
    float max_integrator = (float)(pll_ctx.max_freq - pll_ctx.min_freq) / 2.0f;
    if (pll_ctx.integrator > max_integrator) {
        pll_ctx.integrator = max_integrator;
    }
    if (pll_ctx.integrator < -max_integrator) {
        pll_ctx.integrator = -max_integrator;
    }

    /* Calculate new frequency */
    float new_freq = pll_ctx.current_freq + p_out + pll_ctx.integrator;

    /* Safety limits */
    if (new_freq > (float)pll_ctx.max_freq) {
        new_freq = (float)pll_ctx.max_freq;
    }
    if (new_freq < (float)pll_ctx.min_freq) {
        new_freq = (float)pll_ctx.min_freq;
    }

    /* Apply to hardware with hysteresis to avoid jitter */
    if (fabsf(new_freq - pll_ctx.current_freq) > FREQ_HYSTERESIS_HZ) {
#ifdef ESP_PLATFORM
        if (pll_timer != NULL) {
            /* Calculate timer period from frequency */
            /* Period = clock_freq / switching_freq */
            uint32_t period = 160000000 / (uint32_t)new_freq;  /* 160MHz MCPWM clock */
            mcpwm_timer_set_period(pll_timer, period);
        }
#endif
        pll_ctx.current_freq = new_freq;
    }

    /* Enhanced lock detection with consecutive cycle tracking
     * Per ticket temper-1lj.3: Require 10 consecutive cycles with:
     * - Phase error < ±15°
     * - Frequency within ±2kHz of resonant frequency
     */
    float abs_error = fabsf(error);

    /* Convert phase error to degrees for checking
     * phase_deg = (phase_us / period_us) * 360°
     * period_us = 1e6 / freq_hz
     */
    float period_us = 1000000.0f / pll_ctx.current_freq;
    float phase_error_deg = fabsf((error / period_us) * 360.0f);

    /* Check frequency deviation from resonant frequency */
    float freq_deviation = fabsf(pll_ctx.current_freq - pll_ctx.resonant_freq);

    /* Determine if current conditions meet lock criteria */
    bool lock_criteria_met = (phase_error_deg < PHASE_ERROR_DEG_LOCK) &&
                             (freq_deviation < FREQ_TOLERANCE_HZ);

    if (lock_criteria_met) {
        /* Increment lock count, reset unlock count */
        pll_ctx.lock_count++;
        pll_ctx.unlock_count = 0;

        /* Confirm lock after required consecutive cycles */
        if (!pll_ctx.locked && pll_ctx.lock_count >= LOCK_CYCLES_REQUIRED) {
            pll_ctx.locked = true;
#ifdef ESP_PLATFORM
            ESP_LOGI(TAG, "PLL locked at %.1fHz (error: %.1f deg, deviation: %.0fHz)",
                     pll_ctx.current_freq, phase_error_deg, freq_deviation);
#endif
        }
    } else {
        /* Increment unlock count, reset lock count */
        pll_ctx.unlock_count++;
        pll_ctx.lock_count = 0;

        /* Confirm unlock after required consecutive cycles */
        if (pll_ctx.locked && pll_ctx.unlock_count >= UNLOCK_CYCLES_REQUIRED) {
            pll_ctx.locked = false;
#ifdef ESP_PLATFORM
            ESP_LOGW(TAG, "PLL unlock detected (error: %.1f deg, deviation: %.0fHz)",
                     phase_error_deg, freq_deviation);
#endif
        }
    }
}

void pll_update(void) {
#ifdef ESP_PLATFORM
    if (!pll_enabled) {
        return;
    }
    
    /* Calculate dt from actual elapsed time */
    uint64_t now_us = esp_timer_get_time();
    float dt_sec = (float)(now_us - last_update_time_us) / 1000000.0f;
    last_update_time_us = now_us;
    
    /* Check if phase measurement is ready */
    if (!phase_measurement_ready) {
        /* No ZCD signal detected - possible loss of signal */
        out_of_range_count++;
        if (out_of_range_count > LOSS_OF_LOCK_COUNT) {
            pll_ctx.locked = false;
            ESP_LOGW(TAG, "No ZCD signal detected");
        }
        return;
    }
    phase_measurement_ready = false;
    
    /* Calculate phase lag from captured timestamps */
    int32_t lag_us = (int32_t)(last_zcd_edge_us - last_pwm_edge_us);
    
    /* Handle wraparound (should be positive, within one period) */
    if (lag_us < 0) {
        /* ZCD before PWM edge - add one period */
        lag_us += (int32_t)(1000000.0f / pll_ctx.current_freq);
    }
    
    /* Call the control loop with measured phase */
    pll_update_loop((float)lag_us, dt_sec);
    
#else
    /* Non-ESP: no-op, use pll_update_loop() directly for testing */
#endif
}

float pll_get_frequency(void) {
    return pll_ctx.current_freq;
}

bool pll_is_locked(void) {
    return pll_ctx.locked;
}

void pll_set_target_phase(float phase_us) {
    if (phase_us > 0.0f && phase_us < 10.0f) {
        pll_ctx.target_phase_us = phase_us;
    }
}

void pll_reset(void) {
    pll_ctx.current_freq = (float)PLL_DEFAULT_FREQ_HZ;
    pll_ctx.integrator = 0.0f;
    pll_ctx.locked = false;
    out_of_range_count = 0;
    
#ifdef ESP_PLATFORM
    if (pll_timer != NULL) {
        uint32_t period = 160000000 / PLL_DEFAULT_FREQ_HZ;
        mcpwm_timer_set_period(pll_timer, period);
    }
    ESP_LOGI(TAG, "PLL reset to default frequency %dHz", PLL_DEFAULT_FREQ_HZ);
#endif
}

/**
 * @brief Get PLL context for debugging/monitoring
 */
const pll_context_t* pll_get_context(void) {
    return &pll_ctx;
}

/**
 * @brief Set expected resonant frequency for boundary checking
 */
void pll_set_resonant_frequency(float freq_hz) {
    if (freq_hz > 0.0f && freq_hz < 100000.0f) {
        pll_ctx.resonant_freq = freq_hz;
#ifdef ESP_PLATFORM
        ESP_LOGI(TAG, "Resonant frequency set to %.1f Hz", freq_hz);
#endif
    }
}

/**
 * @brief Check if frequency is within safe operating bounds
 *
 * Per ticket temper-1lj.3:
 * - Minimum frequency: f_res - 5kHz (hard limit)
 * - Maximum frequency: f_res + 10kHz (allows inductive margin)
 * - Outside bounds → immediate shutdown required
 */
bool pll_is_frequency_safe(void) {
#ifndef ESP_PLATFORM
    static bool sim_freq_safe = true;
    /* This allows the simulation API to override the real calculation */
#endif
    float min_safe_freq = pll_ctx.resonant_freq - FREQ_MARGIN_LOW_HZ;
    float max_safe_freq = pll_ctx.resonant_freq + FREQ_MARGIN_HIGH_HZ;

    bool is_safe = (pll_ctx.current_freq >= min_safe_freq) &&
                   (pll_ctx.current_freq <= max_safe_freq);

#ifdef ESP_PLATFORM
    if (!is_safe) {
        ESP_LOGE(TAG, "CRITICAL: Frequency %.1fHz outside safe bounds [%.1f, %.1f]",
                 pll_ctx.current_freq, min_safe_freq, max_safe_freq);
    }
#endif

    return is_safe;
}

#ifndef ESP_PLATFORM
void pll_sim_set_locked(bool locked) {
    pll_ctx.locked = locked;
}

void pll_sim_set_frequency_safe(bool safe) {
    if (safe) {
        pll_ctx.current_freq = pll_ctx.resonant_freq;
    } else {
        pll_ctx.current_freq = 0.0f;
    }
}
#endif

/**
 * @brief Get detailed lock status
 */
bool pll_get_lock_status(uint32_t *lock_cycles, float *phase_error_us) {
    if (lock_cycles != NULL) {
        *lock_cycles = pll_ctx.lock_count;
    }
    if (phase_error_us != NULL) {
        *phase_error_us = last_phase_error_us;
    }
    return pll_ctx.locked;
}
