#include "boxcar.h"

#if BOXCAR_IN_RAM
#include "pico.h"
#define BOXCAR_HOT(name) __not_in_flash_func(name)
#else
#define BOXCAR_HOT(name) name
#endif

/* One byte of the packed word holds four A bits (even positions) and four B
   bits (odd positions). Entry = A nibble in bits[3:0], B nibble in [19:16].
   RAM-resident (filled at init) so the hot loop never waits on XIP flash. */
static uint32_t nibble_table[256];
static bool table_ready = false;

static void build_table(void) {
    for (uint32_t byte = 0; byte < 256u; ++byte) {
        uint32_t value = 0;
        for (uint32_t bit = 0; bit < 4u; ++bit) {
            value |= ((byte >> (2u * bit)) & 1u) << bit;
            value |= ((byte >> (2u * bit + 1u)) & 1u) << (16u + bit);
        }
        nibble_table[byte] = value;
    }
    table_ready = true;
}

uint32_t boxcar_deinterleave(uint32_t packed) {
    if (!table_ready) build_table();
    return nibble_table[packed & 0xffu] | (nibble_table[(packed >> 8) & 0xffu] << 4) |
           (nibble_table[(packed >> 16) & 0xffu] << 8) | (nibble_table[packed >> 24] << 12);
}

void boxcar_init(boxcar_t *box, int32_t *out, uint32_t decimation, uint32_t count) {
    if (!table_ready) build_table();
    box->out = out;
    box->decimation = decimation;
    box->count = count;
    box->written = 0;
    box->left = decimation;
    box->sum_a = box->sum_b = 0;
    box->min_a = box->min_b = INT16_MAX;
    box->max_a = box->max_b = INT16_MIN;
}

/* Hot loop over one contiguous ring span. Placed in SRAM on the RP2040. */
static void BOXCAR_HOT(feed_span)(boxcar_t *box, const volatile uint32_t *p,
                                  const volatile uint32_t *end) {
    const uint32_t *table = nibble_table;
    int32_t sum_a = box->sum_a, sum_b = box->sum_b;
    int32_t min_a = box->min_a, max_a = box->max_a, min_b = box->min_b, max_b = box->max_b;
    uint32_t left = box->left;
    int32_t *out = box->out + 2u * box->written;
    for (; p != end; ++p) {
        uint32_t w = *p;
        uint32_t ab = table[(uint8_t)w] | (table[(uint8_t)(w >> 8)] << 4) |
                      (table[(uint8_t)(w >> 16)] << 8) | (table[w >> 24] << 12);
        int32_t a = (int16_t)(ab & 0xffffu);
        int32_t b = (int16_t)(ab >> 16);
        sum_a += a;
        sum_b += b;
        if (a < min_a) min_a = a;
        if (a > max_a) max_a = a;
        if (b < min_b) min_b = b;
        if (b > max_b) max_b = b;
        if (--left == 0u) {
            out[0] = sum_a;
            out[1] = sum_b;
            out += 2;
            sum_a = sum_b = 0;
            left = box->decimation;
        }
    }
    box->written = (uint32_t)(out - box->out) / 2u;
    box->sum_a = sum_a;
    box->sum_b = sum_b;
    box->min_a = min_a;
    box->max_a = max_a;
    box->min_b = min_b;
    box->max_b = max_b;
    box->left = left;
}

void BOXCAR_HOT(boxcar_feed)(boxcar_t *box, const volatile uint32_t *ring, uint32_t ring_mask,
                             uint32_t from, uint32_t to) {
    uint32_t n = to - from, start = from & ring_mask, first = ring_mask + 1u - start;
    if (n <= first) {
        feed_span(box, ring + start, ring + start + n);
    } else {
        feed_span(box, ring + start, ring + ring_mask + 1u);
        feed_span(box, ring, ring + (n - first));
    }
}

bool BOXCAR_HOT(boxcar_drain)(boxcar_t *box, const volatile uint32_t *ring, uint32_t ring_words,
                              uint32_t *consumed, bool producer_done, boxcar_issued_fn issued,
                              const void *context) {
    uint32_t now = issued(context);
    uint32_t ready = producer_done ? now
                                   : (now > BOXCAR_RING_LAG_WORDS ? now - BOXCAR_RING_LAG_WORDS : 0u);
    if (ready <= *consumed) return true;
    uint32_t from = *consumed;
    boxcar_feed(box, ring, ring_words - 1u, from, ready);
    *consumed = ready;
    return boxcar_ring_intact(from, issued(context), ring_words);
}

void boxcar_extremes(const boxcar_t *box, uint32_t header[2]) {
    header[0] = (uint32_t)(uint16_t)box->min_a | ((uint32_t)(uint16_t)box->max_a << 16);
    header[1] = (uint32_t)(uint16_t)box->min_b | ((uint32_t)(uint16_t)box->max_b << 16);
}
