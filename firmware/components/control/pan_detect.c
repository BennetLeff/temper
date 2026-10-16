/**
 * @file pan_detect.c
 * @brief Pan detection implementation for induction cooker
 *
 * Uses "Pulse and Listen" algorithm:
 * 1. Generate short energy pulse into tank circuit
 * 2. Listen for resonant ring-down cycles via ZCD signal
 * 3. Analyze decay pattern to determine pan presence
 *
 * Decay Interpretation:
 * - < 5 cycles: Pan present (ferrous) - heavy magnetic damping
 * - > 20 cycles: No pan - high Q-factor tank rings freely
 * - < 2 cycles: Non-ferrous or fault - over-damped
 *
 * Builds on the host as well (the ESP-IDF capture glue is under
 * ESP_PLATFORM), so the host tests run the real sequence and thresholds.
 * See pan_detect.h for the zapote wiring and the burst-start rule.
 */

#include "pan_detect.h"
#include "pll_control.h"

#include <stddef.h>

#ifdef ESP_PLATFORM
#include "driver/mcpwm_prelude.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "pan_detect";
#endif

/* Configuration */
#define DECAY_THRESHOLD_PAN 8     /* Edge count below this = pan present */

static pan_detect_config_t s_config = PAN_DETECT_DEFAULT_CONFIG();
static const pan_detect_pulse_ops_t *s_pulse_ops = NULL;
static pan_detect_listen_fn s_listen = NULL;
static float s_last_impedance = 0.0f;

#ifdef ESP_PLATFORM
/* Global context for ISR */
static volatile uint32_t edge_count = 0;
static portMUX_TYPE edge_count_spinlock = portMUX_INITIALIZER_UNLOCKED;

/**
 * @brief Capture callback (ISR) - Counts zero-crossings
 */
static bool IRAM_ATTR decay_capture_cb(mcpwm_cap_channel_handle_t cap_chan,
                                        const mcpwm_capture_event_data_t *edata,
                                        void *user_data) {
    (void)cap_chan;
    (void)edata;
    (void)user_data;
    edge_count++;
    return false; /* No context switch needed */
}

/* Listen over the CT_ZC capture channel. */
static uint32_t capture_listen(uint32_t window_ms) {
    portENTER_CRITICAL(&edge_count_spinlock);
    edge_count = 0;
    portEXIT_CRITICAL(&edge_count_spinlock);

    /* Ringing at 30-60 kHz: 30 cycles is well under 2 ms. */
    vTaskDelay(pdMS_TO_TICKS(window_ms) > 0 ? pdMS_TO_TICKS(window_ms) : 1);

    portENTER_CRITICAL(&edge_count_spinlock);
    const uint32_t n = edge_count;
    portEXIT_CRITICAL(&edge_count_spinlock);
    return n;
}
#endif

esp_err_t pan_detect_init(mcpwm_cap_channel_handle_t cap_chan,
                          const pan_detect_config_t *config) {
    if (config != NULL) {
        s_config = *config;
    } else {
        s_config = (pan_detect_config_t)PAN_DETECT_DEFAULT_CONFIG();
    }
    s_listen = NULL;
    if (cap_chan == NULL) {
#ifdef ESP_PLATFORM
        ESP_LOGE(TAG, "Invalid capture channel handle");
#endif
        return ESP_ERR_INVALID_ARG;
    }
#ifdef ESP_PLATFORM
    mcpwm_capture_event_callbacks_t cbs = {
        .on_cap = decay_capture_cb,
    };
    esp_err_t ret = mcpwm_capture_channel_register_event_callbacks(cap_chan, &cbs, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register capture callback: %s", esp_err_to_name(ret));
        return ret;
    }
    ret = mcpwm_capture_channel_enable(cap_chan);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable capture channel: %s", esp_err_to_name(ret));
        return ret;
    }
    s_listen = capture_listen;
    ESP_LOGI(TAG, "Pan detection listening on CT_ZC (pulse=%luus, threshold=%d/%d)",
             (unsigned long)s_config.pulse_width_us, s_config.threshold_pan,
             s_config.threshold_open);
    return ESP_OK;
#else
    return ESP_ERR_INVALID_ARG;   /* no capture hardware on the host */
#endif
}

void pan_detect_set_pulse_ops(const pan_detect_pulse_ops_t *ops) {
    s_pulse_ops = ops;
}

pan_result_t pan_detect_run_ops(const pan_detect_pulse_ops_t *ops,
                                pan_detect_listen_fn listen,
                                const pan_detect_config_t *config) {
    const pan_detect_config_t *cfg = (config != NULL) ? config : &s_config;
    if (ops == NULL || ops->gates_idle == NULL || ops->set_frequency_hz == NULL ||
        ops->pulse == NULL || listen == NULL) {
        return PAN_DETECT_ERROR;
    }
    /* A pulse is a start of switching: from idle gates only, at or above the
     * last known resonance (zapote C39), or not at all. */
    if (!ops->gates_idle()) {
        return PAN_DETECT_ERROR;
    }
    float f_start;
    if (!pll_burst_start_frequency(&f_start)) {
        return PAN_DETECT_ERROR;
    }
    if (!ops->set_frequency_hz(f_start)) {
        return PAN_DETECT_ERROR;
    }
    if (!ops->pulse(cfg->pulse_width_us)) {
        return PAN_DETECT_ERROR;
    }

    const uint32_t detected_edges = listen(cfg->listen_window_ms);

    /* More damping (fewer edges) = higher impedance pan. edges = 0 means no
     * ring at all (sensor or drive fault): infinity indicator. */
    if (detected_edges > 0) {
        s_last_impedance = 1000.0f / (float)detected_edges;
    } else {
        s_last_impedance = 99999.0f;
    }
    return analyze_edges(detected_edges);
}

pan_result_t analyze_edges(uint32_t edges) {
    if (edges == 0) {
        return PAN_DETECT_ERROR;    /* Sensor fault? */
    } else if (edges < 3) {
        return PAN_DETECT_NON_FERROUS; /* Damped instantly (aluminum or short) */
    } else if (edges < DECAY_THRESHOLD_PAN) {
        return PAN_DETECT_FERROUS;  /* Good ferrous pan */
    } else {
        return PAN_DETECT_NONE;     /* Ringing continued (high Q, no pan) */
    }
}

pan_status_t detect_pan_presence(void) {
    if (s_pulse_ops == NULL || s_listen == NULL) {
#ifdef ESP_PLATFORM
        static bool s_logged;
        if (!s_logged) {
            s_logged = true;
            ESP_LOGE(TAG, "TODO(hardware): %s; reporting no pan",
                     s_listen == NULL ? "no CT_ZC capture" : "no native-21 pulse ops");
        }
#endif
        return PAN_ABSENT;
    }
    return (pan_detect_run_ops(s_pulse_ops, s_listen, &s_config) == PAN_DETECT_FERROUS)
               ? PAN_PRESENT
               : PAN_ABSENT;
}

float get_pan_impedance(void) {
    return s_last_impedance;
}

#ifndef ESP_PLATFORM
/* Host tests: install a listener in place of the CT_ZC capture. */
void pan_detect_host_set_listen(pan_detect_listen_fn listen);
void pan_detect_host_set_listen(pan_detect_listen_fn listen) {
    s_listen = listen;
}
#endif
