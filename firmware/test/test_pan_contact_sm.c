/**
 * @file test_pan_contact_sm.c
 * @brief EVENT_CONTACT_LOST (sensor-r3 D1) in the state machine: a self-loop
 *        in PREHEAT and HEATING that tells the user, ignored elsewhere.
 */

#include <string.h>

#include "unity/unity.h"
#include "../main/state_machine.h"
#include "../main/transition_table.h"

extern void mock_sm_reset(void);
extern void mock_sm_set_pan_status(int status);
extern void mock_sm_set_pan_temperature(float temp_c);
extern const char *mock_sm_get_last_display_message(void);

#define MOCK_PAN_PRESENT 1

static void enter(system_state_t s)
{
    mock_sm_reset();
    state_machine_init();
    mock_sm_set_pan_status(MOCK_PAN_PRESENT);
    mock_sm_set_pan_temperature(60.0f);
    state_machine_reset_temp_baseline();
    state_machine_force_state(s);
}

static void test_contact_lost_is_a_self_loop_with_message(void)
{
    const system_state_t active[] = {STATE_PREHEAT, STATE_HEATING};
    for (size_t i = 0; i < 2; i++) {
        enter(active[i]);
        state_machine_report_pan_contact_lost();
        TEST_ASSERT_EQUAL_INT(active[i], state_machine_get_state());
        TEST_ASSERT_EQUAL_INT(FAULT_NONE, state_machine_get_fault());
        TEST_ASSERT_EQUAL_STRING("PAN MUST TOUCH SENSOR", mock_sm_get_last_display_message());
        /* the generated table agrees */
        TEST_ASSERT_EQUAL_INT(active[i], transition_table[active[i]][EVENT_CONTACT_LOST]);
    }
}

static void test_contact_lost_ignored_outside_power_states(void)
{
    const system_state_t idle_like[] = {STATE_IDLE, STATE_COOLDOWN, STATE_NO_PAN};
    for (size_t i = 0; i < 3; i++) {
        enter(idle_like[i]);
        const system_state_t before = state_machine_get_state();
        state_machine_report_pan_contact_lost();
        TEST_ASSERT_EQUAL_INT(before, state_machine_get_state());
        TEST_ASSERT_TRUE(strcmp("PAN MUST TOUCH SENSOR", mock_sm_get_last_display_message()) != 0);
        TEST_ASSERT_EQUAL_INT(TRANSITION_INVALID, transition_table[idle_like[i]][EVENT_CONTACT_LOST]);
    }
}

void run_pan_contact_sm_tests(void)
{
    RUN_TEST(test_contact_lost_is_a_self_loop_with_message);
    RUN_TEST(test_contact_lost_ignored_outside_power_states);
}
