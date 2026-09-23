#ifndef TEMPER_POWER_ENTRY_RECEIVER_H
#define TEMPER_POWER_ENTRY_RECEIVER_H

#include "journal.h"
#include "protocol.h"

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    PE_RX_LOCKOUT,
    PE_RX_PREP_RESET,
    PE_RX_RESERVED,
    PE_RX_PREPARING,
    PE_RX_HISTORY_RESET,
    PE_RX_CLEAR_CHECK,
    PE_RX_REVALIDATING,
    PE_RX_READY,
    PE_RX_START_PENDING,
    PE_RX_RUN_CONFIRM,
    PE_RX_RUNNING,
} pe_receiver_state_t;

typedef struct {
    bool rail_good;
    bool fault;             /* physical detector summary, true is unsafe */
    bool physical_permit;   /* HOT conductor after isolation */
    bool session_q;         /* independent retained HOT_SESSION_OK */
    bool run_q;             /* independent retained HOT_RUN */
    bool disarm_seen;       /* physical post-trip low-PERMIT memory */
    bool preparation_abort; /* retained trip while Q was already low */
    bool permit_seen_q;     /* historical high HOT PERMIT memory */
    bool session_clear_n;   /* physical async clear at HOT_SESSION_OK */
} pe_receiver_inputs_t;

typedef struct {
    bool abort_n;           /* continuously driven output; low is safe */
    bool attempt_valid;     /* high during current attempt, low on abort/reset */
    bool prep_reset_pulse;  /* separate history reset before reservation */
    bool history_reset_pulse; /* HOT PERMIT history only, after DISARM_ACK */
    bool revalidate_pulse;  /* one adapter-owned pulse, then return low */
    bool run_set_pulse;     /* one adapter-owned pulse, then return low */
    bool wdi_falling_pulse; /* high then low: TPS3431 services falling edge */
    bool transmit;
    pe_frame_t frame;
} pe_receiver_actions_t;

typedef struct {
    uint32_t prepare_window_ms;
    uint32_t start_window_ms;
    uint32_t watchdog_window_ms;
} pe_receiver_config_t;

typedef struct {
    pe_receiver_state_t state;
    pe_receiver_config_t config;
    uint64_t now_ms;
    uint64_t session;
    uint64_t prepare_deadline_ms;
    uint64_t start_deadline_ms;
    uint64_t last_wdi_ms;
    uint32_t intent;
    uint32_t local_epoch;
    uint32_t local_fed;
    uint32_t link_epoch;
    uint32_t link_fed;
    uint32_t next_ping;
    uint32_t awaiting_pong;
    bool abort_n;
    bool clock_fault;
    bool storage_fault;
} pe_receiver_t;

void pe_receiver_init(pe_receiver_t *receiver, pe_receiver_config_t config);
/* All calls require physical inputs sampled for this call. Invalidity asserts
 * abort in software; independent hardware must clear asynchronously. */
void pe_receiver_sample(pe_receiver_t *receiver, uint64_t now_ms,
                        pe_receiver_inputs_t inputs, pe_receiver_actions_t *actions);
bool pe_receiver_prepare_reset(pe_receiver_t *receiver, uint64_t now_ms,
                               pe_receiver_inputs_t inputs,
                               pe_receiver_actions_t *actions);
bool pe_receiver_reserve(pe_receiver_t *receiver, const pe_journal_io_t *journal,
                         uint64_t now_ms, pe_receiver_inputs_t inputs,
                         pe_receiver_actions_t *actions);
bool pe_receiver_publish(pe_receiver_t *receiver, uint64_t now_ms,
                         pe_receiver_inputs_t inputs,
                         pe_receiver_actions_t *actions);
bool pe_receiver_history_reset_complete(pe_receiver_t *receiver,
                                        uint64_t now_ms,
                                        pe_receiver_inputs_t inputs,
                                        pe_receiver_actions_t *actions);
/* Called only after the adapter has applied abort_n high and taken a fresh
 * physical sample of session_clear_n. It consumes the revalidation edge. */
bool pe_receiver_revalidate(pe_receiver_t *receiver, uint64_t now_ms,
                            pe_receiver_inputs_t inputs,
                            pe_receiver_actions_t *actions);
void pe_receiver_frame(pe_receiver_t *receiver, pe_frame_t frame,
                       uint64_t now_ms, pe_receiver_inputs_t inputs,
                       pe_receiver_actions_t *actions);
void pe_receiver_local_progress(pe_receiver_t *receiver, uint32_t epoch);
bool pe_receiver_ping(pe_receiver_t *receiver, uint64_t now_ms,
                      pe_receiver_inputs_t inputs,
                      pe_receiver_actions_t *actions);

#endif
