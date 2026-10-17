#include "line_zc.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static const line_zc_config_t CFG = {.min_width_us = 300, .max_width_us = 4000,
                                     .min_half_us = 7833, .max_half_us = 8834, .cal_offset_us = 0};
/* Feed pulses centred on true zeros of a line at freq_hz, with +/-jit_us edge jitter. */
static int run(double freq_hz, int jit_us, int pulses, int drop_at, uint64_t *max_err_us)
{
    line_zc_t z; line_zc_init(&z, &CFG);
    double half = 1e6 / (2 * freq_hz);
    int events = 0; *max_err_us = 0;
    uint64_t now = 100000;
    for (int k = 0; k < pulses; k++) {
        double zero = 100000 + k * half;
        if (k == drop_at) continue;
        int jr = jit_us ? (rand() % (2 * jit_us + 1)) - jit_us : 0;
        int jf = jit_us ? (rand() % (2 * jit_us + 1)) - jit_us : 0;
        uint64_t rise = (uint64_t)(zero - 1000 + jr), fall = (uint64_t)(zero + 1000 + jf);
        for (; now < fall + (uint64_t)half - 2200; now += 10) {
            if (now == rise - rise % 10) line_zc_edge(&z, rise, true);
            if (now == fall - fall % 10) line_zc_edge(&z, fall, false);
            uint64_t zp;
            if (line_zc_poll(&z, now, &zp)) {
                events++;
                double nearest = 100000 + half * (double)(long)((zp - 100000 + half / 2) / half);
                uint64_t err = (uint64_t)((zp > nearest) ? zp - nearest : nearest - zp);
                if (err > *max_err_us) *max_err_us = err;
                assert(now - zp <= 10);    /* delivered fresh, at the predicted instant */
            }
        }
    }
    return events;
}
int main(void)
{
    uint64_t err;
    srand(1);
    int ev = run(60.0, 0, 40, -1, &err);
    printf("60 Hz clean: %d events, max error %llu us\n", ev, (unsigned long long)err);
    assert(ev >= 30 && err <= 20);
    ev = run(60.0, 50, 200, -1, &err);
    printf("60 Hz +/-50 us edge jitter: %d events, max error %llu us\n", ev, (unsigned long long)err);
    assert(ev >= 180 && err <= 150);
    ev = run(59.5, 0, 40, -1, &err); assert(ev >= 30 && err <= 40);
    ev = run(60.5, 0, 40, -1, &err); assert(ev >= 30 && err <= 40);
    ev = run(50.0, 0, 40, -1, &err); assert(ev == 0);                 /* 10 ms half-period: refused */
    /* A missing pulse drops lock; it re-locks after LINE_ZC_LOCK_PULSES good pulses. */
    ev = run(60.0, 0, 40, 20, &err); assert(ev >= 25 && ev < 36);
    /* No locking before LINE_ZC_LOCK_PULSES pulses, and a glitch pulse unlocks. */
    line_zc_t z; line_zc_init(&z, &CFG); uint64_t zp;
    for (int k = 0; k < 3; k++) { line_zc_edge(&z, 1000 + k * 8333, true); line_zc_edge(&z, 3000 + k * 8333, false); }
    assert(!line_zc_poll(&z, 30000, &zp));
    line_zc_edge(&z, 1000 + 3 * 8333, true); line_zc_edge(&z, 3000 + 3 * 8333, false);
    assert(z.locked);
    line_zc_edge(&z, 30000, true); line_zc_edge(&z, 30050, false);   /* 50 us glitch */
    assert(!z.locked && !line_zc_poll(&z, 40000, &zp));
    puts("line_zc: lock, prediction, jitter, frequency window, dropout and glitch checks PASS");
    return 0;
}
