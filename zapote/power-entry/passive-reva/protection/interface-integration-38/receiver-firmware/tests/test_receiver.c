#include "../receiver.h"

#include <assert.h>
#include <string.h>

typedef struct { uint8_t bytes[PE_JOURNAL_BYTES]; } memory_t;

static uint8_t read_byte(void *context, uint16_t address) {
    return ((memory_t *)context)->bytes[address];
}

static bool write_byte(void *context, uint16_t address, uint8_t value) {
    ((memory_t *)context)->bytes[address] = value;
    return true;
}

static void provision(memory_t *memory) {
    memset(memory, 0xFF, sizeof(*memory));
    uint8_t *p = memory->bytes;
    p[0] = 'T'; p[1] = 'P'; p[2] = 'E'; p[3] = 1;
    for (unsigned i = 0; i < 8; ++i) p[4 + i] = 0;
    uint32_t crc = pe_crc32(p, 20);
    for (unsigned i = 0; i < 4; ++i) p[20 + i] = (uint8_t)(crc >> (8u * i));
    p[31] = 0x3C;
}

static pe_journal_io_t journal_for(memory_t *memory) {
    pe_journal_io_t io = {memory, read_byte, write_byte};
    return io;
}

static pe_receiver_inputs_t disarmed(void) {
    pe_receiver_inputs_t inputs = {0};
    inputs.rail_good = true;
    return inputs;
}

static pe_receiver_t receiver(void) {
    pe_receiver_t rx;
    pe_receiver_config_t config = {10, 10, 20};
    pe_receiver_init(&rx, config);
    return rx;
}

static void prepare(pe_receiver_t *rx, uint64_t at,
                    pe_receiver_inputs_t *inputs,
                    pe_receiver_actions_t *actions) {
    assert(pe_receiver_begin_disarm(rx, at, *inputs, actions));
    assert(actions->attempt_valid && !actions->abort_n);
    /* The real adapter must apply PA6 high, then take fresh samples before
     * the PF1 clock and another fresh Q sample before the prep reset. */
    assert(pe_receiver_clock_disarm(rx, at, *inputs, actions));
    assert(actions->disarm_sample_pulse && !actions->prep_reset_pulse);
    inputs->disarm_seen = true;
    assert(pe_receiver_prepare_reset(rx, at, *inputs, actions));
    assert(actions->prep_reset_pulse && !actions->disarm_sample_pulse);
}

static uint64_t ready(pe_receiver_t *rx, pe_journal_io_t *journal,
                      pe_receiver_inputs_t *inputs, uint64_t at) {
    pe_receiver_actions_t actions;
    prepare(rx, at, inputs, &actions);
    assert(actions.prep_reset_pulse && !actions.abort_n && actions.attempt_valid);
    inputs->preparation_abort = false;
    assert(pe_receiver_reserve(rx, journal, at + 1, *inputs, &actions));
    assert(!actions.transmit);
    assert(pe_receiver_publish(rx, at + 2, *inputs, &actions));
    assert(actions.transmit && actions.frame.type == PE_PREPARE_CHALLENGE);
    assert(!actions.abort_n);
    uint64_t id = actions.frame.session;
    pe_receiver_local_progress(rx, 1);
    pe_frame_t ack = {PE_DISARM_ACK, id, 0};
    pe_receiver_frame(rx, ack, at + 3, *inputs, &actions);
    assert(!actions.abort_n && actions.history_reset_pulse);
    inputs->permit_seen_q = false;
    pe_receiver_local_progress(rx, 2);
    assert(pe_receiver_history_reset_complete(rx, at + 4, *inputs, &actions));
    assert(actions.abort_n && !actions.revalidate_pulse);
    assert(rx->state == PE_RX_CLEAR_CHECK);
    inputs->session_clear_n = true; /* sampled after applying abort_n high */
    assert(pe_receiver_revalidate(rx, at + 5, *inputs, &actions));
    assert(actions.revalidate_pulse);
    inputs->session_q = true;
    pe_receiver_sample(rx, at + 6, *inputs, &actions);
    assert(rx->state == PE_RX_READY && actions.transmit);
    assert(actions.frame.type == PE_READY && actions.frame.session == id);
    return id;
}

static void start_then_stop_requires_new_id(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    uint64_t id = ready(&rx, &journal, &inputs, 1);
    inputs.physical_permit = true;
    inputs.permit_seen_q = true;
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 7}, 7, inputs, &actions);
    assert(rx.state == PE_RX_START_PENDING && actions.frame.type == PE_ACK);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 7}, 8, inputs, &actions);
    assert(rx.state == PE_RX_START_ARMED && !actions.run_set_pulse);
    assert(pe_receiver_commit_run(&rx, 8, inputs, &actions));
    assert(rx.state == PE_RX_RUN_CONFIRM && actions.run_set_pulse);
    inputs.run_q = true;
    pe_receiver_sample(&rx, 9, inputs, &actions);
    assert(rx.state == PE_RX_RUNNING && actions.abort_n);
    pe_receiver_frame(&rx, (pe_frame_t){PE_STOP, id, 0}, 10, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
    assert(!actions.attempt_valid);
    inputs = disarmed();
    assert(ready(&rx, &journal, &inputs, 11) > id);
}

static void start_must_be_current_at_physical_run_set(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    uint64_t id = ready(&rx, &journal, &inputs, 1);
    inputs.physical_permit = true;
    inputs.permit_seen_q = true;
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 7}, 7, inputs, &actions);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 7}, 8, inputs, &actions);
    assert(rx.state == PE_RX_START_ARMED && !actions.run_set_pulse);
    /* Traffic and local progress do not extend the REQUEST deadline. */
    assert(pe_receiver_ping(&rx, 9, inputs, &actions));
    pe_receiver_local_progress(&rx, 3);
    pe_receiver_frame(&rx, (pe_frame_t){PE_PONG, id, 1}, 10, inputs, &actions);
    assert(!pe_receiver_commit_run(&rx, 17, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.run_set_pulse);

    inputs = disarmed();
    id = ready(&rx, &journal, &inputs, 18);
    inputs.physical_permit = true;
    inputs.permit_seen_q = true;
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 8}, 24, inputs, &actions);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 8}, 25, inputs, &actions);
    inputs.fault = true; /* changed after frame receipt, before pin write */
    assert(!pe_receiver_commit_run(&rx, 26, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.run_set_pulse);
}

static void deadline_is_fixed_despite_traffic(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    uint64_t id = ready(&rx, &journal, &inputs, 1);
    inputs.physical_permit = true;
    inputs.permit_seen_q = true;
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 11}, 7, inputs, &actions);
    assert(pe_receiver_ping(&rx, 8, inputs, &actions));
    pe_receiver_local_progress(&rx, 3);
    pe_receiver_frame(&rx, (pe_frame_t){PE_PONG, id, 1}, 9, inputs, &actions);
    pe_receiver_sample(&rx, 10, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 11}, 17, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.run_set_pulse);
    assert(!actions.abort_n);
}

static void receiver_watchdog_needs_both_progress_sources(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    uint64_t id = ready(&rx, &journal, &inputs, 1);
    pe_receiver_local_progress(&rx, 3);
    pe_receiver_sample(&rx, 7, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
    assert(pe_receiver_ping(&rx, 8, inputs, &actions));
    pe_receiver_frame(&rx, (pe_frame_t){PE_PONG, id, 1}, 9, inputs, &actions);
    pe_receiver_sample(&rx, 10, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_receiver_sample(&rx, 25, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
    pe_receiver_sample(&rx, 30, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
    assert(!actions.attempt_valid);
}

static void preparation_trip_and_reset_are_default_abort(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    prepare(&rx, 1, &inputs, &actions);
    assert(pe_receiver_reserve(&rx, &journal, 2, inputs, &actions));
    assert(pe_receiver_publish(&rx, 3, inputs, &actions));
    uint64_t id = actions.frame.session;
    inputs.preparation_abort = true;
    pe_receiver_sample(&rx, 4, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
    inputs.preparation_abort = false;
    inputs.disarm_seen = false;
    pe_receiver_frame(&rx, (pe_frame_t){PE_DISARM_ACK, id, 0}, 5, inputs, &actions);
    assert(!actions.revalidate_pulse && !actions.abort_n);
    id = ready(&rx, &journal, &inputs, 6);
    pe_receiver_init(&rx, (pe_receiver_config_t){10, 10, 20});
    pe_receiver_sample(&rx, 0, inputs, &actions);
    assert(!actions.abort_n && !actions.attempt_valid && rx.state == PE_RX_LOCKOUT);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 7}, 1, inputs, &actions);
    assert(!actions.run_set_pulse);
}

static void clock_rollback_and_bad_store_forbid_retry(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    prepare(&rx, 10, &inputs, &actions);
    pe_receiver_sample(&rx, 9, inputs, &actions);
    assert(rx.clock_fault && !actions.abort_n);
    assert(!pe_receiver_prepare_reset(&rx, 11, inputs, &actions));

    pe_receiver_init(&rx, (pe_receiver_config_t){10, 10, 20});
    inputs.disarm_seen = false;
    memory.bytes[31] = 0;
    prepare(&rx, 1, &inputs, &actions);
    assert(!pe_receiver_reserve(&rx, &journal, 2, inputs, &actions));
    assert(rx.storage_fault && !actions.abort_n);
    assert(!pe_receiver_prepare_reset(&rx, 3, inputs, &actions));
}

static void trip_during_reservation_or_history_reset_cannot_publish_ready(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    prepare(&rx, 1, &inputs, &actions);
    assert(pe_receiver_reserve(&rx, &journal, 2, inputs, &actions));
    inputs.preparation_abort = true;
    assert(!pe_receiver_publish(&rx, 3, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.transmit);

    inputs.preparation_abort = false;
    inputs.disarm_seen = false;
    prepare(&rx, 4, &inputs, &actions);
    assert(pe_receiver_reserve(&rx, &journal, 5, inputs, &actions));
    assert(pe_receiver_publish(&rx, 6, inputs, &actions));
    uint64_t id = actions.frame.session;
    pe_receiver_local_progress(&rx, 1);
    pe_receiver_frame(&rx, (pe_frame_t){PE_DISARM_ACK, id, 0}, 7,
                      inputs, &actions);
    assert(actions.history_reset_pulse && !actions.revalidate_pulse);
    inputs.preparation_abort = true;
    assert(!pe_receiver_history_reset_complete(&rx, 8, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.revalidate_pulse);
}

static void clear_must_be_observed_after_abort_release(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    prepare(&rx, 1, &inputs, &actions);
    assert(pe_receiver_reserve(&rx, &journal, 2, inputs, &actions));
    assert(pe_receiver_publish(&rx, 3, inputs, &actions));
    uint64_t id = actions.frame.session;
    pe_receiver_local_progress(&rx, 1);
    pe_receiver_frame(&rx, (pe_frame_t){PE_DISARM_ACK, id, 0}, 4, inputs, &actions);
    assert(actions.history_reset_pulse);
    pe_receiver_local_progress(&rx, 2);
    assert(pe_receiver_history_reset_complete(&rx, 5, inputs, &actions));
    assert(actions.abort_n && !actions.revalidate_pulse);
    assert(!pe_receiver_revalidate(&rx, 6, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);

    inputs = disarmed();
    prepare(&rx, 7, &inputs, &actions);
    assert(pe_receiver_reserve(&rx, &journal, 8, inputs, &actions));
    assert(pe_receiver_publish(&rx, 9, inputs, &actions));
    id = actions.frame.session;
    pe_receiver_local_progress(&rx, 3);
    pe_receiver_frame(&rx, (pe_frame_t){PE_DISARM_ACK, id, 0}, 10, inputs, &actions);
    pe_receiver_local_progress(&rx, 4);
    assert(pe_receiver_history_reset_complete(&rx, 11, inputs, &actions));
    inputs.session_clear_n = true;
    inputs.preparation_abort = true;
    assert(!pe_receiver_revalidate(&rx, 12, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.revalidate_pulse);
}

static void stop_during_preparation_drops_attempt_valid(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    prepare(&rx, 1, &inputs, &actions);
    assert(actions.attempt_valid && !actions.abort_n);
    assert(pe_receiver_reserve(&rx, &journal, 2, inputs, &actions));
    assert(actions.attempt_valid);
    assert(pe_receiver_publish(&rx, 3, inputs, &actions));
    assert(actions.attempt_valid && actions.transmit);
    pe_receiver_frame(&rx, (pe_frame_t){PE_STOP, rx.session, 0}, 4,
                      inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.attempt_valid &&
           !actions.abort_n && !actions.prep_reset_pulse);
}

static void disarm_requires_post_arm_physical_q(void) {
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    inputs.disarm_seen = true; /* stale pre-trip observation cannot arm */
    assert(!pe_receiver_begin_disarm(&rx, 1, inputs, &actions));
    assert(!actions.attempt_valid && rx.state == PE_RX_LOCKOUT);

    inputs.disarm_seen = false;
    assert(pe_receiver_begin_disarm(&rx, 2, inputs, &actions));
    assert(actions.attempt_valid && !actions.disarm_sample_pulse);
    assert(pe_receiver_clock_disarm(&rx, 3, inputs, &actions));
    assert(actions.disarm_sample_pulse && !actions.prep_reset_pulse);
    assert(!pe_receiver_clock_disarm(&rx, 3, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.attempt_valid);

    assert(pe_receiver_begin_disarm(&rx, 4, inputs, &actions));
    assert(pe_receiver_clock_disarm(&rx, 5, inputs, &actions));
    assert(!pe_receiver_prepare_reset(&rx, 6, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.attempt_valid);

    assert(pe_receiver_begin_disarm(&rx, 7, inputs, &actions));
    assert(pe_receiver_clock_disarm(&rx, 8, inputs, &actions));
    inputs.disarm_seen = true;
    inputs.fault = true;
    assert(!pe_receiver_prepare_reset(&rx, 9, inputs, &actions));
    assert(rx.state == PE_RX_LOCKOUT && !actions.attempt_valid);
}

int main(void) {
    start_then_stop_requires_new_id();
    start_must_be_current_at_physical_run_set();
    deadline_is_fixed_despite_traffic();
    receiver_watchdog_needs_both_progress_sources();
    preparation_trip_and_reset_are_default_abort();
    clock_rollback_and_bad_store_forbid_retry();
    trip_during_reservation_or_history_reset_cannot_publish_ready();
    clear_must_be_observed_after_abort_release();
    stop_during_preparation_drops_attempt_valid();
    disarm_requires_post_arm_physical_q();
    return 0;
}
