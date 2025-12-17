/**
 * @file pan_detect.h
 * @brief Pan detection module for induction cooker
 * 
 * Implements "Pulse and Listen" pan detection algorithm using
 * ESP32-S3 MCPWM capture unit for non-blocking edge counting.
 */

#ifndef PAN_DETECT_H
#define PAN_DETECT_H

#include <stdint.h>
#include <stdbool.h>

/* ESP-IDF includes - only available when building with ESP-IDF */
#ifdef ESP_PLATFORM
#include "driver/mcpwm_prelude.h"
#else
/* Stub types for host-based unit testing */
typedef void* mcpwm_cap_channel_handle_t;
typedef void* mcpwm_timer_handle_t;
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG -1
#endif

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Pan detection result codes
 */
typedef enum {
    PAN_DETECT_NONE,        /**< No pan detected (high Q ringing) */
    PAN_DETECT_FERROUS,     /**< Ferrous pan detected (good for induction) */
    PAN_DETECT_NON_FERROUS, /**< Non-ferrous material (aluminum/copper) */
    PAN_DETECT_ERROR        /**< Detection error (sensor fault) */
} pan_result_t;

/**
 * @brief Pan presence status
 */
typedef enum {
    PAN_ABSENT,
    PAN_PRESENT
} pan_status_t;

/**
 * @brief Pan detection configuration
 */
typedef struct {
    uint32_t pulse_width_us;        /**< Pulse duration in microseconds */
    uint32_t listen_window_ms;      /**< Listen window duration in ms */
    uint8_t  threshold_pan;         /**< Edge count threshold for pan present */
    uint8_t  threshold_open;        /**< Edge count threshold for open coil */
    uint8_t  confidence_required;   /**< Consecutive detections for confirmation */
} pan_detect_config_t;

/**
 * @brief Default configuration values
 */
#define PAN_DETECT_DEFAULT_CONFIG() { \
    .pulse_width_us = 20,             \
    .listen_window_ms = 2,            \
    .threshold_pan = 8,               \
    .threshold_open = 15,             \
    .confidence_required = 3          \
}

/**
 * @brief Initialize pan detection module
 * 
 * @param cap_chan MCPWM capture channel handle for ZCD signal
 * @param config   Configuration parameters (NULL for defaults)
 * @return ESP_OK on success
 */
esp_err_t pan_detect_init(mcpwm_cap_channel_handle_t cap_chan, 
                          const pan_detect_config_t *config);

/**
 * @brief Set timer handle for detect_pan_presence() wrapper
 * 
 * Must be called before using detect_pan_presence() if not
 * using pan_detect_run() directly with explicit timer handle.
 * 
 * @param timer_handle MCPWM timer handle for pulse generation
 */
void pan_detect_set_timer(mcpwm_timer_handle_t timer_handle);

/**
 * @brief Run single pan detection cycle
 * 
 * Generates a short pulse and counts decay oscillations.
 * Execution time: ~2-3ms (non-blocking during listen phase)
 * 
 * @param timer_handle MCPWM timer for generating pulse
 * @return Detection result
 */
pan_result_t pan_detect_run(mcpwm_timer_handle_t timer_handle);

/**
 * @brief Get current pan presence status
 * 
 * Wrapper that returns simple present/absent based on pan_detect_run()
 * 
 * @return PAN_PRESENT if ferrous pan detected, PAN_ABSENT otherwise
 */
pan_status_t detect_pan_presence(void);

/**
 * @brief Get measured pan impedance (relative value)
 * 
 * Returns estimated impedance based on decay characteristics.
 * Used for tracking same pan vs different pan.
 * 
 * @return Relative impedance value (0-1000)
 */
float get_pan_impedance(void);

/**
 * @brief Analyze edge count (for unit testing)
 * 
 * @param edges Number of edges counted during decay
 * @return Detection result based on edge analysis
 */
pan_result_t analyze_edges(uint32_t edges);

#ifdef __cplusplus
}
#endif

#endif /* PAN_DETECT_H */
