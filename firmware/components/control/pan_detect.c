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
 */

#include "pan_detect.h"
#include "driver/mcpwm_prelude.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "pan_detect";

/* Configuration */
#define PULSE_WIDTH_US      20    /* 20 microseconds pulse */
#define DECAY_THRESHOLD_PAN 8     /* Edge count below this = pan present */
#define DECAY_THRESHOLD_OPEN 15   /* Edge count above this = no pan */

/* Global context for ISR */
static volatile uint32_t edge_count = 0;
static portMUX_TYPE edge_count_spinlock = portMUX_INITIALIZER_UNLOCKED;
static mcpwm_cap_channel_handle_t s_cap_chan = NULL;
static mcpwm_timer_handle_t s_timer_handle = NULL;  /* Timer for detect_pan_presence() */
static pan_detect_config_t s_config;
static float s_last_impedance = 0.0f;
static bool s_initialized = false;

/**
 * @brief Capture callback (ISR) - Counts zero-crossings
 * 
 * Note: edge_count is volatile and accessed atomically in 32-bit operations.
 * For extra safety, we use spinlock in the reading code path.
 */
static bool IRAM_ATTR decay_capture_cb(mcpwm_cap_channel_handle_t cap_chan,
                                        const mcpwm_capture_event_data_t *edata,
                                        void *user_data) {
    /* Atomic increment on ESP32 (32-bit aligned access is atomic) */
    edge_count++;
    return false; /* No context switch needed */
}

esp_err_t pan_detect_init(mcpwm_cap_channel_handle_t cap_chan,
                          const pan_detect_config_t *config) {
    if (cap_chan == NULL) {
        ESP_LOGE(TAG, "Invalid capture channel handle");
        return ESP_ERR_INVALID_ARG;
    }
    
    s_cap_chan = cap_chan;
    
    /* Apply configuration or use defaults */
    if (config != NULL) {
        s_config = *config;
    } else {
        s_config = (pan_detect_config_t)PAN_DETECT_DEFAULT_CONFIG();
    }
    
    /* Register capture callback */
    mcpwm_capture_event_callbacks_t cbs = {
        .on_cap = decay_capture_cb,
    };
    esp_err_t ret = mcpwm_capture_channel_register_event_callbacks(cap_chan, &cbs, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register capture callback: %s", esp_err_to_name(ret));
        return ret;
    }
    
    /* Enable capture channel */
    ret = mcpwm_capture_channel_enable(cap_chan);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable capture channel: %s", esp_err_to_name(ret));
        return ret;
    }
    
    s_initialized = true;
    
    ESP_LOGI(TAG, "Pan detection initialized (pulse=%luus, threshold=%d/%d)",
             s_config.pulse_width_us, s_config.threshold_pan, s_config.threshold_open);
    
    return ESP_OK;
}

/**
 * @brief Set timer handle for detect_pan_presence()
 * 
 * Must be called before using detect_pan_presence() wrapper.
 * 
 * @param timer_handle MCPWM timer handle for pulse generation
 */
void pan_detect_set_timer(mcpwm_timer_handle_t timer_handle) {
    s_timer_handle = timer_handle;
    ESP_LOGI(TAG, "Timer handle set for pan detection");
}

pan_result_t pan_detect_run(mcpwm_timer_handle_t timer_handle) {
    if (timer_handle == NULL) {
        ESP_LOGE(TAG, "pan_detect_run called with NULL timer handle");
        return PAN_DETECT_ERROR;
    }
    
    /* 1. Reset capture counter with critical section for ISR safety */
    portENTER_CRITICAL(&edge_count_spinlock);
    edge_count = 0;
    portEXIT_CRITICAL(&edge_count_spinlock);
    
    /* 2. Generate pulse (one-shot) */
    /* We manually start and stop the timer for a precise short burst */
    /* Note: In production, use a dedicated one-shot timer configuration */
    mcpwm_timer_start_stop(timer_handle, MCPWM_TIMER_START_NO_STOP);
    
    /* Busy-wait for pulse duration (acceptable for this short duration) */
    esp_rom_delay_us(s_config.pulse_width_us);
    
    /* Force stop (High-Z or Low, depending on driver logic) */
    mcpwm_timer_start_stop(timer_handle, MCPWM_TIMER_STOP_EMPTY);
    
    /* 3. Listen window */
    /* Allow ringing to occur. Ringing at 30kHz = 33us per cycle. */
    /* 30 cycles ~ 1ms. Wait 2ms to be safe. */
    vTaskDelay(pdMS_TO_TICKS(s_config.listen_window_ms));
    
    /* 4. Analyze results with atomic read */
    portENTER_CRITICAL(&edge_count_spinlock);
    uint32_t detected_edges = edge_count;
    portEXIT_CRITICAL(&edge_count_spinlock);
    
    /* Calculate relative impedance from edge count */
    /* More damping (fewer edges) = higher impedance pan */
    /* Note: edges=0 means sensor fault, set impedance to infinity indicator */
    if (detected_edges > 0) {
        s_last_impedance = 1000.0f / (float)detected_edges;
    } else {
        s_last_impedance = 99999.0f;  /* Infinity indicator - possible short circuit */
    }
    
    ESP_LOGD(TAG, "Detected %lu edges, impedance=%.1f", detected_edges, s_last_impedance);
    
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
    /* Use module-level timer handle set via pan_detect_set_timer() */
    if (s_timer_handle == NULL) {
        ESP_LOGW(TAG, "detect_pan_presence called but timer not set - call pan_detect_set_timer() first");
        return PAN_ABSENT;
    }
    
    if (!s_initialized) {
        ESP_LOGW(TAG, "detect_pan_presence called but module not initialized");
        return PAN_ABSENT;
    }
    
    pan_result_t result = pan_detect_run(s_timer_handle);
    
    if (result == PAN_DETECT_FERROUS) {
        return PAN_PRESENT;
    }
    return PAN_ABSENT;
}

float get_pan_impedance(void) {
    return s_last_impedance;
}
