/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 */

#include "rtd_service.h"

#include "hal.h"
#include "max31865.h"
#include "rail_adc.h"
#include "state_machine.h"
#include "tca9555.h"
#include "temper_pins.h"

/* The expander DRDY path needs the bring-up pin map's TCA9555 symbols
 * (temper_pins.h: EXP_RTD_DRDY, TEMPER_EXPANDER_I2C_ADDR); a pin map without
 * them has no expander path, and a DRDY that is not a GPIO then fails closed. */
#if defined(EXP_RTD_DRDY) && defined(TEMPER_EXPANDER_I2C_ADDR)
#define RTD_HAVE_EXPANDER_DRDY 1
#else
#define RTD_HAVE_EXPANDER_DRDY 0
#endif

#ifdef TEMPER_PAN_CONTROL_C1
#include "config.h"
#include "rtd_convert.h"

/* CR-1 sense-line filter fitted on the controller: enables the CR-7 loading
 * correction. zapote/controller C37 (controller-c1-crs 467917c38) applied CR-1
 * exactly as specified, so the C1 board has it (DECISIONS.md D-FCYC); the
 * manual fault cycle below assumes the same board. */
#ifndef RTD_FRONT_END_CR1
#define RTD_FRONT_END_CR1 1
#endif

typedef enum {
    RTD_C1_PHASE_BIAS = 0,        /* VBIAS on, conversions off: wait STEP          */
    RTD_C1_PHASE_STEP1 = 1,       /* manual step 1 written: wait STEP              */
    RTD_C1_PHASE_STEP2 = 2,       /* manual step 2 written: poll D3:D2, read 07h   */
    RTD_C1_PHASE_RESTART = 3,     /* cycle read: wait RESTART from step 2, 0xC0    */
    RTD_C1_PHASE_CONVERTING = 4,
} rtd_c1_phase_t;

typedef enum {
    RTD_C1_VERIFY_NONE = 0,       /* no verification held                          */
    RTD_C1_VERIFY_REQUESTED = 1,  /* the reset policy asked; starts next tick      */
    RTD_C1_VERIFY_RUNNING = 2,    /* the cycle is running                          */
    RTD_C1_VERIFY_CYCLE_CLEAN = 3,/* 07h read 0; waiting for an unflagged conversion */
    RTD_C1_VERIFY_CLEAN = 4,      /* verified: the next reset may consume it       */
} rtd_c1_verify_t;

static rtd_c1_phase_t s_c1_phase;
static uint64_t s_c1_phase_t0_us;   /* when the phase's wait started              */
static uint64_t s_c1_step2_us;      /* when step 2 was written                    */
static uint8_t s_c1_phase_ticks;    /* ticks spent in the phase                   */
static bool s_c1_power_up;          /* the running cycle is the power-up one      */
static rtd_c1_verify_t s_c1_verify;
static uint32_t s_c1_cycles;
static uint8_t s_c1_cycle_status;
static bool s_c1_first_drdy;        /* waiting for the first conversion after 0xC0 */
static rtd_convert_params_t s_c1_conv;
static rtd_sample_t s_c1_sample;
static bool s_c1_have_sample;
static uint16_t s_c1_same_code;
static bool s_c1_last_flag;        /* fault flag of the latest conversion */
#endif

/* SPI2 maps to HAL bus zero. MAX31865 supports mode 1 and a 500 kHz clock is
 * comfortably below its 5 MHz maximum while board bring-up remains pending. */
#define RTD_SPI2_BUS       0
#define RTD_SPI_CLOCK_HZ   500000u

static max31865_device_t s_max31865;
static volatile bool s_drdy_complete;
static bool s_ready;
static bool s_bootstrap_failed;
static bool s_bootstrap_failure_reported;
static uint8_t s_drdy_wait_ticks;
static void rtd_drdy_isr(hal_pin_t pin, void *context);
static rtd_drdy_source_t s_drdy_request = RTD_DRDY_AUTO;
static rtd_drdy_source_t s_drdy_source;
static uint32_t s_drdy_poll_failures;

void rtd_service_set_drdy_source(rtd_drdy_source_t source)
{
    s_drdy_request = source;
}

rtd_drdy_source_t rtd_service_drdy_source(void)
{
    return s_drdy_source;
}

uint32_t rtd_service_drdy_poll_failures(void)
{
    return s_drdy_poll_failures;
}

/* The expander poll (D-DRDY): DRDY low is a completed conversion. */
static void poll_expander_drdy(void)
{
#if RTD_HAVE_EXPANDER_DRDY
    bool high = true;
    if (!tca9555_board_read_pin(EXP_RTD_DRDY, &high)) {
        s_drdy_poll_failures++;   /* no DRDY this tick; the stale rule bounds it */
        return;
    }
    if (!high) {
        s_drdy_complete = true;
    }
#endif
}

/* Bring up the DRDY path the board has (D-DRDY). */
static hal_status_t drdy_init(void)
{
    rtd_drdy_source_t src = s_drdy_request;
    if (src == RTD_DRDY_AUTO) {
        src = (PIN_RTD_DRDY != HAL_PIN_INVALID) ? RTD_DRDY_GPIO : RTD_DRDY_EXPANDER;
    }
    s_drdy_source = src;
    s_drdy_poll_failures = 0u;
    if (src == RTD_DRDY_GPIO) {
        if (PIN_RTD_DRDY == HAL_PIN_INVALID) {
            return HAL_ERROR_INVALID_ARG;
        }
        hal_status_t status = HAL_GPIO_INIT(PIN_RTD_DRDY, HAL_GPIO_MODE_INPUT);
        if (status != HAL_OK) {
            return status;
        }
        /* MAX31865 DRDY is active-low; only its falling edge marks a completed
         * conversion. */
        return hal_gpio->set_interrupt(PIN_RTD_DRDY, HAL_GPIO_INTR_FALLING, rtd_drdy_isr, NULL);
    }
#if RTD_HAVE_EXPANDER_DRDY
    hal_status_t status = tca9555_board_attach();
    if (status != HAL_OK) {
        return status;
    }
    bool high = true;
    /* The expander must answer before the service counts on it. */
    return tca9555_board_read_pin(EXP_RTD_DRDY, &high) ? HAL_OK : HAL_ERROR;
#else
    return HAL_ERROR_NOT_READY;
#endif
}

static void rtd_drdy_isr(hal_pin_t pin, void *context)
{
    (void)pin;
    (void)context;

    /* No SPI, logging, allocation, or state-machine mutation in interrupt
     * context. The control task atomically consumes this single-bit handoff. */
    s_drdy_complete = true;
}

static void report_bootstrap_failure_once(void)
{
    if (!s_bootstrap_failure_reported) {
        s_bootstrap_failure_reported = true;
        state_machine_report_rtd_device_fault(false, true, NULL);
    }
}

hal_status_t rtd_service_bootstrap(void)
{
    const hal_spi_config_t spi_config = {
        .clock_hz = RTD_SPI_CLOCK_HZ,
        .mode = 1u,
        .pin_mosi = PIN_SPI_MOSI,
        .pin_miso = PIN_SPI_MISO,
        .pin_sclk = PIN_SPI_CLK,
        .pin_cs = PIN_SPI_CS_RTD1,
        .cs_active_high = false,
    };
    hal_spi_device_t spi_device = NULL;
    hal_status_t status;

    s_max31865.spi_device = NULL;
    s_drdy_complete = false;
    s_ready = false;
    s_bootstrap_failed = false;
    s_bootstrap_failure_reported = false;
    s_drdy_wait_ticks = 0u;

    if (hal_spi == NULL || hal_gpio == NULL) {
        s_bootstrap_failed = true;
        return HAL_ERROR_NOT_READY;
    }

    status = hal_spi->bus_init(RTD_SPI2_BUS, &spi_config);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

    status = hal_spi->device_add(RTD_SPI2_BUS, &spi_config, &spi_device);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

    status = drdy_init();
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

#ifdef TEMPER_PAN_CONTROL_C1
    /* C1 on the CR-1 board: no automatic fault cycle (zapote C37). Attach,
     * program the C1 window (it acts on conversions only), switch VBIAS on with
     * conversions off and 07h cleared, and let c1_tick time the manual cycle.
     * The MCP3202 rail ADC joins the bus with its own CS and mode; a failure
     * there leaves the rail unknown (fallback 3.300 V), not the RTD down. */
    if (hal_timer == NULL) {
        s_bootstrap_failed = true;
        return HAL_ERROR_NOT_READY;
    }
    status = max31865_attach(&s_max31865, spi_device);
    if (status == HAL_OK) {
        status = max31865_set_thresholds(&s_max31865, MAX31865_C1_LOW_THRESHOLD_WORD,
                                         MAX31865_C1_HIGH_THRESHOLD_WORD);
    }
    if (status == HAL_OK) {
        status = max31865_bias_on_clear(&s_max31865);
    }
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }
    (void)rail_adc_board_attach(RTD_SPI2_BUS, &spi_config);
    rtd_convert_default_params(&s_c1_conv);
    s_c1_conv.loading_correction = (RTD_FRONT_END_CR1 != 0);
    s_c1_phase = RTD_C1_PHASE_BIAS;
    s_c1_phase_t0_us = HAL_TIME_US();
    s_c1_step2_us = 0u;
    s_c1_phase_ticks = 0u;
    s_c1_power_up = true;
    s_c1_verify = RTD_C1_VERIFY_NONE;
    s_c1_cycles = 0u;
    s_c1_cycle_status = 0u;
    s_c1_first_drdy = false;
    s_c1_have_sample = false;
    s_c1_same_code = 0u;
    s_c1_last_flag = false;
    s_c1_sample = (rtd_sample_t){0};
#else
    status = max31865_initialize(&s_max31865, spi_device);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }
#endif

    s_ready = true;
    return HAL_OK;
}

#ifdef TEMPER_PAN_CONTROL_C1
static void c1_fail_open(void)
{
    s_ready = false;
    state_machine_report_rtd_device_fault(false, true, NULL);
}

static void c1_enter(rtd_c1_phase_t phase)
{
    s_c1_phase = phase;
    s_c1_phase_t0_us = HAL_TIME_US();
    s_c1_phase_ticks = 0u;
}

static bool c1_waited(uint64_t from_us, uint32_t wait_us)
{
    const uint64_t now = HAL_TIME_US();
    return now >= from_us && now - from_us >= wait_us;
}

/* A phase that never completes (no clock, a chip stuck in its cycle) must not
 * leave the RTD unmonitored: fail open after its wait plus the timeout. */
static bool c1_phase_timed_out(uint32_t wait_us)
{
    s_c1_phase_ticks = s_c1_phase_ticks < UINT8_MAX ? (uint8_t)(s_c1_phase_ticks + 1u) : UINT8_MAX;
    return s_c1_phase_ticks > (uint8_t)(wait_us / 10000u + RTD_C1_FAULT_CYCLE_TIMEOUT_TICKS);
}

static void c1_report_status(uint8_t status)
{
    const uint8_t short_bits = MAX31865_FAULT_LOW_THRESHOLD | MAX31865_FAULT_REFIN_LOW |
                               MAX31865_FAULT_RTDIN_LOW;
    state_machine_report_rtd_device_fault((status & short_bits) != 0u,
                                          (status & (uint8_t)~short_bits) != 0u, NULL);
}

/* The manual fault-detection cycle (power-up or reset verification). */
static void c1_fault_cycle_tick(void)
{
    switch (s_c1_phase) {
    case RTD_C1_PHASE_BIAS:
        if (!c1_waited(s_c1_phase_t0_us, RTD_C1_FAULT_CYCLE_STEP_US)) {
            if (c1_phase_timed_out(RTD_C1_FAULT_CYCLE_STEP_US)) {
                c1_fail_open();
            }
            return;
        }
        if (max31865_manual_fault_step1(&s_max31865) != HAL_OK) {
            c1_fail_open();   /* step 2 without step 1 would run the automatic cycle */
            return;
        }
        c1_enter(RTD_C1_PHASE_STEP1);
        return;
    case RTD_C1_PHASE_STEP1:
        if (!c1_waited(s_c1_phase_t0_us, RTD_C1_FAULT_CYCLE_STEP_US)) {
            if (c1_phase_timed_out(RTD_C1_FAULT_CYCLE_STEP_US)) {
                c1_fail_open();
            }
            return;
        }
        if (max31865_manual_fault_step2(&s_max31865) != HAL_OK) {
            c1_fail_open();
            return;
        }
        c1_enter(RTD_C1_PHASE_STEP2);
        s_c1_step2_us = s_c1_phase_t0_us;
        return;
    case RTD_C1_PHASE_STEP2: {
        bool busy = true;
        if (max31865_fault_cycle_busy(&s_max31865, &busy) != HAL_OK) {
            c1_fail_open();
            return;
        }
        if (busy) {
            if (c1_phase_timed_out(0u)) {
                c1_fail_open();
            }
            return;
        }
        uint8_t status = 0u;
        if (max31865_read_fault_status(&s_max31865, &status) != HAL_OK) {
            c1_fail_open();
            return;
        }
        s_c1_cycles++;
        s_c1_cycle_status = status;
        if (status != 0u) {
            c1_report_status(status);
            if (s_c1_power_up) {
                /* A power-up fault blocks the sensor: report and stay down. */
                s_ready = false;
                return;
            }
            /* Reset verification: the input is still faulty. Keep converting so
             * the readings stay live; the latch has absorbed the report. */
            s_c1_verify = RTD_C1_VERIFY_NONE;
        } else if (!s_c1_power_up) {
            s_c1_verify = RTD_C1_VERIFY_CYCLE_CLEAN;
        }
        c1_enter(RTD_C1_PHASE_RESTART);
        return;
    }
    case RTD_C1_PHASE_RESTART:
        if (!c1_waited(s_c1_step2_us, RTD_C1_FAULT_CYCLE_RESTART_US + RTD_C1_FAULT_CYCLE_CHECK_US)) {
            if (c1_phase_timed_out(RTD_C1_FAULT_CYCLE_RESTART_US)) {
                c1_fail_open();
            }
            return;
        }
        /* D-DRDY: read the RTD registers once so DRDY is high when the
         * conversions start; a level left low by a conversion from before the
         * cycle must not pass for the first new one (the expander poll sees
         * levels, not edges). */
        {
            uint8_t msb = 0u;
            uint8_t lsb = 0u;
            if (max31865_read_rtd(&s_max31865, &msb, &lsb) != HAL_OK) {
                c1_fail_open();
                return;
            }
        }
        if (max31865_start_conversions(&s_max31865) != HAL_OK) {
            c1_fail_open();
            return;
        }
        c1_enter(RTD_C1_PHASE_CONVERTING);
        s_c1_power_up = false;
        s_c1_first_drdy = true;
        s_drdy_wait_ticks = 0u;
        s_drdy_complete = false;
        return;
    case RTD_C1_PHASE_CONVERTING:
    default:
        return;
    }
}

static void c1_tick(void)
{
    if (s_c1_phase != RTD_C1_PHASE_CONVERTING) {
        c1_fault_cycle_tick();
        return;
    }

    if (s_c1_verify == RTD_C1_VERIFY_REQUESTED) {
        /* D-FCYC reset verification. VBIAS has been on throughout, so step 1
         * follows the clear at once; 0x82 stops conversions and clears 07h. */
        s_c1_verify = RTD_C1_VERIFY_RUNNING;
        if (max31865_bias_on_clear(&s_max31865) != HAL_OK ||
            max31865_manual_fault_step1(&s_max31865) != HAL_OK) {
            c1_fail_open();
            return;
        }
        c1_enter(RTD_C1_PHASE_STEP1);
        return;
    }

    if (!s_drdy_complete) {
        s_drdy_wait_ticks++;
        if (s_drdy_wait_ticks >= (s_c1_first_drdy ? RTD_C1_FIRST_DRDY_CONTROL_TICKS
                                                  : RTD_C1_STALE_CONTROL_TICKS)) {
            c1_fail_open();
        }
        return;
    }
    s_drdy_complete = false;
    s_drdy_wait_ticks = 0u;
    s_c1_first_drdy = false;

    uint8_t msb = 0u;
    uint8_t lsb = 0u;
    rtd_sample_t smp = s_c1_sample;
    smp.spi_ok = max31865_read_rtd(&s_max31865, &msb, &lsb) == HAL_OK;
    if (!smp.spi_ok) {
        s_c1_sample.spi_ok = false;
        c1_fail_open();
        return;
    }
    bool fault_flag = false;
    const uint16_t prev_code = smp.code;
    smp.code = rtd_convert_split(msb, lsb, &fault_flag);
    if (s_c1_have_sample && smp.code == prev_code) {
        if (s_c1_same_code < UINT16_MAX) {
            s_c1_same_code++;
        }
    } else {
        s_c1_same_code = 0u;
    }
    smp.r_ohm = rtd_convert_code_to_ohm(&s_c1_conv, smp.code);
    smp.t_c = rtd_convert_code_to_c(&s_c1_conv, smp.code);
    smp.fault_status = 0u;
    if (fault_flag) {
        uint8_t status = 0u;
        if (max31865_read_fault_status(&s_max31865, &status) != HAL_OK) {
            smp.spi_ok = false;
            s_c1_sample = smp;
            c1_fail_open();
            return;
        }
        smp.fault_status = status;
        if (status != 0u) {
            c1_report_status(status);
        }
    }
    smp.seq++;
    s_c1_sample = smp;
    s_c1_have_sample = true;
    s_c1_last_flag = fault_flag;
    if (fault_flag) {
        s_c1_verify = RTD_C1_VERIFY_NONE;
    } else if (s_c1_verify == RTD_C1_VERIFY_CYCLE_CLEAN) {
        s_c1_verify = RTD_C1_VERIFY_CLEAN;
    }
    if ((uint32_t)s_c1_same_code + 1u >= RTD_C1_FROZEN_CONVERSIONS) {
        /* The converter answers DRDY with the same word: a frozen reading. */
        s_ready = false;
        state_machine_report_rtd_frozen();
    }
}

bool rtd_service_latest_sample(rtd_sample_t *out)
{
    if (out == NULL || !s_c1_have_sample) {
        return false;
    }
    *out = s_c1_sample;
    return true;
}

bool rtd_service_fault_status_clean(void)
{
    if (!s_ready || !s_c1_have_sample) {
        return false;
    }
    switch (s_c1_verify) {
    case RTD_C1_VERIFY_CLEAN:
        if (s_c1_last_flag) {
            s_c1_verify = RTD_C1_VERIFY_REQUESTED;
            return false;
        }
        s_c1_verify = RTD_C1_VERIFY_NONE;   /* consumed by the reset it allows */
        return true;
    case RTD_C1_VERIFY_NONE:
        s_c1_verify = RTD_C1_VERIFY_REQUESTED;
        return false;
    default:
        return false;   /* requested or running */
    }
}

uint32_t rtd_service_fault_cycles(void)
{
    return s_c1_cycles;
}

uint8_t rtd_service_last_fault_cycle_status(void)
{
    return s_c1_cycle_status;
}
#else
bool rtd_service_latest_sample(rtd_sample_t *out)
{
    (void)out;
    return false;
}

bool rtd_service_fault_status_clean(void)
{
    return true;   /* legacy: the reset policy reads the resistance only */
}

uint32_t rtd_service_fault_cycles(void)
{
    return 0u;
}

uint8_t rtd_service_last_fault_cycle_status(void)
{
    return 0u;
}
#endif

void rtd_service_control_tick(void)
{
    if (s_bootstrap_failed) {
        /* Bootstrap runs before the control task. Report the failure here so
         * only the control task changes state-machine context. */
        report_bootstrap_failure_once();
        return;
    }
    if (s_ready && s_drdy_source == RTD_DRDY_EXPANDER) {
        poll_expander_drdy();
    }

#ifdef TEMPER_PAN_CONTROL_C1
    if (s_ready) {
        c1_tick();
    }
    /* The MCP3202 rail reading shares the bus: taken here, after the MAX31865
     * work of this tick, in the same task (rail_adc.h, D-RAIL). */
    rail_adc_board_service();
    return;
#endif

    if (!s_ready || !s_drdy_complete) {
        if (s_ready) {
            s_drdy_wait_ticks++;
            if (s_drdy_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
                /* A silent MAX31865 or broken DRDY path must not leave the
                 * RTD interlock unmonitored indefinitely. */
                s_ready = false;
                state_machine_report_rtd_device_fault(false, true, NULL);
            }
        }
        return;
    }

    s_drdy_complete = false;
    s_drdy_wait_ticks = 0u;
    if (max31865_service_fault_cycle(&s_max31865,
                                     state_machine_report_rtd_device_fault,
                                     NULL) != HAL_OK) {
        /* The driver has already reported the terminal open fault. Do not
         * try to resume a monitor whose next cycle could not be armed. */
        s_ready = false;
    }
}

bool rtd_service_is_ready(void)
{
    return s_ready;
}
