/*
 * Integrated SELV controller board layer: pin table, boot sequence, RUN_EN and TCA9555 plan.
 * Pure C, no ESP-IDF: host-tested by firmware/test/test_controller_pins.c and cross-checked
 * against the controller ato by firmware/tools/check_controller_pinmap.py.
 */
#include "controller_board.h"
#include <string.h>

#define ROW(g, net, fn, owner, ipull, epull, lvl, apply) \
    {(g), (net), (fn), (owner), (ipull), (epull), (lvl), (apply)}

/* external_pull: a resistor to v3v3 / selv_gnd on the MCU net, or behind one series resistor
 * <= 1 kOhm (the checker derives it from the ato the same way). */
const ctrl_pin_t ctrl_pins[] = {
    /* J4 bridge drive: the n21 binding forces the pads low (D-25) and owns them. */
    ROW(CTRL_GPIO_PWM_HA_MCU, "pwm_ha_mcu", CTRL_FN_MCPWM, CTRL_OWNER_N21, CTRL_PULL_DOWN, CTRL_PULL_DOWN, 0, false),
    ROW(CTRL_GPIO_PWM_LA_MCU, "pwm_la_mcu", CTRL_FN_MCPWM, CTRL_OWNER_N21, CTRL_PULL_DOWN, CTRL_PULL_DOWN, 0, false),
    ROW(CTRL_GPIO_PWM_HB_MCU, "pwm_hb_mcu", CTRL_FN_MCPWM, CTRL_OWNER_N21, CTRL_PULL_DOWN, CTRL_PULL_DOWN, 0, false),
    ROW(CTRL_GPIO_PWM_LB_MCU, "pwm_lb_mcu", CTRL_FN_MCPWM, CTRL_OWNER_N21, CTRL_PULL_DOWN, CTRL_PULL_DOWN, 0, false),
    /* Interlock */
    ROW(CTRL_GPIO_IL_RESET_N, "il_reset_n", CTRL_FN_GPIO_OUT, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, 1, false),
    ROW(CTRL_GPIO_IL_WDI, "il_wdi", CTRL_FN_GPIO_OUT, CTRL_OWNER_SAFETY, CTRL_PULL_NONE, CTRL_PULL_NONE, 0, true),
    ROW(CTRL_GPIO_RUN_EN, "run_en", CTRL_FN_GPIO_OUT, CTRL_OWNER_BOARD, CTRL_PULL_NONE, CTRL_PULL_DOWN, 0, true),
    ROW(CTRL_GPIO_BUS_FAULT_RB, "bus_fault_rb", CTRL_FN_GPIO_IN, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_RAIL_OK_RB, "rail_ok_rb", CTRL_FN_GPIO_IN, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_PERMIT_RB, "permit_rb", CTRL_FN_GPIO_IN, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    /* RTD / MCP3202 bus (SPI2) */
    ROW(CTRL_GPIO_RTD_CS_N, "rtd_cs_n", CTRL_FN_SPI, CTRL_OWNER_RTD, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_RTD_SCK, "rtd_sck", CTRL_FN_SPI, CTRL_OWNER_RTD, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_RTD_SDO, "rtd_sdo", CTRL_FN_SPI, CTRL_OWNER_RTD, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_RTD_SDI, "rtd_sdi", CTRL_FN_SPI, CTRL_OWNER_RTD, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_EXT_ADC_CS_N, "ext_adc_cs_n", CTRL_FN_SPI, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    /* Zero-cross captures */
    ROW(CTRL_GPIO_CT_ZC_MCU, "ct_zc_mcu", CTRL_FN_CAPTURE, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_LINE_ZC_MCU, "line_zc_mcu", CTRL_FN_GPIO_IN, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    /* ADC1 */
    ROW(CTRL_GPIO_CT_MON_ADC, "ct_mon_adc", CTRL_FN_ADC, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_VBUS_ADC, "vbus_adc", CTRL_FN_ADC, CTRL_OWNER_N21, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_HS_ADC, "hs_adc", CTRL_FN_ADC, CTRL_OWNER_THERMAL, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_COIL_ADC, "coil_adc", CTRL_FN_ADC, CTRL_OWNER_THERMAL, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_M12_ADC, "m12_adc", CTRL_FN_ADC, CTRL_OWNER_THERMAL, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_RIM_ADC, "rim_adc", CTRL_FN_ADC, CTRL_OWNER_THERMAL, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    /* I2C to the TCA9555: external 4.7 k pull-ups only. GPIO0 is the SPI-boot strap. */
    ROW(CTRL_GPIO_I2C_SDA, "i2c_sda", CTRL_FN_I2C, CTRL_OWNER_I2C, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    ROW(CTRL_GPIO_BOOT_IO0, "boot_io0", CTRL_FN_I2C, CTRL_OWNER_I2C, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    /* UI bus J7 (SPI3). MISO gets the weak pull-up so an unplugged UI board reads 1s, not noise.
     * D/C is a strap (GPIO45): output preset low, no internal pull of any kind. */
    ROW(CTRL_GPIO_UI_SCK, "ui_sck", CTRL_FN_SPI, CTRL_OWNER_UI, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_UI_MOSI, "ui_mosi", CTRL_FN_SPI, CTRL_OWNER_UI, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_UI_MISO, "ui_miso", CTRL_FN_SPI, CTRL_OWNER_UI, CTRL_PULL_UP, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_UI_CS_OLED_N, "ui_cs_oled_n", CTRL_FN_SPI, CTRL_OWNER_UI, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    ROW(CTRL_GPIO_UI_CS_EXP_N, "ui_cs_exp_n", CTRL_FN_SPI, CTRL_OWNER_UI, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    ROW(CTRL_GPIO_UI_DC, "ui_dc", CTRL_FN_GPIO_OUT, CTRL_OWNER_UI, CTRL_PULL_NONE, CTRL_PULL_DOWN, 0, true),
    /* Blower J10 (L3, C28): owned by the LEDC / PCNT drivers in controller_board_esp32.c, not
     * boot_apply. GPIO46 (strap, 100 k pull-down): LEDC starts at duty 0 = low = full speed, never
     * an internal pull-up. GPIO3: FG via 10 k pull-up, ESD5Z3.3 and 1 k / 1 nF; input only. */
    ROW(CTRL_GPIO_FAN_PWM, "fan_pwm", CTRL_FN_LEDC, CTRL_OWNER_BLOWER, CTRL_PULL_NONE, CTRL_PULL_DOWN, 0, false),
    ROW(CTRL_GPIO_FAN_TACH, "fan_tach", CTRL_FN_PCNT, CTRL_OWNER_BLOWER, CTRL_PULL_NONE, CTRL_PULL_UP, -1, false),
    /* Console and ROM log: USB-Serial-JTAG; UART0 TX only for the ROM log. */
    ROW(CTRL_GPIO_USB_DN, "usb_dn", CTRL_FN_USB, CTRL_OWNER_ROM, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_USB_DP, "usb_dp", CTRL_FN_USB, CTRL_OWNER_ROM, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
    ROW(CTRL_GPIO_UART_TX, "uart_tx", CTRL_FN_UART_TX, CTRL_OWNER_ROM, CTRL_PULL_NONE, CTRL_PULL_NONE, -1, false),
};
const size_t ctrl_pins_count = sizeof ctrl_pins / sizeof ctrl_pins[0];

const ctrl_pin_t *ctrl_pin_find(int gpio)
{
    for (size_t i = 0; i < ctrl_pins_count; i++)
        if (ctrl_pins[i].gpio == gpio) return &ctrl_pins[i];
    return NULL;
}

const ctrl_pin_t *ctrl_pin_by_net(const char *net)
{
    for (size_t i = 0; net && i < ctrl_pins_count; i++)
        if (strcmp(ctrl_pins[i].net, net) == 0) return &ctrl_pins[i];
    return NULL;
}

bool ctrl_board_apply_pins(const ctrl_gpio_ops_t *ops)
{
    if (!ops || !ops->set_level || !ops->config) return false;
    bool ok = true;
    for (size_t i = 0; i < ctrl_pins_count; i++) {
        const ctrl_pin_t *p = &ctrl_pins[i];
        if (!p->boot_apply) continue;
        if (p->fn == CTRL_FN_GPIO_OUT) {
            /* Level first: the output latch holds it before the driver is enabled. */
            if (!ops->set_level(ops->ctx, p->gpio, p->init_level)) ok = false;
            if (!ops->config(ops->ctx, p->gpio, true, p->internal_pull)) ok = false;
            if (!ops->set_level(ops->ctx, p->gpio, p->init_level)) ok = false;
        } else if (p->fn == CTRL_FN_GPIO_IN) {
            if (!ops->config(ops->ctx, p->gpio, false, p->internal_pull)) ok = false;
        }
    }
    return ok;
}

bool ctrl_run_en_request(ctrl_run_en_t *st, const ctrl_gpio_ops_t *ops, bool on)
{
    if (!st || !ops || !ops->set_level) return false;
    bool refused = on && st->killed;
    if (refused) on = false;
    bool ok = ops->set_level(ops->ctx, CTRL_GPIO_RUN_EN, on ? 1 : 0);
    if (!ok && on) (void)ops->set_level(ops->ctx, CTRL_GPIO_RUN_EN, 0);
    st->on = ok && on;
    /* A refused "on" (after a kill) is a failure the caller must see. */
    return ok && !refused;
}

bool ctrl_run_en_kill(ctrl_run_en_t *st, const ctrl_gpio_ops_t *ops)
{
    if (!st) return false;
    st->killed = true;
    st->on = false;
    return ops && ops->set_level && ops->set_level(ops->ctx, CTRL_GPIO_RUN_EN, 0);
}

uint8_t ctrl_exp_output1(bool fan_off)
{
    uint8_t bit = (uint8_t)(1u << (CTRL_EXP_FAN_OFF - 8));
    return fan_off ? (uint8_t)0xFFu : (uint8_t)(0xFFu & ~bit);
}

size_t ctrl_exp_init_writes(bool fan_off_output, ctrl_i2c_write_t out[6])
{
    size_t n = 0;
    /* No polarity inversion anywhere: the read-backs are decoded in ctrl_exp_decode(). */
    out[n++] = (ctrl_i2c_write_t){TCA9555_REG_POLARITY0, 0x00};
    out[n++] = (ctrl_i2c_write_t){TCA9555_REG_POLARITY1, 0x00};
    if (fan_off_output) {
        /* FAN_OFF = 0 (blower on) latched before P15 becomes an output; others stay 1. */
        out[n++] = (ctrl_i2c_write_t){TCA9555_REG_OUTPUT1, ctrl_exp_output1(false)};
        out[n++] = (ctrl_i2c_write_t){TCA9555_REG_CONFIG0, 0xFF};
        out[n++] = (ctrl_i2c_write_t){TCA9555_REG_CONFIG1,
                                      (uint8_t)(0xFFu & ~(1u << (CTRL_EXP_FAN_OFF - 8)))};
    } else {
        out[n++] = (ctrl_i2c_write_t){TCA9555_REG_CONFIG0, 0xFF};
        out[n++] = (ctrl_i2c_write_t){TCA9555_REG_CONFIG1, 0xFF};
    }
    return n;
}

ctrl_exp_inputs_t ctrl_exp_decode(uint16_t raw)
{
    return (ctrl_exp_inputs_t){
        .rtd_drdy = (raw & CTRL_EXP_BIT(CTRL_EXP_RTD_DRDY)) == 0,
        .latched_fault = (raw & CTRL_EXP_BIT(CTRL_EXP_LATCHED_FAULT_RB)) != 0,
        .rtd_fault = (raw & CTRL_EXP_BIT(CTRL_EXP_RTD_FAULT_RB)) != 0,
        .hs_fault = (raw & CTRL_EXP_BIT(CTRL_EXP_HS_FAULT_RB)) != 0,
        .coil_fault = (raw & CTRL_EXP_BIT(CTRL_EXP_COIL_FAULT_RB)) != 0,
        .sup_run_ok = (raw & CTRL_EXP_BIT(CTRL_EXP_SUP_RUN_OK_RB)) != 0,
        .blw_pg = (raw & CTRL_EXP_BIT(CTRL_EXP_BLW_PG)) != 0,
    };
}

void ctrl_blw_pg_init(ctrl_blw_pg_debounce_t *d)
{
    memset(d, 0, sizeof *d);
    d->state = CTRL_BLW_PG_UNKNOWN;
}

ctrl_blw_pg_t ctrl_blw_pg_update(ctrl_blw_pg_debounce_t *d, bool read_ok, uint16_t raw)
{
    if (!d) return CTRL_BLW_PG_UNKNOWN;
    if (!read_ok) {
        ctrl_blw_pg_init(d); /* never "present" (nor "absent") on a bus we cannot read */
        return d->state;
    }
    bool level = (raw & CTRL_EXP_BIT(CTRL_EXP_BLW_PG)) != 0;
    if (d->run == 0u || level != d->last_level) {
        d->last_level = level;
        d->run = 1u;
    } else if (d->run < 0xFFu) {
        d->run++;
    }
    if (d->run >= CTRL_BLW_PG_DEBOUNCE_POLLS)
        d->state = level ? CTRL_BLW_PG_PRESENT : CTRL_BLW_PG_ABSENT;
    return d->state;
}

ctrl_blw_pg_t ctrl_exp_blw_pg(const ctrl_exp_cache_t *c, uint64_t now_us, uint64_t max_age_us)
{
    return ctrl_exp_fresh(c, now_us, max_age_us) ? c->blw_pg : CTRL_BLW_PG_UNKNOWN;
}

bool ctrl_exp_fresh(const ctrl_exp_cache_t *c, uint64_t now_us, uint64_t max_age_us)
{
    return c && c->valid && now_us >= c->t_us && now_us - c->t_us <= max_age_us;
}
