#include "../runtime.h"

#include <assert.h>
#include <string.h>

typedef struct {
    uint8_t bytes[PE_JOURNAL_BYTES];
    uint64_t now;
    pe_receiver_inputs_t inputs;
    bool pins[PE_PIN_COUNT];
    unsigned run_pulses;
    unsigned wdi_pulses;
    uint8_t transmitted[PE_FRAME_SIZE];
    unsigned transmissions;
    unsigned delay_on_abort_high_call;
    uint64_t delayed_time;
    unsigned delay_on_sample_call;
    bool hot_latches_powered;
} fixture_t;

static uint8_t read_byte(void *context, uint16_t address) {
    return ((fixture_t *)context)->bytes[address];
}

static bool write_byte(void *context, uint16_t address, uint8_t value) {
    ((fixture_t *)context)->bytes[address] = value;
    return true;
}

static uint64_t now_ms(void *context) { return ((fixture_t *)context)->now; }

static pe_receiver_inputs_t sample(void *context) {
    fixture_t *fixture = context;
    if (fixture->delay_on_sample_call != 0 &&
        --fixture->delay_on_sample_call == 0) fixture->now = fixture->delayed_time;
    return fixture->inputs;
}

static bool set_level(void *context, pe_output_pin_t pin, bool high) {
    fixture_t *fixture = context;
    fixture->pins[pin] = high;
    if (pin == PE_PIN_ABORT_N && high &&
        fixture->delay_on_abort_high_call != 0 &&
        --fixture->delay_on_abort_high_call == 0) {
        fixture->now = fixture->delayed_time;
    }
    if (pin == PE_PIN_ABORT_N) {
        fixture->inputs.session_clear_n = high;
        if (!high && fixture->hot_latches_powered) {
            /* Model the independent asynchronous clear while HOT stays on. */
            fixture->inputs.session_q = false;
            fixture->inputs.run_q = false;
        }
    }
    return true;
}

static bool pulse(void *context, pe_output_pin_t pin) {
    fixture_t *fixture = context;
    assert(!fixture->pins[pin]);
    if (pin == PE_PIN_DISARM_SAMPLE) {
        assert(fixture->pins[PE_PIN_ATTEMPT_VALID]);
        fixture->inputs.disarm_seen = true;
    } else if (pin == PE_PIN_HISTORY_RESET) {
        fixture->inputs.permit_seen_q = false;
    } else if (pin == PE_PIN_REVALIDATE) {
        assert(fixture->pins[PE_PIN_ABORT_N]);
        fixture->inputs.session_q = true;
    } else if (pin == PE_PIN_RUN_SET) {
        assert(fixture->inputs.physical_permit);
        ++fixture->run_pulses;
        fixture->inputs.run_q = true;
    } else if (pin == PE_PIN_WDI) {
        ++fixture->wdi_pulses;
    }
    return true;
}

static bool transmit(void *context, const uint8_t *bytes, size_t length) {
    fixture_t *fixture = context;
    assert(length == PE_FRAME_SIZE);
    memcpy(fixture->transmitted, bytes, length);
    ++fixture->transmissions;
    return true;
}

static void provision(fixture_t *fixture) {
    memset(fixture, 0, sizeof(*fixture));
    memset(fixture->bytes, 0xFF, sizeof(fixture->bytes));
    uint8_t *p = fixture->bytes;
    p[0] = 'T'; p[1] = 'P'; p[2] = 'E'; p[3] = 1;
    for (unsigned i = 0; i < 8; ++i) p[4 + i] = 0;
    uint32_t crc = pe_crc32(p, 20);
    for (unsigned i = 0; i < 4; ++i) p[20 + i] = (uint8_t)(crc >> (8u * i));
    p[31] = 0x3C;
    fixture->inputs.rail_good = true;
}

static void send_frame(pe_runtime_t *runtime, fixture_t *fixture,
                       pe_frame_t frame, uint64_t at) {
    uint8_t bytes[PE_FRAME_SIZE];
    pe_frame_encode(&frame, bytes);
    fixture->now = at;
    for (size_t i = 0; i < PE_FRAME_SIZE; ++i) {
        pe_runtime_byte(runtime, bytes[i]);
    }
}

static uint64_t prepare_ready(pe_runtime_t *runtime, fixture_t *fixture,
                              pe_journal_io_t *journal) {
    pe_runtime_io_t io = {fixture, now_ms, sample, set_level, pulse,
                          transmit, journal, 1};
    assert(pe_runtime_boot(runtime, io,
                           (pe_receiver_config_t){10, 10, 100}, 5));
    for (unsigned pin = 0; pin < PE_PIN_COUNT; ++pin) {
        assert(!fixture->pins[pin]);
    }
    for (uint64_t at = 1; at <= 5; ++at) {
        fixture->now = at;
        pe_runtime_tick(runtime);
    }
    assert(fixture->transmissions == 1);
    pe_frame_t challenge;
    assert(pe_frame_decode(fixture->transmitted, PE_FRAME_SIZE, &challenge));
    assert(challenge.type == PE_PREPARE_CHALLENGE);
    pe_receiver_local_progress(&runtime->receiver, 1);
    send_frame(runtime, fixture,
               (pe_frame_t){PE_DISARM_ACK, challenge.session, 0}, 6);
    pe_receiver_local_progress(&runtime->receiver, 2);
    for (uint64_t at = 7; at <= 9; ++at) {
        fixture->now = at;
        pe_runtime_tick(runtime);
    }
    assert(runtime->receiver.state == PE_RX_READY);
    assert(fixture->pins[PE_PIN_ABORT_N]);
    return challenge.session;
}

static void accepted_start_has_one_synchronous_run_edge(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    uint64_t id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = true;
    fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 7}, 10);
    assert(runtime.receiver.state == PE_RX_START_PENDING);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 7}, 11);
    assert(runtime.receiver.state == PE_RX_START_ARMED);
    assert(fixture.run_pulses == 0);
    fixture.now = 12;
    pe_runtime_tick(&runtime);
    assert(fixture.run_pulses == 1);
    assert(runtime.receiver.state == PE_RX_RUN_CONFIRM);
    fixture.now = 13;
    pe_runtime_tick(&runtime);
    assert(runtime.receiver.state == PE_RX_RUNNING);
}

static void stop_in_ready_before_permit_high_drives_abort_low(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    uint64_t id = prepare_ready(&runtime, &fixture, &journal);
    assert(!fixture.inputs.physical_permit && !fixture.inputs.permit_seen_q);
    assert(fixture.pins[PE_PIN_ABORT_N]);

    send_frame(&runtime, &fixture, (pe_frame_t){PE_STOP, id, 0}, 10);
    assert(runtime.receiver.state == PE_RX_LOCKOUT);
    assert(!fixture.pins[PE_PIN_ABORT_N] &&
           !fixture.pins[PE_PIN_ATTEMPT_VALID]);
    assert(fixture.run_pulses == 0);

    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 1}, 11);
    assert(runtime.receiver.state == PE_RX_LOCKOUT);
    assert(!fixture.pins[PE_PIN_ABORT_N] && fixture.run_pulses == 0);
}

static void receiver_reset_in_run_clears_powered_hot_latches(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    uint64_t id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 7}, 10);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 7}, 11);
    fixture.now = 12;
    pe_runtime_tick(&runtime);
    fixture.now = 13;
    pe_runtime_tick(&runtime);
    assert(runtime.receiver.state == PE_RX_RUNNING);
    assert(fixture.pins[PE_PIN_ABORT_N] && fixture.inputs.session_q &&
           fixture.inputs.run_q && fixture.inputs.physical_permit);
    assert(fixture.run_pulses == 1);

    /* Reboot only the receiver; retain HOT power and high physical PERMIT. */
    fixture.hot_latches_powered = true;
    pe_runtime_t rebooted;
    pe_runtime_io_t io = {&fixture, now_ms, sample, set_level, pulse,
                          transmit, &journal, 1};
    fixture.now = 14;
    assert(pe_runtime_boot(&rebooted, io,
                           (pe_receiver_config_t){10, 10, 100}, 5));
    assert(fixture.hot_latches_powered && fixture.inputs.physical_permit);
    assert(!fixture.pins[PE_PIN_ABORT_N] &&
           !fixture.pins[PE_PIN_ATTEMPT_VALID]);
    assert(!fixture.inputs.session_q && !fixture.inputs.run_q);
    assert(rebooted.receiver.state == PE_RX_LOCKOUT);

    fixture.now = 15;
    pe_runtime_tick(&rebooted);
    send_frame(&rebooted, &fixture, (pe_frame_t){PE_START, id, 7}, 16);
    assert(rebooted.receiver.state == PE_RX_LOCKOUT);
    assert(!fixture.pins[PE_PIN_ABORT_N] && fixture.run_pulses == 1);
}

static void delayed_or_faulted_commit_never_pulses_run(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    uint64_t id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 7}, 10);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 7}, 11);
    fixture.now = 19; /* deadline 20; one-tick output bound needs slack */
    pe_runtime_tick(&runtime);
    assert(fixture.run_pulses == 0 && !fixture.pins[PE_PIN_ABORT_N]);

    provision(&fixture);
    runtime = (pe_runtime_t){0};
    id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 8}, 10);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 8}, 11);
    fixture.inputs.fault = true;
    fixture.now = 12;
    pe_runtime_tick(&runtime);
    assert(fixture.run_pulses == 0 && !fixture.pins[PE_PIN_ABORT_N]);

    provision(&fixture);
    runtime = (pe_runtime_t){0};
    id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 9}, 10);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 9}, 11);
    fixture.delay_on_abort_high_call = 2;
    fixture.delayed_time = 20; /* second output callback crosses deadline */
    fixture.now = 12;
    pe_runtime_tick(&runtime);
    assert(fixture.run_pulses == 0 && !fixture.pins[PE_PIN_ABORT_N]);

    provision(&fixture);
    runtime = (pe_runtime_t){0};
    id = prepare_ready(&runtime, &fixture, &journal);
    fixture.inputs.physical_permit = fixture.inputs.permit_seen_q = true;
    send_frame(&runtime, &fixture, (pe_frame_t){PE_REQUEST, id, 10}, 10);
    send_frame(&runtime, &fixture, (pe_frame_t){PE_START, id, 10}, 11);
    fixture.delay_on_sample_call = 4;
    fixture.delayed_time = 20; /* final input callback crosses deadline */
    fixture.now = 12;
    pe_runtime_tick(&runtime);
    assert(fixture.run_pulses == 0 && !fixture.pins[PE_PIN_ABORT_N]);
}

static void idle_decoder_timeout_reaches_abort_pin(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    (void)prepare_ready(&runtime, &fixture, &journal);
    fixture.now = 10;
    pe_runtime_byte(&runtime, PE_FRAME_MAGIC);
    assert(fixture.pins[PE_PIN_ABORT_N]);
    fixture.now = 16; /* five-tick byte gap exceeded with no next byte */
    pe_runtime_tick(&runtime);
    assert(runtime.receiver.state == PE_RX_LOCKOUT);
    assert(!fixture.pins[PE_PIN_ABORT_N] && !fixture.pins[PE_PIN_ATTEMPT_VALID]);
    assert(fixture.run_pulses == 0);
}

static void usart_error_reaches_abort_pin(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    (void)prepare_ready(&runtime, &fixture, &journal);
    fixture.now = 10;
    pe_runtime_serial_error(&runtime);
    assert(runtime.receiver.state == PE_RX_LOCKOUT);
    assert(!fixture.pins[PE_PIN_ABORT_N] && !fixture.pins[PE_PIN_ATTEMPT_VALID]);
}

static void watchdog_needs_local_and_matching_link_progress(void) {
    fixture_t fixture;
    provision(&fixture);
    pe_journal_io_t journal = {&fixture, read_byte, write_byte};
    pe_runtime_t runtime;
    uint64_t id = prepare_ready(&runtime, &fixture, &journal);
    fixture.now = 10;
    assert(pe_runtime_ping(&runtime));
    pe_frame_t ping;
    assert(pe_frame_decode(fixture.transmitted, PE_FRAME_SIZE, &ping));
    assert(ping.type == PE_PING && ping.session == id);
    assert(fixture.wdi_pulses == 0);
    pe_runtime_local_progress(&runtime, 3);
    fixture.now = 11;
    pe_runtime_tick(&runtime);
    assert(fixture.wdi_pulses == 0);
    send_frame(&runtime, &fixture,
               (pe_frame_t){PE_PONG, id, ping.value}, 12);
    fixture.now = 13;
    pe_runtime_tick(&runtime);
    assert(fixture.wdi_pulses == 1);
    fixture.now = 14;
    pe_runtime_tick(&runtime);
    assert(fixture.wdi_pulses == 1);
}

int main(void) {
    accepted_start_has_one_synchronous_run_edge();
    stop_in_ready_before_permit_high_drives_abort_low();
    receiver_reset_in_run_clears_powered_hot_latches();
    delayed_or_faulted_commit_never_pulses_run();
    idle_decoder_timeout_reaches_abort_pin();
    usart_error_reaches_abort_pin();
    watchdog_needs_local_and_matching_link_progress();
    return 0;
}
