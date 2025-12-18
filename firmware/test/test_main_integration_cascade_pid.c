/**
 * @file test_main_integration_cascade_pid.c
 * @brief Main test runner for cascade PID integration tests
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_cascade_pid_integration_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_integration_cascade_pid.c");
    
    printf("\n=== Cascade PID Integration Tests ===\n\n");
    run_cascade_pid_integration_tests();
    
    return UnityEnd();
}