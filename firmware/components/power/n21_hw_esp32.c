/*
 * ESP32-S3 implementation of n21_hw_ops_t for the integrated SELV controller (zapote/controller)
 * driving native-21 through J4. Target: ESP-IDF v5.2.x (the version the round-5 bench image built
 * with). NOT YET COMPILED against ESP-IDF or run on hardware: it is opt-in through
 * CONFIG_TEMPER_POWER_HW_BINDING (default n). Every item marked HIL must be confirmed on the bench
 * (COMMISSIONING.md). All decisions about *whether* to run live in n21_binding.c (host-tested);
 * this file only moves bits.
 *
 * PWM (DECISIONS 2026-10-03 O05/O07, D-21, D-25): MCPWM group 0, one 80 MHz up-counting timer,
 * one operator per leg, one comparator at half period. Each output has its own raw generator; the
 * two generators of a leg carry identical actions, the high one through rising-edge delay (RED),
 * the low one through falling-edge delay plus inversion (FED+inv), so HA = RED(raw) and
 * LA = NOT FED(raw): complementary with the 200 ns input non-overlap (16 ticks) on both edges. The
 * UCC21550 DT pin (R9/R17 49.9 k: 396.6-488 ns) then dominates by the driver's longer-of rule.
 * Leg B's raw waveform is leg A's inverted (TEZ->low, half->high): the fixed 180 degree bridge of
 * bridge_plan_cycle. "Pads off" forces raw HA/HB low and raw LA/LB high, i.e. all four outputs
 * low after the dead-time stage; any API failure falls back to the D-25 GPIO-low teardown.
 *
 * Live retiming (frequency loop, hw_pwm_update): the timer is created with update_period_on_empty
 * and the comparators with update_cmp_on_tez, so a new period and half-period compare written while
 * the bridge runs load from the shadow registers at the next timer zero; every period is whole and
 * the counter can never be above a shrunken period. Each leg's two outputs come from ONE comparator
 * through RED / FED+inv, so the leg's non-overlap is independent of when the compare loads; if the
 * period and a compare land on different TEZs (writes straddling a zero), one period carries a
 * duty error of at most half the step (<= 1 kHz: <= 32 ticks at 35 kHz), never an overlap. HIL:
 * confirm the shadow load on a scope across a forced 1 kHz step, and that pwm_program (timer
 * stopped at zero) still starts with the written period under update_period_on_empty.
 *
 * Captures: MCPWM capture channels read the pads back (io_loop_back). Group 0: HA, LA, CT_ZC.
 * Group 1: HA, HB, LB. HA is captured in both groups and serves as each group's phase reference
 * (HA rises one dead time after the PWM timer zero), so no cross-group timer sync is needed.
 * Capture interrupts are enabled only for a short snapshot window (a few bridge periods).
 *
 * Controller layout L2 (DECISIONS C23, C27): the run gate is RUN_EN on GPIO14 (U37 ANDs it with the
 * latch, so it can only remove permission), owned by controller_board_esp32.c, which presets it low
 * at boot. SUP_RUN_OK is TCA9555 P14, read from the expander cache that the control task refreshes;
 * a stale or failed snapshot reads as "not ok". ADC1 also carries the four thermal channels (HS,
 * COIL, M12, RIM); their latest frame means are kept for the thermal owner (n21_hw_thermal_mv).
 */
#include "n21_hw.h"
#include "rms_shadow.h"
#include "controller_board.h"
#include "driver/gpio.h"
#include "driver/mcpwm_prelude.h"
#include "driver/spi_master.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_continuous.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include <math.h>
#include <string.h>

static const char *TAG = "n21_hw";

enum { HA, LA, HB, LB };
static const int PWM_PIN[4] = {N21_GPIO_PWM_HA, N21_GPIO_PWM_LA, N21_GPIO_PWM_HB, N21_GPIO_PWM_LB};
#define N21_ADC_PATTERN_LEN 9
static const int THERMAL_CH[N21_THERMAL_COUNT] = {N21_ADC1_CH_HS, N21_ADC1_CH_COIL, N21_ADC1_CH_M12,
                                                   N21_ADC1_CH_RIM};

#define CAP_EDGES 8
typedef struct {
    volatile uint32_t value[CAP_EDGES];
    volatile uint8_t pos[CAP_EDGES];
    volatile uint8_t n;
} cap_log_t;

enum { C0_HA, C0_LA, C0_CTZC, C1_HA, C1_HB, C1_LB, CAP_COUNT };

typedef struct {
    /* PWM */
    mcpwm_timer_handle_t timer;
    mcpwm_oper_handle_t op[2];
    mcpwm_cmpr_handle_t cmp[2];
    mcpwm_gen_handle_t gen[4];
    bridge_cycle_t cycle;
    bool timer_running;
    /* captures */
    mcpwm_cap_timer_handle_t cap_timer[2];
    mcpwm_cap_channel_handle_t cap[CAP_COUNT];
    cap_log_t log[CAP_COUNT];
    uint32_t cap_hz;
    SemaphoreHandle_t cap_mutex;
    /* ADC1 continuous */
    adc_continuous_handle_t adc;
    adc_cali_handle_t cali_vbus, cali_atten3;
    portMUX_TYPE adc_mux;
    float vbus_mv, ct_mv;
    uint64_t adc_t_us;
    bool adc_fresh;
    /* Bench shadow RMS (CONFIG_TEMPER_POWER_SHADOW_RMS): ADC task accumulates, acquisition closes. */
    rms_shadow_t shadow;
    uint32_t shadow_fs_cur, shadow_fs_req;
    bool shadow_dirty;
    float thermal_mv[N21_THERMAL_COUNT];
    uint64_t thermal_t_us;
    bool thermal_fresh;
    /* MCP3202 */
    spi_device_handle_t ext_adc;
    /* LINE_ZC edge ring (ISR producer, acquisition consumer) */
    portMUX_TYPE zc_mux;
    uint64_t zc_t[16];
    bool zc_level[16];
    volatile uint8_t zc_head, zc_tail;
    /* shared binding */
    SemaphoreHandle_t mutex;
    TaskHandle_t acq_task, adc_task;
    esp_timer_handle_t acq_timer;
} hw_t;

static hw_t hw = {.adc_mux = portMUX_INITIALIZER_UNLOCKED, .zc_mux = portMUX_INITIALIZER_UNLOCKED};
static n21_binding_t binding;
static bool started;

/* ------------------------------------------------------------------ PWM */
/* D-25: last step of every failure path. gpio_reset_pin() enables the weak pull-up, so re-assert a
 * pulled-down push-pull low output afterwards. Attempts every pad even if one call fails. */
static bool pads_gpio_low(void)
{
    bool ok = true;
    for (unsigned i = 0; i < 4; i++) {
        int p = PWM_PIN[i];
        if (gpio_set_level(p, 0) != ESP_OK) ok = false;
        if (gpio_reset_pin(p) != ESP_OK) ok = false;
        if (gpio_set_level(p, 0) != ESP_OK) ok = false;
        if (gpio_pullup_dis(p) != ESP_OK) ok = false;
        if (gpio_pulldown_en(p) != ESP_OK) ok = false;
        if (gpio_set_direction(p, GPIO_MODE_OUTPUT) != ESP_OK) ok = false;
    }
    return ok;
}

static bool force_off(void)
{
    bool ok = true;
    for (unsigned i = 0; i < 4; i++) {
        if (!hw.gen[i]) { ok = false; continue; }
        /* Raw low for the high-side paths, raw high for the inverted low-side paths. */
        int level = (i == HA || i == HB) ? 0 : 1;
        if (mcpwm_generator_set_force_level(hw.gen[i], level, true) != ESP_OK) ok = false;
    }
    return ok;
}

static bool hw_pwm_outputs(void *ctx, bool live)
{
    (void)ctx;
    if (!live) {
        if (force_off()) return true;
        (void)pads_gpio_low(); /* force failed: take the pads away from MCPWM entirely */
        return false;
    }
    if (!hw.timer_running) return false;
    /* Release the low-side (inverting) paths last: until then LA/LB read low. HIL: confirm the
     * first period after release is a truncated but dead-time-correct pulse. */
    bool ok = true;
    const unsigned order[4] = {HA, HB, LA, LB};
    for (unsigned k = 0; k < 4; k++)
        if (mcpwm_generator_set_force_level(hw.gen[order[k]], -1, true) != ESP_OK) ok = false;
    if (!ok) { (void)force_off(); (void)pads_gpio_low(); }
    return ok;
}

static bool pwm_create(void)
{
    mcpwm_timer_config_t tc = {.group_id = 0, .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
                               .resolution_hz = 80000000, .count_mode = MCPWM_TIMER_COUNT_MODE_UP,
                               .period_ticks = 1600, .flags.update_period_on_empty = true};
    if (mcpwm_new_timer(&tc, &hw.timer) != ESP_OK) return false;
    for (unsigned leg = 0; leg < 2; leg++) {
        mcpwm_operator_config_t oc = {.group_id = 0};
        mcpwm_comparator_config_t cc = {.flags.update_cmp_on_tez = true};
        if (mcpwm_new_operator(&oc, &hw.op[leg]) != ESP_OK ||
            mcpwm_operator_connect_timer(hw.op[leg], hw.timer) != ESP_OK ||
            mcpwm_new_comparator(hw.op[leg], &cc, &hw.cmp[leg]) != ESP_OK)
            return false;
        for (unsigned j = 0; j < 2; j++) {
            unsigned i = 2 * leg + j;
            mcpwm_generator_config_t gc = {.gen_gpio_num = PWM_PIN[i]};
            if (mcpwm_new_generator(hw.op[leg], &gc, &hw.gen[i]) != ESP_OK) return false;
            /* Force before anything else happens on the new generator. */
            if (mcpwm_generator_set_force_level(hw.gen[i], j ? 1 : 0, true) != ESP_OK) return false;
            /* Leg A raw: high at TEZ, low at half. Leg B raw: inverse (180 degrees). */
            int at_zero = leg ? MCPWM_GEN_ACTION_LOW : MCPWM_GEN_ACTION_HIGH;
            int at_half = leg ? MCPWM_GEN_ACTION_HIGH : MCPWM_GEN_ACTION_LOW;
            if (mcpwm_generator_set_action_on_timer_event(hw.gen[i],
                    MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, at_zero)) != ESP_OK ||
                mcpwm_generator_set_action_on_compare_event(hw.gen[i],
                    MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, hw.cmp[leg], at_half)) != ESP_OK)
                return false;
        }
    }
    return mcpwm_timer_enable(hw.timer) == ESP_OK;  /* enabled once; started by program */
}

static bool hw_pwm_program(void *ctx, const bridge_cycle_t *c)
{
    (void)ctx;
    if (!c || c->period < 4 || c->period % 2 || !c->dead_ticks) return false;
    if (!force_off()) return false;
    if (hw.timer_running) {
        if (mcpwm_timer_start_stop(hw.timer, MCPWM_TIMER_STOP_EMPTY) != ESP_OK) return false;
        hw.timer_running = false;
    }
    if (mcpwm_timer_set_period(hw.timer, c->period) != ESP_OK) return false;
    for (unsigned leg = 0; leg < 2; leg++) {
        if (mcpwm_comparator_set_compare_value(hw.cmp[leg], c->period / 2) != ESP_OK) return false;
        mcpwm_dead_time_config_t red = {.posedge_delay_ticks = c->dead_ticks};
        mcpwm_dead_time_config_t fed = {.negedge_delay_ticks = c->dead_ticks, .flags.invert_output = true};
        if (mcpwm_generator_set_dead_time(hw.gen[2 * leg], hw.gen[2 * leg], &red) != ESP_OK ||
            mcpwm_generator_set_dead_time(hw.gen[2 * leg + 1], hw.gen[2 * leg + 1], &fed) != ESP_OK)
            return false;
    }
    if (mcpwm_timer_start_stop(hw.timer, MCPWM_TIMER_START_NO_STOP) != ESP_OK) return false;
    hw.timer_running = true;
    hw.cycle = *c;
    return true;
}

/* Live period change while the pads run (frequency loop). Same dead time; the step is bounded by
 * the binding, re-checked here (<= 1/16 of the period, ~3.7 kHz at 60 kHz). Holds cap_mutex so
 * hw_read_ct_zc / hw_pwm_capture never pair one period's edges with the other's period. */
static bool hw_pwm_update(void *ctx, const bridge_cycle_t *c)
{
    (void)ctx;
    if (!c || c->period < 4 || c->period % 2 || c->dead_ticks != hw.cycle.dead_ticks ||
        !hw.timer_running || !hw.cycle.period)
        return false;
    uint32_t d = c->period > hw.cycle.period ? c->period - hw.cycle.period : hw.cycle.period - c->period;
    if (d * 16u > hw.cycle.period) return false;
    if (xSemaphoreTake(hw.cap_mutex, pdMS_TO_TICKS(2)) != pdTRUE) return false;
    bool ok = mcpwm_timer_set_period(hw.timer, c->period) == ESP_OK;
    for (unsigned leg = 0; ok && leg < 2; leg++)
        ok = mcpwm_comparator_set_compare_value(hw.cmp[leg], c->period / 2) == ESP_OK;
    if (ok) hw.cycle = *c;
    xSemaphoreGive(hw.cap_mutex);
    if (!ok) { (void)force_off(); (void)pads_gpio_low(); } /* unknown timing: pads away */
    return ok;
}

/* ------------------------------------------------------------------ captures */
static bool IRAM_ATTR on_cap(mcpwm_cap_channel_handle_t ch, const mcpwm_capture_event_data_t *e, void *ctx)
{
    (void)ch;
    cap_log_t *l = ctx;
    uint8_t n = l->n;
    if (n < CAP_EDGES) {
        l->value[n] = e->cap_value;
        l->pos[n] = e->cap_edge == MCPWM_CAP_EDGE_POS;
        l->n = n + 1;
    }
    return false;
}

static bool cap_create(void)
{
    static const struct { unsigned group; int pin; bool loop, neg; } spec[CAP_COUNT] = {
        [C0_HA] = {0, N21_GPIO_PWM_HA, true, true},  [C0_LA] = {0, N21_GPIO_PWM_LA, true, true},
        [C0_CTZC] = {0, N21_GPIO_CT_ZC, false, false},
        [C1_HA] = {1, N21_GPIO_PWM_HA, true, true},  [C1_HB] = {1, N21_GPIO_PWM_HB, true, true},
        [C1_LB] = {1, N21_GPIO_PWM_LB, true, true},
    };
    for (unsigned g = 0; g < 2; g++) {
        mcpwm_capture_timer_config_t tc = {.group_id = (int)g, .clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT};
        if (mcpwm_new_capture_timer(&tc, &hw.cap_timer[g]) != ESP_OK) return false;
    }
    if (mcpwm_capture_timer_get_resolution(hw.cap_timer[0], &hw.cap_hz) != ESP_OK || !hw.cap_hz) return false;
    for (unsigned i = 0; i < CAP_COUNT; i++) {
        mcpwm_capture_channel_config_t cc = {.gpio_num = spec[i].pin, .prescale = 1,
                                             .flags.pos_edge = true, .flags.neg_edge = spec[i].neg,
                                             .flags.io_loop_back = spec[i].loop};
        mcpwm_capture_event_callbacks_t cb = {.on_cap = on_cap};
        if (mcpwm_new_capture_channel(hw.cap_timer[spec[i].group], &cc, &hw.cap[i]) != ESP_OK ||
            mcpwm_capture_channel_register_event_callbacks(hw.cap[i], &cb, &hw.log[i]) != ESP_OK)
            return false;
    }
    for (unsigned g = 0; g < 2; g++)
        if (mcpwm_capture_timer_enable(hw.cap_timer[g]) != ESP_OK ||
            mcpwm_capture_timer_start(hw.cap_timer[g]) != ESP_OK)
            return false;
    /* Loop-back capture reconfigures the pad; make sure PWM pins are still forced off. */
    return force_off();
}

/* Enable the listed channels for window_us, then disable. Caller holds cap_mutex. */
static void cap_window(const unsigned *list, unsigned n, uint32_t window_us)
{
    for (unsigned k = 0; k < n; k++) { hw.log[list[k]].n = 0; (void)mcpwm_capture_channel_enable(hw.cap[list[k]]); }
    esp_rom_delay_us(window_us);
    for (unsigned k = 0; k < n; k++) (void)mcpwm_capture_channel_disable(hw.cap[list[k]]);
}

static uint32_t to_pwm_ticks(uint32_t cap_ticks)
{
    return (uint32_t)(((uint64_t)cap_ticks * 80000000u + hw.cap_hz / 2) / hw.cap_hz);
}

/* First rise r0, the fall after it f0 and the rise after that r1. */
static bool edges(const cap_log_t *l, uint32_t *r0, uint32_t *high, uint32_t *period)
{
    unsigned n = l->n, i = 0;
    while (i < n && !l->pos[i]) i++;
    if (i + 2 >= n || l->pos[i + 1] || !l->pos[i + 2]) return false;
    *r0 = l->value[i];
    *high = to_pwm_ticks(l->value[i + 1] - l->value[i]);
    *period = to_pwm_ticks(l->value[i + 2] - l->value[i]);
    return true;
}

static uint32_t phase_from(uint32_t t, uint32_t t_ref, uint32_t ref_phase, uint32_t period)
{
    uint32_t d = to_pwm_ticks(t - t_ref) % period;
    return (d + ref_phase) % period;
}

static bool hw_pwm_capture(void *ctx, n21_pwm_capture_t *cap)
{
    (void)ctx;
    memset(cap, 0, sizeof *cap);
    uint32_t P = hw.cycle.period, dead = hw.cycle.dead_ticks;
    if (!P || xSemaphoreTake(hw.cap_mutex, pdMS_TO_TICKS(2)) != pdTRUE) return false;
    static const unsigned list[] = {C0_HA, C0_LA, C1_HA, C1_HB, C1_LB};
    uint32_t window = 3u * P * 1000000u / 80000000u + 2u;  /* three bridge periods */
    cap_window(list, 5, window);
    cap->t_us = (uint64_t)esp_timer_get_time();
    uint32_t a0, a0h, a0p, l0, l0h, l0p, a1, a1h, a1p, b, bh, bp, c, ch, cp;
    bool ok0 = edges(&hw.log[C0_HA], &a0, &a0h, &a0p) && edges(&hw.log[C0_LA], &l0, &l0h, &l0p);
    bool ok1 = edges(&hw.log[C1_HA], &a1, &a1h, &a1p) && edges(&hw.log[C1_HB], &b, &bh, &bp) &&
               edges(&hw.log[C1_LB], &c, &ch, &cp);
    xSemaphoreGive(hw.cap_mutex);
    if (ok1) {
        /* HA rises one dead time after the timer zero: it is the phase reference. */
        cap->out[HA] = (n21_edge_t){dead, a1h, a1p, true};
        cap->out[HB] = (n21_edge_t){phase_from(b, a1, dead, P), bh, bp, true};
        cap->out[LB] = (n21_edge_t){phase_from(c, a1, dead, P), ch, cp, true};
    }
    if (ok0) cap->out[LA] = (n21_edge_t){phase_from(l0, a0, dead, P), l0h, l0p, true};
    return ok0 && ok1;
}

static bool hw_read_ct_zc(void *ctx, uint32_t *zc, uint64_t *t)
{
    (void)ctx;
    uint32_t P = hw.cycle.period, dead = hw.cycle.dead_ticks;
    if (!P || xSemaphoreTake(hw.cap_mutex, pdMS_TO_TICKS(1)) != pdTRUE) return false;
    static const unsigned list[] = {C0_HA, C0_CTZC};
    cap_window(list, 2, 2u * P * 1000000u / 80000000u + 2u);
    *t = (uint64_t)esp_timer_get_time();
    const cap_log_t *ha = &hw.log[C0_HA], *z = &hw.log[C0_CTZC];
    bool ok = false;
    for (unsigned i = 0; i < ha->n && !ok; i++) {
        if (!ha->pos[i] || z->n == 0) continue;
        *zc = phase_from(z->value[0], ha->value[i], dead, P);
        ok = true;
    }
    xSemaphoreGive(hw.cap_mutex);
    return ok;
}

/* ------------------------------------------------------------------ ADC1 continuous (C12) */
#define ADC_FRAME 256
static bool adc_configure(uint32_t fs_hz);
#if CONFIG_TEMPER_POWER_SHADOW_RMS
/* Bench shadow RMS: move the ADC1 sample clock to the one the acquisition context asked for
 * (rms_shadow_hold_fs). adc_continuous_config() needs the stream stopped, so this costs a restart;
 * the half that straddles it is discarded. If the new clock cannot be set, the as-built 80 kS/s is
 * restored; if the stream cannot restart, adc_fresh stays false and the binding fails safe. */
static void shadow_apply_clock(void)
{
    uint32_t req;
    portENTER_CRITICAL(&hw.adc_mux);
    req = hw.shadow_fs_req;
    portEXIT_CRITICAL(&hw.adc_mux);
    if (req == hw.shadow_fs_cur || req == 0) return;
    uint32_t got = req;
    bool ok = adc_continuous_stop(hw.adc) == ESP_OK;
    if (ok && !adc_configure(req)) {
        got = RMS_SHADOW_FS_NOMINAL_HZ;
        (void)adc_configure(got);
    }
    if (adc_continuous_start(hw.adc) != ESP_OK) {
        portENTER_CRITICAL(&hw.adc_mux);
        hw.adc_fresh = false;
        portEXIT_CRITICAL(&hw.adc_mux);
    }
    portENTER_CRITICAL(&hw.adc_mux);
    hw.shadow_fs_cur = got;
    hw.shadow_dirty = true;
    portEXIT_CRITICAL(&hw.adc_mux);
}
#endif
static void adc_task(void *arg)
{
    (void)arg;
    uint8_t buf[ADC_FRAME];
    for (;;) {
        uint32_t got = 0;
        if (adc_continuous_read(hw.adc, buf, sizeof buf, &got, 10) != ESP_OK) {
            portENTER_CRITICAL(&hw.adc_mux);
            hw.adc_fresh = false;
            portEXIT_CRITICAL(&hw.adc_mux);
            continue;
        }
#if CONFIG_TEMPER_POWER_SHADOW_RMS
        double sh_sumsq = 0;
        uint32_t sh_n = 0;
#endif
        int64_t vsum = 0, tsum[N21_THERMAL_COUNT] = {0};
        int vn = 0, ct_worst = -1, ct_dev = -1, tn[N21_THERMAL_COUNT] = {0};
        for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= got; i += SOC_ADC_DIGI_RESULT_BYTES) {
            const adc_digi_output_data_t *d = (const adc_digi_output_data_t *)&buf[i];
            int mv = 0;
            if (d->type2.channel == N21_ADC1_CH_VBUS &&
                adc_cali_raw_to_voltage(hw.cali_vbus, d->type2.data, &mv) == ESP_OK) {
                vsum += mv; vn++;
            } else if (d->type2.channel == N21_ADC1_CH_CT_MON &&
                       adc_cali_raw_to_voltage(hw.cali_atten3, d->type2.data, &mv) == ESP_OK) {
#if CONFIG_TEMPER_POWER_SHADOW_RMS
                {
                    float zero = CONFIG_TEMPER_POWER_CT_MON_ZERO_MV ? (float)CONFIG_TEMPER_POWER_CT_MON_ZERO_MV : 1650.0f;
                    float a = ((float)mv - zero) * (1e-3f / N21_CT_MON_V_PER_A);
                    sh_sumsq += (double)a * a;
                    sh_n++;
                }
#endif
                int dev = mv > 1650 ? mv - 1650 : 1650 - mv;  /* keep the extreme: peak check */
                if (dev > ct_dev) { ct_dev = dev; ct_worst = mv; }
            } else {
                for (unsigned k = 0; k < N21_THERMAL_COUNT; k++)
                    if (d->type2.channel == THERMAL_CH[k] &&
                        adc_cali_raw_to_voltage(hw.cali_atten3, d->type2.data, &mv) == ESP_OK) {
                        tsum[k] += mv; tn[k]++;
                    }
            }
        }
        portENTER_CRITICAL(&hw.adc_mux);
        hw.adc_fresh = vn > 0 && ct_worst >= 0;
        if (hw.adc_fresh) {
            hw.vbus_mv = (float)vsum / (float)vn;
            hw.ct_mv = (float)ct_worst;
            hw.adc_t_us = (uint64_t)esp_timer_get_time();
        }
#if CONFIG_TEMPER_POWER_SHADOW_RMS
        rms_shadow_add_sum(&hw.shadow, sh_sumsq, sh_n);
#endif
        bool all = true;
        for (unsigned k = 0; k < N21_THERMAL_COUNT; k++) all = all && tn[k] > 0;
        if (all) { /* else keep the last means; their age makes them stale */
            for (unsigned k = 0; k < N21_THERMAL_COUNT; k++) hw.thermal_mv[k] = (float)tsum[k] / (float)tn[k];
            hw.thermal_t_us = (uint64_t)esp_timer_get_time();
            hw.thermal_fresh = true;
        }
        portEXIT_CRITICAL(&hw.adc_mux);
#if CONFIG_TEMPER_POWER_SHADOW_RMS
        shadow_apply_clock();
#endif
    }
}

static bool adc_configure(uint32_t fs_hz)
{
    static const struct { int ch, atten; } pat[N21_ADC_PATTERN_LEN] = {
        {N21_ADC1_CH_VBUS, ADC_ATTEN_DB_6}, {N21_ADC1_CH_CT_MON, ADC_ATTEN_DB_12},
        {N21_ADC1_CH_VBUS, ADC_ATTEN_DB_6}, {N21_ADC1_CH_CT_MON, ADC_ATTEN_DB_12},
        {N21_ADC1_CH_VBUS, ADC_ATTEN_DB_6}, {N21_ADC1_CH_HS, ADC_ATTEN_DB_12},
        {N21_ADC1_CH_COIL, ADC_ATTEN_DB_12}, {N21_ADC1_CH_M12, ADC_ATTEN_DB_12},
        {N21_ADC1_CH_RIM, ADC_ATTEN_DB_12},
    };
    adc_digi_pattern_config_t p[N21_ADC_PATTERN_LEN];
    for (unsigned i = 0; i < N21_ADC_PATTERN_LEN; i++)
        p[i] = (adc_digi_pattern_config_t){.atten = pat[i].atten, .channel = pat[i].ch,
                                           .unit = ADC_UNIT_1, .bit_width = SOC_ADC_DIGI_MAX_BITWIDTH};
    adc_continuous_config_t cfg = {.pattern_num = N21_ADC_PATTERN_LEN, .adc_pattern = p, .sample_freq_hz = fs_hz,
                                   .conv_mode = ADC_CONV_SINGLE_UNIT_1,
                                   .format = ADC_DIGI_OUTPUT_FORMAT_TYPE2};
    return adc_continuous_config(hw.adc, &cfg) == ESP_OK;
}

static bool adc_create(void)
{
    adc_continuous_handle_cfg_t hc = {.max_store_buf_size = 4 * ADC_FRAME, .conv_frame_size = ADC_FRAME};
    if (adc_continuous_new_handle(&hc, &hw.adc) != ESP_OK) return false;
    /* DECISIONS C12 pattern at 80 kS/s, with R36's rim NTC as the ninth slot (C27): VBUS, CT_MON,
     * VBUS, CT_MON, VBUS, HS, COIL, M12, RIM (VBUS 26.7 kS/s). HS/COIL/M12/RIM belong to the thermal
     * owner (n21_hw_thermal_mv). HIL (C12 flag): repeated channels in one pattern on this IDF. */
    adc_cali_curve_fitting_config_t c6 = {.unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_6, .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_cali_curve_fitting_config_t c12 = {.unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    hw.shadow_fs_cur = hw.shadow_fs_req = RMS_SHADOW_FS_NOMINAL_HZ;
    if (!adc_configure(RMS_SHADOW_FS_NOMINAL_HZ) ||
        adc_cali_create_scheme_curve_fitting(&c6, &hw.cali_vbus) != ESP_OK ||
        adc_cali_create_scheme_curve_fitting(&c12, &hw.cali_atten3) != ESP_OK ||
        adc_continuous_start(hw.adc) != ESP_OK)
        return false;
    return xTaskCreatePinnedToCore(adc_task, "n21_adc", 3072, NULL, 20, &hw.adc_task, 1) == pdPASS;
}

static bool hw_read_adc1(void *ctx, float *vbus_mv, float *ct_mv)
{
    (void)ctx;
    uint64_t now = (uint64_t)esp_timer_get_time();
    portENTER_CRITICAL(&hw.adc_mux);
    bool ok = hw.adc_fresh && now - hw.adc_t_us <= 2000;
    *vbus_mv = hw.vbus_mv;
    *ct_mv = hw.ct_mv;
    portEXIT_CRITICAL(&hw.adc_mux);
    return ok;
}

#if CONFIG_TEMPER_POWER_SHADOW_RMS
/* Once per closed line half (acquisition context): hand back the shadow RMS of the half that just
 * ended and ask for the ADC clock the next half should run at. Telemetry only. */
static bool hw_shadow_half(void *ctx, uint32_t next_f_hz, float *rms_a, uint32_t *fs_hz)
{
    (void)ctx;
    portENTER_CRITICAL(&hw.adc_mux);
    bool ok = rms_shadow_close(&hw.shadow, rms_a) && !hw.shadow_dirty;
    hw.shadow_dirty = false;
    *fs_hz = hw.shadow_fs_cur;
    portEXIT_CRITICAL(&hw.adc_mux);
    uint32_t want = rms_shadow_hold_fs((float)next_f_hz, *fs_hz);
    portENTER_CRITICAL(&hw.adc_mux);
    hw.shadow_fs_req = want;
    portEXIT_CRITICAL(&hw.adc_mux);
    if (!ok) *rms_a = NAN;
    return ok;
}
#endif

bool n21_hw_thermal_mv(float mv[N21_THERMAL_COUNT], uint32_t max_age_us)
{
    uint64_t now = (uint64_t)esp_timer_get_time();
    portENTER_CRITICAL(&hw.adc_mux);
    bool ok = hw.thermal_fresh && now - hw.thermal_t_us <= max_age_us;
    for (unsigned k = 0; k < N21_THERMAL_COUNT; k++) mv[k] = hw.thermal_mv[k];
    portEXIT_CRITICAL(&hw.adc_mux);
    return ok;
}

/* ------------------------------------------------------------------ MCP3202 (C20) */
static bool ext_adc_create(void)
{
    /* SPI2 is normally initialised by rtd_service. If it is not, bring it up on this board's pins. */
    spi_bus_config_t bus = {.mosi_io_num = N21_GPIO_SPI_MOSI, .miso_io_num = N21_GPIO_SPI_MISO,
                            .sclk_io_num = N21_GPIO_SPI_SCK, .quadwp_io_num = -1, .quadhd_io_num = -1,
                            .max_transfer_sz = 32};
    esp_err_t e = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED);
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) return false;
    /* Mode 3 (CPOL 1, CPHA 1): valid for the MCP3202 (modes 0,0 / 1,1) and the MAX31865 (1 / 3),
     * so the clock idle level never changes between the two devices (C20). 800 kHz is under the
     * MCP3202's 0.9 MHz at 2.7 V. */
    spi_device_interface_config_t dc = {.mode = 3, .clock_speed_hz = 800000,
                                        .spics_io_num = N21_GPIO_EXT_ADC_CS_N, .queue_size = 1,
                                        .cs_ena_pretrans = 1, .cs_ena_posttrans = 1};
    return spi_bus_add_device(SPI2_HOST, &dc, &hw.ext_adc) == ESP_OK;
}

static bool hw_read_ext_adc(void *ctx, unsigned ch, uint16_t *code)
{
    (void)ctx;
    uint8_t tx[3], rx[3] = {0};
    n21_mcp3202_frame(ch, tx);
    spi_transaction_t t = {.length = 24, .tx_buffer = tx, .rx_buffer = rx};
    /* Bus lock: the MAX31865 transaction in the control task waits for this one. */
    if (spi_device_acquire_bus(hw.ext_adc, pdMS_TO_TICKS(2)) != ESP_OK) return false;
    esp_err_t e = spi_device_polling_transmit(hw.ext_adc, &t);
    spi_device_release_bus(hw.ext_adc);
    return e == ESP_OK && n21_mcp3202_decode(rx, code);
}

/* ------------------------------------------------------------------ GPIO: LINE_ZC, read-backs */
static void IRAM_ATTR line_zc_isr(void *arg)
{
    (void)arg;
    uint64_t t = (uint64_t)esp_timer_get_time();
    bool level = gpio_get_level(N21_GPIO_LINE_ZC);
    portENTER_CRITICAL_ISR(&hw.zc_mux);
    uint8_t next = (uint8_t)((hw.zc_head + 1u) % 16u);
    if (next != hw.zc_tail) {
        hw.zc_t[hw.zc_head] = t;
        hw.zc_level[hw.zc_head] = level;
        hw.zc_head = next;
    }
    portEXIT_CRITICAL_ISR(&hw.zc_mux);
}

static size_t hw_line_zc_edges(void *ctx, uint64_t *t, bool *lv, size_t max)
{
    (void)ctx;
    size_t n = 0;
    portENTER_CRITICAL(&hw.zc_mux);
    while (hw.zc_tail != hw.zc_head && n < max) {
        t[n] = hw.zc_t[hw.zc_tail];
        lv[n] = hw.zc_level[hw.zc_tail];
        hw.zc_tail = (uint8_t)((hw.zc_tail + 1u) % 16u);
        n++;
    }
    portEXIT_CRITICAL(&hw.zc_mux);
    return n;
}

static bool hw_read_status(void *ctx, n21_status_rb_t *s)
{
    (void)ctx;
    s->permit = gpio_get_level(N21_GPIO_PERMIT_RB) == 1;
    s->bus_fault = gpio_get_level(N21_GPIO_BUS_FAULT_RB) == 1;
    s->rail_ok = gpio_get_level(N21_GPIO_RAIL_OK_RB) == 1;
    /* SUP_RUN_OK is expander P14 (C27). A stale or failed snapshot is a failed read, which the
     * binding treats as an input fault. */
    ctrl_exp_cache_t c;
    (void)ctrl_board_expander(&c);
    bool fresh = ctrl_exp_fresh(&c, (uint64_t)esp_timer_get_time(), CTRL_EXP_MAX_AGE_US);
    s->sup_run_ok = fresh && ctrl_exp_decode(c.raw).sup_run_ok;
    return fresh;
}

/* RUN_EN (GPIO14, C23): ANDed with the interlock latch by U37, so it only removes permission.
 * Preset low and made an output by ctrl_board_init(); this only changes its level. */
static bool hw_run_gate(void *ctx, bool on)
{
    (void)ctx;
    return ctrl_board_set_run_en(on);
}

static bool hw_interlock_reset_pulse(void *ctx)
{
    (void)ctx;
    /* A falling edge on IL_RESET_N is a reset *request*; the latch grants PERMIT only with every
     * source healthy for >= 1 ms. Idle high. */
    if (gpio_set_level(N21_GPIO_IL_RESET_N, 0) != ESP_OK) return false;
    esp_rom_delay_us(20);
    return gpio_set_level(N21_GPIO_IL_RESET_N, 1) == ESP_OK;
}

static bool gpio_create(void)
{
    gpio_config_t in = {.pin_bit_mask = (1ULL << N21_GPIO_PERMIT_RB) | (1ULL << N21_GPIO_BUS_FAULT_RB) |
                                        (1ULL << N21_GPIO_RAIL_OK_RB),
                        .mode = GPIO_MODE_INPUT};
    gpio_config_t zc = {.pin_bit_mask = 1ULL << N21_GPIO_LINE_ZC, .mode = GPIO_MODE_INPUT,
                        .intr_type = GPIO_INTR_ANYEDGE};
    /* Preload high so configuring the output is not itself a falling edge. */
    gpio_config_t rst = {.pin_bit_mask = 1ULL << N21_GPIO_IL_RESET_N, .mode = GPIO_MODE_OUTPUT};
    if (gpio_set_level(N21_GPIO_IL_RESET_N, 1) != ESP_OK || gpio_config(&rst) != ESP_OK ||
        gpio_set_level(N21_GPIO_IL_RESET_N, 1) != ESP_OK || gpio_config(&in) != ESP_OK ||
        gpio_config(&zc) != ESP_OK)
        return false;
    esp_err_t e = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) return false;
    return gpio_isr_handler_add(N21_GPIO_LINE_ZC, line_zc_isr, NULL) == ESP_OK;
}

/* ------------------------------------------------------------------ glue */
static uint64_t hw_now(void *ctx) { (void)ctx; return (uint64_t)esp_timer_get_time(); }
static void hw_lock(void *ctx) { (void)ctx; xSemaphoreTake(hw.mutex, portMAX_DELAY); }
static void hw_unlock(void *ctx) { (void)ctx; xSemaphoreGive(hw.mutex); }

static void acq_tick(void *arg) { (void)arg; xTaskNotifyGive(hw.acq_task); }
static void acq_task(void *arg)
{
    (void)arg;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        n21_acquire_step(&binding);
#if CONFIG_TEMPER_POWER_SHADOW_RMS
        static unsigned shadow_log_n;
        if (++shadow_log_n % 1600u == 0) { /* about 1 s at the 625 us acquisition period */
            n21_telemetry_t t;
            n21_telemetry(&binding, &t);
            ESP_LOGI(TAG, "tank rms: ad8436 %.2f A, shadow %.2f A (%s, adc %u S/s), f %u Hz",
                     (double)t.last_half.est.tank_rms_a, (double)t.shadow_rms_a,
                     t.shadow_valid ? "valid" : "invalid", (unsigned)t.shadow_fs_hz, (unsigned)t.freq_hz);
        }
#endif
    }
}

static n21_config_t config_from_kconfig(void)
{
    n21_config_t c = n21_config_default();
#if CONFIG_TEMPER_POWER_MODE_BENCH
    c.mode = N21_MODE_BENCH;
#elif CONFIG_TEMPER_POWER_MODE_COMMISSIONED
    c.mode = N21_MODE_COMMISSIONED;
#else
    c.mode = N21_MODE_INHIBITED;
#endif
#if CONFIG_TEMPER_POWER_CALIBRATED
    c.calibrated = true;
#endif
    c.freq.f_max_hz = CONFIG_TEMPER_POWER_F_MAX_HZ;
    c.freq.f_min_hz = CONFIG_TEMPER_POWER_F_MIN_HZ;
    c.freq.pan_q_max = CONFIG_TEMPER_POWER_PAN_Q_MAX_X10 * 0.1f;
    c.freq.pan_r_min_ohm = CONFIG_TEMPER_POWER_PAN_R_MIN_MOHM * 1e-3f;
    /* Commissioned tank ceiling (COMMISSIONING.md "Raising the commissioned tank ceiling"). Out of
     * range leaves the config invalid, so init refuses it. */
    (void)n21_config_set_tank_ceiling(&c, CONFIG_TEMPER_POWER_TANK_CEILING_DA * 0.1f);
    c.limits.est_error = CONFIG_TEMPER_POWER_EST_ERROR_PPM * 1e-6f;
    c.line_zc.cal_offset_us = CONFIG_TEMPER_POWER_LINE_ZC_OFFSET_US;
    c.vsw_delay_ns = CONFIG_TEMPER_POWER_VSW_DELAY_NS;
    c.ct_zc_delay_ns = CONFIG_TEMPER_POWER_CT_ZC_DELAY_NS;
#if CONFIG_TEMPER_POWER_CT_ZC_INVERTED
    c.ct_zc_inverted = true;
#endif
    c.analog.vbus_offset_mv = CONFIG_TEMPER_POWER_VBUS_OFFSET_UV * 1e-3f;
    c.analog.vbus_gain_trim = CONFIG_TEMPER_POWER_VBUS_GAIN_PPM * 1e-6f;
    c.analog.ct_mon_zero_mv = (float)CONFIG_TEMPER_POWER_CT_MON_ZERO_MV;
    c.analog.rms_gain_trim = CONFIG_TEMPER_POWER_RMS_GAIN_PPM * 1e-6f;
    return c;
}

n21_binding_t *n21_hw_binding(void) { return started ? &binding : NULL; }

n21_init_t n21_hw_start(void)
{
    if (started) return N21_INIT_ERROR;
    /* Pads low before any peripheral exists (D-25); RUN_EN low (it already is from ctrl_board_init). */
    (void)pads_gpio_low();
    (void)ctrl_board_set_run_en(false);
    hw.mutex = xSemaphoreCreateMutex();
    hw.cap_mutex = xSemaphoreCreateMutex();
    if (!hw.mutex || !hw.cap_mutex || !gpio_create() || !pwm_create() || !cap_create() ||
        !adc_create() || !ext_adc_create()) {
        ESP_LOGE(TAG, "binding hardware setup failed; pads held low");
        (void)force_off();
        (void)pads_gpio_low();
        return N21_INIT_ERROR;
    }
    const n21_hw_ops_t ops = {
        .now_us = hw_now, .lock = hw_lock, .unlock = hw_unlock,
        .pwm_program = hw_pwm_program, .pwm_update = hw_pwm_update, .pwm_outputs = hw_pwm_outputs,
        .pwm_capture = hw_pwm_capture,
        .run_gate = hw_run_gate, /* RUN_EN, GPIO14 (L2, C23; closes the hardware side of H1) */
        .read_status = hw_read_status, .interlock_reset_pulse = hw_interlock_reset_pulse,
        .read_adc1 = hw_read_adc1, .read_ext_adc = hw_read_ext_adc, .read_ct_zc = hw_read_ct_zc,
        .line_zc_edges = hw_line_zc_edges,
#if CONFIG_TEMPER_POWER_SHADOW_RMS
        .shadow_half = hw_shadow_half,
#endif
        .ctx = &hw,
    };
    const n21_config_t cfg = config_from_kconfig();
    power_binding_t pb;
    n21_init_t r = n21_binding_init(&binding, &cfg, &ops, &pb);
    started = r != N21_INIT_ERROR;
    if (started) {
        const esp_timer_create_args_t ta = {.callback = acq_tick, .name = "n21_acq"};
        if (xTaskCreatePinnedToCore(acq_task, "n21_acq", 4096, NULL, 19, &hw.acq_task, 1) != pdPASS ||
            esp_timer_create(&ta, &hw.acq_timer) != ESP_OK ||
            esp_timer_start_periodic(hw.acq_timer, cfg.acq_period_us) != ESP_OK) {
            ESP_LOGE(TAG, "acquisition start failed; staying inhibited");
            (void)hw_pwm_outputs(&hw, false);
            return N21_INIT_ERROR;
        }
    }
    if (r == N21_INIT_BIND && !power_service_bind(&pb)) {
        ESP_LOGE(TAG, "power_service_bind refused; staying inhibited");
        (void)hw_pwm_outputs(&hw, false);
        return N21_INIT_ERROR;
    }
    ESP_LOGW(TAG, "native-21 binding: init result %d (1 inhibited, 2 bench, 3 bound, 4 no run gate, "
                  "5 not calibrated)", (int)r);
    return r;
}
