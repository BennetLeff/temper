#include "source_policy.h"

#include <stddef.h>

static bool phase_requires_permit_high(temper_esp_phase_t phase) {
    return phase == TEMPER_ESP_REARM_PULSE_STEP ||
           phase == TEMPER_ESP_ARM_STEP || phase == TEMPER_ESP_ACTIVE;
}

static bool phase_requires_watchdog_good(temper_esp_phase_t phase) {
    return phase == TEMPER_ESP_WAIT_PERMIT_HIGH ||
           phase == TEMPER_ESP_REARM_PULSE_STEP ||
           phase == TEMPER_ESP_ARM_STEP || phase == TEMPER_ESP_ACTIVE;
}

static bool phase_is_preauthorization(temper_esp_phase_t phase) {
    return phase == TEMPER_ESP_WAIT_PERMIT_LOW ||
           phase == TEMPER_ESP_WAIT_BUTTON_RELEASE ||
           phase == TEMPER_ESP_SOURCE_SESSION_RESET_STEP ||
           phase == TEMPER_ESP_WAIT_START_PRESS;
}

static void abort_to_lockout(temper_esp_policy_t *policy, bool button_level) {
    policy->phase = TEMPER_ESP_WAIT_PERMIT_LOW;
    policy->source_permit_high_seen = false;
    policy->hot_permit_high_seen = false;
    policy->hot_timer_observed_not_done = false;
    /* A held button at the fault/reset boundary is not a new press. */
    policy->previous_button = button_level;
}

void temper_esp_policy_init(temper_esp_policy_t *policy) {
    if (policy == NULL) return;
    policy->phase = TEMPER_ESP_WAIT_PERMIT_LOW;
    policy->initialized = false;
    policy->previous_button = false;
    policy->source_permit_high_seen = false;
    policy->hot_permit_high_seen = false;
    policy->hot_timer_observed_not_done = false;
}

void temper_esp_policy_step(temper_esp_policy_t *policy,
                           const temper_esp_inputs_t *in,
                           temper_esp_outputs_t *out) {
    if (out == NULL) return;
    *out = (temper_esp_outputs_t){
        .permit_tx_high_request = false,
        .arm_high_request = false,
        .hot_rearm_high_request = false,
        .source_session_reset_low_request = false,
        .wdi_falling_edge_request = false,
        .phase = TEMPER_ESP_WAIT_PERMIT_LOW
    };
    if (policy == NULL || in == NULL) return;

    if (!policy->initialized || in->reset_event) {
        policy->initialized = true;
        abort_to_lockout(policy, in->start_button);
        /* A reset call must never also advance startup or feed WDI. */
        return;
    }

    if (!in->hot_health_raw ||
        (phase_is_preauthorization(policy->phase) &&
         (in->permit_tx_readback || in->hot_permit_readback)) ||
        (phase_requires_watchdog_good(policy->phase) &&
         !in->watchdog_good) ||
        (phase_requires_permit_high(policy->phase) &&
         (!in->permit_tx_readback || !in->hot_permit_readback))) {
        abort_to_lockout(policy, in->start_button);
    }

    const bool rising_button = in->start_button && !policy->previous_button;
    switch (policy->phase) {
    case TEMPER_ESP_WAIT_PERMIT_LOW:
        if (!in->permit_tx_readback && !in->hot_permit_readback &&
            in->hot_health_raw)
            policy->phase = TEMPER_ESP_WAIT_BUTTON_RELEASE;
        break;
    case TEMPER_ESP_WAIT_BUTTON_RELEASE:
        if (!in->permit_tx_readback && !in->hot_permit_readback &&
            !in->start_button)
            policy->phase = TEMPER_ESP_SOURCE_SESSION_RESET_STEP;
        break;
    case TEMPER_ESP_SOURCE_SESSION_RESET_STEP:
        /* Clear retained source PERMIT_SEEN only after both permits are low
         * and the user has released the start button. Deassert next step. */
        if (!in->permit_tx_readback && !in->hot_permit_readback &&
            !in->start_button) {
            out->source_session_reset_low_request = true;
            policy->phase = TEMPER_ESP_WAIT_START_PRESS;
        } else {
            abort_to_lockout(policy, in->start_button);
        }
        break;
    case TEMPER_ESP_WAIT_START_PRESS:
        if (in->permit_tx_readback || in->hot_permit_readback) {
            abort_to_lockout(policy, in->start_button);
        } else if (rising_button && in->watchdog_good) {
            policy->source_permit_high_seen = false;
            policy->hot_permit_high_seen = false;
            policy->hot_timer_observed_not_done = false;
            policy->phase = TEMPER_ESP_WAIT_PERMIT_HIGH;
        }
        break;
    case TEMPER_ESP_WAIT_PERMIT_HIGH:
        /* Low is expected before each readback first rises. Once seen high,
         * either falling again aborts. The timer must be observed not-done
         * after both highs before its done level can qualify this transaction. */
        if (in->permit_tx_readback) {
            policy->source_permit_high_seen = true;
        } else if (policy->source_permit_high_seen) {
            abort_to_lockout(policy, in->start_button);
            break;
        }
        if (in->hot_permit_readback) {
            policy->hot_permit_high_seen = true;
        } else if (policy->hot_permit_high_seen) {
            abort_to_lockout(policy, in->start_button);
            break;
        }
        if (in->permit_tx_readback && in->hot_permit_readback) {
            if (!in->hot_permit_delay_elapsed)
                policy->hot_timer_observed_not_done = true;
            else if (policy->hot_timer_observed_not_done)
                policy->phase = TEMPER_ESP_REARM_PULSE_STEP;
        }
        break;
    case TEMPER_ESP_REARM_PULSE_STEP:
        /* This call is the only place that requests the HOT_REARM rising edge. */
        out->hot_rearm_high_request = true;
        policy->phase = TEMPER_ESP_ARM_STEP;
        break;
    case TEMPER_ESP_ARM_STEP:
        out->arm_high_request = true;
        policy->phase = TEMPER_ESP_ACTIVE;
        break;
    case TEMPER_ESP_ACTIVE:
        /* ARM is an edge request, not a maintained output level. */
        break;
    }

    policy->previous_button = in->start_button;

    /* Requests are assembled synchronously from this invocation only. There is
     * no timer, queue, ISR, or autonomous pulse path in this prototype. */
    out->permit_tx_high_request =
        policy->phase == TEMPER_ESP_WAIT_PERMIT_HIGH ||
        policy->phase == TEMPER_ESP_REARM_PULSE_STEP ||
        policy->phase == TEMPER_ESP_ARM_STEP ||
        policy->phase == TEMPER_ESP_ACTIVE;
    const bool preauthorization_wdi =
        (policy->phase == TEMPER_ESP_WAIT_BUTTON_RELEASE ||
         policy->phase == TEMPER_ESP_WAIT_START_PRESS) &&
        !in->permit_tx_readback && !in->hot_permit_readback;
    const bool startup_wdi =
        (policy->phase == TEMPER_ESP_WAIT_PERMIT_HIGH ||
         policy->phase == TEMPER_ESP_REARM_PULSE_STEP ||
         policy->phase == TEMPER_ESP_ARM_STEP) &&
        in->permit_tx_readback && in->hot_permit_readback &&
        in->watchdog_good;
    const bool active_wdi = policy->phase == TEMPER_ESP_ACTIVE &&
        in->permit_tx_readback && in->hot_permit_readback &&
        in->watchdog_good;
    if (in->hot_health_raw && in->fresh_local_cycle_event &&
        (preauthorization_wdi || startup_wdi || active_wdi))
        out->wdi_falling_edge_request = true;
    out->phase = policy->phase;
}
