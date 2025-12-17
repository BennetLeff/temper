/**
 * @file test_main_pid.c
 * @brief Standalone test runner for PID controller
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_pid_control_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_pid_control.c");
    
    printf("\n=== PID Controller Tests ===\n\n");
    run_pid_control_tests();
    
    return UnityEnd();
}
