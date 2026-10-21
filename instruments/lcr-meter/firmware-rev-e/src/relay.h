#pragma once
/* Latching range relays K1-K3 and the reference relay K4 (docs/rev-e-range-switching.md 3.2).
   No Pico SDK dependency: test/test_host.c runs the sequence against a model of the drivers.

   Each relay is a TQ2SA-L2-5V with a SET and a RESET coil, each on an AO3400A low-side
   driver. The four RESET coils share one driver (PIN_RNG_RESET), so one RESET pulse opens
   every relay. A selection is always: RESET (all four open), then SET of exactly one range
   relay, then, only when asked, SET of K4. One coil driver is on at a time. */
#include <stdbool.h>
#include <stdint.h>

#define RELAY_PULSE_MS 20u /* coil pulse; TQ2SA set and reset time is 4 ms max (TQ2SA.txt line 54) */

typedef struct {
    void *context;
    void (*put)(void *context, unsigned pin, bool on);
    void (*sleep_ms)(void *context, uint32_t ms);
} relay_io;

/* SET coil driver of a range (100, 5000 or 100000 ohm); 0 for any other value. */
unsigned relay_set_pin(uint32_t ohm);
/* RESET all four, SET the range relay of `ohm`, then SET K4 if `reference`. The source must
   already be silent. Returns false, without driving anything, if `ohm` is not a range. */
bool relay_select(const relay_io *io, uint32_t ohm, bool reference);
