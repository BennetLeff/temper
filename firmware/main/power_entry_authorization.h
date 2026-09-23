#ifndef TEMPER_POWER_ENTRY_AUTHORIZATION_H
#define TEMPER_POWER_ENTRY_AUTHORIZATION_H

#include "../../zapote/power-entry/passive-reva/protection/interface-integration-38/receiver-firmware/protocol.h"

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    PE_SOURCE_LOCKOUT,
    PE_SOURCE_WAIT_CHALLENGE,
    PE_SOURCE_SEEN_ARMED,
    PE_SOURCE_CLEAR_SEEN,
    PE_SOURCE_WAIT_READY,
    PE_SOURCE_READY,
    PE_SOURCE_PERMIT_PENDING,
    PE_SOURCE_WAIT_ACK,
    PE_SOURCE_START_SENT,
    PE_SOURCE_RESTART_DISARM,
} pe_source_state_t;

typedef struct {
    bool rail_good;          /* source rail supervisor, independent of WDO */
    bool safety_ok;          /* interlocks excluding TPS3431 WDO */
    bool local_permit_q;
    bool hot_permit;
    bool hot_session_q;
    bool permit_seen_q;
    bool start_button_pressed;
} pe_source_inputs_t;

typedef struct {
    bool stop_n;
    bool challenge_active;
    bool seen_reset_pulse;
    bool permit_set_pulse;
    bool wdi_falling_pulse;
    bool transmit;
    pe_frame_t frame;
} pe_source_actions_t;

typedef struct {
    uint32_t prepare_window_ms;
    uint32_t start_window_ms;
    uint32_t watchdog_window_ms;
} pe_source_config_t;

typedef struct {
    pe_source_state_t state;
    pe_source_config_t config;
    uint64_t now_ms;
    uint64_t deadline_ms;
    uint64_t last_wdi_ms;
    uint64_t session;
    uint64_t last_session;
    uint32_t intent;
    uint32_t next_intent;
    uint32_t next_ping;
    uint32_t awaiting_pong;
    uint32_t last_peer_ping;
    uint32_t local_epoch;
    uint32_t local_fed;
    uint32_t link_epoch;
    uint32_t link_fed;
    bool button_released;
    bool local_permit_seen;
    bool hot_permit_seen;
    bool clock_fault;
    bool restart_requested;
    bool restart_disarm_confirmed;
} pe_source_t;

/* Boot must configure external pins to their safe levels before this core
 * can be used. In particular, no source TPS3431 WDI owner exists on boot. */
void pe_source_init(pe_source_t *source, pe_source_config_t config);
void pe_source_sample(pe_source_t *source, uint64_t now_ms,
                      pe_source_inputs_t inputs, pe_source_actions_t *actions);
void pe_source_frame(pe_source_t *source, pe_frame_t frame, uint64_t now_ms,
                     pe_source_inputs_t inputs, pe_source_actions_t *actions);
void pe_source_byte(pe_source_t *source, pe_stream_t *stream, uint8_t byte,
                    uint64_t now_ms, pe_source_inputs_t inputs,
                    pe_source_actions_t *actions);
void pe_source_stream_idle(pe_source_t *source, pe_stream_t *stream,
                           uint64_t now_ms, pe_source_inputs_t inputs,
                           pe_source_actions_t *actions);
/* Apply challenge_active high, then take a fresh physical sample before
 * requesting the raw reset edge. */
bool pe_source_clock_seen_reset(pe_source_t *source, uint64_t now_ms,
                                 pe_source_inputs_t inputs,
                                 pe_source_actions_t *actions);
/* Call only after applying the reset edge and resampling physical Q. */
bool pe_source_confirm_seen_reset(pe_source_t *source, uint64_t now_ms,
                                   pe_source_inputs_t inputs,
                                   pe_source_actions_t *actions);
void pe_source_local_progress(pe_source_t *source, uint32_t epoch);
bool pe_source_ping(pe_source_t *source, uint64_t now_ms,
                    pe_source_inputs_t inputs, pe_source_actions_t *actions);
void pe_source_stop(pe_source_t *source, pe_source_actions_t *actions);
/* Begin deliberate restart: keep STOP asserted, then take a later physical
 * sample before asking ESP-IDF to restart. This state never requests WDI. */
void pe_source_begin_deliberate_restart(pe_source_t *source,
                                        pe_source_actions_t *actions);
bool pe_source_disarmed_for_restart(const pe_source_t *source,
                                    pe_source_inputs_t inputs);

#endif
