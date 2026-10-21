#include "syncavg.h"

#if SYNCAVG_IN_RAM
#include "pico.h"
#define SYNCAVG_HOT(name) __not_in_flash_func(name)
#else
#define SYNCAVG_HOT(name) name
#endif

static void reset(syncavg_t *s, uint32_t frames) {
    s->frames = frames;
    s->done = 0;
    s->bin = 0;
    s->min_a = s->min_b = INT32_MAX;
    s->max_a = s->max_b = INT32_MIN;
}

void syncavg_init_average(syncavg_t *s, int64_t *sum, uint32_t period, uint32_t frames) {
    s->sum = sum;
    s->raw = 0;
    s->period = period;
    for (uint32_t i = 0; i < 2u * period; ++i) sum[i] = 0;
    reset(s, frames);
}

void syncavg_init_raw(syncavg_t *s, int32_t *raw, uint32_t frames) {
    s->sum = 0;
    s->raw = raw;
    s->period = 0;
    reset(s, frames);
}

/* Hot loop. GCC's >> on a negative int32 is arithmetic. Placed in SRAM on the RP2040. */
void SYNCAVG_HOT(syncavg_feed)(syncavg_t *s, const volatile uint32_t *ring, uint32_t ring_mask,
                               uint32_t start, uint32_t to) {
    int32_t min_a = s->min_a, max_a = s->max_a, min_b = s->min_b, max_b = s->max_b;
    uint32_t word = start + 2u * s->done;
    for (uint32_t f = s->done; f < to; ++f, word += 2u) {
        int32_t a = (int32_t)ring[word & ring_mask] >> SYNCAVG_SHIFT;
        int32_t b = (int32_t)ring[(word + 1u) & ring_mask] >> SYNCAVG_SHIFT;
        if (a < min_a) min_a = a;
        if (a > max_a) max_a = a;
        if (b < min_b) min_b = b;
        if (b > max_b) max_b = b;
        if (s->sum) {
            int64_t *bin = s->sum + 2u * s->bin;
            bin[0] += a;
            bin[1] += b;
            if (++s->bin == s->period) s->bin = 0;
        } else {
            s->raw[2u * f] = a;
            s->raw[2u * f + 1u] = b;
        }
    }
    s->done = to;
    s->min_a = min_a;
    s->max_a = max_a;
    s->min_b = min_b;
    s->max_b = max_b;
}

bool SYNCAVG_HOT(syncavg_drain)(syncavg_t *s, const volatile uint32_t *ring, uint32_t ring_words,
                                uint32_t start, syncavg_issued_fn issued, const void *context) {
    uint32_t now = issued(context);
    uint32_t ready = now - SYNCAVG_RING_LAG_WORDS - start; /* words past start, wrapping */
    if ((int32_t)ready <= 0) return true;
    uint32_t to = ready / 2u;
    if (to > s->frames) to = s->frames;
    if (to <= s->done) return true;
    uint32_t from_word = start + 2u * s->done;
    syncavg_feed(s, ring, ring_words - 1u, start, to);
    /* Word w overwrites the slot of word w - ring_words. */
    return issued(context) - from_word <= ring_words;
}

void syncavg_extremes(const syncavg_t *s, int32_t header[4]) {
    header[0] = s->min_a;
    header[1] = s->max_a;
    header[2] = s->min_b;
    header[3] = s->max_b;
}
