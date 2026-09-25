#include "source_policy.h"
#include <assert.h>
#include <stdio.h>

static temper_policy_outputs_t step(temper_source_policy_t *p,
                                    temper_policy_inputs_t in) {
    temper_policy_outputs_t out;
    temper_source_policy_step(p, &in, &out);
    return out;
}
static temper_policy_inputs_t healthy(void) {
    return (temper_policy_inputs_t){
        .reset_good = true, .rail_good = true, .interlock_good = true,
        .watchdog_good = true
    };
}

static void test_cpu_reset_retained_high_waits_for_physical_low(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.start_request = true; /* retained GPIO high across CPU-only reset */
    in.permit_tx_readback = true;
    in.accepted_validated_frame = true;
    temper_policy_outputs_t out = step(&p, in);
    assert(out.request_permit_low && !out.rearm_pulse);
    assert(!out.heartbeat_edge_request); /* watchdog held until physical low */

    in.reset_event = false;
    for (int i = 0; i < 3; ++i) {
        out = step(&p, in);
        assert(out.request_permit_low && !out.rearm_pulse);
        assert(!out.heartbeat_edge_request);
    }
    in.permit_tx_readback = false;
    out = step(&p, in);
    assert(!out.request_permit_low && !out.rearm_pulse);
    assert(!out.heartbeat_edge_request); /* session still not qualified */
    assert(out.phase == TEMPER_POLICY_WAIT_RESET_GOOD);
    out = step(&p, in);
    assert(out.phase == TEMPER_POLICY_WAIT_START_EDGE);
    assert(!out.heartbeat_edge_request);
    in.new_session_established = true;
    out = step(&p, in);
    assert(!out.heartbeat_edge_request); /* handshake frame is not a heartbeat */
    in.new_session_established = false;
    out = step(&p, in);
    assert(out.heartbeat_edge_request); /* later validated frame */
}

static void test_no_auto_rearm_and_fresh_start_edge_after_release(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.permit_tx_readback = true;
    in.start_request = true;
    (void)step(&p, in);

    in.reset_event = false;
    in.permit_tx_readback = false;
    temper_policy_outputs_t out = step(&p, in);
    assert(!out.rearm_pulse); /* high held through reset is not a fresh edge */
    assert(!out.request_permit_low);
    out = step(&p, in);
    assert(!out.rearm_pulse);

    /* A fresh start edge alone cannot re-arm before a new peer session. */
    in.start_request = false;
    (void)step(&p, in);
    in.start_request = true;
    out = step(&p, in);
    assert(!out.rearm_pulse);

    in.start_request = false; /* observe release */
    out = step(&p, in);
    assert(!out.rearm_pulse);
    in.new_session_established = true;
    out = step(&p, in);
    assert(!out.rearm_pulse);
    in.new_session_established = false;
    in.start_request = true; /* now a fresh low-to-high edge */
    out = step(&p, in);
    assert(out.rearm_pulse && out.phase == TEMPER_POLICY_WAIT_PERMIT_HIGH);
    out = step(&p, in);
    assert(!out.rearm_pulse);
    in.permit_tx_readback = true;
    out = step(&p, in);
    assert(out.phase == TEMPER_POLICY_ACTIVE);
}

static void test_heartbeat_only_on_accepted_frame_event(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.permit_tx_readback = true;
    (void)step(&p, in);
    in.reset_event = false;
    in.permit_tx_readback = false;
    (void)step(&p, in); /* acknowledge low */
    (void)step(&p, in); /* await reset-good feedback */
    in.new_session_established = true;
    (void)step(&p, in); /* fresh session after physical low */
    in.new_session_established = false;
    in.start_request = false;
    (void)step(&p, in); /* release baseline */
    in.start_request = true;
    (void)step(&p, in); /* re-arm */

    in.start_request = false;
    in.accepted_validated_frame = false;
    for (int i = 0; i < 5; ++i)
        assert(!step(&p, in).heartbeat_edge_request);
    in.accepted_validated_frame = true;
    assert(step(&p, in).heartbeat_edge_request);
    in.accepted_validated_frame = false;
    assert(!step(&p, in).heartbeat_edge_request);
}

static void test_health_fault_requires_low_and_fresh_start_again(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.permit_tx_readback = true;
    (void)step(&p, in);
    in.reset_event = false;
    in.permit_tx_readback = false;
    (void)step(&p, in);
    (void)step(&p, in); /* await reset-good feedback */
    in.new_session_established = true;
    (void)step(&p, in);
    in.new_session_established = false;
    in.start_request = false;
    (void)step(&p, in);
    in.start_request = true;
    assert(step(&p, in).rearm_pulse);

    in.start_request = false;
    in.rail_good = false;
    in.permit_tx_readback = true;
    temper_policy_outputs_t out = step(&p, in);
    assert(out.request_permit_low && !out.rearm_pulse && !out.heartbeat_edge_request);
    in.rail_good = true;
    in.permit_tx_readback = false;
    out = step(&p, in);
    assert(!out.rearm_pulse); /* health recovery alone never arms */
    out = step(&p, in);
    assert(out.phase == TEMPER_POLICY_WAIT_START_EDGE);
    in.new_session_established = true;
    (void)step(&p, in);
    in.new_session_established = false;
    in.start_request = true;
    out = step(&p, in);
    assert(out.rearm_pulse);
}

static void test_requested_clear_feedback_and_session_loss(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.reset_good = false; /* firmware is actively commanding clear */
    in.permit_tx_readback = true;
    temper_policy_outputs_t out = step(&p, in);
    assert(out.request_permit_low && !out.heartbeat_edge_request);
    in.reset_event = false;
    in.permit_tx_readback = false;
    out = step(&p, in);
    assert(!out.request_permit_low && out.phase == TEMPER_POLICY_WAIT_RESET_GOOD);
    out = step(&p, in);
    assert(out.phase == TEMPER_POLICY_WAIT_RESET_GOOD && !out.heartbeat_edge_request);
    in.reset_good = true; /* released after physical latch-low observation */
    out = step(&p, in);
    assert(out.phase == TEMPER_POLICY_WAIT_START_EDGE);
    in.new_session_established = true;
    in.accepted_validated_frame = true;
    out = step(&p, in);
    assert(!out.heartbeat_edge_request);
    in.new_session_established = false;
    out = step(&p, in);
    assert(out.heartbeat_edge_request);
    in.session_lost = true;
    out = step(&p, in);
    assert(out.request_permit_low && !out.heartbeat_edge_request);
}

static void test_session_and_start_same_step_cannot_rearm(void) {
    temper_source_policy_t p;
    temper_source_policy_init(&p);
    temper_policy_inputs_t in = healthy();
    in.reset_event = true;
    in.permit_tx_readback = true;
    (void)step(&p, in);
    in.reset_event = false;
    in.permit_tx_readback = false;
    (void)step(&p, in);
    (void)step(&p, in);
    in.start_request = false;
    (void)step(&p, in);
    in.new_session_established = true;
    in.start_request = true;
    in.accepted_validated_frame = true;
    temper_policy_outputs_t out = step(&p, in);
    assert(!out.rearm_pulse && !out.heartbeat_edge_request);
    in.new_session_established = false;
    in.start_request = false;
    (void)step(&p, in);
    in.start_request = true;
    out = step(&p, in);
    assert(out.rearm_pulse);
}

int main(void) {
    test_cpu_reset_retained_high_waits_for_physical_low();
    test_no_auto_rearm_and_fresh_start_edge_after_release();
    test_heartbeat_only_on_accepted_frame_event();
    test_health_fault_requires_low_and_fresh_start_again();
    test_requested_clear_feedback_and_session_loss();
    test_session_and_start_same_step_cannot_rearm();
    puts("PASS: 6 source reset/permit policy tests");
    return 0;
}
