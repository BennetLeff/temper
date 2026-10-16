/**
 * @file pan_soak_store.c
 * @brief Coil-off lower bound across a power cycle (see header; DECISIONS.md D-SOAKNV).
 */

#include "pan_soak_store.h"

#include <stddef.h>
#include <string.h>

static bool hal_ok(const pss_hal_t *hal)
{
    return hal != NULL && hal->load != NULL && hal->save != NULL && hal->clear != NULL;
}

uint32_t pss_boot(pss_t *s, const pss_hal_t *hal)
{
    if (s == NULL) {
        return 0u;
    }
    memset(s, 0, sizeof(*s));
    if (!hal_ok(hal)) {
        s->disabled = true;
        return 0u;
    }
    uint32_t off_s = 0u;
    if (!hal->load(hal->ctx, &off_s)) {
        return 0u;   /* absent or unreadable: unknown */
    }
    s->token_present = true;
    if (off_s == 0u || off_s > PSS_TOKEN_MAX_S) {
        /* Implausible: unknown. Remove it so it cannot be read again. */
        if (hal->clear(hal->ctx)) {
            s->token_present = false;
            s->clears++;
        } else {
            s->failures++;
            s->disabled = true;
        }
        return 0u;
    }
    /* The coil has been off since the write (a revoke precedes every
     * energising), so this period is the token's: no second write. */
    s->written_this_off = true;
    s->boot_credit_s = off_s;
    return off_s;
}

bool pss_revoke(pss_t *s, const pss_hal_t *hal)
{
    if (s == NULL) {
        return false;
    }
    s->written_this_off = false;
    if (!s->token_present) {
        return true;
    }
    if (!hal_ok(hal) || !hal->clear(hal->ctx)) {
        s->failures++;
        s->disabled = true;
        return false;
    }
    /* Verify: a token that still reads back was not erased. */
    uint32_t v = 0u;
    if (hal->load(hal->ctx, &v)) {
        s->failures++;
        s->disabled = true;
        return false;
    }
    s->token_present = false;
    s->clears++;
    return true;
}

void pss_note(pss_t *s, const pss_hal_t *hal, bool coil_active, float off_s)
{
    if (s == NULL) {
        return;
    }
    if (coil_active) {
        (void)pss_revoke(s, hal);
        return;
    }
    if (s->disabled || s->written_this_off || s->token_present || !(off_s >= (float)PSS_TOKEN_OFF_S) ||
        !hal_ok(hal)) {
        return;
    }
    s->written_this_off = true;   /* one attempt per coil-off period */
    if (!hal->save(hal->ctx, PSS_TOKEN_OFF_S)) {
        s->failures++;
        s->disabled = true;
        return;
    }
    s->token_present = true;
    s->writes++;
}

uint32_t pss_credit_s(const pss_t *s)
{
    return (s != NULL && s->token_present && s->written_this_off) ? PSS_TOKEN_OFF_S : 0u;
}
