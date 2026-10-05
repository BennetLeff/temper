/* Real contact guard + production state machine/handlers; only hardware is mocked. */
#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../main/state_handlers.h"
#include "../main/contact_guard.h"
#include <stdint.h>
extern void mock_sm_reset(void);
extern void mock_sm_set_time(uint32_t);
extern void mock_sm_advance_time(uint32_t);
extern void mock_sm_set_pan_status(int);
extern void mock_sm_set_pan_temperature(float);
extern void mock_sm_press_button(button_id_t);
extern void mock_sm_release_all_buttons(void);
extern uint32_t mock_sm_get_power_level(void);
extern uint32_t mock_sm_get_positive_power_count(void);
static uint32_t positive_before_tick;
extern uint32_t mock_sm_get_pwm_disable_count(void);
extern uint32_t mock_sm_get_trigger_shutdown_count(void);
extern bool mock_sm_get_pll_enabled(void);
extern fault_code_t mock_sm_get_last_logged_fault(void);
extern uint32_t get_time_ms(void);
void setUp(void) { mock_sm_reset(); state_machine_init(); positive_before_tick = 0; }
void tearDown(void) {}
static void tick(uint32_t ms, contact_sample_state_t sample) {
    positive_before_tick = mock_sm_get_positive_power_count();
    mock_sm_advance_time(ms);
    contact_guard_submit(sample, get_time_ms());
    state_machine_update();
}
static void release(void) {
    for(unsigned i=0;i<=CONTACT_RELEASE_MS/10;++i) tick(10, CONTACT_SAMPLE_RELEASED);
}
static void acquire(void) {
    release();
    tick(10, CONTACT_SAMPLE_LOADED);
    for (unsigned i=0; i<10; ++i) tick(10, CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_TRUE(contact_guard_valid(get_time_ms()));
}
static void start(void) {
    mock_sm_set_pan_status(1);
    mock_sm_press_button(BUTTON_START);
    tick(10, CONTACT_SAMPLE_LOADED);
    mock_sm_release_all_buttons();
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());
}
static void heat(void) {
    acquire(); start();
    for (unsigned i=0; i<30 && state_machine_get_state()!=STATE_PREHEAT; ++i)
        tick(10, CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
    tick(10, CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_TRUE(mock_sm_get_power_level()>0);
}
static void assert_cut(void) {
    TEST_ASSERT_EQUAL(positive_before_tick,mock_sm_get_positive_power_count());
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_PROBE_CONTACT, state_machine_get_fault());
    TEST_ASSERT_EQUAL(0, mock_sm_get_power_level());
    TEST_ASSERT_FALSE(mock_sm_get_pll_enabled());
    TEST_ASSERT_TRUE(mock_sm_get_pwm_disable_count()>0);
    TEST_ASSERT_TRUE(mock_sm_get_trigger_shutdown_count()>0);
    TEST_ASSERT_EQUAL(FAULT_PROBE_CONTACT, mock_sm_get_last_logged_fault());
}
static void absent_backend_blocks_start(void) {
    state_machine_update(); mock_sm_press_button(BUTTON_START);
    state_machine_update(); assert_cut();
}
static void requires_release_and_continuous_acquisition(void) {
    for(unsigned i=0;i<20;++i) tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
    release();
    tick(10,CONTACT_SAMPLE_LOADED);
    tick(40,CONTACT_SAMPLE_LOADED);
    release();
    tick(10,CONTACT_SAMPLE_LOADED);
    for(unsigned i=0;i<9;++i) tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
    tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_TRUE(contact_guard_valid(get_time_ms()));
}
static void lost_contact_with_pan_present_cuts_before_preheat(void) {
    heat(); tick(10,CONTACT_SAMPLE_RELEASED); assert_cut();
}
static void lost_contact_in_heating_preempts_ui_delay(void) {
    heat(); mock_sm_set_pan_temperature(95); state_machine_reset_temp_baseline();
    tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_EQUAL(STATE_HEATING,state_machine_get_state());
    show_message_then_transition("TEST",STATE_PREHEAT);
    tick(10,CONTACT_SAMPLE_RELEASED); assert_cut();
    acquire(); mock_sm_advance_time(4000); state_machine_update(); assert_cut();
}
static void loss_in_pan_detection_cuts(void) {
    acquire(); start(); tick(10,CONTACT_SAMPLE_FAULT); assert_cut();
}
static void stale_input_cuts_at_deadline(void) {
    heat(); positive_before_tick=mock_sm_get_positive_power_count(); mock_sm_advance_time(CONTACT_MAX_SAMPLE_AGE_MS); state_machine_update(); assert_cut();
}
static void future_or_replayed_sample_cannot_refresh(void) {
    acquire(); contact_guard_submit(CONTACT_SAMPLE_LOADED,get_time_ms()+1000);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
    contact_guard_reset(); acquire();
    uint32_t old=get_time_ms();
    mock_sm_advance_time(CONTACT_MAX_SAMPLE_AGE_MS);
    contact_guard_submit(CONTACT_SAMPLE_LOADED,old);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
}
static void fault_never_auto_resumes_or_button_resets(void) {
    heat(); tick(10,CONTACT_SAMPLE_FAULT); assert_cut();
    acquire(); mock_sm_press_button(BUTTON_RESET); state_machine_update(); assert_cut();
}
static void unavailable_and_invalid_inputs_drop_validity(void) {
    acquire(); tick(10,CONTACT_SAMPLE_UNAVAILABLE);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
    acquire(); tick(10,(contact_sample_state_t)99);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
}
static void wraparound_preserves_bounded_age(void) {
    mock_sm_set_time(UINT32_MAX-150); acquire();
    tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_TRUE(contact_guard_valid(get_time_ms()));
    mock_sm_advance_time(CONTACT_MAX_SAMPLE_AGE_MS);
    TEST_ASSERT_FALSE(contact_guard_valid(get_time_ms()));
}
static void no_pan_resume_cannot_bypass_contact(void) {
    heat(); state_machine_force_state(STATE_NO_PAN);
    tick(10,CONTACT_SAMPLE_RELEASED); assert_cut();
}
static void all_loss_phases_meet_software_deadline(void) {
    /* 50 phases exercise reported loss and missing updates in all active states. */
    const system_state_t states[] = {STATE_PAN_DET,STATE_PREHEAT,STATE_HEATING};
    for(unsigned state=0;state<3;++state) {
        for(unsigned phase=0;phase<50;++phase) {
            setUp(); acquire(); start();
            state_machine_force_state(states[state]);
            positive_before_tick=mock_sm_get_positive_power_count();
            uint32_t observed=get_time_ms();
            mock_sm_advance_time(phase);
            contact_guard_submit(CONTACT_SAMPLE_RELEASED,get_time_ms());
            state_machine_update(); assert_cut();
            TEST_ASSERT_EQUAL(phase,get_time_ms()-observed);
            setUp(); acquire(); start();
            state_machine_force_state(states[state]);
            positive_before_tick=mock_sm_get_positive_power_count();
            mock_sm_advance_time(CONTACT_MAX_SAMPLE_AGE_MS+phase%10);
            state_machine_update(); assert_cut();
        }
    }
}
static void same_timestamp_contradiction_revokes(void) {

    heat(); positive_before_tick=mock_sm_get_positive_power_count(); contact_guard_submit(CONTACT_SAMPLE_RELEASED,get_time_ms());
    state_machine_update(); assert_cut();
}
static void reversed_clock_revokes(void) {
    heat(); positive_before_tick=mock_sm_get_positive_power_count(); mock_sm_set_time(get_time_ms()-1);
    state_machine_update(); assert_cut();
}
static void stale_boundary_and_replay(void) {
    heat(); uint32_t last=get_time_ms();
    mock_sm_advance_time(CONTACT_MAX_SAMPLE_AGE_MS-1);
    state_machine_update(); TEST_ASSERT_EQUAL(STATE_PREHEAT,state_machine_get_state());
    positive_before_tick=mock_sm_get_positive_power_count();
    contact_guard_submit(CONTACT_SAMPLE_LOADED,last);
    mock_sm_advance_time(1); state_machine_update(); assert_cut();
}
static void active_entries_cannot_bypass(void) {
    state_machine_update(); transition_to(STATE_PREHEAT); assert_cut();
    state_machine_init(); state_machine_update(); transition_to(STATE_HEATING); assert_cut();
}
static void runaway_wins_over_contact_loss(void) {
    heat(); mock_sm_set_pan_temperature(400);
    tick(10,CONTACT_SAMPLE_RELEASED);
    TEST_ASSERT_EQUAL(STATE_RUNAWAY_FAULT,state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_RUNAWAY_BOUNDARY,state_machine_get_fault());
    TEST_ASSERT_EQUAL(0,mock_sm_get_power_level());
    TEST_ASSERT_TRUE(mock_sm_get_trigger_shutdown_count()>0);
}
static void low_temperature_branch_loss_cuts(void) {
    heat(); state_machine_set_target_temp(40); mock_sm_set_pan_temperature(35);
    state_machine_reset_temp_baseline(); tick(10,CONTACT_SAMPLE_LOADED);
    TEST_ASSERT_EQUAL(STATE_HEATING,state_machine_get_state());
    tick(10,CONTACT_SAMPLE_LOADED);
    tick(10,CONTACT_SAMPLE_RELEASED); assert_cut();
}
int main(void) {

    UnityBegin("test_contact_interlock.c");
    RUN_TEST(all_loss_phases_meet_software_deadline);
    RUN_TEST(same_timestamp_contradiction_revokes);
    RUN_TEST(reversed_clock_revokes);
    RUN_TEST(stale_boundary_and_replay);
    RUN_TEST(active_entries_cannot_bypass);
    RUN_TEST(runaway_wins_over_contact_loss);
    RUN_TEST(low_temperature_branch_loss_cuts);
    RUN_TEST(absent_backend_blocks_start);

    RUN_TEST(requires_release_and_continuous_acquisition);
    RUN_TEST(lost_contact_with_pan_present_cuts_before_preheat);
    RUN_TEST(lost_contact_in_heating_preempts_ui_delay);
    RUN_TEST(loss_in_pan_detection_cuts);
    RUN_TEST(stale_input_cuts_at_deadline);
    RUN_TEST(future_or_replayed_sample_cannot_refresh);
    RUN_TEST(fault_never_auto_resumes_or_button_resets);
    RUN_TEST(unavailable_and_invalid_inputs_drop_validity);
    RUN_TEST(wraparound_preserves_bounded_age);
    RUN_TEST(no_pan_resume_cannot_bypass_contact);
    return UnityEnd();
}
