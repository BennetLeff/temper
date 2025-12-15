/**
 * @file test_main_state_machine.c
 * @brief Standalone test runner for state machine
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_state_machine_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_state_machine.c");
    
    printf("\n=== State Machine Tests ===\n\n");
    run_state_machine_tests();
    
    return UnityEnd();
}
