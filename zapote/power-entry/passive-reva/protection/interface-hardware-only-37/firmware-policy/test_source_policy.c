#include "source_policy.h"

#include <assert.h>
#include <stdio.h>

static temper_esp_outputs_t step(temper_esp_policy_t *policy,
                                 temper_esp_inputs_t in) {
    temper_esp_outputs_t out;
    temper_esp_policy_step(policy, &in, &out);
    return out;
}

static temper_esp_inputs_t healthy(void) {
    return (temper_esp_inputs_t){
        .hot_health_raw = true,
        .watchdog_good = true,
        .hot_permit_readback = false
    };
}

static void enter_start_wait(temper_esp_policy_t *p,
                             temper_esp_inputs_t *in) {
    in->reset_event = true;
    in->permit_tx_readback = true;
    temper_esp_outputs_t out = step(p, *in);
    assert(!out.permit_tx_high_request && !out.arm_high_request);
    assert(!out.hot_rearm_high_request && !out.wdi_falling_edge_request);

    in->reset_event = false;
    in->permit_tx_readback = false;
    in->hot_permit_readback = false;
    in->fresh_local_cycle_event = false;
    out = step(p, *in);
    assert(out.phase == TEMPER_ESP_WAIT_BUTTON_RELEASE);
    in->start_button = false;
    out = step(p, *in);
    assert(out.phase == TEMPER_ESP_SOURCE_SESSION_RESET_STEP);
    assert(!out.source_session_reset_low_request);
    out = step(p, *in);
    assert(out.phase == TEMPER_ESP_WAIT_START_PRESS);
    assert(out.source_session_reset_low_request);
    out = step(p, *in);
    assert(!out.source_session_reset_low_request);
}

static void test_reset_holds_outputs_low_until_physical_permit_low(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    in.reset_event = true;
    in.start_button = true; /* held across a CPU-only reset */
    in.permit_tx_readback = true;
    in.fresh_local_cycle_event = true;
    for (int i = 0; i < 4; ++i) {
        temper_esp_outputs_t out = step(&p, in);
        assert(!out.permit_tx_high_request && !out.arm_high_request);
        assert(!out.hot_rearm_high_request && !out.wdi_falling_edge_request);
        in.reset_event = false;
    }
    in.fresh_local_cycle_event = false;
    in.permit_tx_readback = false;
    temper_esp_outputs_t out = step(&p, in);
    assert(!out.wdi_falling_edge_request && !out.hot_rearm_high_request);
    assert(out.phase == TEMPER_ESP_WAIT_BUTTON_RELEASE);
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_BUTTON_RELEASE);
    in.start_button = false;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_SOURCE_SESSION_RESET_STEP);
    assert(!out.source_session_reset_low_request);
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_START_PRESS);
    assert(out.source_session_reset_low_request);
    out = step(&p, in);
    assert(!out.source_session_reset_low_request);
    assert(!out.wdi_falling_edge_request);
}

static void test_reset_event_cannot_feed_wdi_on_same_step(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    in.reset_event = true;
    in.fresh_local_cycle_event = true;
    /* Both readbacks already low formerly allowed this reset call to
     * advance startup and request a watchdog edge. */
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
    assert(!out.permit_tx_high_request && !out.arm_high_request);
    assert(!out.hot_rearm_high_request && !out.wdi_falling_edge_request);
    assert(!out.source_session_reset_low_request);
}

static void test_fresh_press_orders_permit_delay_rearm_then_arm(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);

    in.start_button = true;
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);
    assert(out.permit_tx_high_request);
    assert(!out.hot_rearm_high_request && !out.arm_high_request);

    in.start_button = false;
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    in.fresh_local_cycle_event = true;
    /* Model one policy cycle per millisecond: this keeps the source watchdog
     * fed through 250 ms, beyond its cited 145 ms corner, during HOT blanking. */
    for (int elapsed_ms = 0; elapsed_ms < 250; ++elapsed_ms) {
        out = step(&p, in);
        assert(out.permit_tx_high_request);
        assert(!out.hot_rearm_high_request && !out.arm_high_request);
        assert(out.wdi_falling_edge_request);
    }
    in.hot_permit_delay_elapsed = true;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_REARM_PULSE_STEP);
    assert(out.permit_tx_high_request);
    assert(!out.hot_rearm_high_request && !out.arm_high_request);

    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_ARM_STEP);
    assert(out.permit_tx_high_request && out.hot_rearm_high_request);
    assert(!out.arm_high_request);

    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_ACTIVE);
    assert(out.arm_high_request && !out.hot_rearm_high_request);
    assert(out.permit_tx_high_request);
}

static void test_health_permit_or_watchdog_loss_aborts_and_requires_press(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    (void)step(&p, in);
    in.hot_permit_delay_elapsed = true;
    (void)step(&p, in);
    (void)step(&p, in); /* one rearm step */
    temper_esp_outputs_t out = step(&p, in); /* arm */
    assert(out.arm_high_request);

    in.watchdog_good = false;
    in.fresh_local_cycle_event = true;
    out = step(&p, in);
    assert(!out.permit_tx_high_request && !out.arm_high_request);
    assert(!out.hot_rearm_high_request && !out.wdi_falling_edge_request);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);

    in.watchdog_good = true;
    in.permit_tx_readback = false;
    in.hot_permit_readback = false;
    in.start_button = true; /* button remains held */
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_BUTTON_RELEASE);
    in.start_button = false;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_SOURCE_SESSION_RESET_STEP);
    out = step(&p, in);
    assert(out.source_session_reset_low_request);
    out = step(&p, in);
    assert(!out.source_session_reset_low_request);
    in.start_button = true; /* only a new press can begin */
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);

    in.hot_health_raw = false;
    out = step(&p, in);
    assert(!out.permit_tx_high_request && !out.arm_high_request);
    assert(!out.hot_rearm_high_request && !out.wdi_falling_edge_request);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
}

static void test_watchdog_recovers_only_after_physical_permit_low(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    in.watchdog_good = false; /* TPS3431 timed out during reset */
    in.reset_event = true;
    in.permit_tx_readback = true;
    in.fresh_local_cycle_event = true;
    temper_esp_outputs_t out = step(&p, in);
    assert(!out.wdi_falling_edge_request && !out.arm_high_request);

    in.reset_event = false;
    in.permit_tx_readback = false;
    in.hot_permit_readback = false;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_BUTTON_RELEASE);
    assert(out.wdi_falling_edge_request); /* validated frame can recover WDI */
    assert(!out.permit_tx_high_request && !out.arm_high_request);

    in.fresh_local_cycle_event = false;
    in.start_button = false;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_SOURCE_SESSION_RESET_STEP);
    assert(!out.wdi_falling_edge_request);
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_START_PRESS);
    assert(out.source_session_reset_low_request);
    out = step(&p, in);
    assert(!out.source_session_reset_low_request);
    in.watchdog_good = true; /* external timer recovered */
    in.start_button = true;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);
    assert(out.permit_tx_high_request && !out.hot_rearm_high_request);
}

static void test_startup_timer_wait_feeds_wdi_but_requires_fresh_not_done(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.start_button = false;
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.fresh_local_cycle_event = true;
    in.hot_permit_delay_elapsed = true; /* stale prior-transaction level */
    for (int i = 0; i < 4; ++i) {
        temper_esp_outputs_t out = step(&p, in);
        assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);
        assert(!out.hot_rearm_high_request && !out.arm_high_request);
        assert(out.wdi_falling_edge_request);
    }

    in.hot_permit_delay_elapsed = false; /* observe fresh timer not-done */
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);
    in.hot_permit_delay_elapsed = true;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_REARM_PULSE_STEP);
    assert(out.hot_rearm_high_request == false);
}

static void test_missing_hot_permit_readback_stops_wdi_and_faults_low(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = false; /* open HOT wire / absent readback */
    in.fresh_local_cycle_event = true;
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_HIGH);
    assert(out.permit_tx_high_request);
    assert(!out.wdi_falling_edge_request);

    in.watchdog_good = false; /* independent watchdog expires */
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
    assert(!out.permit_tx_high_request && !out.wdi_falling_edge_request);
}

static void test_stalled_policy_step_never_requests_wdi(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    (void)step(&p, in);
    in.hot_permit_delay_elapsed = true;
    (void)step(&p, in);
    (void)step(&p, in);
    (void)step(&p, in);
    assert(p.phase == TEMPER_ESP_ACTIVE);

    /* No policy invocation means no new WDI request can be produced. */
    in.fresh_local_cycle_event = false;
    temper_esp_outputs_t out = step(&p, in);
    assert(!out.wdi_falling_edge_request);
    in.fresh_local_cycle_event = true;
    out = step(&p, in);
    assert(out.wdi_falling_edge_request);
    in.fresh_local_cycle_event = false;
    out = step(&p, in);
    assert(!out.wdi_falling_edge_request);
}

static void test_arm_is_one_step_and_active_has_no_arm_level(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    (void)step(&p, in);
    in.hot_permit_delay_elapsed = true;
    (void)step(&p, in); /* qualify current HOT delay */
    (void)step(&p, in); /* HOT_REARM request */
    temper_esp_outputs_t out = step(&p, in); /* one ARM request */
    assert(out.phase == TEMPER_ESP_ACTIVE && out.arm_high_request);

    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_ACTIVE);
    assert(!out.arm_high_request && !out.hot_rearm_high_request);
    in.start_button = false; /* wire disconnect/reconnect cannot retrigger */
    out = step(&p, in);
    assert(!out.arm_high_request && !out.hot_rearm_high_request);
    in.start_button = true;
    out = step(&p, in);
    assert(!out.arm_high_request && !out.hot_rearm_high_request);
}

static void test_independent_wdi_counterexample_keeps_stale_path_alive(void) {
    /* Counterexample to adding an independent periodic WDI task: a source
     * fault requests permit low, but an autonomous edge can keep its watchdog
     * alive while a delayed HOT_REARM command remains queued. */
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    (void)step(&p, in);
    in.hot_permit_delay_elapsed = true;
    (void)step(&p, in);
    (void)step(&p, in);
    (void)step(&p, in);

    in.hot_health_raw = false;
    in.fresh_local_cycle_event = false;
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
    assert(!out.permit_tx_high_request);
    assert(!out.wdi_falling_edge_request && !out.hot_rearm_high_request);

    /* Policy remains locked out, but the source latch has not yet reported
     * low. A separate WDI scheduler could refresh its watchdog in this gap. */
    in.hot_health_raw = true;
    out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
    assert(!out.wdi_falling_edge_request && !out.hot_rearm_high_request);
    const bool independent_wdi_refreshes_watchdog = true; /* counterexample */
    const bool delayed_rearm_reaches_receiver =
        independent_wdi_refreshes_watchdog && in.permit_tx_readback &&
        in.hot_permit_delay_elapsed;
    assert(delayed_rearm_reaches_receiver);
}

static void test_hot_wire_readback_is_distinct_from_raw_health(void) {
    temper_esp_policy_t p;
    temper_esp_policy_init(&p);
    temper_esp_inputs_t in = healthy();
    enter_start_wait(&p, &in);
    in.start_button = true;
    (void)step(&p, in);
    in.permit_tx_readback = true;
    in.hot_permit_readback = true;
    in.hot_permit_delay_elapsed = false;
    (void)step(&p, in);
    in.hot_permit_delay_elapsed = true;
    (void)step(&p, in);
    (void)step(&p, in);
    (void)step(&p, in);
    assert(p.phase == TEMPER_ESP_ACTIVE);
    /* An open HOT permit conductor leaves raw rails/fault and source Q1 high.
     * The separate HOT-side physical readback is what makes it observable. */
    in.hot_health_raw = true;
    in.hot_permit_readback = false;
    temper_esp_outputs_t out = step(&p, in);
    assert(out.phase == TEMPER_ESP_WAIT_PERMIT_LOW);
    assert(!out.permit_tx_high_request && !out.arm_high_request);
    assert(in.hot_health_raw && in.permit_tx_readback);
}

int main(void) {
    test_reset_holds_outputs_low_until_physical_permit_low();
    test_reset_event_cannot_feed_wdi_on_same_step();
    test_fresh_press_orders_permit_delay_rearm_then_arm();
    test_health_permit_or_watchdog_loss_aborts_and_requires_press();
    test_watchdog_recovers_only_after_physical_permit_low();
    test_startup_timer_wait_feeds_wdi_but_requires_fresh_not_done();
    test_missing_hot_permit_readback_stops_wdi_and_faults_low();
    test_arm_is_one_step_and_active_has_no_arm_level();
    test_stalled_policy_step_never_requests_wdi();
    test_independent_wdi_counterexample_keeps_stale_path_alive();
    test_hot_wire_readback_is_distinct_from_raw_health();
    puts("PASS: 11 ESP-only source policy tests");
    return 0;
}
