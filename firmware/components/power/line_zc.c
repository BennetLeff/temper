#include "line_zc.h"
#include <string.h>
static void unlock(line_zc_t *z)
{
    z->good = 0;
    z->locked = false;
    z->have_centre = false;
}
void line_zc_init(line_zc_t *z, const line_zc_config_t *c)
{
    memset(z, 0, sizeof *z);
    z->cfg = *c;
}
void line_zc_edge(line_zc_t *z, uint64_t t, bool level)
{
    if (level == z->high) return;          /* duplicate level report */
    z->high = level;
    if (level) {                           /* rising: pulse start */
        z->rise_us = t;
        z->have_rise = true;
        return;
    }
    if (!z->have_rise || t < z->rise_us) return;
    z->have_rise = false;
    uint64_t width = t - z->rise_us;
    if (width < z->cfg.min_width_us || width > z->cfg.max_width_us) { unlock(z); return; }
    uint64_t centre = z->rise_us + width / 2 - z->cfg.cal_offset_us;
    if (z->have_centre) {
        uint64_t half = centre - z->last_centre_us;
        if (centre < z->last_centre_us || half < z->cfg.min_half_us || half > z->cfg.max_half_us) {
            unlock(z);
            z->last_centre_us = centre;
            z->have_centre = true;
            return;
        }
        /* first-order smoothing of the half-period */
        z->half_us = z->half_us ? (uint32_t)((3u * z->half_us + half) / 4u) : (uint32_t)half;
        if (z->good < 255) z->good++;
    }
    z->last_centre_us = centre;
    z->have_centre = true;
    if (z->good >= LINE_ZC_LOCK_PULSES - 1) {
        z->locked = true;
        z->next_us = centre + z->half_us;  /* the zero after the one just measured */
    }
}
bool line_zc_poll(line_zc_t *z, uint64_t now, uint64_t *zero_us)
{
    if (!z->locked) return false;
    if (now > z->last_centre_us + 3u * z->half_us / 2u + z->half_us) { unlock(z); return false; }
    if (now < z->next_us) return false;
    *zero_us = z->next_us;
    z->next_us += z->half_us;              /* re-anchored by the next measured centre */
    return true;
}
