#ifndef TEMPER_ESP_ONLY_SOURCE_POLICY_H
#define TEMPER_ESP_ONLY_SOURCE_POLICY_H

#include <stdbool.h>

/* Portable policy experiment only. This is not linked to ESP-IDF firmware. */
typedef enum {
    TEMPER_ESP_WAIT_PERMIT_LOW = 0,
    TEMPER_ESP_WAIT_BUTTON_RELEASE,
    TEMPER_ESP_SOURCE_SESSION_RESET_STEP,
    TEMPER_ESP_WAIT_START_PRESS,
    TEMPER_ESP_WAIT_PERMIT_HIGH,
    TEMPER_ESP_REARM_PULSE_STEP,
    TEMPER_ESP_ARM_STEP,
    TEMPER_ESP_ACTIVE
} temper_esp_phase_t;

typedef struct {
    temper_esp_phase_t phase;
    bool initialized;
    bool previous_button;
    bool source_permit_high_seen;
    bool hot_permit_high_seen;
    bool hot_timer_observed_not_done;
} temper_esp_policy_t;

typedef struct {
    /* Event on every reset, including a CPU-only ESP reset. */
    bool reset_event;
    /* Raw HOT rails/fault indication; it does not monitor the HOT PERMIT wire. */
    bool hot_health_raw;
    /* Physical readback of the source-side PERMIT_TX latch/output. */
    bool permit_tx_readback;
    /* Independent physical readback at HOT; not derivable from source Q1. */
    bool hot_permit_readback;
    bool watchdog_good;
    bool start_button;
    /* Local monotonic timeout: current transaction, after both permits read high. */
    bool hot_permit_delay_elapsed;
    /* Current-step event from a fresh local control/safety cycle, never queued. */
    bool fresh_local_cycle_event;
} temper_esp_inputs_t;

typedef struct {
    /* false requests source PERMIT low; true requests source PERMIT high. */
    bool permit_tx_high_request;
    bool arm_high_request;
    /* One-step HOT_REARM high request; no pulse is scheduled by this module. */
    bool hot_rearm_high_request;
    /* One-step active-low clear for retained source PERMIT_SEEN state. */
    bool source_session_reset_low_request;
    /* One-step WDI falling-edge request from this same policy invocation. */
    bool wdi_falling_edge_request;
    temper_esp_phase_t phase;
} temper_esp_outputs_t;

void temper_esp_policy_init(temper_esp_policy_t *policy);
void temper_esp_policy_step(temper_esp_policy_t *policy,
                            const temper_esp_inputs_t *inputs,
                            temper_esp_outputs_t *outputs);

#endif
