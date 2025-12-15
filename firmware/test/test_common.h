/**
 * @file test_common.h
 * @brief Common test utilities and domain-specific assertions
 * 
 * Provides shared macros, fixtures, and assertions for testing
 * the induction cooker firmware.
 */

#ifndef TEST_COMMON_H
#define TEST_COMMON_H

#include "unity/unity.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Induction Cooker Specifications (from design documents)
 * ============================================================================ */

/* Over-current protection */
#ifndef OCP_THRESHOLD_AMPS
#define OCP_THRESHOLD_AMPS      50.0f   /* ±5A tolerance */
#endif
#define OCP_TOLERANCE_AMPS      5.0f
#define OCP_COMPARATOR_VOLTS    2.5f    /* Voltage at comparator threshold */

/* Over-voltage protection */
#ifndef OVP_THRESHOLD_VOLTS
#define OVP_THRESHOLD_VOLTS     390.0f
#endif
#define OVP_DIVIDER_VOLTS       3.55f   /* After resistor divider */

/* Thermal limits */
#ifndef THERMAL_SHUTDOWN_C
#define THERMAL_SHUTDOWN_C      85.0f   /* IGBT junction */
#endif
#define HEATSINK_MAX_C          100.0f
#define AMBIENT_MAX_C           40.0f

/* Watchdog */
#ifndef WATCHDOG_TIMEOUT_MS
#define WATCHDOG_TIMEOUT_MS     1600    /* TPS3823-33 timeout */
#endif

/* Temperature sensing */
#ifndef TEMP_PRECISION_C
#define TEMP_PRECISION_C        0.5f    /* ±0.5°C accuracy */
#endif

/* Switching frequency */
#ifndef FREQ_MIN_KHZ
#define FREQ_MIN_KHZ            38.0f
#endif
#ifndef FREQ_MAX_KHZ
#define FREQ_MAX_KHZ            50.0f
#endif

/* Timing */
#ifndef DEAD_TIME_NS
#define DEAD_TIME_NS            500     /* Minimum dead time */
#endif

/* Pan detection thresholds */
#ifndef PAN_VALID_MIN_AMPS
#define PAN_VALID_MIN_AMPS      3.0f    /* Below = small object */
#endif
#ifndef PAN_VALID_MAX_AMPS
#define PAN_VALID_MAX_AMPS      15.0f   /* Valid pan range */
#endif
#ifndef PAN_NO_LOAD_AMPS
#define PAN_NO_LOAD_AMPS        20.0f   /* Above = no pan */
#endif

/* ============================================================================
 * Domain-Specific Test Assertions
 * ============================================================================ */

/**
 * @brief Assert temperature is within precision tolerance
 * @param expected Expected temperature in °C
 * @param actual Actual temperature in °C
 */
#define TEST_ASSERT_TEMP_WITHIN(expected, actual) \
    TEST_ASSERT_FLOAT_WITHIN_MESSAGE(TEMP_PRECISION_C, (expected), (actual), \
        "Temperature outside ±0.5°C precision")

/**
 * @brief Assert current is within OCP threshold tolerance
 * @param expected Expected current in Amps
 * @param actual Actual current in Amps
 */
#define TEST_ASSERT_CURRENT_WITHIN_OCP(expected, actual) \
    TEST_ASSERT_FLOAT_WITHIN_MESSAGE(OCP_TOLERANCE_AMPS, (expected), (actual), \
        "Current outside OCP tolerance")

/**
 * @brief Assert frequency is within valid operating range
 * @param freq Frequency in kHz
 */
#define TEST_ASSERT_FREQ_IN_RANGE(freq) \
    do { \
        TEST_ASSERT_GREATER_OR_EQUAL(FREQ_MIN_KHZ, (freq)); \
        TEST_ASSERT_LESS_OR_EQUAL(FREQ_MAX_KHZ, (freq)); \
    } while(0)

/**
 * @brief Assert current indicates valid pan
 * @param current Pan detection current in Amps
 */
#define TEST_ASSERT_PAN_VALID(current) \
    do { \
        TEST_ASSERT_GREATER_OR_EQUAL(PAN_VALID_MIN_AMPS, (current)); \
        TEST_ASSERT_LESS_OR_EQUAL(PAN_VALID_MAX_AMPS, (current)); \
    } while(0)

/**
 * @brief Assert current indicates no pan detected
 * @param current Pan detection current in Amps
 */
#define TEST_ASSERT_NO_PAN(current) \
    TEST_ASSERT_GREATER_THAN(PAN_NO_LOAD_AMPS, (current))

/**
 * @brief Assert current indicates small object (not suitable)
 * @param current Pan detection current in Amps
 */
#define TEST_ASSERT_SMALL_OBJECT(current) \
    TEST_ASSERT_LESS_THAN(PAN_VALID_MIN_AMPS, (current))

/**
 * @brief Assert duty cycle is in valid range [0, 100]
 * @param duty Duty cycle percentage
 */
#define TEST_ASSERT_DUTY_VALID(duty) \
    do { \
        TEST_ASSERT_GREATER_OR_EQUAL(0.0f, (duty)); \
        TEST_ASSERT_LESS_OR_EQUAL(100.0f, (duty)); \
    } while(0)

/**
 * @brief Assert state machine is in expected state
 * @param expected Expected system_state_t value
 * @param actual Actual system_state_t value
 */
#define TEST_ASSERT_STATE(expected, actual) \
    TEST_ASSERT_EQUAL_INT_MESSAGE((expected), (actual), \
        "State machine in unexpected state")

/**
 * @brief Assert no fault is active
 * @param fault_code Current fault code
 */
#define TEST_ASSERT_NO_FAULT(fault_code) \
    TEST_ASSERT_EQUAL_INT_MESSAGE(0, (fault_code), \
        "Unexpected fault detected")

/**
 * @brief Assert specific fault is active
 * @param expected Expected fault code
 * @param actual Actual fault code
 */
#define TEST_ASSERT_FAULT(expected, actual) \
    TEST_ASSERT_EQUAL_INT_MESSAGE((expected), (actual), \
        "Expected fault not detected")

/* ============================================================================
 * Test Fixtures and Helpers
 * ============================================================================ */

/**
 * @brief Initialize all mocks to default state
 * Call this in setUp() for tests using HAL mocks
 */
void test_reset_all_mocks(void);

/**
 * @brief Set up a standard "safe" state for testing
 * - Temperature: 25°C (ambient)
 * - Current: 0A
 * - Fan: running
 * - All interlocks: clear
 */
void test_setup_safe_state(void);

/**
 * @brief Set up state for pan detection testing
 * - Temperature: 25°C
 * - Sets mock ADC to return specified current
 * @param current_amps Simulated pan detection current
 */
void test_setup_pan_detection(float current_amps);

/**
 * @brief Set up state for thermal testing
 * @param heatsink_temp_c Heatsink temperature
 * @param igbt_temp_c IGBT junction temperature
 */
void test_setup_thermal(float heatsink_temp_c, float igbt_temp_c);

/**
 * @brief Simulate time passing (for timeout tests)
 * @param ms Milliseconds to advance
 */
void test_advance_time_ms(uint32_t ms);

/**
 * @brief Get number of emergency stop calls since last reset
 * @return Count of hal_pwm_emergency_stop() calls
 */
uint32_t test_get_emergency_stop_count(void);

/**
 * @brief Get number of watchdog feed calls since last reset
 * @return Count of watchdog_feed() calls
 */
uint32_t test_get_watchdog_feed_count(void);

/* ============================================================================
 * Test Registration Helpers
 * ============================================================================ */

/**
 * @brief Declare external test functions from a test module
 * Usage: DECLARE_TEST_MODULE(state_machine)
 * Expands to: extern void run_state_machine_tests(void);
 */
#define DECLARE_TEST_MODULE(name) \
    extern void run_##name##_tests(void)

/**
 * @brief Run a test module
 * Usage: RUN_TEST_MODULE(state_machine)
 * Expands to: run_state_machine_tests()
 */
#define RUN_TEST_MODULE(name) \
    run_##name##_tests()

/* ============================================================================
 * ADC Conversion Helpers
 * ============================================================================ */

/**
 * @brief Convert current to expected ADC voltage (through CT + burden)
 * CT ratio: 1000:1, Burden: 100Ω
 * @param current_amps Primary current in Amps
 * @return Expected voltage in mV
 */
static inline float current_to_adc_mv(float current_amps)
{
    /* CT secondary = primary / 1000 */
    /* Burden voltage = secondary * 100Ω * 1000 mV/V */
    return (current_amps / 1000.0f) * 100.0f * 1000.0f;
}

/**
 * @brief Convert temperature to expected ADC value (PT1000 RTD)
 * @param temp_c Temperature in Celsius
 * @return Expected ADC raw value (12-bit)
 */
static inline uint16_t temp_to_adc_raw(float temp_c)
{
    /* PT1000: R = 1000 * (1 + 0.00385 * T) */
    /* With MAX31865 and reference resistor */
    float resistance = 1000.0f * (1.0f + 0.00385f * temp_c);
    /* Simplified: assume linear mapping to 12-bit ADC */
    /* 0°C = 1000Ω = ~1365, 100°C = 1385Ω = ~1886 */
    return (uint16_t)((resistance / 4000.0f) * 4095.0f);
}

/**
 * @brief Convert DC bus voltage to expected ADC value
 * Divider: 390V -> 3.55V (110:1 ratio)
 * @param voltage_v DC bus voltage in Volts
 * @return Expected ADC voltage in mV
 */
static inline float bus_voltage_to_adc_mv(float voltage_v)
{
    return (voltage_v / 110.0f) * 1000.0f;  /* mV */
}

#ifdef __cplusplus
}
#endif

#endif /* TEST_COMMON_H */
