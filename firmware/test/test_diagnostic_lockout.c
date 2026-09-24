#include "diagnostic_lockout.h"
#include "power_entry_esp32_adapter.h"
#include "temper_pins.h"

#include <assert.h>
#include <stddef.h>

typedef struct {
    int pins[5];
    bool levels[5];
    size_t count;
    int fail_pin;
} recorder_t;

static bool record_drive(void *context, int pin, bool high) {
    recorder_t *rec = context;
    assert(rec->count < 5);
    rec->pins[rec->count] = pin;
    rec->levels[rec->count] = high;
    rec->count++;
    return pin != rec->fail_pin;
}

static void assert_sequence(const recorder_t *rec) {
    const int expected_pins[5] = {
        PE_ESP_GPIO_STOP_N, PIN_RUNAWAY_CUT, PIN_PWM_HI,
        PIN_PWM_LO, PIN_RELAY_BYPASS,
    };
    const bool expected_levels[5] = {false, true, false, false, false};
    assert(rec->count == 5);
    for (size_t i = 0; i < rec->count; i++) {
        assert(rec->pins[i] == expected_pins[i]);
        assert(rec->levels[i] == expected_levels[i]);
    }
}

int main(void) {
    assert(!diagnostic_lockout_apply(NULL, NULL));

    recorder_t rec = {.fail_pin = -1};
    assert(diagnostic_lockout_apply(record_drive, &rec));
    assert_sequence(&rec);

    /* Every output still gets its cut value after any single failed GPIO
     * write, and the caller learns that the lockout could not be established. */
    for (size_t failed = 0; failed < 5; failed++) {
        rec = (recorder_t){.fail_pin = rec.pins[failed]};
        assert(!diagnostic_lockout_apply(record_drive, &rec));
        assert_sequence(&rec);
    }
    return 0;
}
