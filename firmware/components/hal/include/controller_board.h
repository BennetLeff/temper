#ifndef TEMPER_CONTROLLER_BOARD_H
#define TEMPER_CONTROLLER_BOARD_H
/*
 * Integrated SELV controller board layer (pure, host-tested by firmware/test/test_controller_pins.c).
 *
 *  - ctrl_pins[]: one row per used GPIO, built from controller_pins.h. It is both the documented
 *    map (no duplicates, strap rules, owners) and the input of ctrl_board_apply_pins(), so the
 *    tests check what the firmware actually applies at boot.
 *  - TCA9555 (U8) register plan and input decoding.
 *  - RUN_EN (GPIO14, DECISIONS C23): preset low before the pad becomes an output; the only
 *    firmware action on it is to remove or restore permission, never to bypass the latch.
 *
 * The ESP-IDF glue is components/hal/esp32/controller_board_esp32.c.
 */
#include "controller_pins.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { CTRL_PULL_NONE = 0, CTRL_PULL_UP, CTRL_PULL_DOWN } ctrl_pull_t;

typedef enum {
    CTRL_FN_GPIO_IN = 0, /* plain digital input */
    CTRL_FN_GPIO_OUT,    /* plain push-pull output */
    CTRL_FN_ADC,         /* ADC1 analog input */
    CTRL_FN_MCPWM,       /* bridge PWM output (n21 binding; loop-back captured) */
    CTRL_FN_CAPTURE,     /* MCPWM capture input */
    CTRL_FN_SPI,         /* SPI master signal (SCK/MOSI/MISO/CS) */
    CTRL_FN_I2C,         /* I2C master, open drain */
    CTRL_FN_LEDC,        /* LEDC PWM output (L3 blower speed) */
    CTRL_FN_PCNT,        /* pulse counter input (blower tach) */
    CTRL_FN_USB,         /* USB-Serial-JTAG pad */
    CTRL_FN_UART_TX,     /* UART0 TX, ROM log only */
} ctrl_fn_t;

typedef enum {
    CTRL_OWNER_BOARD = 0, /* ctrl_board_apply_pins() at boot */
    CTRL_OWNER_N21,       /* components/power/n21_hw_esp32.c */
    CTRL_OWNER_SAFETY,    /* components/safety (TPS3823 heartbeat) */
    CTRL_OWNER_RTD,       /* rtd_service / MCP3202 on SPI2 */
    CTRL_OWNER_UI,        /* UI bus on SPI3 */
    CTRL_OWNER_I2C,       /* TCA9555 I2C master */
    CTRL_OWNER_THERMAL,   /* ADC1 thermal channels */
    CTRL_OWNER_BLOWER,    /* L3 blower: STUB, pins left at reset */
    CTRL_OWNER_ROM,       /* console / ROM log: never reconfigured */
} ctrl_owner_t;

typedef struct {
    int gpio;
    const char *net;           /* ato net name (lower case) */
    ctrl_fn_t fn;
    ctrl_owner_t owner;
    ctrl_pull_t internal_pull; /* what firmware enables on the pad */
    ctrl_pull_t external_pull; /* what the board fits */
    int init_level;            /* outputs: level written before the pad is an output; else -1 */
    bool boot_apply;           /* configured by ctrl_board_apply_pins() */
} ctrl_pin_t;

extern const ctrl_pin_t ctrl_pins[];
extern const size_t ctrl_pins_count;

const ctrl_pin_t *ctrl_pin_find(int gpio);
const ctrl_pin_t *ctrl_pin_by_net(const char *net);

/* Minimal GPIO operations, so the boot sequence is host-testable. */
typedef struct {
    bool (*set_level)(void *ctx, int gpio, int level);
    bool (*config)(void *ctx, int gpio, bool output, ctrl_pull_t pull);
    void *ctx;
} ctrl_gpio_ops_t;

/* Applies every boot_apply row: for outputs the level is written first, then the pad is made an
 * output, so no row ever glitches (RUN_EN stays low throughout). Returns false if any call fails;
 * every row is still attempted. */
bool ctrl_board_apply_pins(const ctrl_gpio_ops_t *ops);

/* RUN_EN (C23). on=false removes permission; on=true only lets the interlock latch through.
 * ctrl_run_en_kill() is the firmware safety cut (runaway boundary, latched faults): it drives
 * RUN_EN low and refuses every later request for "on" until the MCU resets. It replaces the legacy
 * board's RUNAWAY_CUT output, which does not exist on this board (GPIO15 is PWM_HB here). */
typedef struct {
    bool on;
    bool killed;
} ctrl_run_en_t;
bool ctrl_run_en_request(ctrl_run_en_t *st, const ctrl_gpio_ops_t *ops, bool on);
bool ctrl_run_en_kill(ctrl_run_en_t *st, const ctrl_gpio_ops_t *ops);

/* ---------------------------------------------------------------- TCA9555 */
enum {
    TCA9555_REG_INPUT0 = 0, TCA9555_REG_INPUT1 = 1, TCA9555_REG_OUTPUT0 = 2, TCA9555_REG_OUTPUT1 = 3,
    TCA9555_REG_POLARITY0 = 4, TCA9555_REG_POLARITY1 = 5, TCA9555_REG_CONFIG0 = 6, TCA9555_REG_CONFIG1 = 7,
};
#define CTRL_EXP_BIT(n) ((uint16_t)(1u << (n)))

typedef struct { uint8_t reg, value; } ctrl_i2c_write_t;

/* Register writes, in order, for the expander. With fan_off_output=false (today: the L3 blower
 * driver is a stub) every pin stays an input, as at power-up. With true, OUTPUT1 is written with
 * FAN_OFF = 0 (blower on) BEFORE CONFIG1 makes P15 an output: the TCA9555 output register powers
 * up as 1s, so the reverse order would switch the blower off. Returns the count (<= 6). */
size_t ctrl_exp_init_writes(bool fan_off_output, ctrl_i2c_write_t out[6]);

typedef struct {
    bool rtd_drdy;      /* P07 low: a MAX31865 conversion is ready */
    bool latched_fault; /* P10 high */
    bool rtd_fault;     /* P11 high */
    bool hs_fault;      /* P12 high */
    bool coil_fault;    /* P13 high */
    bool sup_run_ok;    /* P14 high */
} ctrl_exp_inputs_t;

/* raw = INPUT0 | INPUT1 << 8 */
ctrl_exp_inputs_t ctrl_exp_decode(uint16_t raw);

/* A cached snapshot of the input port, refreshed by the control task. */
typedef struct {
    uint16_t raw;
    uint64_t t_us;
    bool valid;
} ctrl_exp_cache_t;

/* True only for a valid snapshot no older than max_age_us. A stale or failed read must be treated
 * as "not ok" by every consumer (SUP_RUN_OK false, DRDY not seen). */
bool ctrl_exp_fresh(const ctrl_exp_cache_t *c, uint64_t now_us, uint64_t max_age_us);

/* Snapshot age limit for SUP_RUN_OK consumers: five 10 ms control ticks. */
#define CTRL_EXP_MAX_AGE_US 50000u

/* ---------------------------------------------------------------- ESP32 glue (target only) */
#if defined(ESP_PLATFORM)
bool ctrl_board_init(void);                       /* pins, I2C + expander, UI SPI3 bus */
bool ctrl_board_set_run_en(bool on);              /* GPIO14; "on" refused after a kill */
bool ctrl_board_run_en_kill(void);                /* latched until MCU reset */
bool ctrl_board_poll_expander(void);              /* control task, every tick */
bool ctrl_board_expander(ctrl_exp_cache_t *out);  /* copy of the cache (any task) */
/* STUB, controller L3 (hardware in progress): blower on J10. on=false -> FAN_OFF (P15) high;
 * drive 0..1 -> GPIO46 LEDC duty via blower_pwm_duty_from_drive(). Tach: GPIO3 PCNT in Hz.
 * Both return false (not implemented) and touch no pin, which leaves the blower at its hardware
 * default: running (L2: fan-off gate pulled down; L3: full speed with GPIO46 pulled down). */
bool ctrl_board_blower_drive(bool on, float drive);
bool ctrl_board_blower_tach_hz(float *hz);
#endif

#endif
