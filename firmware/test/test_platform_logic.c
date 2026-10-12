/* Pure logic of the ESP32 platform layer (components/platform/platform_logic.c): MAX31865 word ->
 * ohm -> PT100 temperature with the fail-safe sentinels the state machine trips on, the blower
 * full-speed floor (never lowers the fan law), the NVS fault-log ring, display text and the
 * UI-board input decoding. Assertions are the oracle (built with -UNDEBUG). */
#include "platform_logic.h"
#include "max31865.h"
#include "n21_binding.h"
#include "../config.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned tests;
#define TEST(fn) do { fn(); tests++; printf("PASS %s\n", #fn); } while (0)
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

/* word for a resistance, as the MAX31865 would produce it (15-bit code << 1, fault bit clear) */
static uint16_t word_for(float ohm)
{
    return (uint16_t)(((uint16_t)floorf(32768.0f * ohm / MAX31865_RREF_OHM)) << 1);
}

/* ---------------------------------------------------------------- MAX31865 / PT100 */
static void test_word_to_ohm(void)
{
    assert(max31865_rtd_word_to_ohm(0x0000u, MAX31865_RREF_OHM) == 0.0f);
    /* Full scale (code 0x7FFF) is just under RREF. */
    assert(NEAR(max31865_rtd_word_to_ohm(0xFFFEu, MAX31865_RREF_OHM), MAX31865_RREF_OHM * 32767.0f / 32768.0f, 1e-3));
    for (float r = 20.0f; r < 400.0f; r += 7.3f)
        assert(NEAR(max31865_rtd_word_to_ohm(word_for(r), MAX31865_RREF_OHM), r, MAX31865_RREF_OHM / 32768.0f));
}

static void test_fault_bit_and_bad_rref_are_infinite(void)
{
    assert(isinf(max31865_rtd_word_to_ohm(word_for(100.0f) | MAX31865_RTD_WORD_FAULT, MAX31865_RREF_OHM)));
    assert(isinf(max31865_rtd_word_to_ohm(word_for(100.0f), 0.0f)));
    assert(isinf(max31865_rtd_word_to_ohm(word_for(100.0f), NAN)));
    assert(isinf(max31865_rtd_word_to_ohm(word_for(100.0f), -430.0f)));
}

/* The conversion's RREF and the threshold words in config.yaml (derived from the board's r_ref by
 * board_derivations.yaml) must describe the same reference: the words decode to 10 / 300 ohm. */
static void test_rref_matches_threshold_words(void)
{
    float lo = max31865_rtd_word_to_ohm(MAX31865_LOW_THRESHOLD_WORD, MAX31865_RREF_OHM);
    float hi = max31865_rtd_word_to_ohm(MAX31865_HIGH_THRESHOLD_WORD, MAX31865_RREF_OHM);
    float lsb = MAX31865_RREF_OHM / 32768.0f;
    assert(NEAR(lo, RTD_SHORT_FAULT_OHM, lsb));
    assert(NEAR(hi, RTD_OPEN_FAULT_OHM, lsb));
}

static void test_pt100_round_trip_and_table(void)
{
    /* IEC 60751 table values (T >= 0 C form). */
    assert(NEAR(pt100_r_at(0.0f), 100.000, 1e-3));
    assert(NEAR(pt100_r_at(100.0f), 138.506, 2e-3));
    assert(NEAR(pt100_r_at(250.0f), 194.098, 2e-3));
    assert(NEAR(pt100_r_at(300.0f), 212.052, 2e-3));
    for (float t = 0.0f; t <= 850.0f; t += 5.0f) assert(NEAR(pt100_ohm_to_c(pt100_r_at(t)), t, 0.01));
    /* Through the MAX31865 quantisation: within 1 LSB (0.013 ohm, ~0.035 K). */
    for (float t = 0.0f; t <= 300.0f; t += 10.0f)
        assert(NEAR(platform_pan_temperature(true, word_for(pt100_r_at(t)), MAX31865_RREF_OHM), t, 0.05));
}

/* Below 0 C the quadratic ignores the CVD C term. Bound the error against the full equation. */
static void test_pt100_below_zero_error(void)
{
    const double C = -4.183e-12;
    for (double t = -50.0; t < 0.0; t += 1.0) {
        double r = 100.0 * (1.0 + 3.9083e-3 * t - 5.775e-7 * t * t + C * (t - 100.0) * t * t * t);
        float back = pt100_ohm_to_c((float)r);
        assert(NEAR(back, t, 0.03)); /* < 0.03 K down to -50 C */
    }
}

static void test_pan_and_rtd_sentinels(void)
{
    /* No usable word: resistance +inf (state machine: FAULT_PROBE_OPEN; safety.c: !isfinite),
     * temperature NaN (runaway boundary: immediate breach). Never a plausible value. */
    float r = platform_rtd_resistance(false, word_for(110.0f), MAX31865_RREF_OHM);
    assert(isinf(r) && r > 0.0f);
    assert(r > RTD_GROSS_OPEN_DIAGNOSTIC_OHM && r >= RTD_OPEN_FAULT_OHM);
    assert(isnan(platform_pan_temperature(false, word_for(110.0f), MAX31865_RREF_OHM)));
    /* Fault bit set: same. */
    uint16_t w = word_for(110.0f) | MAX31865_RTD_WORD_FAULT;
    assert(isinf(platform_rtd_resistance(true, w, MAX31865_RREF_OHM)));
    assert(isnan(platform_pan_temperature(true, w, MAX31865_RREF_OHM)));
    /* A shorted or never-converted register (0 ohm) is outside the PT100 range: no temperature,
     * and the resistance is at or below the short threshold. */
    assert(isnan(platform_pan_temperature(true, 0x0000u, MAX31865_RREF_OHM)));
    assert(platform_rtd_resistance(true, 0x0000u, MAX31865_RREF_OHM) <= RTD_SHORT_FAULT_OHM);
    /* Healthy word: finite and inside the guard window. */
    r = platform_rtd_resistance(true, word_for(110.0f), MAX31865_RREF_OHM);
    assert(r > RTD_SHORT_FAULT_OHM && r < RTD_OPEN_FAULT_OHM);
    /* Sentinel semantics: NaN would slip through the state machine's ordered comparisons, +inf
     * does not. This is why the resistance sentinel is +inf. */
    float nan = NAN;
    assert(!(nan > RTD_GROSS_OPEN_DIAGNOSTIC_OHM) && !(nan >= RTD_OPEN_FAULT_OHM) && !(nan <= RTD_SHORT_FAULT_OHM));
    assert(INFINITY > IGBT_SHORT_CURRENT_THRESHOLD && !isfinite(INFINITY));
    assert(isnan(pt100_ohm_to_c(INFINITY)) && isnan(pt100_ohm_to_c(NAN)) && isnan(pt100_ohm_to_c(-1.0f)));
}

/* ---------------------------------------------------------------- native-21 over-current sources */
static void test_power_bus_trip(void)
{
    /* healthy: BUS_FAULT low; PERMIT low before the bridge runs is normal (latched at power-up) */
    assert(!platform_power_bus_trip(true, false, false, false));
    assert(!platform_power_bus_trip(true, false, true, false));
    assert(!platform_power_bus_trip(true, false, true, true));
    /* BUS_FAULT high: always tripped */
    assert(platform_power_bus_trip(true, true, true, true));
    assert(platform_power_bus_trip(true, true, false, false));
    /* PERMIT dropped while running */
    assert(platform_power_bus_trip(true, false, false, true));
    /* read-back unknown (no binding): tripped whatever the levels */
    assert(platform_power_bus_trip(false, false, true, false));
}

static void test_power_tank_trip(void)
{
    assert(!platform_power_tank_trip(true, N21_FAULT_NONE));
    assert(platform_power_tank_trip(true, N21_FAULT_TANK_PEAK));
    assert(platform_power_tank_trip(true, N21_FAULT_TANK_RMS));
    assert(platform_power_tank_trip(true, N21_FAULT_CT_MON));      /* current unknown */
    assert(platform_power_tank_trip(true, N21_FAULT_RMS_CHANNEL)); /* current unknown */
    /* other binding faults are not over-current (the binding inhibits power on its own) */
    assert(!platform_power_tank_trip(true, N21_FAULT_HW));
    assert(!platform_power_tank_trip(true, N21_FAULT_VBUS_OVERRANGE));
    assert(!platform_power_tank_trip(true, N21_FAULT_PHASE));
    assert(!platform_power_tank_trip(true, N21_FAULT_CT_ZC_STALE));
    assert(!platform_power_tank_trip(true, N21_FAULT_PWM));
    assert(platform_power_tank_trip(false, N21_FAULT_NONE)); /* unknown: tripped */
}

/* ---------------------------------------------------------------- blower floor */
static void test_blower_floor_never_lowers_speed(void)
{
    /* duty 0 = full speed (C28); duty rises -> speed falls. */
    for (int on = 0; on <= 1; on++)
        for (float d = 0.0f; d <= 0.85f; d += 0.05f) {
            bool o = on;
            float duty = d;
            platform_blower_apply_floor(false, &o, &duty);
            assert(o == (bool)on && duty == d); /* no floor: the fan law's command unchanged */
            platform_blower_apply_floor(true, &o, &duty);
            assert(o && duty == 0.0f); /* floor: on, full speed */
        }
}

static void test_fan_requests(void)
{
    platform_fan_req_t r = {0};
    platform_fan_request_speed(&r, true);
    assert(r.full_speed_floor);
    platform_fan_request_auto(&r, false); /* leaving auto keeps the last request */
    assert(r.full_speed_floor);
    platform_fan_request_auto(&r, true);
    assert(!r.full_speed_floor);
    platform_fan_request_speed(&r, true);
    platform_fan_request_speed(&r, false); /* MIN / MEDIUM / OFF: the fan law decides */
    assert(!r.full_speed_floor);
}

/* ---------------------------------------------------------------- fault log */
static void test_fault_log_ring(void)
{
    platform_fault_log_t log;
    platform_fault_log_init(&log);
    assert(platform_fault_log_valid(&log));
    assert(platform_fault_log_count(&log) == 0 && platform_fault_log_get(&log, 0) == NULL);
    platform_fault_log_new_boot(&log);
    for (uint16_t i = 1; i <= 40; i++) {
        platform_fault_log_append(&log, i, 1000u * i);
        assert(platform_fault_log_valid(&log));
        const platform_fault_rec_t *r = platform_fault_log_get(&log, 0);
        assert(r && r->code == i && r->t_ms == 1000u * i && r->boot == 1);
    }
    assert(platform_fault_log_count(&log) == PLATFORM_FAULT_LOG_LEN);
    /* oldest kept = 40 - 15 = 25 */
    assert(platform_fault_log_get(&log, PLATFORM_FAULT_LOG_LEN - 1)->code == 25);
    assert(platform_fault_log_get(&log, PLATFORM_FAULT_LOG_LEN) == NULL);
}

static void test_fault_log_rejects_corrupt_blob(void)
{
    platform_fault_log_t log;
    platform_fault_log_init(&log);
    platform_fault_log_append(&log, 7, 1);
    log.magic ^= 1u;
    assert(!platform_fault_log_valid(&log));
    platform_fault_log_init(&log);
    platform_fault_log_append(&log, 7, 1);
    log.rec[1].seq = 99; /* seq beyond next_seq */
    assert(!platform_fault_log_valid(&log));
    platform_fault_log_init(&log);
    log.rec[3].seq = 2; /* wrong slot */
    log.next_seq = 5;
    assert(!platform_fault_log_valid(&log));
}

/* ---------------------------------------------------------------- display */
static void test_display_text(void)
{
    char b[16];
    platform_fmt_temperature(b, sizeof b, 104.6f);
    assert(strcmp(b, "105 C") == 0);
    platform_fmt_temperature(b, sizeof b, NAN);
    assert(strcmp(b, "--- C") == 0);
    platform_fmt_countdown(b, sizeof b, 125);
    assert(strcmp(b, "2:05") == 0);
    platform_fmt_countdown(b, sizeof b, 0);
    assert(strcmp(b, "0:00") == 0);
}

static void test_oled_framebuffer(void)
{
    static uint8_t fb[PLATFORM_OLED_FB_BYTES];
    platform_oled_clear(fb);
    platform_oled_set_pixel(fb, 0, 0, 0xF);
    platform_oled_set_pixel(fb, 1, 0, 0x3);
    assert(fb[0] == 0xF3);                                   /* left pixel in the high nibble */
    platform_oled_set_pixel(fb, 255, 63, 0xA);
    assert(fb[PLATFORM_OLED_FB_BYTES - 1] == 0x0A);
    platform_oled_set_pixel(fb, 256, 0, 0xF);                /* clipped, no write */
    platform_oled_set_pixel(fb, 0, 64, 0xF);
    assert(fb[1] == 0x00);
    /* '!' = column 2 rows 0..4 and 6 */
    platform_oled_clear(fb);
    unsigned x = platform_oled_text(fb, 0, 0, 1, "!", 0xF);
    assert(x == 6);
    for (unsigned row = 0; row < 7; row++) assert(platform_oled_get_pixel(fb, 2, row) == (row == 5 ? 0 : 0xF));
    assert(platform_oled_get_pixel(fb, 1, 0) == 0 && platform_oled_get_pixel(fb, 3, 0) == 0);
    /* lower case draws as upper case */
    static uint8_t fb2[PLATFORM_OLED_FB_BYTES];
    platform_oled_clear(fb);
    platform_oled_clear(fb2);
    platform_oled_text(fb, 0, 0, 2, "heating", 0xF);
    platform_oled_text(fb2, 0, 0, 2, "HEATING", 0xF);
    assert(memcmp(fb, fb2, sizeof fb) == 0);
    /* render does not write outside the buffer even for an over-long line */
    platform_oled_render(fb, "A VERY LONG MESSAGE THAT DOES NOT FIT", "123 C");
}

/* ---------------------------------------------------------------- UI inputs */
static void test_debounce(void)
{
    platform_debounce_t d;
    platform_debounce_init(&d);
    assert(platform_debounce_step(&d, 0xFE, 5) == 0xFF); /* first read: nothing pressed yet */
    for (int i = 0; i < 3; i++) assert(platform_debounce_step(&d, 0xFE, 5) == 0xFF);
    assert(platform_debounce_step(&d, 0xFE, 5) == 0xFE); /* 5th identical read */
    /* a 1-poll glitch does not change the stable state */
    assert(platform_debounce_step(&d, 0xFF, 5) == 0xFE);
    assert(platform_debounce_step(&d, 0xFE, 5) == 0xFE);
}

static void test_quadrature(void)
{
    platform_quad_t q;
    platform_quad_init(&q);
    static const bool seq[4][2] = {{0, 0}, {0, 1}, {1, 1}, {1, 0}};
    int sum = 0;
    assert(platform_quad_step(&q, 0, 0) == 0);
    for (int k = 1; k <= 8; k++) sum += platform_quad_step(&q, seq[k % 4][0], seq[k % 4][1]);
    assert(sum == 2);
    sum = 0;
    for (int k = 7; k >= 0; k--) sum += platform_quad_step(&q, seq[k % 4][0], seq[k % 4][1]);
    assert(sum == -2);
    /* invalid jump resets the partial count */
    platform_quad_init(&q);
    platform_quad_step(&q, 0, 0);
    platform_quad_step(&q, 0, 1);
    platform_quad_step(&q, 1, 1);
    assert(platform_quad_step(&q, 0, 0) == 0 && q.acc == 0);
}

static void test_buzzer(void)
{
    platform_buzzer_t b = {0};
    assert(!platform_buzzer_output(&b, 0));
    platform_buzzer_beep(&b, 1000, 200);
    assert(platform_buzzer_output(&b, 1199));
    assert(!platform_buzzer_output(&b, 1200));
    platform_buzzer_beep(&b, 0xFFFFFF00u, 0x200); /* wraps */
    assert(platform_buzzer_output(&b, 0xFFFFFFF0u) && platform_buzzer_output(&b, 0x50));
    assert(!platform_buzzer_output(&b, 0x100));
    platform_buzzer_continuous(&b);
    platform_buzzer_beep(&b, 0, 10); /* does not shorten the alarm */
    assert(platform_buzzer_output(&b, 100000));
    platform_buzzer_stop(&b);
    assert(!platform_buzzer_output(&b, 100001));
}

int main(void)
{
    TEST(test_word_to_ohm);
    TEST(test_fault_bit_and_bad_rref_are_infinite);
    TEST(test_rref_matches_threshold_words);
    TEST(test_pt100_round_trip_and_table);
    TEST(test_pt100_below_zero_error);
    TEST(test_pan_and_rtd_sentinels);
    TEST(test_power_bus_trip);
    TEST(test_power_tank_trip);
    TEST(test_blower_floor_never_lowers_speed);
    TEST(test_fan_requests);
    TEST(test_fault_log_ring);
    TEST(test_fault_log_rejects_corrupt_blob);
    TEST(test_display_text);
    TEST(test_oled_framebuffer);
    TEST(test_debounce);
    TEST(test_quadrature);
    TEST(test_buzzer);
    printf("%u platform logic tests passed\n", tests);
    return 0;
}
