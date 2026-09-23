#include "runtime.h"

#include <limits.h>
#include <string.h>

static void io_abort(pe_runtime_t *runtime) {
    runtime->io_fault = true;
    runtime->receiver.state = PE_RX_LOCKOUT;
    runtime->receiver.abort_n = false;
    runtime->receiver.storage_fault = true;
    for (pe_output_pin_t pin = PE_PIN_ABORT_N; pin < PE_PIN_COUNT; ++pin) {
        (void)runtime->io.set_level(runtime->io.context, pin, false);
    }
}

static bool apply(pe_runtime_t *runtime, pe_receiver_actions_t actions) {
    void *context = runtime->io.context;
    if (!actions.abort_n &&
        !runtime->io.set_level(context, PE_PIN_ABORT_N, false)) goto fault;
    if (!actions.attempt_valid &&
        !runtime->io.set_level(context, PE_PIN_ATTEMPT_VALID, false)) goto fault;
    if (actions.attempt_valid &&
        !runtime->io.set_level(context, PE_PIN_ATTEMPT_VALID, true)) goto fault;
    if (actions.abort_n &&
        !runtime->io.set_level(context, PE_PIN_ABORT_N, true)) goto fault;
    if (actions.disarm_sample_pulse &&
        !runtime->io.pulse(context, PE_PIN_DISARM_SAMPLE)) goto fault;
    if (actions.prep_reset_pulse &&
        !runtime->io.pulse(context, PE_PIN_PREP_RESET)) goto fault;
    if (actions.history_reset_pulse &&
        !runtime->io.pulse(context, PE_PIN_HISTORY_RESET)) goto fault;
    if (actions.revalidate_pulse &&
        !runtime->io.pulse(context, PE_PIN_REVALIDATE)) goto fault;
    if (actions.run_set_pulse) goto fault; /* only commit_run owns this edge */
    if (actions.wdi_falling_pulse &&
        !runtime->io.pulse(context, PE_PIN_WDI)) goto fault;
    if (actions.transmit) {
        uint8_t bytes[PE_FRAME_SIZE];
        pe_frame_encode(&actions.frame, bytes);
        if (!runtime->io.transmit(context, bytes, sizeof(bytes))) goto fault;
    }
    return true;
fault:
    io_abort(runtime);
    return false;
}

bool pe_runtime_boot(pe_runtime_t *runtime, pe_runtime_io_t io,
                     pe_receiver_config_t config, uint32_t max_byte_gap_ms) {
    memset(runtime, 0, sizeof(*runtime));
    runtime->io = io;
    if (io.set_level == NULL) {
        runtime->io_fault = true;
        return false;
    }
    for (pe_output_pin_t pin = PE_PIN_ABORT_N; pin < PE_PIN_COUNT; ++pin) {
        if (!io.set_level(io.context, pin, false)) {
            runtime->io_fault = true;
            return false;
        }
    }
    pe_receiver_init(&runtime->receiver, config);
    pe_stream_init(&runtime->stream, max_byte_gap_ms);
    if (io.now_ms == NULL || io.sample == NULL || io.pulse == NULL ||
        io.transmit == NULL || io.journal == NULL ||
        io.max_sample_to_run_pin_ms == 0 || max_byte_gap_ms == 0) {
        io_abort(runtime);
        return false;
    }
    return true;
}

static void step(pe_runtime_t *runtime) {
    pe_receiver_t *receiver = &runtime->receiver;
    pe_receiver_actions_t actions;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    switch (receiver->state) {
    case PE_RX_LOCKOUT:
        (void)pe_receiver_begin_disarm(receiver, now, inputs, &actions);
        break;
    case PE_RX_DISARM_ARMED:
        (void)pe_receiver_clock_disarm(receiver, now, inputs, &actions);
        break;
    case PE_RX_DISARM_SAMPLED:
        (void)pe_receiver_prepare_reset(receiver, now, inputs, &actions);
        break;
    case PE_RX_PREP_RESET:
        (void)pe_receiver_reserve(receiver, runtime->io.journal, now,
                                  inputs, &actions);
        break;
    case PE_RX_RESERVED:
        (void)pe_receiver_publish(receiver, now, inputs, &actions);
        break;
    case PE_RX_HISTORY_RESET:
        (void)pe_receiver_history_reset_complete(receiver, now, inputs,
                                                 &actions);
        break;
    case PE_RX_CLEAR_CHECK:
        (void)pe_receiver_revalidate(receiver, now, inputs, &actions);
        break;
    default:
        pe_receiver_sample(receiver, now, inputs, &actions);
        break;
    }
    (void)apply(runtime, actions);
}

static void cancel_attempt(pe_runtime_t *runtime) {
    pe_receiver_actions_t actions;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    pe_receiver_frame(&runtime->receiver,
                      (pe_frame_t){PE_ABORT, 0, 0}, now, inputs, &actions);
    (void)apply(runtime, actions);
}

static void commit_run(pe_runtime_t *runtime) {
    pe_receiver_t *receiver = &runtime->receiver;
    pe_receiver_actions_t actions;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    uint64_t bound = runtime->io.max_sample_to_run_pin_ms;
    if (now > UINT64_MAX - bound ||
        now + bound >= receiver->start_deadline_ms) {
        cancel_attempt(runtime);
        return;
    }
    if (!pe_receiver_commit_run(receiver, now, inputs, &actions)) {
        (void)apply(runtime, actions);
        return;
    }
    /* Sample again after the state transition. The independent asynchronous
     * clear path must still dominate a trip coincident with the raw edge. */
    now = runtime->io.now_ms(runtime->io.context);
    inputs = runtime->io.sample(runtime->io.context);
    pe_receiver_actions_t checked;
    pe_receiver_sample(receiver, now, inputs, &checked);
    if (receiver->state != PE_RX_RUN_CONFIRM ||
        now > UINT64_MAX - bound ||
        now + bound >= receiver->start_deadline_ms ||
        !checked.abort_n) {
        cancel_attempt(runtime);
        return;
    }
    /* Apply the final pulse without a queue. Target evidence must bound the
     * callback's entry latency and prove its low-high-low electrical edge. */
    bool wdi = actions.wdi_falling_pulse || checked.wdi_falling_pulse;
    checked.wdi_falling_pulse = false;
    actions.wdi_falling_pulse = false;
    if (!apply(runtime, checked)) return;
    /* Applying the checked outputs is itself a target callback and may
     * consume the remaining START window. Recheck after it, before RUN. */
    inputs = runtime->io.sample(runtime->io.context);
    now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_sample(receiver, now, inputs, &checked);
    wdi = wdi || checked.wdi_falling_pulse;
    if (receiver->state != PE_RX_RUN_CONFIRM ||
        now > UINT64_MAX - bound ||
        now + bound >= receiver->start_deadline_ms ||
        !checked.abort_n) {
        cancel_attempt(runtime);
        return;
    }
    if (!runtime->io.pulse(runtime->io.context, PE_PIN_RUN_SET)) {
        io_abort(runtime);
        return;
    }
    if (wdi && !runtime->io.pulse(runtime->io.context, PE_PIN_WDI)) {
        io_abort(runtime);
    }
}

void pe_runtime_tick(pe_runtime_t *runtime) {
    if (runtime->io_fault) return;
    pe_receiver_actions_t actions;
    bool was_active = runtime->receiver.state != PE_RX_LOCKOUT;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    pe_receiver_stream_idle(&runtime->receiver, &runtime->stream,
                            now, inputs, &actions);
    if (!apply(runtime, actions) ||
        (was_active && runtime->receiver.state == PE_RX_LOCKOUT)) {
        return;
    }
    if (runtime->receiver.state == PE_RX_START_ARMED) {
        commit_run(runtime);
    } else {
        step(runtime);
    }
}

void pe_runtime_byte(pe_runtime_t *runtime, uint8_t byte) {
    if (runtime->io_fault) return;
    pe_receiver_actions_t actions;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    pe_receiver_byte(&runtime->receiver, &runtime->stream, byte,
                     now, inputs, &actions);
    (void)apply(runtime, actions);
}

void pe_runtime_serial_error(pe_runtime_t *runtime) {
    if (runtime->io_fault) return;
    cancel_attempt(runtime);
    pe_stream_init(&runtime->stream, runtime->stream.max_gap_ms);
}

void pe_runtime_local_progress(pe_runtime_t *runtime, uint32_t epoch) {
    if (!runtime->io_fault) pe_receiver_local_progress(&runtime->receiver, epoch);
}

bool pe_runtime_ping(pe_runtime_t *runtime) {
    if (runtime->io_fault) return false;
    pe_receiver_actions_t actions;
    uint64_t now = runtime->io.now_ms(runtime->io.context);
    pe_receiver_inputs_t inputs = runtime->io.sample(runtime->io.context);
    if (!pe_receiver_ping(&runtime->receiver, now, inputs, &actions)) {
        (void)apply(runtime, actions);
        return false;
    }
    return apply(runtime, actions);
}
