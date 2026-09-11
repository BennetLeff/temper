/** @file test_main_max31865.c */

#include <stdio.h>

#include "unity/unity.h"

extern void run_max31865_tests(void);

int main(void)
{
    UnityBegin("test_max31865.c");
    printf("\n=== MAX31865 Contract Tests ===\n\n");
    run_max31865_tests();
    return UnityEnd();
}
