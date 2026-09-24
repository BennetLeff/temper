#ifndef TEMPER_DIAGNOSTIC_LOCKOUT_H
#define TEMPER_DIAGNOSTIC_LOCKOUT_H

#include <stdbool.h>

/* Platform-free pin order used by the diagnostic image and its host test.
 * The callback must load the GPIO output latch before enabling direction. */
typedef bool (*diagnostic_drive_pin_t)(void *context, int pin, bool high);

bool diagnostic_lockout_apply(diagnostic_drive_pin_t drive, void *context);

#endif
