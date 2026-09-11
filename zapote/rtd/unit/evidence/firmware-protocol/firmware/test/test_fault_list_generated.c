/**
 * @file test_fault_list_generated.c
 * @brief Verify the generated FAULT_LIST is complete and correct.
 *
 * Tests:
 * - FAULT_IGBT_SHORT and FAULT_ADC_STUCK exist in the enum
 * - FAULT_COUNT matches expected total (14: 9 manifest + 5 supplemental)
 * - String table is complete and non-empty for all fault codes
 * - Known labels preserved (backward compatibility with EEPROM logs)
 */

#include "unity/unity.h"
#include "../main/state_machine.h"
#include <string.h>

/* Unity required functions */
void setUp(void) {}
void tearDown(void) {}

/* ---------------------------------------------------------------------------
 * Enum existence
 * --------------------------------------------------------------------------- */

void test_fault_igbt_short_exists(void)
{
    /* FAULT_IGBT_SHORT must be a valid enum value — not 0 (FAULT_NONE)
     * and not equal to FAULT_COUNT (sentinel). */
    TEST_ASSERT_NOT_EQUAL(0, FAULT_IGBT_SHORT);
    TEST_ASSERT_NOT_EQUAL(FAULT_COUNT, FAULT_IGBT_SHORT);
    TEST_ASSERT(FAULT_IGBT_SHORT < FAULT_COUNT);
}

void test_fault_adc_stuck_exists(void)
{
    TEST_ASSERT_NOT_EQUAL(0, FAULT_ADC_STUCK);
    TEST_ASSERT_NOT_EQUAL(FAULT_COUNT, FAULT_ADC_STUCK);
    TEST_ASSERT(FAULT_ADC_STUCK < FAULT_COUNT);
}

/* ---------------------------------------------------------------------------
 * Count sentinel
 * --------------------------------------------------------------------------- */

void test_fault_count_expected(void)
{
    /* 9 manifest-derived + 5 supplemental = 14 total */
    TEST_ASSERT_EQUAL(14, FAULT_COUNT);
}

/* ---------------------------------------------------------------------------
 * String table completeness
 * --------------------------------------------------------------------------- */

void test_fault_name_table_complete(void)
{
    /* Every entry in fault_name_table must have a non-null, non-empty name.
     * The table is indexed by fault code value. */
    for (int i = 0; i < FAULT_COUNT; i++) {
        TEST_ASSERT_NOT_NULL(fault_name_table[i].name);
        TEST_ASSERT_NOT_EQUAL(0, strlen(fault_name_table[i].name));
    }
}

/* ---------------------------------------------------------------------------
 * Known label values (backward compatibility)
 * --------------------------------------------------------------------------- */

void test_fault_labels_preserved(void)
{
    /* Verify the existing hand-maintained labels are preserved in the
     * generated header via label overrides. These strings are consumed
     * by EEPROM logging and test assertions. */
    TEST_ASSERT_EQUAL_STRING("OVER TEMP",
        fault_name_table[FAULT_OVER_TEMP].name);
    TEST_ASSERT_EQUAL_STRING("OVER CURRENT",
        fault_name_table[FAULT_OVER_CURRENT].name);
    TEST_ASSERT_EQUAL_STRING("FAN FAILED",
        fault_name_table[FAULT_FAN_FAILURE].name);
    TEST_ASSERT_EQUAL_STRING("PROBE OPEN",
        fault_name_table[FAULT_PROBE_OPEN].name);
    TEST_ASSERT_EQUAL_STRING("PROBE SHORT",
        fault_name_table[FAULT_PROBE_SHORT].name);
    TEST_ASSERT_EQUAL_STRING("COOLDOWN FAULT",
        fault_name_table[FAULT_COOLDOWN_OVERHEAT].name);
}

/* ---------------------------------------------------------------------------
 * Test runner
 * --------------------------------------------------------------------------- */

int main(void)
{
    UnityBegin("test_fault_list_generated.c");

    RUN_TEST(test_fault_igbt_short_exists);
    RUN_TEST(test_fault_adc_stuck_exists);
    RUN_TEST(test_fault_count_expected);
    RUN_TEST(test_fault_name_table_complete);
    RUN_TEST(test_fault_labels_preserved);

    return 0;
}
