#include "relay.h"
#include "pins.h"

unsigned relay_set_pin(uint32_t ohm) {
    switch (ohm) {
    case 100u: return PIN_RNG_SET_LO;
    case 5000u: return PIN_RNG_SET_MED;
    case 100000u: return PIN_RNG_SET_HI;
    default: return 0u;
    }
}

static void pulse(const relay_io *io, unsigned pin) {
    io->put(io->context, pin, true);
    io->sleep_ms(io->context, RELAY_PULSE_MS);
    io->put(io->context, pin, false);
}

bool relay_select(const relay_io *io, uint32_t ohm, bool reference) {
    unsigned set_pin = relay_set_pin(ohm);
    if (set_pin == 0u) return false;
    /* Four RESET coils at once: 4 x 28.1 mA through the 2.2 Ohm coil-supply resistor (README). */
    pulse(io, PIN_RNG_RESET);
    pulse(io, set_pin);
    if (reference) pulse(io, PIN_RNG_SET_REF);
    return true;
}
