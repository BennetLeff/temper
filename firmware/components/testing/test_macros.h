/**
 * @file test_macros.h
 * @brief Unified test assertion macros (ADDITIVE, non-breaking)
 * 
 * Provides consistent assertion patterns for firmware testing.
 * Can be used alongside or instead of Unity TEST_ASSERT_* macros.
 */

#ifndef TEST_MACROS_H
#define TEST_MACROS_H

#include <stdint.h>
#include <stdbool.h>
#include "unity.h"

/* ================================
 * Assertion Macros (ADDITIVE - can coexist with Unity)
 * ================================
 */

/**
 * @brief Check condition, fail if false
 * 
 * Usage:
 *     TEST_ASSERT(count > 0, "Count must be positive");
 */
#define TEST_ASSERT(cond, msg) \
    if (!(cond)) { \
        TEST_FAIL_MESSAGE(#cond, msg); \
        UNITY_TEST_FAIL(__FILE__, __LINE__); \
    }

/**
 * @brief Check pointer, fail if NULL
 * 
 * Usage:
 *     TEST_ASSERT_NOT_NULL(buffer);
 */
#define TEST_ASSERT_NOT_NULL(ptr, msg) \
    TEST_ASSERT((ptr) != NULL, msg)

/**
 * @brief Check two values equal
 * 
 * Usage:
 *     TEST_ASSERT_EQ(expected, actual, "Values don't match");
 */
#define TEST_ASSERT_EQ(a, b, msg) \
    TEST_ASSERT((a) == (b), msg)

/**
 * @brief Check value in range [min, max]
 * 
 * Usage:
 *     TEST_ASSERT_IN_RANGE(value, min, max, "Value out of range");
 */
#define TEST_ASSERT_IN_RANGE(val, min, max, msg) \
    TEST_ASSERT((val) >= (min) && (val) <= (max), msg)

/**
 * @brief Check array index is valid
 * 
 * Usage:
 *     TEST_ASSERT_ARRAY_INDEX(index, size, "Index out of bounds");
 */
#define TEST_ASSERT_ARRAY_INDEX(idx, size, msg) \
    TEST_ASSERT((idx) < (size), msg)

/**
 * @brief Check pointer is not NULL (convenience wrapper)
 * 
 * Usage:
 *     TEST_ASSERT_NOT_NULL(ptr, "Pointer cannot be NULL");
 */
#define TEST_CHECK_PTR(ptr) \
    TEST_ASSERT_NOT_NULL(ptr, "Pointer cannot be NULL")

/* ================================
 * Message Formatting (ADDITIVE helper)
 * ================================
 */

/**
 * @brief Format assertion failure message
 * 
 * @param condition The failed condition as string
 * @param message Descriptive message
 */
#define TEST_FAIL_MESSAGE(condition, message) \
    (void)fprintf(stderr, "Assertion failed: %s - %s\n", condition, message)

/* ================================
 * Memory Tracking (ADDITIVE for testing)
 * ================================
 */

/**
 * @brief Enable memory tracking for leak detection
 * 
 * Define DEBUG_MEMORY in project settings to enable.
 * 
 * Usage:
 *     void *ptr = ALLOC_TRACK(64);
 *     // ... use ptr
 *     FREE_TRACK(ptr);
 *     
 *     if (g_alloc_count != g_free_count) {
 *         printf("MEMORY LEAK: %lu allocs, %lu frees\n", g_alloc_count, g_free_count);
 *     }
 */
#ifdef DEBUG_MEMORY
    extern unsigned long g_alloc_count;
    extern unsigned long g_free_count;

/**
 * @brief Allocate memory with tracking
 * 
 * @param size Number of bytes to allocate
 * @return Pointer to allocated memory or NULL on failure
 */
#define ALLOC_TRACK(size) \
    ({ \
        g_alloc_count++; \
        malloc(size); \
    })

/**
 * @brief Free memory with tracking
 * 
 * @param ptr Pointer to memory to free (NULL-safe)
 */
#define FREE_TRACK(ptr) \
    do { \
        if ((ptr) != NULL) { \
            g_free_count++; \
            free(ptr); \
        } \
    } while (0)

#else
    /* Production builds: no tracking overhead */
#define ALLOC_TRACK(size) malloc(size)
#define FREE_TRACK(ptr) if ((ptr) != NULL) free(ptr)
#endif

/**
 * @brief Check for memory leaks
 * 
 * @return true if allocs != frees, false otherwise
 * 
 * Usage:
 *     if (TEST_ASSERT_NO_LEAKS()) {
 *         // Fail with leak detected
 *     }
 */
#define TEST_ASSERT_NO_LEAKS() \
    TEST_ASSERT(g_alloc_count == g_free_count, "Memory leak detected: not all memory freed")

/**
 * @brief Get memory statistics
 * 
 * @return Struct with allocation and free counts
 */
typedef struct {
    unsigned long total_allocs;
    unsigned long total_frees;
    unsigned long leaked_bytes;
} memory_stats_t;

#define TEST_GET_MEMORY_STATS() \
    ((memory_stats_t){ .total_allocs = g_alloc_count, .total_frees = g_free_count, .leaked_bytes = (g_alloc_count - g_free_count) * sizeof(void*) })

/**
 * @brief Reset memory tracking counters
 * 
 * Call this before starting a new test to get clean baseline.
 */
#define TEST_RESET_MEMORY_STATS() \
    do { \
        g_alloc_count = 0; \
        g_free_count = 0; \
    } while (0)

/**
 * @brief Print memory statistics
 * 
 * Usage:
 *     TEST_PRINT_MEMORY_STATS();
 */
#define TEST_PRINT_MEMORY_STATS() \
    do { \
        memory_stats_t stats = TEST_GET_MEMORY_STATS(); \
        if (stats.total_allocs != stats.total_frees) { \
            printf("WARNING: Potential memory leak detected\\n"); \
        } \
        printf("Memory stats:\\n"); \
        printf("  Total allocs: %lu\\n", stats.total_allocs); \
        printf("  Total frees:  %lu\\n", stats.total_frees); \
        printf("  Leaked:     %lu objects * %zu bytes\\n", stats.leaked_bytes, sizeof(void*)); \
    } while (0)

#else
    /* Production builds: no tracking */
#define ALLOC_TRACK(size) malloc(size)
#define FREE_TRACK(ptr) if ((ptr) != NULL) free(ptr)
    TEST_ASSERT_NO_LEAKS()  TEST_ASSERT(true, "No leak tracking in production builds")
    TEST_RESET_MEMORY_STATS() ({ 0; })
    TEST_GET_MEMORY_STATS() ((memory_stats_t){ .total_allocs = 0, .total_frees = 0, .leaked_bytes = 0 })
    TEST_PRINT_MEMORY_STATS() printf("Memory tracking not enabled in production builds\\n")
#endif

/**
 * @brief Assert strings are equal (case-insensitive, first N chars)
 * 
 * Useful for checking error messages or command outputs.
 * 
 * Usage:
 *     TEST_ASSERT_STR_EQ(expected, actual, "Strings don't match");
 */
#define TEST_ASSERT_STR_EQ_N(a, b, n, msg) \
    TEST_ASSERT(string_equals_n((a), (b), (n)), msg)

/**
 * @brief Assert string starts with prefix (case-insensitive)
 * 
 * Usage:
 *     TEST_ASSERT_STR_STARTS(str, prefix, "String must start with prefix");
 */
#define TEST_ASSERT_STR_STARTS(str, prefix) \
    TEST_ASSERT(string_starts_with((str), (prefix)), msg)

/**
 * @brief Assert string is numeric (integer)
 * 
 * Usage:
 *     TEST_ASSERT_STR_NUMERIC(str, "String must be numeric");
 */
#define TEST_ASSERT_STR_NUMERIC(str) \
    TEST_ASSERT(string_is_numeric((str)), msg)

/**
 * @brief Assert value is finite (not NaN or inf)
 * 
 * Usage:
 *     TEST_ASSERT(isfinite(value), "Value must be finite");
 */
#define TEST_ASSERT_IS_FINITE(val) \
    TEST_ASSERT(test_is_finite_helper(val), "Value must be finite (not NaN/inf)")

/**
 * @brief Assert value in range [min, max]
 * 
 * Usage:
 *     TEST_ASSERT_IN_RANGE(value, min, max, "Value must be in range");
 */
#define TEST_ASSERT_IN_RANGE_INCLUSIVE(val, min, max, msg) \
    TEST_ASSERT((val) > (min) && (val) < (max), msg)

/**
 * @brief Assert buffer is all zeros
 * 
 * Usage:
 *     TEST_ASSERT_BUFFER_ZERO(buffer, size, "Buffer must be zeroed");
 */
#define TEST_ASSERT_BUFFER_ZERO(buf, size) \
    TEST_ASSERT(buffer_is_zero((buf), (size)), "Buffer must be zeroed")

#endif /* TEST_MACROS_H */
