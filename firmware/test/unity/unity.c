/* ==========================================
    Unity Project - A Test Framework for C
    Copyright (c) 2007-2021 Mike Karlesky, Mark VanderVoord, Greg Williams
    [Released under MIT License]
    
    Simplified implementation for embedded testing
========================================== */

#include "unity.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

/* Global Unity state */
struct UNITY_STORAGE_T Unity;

/*-------------------------------------------------------
 * Output Helper Functions
 *-------------------------------------------------------*/

static void UnityPrint(const char* string)
{
    if (string != NULL)
    {
        while (*string)
        {
            UNITY_OUTPUT_CHAR(*string);
            string++;
        }
    }
}

static void UnityPrintNumber(const int number)
{
    char buffer[16];
    snprintf(buffer, sizeof(buffer), "%d", number);
    UnityPrint(buffer);
}

static void UnityPrintUnsigned(const unsigned int number)
{
    char buffer[16];
    snprintf(buffer, sizeof(buffer), "%u", number);
    UnityPrint(buffer);
}

static void UnityPrintHex(const unsigned int number, int width)
{
    char buffer[16];
    switch (width)
    {
        case 2:  snprintf(buffer, sizeof(buffer), "0x%02X", (unsigned char)number); break;
        case 4:  snprintf(buffer, sizeof(buffer), "0x%04X", (unsigned short)number); break;
        default: snprintf(buffer, sizeof(buffer), "0x%08X", number); break;
    }
    UnityPrint(buffer);
}

#ifdef UNITY_INCLUDE_FLOAT
static void UnityPrintFloat(const float number)
{
    char buffer[32];
    if (isnan(number)) {
        UnityPrint("nan");
    } else if (isinf(number)) {
        UnityPrint(number > 0 ? "inf" : "-inf");
    } else {
        snprintf(buffer, sizeof(buffer), "%.6f", (double)number);
        UnityPrint(buffer);
    }
}
#endif

#ifdef UNITY_INCLUDE_DOUBLE
static void UnityPrintDouble(const double number)
{
    char buffer[32];
    if (isnan(number)) {
        UnityPrint("nan");
    } else if (isinf(number)) {
        UnityPrint(number > 0 ? "inf" : "-inf");
    } else {
        snprintf(buffer, sizeof(buffer), "%.12f", number);
        UnityPrint(buffer);
    }
}
#endif

static void UnityPrintNewLine(void)
{
    UNITY_OUTPUT_CHAR('\n');
}

/*-------------------------------------------------------
 * Test Runner Functions
 *-------------------------------------------------------*/

void UnityBegin(const char* filename)
{
    Unity.TestFile = filename;
    Unity.CurrentTestName = NULL;
    Unity.CurrentTestLineNumber = 0;
    Unity.NumberOfTests = 0;
    Unity.TestFailures = 0;
    Unity.TestIgnores = 0;
    Unity.CurrentTestFailed = 0;
    Unity.CurrentTestIgnored = 0;
}

int UnityEnd(void)
{
    UnityPrint("-----------------------");
    UnityPrintNewLine();
    UnityPrintNumber(Unity.NumberOfTests);
    UnityPrint(" Tests ");
    UnityPrintNumber(Unity.TestFailures);
    UnityPrint(" Failures ");
    UnityPrintNumber(Unity.TestIgnores);
    UnityPrint(" Ignored");
    UnityPrintNewLine();
    
    if (Unity.TestFailures == 0)
    {
        UnityPrint("OK");
    }
    else
    {
        UnityPrint("FAIL");
    }
    UnityPrintNewLine();
    UNITY_OUTPUT_FLUSH();
    
    return (int)(Unity.TestFailures);
}

void UnityConcludeTest(void)
{
    if (Unity.CurrentTestIgnored)
    {
        UnityPrint(Unity.TestFile);
        UnityPrint(":");
        UnityPrintNumber(Unity.CurrentTestLineNumber);
        UnityPrint(":");
        UnityPrint(Unity.CurrentTestName);
        UnityPrint(":IGNORE");
        UnityPrintNewLine();
    }
    else if (Unity.CurrentTestFailed)
    {
        /* Failure message already printed */
    }
    else
    {
        UnityPrint(Unity.TestFile);
        UnityPrint(":");
        UnityPrintNumber(Unity.CurrentTestLineNumber);
        UnityPrint(":");
        UnityPrint(Unity.CurrentTestName);
        UnityPrint(":PASS");
        UnityPrintNewLine();
    }
    
    Unity.CurrentTestFailed = 0;
    Unity.CurrentTestIgnored = 0;
    UNITY_OUTPUT_FLUSH();
}

void UnityDefaultTestRun(UnityTestFunction Func, const char* FuncName, int FuncLineNum)
{
    Unity.CurrentTestName = FuncName;
    Unity.CurrentTestLineNumber = FuncLineNum;
    Unity.NumberOfTests++;
    
    /* Call user setUp if exists */
    setUp();
    
    if (setjmp(Unity.AbortFrame) == 0)
    {
        Func();
    }
    
    /* Call user tearDown if exists */
    tearDown();
    
    UnityConcludeTest();
}

/*-------------------------------------------------------
 * Assertion Helper Functions
 *-------------------------------------------------------*/

static void UnityTestResultsBegin(const char* file, int line)
{
    UnityPrint(file);
    UnityPrint(":");
    UnityPrintNumber(line);
    UnityPrint(":");
    UnityPrint(Unity.CurrentTestName);
    UnityPrint(":");
}

static void UnityTestResultsFailBegin(int line)
{
    UnityTestResultsBegin(Unity.TestFile, line);
    UnityPrint("FAIL:");
}

static void UnityAddMsgIfSpecified(const char* msg)
{
    if (msg)
    {
        UnityPrint(" ");
        UnityPrint(msg);
    }
}

static void UnityPrintExpectedAndActualStrings(const char* expected, const char* actual)
{
    UnityPrint(" Expected '");
    UnityPrint(expected ? expected : "NULL");
    UnityPrint("' Was '");
    UnityPrint(actual ? actual : "NULL");
    UnityPrint("'");
}

/*-------------------------------------------------------
 * Assertion Functions
 *-------------------------------------------------------*/

void UnityFail(const char* message, int line)
{
    Unity.TestFailures++;
    Unity.CurrentTestFailed = 1;
    UnityTestResultsFailBegin(line);
    UnityAddMsgIfSpecified(message);
    UnityPrintNewLine();
    longjmp(Unity.AbortFrame, 1);
}

void UnityIgnore(const char* message, int line)
{
    (void)line;  /* Unused in ignore */
    Unity.TestIgnores++;
    Unity.CurrentTestIgnored = 1;
    UnityAddMsgIfSpecified(message);
    longjmp(Unity.AbortFrame, 1);
}

void UnityMessage(const char* message, int line)
{
    UnityTestResultsBegin(Unity.TestFile, line);
    UnityPrint("INFO:");
    UnityAddMsgIfSpecified(message);
    UnityPrintNewLine();
}

void UnityAssertEqualNumber(const int expected,
                            const int actual,
                            const char* msg,
                            const unsigned int lineNumber,
                            const UNITY_DISPLAY_STYLE_T style)
{
    if (expected != actual)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected ");
        
        switch (style)
        {
            case UNITY_DISPLAY_STYLE_UINT:
                UnityPrintUnsigned((unsigned)expected);
                UnityPrint(" Was ");
                UnityPrintUnsigned((unsigned)actual);
                break;
            case UNITY_DISPLAY_STYLE_HEX8:
                UnityPrintHex(expected, 2);
                UnityPrint(" Was ");
                UnityPrintHex(actual, 2);
                break;
            case UNITY_DISPLAY_STYLE_HEX16:
                UnityPrintHex(expected, 4);
                UnityPrint(" Was ");
                UnityPrintHex(actual, 4);
                break;
            case UNITY_DISPLAY_STYLE_HEX32:
                UnityPrintHex(expected, 8);
                UnityPrint(" Was ");
                UnityPrintHex(actual, 8);
                break;
            default:
                UnityPrintNumber(expected);
                UnityPrint(" Was ");
                UnityPrintNumber(actual);
                break;
        }
        
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertEqualInt(const int expected,
                         const int actual,
                         const char* msg,
                         const unsigned int lineNumber)
{
    UnityAssertEqualNumber(expected, actual, msg, lineNumber, UNITY_DISPLAY_STYLE_INT);
}

void UnityAssertBits(const int mask,
                     const int expected,
                     const int actual,
                     const char* msg,
                     const unsigned int lineNumber)
{
    if ((mask & expected) != (mask & actual))
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected ");
        UnityPrintHex(expected & mask, 8);
        UnityPrint(" Was ");
        UnityPrintHex(actual & mask, 8);
        UnityPrint(" (Mask ");
        UnityPrintHex(mask, 8);
        UnityPrint(")");
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertEqualString(const char* expected,
                            const char* actual,
                            const char* msg,
                            const unsigned int lineNumber)
{
    /* Handle NULL cases */
    if (expected == NULL && actual == NULL) return;
    
    if (expected == NULL || actual == NULL || strcmp(expected, actual) != 0)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrintExpectedAndActualStrings(expected, actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertEqualMemory(const void* expected,
                            const void* actual,
                            const unsigned int length,
                            const char* msg,
                            const unsigned int lineNumber)
{
    if (expected == NULL && actual == NULL) return;
    
    if (expected == NULL || actual == NULL || memcmp(expected, actual, length) != 0)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Memory Mismatch");
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertNumbersWithin(const int delta,
                              const int expected,
                              const int actual,
                              const char* msg,
                              const unsigned int lineNumber)
{
    int diff = actual - expected;
    if (diff < 0) diff = -diff;
    
    if (diff > delta)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Values Not Within Delta ");
        UnityPrintNumber(delta);
        UnityPrint(" Expected ");
        UnityPrintNumber(expected);
        UnityPrint(" Was ");
        UnityPrintNumber(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

/*-------------------------------------------------------
 * Floating Point Assertions
 *-------------------------------------------------------*/

#ifdef UNITY_INCLUDE_FLOAT
void UnityAssertFloatsWithin(const float delta,
                             const float expected,
                             const float actual,
                             const char* msg,
                             const unsigned int lineNumber)
{
    float diff = actual - expected;
    if (diff < 0.0f) diff = -diff;
    
    if (isnan(expected) && isnan(actual)) return;
    if (isnan(expected) || isnan(actual) || diff > delta)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected ");
        UnityPrintFloat(expected);
        UnityPrint(" +/- ");
        UnityPrintFloat(delta);
        UnityPrint(" Was ");
        UnityPrintFloat(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertEqualFloat(const float expected,
                           const float actual,
                           const char* msg,
                           const unsigned int lineNumber)
{
    /* Use small delta for floating point comparison */
    UnityAssertFloatsWithin(0.00001f, expected, actual, msg, lineNumber);
}

void UnityAssertFloatIsInf(const float actual,
                           const char* msg,
                           const unsigned int lineNumber)
{
    if (!isinf(actual) || actual < 0)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected Inf Was ");
        UnityPrintFloat(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertFloatIsNegInf(const float actual,
                              const char* msg,
                              const unsigned int lineNumber)
{
    if (!isinf(actual) || actual > 0)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected -Inf Was ");
        UnityPrintFloat(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertFloatIsNaN(const float actual,
                           const char* msg,
                           const unsigned int lineNumber)
{
    if (!isnan(actual))
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected NaN Was ");
        UnityPrintFloat(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}
#endif

#ifdef UNITY_INCLUDE_DOUBLE
void UnityAssertDoublesWithin(const double delta,
                              const double expected,
                              const double actual,
                              const char* msg,
                              const unsigned int lineNumber)
{
    double diff = actual - expected;
    if (diff < 0.0) diff = -diff;
    
    if (isnan(expected) && isnan(actual)) return;
    if (isnan(expected) || isnan(actual) || diff > delta)
    {
        Unity.TestFailures++;
        Unity.CurrentTestFailed = 1;
        UnityTestResultsFailBegin(lineNumber);
        UnityPrint(" Expected ");
        UnityPrintDouble(expected);
        UnityPrint(" +/- ");
        UnityPrintDouble(delta);
        UnityPrint(" Was ");
        UnityPrintDouble(actual);
        UnityAddMsgIfSpecified(msg);
        UnityPrintNewLine();
        longjmp(Unity.AbortFrame, 1);
    }
}

void UnityAssertEqualDouble(const double expected,
                            const double actual,
                            const char* msg,
                            const unsigned int lineNumber)
{
    /* Use small delta for double comparison */
    UnityAssertDoublesWithin(0.00000000001, expected, actual, msg, lineNumber);
}
#endif
