/* Host test for the SDK-free Rev E modules, built with the system C compiler:
     cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -Isrc test/test_host.c src/syncavg.c \
        src/wave.c src/tac5112.c src/relay.c -lm
   (add -DLCR_FS_375K=1 for the 375 kHz build; build.sh runs both).
   It checks the synchronous averager and raw capture against a direct reference with a
   simulated DMA producer (including ring wrap, odd start words and overrun), the waveform
   limit and tone generator, the CRC, the TAC5112 bring-up sequence against a model of the
   register file, and the relay coil sequence against a model of the four drivers. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pins.h"
#include "relay.h"
#include "syncavg.h"
#include "tac5112.h"
#include "wave.h"

static int failures = 0;
#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #condition); \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static uint32_t rng_state = 0x9e3779b9u;
static uint32_t xorshift32(void) {
    uint32_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return rng_state = x;
}

/* ------------------------------------------------------------------ syncavg */
/* A DMA producer writing stream[] into a ring; `issued` words written so far. */
#define RING 64u
static uint32_t ring[RING];
static uint32_t stream[40000];
typedef struct {
    uint32_t issued, step;
} producer;
static uint32_t producer_issued(const void *context) {
    producer *p = (producer *)context;
    /* Each call lets the producer write `step` more words. */
    for (uint32_t i = 0; i < p->step; ++i, ++p->issued) ring[p->issued % RING] = stream[p->issued];
    return p->issued;
}

static void test_average(uint32_t period, uint32_t frames, uint32_t start, uint32_t step) {
    for (uint32_t i = 0; i < sizeof stream / sizeof stream[0]; ++i) stream[i] = xorshift32();
    static int64_t sum[2 * 512], want[2 * 512];
    memset(want, 0, sizeof want);
    int32_t ext[4] = {INT32_MAX, INT32_MIN, INT32_MAX, INT32_MIN};
    for (uint32_t f = 0; f < frames; ++f) {
        int32_t a = (int32_t)stream[start + 2 * f] >> 8, b = (int32_t)stream[start + 2 * f + 1] >> 8;
        want[2 * (f % period)] += a;
        want[2 * (f % period) + 1] += b;
        if (a < ext[0]) ext[0] = a;
        if (a > ext[1]) ext[1] = a;
        if (b < ext[2]) ext[2] = b;
        if (b > ext[3]) ext[3] = b;
    }
    syncavg_t s;
    syncavg_init_average(&s, sum, period, frames);
    producer p = {0, step};
    bool intact = true;
    for (int guard = 0; s.done < frames && guard < 1000000; ++guard)
        intact &= syncavg_drain(&s, ring, RING, start, producer_issued, &p);
    CHECK(intact);
    CHECK(s.done == frames);
    CHECK(memcmp(sum, want, 2 * period * sizeof sum[0]) == 0);
    int32_t header[4];
    syncavg_extremes(&s, header);
    CHECK(memcmp(header, ext, sizeof ext) == 0);
}

static void test_raw(uint32_t frames, uint32_t start) {
    for (uint32_t i = 0; i < sizeof stream / sizeof stream[0]; ++i) stream[i] = xorshift32();
    static int32_t raw[2 * 4096];
    syncavg_t s;
    syncavg_init_raw(&s, raw, frames);
    producer p = {0, 3};
    bool intact = true;
    for (int guard = 0; s.done < frames && guard < 1000000; ++guard)
        intact &= syncavg_drain(&s, ring, RING, start, producer_issued, &p);
    CHECK(intact);
    for (uint32_t f = 0; f < frames; ++f) {
        CHECK(raw[2 * f] == (int32_t)stream[start + 2 * f] >> 8);
        CHECK(raw[2 * f + 1] == (int32_t)stream[start + 2 * f + 1] >> 8);
    }
}

/* A producer that runs ahead by more than the ring between consumer steps. (The test
   producer advances on every issued() call and the drain calls it twice per step.) */
static void test_overrun(void) {
    static int64_t sum[2 * 16];
    syncavg_t s;
    syncavg_init_average(&s, sum, 16, 1000);
    producer p = {0, RING + 8};
    bool intact = true;
    for (int guard = 0; s.done < 1000 && guard < 100000; ++guard)
        intact &= syncavg_drain(&s, ring, RING, 0, producer_issued, &p);
    CHECK(!intact);
    /* Exactly one ring of lead is still safe: the overwritten slot is never read. */
    syncavg_init_average(&s, sum, 16, 1000);
    p.issued = 0;
    p.step = 2;
    intact = true;
    for (int guard = 0; s.done < 1000 && guard < 100000; ++guard)
        intact &= syncavg_drain(&s, ring, RING, 0, producer_issued, &p);
    CHECK(intact);
}

/* ------------------------------------------------------------------ wave */
static void test_wave(void) {
    CHECK(wave_crc32("123456789", 9) == 0xcbf43926u);
    CHECK(wave_crc32_update(wave_crc32_update(0, "1234", 4), "56789", 5) == 0xcbf43926u);
    /* SOURCE_LIMIT_CODE = floor(1.7 / (2 sqrt 2 * 2.0/2.2) * 2^31). */
    double limit = 1.7 / (2.0 * sqrt(2.0) * 2.0 / 2.2) * 2147483648.0;
    CHECK((double)SOURCE_LIMIT_CODE <= limit && limit < (double)SOURCE_LIMIT_CODE + 1.0);

    static int32_t w[WAVE_MAX_PERIOD];
    CHECK(wave_tone(w, 1, WAVE_MIN_PERIOD - 1, 100) == WAVE_ERR_PERIOD);
    CHECK(wave_tone(w, 1, WAVE_MAX_PERIOD + 1, 100) == WAVE_ERR_PERIOD);
    CHECK(wave_tone(w, 0, 375, 100) == WAVE_ERR_FREQUENCY);
    CHECK(wave_tone(w, 2, 375, 0) == WAVE_ERR_LEVEL);
    CHECK(wave_tone(w, 2, 375, SOURCE_LIMIT_MV + 1) == WAVE_ERR_LEVEL);
    /* The frame rate is the build's clock tree, exactly. */
    CHECK((uint64_t)FS_HZ * BCLK_CYCLES * FRAME_BCLKS == SYSTEM_CLOCK_HZ);
#if !LCR_FS_375K
    /* 85 kHz is the last legal tone: 187500 * 34 / 75 = 85000; 35 / 75 is 87.5 kHz. */
    CHECK(wave_tone(w, 34, 75, 1000) == WAVE_OK);
    CHECK(wave_tone(w, 35, 75, 1000) == WAVE_ERR_FREQUENCY);
    /* Temper frequencies: 1 kHz = 2/375, 27 kHz = 18/125, 60 kHz = 8/25. */
    const uint32_t tones[][2] = {{2, 375}, {18, 125}, {8, 25}, {1, 4096}, {301, 4096}};
#else
    /* 85 kHz is the last legal tone: 375000 * 17 / 75 = 85000; 18 / 75 is 90 kHz. */
    CHECK(wave_tone(w, 17, 75, 1000) == WAVE_OK);
    CHECK(wave_tone(w, 18, 75, 1000) == WAVE_ERR_FREQUENCY);
    /* Temper frequencies: 1 kHz = 1/375, 27 kHz = 9/125, 60 kHz = 4/25. */
    const uint32_t tones[][2] = {{1, 375}, {9, 125}, {4, 25}, {1, 4096}, {301, 4096}};
#endif
    for (unsigned t = 0; t < 3; ++t)
        CHECK((uint64_t)FS_HZ * tones[t][0] == (uint64_t)(t == 0 ? 1000u : t == 1 ? 27000u : 60000u) * tones[t][1]);
    /* Each tone at full level stays within the limit and has its single DFT line at bin
       `cycles` with the requested amplitude. */
    for (unsigned t = 0; t < sizeof tones / sizeof tones[0]; ++t) {
        uint32_t cycles = tones[t][0], period = tones[t][1];
        CHECK(wave_tone(w, cycles, period, SOURCE_LIMIT_MV) == WAVE_OK);
        CHECK(wave_check(w, period) == WAVE_OK);
        double re = 0, im = 0, rest = 0;
        for (uint32_t k = 0; k < period; ++k) {
            double phase = 2.0 * 3.14159265358979323846 * (double)cycles * k / period;
            re += w[k] * cos(phase);
            im += w[k] * sin(phase);
        }
        double amplitude = 2.0 * sqrt(re * re + im * im) / period;
        CHECK(fabs(amplitude - SOURCE_LIMIT_CODE) < 2.0);
        CHECK(fabs(re) / period < 1.0); /* sine phase: no cosine component */
        for (uint32_t k = 0; k < period; ++k) {
            double ideal = SOURCE_LIMIT_CODE * sin(2.0 * 3.14159265358979323846 * (double)cycles * k / period);
            rest = fmax(rest, fabs(w[k] - ideal));
        }
        CHECK(rest <= 1.0); /* every word is the rounded ideal */
    }
    w[7] = SOURCE_LIMIT_CODE + 1;
    CHECK(wave_check(w, 16) == WAVE_ERR_LEVEL);
    w[7] = -SOURCE_LIMIT_CODE;
    CHECK(wave_check(w, 16) == WAVE_OK);
}

/* ------------------------------------------------------------------ tac5112 */
typedef struct {
    uint8_t reg[128];
    int awake, nack_at, writes;
    uint32_t elapsed_ms, wake_ms, channel_ms;
    uint8_t order[64];
    bool clock_ok;
} codec_model;
static bool model_write(void *context, uint8_t reg, uint8_t value) {
    codec_model *m = context;
    if (m->writes == m->nack_at) return false;
    m->order[m->writes++ % 64] = reg;
    if (reg == TAC_SW_RESET && value == 1u) {
        memset(m->reg, 0, sizeof m->reg);
        m->awake = 0;
        return true;
    }
    if (reg == TAC_DEV_MISC_CFG && (value & 1u)) {
        m->awake = 1;
        m->wake_ms = m->elapsed_ms;
    }
    if (reg >= 0x10u && reg != TAC_PAGE_CFG && !m->channel_ms) m->channel_ms = m->elapsed_ms;
    m->reg[reg] = value;
    if (reg == TAC_PWR_CFG) {
        uint8_t up = (value & 0x80u ? m->reg[TAC_CH_EN] & 0xF0u : 0u) | (value & 0x40u ? m->reg[TAC_CH_EN] & 0x0Fu : 0u);
        m->reg[TAC_DEV_STS0] = up;
        m->reg[TAC_DEV_STS1] = (uint8_t)((up ? 7u : 6u) << 5);
        m->reg[TAC_CLK_DET_STS0] = (uint8_t)((m->clock_ok ? TAC_RATE_BIN : 15u) << 2);
    }
    return true;
}
static bool model_read(void *context, uint8_t reg, uint8_t *value) {
    codec_model *m = context;
    *value = m->reg[reg & 127u];
    return true;
}
static void model_sleep(void *context, uint32_t ms) { ((codec_model *)context)->elapsed_ms += ms; }

static void test_codec(void) {
    codec_model m = {.nack_at = -1, .clock_ok = true};
    tac5112_io io = {&m, model_write, model_read, model_sleep};
    CHECK(tac5112_start(&io) == TAC_OK);
    CHECK(m.order[0] == TAC_PAGE_CFG && m.order[1] == TAC_SW_RESET);
    CHECK(m.awake);
    CHECK(m.channel_ms >= m.wake_ms + 10u); /* channel registers 10 ms after leaving sleep */
    CHECK(m.order[m.writes - 1] == TAC_PWR_CFG && m.order[m.writes - 2] == TAC_CH_EN);
    CHECK(m.reg[TAC_DEV_MISC_CFG] == 0x09u);
    CHECK(m.reg[TAC_INTF_CFG1] == 0x51u);
#if !LCR_FS_375K
    CHECK(m.reg[TAC_PASI_CFG0] == 0x30u); /* TDM, 32-bit slots */
    /* Low-latency decimation and interpolation filters ([7:6] = 01), HPF all-pass IIR. */
    CHECK(m.reg[TAC_DSP_CFG0] == 0x42u && m.reg[TAC_DSP_CFG1] == 0x42u);
    CHECK(TAC_RATE_BIN == 10u);
#else
    CHECK(m.reg[TAC_PASI_CFG0] == 0x20u); /* TDM, 24-bit slots */
    /* Linear-phase filters ([7:6] = 00), HPF all-pass IIR. */
    CHECK(m.reg[TAC_DSP_CFG0] == 0x02u && m.reg[TAC_DSP_CFG1] == 0x02u);
    CHECK(TAC_RATE_BIN == 5u);
#endif
    CHECK(m.reg[TAC_ADC_CH1_CFG0] == 0x25u && m.reg[TAC_ADC_CH2_CFG0] == 0x25u);
    /* 0x25 = INSRC 00 differential, IMP 10 (40 kOhm), CM_TOL 01, FULLSCALE 0, BW_MODE 1. */
    CHECK((m.reg[TAC_ADC_CH1_CFG0] >> 6) == 0u && ((m.reg[TAC_ADC_CH1_CFG0] >> 4) & 3u) == 2u &&
          ((m.reg[TAC_ADC_CH1_CFG0] >> 2) & 3u) == 1u && (m.reg[TAC_ADC_CH1_CFG0] & 3u) == 1u);
    CHECK(m.reg[TAC_OUT1X_CFG1] == 0x21u);
    CHECK((m.reg[TAC_DSP_CFG0] & 0x3Fu) == 0x02u && (m.reg[TAC_DSP_CFG1] & 0x3Fu) == 0x02u);
    CHECK(m.reg[TAC_CH_EN] == 0xC8u && m.reg[TAC_PWR_CFG] == 0xC0u);
    CHECK(m.reg[TAC_PASI_RX_CH2_CFG] == 0x01u);
    /* ADC-only power for the loopback self-test, then back. */
    CHECK(tac5112_power(&io, TAC_POWER_ADC) == TAC_OK);
    CHECK(tac5112_check(&io, TAC_POWER_ALL) == TAC_ERR_POWER);
    CHECK(tac5112_power(&io, TAC_POWER_ALL) == TAC_OK);

    codec_model bad = {.nack_at = 5, .clock_ok = true};
    io.context = &bad;
    CHECK(tac5112_start(&io) == TAC_ERR_BUS);
    codec_model slow = {.nack_at = -1, .clock_ok = false};
    io.context = &slow;
    CHECK(tac5112_start(&io) == TAC_ERR_CLOCK);
    CHECK(strcmp(tac5112_status_name(TAC_ERR_CLOCK), "codec_clock") == 0);
}

/* ------------------------------------------------------------------ relays */
/* Model of the five AO3400A coil drivers: every edge with its time, and the latched state
   of K1-K4 (a SET pulse closes its relay; the shared RESET pulse opens all four). */
typedef struct {
    uint32_t now_ms;
    bool on[32];
    unsigned events;
    unsigned pin[32];
    bool level[32];
    uint32_t at[32];
    int max_on;
    bool closed[4]; /* K1 (100), K2 (5k), K3 (100k), K4 (reference) */
} relay_model;
static int relay_index(unsigned pin) {
    return pin == PIN_RNG_SET_LO ? 0 : pin == PIN_RNG_SET_MED ? 1 : pin == PIN_RNG_SET_HI ? 2
         : pin == PIN_RNG_SET_REF ? 3 : -1;
}
static void relay_model_put(void *context, unsigned pin, bool on) {
    relay_model *m = context;
    if (m->events < 32u) {
        m->pin[m->events] = pin;
        m->level[m->events] = on;
        m->at[m->events] = m->now_ms;
    }
    ++m->events;
    m->on[pin & 31u] = on;
    int count = 0;
    for (unsigned p = 0; p < 32u; ++p) count += m->on[p];
    if (count > m->max_on) m->max_on = count;
    if (on && pin == PIN_RNG_RESET)
        for (int k = 0; k < 4; ++k) m->closed[k] = false;
    else if (on && relay_index(pin) >= 0) m->closed[relay_index(pin)] = true;
}
static void relay_model_sleep(void *context, uint32_t ms) { ((relay_model *)context)->now_ms += ms; }

static void test_relays(void) {
    /* Distinct drivers; the reference relay is GPIO14 (RNG_SET_REF, RP2040 pin 17). */
    CHECK(PIN_RNG_SET_REF == 14u);
    const unsigned pins[] = {PIN_RNG_RESET, PIN_RNG_SET_LO, PIN_RNG_SET_MED, PIN_RNG_SET_HI, PIN_RNG_SET_REF,
                             PIN_I2S_DIN, PIN_I2S_DOUT, PIN_I2S_BCLK, PIN_I2S_FSYNC, PIN_I2C_SDA, PIN_I2C_SCL,
                             PIN_USB_VBUS, PIN_LED};
    for (unsigned i = 0; i < sizeof pins / sizeof pins[0]; ++i)
        for (unsigned j = i + 1; j < sizeof pins / sizeof pins[0]; ++j) CHECK(pins[i] != pins[j]);
    CHECK(relay_set_pin(100u) == PIN_RNG_SET_LO && relay_set_pin(5000u) == PIN_RNG_SET_MED &&
          relay_set_pin(100000u) == PIN_RNG_SET_HI && relay_set_pin(1000u) == 0u);
    const uint32_t ranges[] = {100u, 5000u, 100000u};
    for (unsigned r = 0; r < 3; ++r)
        for (int reference = 0; reference < 2; ++reference) {
            /* Start from the worst latched state: every relay closed. */
            relay_model m = {.closed = {true, true, true, true}};
            relay_io io = {&m, relay_model_put, relay_model_sleep};
            CHECK(relay_select(&io, ranges[r], reference));
            /* RESET first, then exactly one range SET, then K4 only when asked: one driver on
               at a time, 20 ms pulses, every driver off at the end. */
            unsigned want = reference ? 6u : 4u;
            CHECK(m.events == want);
            CHECK(m.pin[0] == PIN_RNG_RESET && m.level[0] && m.pin[1] == PIN_RNG_RESET && !m.level[1]);
            CHECK(m.pin[2] == relay_set_pin(ranges[r]) && m.level[2] && !m.level[3]);
            if (reference) CHECK(m.pin[4] == PIN_RNG_SET_REF && m.level[4] && !m.level[5]);
            for (unsigned e = 0; e + 1 < want; e += 2) CHECK(m.at[e + 1] - m.at[e] == RELAY_PULSE_MS);
            CHECK(m.max_on == 1);
            for (unsigned p = 0; p < 32u; ++p) CHECK(!m.on[p]);
            for (int k = 0; k < 3; ++k) CHECK(m.closed[k] == ((unsigned)k == r));
            CHECK(m.closed[3] == (reference != 0));
        }
    /* An unknown range drives nothing. */
    relay_model m = {.closed = {false, false, false, true}};
    relay_io io = {&m, relay_model_put, relay_model_sleep};
    CHECK(!relay_select(&io, 1000u, true));
    CHECK(m.events == 0u);
    /* Boot (main.c): RESET then the 100 kOhm range leaves K4 open from any latched state. */
    CHECK(relay_select(&io, 100000u, false));
    CHECK(!m.closed[3] && m.closed[2] && !m.closed[0] && !m.closed[1]);
}

int main(void) {
    test_average(16, 1000, 0, 3);
    test_average(375, 3 * 375, 1, 7);   /* odd start: frames straddle the ring wrap */
    test_average(125, 40 * 125, 5, 2);  /* consumer one frame behind the producer */
    test_average(512, 512, 2, 16);
    /* 19 words per issued() call is the largest the post-read check (issued after the read
       minus the first word read <= ring words) accepts with this model, which advances on
       both of the drain's issued() calls; 20 is flagged although no slot was overwritten.
       The check is conservative by construction: it cannot know when, during the read, the
       producer passed the slot. */
    test_average(25, 25 * 37, 3, 19);
    test_raw(4096, 1);
    test_raw(17, 0);
    test_overrun();
    test_wave();
    test_codec();
    test_relays();
    if (failures) {
        fprintf(stderr, "FAIL: %d checks\n", failures);
        return 1;
    }
    printf("PASS (fs %u Hz): syncavg averaging/raw/extremes/ring wrap/odd start/overrun; wave CRC, limit "
           "derivation, tone lines at 1/27/60 kHz and bounds; TAC5112 bring-up order, values, status; "
           "relays RESET-then-SET, one coil at a time, K4 only with a range, boot opens K4\n",
           FS_HZ);
    return 0;
}
