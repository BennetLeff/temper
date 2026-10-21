#pragma once
/* Period-locked averaging of the TAC5112 TDM stream. No Pico SDK dependency:
   test/test_host.c compiles this file with the host C compiler.

   Input: the RX DMA ring, two 32-bit words per frame (slot 0 = ADC channel 1 = A,
   slot 1 = ADC channel 2 = B). Each word is a left-justified two's-complement sample; the
   sample is the word arithmetically shifted right by 8 (24 bits, full scale +-2^23).
   The DAC repeats a `period`-frame waveform, so frame j of a capture always meets the
   same waveform index (j + c) mod period, c a constant. Averaging mode sums frame j into
   bin j mod period over `frames` frames; raw mode stores each frame's two samples. */
#include <stdbool.h>
#include <stdint.h>

#define SYNCAVG_SHIFT 8
/* While the producer runs, the newest words it has issued may not be in RAM yet. */
#define SYNCAVG_RING_LAG_WORDS 4u

typedef struct {
    int64_t *sum;        /* averaging: 2 * period int64, A[k] then B[k] per bin */
    int32_t *raw;        /* raw: 2 * frames int32, A then B per frame (sum == NULL) */
    uint32_t period;     /* bins; raw mode: unused */
    uint32_t frames;     /* frames to consume */
    uint32_t done;       /* frames consumed */
    uint32_t bin;        /* bin of the next frame */
    int32_t min_a, max_a, min_b, max_b;
} syncavg_t;

void syncavg_init_average(syncavg_t *s, int64_t *sum, uint32_t period, uint32_t frames);
void syncavg_init_raw(syncavg_t *s, int32_t *raw, uint32_t frames);
/* Consume frames [s->done, to). Frame f is ring words start + 2f and start + 2f + 1
   (absolute word indices, masked by ring_mask = ring words - 1). */
void syncavg_feed(syncavg_t *s, const volatile uint32_t *ring, uint32_t ring_mask,
                  uint32_t start, uint32_t to);
/* Producer progress: total words written to the ring since it was armed. */
typedef uint32_t (*syncavg_issued_fn)(const void *context);
/* One consumer step: consume every whole frame that is safe to read. Returns false if a
   ring slot read in this step may have been overwritten (overrun): the capture is invalid. */
bool syncavg_drain(syncavg_t *s, const volatile uint32_t *ring, uint32_t ring_words,
                   uint32_t start, syncavg_issued_fn issued, const void *context);
/* Word-aligned 16-byte header: A min, A max, B min, B max as little-endian int32. */
void syncavg_extremes(const syncavg_t *s, int32_t header[4]);
