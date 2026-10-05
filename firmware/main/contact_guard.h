#ifndef TEMPER_CONTACT_GUARD_H
#define TEMPER_CONTACT_GUARD_H
#include <stdbool.h>
#include <stdint.h>

/* Engineering test budgets, not measured hardware response limits. */
#define CONTACT_RELEASE_MS 100U
#define CONTACT_ACQUIRE_MS 100U
#define CONTACT_MAX_SAMPLE_AGE_MS 50U

typedef enum {
    CONTACT_SAMPLE_UNAVAILABLE = 0,
    CONTACT_SAMPLE_RELEASED,
    CONTACT_SAMPLE_LOADED,
    CONTACT_SAMPLE_FAULT
} contact_sample_state_t;

/* Control-task-only API. No ISR or other task may call it directly.
 * Reset clears evidence and sets contact unavailable. The board currently has NO contact detector backend.
 * A future qualified driver must submit freshly acquired, diagnostically valid
 * force/position evidence; RTD temperature or induction presence is NOT evidence.
 * RELEASED must prove return/unloaded state; LOADED requires both independent
 * mechanical channels consistent. Never refresh a cached sample's timestamp.
 */
void contact_guard_reset(void);
void contact_guard_submit(contact_sample_state_t state, uint32_t sampled_at_ms);
bool contact_guard_valid(uint32_t now_ms);
#endif
