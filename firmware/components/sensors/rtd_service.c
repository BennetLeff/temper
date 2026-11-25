/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 *
 * Integrated controller, layout L2: SPI2 on RTD_SCK 11 / RTD_SDI (MOSI) 13 / RTD_SDO (MISO) 12,
 * CS 10, mode 3 so the MCP3202 can share the bus (DECISIONS C20). DRDY moved from GPIO14 to the
 * TCA9555 P07 (C23), so it is no longer an interrupt: the control task samples its level from the
 * expander snapshot every tick. The fault-cycle and conversion schedule is in rtd_service.h. A
 * missed or stuck DRDY ends in the fail-silent timeout (fail-closed), never in a stale reading.
 */

#include "rtd_service.h"

#include "hal.h"
#include "max31865.h"
#include "state_machine.h"
#include "controller_pins.h"

/* SPI2 maps to HAL bus zero. MAX31865 supports modes 1 and 3; mode 3 is shared with the MCP3202
 * (C20). A 500 kHz clock is comfortably below its 5 MHz maximum while bring-up remains pending. */
#define RTD_SPI2_BUS       0
#define RTD_SPI_CLOCK_HZ   500000u

static max31865_device_t s_max31865;
static rtd_drdy_level_fn s_drdy_level;
static void *s_drdy_ctx;
static bool s_ready;
static bool s_bootstrap_failed;
static bool s_bootstrap_failure_reported;

typedef enum {
    RTD_PHASE_BIAS = 0,   /* VBIAS on, conversions off: wait STEP             */
    RTD_PHASE_STEP1,      /* manual step 1 written: wait STEP                 */
    RTD_PHASE_STEP2,      /* manual step 2 written: poll D3:D2, read 07h      */
    RTD_PHASE_RESTART,    /* 07h clean: wait RESTART from step 2              */
    RTD_PHASE_CONVERTING,
} rtd_phase_t;
static rtd_phase_t s_phase;
static uint8_t s_wait_ticks;          /* ticks waiting for the current cycle / conversion */
static hal_time_us_t s_phase_t0_us;   /* start of the running manual-cycle wait */
static bool s_drdy_armed;             /* DRDY seen high (released) since the last data read */

/* Latest RTD data word, read on each conversion (rtd_service_latest_word). */
static uint16_t s_rtd_word;
static bool s_rtd_word_valid;
static uint8_t s_rtd_word_age_ticks;

void rtd_service_set_drdy_source(rtd_drdy_level_fn level, void *context)
{
    s_drdy_level = level;
    s_drdy_ctx = context;
}

static bool drdy_sample(bool refresh, bool *low)
{
    return s_drdy_level != NULL && s_drdy_level(s_drdy_ctx, refresh, low);
}

static void report_bootstrap_failure_once(void)
{
    if (!s_bootstrap_failure_reported) {
        s_bootstrap_failure_reported = true;
        state_machine_report_rtd_device_fault(false, true, NULL);
    }
}

/* Terminal: a fault went to the state machine (which has latched the power cut). */
static void fail_closed(bool report_open)
{
    s_ready = false;
    if (report_open) {
        state_machine_report_rtd_device_fault(false, true, NULL);
    }
}

hal_status_t rtd_service_bootstrap(void)
{
    const hal_spi_config_t spi_config = {
        .clock_hz = RTD_SPI_CLOCK_HZ,
        .mode = CTRL_RTD_SPI_MODE,
        .pin_mosi = CTRL_GPIO_RTD_SDI,
        .pin_miso = CTRL_GPIO_RTD_SDO,
        .pin_sclk = CTRL_GPIO_RTD_SCK,
        .pin_cs = CTRL_GPIO_RTD_CS_N,
        .cs_active_high = false,
    };
    hal_spi_device_t spi_device = NULL;
    hal_status_t status;

    s_max31865.spi_device = NULL;
    s_ready = false;
    s_bootstrap_failed = false;
    s_bootstrap_failure_reported = false;
    s_phase = RTD_PHASE_BIAS;
    s_wait_ticks = 0u;
    s_phase_t0_us = 0u;
    s_drdy_armed = false;
    s_rtd_word = 0u;
    s_rtd_word_valid = false;
    s_rtd_word_age_ticks = 0u;

    if (hal_spi == NULL || hal_timer == NULL || s_drdy_level == NULL) {
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

    /* Thresholds, then VBIAS on; the control tick runs the manual fault cycle. */
    status = max31865_initialize(&s_max31865, spi_device);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

    s_phase_t0_us = hal_timer->get_time_us();
    s_ready = true;
    return HAL_OK;
}

/* Read the data word (releases DRDY), then re-sample DRDY: the next low counts as a new
 * conversion only once DRDY has been seen high. A DRDY stuck low therefore yields one
 * conversion and then the fail-silent timeout. */
static bool read_word_and_rearm(uint16_t *word)
{
    bool ok = max31865_read_rtd_word(&s_max31865, word) == HAL_OK;
    bool low = true;
    s_drdy_armed = ok && drdy_sample(true, &low) && !low;
    return ok;
}

static bool waited(uint32_t wait_us)
{
    const hal_time_us_t now = hal_timer->get_time_us();
    return now >= s_phase_t0_us && now - s_phase_t0_us >= wait_us;
}

static void enter(rtd_phase_t phase)
{
    s_phase = phase;
    s_wait_ticks = 0u;
}

/* A phase that never completes (stopped clock, chip stuck in its cycle) must not leave the RTD
 * unmonitored. */
static void phase_wait(void)
{
    if (++s_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
        fail_closed(true);
    }
}

/* Release a stale DRDY, then start conversions. */
static void start_converting(void)
{
    uint16_t discard = 0u;
    (void)read_word_and_rearm(&discard); /* no conversion yet */
    if (max31865_start_conversions(&s_max31865) != HAL_OK) {
        fail_closed(true);
        return;
    }
    enter(RTD_PHASE_CONVERTING);
}

static void tick_fault_cycle(void)
{
    bool done = false;
    bool reported = false;

    switch (s_phase) {
    case RTD_PHASE_BIAS:
    case RTD_PHASE_STEP1:
        if (!waited(RTD_FAULT_CYCLE_STEP_US)) {
            phase_wait();
            return;
        }
        if ((s_phase == RTD_PHASE_BIAS ? max31865_manual_fault_step1(&s_max31865)
                                       : max31865_manual_fault_step2(&s_max31865)) != HAL_OK) {
            fail_closed(true); /* step 2 without step 1 would be the automatic cycle */
            return;
        }
        s_phase_t0_us = hal_timer->get_time_us();
        enter(s_phase == RTD_PHASE_BIAS ? RTD_PHASE_STEP1 : RTD_PHASE_STEP2);
        return;
    case RTD_PHASE_STEP2:
        if (max31865_fault_cycle_done(&s_max31865, &done) != HAL_OK) {
            fail_closed(true);
            return;
        }
        if (!done) {
            phase_wait();
            return;
        }
        if (max31865_check_fault_status(&s_max31865, state_machine_report_rtd_device_fault, NULL,
                                        &reported) != HAL_OK || reported) {
            fail_closed(false); /* the driver has reported */
            return;
        }
        enter(RTD_PHASE_RESTART);
        /* fall through */
    case RTD_PHASE_RESTART:
        if (!waited(RTD_FAULT_CYCLE_RESTART_US)) { /* s_phase_t0_us is still step 2's */
            phase_wait();
            return;
        }
        start_converting();
        return;
    case RTD_PHASE_CONVERTING:
    default:
        return;
    }
}

static void tick_converting(void)
{
    bool low = false;
    bool sampled = drdy_sample(false, &low);
    bool completed = false;

    if (sampled && !low) {
        s_drdy_armed = true;
    } else if (sampled && low && s_drdy_armed) {
        uint16_t word = 0u;
        completed = true;
        s_rtd_word_valid = read_word_and_rearm(&word);
        s_rtd_word = word;
        s_rtd_word_age_ticks = 0u;
        s_wait_ticks = 0u;
        if (s_rtd_word_valid && (word & MAX31865_RTD_WORD_FAULT) != 0u) {
            /* Threshold (or other) fault detected during this conversion. */
            (void)max31865_report_conversion_fault(&s_max31865,
                                                   state_machine_report_rtd_device_fault,
                                                   NULL);
            fail_closed(false);
            return;
        }
    }

    if (!completed && ++s_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
        /* A silent MAX31865 or broken DRDY path must not leave the RTD interlock unmonitored. */
        fail_closed(true);
        return;
    }
}

void rtd_service_control_tick(void)
{
    if (s_rtd_word_age_ticks < UINT8_MAX) {
        s_rtd_word_age_ticks++;
    }

    if (s_bootstrap_failed) {
        /* Bootstrap runs before the control task. Report the failure here so
         * only the control task changes state-machine context. */
        report_bootstrap_failure_once();
        return;
    }
    if (!s_ready) {
        return;
    }
    if (s_phase == RTD_PHASE_CONVERTING) {
        tick_converting();
    } else {
        tick_fault_cycle();
    }
}

bool rtd_service_startup(void (*step)(void *context), void *context)
{
    for (uint32_t i = 0u; i < RTD_STARTUP_MAX_TICKS; i++) {
        if (step != NULL) {
            step(context);
        }
        rtd_service_control_tick();
        if (rtd_service_latest_word(NULL, NULL)) {
            return true;
        }
        if (!s_ready) {
            return false; /* reported by the tick */
        }
    }
    fail_closed(true);
    return false;
}

bool rtd_service_is_ready(void)
{
    return s_ready;
}

bool rtd_service_converting(void)
{
    return s_ready && s_phase == RTD_PHASE_CONVERTING;
}

bool rtd_service_latest_word(uint16_t *rtd_word, uint8_t *age_ticks)
{
    if (!s_ready || !s_rtd_word_valid ||
        s_rtd_word_age_ticks > RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
        return false;
    }
    if (rtd_word != NULL) {
        *rtd_word = s_rtd_word;
    }
    if (age_ticks != NULL) {
        *age_ticks = s_rtd_word_age_ticks;
    }
    return true;
}
