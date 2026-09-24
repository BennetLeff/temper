#include "../main/power_entry_authorization.h"

#include <assert.h>

static pe_source_inputs_t safe_disarm(void) {
    pe_source_inputs_t inputs = {0};
    inputs.rail_good = true;
    inputs.safety_ok = true;
    return inputs;
}

static pe_source_t source(void) {
    pe_source_t src;
    pe_source_init(&src, (pe_source_config_t){20, 10, 30});
    return src;
}

static uint64_t ready(pe_source_t *src, pe_source_inputs_t *inputs) {
    pe_source_actions_t actions;
    pe_source_sample(src, 1, *inputs, &actions);
    assert(src->state == PE_SOURCE_WAIT_CHALLENGE && actions.stop_n);
    assert(!actions.wdi_falling_pulse);
    pe_source_frame(src, (pe_frame_t){PE_PREPARE_CHALLENGE, 71, 0},
                    2, *inputs, &actions);
    assert(src->state == PE_SOURCE_SEEN_ARMED);
    assert(actions.challenge_active && !actions.seen_reset_pulse);
    assert(!actions.transmit);
    assert(pe_source_clock_seen_reset(src, 3, *inputs, &actions));
    assert(actions.challenge_active && actions.seen_reset_pulse);
    /* Applying the pulse and taking a fresh physical Q sample is required. */
    assert(pe_source_confirm_seen_reset(src, 4, *inputs, &actions));
    assert(actions.transmit && actions.frame.type == PE_DISARM_ACK);
    assert(!actions.challenge_active);
    inputs->hot_session_q = true;
    pe_source_frame(src, (pe_frame_t){PE_READY, 71, 0}, 5, *inputs, &actions);
    assert(src->state == PE_SOURCE_READY && actions.stop_n);
    return 71;
}

static void held_button_and_reset_cannot_replay_start(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    uint64_t id = ready(&src, &inputs);
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 5, inputs, &actions);
    assert(src.state == PE_SOURCE_READY && !actions.permit_set_pulse);
    inputs.start_button_pressed = false;
    pe_source_sample(&src, 6, inputs, &actions);
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions);
    assert(src.state == PE_SOURCE_PERMIT_PENDING && actions.permit_set_pulse);
    assert(!actions.transmit);
    inputs.local_permit_q = true;
    inputs.hot_permit = true;
    pe_source_sample(&src, 8, inputs, &actions);
    assert(src.state == PE_SOURCE_WAIT_ACK && actions.transmit);
    assert(actions.frame.type == PE_REQUEST && actions.frame.session == id);
    uint32_t intent = actions.frame.value;
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 9,
                    inputs, &actions);
    assert(src.state == PE_SOURCE_START_ARMED && !actions.transmit);
    inputs.permit_seen_q = true; /* physical async preset after HOT PERMIT */
    assert(pe_source_commit_start(&src, 10, 1, inputs, &actions));
    assert(src.state == PE_SOURCE_START_SENT && actions.transmit);
    assert(actions.frame.type == PE_START && actions.frame.value == intent);
    assert(!pe_source_commit_start(&src, 11, 1, inputs, &actions));
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.transmit);
    pe_source_init(&src, (pe_source_config_t){20, 10, 30});
    pe_source_sample(&src, 0, inputs, &actions); /* retained GPIO/Q at reset */
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.stop_n);
    assert(!actions.transmit && !actions.wdi_falling_pulse);
    assert(!pe_source_disarmed_for_restart(&src, inputs));
}

static void fixed_start_deadline_and_duplicate_ack_abort(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    uint64_t id = ready(&src, &inputs);
    pe_source_sample(&src, 5, inputs, &actions); /* button released */
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions);
    inputs.local_permit_q = true;
    inputs.hot_permit = true;
    pe_source_sample(&src, 8, inputs, &actions);
    uint32_t intent = actions.frame.value;
    pe_source_frame(&src, (pe_frame_t){PE_PING, id, 1}, 9, inputs, &actions);
    assert(actions.transmit && actions.frame.type == PE_PONG);
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 17,
                    inputs, &actions);
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.stop_n);
    assert(!actions.transmit);

    src = source();
    inputs = safe_disarm();
    id = ready(&src, &inputs);
    pe_source_sample(&src, 5, inputs, &actions);
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions);
    inputs.local_permit_q = inputs.hot_permit = true;
    pe_source_sample(&src, 8, inputs, &actions);
    intent = actions.frame.value;
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 9,
                    inputs, &actions);
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 10,
                    inputs, &actions);
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.stop_n);
    assert(!actions.transmit);
}

static void delayed_or_unreadable_start_never_transmits(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    uint64_t id = ready(&src, &inputs);
    pe_source_sample(&src, 6, inputs, &actions); /* fresh release */
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions); /* deadline 17 */
    inputs.local_permit_q = inputs.hot_permit = inputs.permit_seen_q = true;
    pe_source_sample(&src, 8, inputs, &actions);
    uint32_t intent = actions.frame.value;
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 9,
                    inputs, &actions);
    assert(src.state == PE_SOURCE_START_ARMED && !actions.transmit);
    assert(!pe_source_commit_start(&src, 16, 1, inputs, &actions));
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.transmit);

    src = source();
    inputs = safe_disarm();
    id = ready(&src, &inputs);
    pe_source_sample(&src, 6, inputs, &actions);
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions);
    inputs.local_permit_q = inputs.hot_permit = inputs.permit_seen_q = true;
    pe_source_sample(&src, 8, inputs, &actions);
    intent = actions.frame.value;
    pe_source_frame(&src, (pe_frame_t){PE_ACK, id, intent}, 9,
                    inputs, &actions);
    inputs.hot_permit = false; /* physical readback lost after ACK */
    assert(!pe_source_commit_start(&src, 10, 1, inputs, &actions));
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.transmit);
}

static void wdi_requires_local_and_link_progress_after_preparation(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    uint64_t id = ready(&src, &inputs);
    pe_source_local_progress(&src, 1);
    pe_source_sample(&src, 5, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_source_local_progress(&src, 2);
    pe_source_sample(&src, 6, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
    assert(pe_source_ping(&src, 7, inputs, &actions));
    assert(actions.frame.type == PE_PING);
    pe_source_frame(&src, (pe_frame_t){PE_PONG, id, actions.frame.value},
                    8, inputs, &actions);
    pe_source_sample(&src, 9, inputs, &actions);
    assert(actions.wdi_falling_pulse);
    pe_source_sample(&src, 10, inputs, &actions);
    assert(!actions.wdi_falling_pulse);
}

static void stale_seen_memory_is_cleared_during_new_challenge(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    inputs.permit_seen_q = true; /* retained from the previous session */
    pe_source_sample(&src, 1, inputs, &actions);
    assert(src.state == PE_SOURCE_WAIT_CHALLENGE && actions.stop_n);
    pe_source_frame(&src, (pe_frame_t){PE_PREPARE_CHALLENGE, 72, 0},
                    2, inputs, &actions);
    assert(src.state == PE_SOURCE_SEEN_ARMED && !actions.seen_reset_pulse);
    assert(pe_source_clock_seen_reset(&src, 3, inputs, &actions));
    assert(!pe_source_confirm_seen_reset(&src, 4, inputs, &actions));
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.transmit);

    pe_source_sample(&src, 5, inputs, &actions);
    pe_source_frame(&src, (pe_frame_t){PE_PREPARE_CHALLENGE, 72, 0},
                    6, inputs, &actions);
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.seen_reset_pulse);
    pe_source_sample(&src, 7, inputs, &actions);
    pe_source_frame(&src, (pe_frame_t){PE_PREPARE_CHALLENGE, 73, 0},
                    8, inputs, &actions);
    assert(pe_source_clock_seen_reset(&src, 9, inputs, &actions));
    inputs.permit_seen_q = false; /* fresh physical Q sample after edge */
    assert(pe_source_confirm_seen_reset(&src, 10, inputs, &actions));
    assert(actions.transmit && actions.frame.type == PE_DISARM_ACK);
}

static void brief_local_permit_loss_aborts_before_request(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    ready(&src, &inputs);
    pe_source_sample(&src, 6, inputs, &actions); /* released button */
    inputs.start_button_pressed = true;
    pe_source_sample(&src, 7, inputs, &actions);
    assert(actions.permit_set_pulse);
    inputs.local_permit_q = true;
    pe_source_sample(&src, 8, inputs, &actions);
    assert(src.state == PE_SOURCE_PERMIT_PENDING && !actions.transmit);
    inputs.local_permit_q = false;
    pe_source_sample(&src, 9, inputs, &actions);
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.stop_n);
    assert(!actions.transmit);
}

static void malformed_response_aborts_authorization(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    uint64_t id = ready(&src, &inputs);
    pe_stream_t stream;
    pe_stream_init(&stream, 5);
    uint8_t bytes[PE_FRAME_SIZE];
    pe_frame_encode(&(pe_frame_t){PE_PING, id, 1}, bytes);
    bytes[6] ^= 1u;
    for (size_t i = 0; i < PE_FRAME_SIZE; ++i) {
        pe_source_byte(&src, &stream, bytes[i], i + 6, inputs, &actions);
    }
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.stop_n);
    assert(!actions.wdi_falling_pulse);
}

static void first_wdi_waits_for_physical_disarm(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    inputs.local_permit_q = true; /* retained source output at CPU reset */
    pe_source_local_progress(&src, 1);
    pe_source_sample(&src, 1, inputs, &actions);
    assert(src.state == PE_SOURCE_LOCKOUT && !actions.wdi_falling_pulse);
    inputs.local_permit_q = false;
    pe_source_sample(&src, 2, inputs, &actions);
    assert(src.state == PE_SOURCE_WAIT_CHALLENGE && !actions.wdi_falling_pulse);
    pe_source_local_progress(&src, 2);
    pe_source_sample(&src, 3, inputs, &actions);
    assert(actions.wdi_falling_pulse);
}

static void deliberate_restart_waits_for_later_disarm_sample(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    ready(&src, &inputs);
    pe_source_begin_deliberate_restart(&src, &actions);
    assert(src.state == PE_SOURCE_RESTART_DISARM && !actions.stop_n);
    assert(actions.transmit && actions.frame.type == PE_STOP);
    assert(!pe_source_disarmed_for_restart(&src, inputs));
    pe_source_sample(&src, 6, inputs, &actions);
    assert(!actions.stop_n && !actions.wdi_falling_pulse);
    assert(!pe_source_disarmed_for_restart(&src, inputs));
    inputs.hot_session_q = false; /* read after retained clear */
    pe_source_sample(&src, 7, inputs, &actions);
    assert(!actions.stop_n && !actions.wdi_falling_pulse);
    assert(pe_source_disarmed_for_restart(&src, inputs));
    pe_source_frame(&src, (pe_frame_t){PE_READY, 71, 0}, 8,
                    inputs, &actions);
    assert(src.state == PE_SOURCE_RESTART_DISARM && !actions.transmit);
    pe_stream_t stream;
    pe_stream_init(&stream, 2);
    pe_source_byte(&src, &stream, PE_FRAME_MAGIC, 9, inputs, &actions);
    pe_source_stream_idle(&src, &stream, 12, inputs, &actions);
    pe_source_sample(&src, 13, inputs, &actions);
    assert(src.state == PE_SOURCE_RESTART_DISARM && !actions.stop_n);
    assert(!actions.wdi_falling_pulse && !actions.transmit);
}

static void cooker_fault_latch_reset_needs_physical_disarm(void) {
    pe_source_t src = source();
    pe_source_inputs_t inputs = safe_disarm();
    pe_source_actions_t actions;
    ready(&src, &inputs);
    pe_source_begin_deliberate_restart(&src, &actions);
    inputs.safety_ok = false; /* cooker interlock is latched low */
    assert(!pe_source_cooker_latch_reset_eligible(&src, inputs));
    inputs.hot_session_q = true;
    pe_source_sample(&src, 6, inputs, &actions);
    assert(!actions.stop_n);
    assert(!pe_source_cooker_latch_reset_eligible(&src, inputs));
    inputs.hot_session_q = false;
    inputs.hot_permit = true;
    pe_source_sample(&src, 7, inputs, &actions);
    assert(!pe_source_cooker_latch_reset_eligible(&src, inputs));
    inputs.hot_permit = false;
    inputs.local_permit_q = true;
    pe_source_sample(&src, 8, inputs, &actions);
    assert(!pe_source_cooker_latch_reset_eligible(&src, inputs));
    inputs.local_permit_q = false;
    inputs.rail_good = false;
    pe_source_sample(&src, 9, inputs, &actions);
    assert(!pe_source_cooker_latch_reset_eligible(&src, inputs));
    inputs.rail_good = true;
    pe_source_sample(&src, 10, inputs, &actions);
    assert(pe_source_cooker_latch_reset_eligible(&src, inputs));
    assert(!pe_source_disarmed_for_restart(&src, inputs));
    assert(!actions.stop_n && !actions.wdi_falling_pulse &&
           !actions.permit_set_pulse && !actions.seen_reset_pulse);
    inputs.safety_ok = true; /* verified only after a later physical reset */
    assert(!pe_source_disarmed_for_restart(&src, inputs));
    pe_source_sample(&src, 11, inputs, &actions);
    assert(pe_source_disarmed_for_restart(&src, inputs));
}

int main(void) {
    held_button_and_reset_cannot_replay_start();
    fixed_start_deadline_and_duplicate_ack_abort();
    wdi_requires_local_and_link_progress_after_preparation();
    stale_seen_memory_is_cleared_during_new_challenge();
    brief_local_permit_loss_aborts_before_request();
    malformed_response_aborts_authorization();
    first_wdi_waits_for_physical_disarm();
    deliberate_restart_waits_for_later_disarm_sample();
    cooker_fault_latch_reset_needs_physical_disarm();
    delayed_or_unreadable_start_never_transmits();
    return 0;
}
