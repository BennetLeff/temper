/**
 * @file pan_io.c
 * @brief Native-21 inputs of the C1 pan loop (ESP-IDF only): stage power, rim NTC, heatsink NTC.
 *
 * The sensor-r3 rim and heatsink drivers are used unchanged over the binding's continuous ADC1 frame
 * means (n21_hw_thermal_mv): one fixed 12 dB range, so the attenuation the drivers ask for is ignored
 * (their range rules only raise the resolution). The rail is reported as not measured: the drivers
 * then assume 3.300 V and the cold soak uses its wider threshold (pan_cold_soak.h).
 * Without CONFIG_TEMPER_POWER_HW_BINDING nothing is readable and every check fails closed.
 */
#include "sdkconfig.h"
#include "pan_control.h"
#include "../components/control/thermal_mgmt.h"
#include "esp_timer.h"
#include "hs_ntc.h"
#include "platform_logic.h"
#include "rim_ntc.h"
#if CONFIG_TEMPER_POWER_HW_BINDING
#include "n21_hw.h"
#include "n21_binding.h"
#endif

#define PAN_IO_MAX_AGE_US 20000u

extern uint32_t get_time_ms(void);

bool read_stage_power(pan_stage_power_t *out)
{
    *out = (pan_stage_power_t){0};
#if CONFIG_TEMPER_POWER_HW_BINDING
    static uint32_t s_halves;
    n21_binding_t *b = n21_hw_binding();
    if (b == NULL) return false;
    n21_telemetry_t t;
    n21_telemetry(b, &t);
    /* About 12 half cycles close per 100 ms control period; none means the estimate is stale. */
    out->valid = platform_stage_power(t.have_half, t.halves_ok, &s_halves, t.last_half.est.tank_rms_a,
                                      t.last_half.est.p_inv_w, &out->p_inv_w);
#endif
    return out->valid;
}

#if CONFIG_TEMPER_POWER_HW_BINDING
static bool read_mv(unsigned idx, const ntc_channel_t *ch, float *mv)
{
    float all[N21_THERMAL_COUNT];
    if (!ntc_input_settled(ch, (uint32_t)(esp_timer_get_time() / 1000)) ||
        !n21_hw_thermal_mv(all, PAN_IO_MAX_AGE_US)) return false;
    *mv = all[idx];
    return true;
}
#endif

static bool rim_node_mv(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    (void)atten;
#if CONFIG_TEMPER_POWER_HW_BINDING
    return read_mv(N21_THERMAL_RIM, &THERMAL_NTC_RIM, mv);
#else
    (void)mv;
    return false;
#endif
}

static bool hs_pin_mv(void *ctx, rim_atten_t atten, float *mv)
{
    (void)ctx;
    (void)atten;
#if CONFIG_TEMPER_POWER_HW_BINDING
    return read_mv(N21_THERMAL_HS, &THERMAL_NTC_SINK, mv);
#else
    (void)mv;
    return false;
#endif
}

static bool rail_not_measured(void *ctx, float *mv)
{
    (void)ctx;
    (void)mv;
    return false;
}

const rim_ntc_hal_t *rim_ntc_board_hal(void)
{
    static const rim_ntc_hal_t hal = {.read_node_mv = rim_node_mv, .read_v3v3_mv = rail_not_measured};
    return &hal;
}

bool read_heatsink_ntc(hs_ntc_reading_t *out)
{
    static const hs_ntc_hal_t hal = {.read_pin_mv = hs_pin_mv, .read_v3v3_mv = rail_not_measured};
    static hs_ntc_t s_hs;
    static bool s_init;
    if (!s_init) {
        hs_ntc_params_t p;
        hs_ntc_default_params(&p);
        s_init = hs_ntc_init(&s_hs, &p);
    }
    hs_ntc_poll(&s_hs, &hal, get_time_ms(), out);
    return out->state == HS_NTC_VALID;
}
