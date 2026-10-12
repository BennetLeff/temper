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
    CTRL_OWNER_BLOWER,    /* L3 blower: LEDC (GPIO46) and PCNT (GPIO3) drivers, not boot_apply */
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

/* Register writes, in order, for the expander. With fan_off_output=true (L3) OUTPUT1 is written
 * with FAN_OFF = 0 (blower on) BEFORE CONFIG1 makes P15 an output: the TCA9555 output register
 * powers up as 1s, so the reverse order would switch the blower off. With false every pin stays an
 * input, as at power-up (the 10 k gate pull-down keeps the blower running). Every other pin,
 * including BLW_PG (P16, driven by the V15_BLW divider), stays an input either way. Returns the
 * count. */
size_t ctrl_exp_init_writes(bool fan_off_output, ctrl_i2c_write_t out[6]);
/* OUTPUT1 value for a FAN_OFF request: only P15 is an output, the other port-1 bits stay 1. */
uint8_t ctrl_exp_output1(bool fan_off);

typedef struct {
    bool rtd_drdy;      /* P07 low: a MAX31865 conversion is ready */
    bool latched_fault; /* P10 high */
    bool rtd_fault;     /* P11 high */
    bool hs_fault;      /* P12 high */
    bool coil_fault;    /* P13 high */
    bool sup_run_ok;    /* P14 high */
    bool blw_pg;        /* P16 high: PS3 present (raw level, one read; use the debounced cache) */
} ctrl_exp_inputs_t;

/* raw = INPUT0 | INPUT1 << 8 */
ctrl_exp_inputs_t ctrl_exp_decode(uint16_t raw);

/* BLW_PG (P16, DECISIONS C33): the blower supply PS3 as the firmware believes it. UNKNOWN is never
 * "present" and never "absent": the expander read failed, the snapshot is stale, or the level has
 * not been the same for CTRL_BLW_PG_DEBOUNCE_POLLS polls yet since boot or since a failed read. */
typedef enum {
    CTRL_BLW_PG_UNKNOWN = 0,
    CTRL_BLW_PG_ABSENT,  /* P16 low on every one of the last CTRL_BLW_PG_DEBOUNCE_POLLS polls */
    CTRL_BLW_PG_PRESENT, /* P16 high on every one of the last CTRL_BLW_PG_DEBOUNCE_POLLS polls */
} ctrl_blw_pg_t;

/* Consecutive identical reads before the debounced state changes: 3 x the 10 ms poll = 30 ms. */
#define CTRL_BLW_PG_DEBOUNCE_POLLS 3u

typedef struct {
    ctrl_blw_pg_t state; /* debounced */
    bool last_level;     /* level of the current run */
    uint8_t run;         /* consecutive reads at last_level (saturates) */
} ctrl_blw_pg_debounce_t;

void ctrl_blw_pg_init(ctrl_blw_pg_debounce_t *d);
/* One expander poll. read_ok=false (failed I2C read) drops the state to UNKNOWN at once and restarts
 * the count, so a recovered bus needs CTRL_BLW_PG_DEBOUNCE_POLLS good reads before it reports
 * either level. A changed level holds the previous debounced state until it has repeated
 * CTRL_BLW_PG_DEBOUNCE_POLLS times. Returns the debounced state. */
ctrl_blw_pg_t ctrl_blw_pg_update(ctrl_blw_pg_debounce_t *d, bool read_ok, uint16_t raw);

/* A cached snapshot of the input port, refreshed by the control task. */
typedef struct {
    uint16_t raw;
    uint64_t t_us;
    bool valid;
    ctrl_blw_pg_t blw_pg; /* debounced P16, updated on every poll (UNKNOWN after a failed read) */
} ctrl_exp_cache_t;

/* True only for a valid snapshot no older than max_age_us. A stale or failed read must be treated
 * as "not ok" by every consumer (SUP_RUN_OK false, DRDY not seen). */
bool ctrl_exp_fresh(const ctrl_exp_cache_t *c, uint64_t now_us, uint64_t max_age_us);

/* Snapshot age limit for SUP_RUN_OK consumers: five 10 ms control ticks. */
#define CTRL_EXP_MAX_AGE_US 50000u

/* BLW_PG for a consumer: the cache's debounced state if the snapshot is fresh, else UNKNOWN. */
ctrl_blw_pg_t ctrl_exp_blw_pg(const ctrl_exp_cache_t *c, uint64_t now_us, uint64_t max_age_us);

/* L3 blower PWM (GPIO46, LEDC): 20 kHz behind the 12.1 k / 1 uF (13 Hz) filter leaves < 10 mV of
 * ripple at the buck output; 10-bit duty (LEDC: 80 MHz / 20 kHz allows up to 11 bits). */
#define CTRL_BLOWER_LEDC_FREQ_HZ  20000u
#define CTRL_BLOWER_LEDC_RES_BITS    10u
/* PCNT glitch filter on the FG input (S3 maximum ~12.7 us); FG pulses are milliseconds long. */
#define CTRL_BLOWER_TACH_GLITCH_NS 10000u

/* ---------------------------------------------------------------- ESP32 glue (target only) */
#if defined(ESP_PLATFORM)
bool ctrl_board_init(void);                       /* pins, I2C + expander, UI SPI3 bus */
bool ctrl_board_set_run_en(bool on);              /* GPIO14; "on" refused after a kill */
bool ctrl_board_run_en_kill(void);                /* latched until MCU reset */
bool ctrl_board_poll_expander(void);              /* control task, every tick; debounces BLW_PG */
bool ctrl_board_expander(ctrl_exp_cache_t *out);  /* copy of the cache (any task) */
/* L3 blower on J10 (DECISIONS C28). The decisions are blower_ctrl_step() (thermal_mgmt.c); these
 * only move bits.
 *  - ctrl_board_blower_apply(): GPIO46 LEDC compare counts (blower_ledc_counts(); 0 = full speed)
 *    and expander P15 FAN_OFF.
 *    Any LEDC failure stops the channel at idle level 0 = full speed; FAN_OFF is only ever set
 *    high on an explicit off request, and every reset leaves it an input (blower on).
 *  - ctrl_board_blower_tach_count(): GPIO3 PCNT rising edges, as a free-running 16-bit count. */
bool ctrl_board_blower_apply(bool on, uint32_t ledc_counts);
bool ctrl_board_blower_tach_count(uint16_t *count);
#endif

#endif
