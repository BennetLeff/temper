/**
 * @file test_main_power_gate.c
 * @brief Test runner for test_power_gate.c
 */

#include <stdio.h>
#include "unity/unity.h"

extern void run_power_gate_tests(void);
extern void power_gate_test_setup(void);

void setUp(void) {
    power_gate_test_setup();
}

void tearDown(void) {
}

int main(void) {
    UnityBegin("test_power_gate.c");
    printf("\n=== power_gate tests ===\n\n");
    run_power_gate_tests();
    return UnityEnd();
}
