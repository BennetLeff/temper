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
    inputs.disarm_seen = true;
    return inputs;
}

static pe_receiver_t receiver(void) {
    pe_receiver_t rx;
    pe_receiver_config_t config = {10, 10, 20};
    pe_receiver_init(&rx, config);
    return rx;
}

static uint64_t ready(pe_receiver_t *rx, pe_journal_io_t *journal,
                      pe_receiver_inputs_t *inputs, uint64_t at) {
    pe_receiver_actions_t actions;
    assert(pe_receiver_begin(rx, journal, at, *inputs, &actions));
    assert(actions.transmit && actions.frame.type == PE_PREPARE_CHALLENGE);
    assert(!actions.abort_n);
    uint64_t id = actions.frame.session;
    pe_frame_t ack = {PE_DISARM_ACK, id, 0};
    pe_receiver_frame(rx, ack, at + 1, *inputs, &actions);
    assert(actions.abort_n && actions.revalidate_pulse);
    inputs->session_q = true;
    pe_receiver_sample(rx, at + 2, *inputs, &actions);
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
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 7}, 4, inputs, &actions);
    assert(rx.state == PE_RX_START_PENDING && actions.frame.type == PE_ACK);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 7}, 5, inputs, &actions);
    assert(rx.state == PE_RX_RUN_CONFIRM && actions.run_set_pulse);
    inputs.run_q = true;
    pe_receiver_sample(&rx, 6, inputs, &actions);
    assert(rx.state == PE_RX_RUNNING && actions.abort_n);
    pe_receiver_frame(&rx, (pe_frame_t){PE_STOP, id, 0}, 7, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
    inputs = disarmed();
    assert(ready(&rx, &journal, &inputs, 8) > id);
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
    pe_receiver_frame(&rx, (pe_frame_t){PE_REQUEST, id, 11}, 4, inputs, &actions);
    assert(pe_receiver_ping(&rx, 5, inputs, &actions));
    pe_receiver_local_progress(&rx, 1);
    pe_receiver_frame(&rx, (pe_frame_t){PE_PONG, id, 1}, 6, inputs, &actions);
    pe_receiver_sample(&rx, 7, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_receiver_frame(&rx, (pe_frame_t){PE_START, id, 11}, 14, inputs, &actions);
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
    pe_receiver_local_progress(&rx, 1);
    pe_receiver_sample(&rx, 5, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
    assert(pe_receiver_ping(&rx, 6, inputs, &actions));
    pe_receiver_frame(&rx, (pe_frame_t){PE_PONG, id, 1}, 7, inputs, &actions);
    pe_receiver_sample(&rx, 8, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_receiver_sample(&rx, 22, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
    pe_receiver_sample(&rx, 28, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
}

static void preparation_trip_and_reset_are_default_abort(void) {
    memory_t memory;
    provision(&memory);
    pe_journal_io_t journal = journal_for(&memory);
    pe_receiver_t rx = receiver();
    pe_receiver_inputs_t inputs = disarmed();
    pe_receiver_actions_t actions;
    assert(pe_receiver_begin(&rx, &journal, 1, inputs, &actions));
    uint64_t id = actions.frame.session;
    inputs.preparation_abort = true;
    pe_receiver_sample(&rx, 2, inputs, &actions);
    assert(rx.state == PE_RX_LOCKOUT && !actions.abort_n);
    inputs.preparation_abort = false;
    pe_receiver_frame(&rx, (pe_frame_t){PE_DISARM_ACK, id, 0}, 3, inputs, &actions);
    assert(!actions.revalidate_pulse && !actions.abort_n);
    id = ready(&rx, &journal, &inputs, 4);
    pe_receiver_init(&rx, (pe_receiver_config_t){10, 10, 20});
    pe_receiver_sample(&rx, 0, inputs, &actions);
    assert(!actions.abort_n && rx.state == PE_RX_LOCKOUT);
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
    assert(pe_receiver_begin(&rx, &journal, 10, inputs, &actions));
    pe_receiver_sample(&rx, 9, inputs, &actions);
    assert(rx.clock_fault && !actions.abort_n);
    assert(!pe_receiver_begin(&rx, &journal, 11, inputs, &actions));

    pe_receiver_init(&rx, (pe_receiver_config_t){10, 10, 20});
    memory.bytes[31] = 0;
    assert(!pe_receiver_begin(&rx, &journal, 1, inputs, &actions));
    assert(rx.storage_fault && !actions.abort_n);
    assert(!pe_receiver_begin(&rx, &journal, 2, inputs, &actions));
}

int main(void) {
    start_then_stop_requires_new_id();
    deadline_is_fixed_despite_traffic();
    receiver_watchdog_needs_both_progress_sources();
    preparation_trip_and_reset_are_default_abort();
    clock_rollback_and_bad_store_forbid_retry();
    return 0;
}
