/**
 * @file pan_detect_logic.c
 * @brief Pure logic functions from pan detection module (no ESP-IDF dependencies)
 * 
 * This file contains the analyze_edges() function extracted for unit testing.
 * The actual pan_detect.c has ESP-IDF dependencies that prevent host compilation.
 */

#include "../components/control/pan_detect.h"

/* Thresholds from pan_detect.c */
#define DECAY_THRESHOLD_PAN   8     /* Edge count below this = pan present */

/**
 * @brief Analyze edge count to determine pan presence
 * 
 * Logic extracted from pan_detect.c for unit testing.
 */
pan_result_t analyze_edges(uint32_t edges) {
    if (edges == 0) {
        return PAN_DETECT_ERROR;    /* Sensor fault? */
    } else if (edges < 3) {
        return PAN_DETECT_NON_FERROUS; /* Damped instantly (aluminum or short) */
    } else if (edges < DECAY_THRESHOLD_PAN) {
        return PAN_DETECT_FERROUS;  /* Good ferrous pan */
    } else {
        return PAN_DETECT_NONE;     /* Ringing continued (high Q, no pan) */
    }
}
