/* Integrated controller pin map (layout L2 + L3 blower lines): the table, the boot sequence, RUN_EN,
 * the strap rules, the UART0 console rule and the TCA9555 plan. Assertions are the oracle (built
 * with -UNDEBUG). The map itself is cross-checked against the controller ato by
 * firmware/tools/check_controller_pinmap.py (pytest: firmware/tools/test_check_controller_pinmap.py).
 *
 * Strap rules are restated here from the ESP32-S3 datasheet (Table 2-1/2-2, "Strapping Pins")
 * rather than taken from the firmware, so the table is checked against an independent copy. */
#include "controller_board.h"
#include "n21_pins.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#ifndef SDKCONFIG_DEFAULTS_PATH
#error "SDKCONFIG_DEFAULTS_PATH must point at firmware/sdkconfig.defaults"
#endif

static unsigned tests;
#define TEST(fn) do { fn(); tests++; printf("PASS %s\n", #fn); } while (0)

/* ------------------------------------------------------------------ recording GPIO fake */
typedef struct { int gpio; char op; int arg; ctrl_pull_t pull; } op_t; /* op: 'L' level, 'C' config */
static op_t ops_log[128];
static unsigned n_ops;
static int level[49];
static bool fail_gpio[49];

static bool f_set(void *c, int gpio, int lvl)
{
    (void)c;
    assert(n_ops < 128);
    ops_log[n_ops++] = (op_t){gpio, 'L', lvl, CTRL_PULL_NONE};
    if (fail_gpio[gpio]) return false;
    level[gpio] = lvl;
    return true;
}
static bool f_cfg(void *c, int gpio, bool output, ctrl_pull_t pull)
{
    (void)c;
    assert(n_ops < 128);
    ops_log[n_ops++] = (op_t){gpio, 'C', output, pull};
    return !fail_gpio[gpio];
}
static const ctrl_gpio_ops_t OPS = {.set_level = f_set, .config = f_cfg, .ctx = NULL};
static void fake_reset(void)
{
    n_ops = 0;
    memset(level, 0, sizeof level);
    memset(fail_gpio, 0, sizeof fail_gpio);
    for (int g = 0; g < 49; g++) level[g] = -1; /* unknown until written */
}

/* ------------------------------------------------------------------ map */
static bool module_gpio(int g)
{
    /* ESP32-S3-WROOM-1U-N8 pins: GPIO0-21 and 35-48. 26-32 are the in-package flash; 22-25
     * do not exist; 33/34 are not on the module's pads. */
    return (g >= 0 && g <= 21) || (g >= 35 && g <= 48);
}

static void test_no_duplicate_gpio_or_net(void)
{
    for (size_t i = 0; i < ctrl_pins_count; i++) {
        assert(module_gpio(ctrl_pins[i].gpio));
        for (size_t j = i + 1; j < ctrl_pins_count; j++) {
            if (ctrl_pins[i].gpio == ctrl_pins[j].gpio)
                printf("duplicate GPIO%d: %s / %s\n", ctrl_pins[i].gpio, ctrl_pins[i].net, ctrl_pins[j].net);
            assert(ctrl_pins[i].gpio != ctrl_pins[j].gpio);
            assert(strcmp(ctrl_pins[i].net, ctrl_pins[j].net) != 0);
        }
    }
    /* Every module GPIO is used on this board: there is no spare pin to move anything to. */
    unsigned module = 0;
    for (int g = 0; g < 49; g++) module += module_gpio(g);
    assert(ctrl_pins_count == module);
}

static void test_expander_bits_unique(void)
{
    const int bits[] = {CTRL_EXP_RTD_DRDY, CTRL_EXP_LATCHED_FAULT_RB, CTRL_EXP_RTD_FAULT_RB,
                        CTRL_EXP_HS_FAULT_RB, CTRL_EXP_COIL_FAULT_RB, CTRL_EXP_SUP_RUN_OK_RB,
                        CTRL_EXP_FAN_OFF, CTRL_EXP_RTD2_CS_RESERVED};
    const size_t n = sizeof bits / sizeof bits[0];
    for (size_t i = 0; i < n; i++) {
        assert(bits[i] >= 0 && bits[i] <= 15);
        for (size_t j = i + 1; j < n; j++) assert(bits[i] != bits[j]);
    }
    /* The pins that moved onto the expander in L2 are no longer GPIOs. */
    assert(ctrl_pin_by_net("rtd_drdy") == NULL);
    assert(ctrl_pin_by_net("sup_run_ok_rb") == NULL);
    assert(CTRL_EXP_RTD_DRDY == 7);       /* P07 */
    assert(CTRL_EXP_SUP_RUN_OK_RB == 12); /* P14 */
}

static void test_l2_moves(void)
{
    /* The L2 list, one assertion per moved signal. */
    assert(ctrl_pin_find(14) == ctrl_pin_by_net("run_en"));
    assert(ctrl_pin_find(37) == ctrl_pin_by_net("i2c_sda"));
    assert(ctrl_pin_find(0) == ctrl_pin_by_net("boot_io0") && CTRL_GPIO_I2C_SCL == 0);
    assert(ctrl_pin_find(9) == ctrl_pin_by_net("rim_adc") && CTRL_ADC1_CH_RIM_ADC == 8);
    assert(ctrl_pin_find(40) == ctrl_pin_by_net("ui_sck"));
    assert(ctrl_pin_find(41) == ctrl_pin_by_net("ui_mosi"));
    assert(ctrl_pin_find(44) == ctrl_pin_by_net("ui_miso"));
    assert(ctrl_pin_find(47) == ctrl_pin_by_net("ui_cs_oled_n"));
    assert(ctrl_pin_find(45) == ctrl_pin_by_net("ui_dc"));
    assert(ctrl_pin_find(48) == ctrl_pin_by_net("ui_cs_exp_n"));
    /* ESP32-S3 ADC1: GPIOn is ADC1_CH(n-1) for n = 1..10; every analog row is on ADC1. */
    const struct { int gpio, ch; } adc[] = {
        {CTRL_GPIO_CT_MON_ADC, CTRL_ADC1_CH_CT_MON_ADC}, {CTRL_GPIO_VBUS_ADC, CTRL_ADC1_CH_VBUS_ADC},
        {CTRL_GPIO_HS_ADC, CTRL_ADC1_CH_HS_ADC}, {CTRL_GPIO_COIL_ADC, CTRL_ADC1_CH_COIL_ADC},
        {CTRL_GPIO_M12_ADC, CTRL_ADC1_CH_M12_ADC}, {CTRL_GPIO_RIM_ADC, CTRL_ADC1_CH_RIM_ADC}};
    for (size_t i = 0; i < sizeof adc / sizeof adc[0]; i++) {
        assert(adc[i].ch == adc[i].gpio - 1);
        assert(ctrl_pin_find(adc[i].gpio)->fn == CTRL_FN_ADC);
    }
    for (size_t i = 0; i < ctrl_pins_count; i++)
        if (ctrl_pins[i].fn == CTRL_FN_ADC) assert(ctrl_pins[i].gpio >= 1 && ctrl_pins[i].gpio <= 10);
    /* The UI bus and the RTD / MCP3202 bus share no pin (C26). */
    const int ui[] = {40, 41, 44, 45, 47, 48}, rtd[] = {10, 11, 12, 13, 42};
    for (size_t i = 0; i < 6; i++)
        for (size_t j = 0; j < 5; j++) assert(ui[i] != rtd[j]);
    /* The native-21 binding sees the same numbers. */
    assert(N21_GPIO_RUN_EN == 14 && N21_EXP_SUP_RUN_OK_RB == CTRL_EXP_SUP_RUN_OK_RB);
    assert(N21_GPIO_SPI_SCK == 11 && N21_GPIO_SPI_MOSI == 13 && N21_GPIO_SPI_MISO == 12);
    assert(N21_ADC1_CH_RIM == 8);
}

/* ------------------------------------------------------------------ straps */
typedef enum { MUST_READ_HIGH, MUST_READ_LOW, EFUSE_ONLY } strap_kind_t;
static const struct {
    int gpio;
    strap_kind_t kind;
    unsigned allowed_fns; /* bit per ctrl_fn_t */
} STRAPS[] = {
    {0, MUST_READ_HIGH, 1u << CTRL_FN_I2C | 1u << CTRL_FN_GPIO_IN},            /* SPI boot */
    {3, EFUSE_ONLY, 1u << CTRL_FN_GPIO_IN | 1u << CTRL_FN_PCNT},               /* JTAG select */
    {45, MUST_READ_LOW, 1u << CTRL_FN_GPIO_OUT | 1u << CTRL_FN_GPIO_IN},       /* VDD_SPI 3.3 V */
    {46, MUST_READ_LOW, 1u << CTRL_FN_LEDC | 1u << CTRL_FN_GPIO_OUT | 1u << CTRL_FN_GPIO_IN},
};

static void test_strap_pins_used_only_as_allowed(void)
{
    for (size_t i = 0; i < sizeof STRAPS / sizeof STRAPS[0]; i++) {
        const ctrl_pin_t *p = ctrl_pin_find(STRAPS[i].gpio);
        assert(p);
        assert(STRAPS[i].allowed_fns & (1u << p->fn));
        switch (STRAPS[i].kind) {
        case MUST_READ_HIGH:
            assert(p->external_pull == CTRL_PULL_UP && p->internal_pull != CTRL_PULL_DOWN);
            assert(p->fn != CTRL_FN_GPIO_OUT);
            break;
        case MUST_READ_LOW:
            assert(p->external_pull == CTRL_PULL_DOWN && p->internal_pull != CTRL_PULL_UP);
            if (p->fn == CTRL_FN_GPIO_OUT || p->fn == CTRL_FN_LEDC) assert(p->init_level == 0);
            break;
        case EFUSE_ONLY:
            assert(p->fn == CTRL_FN_GPIO_IN || p->fn == CTRL_FN_PCNT);
            break;
        }
    }
    /* What the boot sequence actually does to them. */
    fake_reset();
    assert(ctrl_board_apply_pins(&OPS));
    for (unsigned k = 0; k < n_ops; k++) {
        const op_t *o = &ops_log[k];
        if (o->gpio == 45 || o->gpio == 46) {
            assert(!(o->op == 'C' && o->pull == CTRL_PULL_UP));
            assert(!(o->op == 'L' && o->arg != 0));
        }
        /* GPIO0 and GPIO3 belong to the I2C / PCNT drivers; GPIO46 is left at reset (L3 stub). */
        assert(o->gpio != 0 && o->gpio != 3 && o->gpio != 46);
    }
}

/* ------------------------------------------------------------------ RUN_EN */
static void test_run_en_defaults_low(void)
{
    const ctrl_pin_t *p = ctrl_pin_find(CTRL_GPIO_RUN_EN);
    assert(p && p->fn == CTRL_FN_GPIO_OUT && p->boot_apply && p->owner == CTRL_OWNER_BOARD);
    assert(p->init_level == 0 && p->internal_pull != CTRL_PULL_UP && p->external_pull == CTRL_PULL_DOWN);

    /* Boot: the first touch of GPIO14 writes 0, then makes it an output; it is never 1. */
    fake_reset();
    assert(ctrl_board_apply_pins(&OPS));
    int first = -1, config = -1;
    for (unsigned k = 0; k < n_ops; k++) {
        if (ops_log[k].gpio != CTRL_GPIO_RUN_EN) continue;
        if (first < 0) first = (int)k;
        if (ops_log[k].op == 'C') { config = (int)k; assert(ops_log[k].arg == 1); }
        if (ops_log[k].op == 'L') assert(ops_log[k].arg == 0);
        if (ops_log[k].op == 'C') assert(ops_log[k].pull != CTRL_PULL_UP);
    }
    assert(first >= 0 && config > first && ops_log[first].op == 'L' && ops_log[first].arg == 0);
    assert(level[CTRL_GPIO_RUN_EN] == 0);

    /* Run gate: on, off, kill; after the kill "on" is refused and the pad stays low. */
    ctrl_run_en_t st = {0};
    assert(!st.on && !st.killed);
    assert(ctrl_run_en_request(&st, &OPS, true) && level[CTRL_GPIO_RUN_EN] == 1 && st.on);
    assert(ctrl_run_en_request(&st, &OPS, false) && level[CTRL_GPIO_RUN_EN] == 0 && !st.on);
    assert(ctrl_run_en_request(&st, &OPS, true) && level[CTRL_GPIO_RUN_EN] == 1);
    assert(ctrl_run_en_kill(&st, &OPS) && level[CTRL_GPIO_RUN_EN] == 0);
    assert(!ctrl_run_en_request(&st, &OPS, true) && level[CTRL_GPIO_RUN_EN] == 0 && !st.on);
    assert(ctrl_run_en_request(&st, &OPS, false));
    /* A failed write never reports "on". */
    ctrl_run_en_t st2 = {0};
    fail_gpio[CTRL_GPIO_RUN_EN] = true;
    assert(!ctrl_run_en_request(&st2, &OPS, true) && !st2.on);
}

static void test_boot_outputs_preset_before_enable(void)
{
    fake_reset();
    assert(ctrl_board_apply_pins(&OPS));
    for (size_t i = 0; i < ctrl_pins_count; i++) {
        const ctrl_pin_t *p = &ctrl_pins[i];
        if (!p->boot_apply || p->fn != CTRL_FN_GPIO_OUT) continue;
        int seen_level = 0;
        for (unsigned k = 0; k < n_ops; k++) {
            if (ops_log[k].gpio != p->gpio) continue;
            if (ops_log[k].op == 'L') { assert(ops_log[k].arg == p->init_level); seen_level = 1; }
            if (ops_log[k].op == 'C') assert(seen_level);
        }
        assert(level[p->gpio] == p->init_level);
    }
    /* A failing pad is reported, and the other rows are still applied. */
    fake_reset();
    fail_gpio[CTRL_GPIO_IL_WDI] = true;
    assert(!ctrl_board_apply_pins(&OPS));
    assert(level[CTRL_GPIO_RUN_EN] == 0 && level[CTRL_GPIO_UI_DC] == 0);
}

/* ------------------------------------------------------------------ console */
static void test_uart0_console_disabled_when_gpio44_is_spi(void)
{
    const ctrl_pin_t *p = ctrl_pin_find(44);
    assert(p && p->fn == CTRL_FN_SPI && strcmp(p->net, "ui_miso") == 0);
    assert(CTRL_CONSOLE_UART0_ALLOWED == 0);
    /* No row is a UART RX, and USB-Serial-JTAG keeps 19/20. */
    assert(ctrl_pin_find(19)->fn == CTRL_FN_USB && ctrl_pin_find(20)->fn == CTRL_FN_USB);

    FILE *f = fopen(SDKCONFIG_DEFAULTS_PATH, "r");
    assert(f);
    char line[256];
    bool usb_jtag = false, uart_console = false, secondary_none = false;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#') continue;
        if (strstr(line, "CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y")) usb_jtag = true;
        if (strstr(line, "CONFIG_ESP_CONSOLE_UART_DEFAULT=y") ||
            strstr(line, "CONFIG_ESP_CONSOLE_UART_CUSTOM=y") ||
            strstr(line, "CONFIG_ESP_CONSOLE_UART=y") ||
            strstr(line, "CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y"))
            uart_console = true;
        if (strstr(line, "CONFIG_ESP_CONSOLE_SECONDARY_NONE=y")) secondary_none = true;
    }
    fclose(f);
    assert(usb_jtag && !uart_console && secondary_none);
}

/* ------------------------------------------------------------------ TCA9555 */
static void test_expander_plan_and_decode(void)
{
    ctrl_i2c_write_t w[6];
    size_t n = ctrl_exp_init_writes(false, w);
    bool cfg0 = false, cfg1 = false;
    for (size_t i = 0; i < n; i++) {
        if (w[i].reg == TCA9555_REG_CONFIG0) { cfg0 = true; assert(w[i].value == 0xFF); }
        if (w[i].reg == TCA9555_REG_CONFIG1) { cfg1 = true; assert(w[i].value == 0xFF); }
        assert(w[i].reg != TCA9555_REG_OUTPUT0 && w[i].reg != TCA9555_REG_OUTPUT1);
        if (w[i].reg == TCA9555_REG_POLARITY0 || w[i].reg == TCA9555_REG_POLARITY1) assert(w[i].value == 0);
    }
    assert(cfg0 && cfg1);

    /* L3: FAN_OFF output. Its latch is written 0 (blower on) BEFORE P15 becomes an output. */
    n = ctrl_exp_init_writes(true, w);
    int out1 = -1, conf1 = -1;
    for (size_t i = 0; i < n; i++) {
        if (w[i].reg == TCA9555_REG_OUTPUT1) { out1 = (int)i; assert(!(w[i].value & (1u << (CTRL_EXP_FAN_OFF - 8)))); }
        if (w[i].reg == TCA9555_REG_CONFIG1) {
            conf1 = (int)i;
            assert(w[i].value == (uint8_t)~(1u << (CTRL_EXP_FAN_OFF - 8))); /* only P15 is an output */
        }
        if (w[i].reg == TCA9555_REG_CONFIG0) assert(w[i].value == 0xFF);    /* P07 DRDY stays an input */
    }
    assert(out1 >= 0 && conf1 > out1);

    /* Decode: idle board (all pulled high, DRDY high) = run ok, no faults, no DRDY. */
    ctrl_exp_inputs_t in = ctrl_exp_decode(0xFFFF & ~(CTRL_EXP_BIT(CTRL_EXP_LATCHED_FAULT_RB) |
                                                       CTRL_EXP_BIT(CTRL_EXP_RTD_FAULT_RB) |
                                                       CTRL_EXP_BIT(CTRL_EXP_HS_FAULT_RB) |
                                                       CTRL_EXP_BIT(CTRL_EXP_COIL_FAULT_RB)));
    assert(!in.rtd_drdy && in.sup_run_ok && !in.latched_fault && !in.rtd_fault && !in.hs_fault && !in.coil_fault);
    in = ctrl_exp_decode(0x0000);
    assert(in.rtd_drdy && !in.sup_run_ok);
    in = ctrl_exp_decode(CTRL_EXP_BIT(CTRL_EXP_HS_FAULT_RB));
    assert(in.hs_fault && !in.coil_fault && in.rtd_drdy && !in.sup_run_ok);

    /* Freshness: invalid, stale and future snapshots are not ok. */
    ctrl_exp_cache_t c = {.raw = 0xFFFF, .t_us = 1000, .valid = false};
    assert(!ctrl_exp_fresh(&c, 1000, CTRL_EXP_MAX_AGE_US));
    c.valid = true;
    assert(ctrl_exp_fresh(&c, 1000 + CTRL_EXP_MAX_AGE_US, CTRL_EXP_MAX_AGE_US));
    assert(!ctrl_exp_fresh(&c, 1001 + CTRL_EXP_MAX_AGE_US, CTRL_EXP_MAX_AGE_US));
    assert(!ctrl_exp_fresh(&c, 999, CTRL_EXP_MAX_AGE_US));
    assert(!ctrl_exp_fresh(NULL, 1000, CTRL_EXP_MAX_AGE_US));
}

int main(void)
{
    TEST(test_no_duplicate_gpio_or_net);
    TEST(test_expander_bits_unique);
    TEST(test_l2_moves);
    TEST(test_strap_pins_used_only_as_allowed);
    TEST(test_run_en_defaults_low);
    TEST(test_boot_outputs_preset_before_enable);
    TEST(test_uart0_console_disabled_when_gpio44_is_spi);
    TEST(test_expander_plan_and_decode);
    printf("controller pin map: %u tests passed\n", tests);
    return 0;
}
