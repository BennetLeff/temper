/**
 * @file test_main_state_machine.c
 * @brief Standalone test runner for state machine
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test functions */
extern void run_state_machine_tests(void);
extern void test_transition_table(void);
extern void test_transition_table_cross_check(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_state_machine.c");
    
    printf("\n=== State Machine Tests ===\n\n");
    run_state_machine_tests();
    
    printf("\n=== Transition Table Tests ===\n\n");
    RUN_TEST(test_transition_table);
    
    printf("\n=== Transition Table Cross-Check ===\n\n");
    RUN_TEST(test_transition_table_cross_check);
    
    return UnityEnd();
}
