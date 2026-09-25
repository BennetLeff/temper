#ifndef TEMPER_SOURCE_POLICY_H
#define TEMPER_SOURCE_POLICY_H

#include <stdbool.h>

/* Prototype contract only. Caller must provide trusted reset, health, physical
 * PERMIT_TX readback, and already-validated frame events. This module has no
 * transport parser, ESP GPIO driver, timing source, or product safety claim.
 */
typedef enum {
    TEMPER_POLICY_WAIT_PERMIT_LOW = 0,
    TEMPER_POLICY_WAIT_RESET_GOOD,
    TEMPER_POLICY_WAIT_START_EDGE,
    TEMPER_POLICY_WAIT_PERMIT_HIGH,
    TEMPER_POLICY_ACTIVE
} temper_policy_phase_t;

typedef struct {
    temper_policy_phase_t phase;
    bool initialized;
    bool start_was_low;
    bool previous_start;
    bool session_ready;
} temper_source_policy_t;

typedef struct {
    /* One-call event: true on boot/reset, including CPU-only reset. */
    bool reset_event;
    bool reset_good;
    bool rail_good;
    bool interlock_good;
    bool watchdog_good;
    /* Must be a physical observation of source latch Q1/PERMIT_TX. */
    bool permit_tx_readback;
    bool start_request;
    /* One-call event from a new handshake completed after this reset. */
    bool new_session_established;
    bool session_lost;
    /* One-call event, emitted only after in-session frame validation. */
    bool accepted_validated_frame;
} temper_policy_inputs_t;

typedef struct {
    /* Asserted continuously until the input readback confirms low. */
    bool request_permit_low;
    /* One-call edge to source latch; never repeated while start stays high. */
    bool rearm_pulse;
    /* Request for one WDI falling edge; driver owns actual high/low timing. */
    bool heartbeat_edge_request;
    temper_policy_phase_t phase;
} temper_policy_outputs_t;

void temper_source_policy_init(temper_source_policy_t *policy);
void temper_source_policy_step(temper_source_policy_t *policy,
                               const temper_policy_inputs_t *inputs,
                               temper_policy_outputs_t *outputs);

#endif
