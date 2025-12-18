/**
 * @file zvs_monitor.c
 * @brief ZVS verification implementation
 *
 * Per ticket temper-1lj.3:
 * Implements hardware-based ZVS verification to detect hard switching
 * and prevent IGBT thermal runaway.
 *
 * Hard Switching Detection:
 * - Samples switching node voltage just before high-side turn-on
 * - ZVS requires V_SW < 50V (near zero)
 * - Hard switching indicated by V_SW > 50V (high voltage)
 *
 * Failure Modes:
 * 1. Pan removed during operation
 * 2. PLL frequency divergence
 * 3. Resonant component failure
 * 4. Load impedance change
 */

#include "zvs_monitor.h"
#include <stddef.h>
#include <stdbool.h>

#ifdef ESP_PLATFORM
#include "esp_log.h"
static const char *TAG = "zvs_monitor";
#endif

/* Default configuration values */
#define ZVS_THRESHOLD_V         50.0f   /* Switching node voltage threshold */
#define ZVS_WARNING_COUNT       3       /* Consecutive hard switches for warning */
#define ZVS_POWER_REDUCE_COUNT  3       /* Consecutive for power reduction */
#define ZVS_FAULT_COUNT         10      /* Consecutive for fault/shutdown */
#define ZVS_POWER_REDUCTION     0.5f    /* 50% power reduction */

/* Global ZVS context */
static zvs_context_t zvs_ctx = {
    .threshold_voltage = ZVS_THRESHOLD_V,
    .consecutive_hard_switches = 0,
    .total_hard_switches = 0,
    .total_measurements = 0,
    .status = ZVS_OK,
    .last_vsw_voltage = 0.0f,
    .power_reduced = false
};

static uint32_t warning_threshold = ZVS_WARNING_COUNT;
static uint32_t power_reduce_threshold = ZVS_POWER_REDUCE_COUNT;
static uint32_t fault_threshold = ZVS_FAULT_COUNT;
static float power_reduction_factor = ZVS_POWER_REDUCTION;

void zvs_init(const zvs_config_t *config) {
    if (config != NULL) {
        zvs_ctx.threshold_voltage = config->threshold_voltage;
        warning_threshold = config->warning_count;
        power_reduce_threshold = config->power_reduce_count;
        fault_threshold = config->fault_count;
        power_reduction_factor = config->power_reduction_factor;
    } else {
        /* Use defaults */
        zvs_ctx.threshold_voltage = ZVS_THRESHOLD_V;
        warning_threshold = ZVS_WARNING_COUNT;
        power_reduce_threshold = ZVS_POWER_REDUCE_COUNT;
        fault_threshold = ZVS_FAULT_COUNT;
        power_reduction_factor = ZVS_POWER_REDUCTION;
    }

    zvs_ctx.consecutive_hard_switches = 0;
    zvs_ctx.total_hard_switches = 0;
    zvs_ctx.total_measurements = 0;
    zvs_ctx.status = ZVS_OK;
    zvs_ctx.last_vsw_voltage = 0.0f;
    zvs_ctx.power_reduced = false;

#ifdef ESP_PLATFORM
    ESP_LOGI(TAG, "ZVS monitor initialized: threshold=%.1fV, fault_count=%lu",
             zvs_ctx.threshold_voltage, fault_threshold);
#endif
}

void zvs_update(float vsw_voltage) {
    zvs_ctx.last_vsw_voltage = vsw_voltage;
    zvs_ctx.total_measurements++;

    /* Check if hard switching occurred */
    bool hard_switching = (vsw_voltage > zvs_ctx.threshold_voltage);

    if (hard_switching) {
        zvs_ctx.consecutive_hard_switches++;
        zvs_ctx.total_hard_switches++;

        /* Update status based on severity */
        if (zvs_ctx.consecutive_hard_switches >= fault_threshold) {
            /* CRITICAL: Shutdown required */
            zvs_ctx.status = ZVS_FAULT;
#ifdef ESP_PLATFORM
            ESP_LOGE(TAG, "ZVS FAULT: %lu consecutive hard switches (V_SW=%.1fV)",
                     zvs_ctx.consecutive_hard_switches, vsw_voltage);
#endif
        } else if (zvs_ctx.consecutive_hard_switches > power_reduce_threshold) {
            /* Reduce power to protect IGBT */
            if (!zvs_ctx.power_reduced) {
                zvs_ctx.status = ZVS_POWER_REDUCTION;
                zvs_ctx.power_reduced = true;
#ifdef ESP_PLATFORM
                ESP_LOGW(TAG, "ZVS power reduction: %lu consecutive hard switches (V_SW=%.1fV)",
                         zvs_ctx.consecutive_hard_switches, vsw_voltage);
#endif
            }
        } else if (zvs_ctx.consecutive_hard_switches >= warning_threshold) {
            /* Warning level - log for diagnosis */
            zvs_ctx.status = ZVS_WARNING;
#ifdef ESP_PLATFORM
            ESP_LOGW(TAG, "ZVS warning: %lu consecutive hard switches (V_SW=%.1fV)",
                     zvs_ctx.consecutive_hard_switches, vsw_voltage);
#endif
        }
    } else {
        /* ZVS achieved - reset consecutive counter */
        if (zvs_ctx.consecutive_hard_switches > 0) {
#ifdef ESP_PLATFORM
            ESP_LOGI(TAG, "ZVS restored (V_SW=%.1fV)", vsw_voltage);
#endif
        }
        zvs_ctx.consecutive_hard_switches = 0;
        zvs_ctx.status = ZVS_OK;
        zvs_ctx.power_reduced = false;
    }
}

zvs_status_t zvs_get_status(void) {
    return zvs_ctx.status;
}

bool zvs_is_healthy(void) {
    return (zvs_ctx.status == ZVS_OK || zvs_ctx.status == ZVS_WARNING);
}

void zvs_get_stats(uint32_t *hard_switches, uint32_t *total_switches, float *success_rate) {
    if (hard_switches != NULL) {
        *hard_switches = zvs_ctx.consecutive_hard_switches;
    }
    if (total_switches != NULL) {
        *total_switches = zvs_ctx.total_hard_switches;
    }
    if (success_rate != NULL) {
        if (zvs_ctx.total_measurements > 0) {
            uint32_t successes = zvs_ctx.total_measurements - zvs_ctx.total_hard_switches;
            *success_rate = (float)successes / (float)zvs_ctx.total_measurements;
        } else {
            *success_rate = 1.0f;  /* No measurements yet, assume OK */
        }
    }
}

float zvs_get_power_factor(void) {
    if (zvs_ctx.power_reduced) {
        return power_reduction_factor;
    }
    return 1.0f;  /* Normal operation */
}

void zvs_reset(void) {
    zvs_ctx.consecutive_hard_switches = 0;
    zvs_ctx.total_hard_switches = 0;
    zvs_ctx.total_measurements = 0;
    zvs_ctx.status = ZVS_OK;
    zvs_ctx.last_vsw_voltage = 0.0f;
    zvs_ctx.power_reduced = false;

#ifdef ESP_PLATFORM
    ESP_LOGI(TAG, "ZVS monitor reset");
#endif
}

const zvs_context_t* zvs_get_context(void) {
    return &zvs_ctx;
}

#ifndef ESP_PLATFORM
void zvs_sim_set_status(zvs_status_t status) {
    zvs_ctx.status = status;
}
#endif

