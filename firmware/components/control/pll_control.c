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
    .locked = false
};

static bool pll_enabled = false;
static uint32_t out_of_range_count = 0;
static uint64_t last_update_time_us = 0;

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
    
    /* Update lock status with hysteresis to prevent flicker */
    float abs_error = fabsf(error);
    if (pll_ctx.locked) {
        /* Unlock if error exceeds tolerance + hysteresis */
        if (abs_error > (LOCK_TOLERANCE_US + LOCK_HYSTERESIS_US)) {
            pll_ctx.locked = false;
        }
    } else {
        /* Lock if error within tolerance */
        if (abs_error < LOCK_TOLERANCE_US) {
            pll_ctx.locked = true;
#ifdef ESP_PLATFORM
            ESP_LOGI(TAG, "PLL locked at %.1fHz", pll_ctx.current_freq);
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
