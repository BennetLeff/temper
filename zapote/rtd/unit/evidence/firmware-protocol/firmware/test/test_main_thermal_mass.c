/**
 * @file test_main_thermal_mass.c
 * @brief Main test runner for thermal mass estimation tests
 */

#include <stdio.h>
#include "unity/unity.h"

/* External test function */
extern void run_thermal_mass_tests(void);

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

int main(void) {
    UnityBegin("test_thermal_mass.c");
    
    printf("\n=== Thermal Mass Estimation Tests ===\n\n");
    run_thermal_mass_tests();
    
    return UnityEnd();
}