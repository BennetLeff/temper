#include "source_policy.h"
#include <stddef.h>

static bool ambient_healthy(const temper_policy_inputs_t *in) {
    return in->rail_good && in->interlock_good;
}

static void enter_wait_low(temper_source_policy_t *p, bool start_level) {
    p->phase = TEMPER_POLICY_WAIT_PERMIT_LOW;
    p->start_was_low = false;
    p->session_ready = false;
    /* A high level present during reset/fault is never a new start edge. */
    p->previous_start = start_level;
}

void temper_source_policy_init(temper_source_policy_t *p) {
    if (p == NULL) return;
    p->phase = TEMPER_POLICY_WAIT_PERMIT_LOW;
    p->initialized = false;
    p->start_was_low = false;
    p->previous_start = false;
    p->session_ready = false;
}

void temper_source_policy_step(temper_source_policy_t *p,
                               const temper_policy_inputs_t *in,
                               temper_policy_outputs_t *out) {
    if (out == NULL) return;
    *out = (temper_policy_outputs_t){
        .request_permit_low = true,
        .rearm_pulse = false,
        .heartbeat_edge_request = false,
        .phase = TEMPER_POLICY_WAIT_PERMIT_LOW
    };
    if (p == NULL || in == NULL) return;

    const bool session_ready_before_event = p->session_ready;

    if (!p->initialized || in->reset_event) {
        p->initialized = true;
        enter_wait_low(p, in->start_request);
    }

    if (!ambient_healthy(in) || in->session_lost) {
        enter_wait_low(p, in->start_request);
    } else if (p->phase == TEMPER_POLICY_WAIT_PERMIT_LOW) {
        /* The requested low may itself drive SOURCE_RESET_GOOD low, so that
         * input cannot be required high until the request is released. */
        if (!in->permit_tx_readback) p->phase = TEMPER_POLICY_WAIT_RESET_GOOD;
    } else if (p->phase == TEMPER_POLICY_WAIT_RESET_GOOD) {
        if (in->permit_tx_readback) {
            enter_wait_low(p, in->start_request);
        } else if (in->reset_good) {
            p->phase = TEMPER_POLICY_WAIT_START_EDGE;
            p->start_was_low = !in->start_request;
        }
    } else if (!in->reset_good ||
               (p->phase >= TEMPER_POLICY_WAIT_PERMIT_HIGH && !in->watchdog_good)) {
        enter_wait_low(p, in->start_request);
    } else if (p->phase == TEMPER_POLICY_ACTIVE &&
               !in->permit_tx_readback) {
        /* Loss of the physical permit indication is a latched lockout. */
        enter_wait_low(p, in->start_request);
    } else if (p->phase == TEMPER_POLICY_WAIT_START_EDGE) {
        if (in->permit_tx_readback) {
            /* Unexpected permit assertion: require a new low observation. */
            enter_wait_low(p, in->start_request);
        } else {
            if (in->new_session_established) p->session_ready = true;
            const bool rising_start = in->start_request && !p->previous_start;
            if (!in->start_request) p->start_was_low = true;
            if (rising_start && p->start_was_low && session_ready_before_event && in->watchdog_good) {
                out->rearm_pulse = true;
                p->phase = TEMPER_POLICY_WAIT_PERMIT_HIGH;
            }
        }
    } else if (p->phase == TEMPER_POLICY_WAIT_PERMIT_HIGH) {
        if (in->permit_tx_readback) {
            p->phase = TEMPER_POLICY_ACTIVE;
        }
    }

    /* Start level tracking is continuous. A high held over reset cannot make
     * a later synthetic edge; a low must be observed before a fresh rise. */
    p->previous_start = in->start_request;

    out->request_permit_low = p->phase == TEMPER_POLICY_WAIT_PERMIT_LOW;
    out->phase = p->phase;

    /* The driver must turn this event into a real WDI falling edge. */
    out->heartbeat_edge_request = session_ready_before_event && p->session_ready && ambient_healthy(in) &&
        in->reset_good && in->accepted_validated_frame &&
        p->phase >= TEMPER_POLICY_WAIT_START_EDGE &&
        (p->phase == TEMPER_POLICY_ACTIVE || !in->permit_tx_readback);
}
