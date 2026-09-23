#include "../main/power_entry_source_runtime.h"

#include <assert.h>
#include <string.h>

typedef struct {
    uint64_t now;
    pe_source_inputs_t inputs;
    bool levels[PE_SOURCE_PIN_COUNT];
    unsigned pulses[PE_SOURCE_PIN_COUNT];
    unsigned cancels;
    pe_frame_t sent[8];
    unsigned sent_count;
    bool queued_tx;
    bool delay_ack_apply;
    bool delay_permit_apply;
    bool fail_start_write;
    bool delay_start_wire;
    bool slow_start_wire;
    bool slow_permit_pulse;
    unsigned event_count;
    unsigned last_wdi_event;
    unsigned ping_send_event;
} fake_io_t;

static uint64_t fake_now(void *context) {
    return ((fake_io_t *)context)->now;
}

static pe_source_inputs_t fake_sample(void *context) {
    return ((fake_io_t *)context)->inputs;
}

static bool fake_set(void *context, pe_source_pin_t pin, bool high) {
    fake_io_t *fake = context;
    fake->levels[pin] = high;
    if (pin == PE_SOURCE_PIN_STOP_N && high && fake->delay_ack_apply) {
        fake->now = 17; /* START deadline after fresh press at 7 ms */
        fake->delay_ack_apply = false;
    }
    if (pin == PE_SOURCE_PIN_STOP_N && high && fake->delay_permit_apply) {
        fake->now = 17;
        fake->delay_permit_apply = false;
    }
    return true;
}

static bool fake_pulse(void *context, pe_source_pin_t pin) {
    fake_io_t *fake = context;
    assert(!fake->levels[pin]);
    ++fake->pulses[pin];
    if (pin == PE_SOURCE_PIN_SEEN_RESET_REQUEST) {
        assert(fake->levels[PE_SOURCE_PIN_CHALLENGE_ACTIVE]);
        fake->inputs.permit_seen_q = false;
    }
    if (pin == PE_SOURCE_PIN_PERMIT_SET_REQUEST) {
        assert(fake->levels[PE_SOURCE_PIN_STOP_N]);
        fake->inputs.local_permit_q = true;
        fake->inputs.hot_permit = true;
        fake->inputs.permit_seen_q = true;
        if (fake->slow_permit_pulse) fake->now = 12;
    }
    if (pin == PE_SOURCE_PIN_WDI_HEARTBEAT) {
        fake->last_wdi_event = ++fake->event_count;
    }
    return true;
}

static bool fake_cancel_tx(void *context) {
    fake_io_t *fake = context;
    ++fake->cancels;
    fake->queued_tx = false;
    return true;
}

static bool fake_send(void *context, const uint8_t *bytes, size_t length) {
    fake_io_t *fake = context;
    pe_frame_t frame;
    assert(pe_frame_decode(bytes, length, &frame));
    assert(fake->levels[PE_SOURCE_PIN_STOP_N] == (frame.type != PE_STOP));
    if (frame.type == PE_PING) {
        fake->ping_send_event = ++fake->event_count;
    }
    if (frame.type == PE_START && fake->fail_start_write) return false;
    assert(fake->sent_count < sizeof(fake->sent) / sizeof(fake->sent[0]));
    fake->sent[fake->sent_count++] = frame;
    if (frame.type == PE_START && fake->delay_start_wire) fake->now = 17;
    if (frame.type == PE_START && fake->slow_start_wire) fake->now = 12;
    return true;
}

static pe_source_runtime_t boot(fake_io_t *fake) {
    pe_source_runtime_t runtime;
    memset(fake, 0, sizeof(*fake));
    for (pe_source_pin_t pin = PE_SOURCE_PIN_STOP_N;
         pin < PE_SOURCE_PIN_COUNT; ++pin) fake->levels[pin] = true;
    fake->inputs.rail_good = true;
    fake->inputs.safety_ok = true;
    pe_source_runtime_io_t io = {
        .context = fake,
        .now_ms = fake_now,
        .sample = fake_sample,
        .set_level = fake_set,
        .pulse = fake_pulse,
        .cancel_uart_tx = fake_cancel_tx,
        .send_frame = fake_send,
        .max_sample_to_start_end_ms = 1,
        .max_sample_to_wdi_ms = 1,
        .max_sample_to_control_pin_ms = 1,
    };
    assert(pe_source_runtime_boot(&runtime, io,
                                  (pe_source_config_t){20, 10, 30}, 5));
    assert(!runtime.io_fault && fake->cancels == 1);
    for (pe_source_pin_t pin = PE_SOURCE_PIN_STOP_N;
         pin < PE_SOURCE_PIN_COUNT; ++pin) assert(!fake->levels[pin]);
    return runtime;
}

static void receive(pe_source_runtime_t *runtime, fake_io_t *fake,
                    pe_frame_t frame, uint64_t now) {
    uint8_t bytes[PE_FRAME_SIZE];
    pe_frame_encode(&frame, bytes);
    fake->now = now;
    for (size_t i = 0; i < sizeof(bytes); ++i) {
        pe_source_runtime_byte(runtime, bytes[i]);
    }
}

static void through_request(pe_source_runtime_t *runtime, fake_io_t *fake) {
    fake->now = 1;
    pe_source_runtime_tick(runtime);
    assert(runtime->source.state == PE_SOURCE_WAIT_CHALLENGE);
    receive(runtime, fake, (pe_frame_t){PE_PREPARE_CHALLENGE, 71, 0}, 2);
    assert(runtime->source.state == PE_SOURCE_SEEN_ARMED);
    assert(fake->levels[PE_SOURCE_PIN_CHALLENGE_ACTIVE]);
    fake->now = 3;
    pe_source_runtime_tick(runtime);
    assert(runtime->source.state == PE_SOURCE_CLEAR_SEEN);
    fake->now = 4;
    pe_source_runtime_tick(runtime);
    assert(runtime->source.state == PE_SOURCE_WAIT_READY);
    assert(fake->pulses[PE_SOURCE_PIN_SEEN_RESET_REQUEST] == 1);
    assert(fake->sent_count == 1 && fake->sent[0].type == PE_DISARM_ACK);
    assert(!fake->levels[PE_SOURCE_PIN_CHALLENGE_ACTIVE]);
    fake->inputs.hot_session_q = true;
    receive(runtime, fake, (pe_frame_t){PE_READY, 71, 0}, 5);
    assert(runtime->source.state == PE_SOURCE_READY);
    fake->now = 6;
    pe_source_runtime_tick(runtime); /* observe button released */
    fake->inputs.start_button_pressed = true;
    fake->now = 7;
    pe_source_runtime_tick(runtime);
    assert(fake->pulses[PE_SOURCE_PIN_PERMIT_SET_REQUEST] == 1);
    fake->now = 8;
    pe_source_runtime_tick(runtime);
    assert(runtime->source.state == PE_SOURCE_WAIT_ACK);
    assert(fake->sent_count == 2 && fake->sent[1].type == PE_REQUEST);
}

static void start_and_restart(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.source.state == PE_SOURCE_START_SENT);
    assert(fake.sent_count == 3 && fake.sent[2].type == PE_START);
    assert(fake.levels[PE_SOURCE_PIN_STOP_N]);

    fake.queued_tx = true; /* cancellation must drain even a stale TX */
    fake.now = 10;
    pe_source_runtime_begin_restart(&runtime);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N] && !fake.queued_tx);
    assert(fake.sent_count == 4 && fake.sent[3].type == PE_STOP);
    assert(!pe_source_runtime_disarmed_for_restart(&runtime));
    fake.inputs.local_permit_q = false;
    fake.inputs.hot_permit = false;
    fake.inputs.hot_session_q = false;
    fake.now = 11;
    assert(pe_source_runtime_disarmed_for_restart(&runtime));
    assert(fake.pulses[PE_SOURCE_PIN_WDI_HEARTBEAT] == 0);
}

static void late_commit_cancels_start(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    fake.delay_ack_apply = true;
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.sent_count == 2 && !fake.levels[PE_SOURCE_PIN_STOP_N]);
    assert(fake.cancels >= 2);
}

static void failed_uart_write_disarms(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    fake.fail_start_write = true;
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.sent_count == 2 && !fake.levels[PE_SOURCE_PIN_STOP_N]);
    assert(fake.cancels >= 2);
}

static void watchdog_edge_precedes_blocking_uart_write(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    pe_source_runtime_local_progress(&runtime, 1);
    assert(pe_source_runtime_ping(&runtime));
    assert(fake.pulses[PE_SOURCE_PIN_WDI_HEARTBEAT] == 1);
    assert(fake.last_wdi_event < fake.ping_send_event);
}

static void delayed_actions_cannot_feed_after_deadline(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    pe_source_runtime_local_progress(&runtime, 1);
    fake.delay_ack_apply = true;
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.pulses[PE_SOURCE_PIN_WDI_HEARTBEAT] == 0);
    assert(fake.sent_count == 2 && !fake.levels[PE_SOURCE_PIN_STOP_N]);
}

static void late_uart_completion_drops_permission(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    fake.delay_start_wire = true;
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.sent_count == 3 && fake.sent[2].type == PE_START);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N]);
}

static void overbound_uart_completion_drops_permission(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    fake.slow_start_wire = true;
    receive(&runtime, &fake,
            (pe_frame_t){PE_ACK, 71, fake.sent[1].value}, 9);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.sent_count == 3 && fake.sent[2].type == PE_START);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N]);
}

static void delayed_permit_write_cannot_rearm(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    fake.now = 1;
    pe_source_runtime_tick(&runtime);
    receive(&runtime, &fake, (pe_frame_t){PE_PREPARE_CHALLENGE, 71, 0}, 2);
    fake.now = 3;
    pe_source_runtime_tick(&runtime);
    fake.now = 4;
    pe_source_runtime_tick(&runtime);
    fake.inputs.hot_session_q = true;
    receive(&runtime, &fake, (pe_frame_t){PE_READY, 71, 0}, 5);
    fake.now = 6;
    pe_source_runtime_tick(&runtime);
    fake.inputs.start_button_pressed = true;
    fake.delay_permit_apply = true;
    fake.now = 7;
    pe_source_runtime_tick(&runtime);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.pulses[PE_SOURCE_PIN_PERMIT_SET_REQUEST] == 0);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N]);
}

static void overbound_control_pulse_disarms(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    fake.now = 1;
    pe_source_runtime_tick(&runtime);
    receive(&runtime, &fake, (pe_frame_t){PE_PREPARE_CHALLENGE, 71, 0}, 2);
    fake.now = 3;
    pe_source_runtime_tick(&runtime);
    fake.now = 4;
    pe_source_runtime_tick(&runtime);
    fake.inputs.hot_session_q = true;
    receive(&runtime, &fake, (pe_frame_t){PE_READY, 71, 0}, 5);
    fake.now = 6;
    pe_source_runtime_tick(&runtime);
    fake.inputs.start_button_pressed = true;
    fake.slow_permit_pulse = true;
    fake.now = 7;
    pe_source_runtime_tick(&runtime);
    assert(runtime.io_fault && runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(fake.pulses[PE_SOURCE_PIN_PERMIT_SET_REQUEST] == 1);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N]);
}

static void serial_error_cancels_pending_write(void) {
    fake_io_t fake;
    pe_source_runtime_t runtime = boot(&fake);
    through_request(&runtime, &fake);
    fake.queued_tx = true;
    pe_source_runtime_serial_error(&runtime);
    assert(runtime.source.state == PE_SOURCE_LOCKOUT);
    assert(!fake.levels[PE_SOURCE_PIN_STOP_N] && !fake.queued_tx);
    assert(fake.sent_count == 3 && fake.sent[2].type == PE_STOP);
}

int main(void) {
    start_and_restart();
    late_commit_cancels_start();
    failed_uart_write_disarms();
    watchdog_edge_precedes_blocking_uart_write();
    delayed_actions_cannot_feed_after_deadline();
    late_uart_completion_drops_permission();
    overbound_uart_completion_drops_permission();
    delayed_permit_write_cannot_rearm();
    overbound_control_pulse_disarms();
    serial_error_cancels_pending_write();
    return 0;
}
