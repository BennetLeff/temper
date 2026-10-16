/*
 * Pure logic behind the ESP32 platform layer (see include/platform_logic.h). No ESP-IDF.
 */
#include "platform_logic.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "max31865.h"
#include "n21_binding.h"

/* ---------------------------------------------------------------- pan RTD */
float pt100_r_at(float t_c)
{
    return PT100_R0_OHM * (1.0f + PT100_CVD_A * t_c + PT100_CVD_B * t_c * t_c);
}

float pt100_ohm_to_c(float ohm)
{
    if (!isfinite(ohm)) return NAN;
    if (ohm < pt100_r_at(PT100_T_MIN_C) || ohm > pt100_r_at(PT100_T_MAX_C)) return NAN;
    /* B t^2 + A t + (1 - R/R0) = 0, the root that is continuous through 0 C. */
    double a = PT100_CVD_A, b = PT100_CVD_B;
    double disc = a * a - 4.0 * b * (1.0 - (double)ohm / PT100_R0_OHM);
    if (disc < 0.0) return NAN;
    return (float)((-a + sqrt(disc)) / (2.0 * b));
}

float platform_rtd_resistance(bool have_word, uint16_t rtd_word, float rref_ohm)
{
    if (!have_word) return INFINITY;
    return max31865_rtd_word_to_ohm(rtd_word, rref_ohm);
}

float platform_pan_temperature(bool have_word, uint16_t rtd_word, float rref_ohm)
{
    return pt100_ohm_to_c(platform_rtd_resistance(have_word, rtd_word, rref_ohm));
}

/* ---------------------------------------------------------------- native-21 over-current sources */
bool platform_power_bus_trip(bool status_known, bool bus_fault, bool permit, bool bridge_running)
{
    return !status_known || bus_fault || (bridge_running && !permit);
}

bool platform_power_tank_trip(bool known, int n21_fault)
{
    if (!known) return true;
    switch (n21_fault) {
    case N21_FAULT_TANK_PEAK:
    case N21_FAULT_TANK_RMS:
    case N21_FAULT_CT_MON:
    case N21_FAULT_RMS_CHANNEL:
        return true;
    default:
        return false;
    }
}

/* ---------------------------------------------------------------- BIAS_GOOD read-back (B13 H2) */
uint64_t platform_permit_step(platform_permit_t *p, bool permit_high, uint64_t now_us,
                              uint64_t edge_us)
{
    /* A RUN_EN edge after the previous sample and not in the future. */
    bool edge = p->known && edge_us != 0 && edge_us > p->last_us && edge_us <= now_us;
    if (!p->known || permit_high != p->high)
        p->since_us = edge ? edge_us : now_us;
    else if (edge)
        p->since_us = edge_us; /* same level at both samples: a pulse ended at the edge */
    p->known = true;
    p->high = permit_high;
    p->last_us = now_us;
    return now_us - p->since_us;
}

void platform_bias_idle_reset(platform_bias_idle_t *s)
{
    memset(s, 0, sizeof *s);
}

static unsigned bits_set(uint8_t v)
{
    unsigned n = 0;
    for (; v; v &= (uint8_t)(v - 1u)) n++;
    return n;
}

bool platform_bias_idle_step(platform_bias_idle_t *s, platform_bias_level_t level, bool permit_high,
                             uint64_t permit_us, uint32_t fall_us, unsigned trip, unsigned window)
{
    if (s->tripped) return true;
    if (level == PLATFORM_BIAS_NOT_FITTED || permit_high || permit_us < fall_us) {
        s->history = 0;
        return false;
    }
    if (window == 0 || window > 8) window = 8;
    uint8_t mask = (uint8_t)((1u << window) - 1u);
    bool failed = level != PLATFORM_BIAS_LOW;
    s->history = (uint8_t)(((unsigned)s->history << 1 | (failed ? 1u : 0u)) & mask);
    s->tripped = trip > 0 && bits_set(s->history) >= trip;
    return s->tripped;
}

void platform_bias_run_reset(platform_bias_run_t *r)
{
    memset(r, 0, sizeof *r);
}

bool platform_bias_run_step(platform_bias_run_t *r, platform_bias_level_t level, uint32_t now_ms,
                            uint32_t debounce_ms)
{
    if (level == PLATFORM_BIAS_NOT_FITTED || level == PLATFORM_BIAS_HIGH) {
        r->in_low = false;
        return false;
    }
    /* Unsigned differences: wrap-safe. */
    if (!r->in_low || now_ms - r->last_ms > debounce_ms) {
        r->in_low = true;
        r->first_low_ms = now_ms;
        r->last_ms = now_ms;
        return false;
    }
    r->last_ms = now_ms;
    return now_ms - r->first_low_ms >= debounce_ms;
}

bool platform_bias_lost_step(platform_bias_run_t *r, platform_bias_level_t level, bool permit_high,
                             uint64_t permit_us, uint32_t rise_us, uint32_t now_ms,
                             uint32_t debounce_ms)
{
    if (!permit_high || permit_us < rise_us) {
        platform_bias_run_reset(r);
        return false;
    }
    return platform_bias_run_step(r, level, now_ms, debounce_ms);
}

/* ---------------------------------------------------------------- blower request */
void platform_fan_request_speed(platform_fan_req_t *r, bool speed_is_max)
{
    r->full_speed_floor = speed_is_max;
}

void platform_fan_request_auto(platform_fan_req_t *r, bool auto_mode)
{
    if (auto_mode) r->full_speed_floor = false;
}

void platform_blower_apply_floor(bool full_speed_floor, bool *on, float *duty)
{
    if (!full_speed_floor) return;
    *on = true;
    *duty = 0.0f;
}

/* ---------------------------------------------------------------- fault log */
void platform_fault_log_init(platform_fault_log_t *log)
{
    memset(log, 0, sizeof *log);
    log->magic = PLATFORM_FAULT_LOG_MAGIC;
    log->next_seq = 1u;
}

bool platform_fault_log_valid(const platform_fault_log_t *log)
{
    if (log->magic != PLATFORM_FAULT_LOG_MAGIC || log->next_seq == 0u) return false;
    for (size_t i = 0; i < PLATFORM_FAULT_LOG_LEN; i++) {
        const platform_fault_rec_t *r = &log->rec[i];
        if (r->seq == 0u) continue;
        if (r->seq >= log->next_seq) return false;
        if (r->seq % PLATFORM_FAULT_LOG_LEN != i) return false;
    }
    return true;
}

void platform_fault_log_new_boot(platform_fault_log_t *log)
{
    log->boot++;
}

void platform_fault_log_append(platform_fault_log_t *log, uint16_t code, uint32_t t_ms)
{
    uint32_t seq = log->next_seq;
    platform_fault_rec_t *r = &log->rec[seq % PLATFORM_FAULT_LOG_LEN];
    r->seq = seq;
    r->t_ms = t_ms;
    r->code = code;
    r->boot = log->boot;
    log->next_seq = seq + 1u == 0u ? 1u : seq + 1u;
}

size_t platform_fault_log_count(const platform_fault_log_t *log)
{
    size_t n = 0;
    for (size_t i = 0; i < PLATFORM_FAULT_LOG_LEN; i++)
        if (log->rec[i].seq != 0u) n++;
    return n;
}

const platform_fault_rec_t *platform_fault_log_get(const platform_fault_log_t *log, size_t k)
{
    if (k >= platform_fault_log_count(log)) return NULL;
    uint32_t seq = log->next_seq - 1u - (uint32_t)k;
    const platform_fault_rec_t *r = &log->rec[seq % PLATFORM_FAULT_LOG_LEN];
    return r->seq == seq ? r : NULL;
}

/* ---------------------------------------------------------------- display text */
void platform_fmt_temperature(char *out, size_t n, float temp_c)
{
    if (n == 0) return;
    if (!isfinite(temp_c)) {
        snprintf(out, n, "--- C");
        return;
    }
    snprintf(out, n, "%d C", (int)lroundf(temp_c));
}

void platform_fmt_countdown(char *out, size_t n, uint16_t seconds)
{
    if (n == 0) return;
    snprintf(out, n, "%u:%02u", (unsigned)(seconds / 60u), (unsigned)(seconds % 60u));
}

/* Classic 5 x 7 font, columns left to right, bit 0 = top row. ASCII 0x20..0x5F. */
static const uint8_t s_font[64][5] = {
    {0x00, 0x00, 0x00, 0x00, 0x00}, {0x00, 0x00, 0x5F, 0x00, 0x00}, {0x00, 0x07, 0x00, 0x07, 0x00},
    {0x14, 0x7F, 0x14, 0x7F, 0x14}, {0x24, 0x2A, 0x7F, 0x2A, 0x12}, {0x23, 0x13, 0x08, 0x64, 0x62},
    {0x36, 0x49, 0x55, 0x22, 0x50}, {0x00, 0x05, 0x03, 0x00, 0x00}, {0x00, 0x1C, 0x22, 0x41, 0x00},
    {0x00, 0x41, 0x22, 0x1C, 0x00}, {0x08, 0x2A, 0x1C, 0x2A, 0x08}, {0x08, 0x08, 0x3E, 0x08, 0x08},
    {0x00, 0x50, 0x30, 0x00, 0x00}, {0x08, 0x08, 0x08, 0x08, 0x08}, {0x00, 0x60, 0x60, 0x00, 0x00},
    {0x20, 0x10, 0x08, 0x04, 0x02}, {0x3E, 0x51, 0x49, 0x45, 0x3E}, {0x00, 0x42, 0x7F, 0x40, 0x00},
    {0x42, 0x61, 0x51, 0x49, 0x46}, {0x21, 0x41, 0x45, 0x4B, 0x31}, {0x18, 0x14, 0x12, 0x7F, 0x10},
    {0x27, 0x45, 0x45, 0x45, 0x39}, {0x3C, 0x4A, 0x49, 0x49, 0x30}, {0x01, 0x71, 0x09, 0x05, 0x03},
    {0x36, 0x49, 0x49, 0x49, 0x36}, {0x06, 0x49, 0x49, 0x29, 0x1E}, {0x00, 0x36, 0x36, 0x00, 0x00},
    {0x00, 0x56, 0x36, 0x00, 0x00}, {0x08, 0x14, 0x22, 0x41, 0x00}, {0x14, 0x14, 0x14, 0x14, 0x14},
    {0x00, 0x41, 0x22, 0x14, 0x08}, {0x02, 0x01, 0x51, 0x09, 0x06}, {0x32, 0x49, 0x79, 0x41, 0x3E},
    {0x7E, 0x11, 0x11, 0x11, 0x7E}, {0x7F, 0x49, 0x49, 0x49, 0x36}, {0x3E, 0x41, 0x41, 0x41, 0x22},
    {0x7F, 0x41, 0x41, 0x22, 0x1C}, {0x7F, 0x49, 0x49, 0x49, 0x41}, {0x7F, 0x09, 0x09, 0x01, 0x01},
    {0x3E, 0x41, 0x41, 0x51, 0x32}, {0x7F, 0x08, 0x08, 0x08, 0x7F}, {0x00, 0x41, 0x7F, 0x41, 0x00},
    {0x20, 0x40, 0x41, 0x3F, 0x01}, {0x7F, 0x08, 0x14, 0x22, 0x41}, {0x7F, 0x40, 0x40, 0x40, 0x40},
    {0x7F, 0x02, 0x04, 0x02, 0x7F}, {0x7F, 0x04, 0x08, 0x10, 0x7F}, {0x3E, 0x41, 0x41, 0x41, 0x3E},
    {0x7F, 0x09, 0x09, 0x09, 0x06}, {0x3E, 0x41, 0x51, 0x21, 0x5E}, {0x7F, 0x09, 0x19, 0x29, 0x46},
    {0x46, 0x49, 0x49, 0x49, 0x31}, {0x01, 0x01, 0x7F, 0x01, 0x01}, {0x3F, 0x40, 0x40, 0x40, 0x3F},
    {0x1F, 0x20, 0x40, 0x20, 0x1F}, {0x7F, 0x20, 0x18, 0x20, 0x7F}, {0x63, 0x14, 0x08, 0x14, 0x63},
    {0x03, 0x04, 0x78, 0x04, 0x03}, {0x61, 0x51, 0x49, 0x45, 0x43}, {0x00, 0x7F, 0x41, 0x41, 0x00},
    {0x02, 0x04, 0x08, 0x10, 0x20}, {0x00, 0x41, 0x41, 0x7F, 0x00}, {0x04, 0x02, 0x01, 0x02, 0x04},
    {0x40, 0x40, 0x40, 0x40, 0x40},
};

void platform_oled_clear(uint8_t *fb)
{
    memset(fb, 0, PLATFORM_OLED_FB_BYTES);
}

void platform_oled_set_pixel(uint8_t *fb, unsigned x, unsigned y, uint8_t grey)
{
    if (x >= PLATFORM_OLED_W || y >= PLATFORM_OLED_H) return;
    uint8_t *p = &fb[y * (PLATFORM_OLED_W / 2u) + x / 2u];
    grey &= 0x0Fu;
    *p = (x & 1u) ? (uint8_t)((*p & 0xF0u) | grey) : (uint8_t)((*p & 0x0Fu) | (grey << 4));
}

uint8_t platform_oled_get_pixel(const uint8_t *fb, unsigned x, unsigned y)
{
    if (x >= PLATFORM_OLED_W || y >= PLATFORM_OLED_H) return 0;
    uint8_t v = fb[y * (PLATFORM_OLED_W / 2u) + x / 2u];
    return (x & 1u) ? (uint8_t)(v & 0x0Fu) : (uint8_t)(v >> 4);
}

unsigned platform_oled_text(uint8_t *fb, unsigned x, unsigned y, unsigned scale, const char *s,
                            uint8_t grey)
{
    if (scale == 0) scale = 1;
    for (; s && *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c >= 'a' && c <= 'z') c = (unsigned char)(c - 'a' + 'A');
        if (c < 0x20u || c > 0x5Fu) c = '?';
        const uint8_t *g = s_font[c - 0x20u];
        for (unsigned col = 0; col < 5u; col++)
            for (unsigned row = 0; row < 7u; row++)
                if (g[col] & (1u << row))
                    for (unsigned dy = 0; dy < scale; dy++)
                        for (unsigned dx = 0; dx < scale; dx++)
                            platform_oled_set_pixel(fb, x + col * scale + dx, y + row * scale + dy, grey);
        x += 6u * scale;
        if (x >= PLATFORM_OLED_W) break;
    }
    return x;
}

void platform_oled_render(uint8_t *fb, const char *line1, const char *line2)
{
    platform_oled_clear(fb);
    (void)platform_oled_text(fb, 4u, 8u, 2u, line1, 0x0Fu);
    (void)platform_oled_text(fb, 4u, 38u, 2u, line2, 0x0Fu);
}

/* ---------------------------------------------------------------- UI board inputs */
void platform_debounce_init(platform_debounce_t *d)
{
    memset(d, 0, sizeof *d);
}

uint8_t platform_debounce_step(platform_debounce_t *d, uint8_t raw, uint8_t polls)
{
    if (polls == 0) polls = 1;
    if (!d->primed) {
        /* The first read only starts a run: nothing is reported pressed until it has repeated. */
        d->primed = true;
        d->stable = 0xFFu; /* active-low inputs: all released */
        d->candidate = raw;
        d->run = 1;
    } else if (raw == d->candidate) {
        if (d->run < 0xFFu) d->run++;
    } else {
        d->candidate = raw;
        d->run = 1;
    }
    if (d->run >= polls) d->stable = d->candidate;
    return d->stable;
}

void platform_quad_init(platform_quad_t *q)
{
    memset(q, 0, sizeof *q);
}

int platform_quad_step(platform_quad_t *q, bool a, bool b)
{
    uint8_t now = (uint8_t)((a ? 2u : 0u) | (b ? 1u : 0u));
    if (!q->primed) {
        q->primed = true;
        q->prev = now;
        q->acc = 0;
        return 0;
    }
    if (now == q->prev) return 0;
    /* Gray sequence 00 -> 01 -> 11 -> 10 -> 00 is +1 per step. */
    static const int8_t dir[4][4] = {
        /* prev\now  00  01  10  11 */
        /* 00 */ {0, +1, -1, 0},
        /* 01 */ {-1, 0, 0, +1},
        /* 10 */ {+1, 0, 0, -1},
        /* 11 */ {0, -1, +1, 0},
    };
    int8_t d = dir[q->prev][now];
    q->prev = now;
    if (d == 0) { /* both lines changed: direction unknown */
        q->acc = 0;
        return 0;
    }
    q->acc = (int8_t)(q->acc + d);
    if (q->acc >= 4) { q->acc = 0; return +1; }
    if (q->acc <= -4) { q->acc = 0; return -1; }
    return 0;
}

void platform_buzzer_beep(platform_buzzer_t *b, uint32_t now_ms, uint32_t duration_ms)
{
    if (b->mode == PLATFORM_BUZZ_CONTINUOUS) return; /* a beep never ends a continuous alarm */
    b->mode = PLATFORM_BUZZ_TIMED;
    b->until_ms = now_ms + duration_ms;
}

void platform_buzzer_continuous(platform_buzzer_t *b)
{
    b->mode = PLATFORM_BUZZ_CONTINUOUS;
}

void platform_buzzer_stop(platform_buzzer_t *b)
{
    b->mode = PLATFORM_BUZZ_OFF;
}

bool platform_buzzer_output(platform_buzzer_t *b, uint32_t now_ms)
{
    if (b->mode == PLATFORM_BUZZ_TIMED && (int32_t)(now_ms - b->until_ms) >= 0) b->mode = PLATFORM_BUZZ_OFF;
    return b->mode != PLATFORM_BUZZ_OFF;
}

/* ---------------------------------------------------------------- UI link supervision */
void platform_ui_link_init(platform_ui_link_t *l, uint32_t now_ms)
{
    l->last_good_ms = now_ms;
    l->ok = true;
    l->stop_latched = false;
}

bool platform_ui_link_poll(platform_ui_link_t *l, uint32_t now_ms, bool ok, uint32_t lost_ms)
{
    if (ok) {
        l->last_good_ms = now_ms;
        l->ok = true;
        return false;
    }
    l->ok = false;
    if ((uint32_t)(now_ms - l->last_good_ms) > lost_ms) {
        l->stop_latched = true;
        return true;
    }
    return false;
}

void platform_ui_link_reacquired(platform_ui_link_t *l, uint32_t now_ms)
{
    l->last_good_ms = now_ms;
    l->ok = true;
}

bool platform_ui_link_take_stop(platform_ui_link_t *l)
{
    if (!l->stop_latched) return false;
    if (l->ok) l->stop_latched = false;
    return true;
}

uint32_t platform_ui_powerup_wait_remaining_ms(uint32_t now_ms, uint32_t since_ms, uint32_t wait_ms)
{
    uint32_t elapsed = now_ms - since_ms;
    return elapsed >= wait_ms ? 0u : wait_ms - elapsed;
}
