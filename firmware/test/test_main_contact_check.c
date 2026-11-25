/**
 * @file test_main_contact_check.c
 * @brief Runner for the sensor-r3 contact-loss detector (D1) tests.
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_contact_check_tests(void);

void setUp(void) {}
void tearDown(void) {}

int main(void)
{
    UnityBegin("test_contact_check.c");
    printf("\n=== sensor-r3 Contact Check (D1) Tests ===\n\n");
    run_contact_check_tests();
    return UnityEnd();
}
