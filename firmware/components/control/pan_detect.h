/**
 * @file pan_detect.h
 * @brief Pan detection: pulse the tank and count the CT_ZC ring-down edges
 *
 * "Pulse and listen": a short burst into the tank, then the number of
 * tank-current zero crossings during a listen window. A free coil rings for
 * many cycles; a ferrous pan damps it within a few.
 *
 * zapote/controller wiring:
 * - Listen: CT_ZC_MCU (GPIO38, PIN_CT_ZC), the tank-current zero cross from
 *   native-21. On the target pan_detect_init() takes an MCPWM capture channel
 *   on that pin (board_power_init()) and counts its edges.
 * - Pulse: the native-21 full-bridge gate drive. Its waveform is the power
 *   stage's (codex/power-stage-integration) and is not specified in this
 *   tree, so no pulse ops are installed and detect_pan_presence() reports
 *   PAN_ABSENT: no pan, no power (TODO(hardware), DECISIONS.md D-BRINGUP).
 *
 * The pulse is a start of switching, so it obeys the burst-start rule
 * (pll_burst_start_frequency(), zapote C39): it runs only from idle gates, at
 * a frequency at or above the last known resonance, and not at all when the
 * rule refuses. pan_detect_run_ops() is that sequence; it uses only the ops
 * it is given, so the host tests drive it.
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
typedef int esp_err_t;
#ifndef ESP_OK
#define ESP_OK 0
#endif
#ifndef ESP_ERR_INVALID_ARG
#define ESP_ERR_INVALID_ARG 0x102
#endif
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
    PAN_DETECT_ERROR        /**< Detection error, or no pulse was allowed */
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
 * @brief Gate side of a detection pulse, provided by the power stage.
 *
 * Every member is required. The pulse starts only after gates_idle() is true
 * and set_frequency_hz() has programmed the burst-start frequency.
 */
typedef struct {
    bool (*gates_idle)(void);              /**< every gate command low */
    bool (*set_frequency_hz)(float f_hz);  /**< program the pulse frequency */
    bool (*pulse)(uint32_t width_us);      /**< switch for width_us; end with every gate low */
} pan_detect_pulse_ops_t;

/** Count CT_ZC edges over window_ms (from a zero count). */
typedef uint32_t (*pan_detect_listen_fn)(uint32_t window_ms);

/**
 * @brief Initialize pan detection on the target: count edges on a CT_ZC
 *        capture channel (registers the callback and enables the channel).
 *
 * @param cap_chan MCPWM capture channel on CT_ZC (NULL: error)
 * @param config   Configuration parameters (NULL for defaults)
 * @return ESP_OK on success; on the host, ESP_ERR_INVALID_ARG (no capture)
 */
esp_err_t pan_detect_init(mcpwm_cap_channel_handle_t cap_chan,
                          const pan_detect_config_t *config);

/**
 * @brief Install the power stage's pulse ops (NULL removes them).
 *
 * Without them detect_pan_presence() reports PAN_ABSENT.
 */
void pan_detect_set_pulse_ops(const pan_detect_pulse_ops_t *ops);

/**
 * @brief One detection: burst-start check, pulse, listen, classify.
 *
 * @return PAN_DETECT_ERROR without pulsing when any op is missing, the gates
 *         are not idle, or the burst-start rule refuses; PAN_DETECT_ERROR
 *         after the pulse when an op fails; otherwise analyze_edges().
 */
pan_result_t pan_detect_run_ops(const pan_detect_pulse_ops_t *ops,
                                pan_detect_listen_fn listen,
                                const pan_detect_config_t *config);

/**
 * @brief Get current pan presence status
 *
 * @return PAN_PRESENT only for a ferrous result from pan_detect_run_ops()
 *         with the installed ops; PAN_ABSENT otherwise (fail safe).
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
