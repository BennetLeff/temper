/**
 * @file test_main_pan_contact_sm.c
 * @brief Runner for the EVENT_CONTACT_LOST state-machine tests.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_pan_contact_sm_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_pan_contact_sm.c");
    printf("\n=== sensor-r3 EVENT_CONTACT_LOST State Machine Tests ===\n\n");
    run_pan_contact_sm_tests();
    return UnityEnd();
}
