/* ==========================================
    Unity Project - A Test Framework for C
    Copyright (c) 2007-2021 Mike Karlesky, Mark VanderVoord, Greg Williams
    [Released under MIT License. Please refer to license.txt for details]
========================================== */

#ifndef UNITY_FRAMEWORK_H
#define UNITY_FRAMEWORK_H
#define UNITY

#ifdef __cplusplus
extern "C"
{
#endif

#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>

/*-------------------------------------------------------
 * Configuration Options
 *-------------------------------------------------------*/

/* Define UNITY_INCLUDE_FLOAT_SUPPORT for floating point comparisons */
#ifndef UNITY_EXCLUDE_FLOAT
#define UNITY_INCLUDE_FLOAT
#endif

/* Define UNITY_INCLUDE_DOUBLE_SUPPORT for double precision comparisons */
#ifndef UNITY_EXCLUDE_DOUBLE
#define UNITY_INCLUDE_DOUBLE
#endif

/* Printf support for test output */
#ifndef UNITY_OUTPUT_CHAR
#include <stdio.h>
#define UNITY_OUTPUT_CHAR(c) putchar(c)
#endif

/* Flush output */
#ifndef UNITY_OUTPUT_FLUSH
#include <stdio.h>
#define UNITY_OUTPUT_FLUSH() fflush(stdout)
#endif

/*-------------------------------------------------------
 * Internal Structs and Typedefs
 *-------------------------------------------------------*/

typedef void (*UnityTestFunction)(void);

typedef enum
{
    UNITY_DISPLAY_STYLE_INT = 0,
    UNITY_DISPLAY_STYLE_UINT,
    UNITY_DISPLAY_STYLE_HEX8,
    UNITY_DISPLAY_STYLE_HEX16,
    UNITY_DISPLAY_STYLE_HEX32
} UNITY_DISPLAY_STYLE_T;

typedef enum
{
    UNITY_WITHIN = 0,
    UNITY_EQUAL_TO,
    UNITY_GREATER_THAN,
    UNITY_GREATER_OR_EQUAL,
    UNITY_SMALLER_THAN,
    UNITY_SMALLER_OR_EQUAL,
    UNITY_UNKNOWN
} UNITY_COMPARISON_T;

struct UNITY_STORAGE_T
{
    const char* TestFile;
    const char* CurrentTestName;
    uint32_t CurrentTestLineNumber;
    uint32_t NumberOfTests;
    uint32_t TestFailures;
    uint32_t TestIgnores;
    uint32_t CurrentTestFailed;
    uint32_t CurrentTestIgnored;
    jmp_buf AbortFrame;
};

extern struct UNITY_STORAGE_T Unity;

/*-------------------------------------------------------
 * Test Runner Functions
 *-------------------------------------------------------*/

void UnityBegin(const char* filename);
int UnityEnd(void);
void UnityConcludeTest(void);
void UnityDefaultTestRun(UnityTestFunction Func, const char* FuncName, int FuncLineNum);

/*-------------------------------------------------------
 * Test Assertion Functions
 *-------------------------------------------------------*/

void UnityAssertEqualNumber(const int expected,
                            const int actual,
                            const char* msg,
                            const unsigned int lineNumber,
                            const UNITY_DISPLAY_STYLE_T style);

void UnityAssertEqualInt(const int expected,
                         const int actual,
                         const char* msg,
                         const unsigned int lineNumber);

void UnityAssertBits(const int mask,
                     const int expected,
                     const int actual,
                     const char* msg,
                     const unsigned int lineNumber);

void UnityAssertEqualString(const char* expected,
                            const char* actual,
                            const char* msg,
                            const unsigned int lineNumber);

void UnityAssertEqualMemory(const void* expected,
                            const void* actual,
                            const unsigned int length,
                            const char* msg,
                            const unsigned int lineNumber);

void UnityAssertNumbersWithin(const int delta,
                              const int expected,
                              const int actual,
                              const char* msg,
                              const unsigned int lineNumber);

void UnityFail(const char* message, const int line);
void UnityIgnore(const char* message, const int line);
void UnityMessage(const char* message, const int line);

/*-------------------------------------------------------
 * Floating Point Assertions
 *-------------------------------------------------------*/

#ifdef UNITY_INCLUDE_FLOAT
void UnityAssertFloatsWithin(const float delta,
                             const float expected,
                             const float actual,
                             const char* msg,
                             const unsigned int lineNumber);

void UnityAssertEqualFloat(const float expected,
                           const float actual,
                           const char* msg,
                           const unsigned int lineNumber);

void UnityAssertFloatIsInf(const float actual,
                           const char* msg,
                           const unsigned int lineNumber);

void UnityAssertFloatIsNegInf(const float actual,
                              const char* msg,
                              const unsigned int lineNumber);

void UnityAssertFloatIsNaN(const float actual,
                           const char* msg,
                           const unsigned int lineNumber);
#endif

#ifdef UNITY_INCLUDE_DOUBLE
void UnityAssertDoublesWithin(const double delta,
                              const double expected,
                              const double actual,
                              const char* msg,
                              const unsigned int lineNumber);

void UnityAssertEqualDouble(const double expected,
                            const double actual,
                            const char* msg,
                            const unsigned int lineNumber);
#endif

/*-------------------------------------------------------
 * Boolean Assertions
 *-------------------------------------------------------*/

#define UNITY_TEST_ASSERT_TRUE(condition, line, message)  \
    do { if (!(condition)) UnityFail((message), (line)); } while(0)

#define UNITY_TEST_ASSERT_FALSE(condition, line, message) \
    do { if (condition) UnityFail((message), (line)); } while(0)

#define UNITY_TEST_ASSERT_NULL(pointer, line, message)    \
    do { if ((pointer) != NULL) UnityFail((message), (line)); } while(0)

#define UNITY_TEST_ASSERT_NOT_NULL(pointer, line, message) \
    do { if ((pointer) == NULL) UnityFail((message), (line)); } while(0)

/*-------------------------------------------------------
 * User-Facing Macros
 *-------------------------------------------------------*/

/* Run a test */
#define RUN_TEST(func) UnityDefaultTestRun(func, #func, __LINE__)

/* Setup and teardown (user provides these if needed) */
void setUp(void);
void tearDown(void);

/* Basic assertions */
#define TEST_FAIL()                         UnityFail(NULL, __LINE__)
#define TEST_FAIL_MESSAGE(message)          UnityFail((message), __LINE__)
#define TEST_IGNORE()                       UnityIgnore(NULL, __LINE__)
#define TEST_IGNORE_MESSAGE(message)        UnityIgnore((message), __LINE__)
#define TEST_MESSAGE(message)               UnityMessage((message), __LINE__)

/* Boolean assertions */
#define TEST_ASSERT(condition)              UNITY_TEST_ASSERT_TRUE((condition), __LINE__, " Expression Evaluated To FALSE")
#define TEST_ASSERT_TRUE(condition)         UNITY_TEST_ASSERT_TRUE((condition), __LINE__, " Expected TRUE Was FALSE")
#define TEST_ASSERT_FALSE(condition)        UNITY_TEST_ASSERT_FALSE((condition), __LINE__, " Expected FALSE Was TRUE")
#define TEST_ASSERT_NULL(pointer)           UNITY_TEST_ASSERT_NULL((pointer), __LINE__, " Expected NULL")
#define TEST_ASSERT_NOT_NULL(pointer)       UNITY_TEST_ASSERT_NOT_NULL((pointer), __LINE__, " Expected Not-NULL")

/* Integer assertions */
#define TEST_ASSERT_EQUAL_INT(expected, actual)          UnityAssertEqualInt((expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_EQUAL_INT_MESSAGE(expected, actual, message) UnityAssertEqualInt((expected), (actual), (message), __LINE__)
#define TEST_ASSERT_EQUAL(expected, actual)              TEST_ASSERT_EQUAL_INT((expected), (actual))
#define TEST_ASSERT_EQUAL_MESSAGE(expected, actual, msg) TEST_ASSERT_EQUAL_INT_MESSAGE((expected), (actual), (msg))

#define TEST_ASSERT_NOT_EQUAL(expected, actual)          UNITY_TEST_ASSERT_FALSE(((expected) == (actual)), __LINE__, " Expected Not-Equal")

#define TEST_ASSERT_INT_WITHIN(delta, expected, actual)  UnityAssertNumbersWithin((delta), (expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_INT_WITHIN_MESSAGE(delta, expected, actual, message) UnityAssertNumbersWithin((delta), (expected), (actual), (message), __LINE__)

/* Unsigned assertions */
#define TEST_ASSERT_EQUAL_UINT(expected, actual)         UnityAssertEqualNumber((expected), (actual), NULL, __LINE__, UNITY_DISPLAY_STYLE_UINT)
#define TEST_ASSERT_EQUAL_UINT8(expected, actual)        TEST_ASSERT_EQUAL_UINT((expected), (actual))
#define TEST_ASSERT_EQUAL_UINT16(expected, actual)       TEST_ASSERT_EQUAL_UINT((expected), (actual))
#define TEST_ASSERT_EQUAL_UINT32(expected, actual)       TEST_ASSERT_EQUAL_UINT((expected), (actual))

/* Hex assertions */
#define TEST_ASSERT_EQUAL_HEX(expected, actual)          UnityAssertEqualNumber((expected), (actual), NULL, __LINE__, UNITY_DISPLAY_STYLE_HEX32)
#define TEST_ASSERT_EQUAL_HEX8(expected, actual)         UnityAssertEqualNumber((expected), (actual), NULL, __LINE__, UNITY_DISPLAY_STYLE_HEX8)
#define TEST_ASSERT_EQUAL_HEX16(expected, actual)        UnityAssertEqualNumber((expected), (actual), NULL, __LINE__, UNITY_DISPLAY_STYLE_HEX16)
#define TEST_ASSERT_EQUAL_HEX32(expected, actual)        UnityAssertEqualNumber((expected), (actual), NULL, __LINE__, UNITY_DISPLAY_STYLE_HEX32)

/* Bit-level assertions */
#define TEST_ASSERT_BITS(mask, expected, actual)         UnityAssertBits((mask), (expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_BITS_HIGH(mask, actual)              UnityAssertBits((mask), (mask), (actual), NULL, __LINE__)
#define TEST_ASSERT_BITS_LOW(mask, actual)               UnityAssertBits((mask), 0, (actual), NULL, __LINE__)
#define TEST_ASSERT_BIT_HIGH(bit, actual)                UnityAssertBits((1 << (bit)), (1 << (bit)), (actual), NULL, __LINE__)
#define TEST_ASSERT_BIT_LOW(bit, actual)                 UnityAssertBits((1 << (bit)), 0, (actual), NULL, __LINE__)

/* String assertions */
#define TEST_ASSERT_EQUAL_STRING(expected, actual)       UnityAssertEqualString((expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_EQUAL_STRING_MESSAGE(expected, actual, message) UnityAssertEqualString((expected), (actual), (message), __LINE__)

/* Memory assertions */
#define TEST_ASSERT_EQUAL_MEMORY(expected, actual, len)  UnityAssertEqualMemory((expected), (actual), (len), NULL, __LINE__)
#define TEST_ASSERT_EQUAL_MEMORY_MESSAGE(expected, actual, len, message) UnityAssertEqualMemory((expected), (actual), (len), (message), __LINE__)

/* Float assertions */
#ifdef UNITY_INCLUDE_FLOAT
#define TEST_ASSERT_FLOAT_WITHIN(delta, expected, actual)          UnityAssertFloatsWithin((delta), (expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_FLOAT_WITHIN_MESSAGE(delta, expected, actual, message) UnityAssertFloatsWithin((delta), (expected), (actual), (message), __LINE__)
#define TEST_ASSERT_EQUAL_FLOAT(expected, actual)                  UnityAssertEqualFloat((expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_EQUAL_FLOAT_MESSAGE(expected, actual, message) UnityAssertEqualFloat((expected), (actual), (message), __LINE__)
#define TEST_ASSERT_FLOAT_IS_INF(actual)                           UnityAssertFloatIsInf((actual), NULL, __LINE__)
#define TEST_ASSERT_FLOAT_IS_NEG_INF(actual)                       UnityAssertFloatIsNegInf((actual), NULL, __LINE__)
#define TEST_ASSERT_FLOAT_IS_NAN(actual)                           UnityAssertFloatIsNaN((actual), NULL, __LINE__)
#endif

/* Double assertions */
#ifdef UNITY_INCLUDE_DOUBLE
#define TEST_ASSERT_DOUBLE_WITHIN(delta, expected, actual)         UnityAssertDoublesWithin((delta), (expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_DOUBLE_WITHIN_MESSAGE(delta, expected, actual, message) UnityAssertDoublesWithin((delta), (expected), (actual), (message), __LINE__)
#define TEST_ASSERT_EQUAL_DOUBLE(expected, actual)                 UnityAssertEqualDouble((expected), (actual), NULL, __LINE__)
#define TEST_ASSERT_EQUAL_DOUBLE_MESSAGE(expected, actual, message) UnityAssertEqualDouble((expected), (actual), (message), __LINE__)
#endif

/* Comparison assertions */
#define TEST_ASSERT_GREATER_THAN(threshold, actual)      UNITY_TEST_ASSERT_TRUE(((actual) > (threshold)), __LINE__, " Expected Greater Than")
#define TEST_ASSERT_GREATER_OR_EQUAL(threshold, actual)  UNITY_TEST_ASSERT_TRUE(((actual) >= (threshold)), __LINE__, " Expected Greater Or Equal")
#define TEST_ASSERT_LESS_THAN(threshold, actual)         UNITY_TEST_ASSERT_TRUE(((actual) < (threshold)), __LINE__, " Expected Less Than")
#define TEST_ASSERT_LESS_OR_EQUAL(threshold, actual)     UNITY_TEST_ASSERT_TRUE(((actual) <= (threshold)), __LINE__, " Expected Less Or Equal")

#ifdef __cplusplus
}
#endif

#endif /* UNITY_FRAMEWORK_H */
