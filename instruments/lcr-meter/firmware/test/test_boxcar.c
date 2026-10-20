/* Host test for src/boxcar.c, built with the system C compiler:
     cc -std=c11 -O2 -Wall -Wextra -Werror -I../src test_boxcar.c ../src/boxcar.c
   It checks the deinterleave against the PIO bit order, the boxcar sums and
   extremes against a direct reference, the ring-overrun detector against a
   simulated DMA producer, and a golden payload CRC shared with the host tests. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "boxcar.h"

static int failures = 0;
#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #condition); \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static uint32_t rng_state;
static uint32_t xorshift32(void) {
    uint32_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return rng_state = x;
}

/* PIO order: `in pins, 2` shifts left, so bit 2i is A_i and bit 2i+1 is B_i. */
static uint32_t pack(int16_t a, int16_t b) {
    uint32_t word = 0;
    for (uint32_t bit = 0; bit < 16u; ++bit) {
        word |= (((uint32_t)(uint16_t)a >> bit) & 1u) << (2u * bit);
        word |= (((uint32_t)(uint16_t)b >> bit) & 1u) << (2u * bit + 1u);
    }
    return word;
}
static int16_t lane(uint32_t packed, uint32_t channel) {
    uint16_t value = 0;
    for (uint32_t bit = 0; bit < 16u; ++bit)
        value |= (uint16_t)(((packed >> (2u * bit + channel)) & 1u) << bit);
    return (int16_t)value;
}

static void reference(const uint32_t *stream, uint32_t decimation, uint32_t count, int32_t *sums,
                      int32_t extremes[4]) {
    extremes[0] = extremes[2] = INT16_MAX;
    extremes[1] = extremes[3] = INT16_MIN;
    for (uint32_t k = 0; k < count; ++k) {
        int64_t sa = 0, sb = 0;
        for (uint32_t j = 0; j < decimation; ++j) {
            int32_t a = lane(stream[k * decimation + j], 0);
            int32_t b = lane(stream[k * decimation + j], 1);
            sa += a;
            sb += b;
            if (a < extremes[0]) extremes[0] = a;
            if (a > extremes[1]) extremes[1] = a;
            if (b < extremes[2]) extremes[2] = b;
            if (b > extremes[3]) extremes[3] = b;
        }
        sums[2 * k] = (int32_t)sa;
        sums[2 * k + 1] = (int32_t)sb;
    }
}

/* Simulated DMA: each issued() call advances by a random 0..max_step words and
   writes them to the ring at once, i.e. before the reads that follow; the
   newest LAG-1 issued words stay "in flight" (not yet in RAM). One drain step
   spans three advances (the previous step's re-check, this step's two calls),
   so max_step <= (64 - 4) / 3 = 20 can never lap a 64-word ring. */
typedef struct {
    const uint32_t *stream;
    uint32_t total, issued, landed;
    uint32_t *ring;
    uint32_t ring_words;
    uint32_t max_step;
    uint32_t calls;
} producer_t;
static void land(producer_t *p, uint32_t upto) {
    for (; p->landed < upto; ++p->landed) p->ring[p->landed & (p->ring_words - 1u)] = p->stream[p->landed];
}
static uint32_t producer_issued(const void *context) {
    producer_t *p = (producer_t *)(uintptr_t)context;
    ++p->calls;
    uint32_t step = p->max_step ? xorshift32() % (p->max_step + 1u) : 0u;
    p->issued = p->issued + step > p->total ? p->total : p->issued + step;
    uint32_t in_flight = BOXCAR_RING_LAG_WORDS - 1u;
    land(p, p->issued > in_flight ? p->issued - in_flight : 0u);
    return p->issued;
}

/* Returns true when the run finished without a reported overrun. */
static bool run_ring(const uint32_t *stream, uint32_t decimation, uint32_t count, uint32_t ring_words,
                     uint32_t max_step, int32_t *out, boxcar_t *box) {
    uint32_t *ring = calloc(ring_words, sizeof(uint32_t));
    memset(ring, 0xa5, ring_words * sizeof(uint32_t));
    producer_t p = {stream, decimation * count, 0, 0, ring, ring_words, max_step, 0};
    boxcar_init(box, out, decimation, count);
    uint32_t consumed = 0;
    bool intact = true;
    while (intact && consumed < p.total) {
        bool done = p.issued == p.total;
        if (done) land(&p, p.total); /* DMA idle: every issued word has landed */
        intact = boxcar_drain(box, ring, ring_words, &consumed, done, producer_issued, &p);
    }
    free(ring);
    return intact;
}

static void test_deinterleave(void) {
    rng_state = 0x9e3779b9u;
    const int16_t corners[] = {0, 1, -1, 32767, -32768, 0x1234, (int16_t)0xa55a};
    for (size_t i = 0; i < sizeof corners / sizeof corners[0]; ++i)
        for (size_t j = 0; j < sizeof corners / sizeof corners[0]; ++j) {
            uint32_t ab = boxcar_deinterleave(pack(corners[i], corners[j]));
            CHECK((int16_t)(ab & 0xffffu) == corners[i]);
            CHECK((int16_t)(ab >> 16) == corners[j]);
        }
    for (int i = 0; i < 200000; ++i) {
        uint32_t w = xorshift32();
        uint32_t ab = boxcar_deinterleave(w);
        CHECK((int16_t)(ab & 0xffffu) == lane(w, 0));
        CHECK((int16_t)(ab >> 16) == lane(w, 1));
    }
}

static void test_sums_and_extremes(void) {
    enum { COUNT = 517 };
    static uint32_t stream[BOXCAR_MAX_DECIMATION * COUNT];
    static int32_t out[2 * COUNT], expect[2 * COUNT];
    for (uint32_t decimation = 1; decimation <= BOXCAR_MAX_DECIMATION; ++decimation) {
        rng_state = 0x2545f491u + decimation;
        for (uint32_t i = 0; i < decimation * COUNT; ++i) stream[i] = xorshift32();
        /* Full-scale codes on both lanes must be summed exactly and reported. */
        stream[3] = pack(-32768, 32767);
        stream[decimation * COUNT - 1u] = pack(32767, -32768);
        int32_t extremes[4];
        reference(stream, decimation, COUNT, expect, extremes);
        boxcar_t box;
        memset(out, 0, sizeof out);
        CHECK(run_ring(stream, decimation, COUNT, 64, 18, out, &box));
        CHECK(box.written == COUNT);
        CHECK(memcmp(out, expect, sizeof(int32_t) * 2u * COUNT) == 0);
        CHECK(box.min_a == -32768 && box.max_a == 32767 && box.min_b == -32768 && box.max_b == 32767);
        CHECK(box.min_a == extremes[0] && box.max_a == extremes[1]);
        CHECK(box.min_b == extremes[2] && box.max_b == extremes[3]);
        /* The largest possible sum, 20 * -32768, fits int32 with ample margin. */
        for (uint32_t i = 0; i < decimation * COUNT; ++i) stream[i] = pack(-32768, 32767);
        reference(stream, decimation, COUNT, expect, extremes);
        CHECK(run_ring(stream, decimation, COUNT, 64, 18, out, &box));
        CHECK(out[0] == -32768 * (int32_t)decimation && out[1] == 32767 * (int32_t)decimation);
        CHECK(memcmp(out, expect, sizeof(int32_t) * 2u * COUNT) == 0);
    }
    /* A single clipped conversion in an otherwise quiet record is reported. */
    for (uint32_t i = 0; i < 20u * 300u; ++i) stream[i] = pack((int16_t)(i % 7), -(int16_t)(i % 5));
    stream[4321] = pack(32700, 0);
    boxcar_t box;
    CHECK(run_ring(stream, 20, 300, 64, 18, out, &box));
    CHECK(box.max_a == 32700 && box.min_a == 0 && box.max_b == 0 && box.min_b == -4);
}

static void test_overrun_detection(void) {
    CHECK(boxcar_ring_intact(100, 164, 64));  /* word 164 would overwrite word 100: not yet issued */
    CHECK(!boxcar_ring_intact(100, 165, 64)); /* word 164 issued: word 100's slot may be lost */
    CHECK(boxcar_ring_intact(0xfffffff0u, 0x00000030u, 64)); /* index wrap */
    enum { COUNT = 400 };
    static uint32_t stream[BOXCAR_MAX_DECIMATION * COUNT];
    static int32_t out[2 * COUNT], expect[2 * COUNT];
    int clean = 0, overruns = 0;
    for (uint32_t trial = 0; trial < 400; ++trial) {
        uint32_t decimation = 1u + trial % BOXCAR_MAX_DECIMATION;
        rng_state = 0x6b8b4567u + trial;
        for (uint32_t i = 0; i < decimation * COUNT; ++i) stream[i] = xorshift32();
        int32_t extremes[4];
        reference(stream, decimation, COUNT, expect, extremes);
        boxcar_t box;
        /* Step limits 16..27 straddle the 20-word no-lap bound of a 64-word ring. */
        if (run_ring(stream, decimation, COUNT, 64, 16u + trial % 12u, out, &box)) {
            ++clean;
            /* Soundness: no reported overrun implies every word was read intact. */
            CHECK(memcmp(out, expect, sizeof(int32_t) * 2u * COUNT) == 0);
        } else {
            ++overruns;
        }
    }
    printf("overrun trials: %d clean (bit-exact), %d reported overrun\n", clean, overruns);
    CHECK(clean > 100 && overruns > 100);
    /* A single producer burst larger than the ring is always detected. */
    rng_state = 1;
    for (uint32_t i = 0; i < 20u * COUNT; ++i) stream[i] = xorshift32();
    boxcar_t box;
    CHECK(!run_ring(stream, 20, COUNT, 64, 0x10000u, out, &box));
}

/* Payload bytes as transmitted: extremes header, then A,B int32 sums. */
static uint32_t crc32(const uint8_t *p, size_t length) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= p[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
static void put32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}
/* Shared with host/tests/cli.rs (golden_payload_matches_firmware_vector). */
#define GOLDEN_DECIMATION 7u
#define GOLDEN_COUNT 300u
#define GOLDEN_SEED 0x12345678u
#define GOLDEN_CRC 0x2b378b6fu
static void test_golden_payload(void) {
    static uint32_t stream[GOLDEN_DECIMATION * GOLDEN_COUNT];
    static int32_t out[2 * GOLDEN_COUNT];
    static uint8_t bytes[8 + 8 * GOLDEN_COUNT];
    rng_state = GOLDEN_SEED;
    for (uint32_t i = 0; i < GOLDEN_DECIMATION * GOLDEN_COUNT; ++i) stream[i] = xorshift32();
    boxcar_t box;
    CHECK(run_ring(stream, GOLDEN_DECIMATION, GOLDEN_COUNT, 4096, 300, out, &box));
    uint32_t header[2];
    boxcar_extremes(&box, header);
    put32(bytes, header[0]);
    put32(bytes + 4, header[1]);
    for (uint32_t i = 0; i < 2 * GOLDEN_COUNT; ++i) put32(bytes + 8 + 4 * i, (uint32_t)out[i]);
    uint32_t crc = crc32(bytes, sizeof bytes);
    printf("golden payload: decimation %u, count %u, seed 0x%08x, CRC32 0x%08x\n", GOLDEN_DECIMATION,
           GOLDEN_COUNT, GOLDEN_SEED, crc);
    CHECK(crc == GOLDEN_CRC);
}

int main(void) {
    CHECK(crc32((const uint8_t *)"123456789", 9) == 0xcbf43926u);
    test_deinterleave();
    test_sums_and_extremes();
    test_overrun_detection();
    test_golden_payload();
    if (failures) {
        fprintf(stderr, "FAIL: %d check(s)\n", failures);
        return 1;
    }
    puts("PASS: deinterleave (corners + 200000 random words); boxcar sums/extremes for decimation 1..20 "
         "through a 64-word ring; single-conversion clip extremes; overrun detector soundness "
         "(400 randomized producer schedules) and forced overrun; golden payload CRC");
    return 0;
}
