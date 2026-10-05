#include "contact_guard.h"

extern uint32_t get_time_ms(void);
static bool have_sample;
static bool release_seen;
static bool acquiring;
static uint32_t last_sample_ms;
static uint32_t acquisition_start_ms;
static uint32_t release_start_ms;
static contact_sample_state_t last_state;

void contact_guard_reset(void) {
    have_sample = false;
    release_seen = false;
    acquiring = false;
    last_state = CONTACT_SAMPLE_UNAVAILABLE;
}

void contact_guard_submit(contact_sample_state_t state, uint32_t sampled_at_ms) {
    uint32_t now = get_time_ms();
    /* Unsigned age also rejects future/reversed time, permitting normal wrap.
     * Never accept a gap as continuous acquisition or keep an old release proof. */
    if ((uint32_t)(now - sampled_at_ms) >= CONTACT_MAX_SAMPLE_AGE_MS ||
        state == CONTACT_SAMPLE_UNAVAILABLE ||
        (state != CONTACT_SAMPLE_RELEASED && state != CONTACT_SAMPLE_LOADED)) {
        contact_guard_reset();
        return;
    }
    if (have_sample) {
        uint32_t delta = sampled_at_ms - last_sample_ms;
        if (delta == 0) {
            /* Contradictory evidence must revoke permission even at one timestamp. */
            if (state != last_state) contact_guard_reset();
            return; /* an identical replay is not a new observation */
        }
        if (delta >= UINT32_C(0x80000000)) {
            contact_guard_reset();
            return;
        }

        if (delta >= CONTACT_MAX_SAMPLE_AGE_MS) contact_guard_reset();
    }
    have_sample = true;
    last_sample_ms = sampled_at_ms;

    if (state == CONTACT_SAMPLE_RELEASED) {
        if (last_state != CONTACT_SAMPLE_RELEASED) {
            release_start_ms = sampled_at_ms;
            release_seen = false;
        }
        if ((uint32_t)(sampled_at_ms - release_start_ms) >= CONTACT_RELEASE_MS)
            release_seen = true;

        acquiring = false;
    } else if (release_seen && !acquiring) {
        acquisition_start_ms = sampled_at_ms;
        acquiring = true;
    }
    last_state = state;
}

bool contact_guard_valid(uint32_t now_ms) {
    if (!have_sample ||
        (uint32_t)(now_ms - last_sample_ms) >= CONTACT_MAX_SAMPLE_AGE_MS) {
        contact_guard_reset();
        return false;
    }
    return last_state == CONTACT_SAMPLE_LOADED && release_seen && acquiring &&
           (uint32_t)(last_sample_ms - acquisition_start_ms) >= CONTACT_ACQUIRE_MS;
}
