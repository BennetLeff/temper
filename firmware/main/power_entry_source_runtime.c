#include "power_entry_source_runtime.h"

#include <string.h>

static void io_abort(pe_source_runtime_t *runtime) {
    pe_source_actions_t ignored;
    runtime->io_fault = true;
    pe_source_stop(&runtime->source, &ignored);
    if (runtime->io.set_level != NULL) {
        (void)runtime->io.set_level(runtime->io.context, PE_SOURCE_PIN_STOP_N,
                                    false);
    }
    if (runtime->io.cancel_uart_tx != NULL) {
        (void)runtime->io.cancel_uart_tx(runtime->io.context);
    }
    if (runtime->io.set_level != NULL) {
        for (pe_source_pin_t pin = PE_SOURCE_PIN_CHALLENGE_ACTIVE;
             pin < PE_SOURCE_PIN_WDI_HEARTBEAT; ++pin) {
            (void)runtime->io.set_level(runtime->io.context, pin, false);
        }
    }
}

static bool within_sample_bound(pe_source_runtime_t *runtime,
                                uint32_t bound_ms) {
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    return now >= runtime->source.now_ms &&
           now - runtime->source.now_ms <= bound_ms;
}

static bool current_control_sample(pe_source_runtime_t *runtime,
                                   bool reset_seen) {
    if (!within_sample_bound(runtime,
                             runtime->io.max_sample_to_control_pin_ms)) return false;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) return false;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    if (!within_sample_bound(runtime,
                             runtime->io.max_sample_to_control_pin_ms) ||
        now >= runtime->source.deadline_ms ||
        runtime->source.deadline_ms - now <=
            runtime->io.max_sample_to_control_pin_ms) return false;
    /* Reserve the entire target-verified sample-to-edge bound before the
     * positive pulse edge. A post-edge check can detect a late request but
     * cannot retract it. The adapter still has to meet its promised bound. */
    if (!inputs.rail_good || !inputs.safety_ok ||
        inputs.local_permit_q || inputs.hot_permit) return false;
    if (reset_seen) {
        return runtime->source.state == PE_SOURCE_CLEAR_SEEN &&
               !inputs.hot_session_q;
    }
    return runtime->source.state == PE_SOURCE_PERMIT_PENDING &&
           inputs.hot_session_q && !inputs.permit_seen_q;
}

static bool apply(pe_source_runtime_t *runtime, pe_source_actions_t actions) {
    void *context = runtime->io.context;
    if (!actions.stop_n) {
        if (!runtime->io.set_level(context, PE_SOURCE_PIN_STOP_N, false) ||
            !runtime->io.cancel_uart_tx(context)) goto fault;
    }
    if (!runtime->io.set_level(context, PE_SOURCE_PIN_CHALLENGE_ACTIVE,
                               actions.challenge_active)) goto fault;
    if (actions.stop_n &&
        !runtime->io.set_level(context, PE_SOURCE_PIN_STOP_N, true)) goto fault;
    if (actions.seen_reset_pulse &&
        (!current_control_sample(runtime, true) ||
         !runtime->io.pulse(context, PE_SOURCE_PIN_SEEN_RESET_REQUEST) ||
         !within_sample_bound(runtime,
                              runtime->io.max_sample_to_control_pin_ms))) goto fault;
    if (actions.permit_set_pulse &&
        (!current_control_sample(runtime, false) ||
         !runtime->io.pulse(context, PE_SOURCE_PIN_PERMIT_SET_REQUEST) ||
         !within_sample_bound(runtime,
                              runtime->io.max_sample_to_control_pin_ms))) goto fault;
    /* Never leave a WDI action pending behind a blocking UART write. */
    if (actions.wdi_falling_pulse) {
        uint64_t now = runtime->io.now_ms(context);
        if (!within_sample_bound(runtime,
                                 runtime->io.max_sample_to_wdi_ms) ||
            (runtime->source.state >= PE_SOURCE_SEEN_ARMED &&
             runtime->source.state <= PE_SOURCE_START_ARMED &&
             runtime->source.state != PE_SOURCE_READY &&
             (now >= runtime->source.deadline_ms ||
              runtime->source.deadline_ms - now <=
                  runtime->io.max_sample_to_wdi_ms)) ||
            !runtime->io.pulse(context, PE_SOURCE_PIN_WDI_HEARTBEAT) ||
            !within_sample_bound(runtime,
                                 runtime->io.max_sample_to_wdi_ms)) goto fault;
    }
    if (actions.transmit) {
        uint8_t bytes[PE_FRAME_SIZE];
        pe_frame_encode(&actions.frame, bytes);
        if (!runtime->io.send_frame(context, bytes, sizeof(bytes))) goto fault;
        /* The receiver independently rejects late START. This catches an
         * adapter that violated its promised complete-frame bound and drops
         * source permission rather than continuing the session. */
        if (actions.frame.type == PE_START &&
            (runtime->io.now_ms(context) >= runtime->source.deadline_ms ||
             !within_sample_bound(runtime,
                                  runtime->io.max_sample_to_start_end_ms))) goto fault;
    }
    return true;
fault:
    io_abort(runtime);
    return false;
}

bool pe_source_runtime_boot(pe_source_runtime_t *runtime,
                            pe_source_runtime_io_t io,
                            pe_source_config_t config,
                            uint32_t max_byte_gap_ms) {
    memset(runtime, 0, sizeof(*runtime));
    runtime->io = io;
    if (io.set_level == NULL) {
        runtime->io_fault = true;
        return false;
    }
    /* A CPU-only reset may retain the WDI pad high. Writing it low here
     * would be a qualifying falling watchdog edge before disarm. The target
     * adapter must leave WDI untouched until a requested pulse is permitted
     * after a fresh physical disarm sample. */
    for (pe_source_pin_t pin = PE_SOURCE_PIN_STOP_N;
         pin < PE_SOURCE_PIN_WDI_HEARTBEAT; ++pin) {
        if (!io.set_level(io.context, pin, false)) {
            io_abort(runtime);
            return false;
        }
    }
    if (io.now_ms == NULL || io.sample == NULL || io.pulse == NULL ||
        io.cancel_uart_tx == NULL || io.send_frame == NULL ||
        io.max_sample_to_start_end_ms == 0 ||
        io.max_sample_to_wdi_ms == 0 ||
        io.max_sample_to_control_pin_ms == 0 || max_byte_gap_ms == 0 ||
        !io.cancel_uart_tx(io.context)) {
        io_abort(runtime);
        return false;
    }
    pe_source_init(&runtime->source, config);
    pe_stream_init(&runtime->stream, max_byte_gap_ms);
    return true;
}

static void advance_preparation(pe_source_runtime_t *runtime) {
    pe_source_actions_t actions;
    if (runtime->source.state == PE_SOURCE_SEEN_ARMED) {
        pe_source_inputs_t inputs;
        if (!runtime->io.sample(runtime->io.context, &inputs)) {
            io_abort(runtime);
            return;
        }
        uint64_t now = runtime->io.now_ms(runtime->io.context);
        (void)pe_source_clock_seen_reset(&runtime->source, now, inputs,
                                         &actions);
        (void)apply(runtime, actions);
    } else if (runtime->source.state == PE_SOURCE_CLEAR_SEEN) {
        pe_source_inputs_t inputs;
        if (!runtime->io.sample(runtime->io.context, &inputs)) {
            io_abort(runtime);
            return;
        }
        uint64_t now = runtime->io.now_ms(runtime->io.context);
        (void)pe_source_confirm_seen_reset(&runtime->source, now, inputs,
                                           &actions);
        (void)apply(runtime, actions);
    }
}

static void commit_start(pe_source_runtime_t *runtime) {
    pe_source_actions_t actions;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) {
        io_abort(runtime);
        return;
    }
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    (void)pe_source_commit_start(&runtime->source, now,
                                 runtime->io.max_sample_to_start_end_ms,
                                 inputs, &actions);
    (void)apply(runtime, actions);
}

void pe_source_runtime_tick(pe_source_runtime_t *runtime) {
    if (runtime->io_fault) return;
    pe_source_actions_t actions;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) {
        io_abort(runtime);
        return;
    }
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_source_stream_idle(&runtime->source, &runtime->stream, now, inputs,
                          &actions);
    if (!apply(runtime, actions)) return;
    advance_preparation(runtime);
    if (!runtime->io_fault && runtime->source.state == PE_SOURCE_START_ARMED) {
        commit_start(runtime);
    }
}

void pe_source_runtime_byte(pe_source_runtime_t *runtime, uint8_t byte) {
    if (runtime->io_fault) return;
    pe_source_actions_t actions;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) {
        io_abort(runtime);
        return;
    }
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_source_byte(&runtime->source, &runtime->stream, byte, now, inputs,
                   &actions);
    if (!apply(runtime, actions)) return;
    if (!runtime->io_fault && runtime->source.state == PE_SOURCE_START_ARMED) {
        commit_start(runtime);
    }
}

void pe_source_runtime_serial_error(pe_source_runtime_t *runtime) {
    if (runtime->io_fault) return;
    pe_source_runtime_stop(runtime);
    pe_stream_init(&runtime->stream, runtime->stream.max_gap_ms);
}

void pe_source_runtime_local_progress(pe_source_runtime_t *runtime,
                                      uint64_t control_epoch,
                                      uint64_t monitor_epoch) {
    if (runtime->io_fault) return;
    if (!runtime->progress_baselined) {
        runtime->progress_baselined = true;
        runtime->control_observed = control_epoch;
        runtime->monitor_observed = monitor_epoch;
        runtime->control_credited = control_epoch;
        runtime->monitor_credited = monitor_epoch;
        return;
    }
    if (control_epoch < runtime->control_observed ||
        monitor_epoch < runtime->monitor_observed) {
        io_abort(runtime);
        return;
    }
    runtime->control_observed = control_epoch;
    runtime->monitor_observed = monitor_epoch;
    if (control_epoch <= runtime->control_credited ||
        monitor_epoch <= runtime->monitor_credited) return;
    if (runtime->paired_progress_epoch == UINT64_MAX) {
        io_abort(runtime);
        return;
    }
    runtime->control_credited = control_epoch;
    runtime->monitor_credited = monitor_epoch;
    pe_source_local_progress(&runtime->source,
                             ++runtime->paired_progress_epoch);
}

bool pe_source_runtime_ping(pe_source_runtime_t *runtime) {
    if (runtime->io_fault) return false;
    pe_source_actions_t actions;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) {
        io_abort(runtime);
        return false;
    }
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    bool requested = pe_source_ping(&runtime->source, now, inputs, &actions);
    return apply(runtime, actions) && requested;
}

void pe_source_runtime_stop(pe_source_runtime_t *runtime) {
    if (runtime->io_fault) return;
    pe_source_actions_t actions;
    pe_source_stop(&runtime->source, &actions);
    (void)apply(runtime, actions);
}

void pe_source_runtime_begin_restart(pe_source_runtime_t *runtime) {
    if (runtime->io_fault) return;
    pe_source_actions_t actions;
    pe_source_begin_deliberate_restart(&runtime->source, &actions);
    (void)apply(runtime, actions);
}

bool pe_source_runtime_disarmed_for_restart(pe_source_runtime_t *runtime) {
    if (runtime->io_fault || !runtime->source.restart_requested) return false;
    pe_source_actions_t actions;
    pe_source_inputs_t inputs;
    if (!runtime->io.sample(runtime->io.context, &inputs)) {
        io_abort(runtime);
        return false;
    }
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_source_sample(&runtime->source, now, inputs, &actions);
    if (!apply(runtime, actions)) return false;
    return pe_source_disarmed_for_restart(&runtime->source, inputs);
}
