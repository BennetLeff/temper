#pragma once
/* Boxcar decimation of the ADS9224R dual-lane stream. No Pico SDK dependency:
   test/test_boxcar.c compiles this file with the host C compiler.

   Input: one packed 32-bit word per 1 MSPS conversion, bits[31:0] =
   B15,A15,...,B0,A0 (two's complement), exactly as the PIO autopushes it.
   Output: for each run of `decimation` consecutive conversions, the int32 sum
   of channel A then the int32 sum of channel B. The extremes record the most
   negative and most positive single conversion seen on each channel. */
#include <stdbool.h>
#include <stdint.h>

#define BOXCAR_MAX_DECIMATION 20u

typedef struct {
    int32_t *out;        /* 2 * count int32: A sum, B sum per output sample */
    uint32_t decimation; /* conversions per output sample, 1..20 */
    uint32_t count;      /* output samples requested */
    uint32_t written;    /* complete output samples stored */
    uint32_t left;       /* conversions still needed for the current output */
    int32_t sum_a, sum_b;
    int32_t min_a, max_a, min_b, max_b;
} boxcar_t;

/* A in bits[15:0], B in bits[31:16]: the inverse of the PIO bit interleave. */
uint32_t boxcar_deinterleave(uint32_t packed);
void boxcar_init(boxcar_t *box, int32_t *out, uint32_t decimation, uint32_t count);
/* Consume ring words with absolute indices [from, to). ring_mask = words - 1. */
void boxcar_feed(boxcar_t *box, const volatile uint32_t *ring, uint32_t ring_mask,
                 uint32_t from, uint32_t to);
/* True when no ring slot read since `from` can have been overwritten: the
   producer had issued at most `issued_after` words, measured after the reads.
   Word w overwrites the slot of word w - ring_words. */
static inline bool boxcar_ring_intact(uint32_t from, uint32_t issued_after,
                                      uint32_t ring_words) {
    return issued_after - from <= ring_words;
}
/* While the producer runs, the newest words it has issued may not have landed
   in RAM yet; leave this many unread (4 µs at 1 MSPS). */
#define BOXCAR_RING_LAG_WORDS 4u
/* Producer progress: total words issued so far (for DMA: total - TRANS_COUNT). */
typedef uint32_t (*boxcar_issued_fn)(const void *context);
/* One consumer step: sum every word that is safe to read, advancing *consumed.
   producer_done must be sampled before this call. Returns false if any slot
   read in this step may have been overwritten (overrun): the capture is invalid. */
bool boxcar_drain(boxcar_t *box, const volatile uint32_t *ring, uint32_t ring_words,
                  uint32_t *consumed, bool producer_done, boxcar_issued_fn issued,
                  const void *context);
/* Word-aligned 8-byte header: A min, A max, B min, B max as little-endian int16. */
void boxcar_extremes(const boxcar_t *box, uint32_t header[2]);
