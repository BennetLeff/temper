#ifndef TEMPER_POWER_ENTRY_AVR64DA32_BOOT_CONTRACT_H
#define TEMPER_POWER_ENTRY_AVR64DA32_BOOT_CONTRACT_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t wdtcfg;
    uint8_t bodcfg;
    uint8_t osccfg;
    uint8_t syscfg0;
} pe_avr_fuses_t;

/* Exact programmed-fuse readback is required before the receiver runtime
 * starts. Zero-filled expectations deliberately keep the default image
 * locked. This check does not replace a programmer readback or pin captures. */
bool pe_avr_boot_fuses_ok(pe_avr_fuses_t actual, pe_avr_fuses_t expected);

#endif
