/**
 * @file mock_max31865.c
 * @brief MAX31865 fault-detection model on the SPI mock (see mock_max31865.h).
 */

#include "mock_max31865.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "../include/hal_spi.h"
#include "../include/hal_timer.h"
#include "../include/temper_pins.h"

#define REG_CONFIG 0x00u
#define REG_FAULT  0x07u

#define CFG_VBIAS  0x80u
#define CFG_AUTO   0x40u
#define CFG_1SHOT  0x20u
#define CFG_FC     0x0Cu
#define CFG_CLEAR  0x02u

#define AUTO_DELAY_US 100u   /* data sheet Figure 4: the automatic cycle's delays */

extern uint8_t mock_spi_get_register(hal_spi_device_t device, uint8_t reg);
extern void mock_spi_set_register(hal_spi_device_t device, uint8_t reg, uint8_t value);
typedef void (*mock_spi_write_hook_t)(intptr_t device, uint8_t reg, const uint8_t *data, size_t len);
extern void mock_spi_set_write_hook(mock_spi_write_hook_t hook);
typedef void (*mock_spi_read_hook_t)(intptr_t device, uint8_t reg, size_t len);
extern void mock_spi_set_read_hook(mock_spi_read_hook_t hook);
extern void mock_gpio_trigger_interrupt(hal_pin_t pin);

static struct {
    bool attached;
    intptr_t dev;
    mock_max31865_input_t input;
    bool vbias;
    bool sw_open;          /* FORCE- switch open (inside a cycle) */
    bool step1_pending;    /* manual step 1 done, waiting for step 2 */
    uint64_t t_change;     /* last analog change (VBIAS, switch, input) */
    float refn0, rtdn0;    /* node values at t_change, fraction of VBIAS */
    uint64_t t_closed;     /* when FORCE- last closed after a cycle, or VBIAS came on */
    bool converting;
    uint64_t t_conv_start;
    uint32_t auto_cycles, manual_cycles, fast_steps, early_restarts, conv_starts;
    uint8_t last_bits;
    bool drdy_expander;    /* DRDY as a level on the expander (zapote), not a GPIO edge */
    bool drdy_low;
} m;

static uint64_t now_us(void)
{
    return (uint64_t)HAL_TIME_US();
}

static void targets(float *refn, float *rtdn)
{
    const mock_max31865_afe_dc_t *d = &k_mock_max31865_afe_dc[m.input];
    if (!m.vbias) {
        *refn = d->refn_rest;
        *rtdn = d->rtdin_n_rest;
    } else if (m.sw_open) {
        *refn = d->refn_open;
        *rtdn = d->rtdin_n_open;
    } else {
        *refn = d->refn_closed;
        *rtdn = d->rtdin_n_closed;
    }
}

static void nodes(uint64_t t, float *refn, float *rtdn)
{
    float tr, tn;
    targets(&tr, &tn);
    const double dt = t > m.t_change ? (double)(t - m.t_change) : 0.0;
    const float k = (float)exp(-dt / (double)MOCK_MAX31865_AFE_TAU_US);
    *refn = tr + (m.refn0 - tr) * k;
    *rtdn = tn + (m.rtdn0 - tn) * k;
}

/* Snapshot the nodes at t, then the caller changes the analog state. */
static void begin_change(uint64_t t)
{
    nodes(t, &m.refn0, &m.rtdn0);
    m.t_change = t;
}

static uint8_t closed_check(uint64_t t)
{
    float r, n;
    nodes(t, &r, &n);
    (void)n;
    return r > MOCK_MAX31865_AFE_COMPARATOR ? 0x20u : 0u;   /* D5 */
}

static uint8_t open_check(uint64_t t)
{
    float r, n;
    nodes(t, &r, &n);
    uint8_t b = 0u;
    if (r < MOCK_MAX31865_AFE_COMPARATOR) {
        b |= 0x10u;   /* D4 */
    }
    if (n < MOCK_MAX31865_AFE_COMPARATOR) {
        b |= 0x08u;   /* D3 */
    }
    return b;
}

static void set_switch(uint64_t t, bool open)
{
    if (m.sw_open != open) {
        begin_change(t);
        m.sw_open = open;
        if (!open) {
            m.t_closed = t;
        }
    }
}

static void on_config(uint8_t v)
{
    const uint64_t t = now_us();
    hal_spi_device_t dev = (hal_spi_device_t)m.dev;
    uint8_t status = mock_spi_get_register(dev, REG_FAULT);
    uint8_t cfg = v;

    /* D1: "Write a 1 to this bit while writing 0 to bits D5, D3, and D2". */
    if ((v & CFG_CLEAR) != 0u) {
        if ((v & (CFG_1SHOT | CFG_FC)) == 0u) {
            status = 0u;
        }
        cfg = (uint8_t)(cfg & (uint8_t)~CFG_CLEAR);   /* self-clearing */
    }
    const bool vbias = (v & CFG_VBIAS) != 0u;
    if (vbias != m.vbias) {
        begin_change(t);
        m.vbias = vbias;
        if (vbias) {
            m.t_closed = t;
        }
    }
    const bool conv = vbias && (v & CFG_AUTO) != 0u;
    if (conv && !m.converting) {
        m.conv_starts++;
        m.t_conv_start = t;
        if (t - m.t_closed < MOCK_MAX31865_AFE_RESTART_MIN_US) {
            m.early_restarts++;
        }
    }
    m.converting = conv;

    const uint8_t fc = v & CFG_FC;
    /* "if 1 is written to D5 (1-Shot) and D2 or D3 in a single write, both
     * commands are ignored." */
    const bool ignored = (v & CFG_1SHOT) != 0u && fc != 0u;
    if (!ignored) {
        if (fc == 0x04u || (fc == 0x0Cu && !m.step1_pending)) {
            /* automatic: 100 us, closed check, FORCE- open, 100 us, open check */
            m.auto_cycles++;
            uint8_t b = closed_check(t + AUTO_DELAY_US);
            set_switch(t + AUTO_DELAY_US, true);
            b |= open_check(t + 2u * AUTO_DELAY_US);
            set_switch(t + 2u * AUTO_DELAY_US, false);
            m.last_bits = b;
            status |= b;
            cfg = (uint8_t)(cfg & (uint8_t)~CFG_FC);
        } else if (fc == 0x08u) {
            if (t - m.t_change < MOCK_MAX31865_AFE_STEP_MIN_US) {
                m.fast_steps++;
            }
            const uint8_t b = closed_check(t);
            set_switch(t, true);
            m.step1_pending = true;
            m.last_bits = b;
            status |= b;
        } else if (fc == 0x0Cu) {
            if (t - m.t_change < MOCK_MAX31865_AFE_STEP_MIN_US) {
                m.fast_steps++;
            }
            const uint8_t b = open_check(t);
            set_switch(t, false);
            m.step1_pending = false;
            m.manual_cycles++;
            m.last_bits = (uint8_t)(m.last_bits | b);
            status |= b;
            cfg = (uint8_t)(cfg & (uint8_t)~CFG_FC);   /* D3:D2 self-clear */
        } else if (m.step1_pending) {
            /* step 1 abandoned: the switch closes again */
            set_switch(t, false);
            m.step1_pending = false;
        }
    }
    mock_spi_set_register(dev, REG_FAULT, status);
    mock_spi_set_register(dev, REG_CONFIG, cfg);
}

static void write_hook(intptr_t device, uint8_t reg, const uint8_t *data, size_t len)
{
    if (!m.attached || device != m.dev || len == 0u) {
        return;
    }
    if (reg == (0x80u | REG_CONFIG) || reg == REG_CONFIG) {
        on_config(data[0]);
    }
}

/* "When a read operation of an RTD resistance data register occurs, DRDY
 * returns high" (19-6478 Rev 3). */
static void read_hook(intptr_t device, uint8_t reg, size_t len)
{
    if (m.attached && device == m.dev && len > 0u && reg <= 0x02u && reg + len > 0x01u) {
        m.drdy_low = false;
    }
}

void mock_max31865_drdy_assert(void)
{
    if (m.drdy_expander) {
        m.drdy_low = true;
    } else {
        mock_gpio_trigger_interrupt(PIN_RTD_DRDY);
    }
}

void mock_max31865_set_drdy_expander(bool on)
{
    m.drdy_expander = on;
    m.drdy_low = false;
}

bool mock_max31865_drdy_high(void)
{
    return !m.drdy_low;
}

void mock_max31865_attach(int device_index)
{
    memset(&m, 0, sizeof(m));
    m.attached = true;
    m.dev = (intptr_t)device_index;
    m.input = MOCK_MAX31865_INPUT_HEALTHY;
    m.t_change = now_us();
    m.refn0 = k_mock_max31865_afe_dc[m.input].refn_rest;
    m.rtdn0 = k_mock_max31865_afe_dc[m.input].rtdin_n_rest;
    mock_spi_set_write_hook(write_hook);
    mock_spi_set_read_hook(read_hook);
}

void mock_max31865_detach(void)
{
    m.attached = false;
}

void mock_max31865_set_input(mock_max31865_input_t input)
{
    if (input >= MOCK_MAX31865_INPUT_COUNT || input == m.input) {
        return;
    }
    begin_change(now_us());
    m.input = input;
}

mock_max31865_input_t mock_max31865_input(void) { return m.input; }
uint32_t mock_max31865_auto_cycles(void) { return m.auto_cycles; }
uint32_t mock_max31865_manual_cycles(void) { return m.manual_cycles; }
uint32_t mock_max31865_fast_steps(void) { return m.fast_steps; }
uint32_t mock_max31865_early_restarts(void) { return m.early_restarts; }
uint32_t mock_max31865_conversion_starts(void) { return m.conv_starts; }
uint64_t mock_max31865_conversion_start_us(void) { return m.t_conv_start; }
bool mock_max31865_converting(void) { return m.converting; }
uint8_t mock_max31865_last_cycle_bits(void) { return m.last_bits; }
