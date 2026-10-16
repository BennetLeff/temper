/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 */

#include "rtd_service.h"

#include "hal.h"
#include "max31865.h"
#include "state_machine.h"
#include "temper_pins.h"

#ifdef TEMPER_PAN_CONTROL_C1
#include "config.h"
#include "rtd_convert.h"

/* CR-1 sense-line filter fitted on the controller (pcb/CHANGE-REQUEST.md):
 * enables the CR-7 loading correction. The controller as captured has no
 * CR-1, so the default is 0. */
#ifndef RTD_FRONT_END_CR1
#define RTD_FRONT_END_CR1 0
#endif

typedef enum {
    RTD_C1_PHASE_FAULT_CYCLE = 0,
    RTD_C1_PHASE_CONVERTING = 1,
} rtd_c1_phase_t;

static rtd_c1_phase_t s_c1_phase;
static rtd_convert_params_t s_c1_conv;
static rtd_sample_t s_c1_sample;
static bool s_c1_have_sample;
static uint16_t s_c1_same_code;
static bool s_c1_last_flag;        /* fault flag of the latest conversion */
static bool s_c1_clear_requested;  /* D-OPEN: clear 07h on the next tick */
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

    status = HAL_GPIO_INIT(PIN_RTD_DRDY, HAL_GPIO_MODE_INPUT);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

    /* MAX31865 DRDY is active-low; only its falling edge marks a completed
     * conversion/fault-detection cycle. */
    status = hal_gpio->set_interrupt(PIN_RTD_DRDY, HAL_GPIO_INTR_FALLING,
                                     rtd_drdy_isr, NULL);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

    status = max31865_initialize(&s_max31865, spi_device);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }

#ifdef TEMPER_PAN_CONTROL_C1
    /* C1 Pt100 window (CR-7). max31865_initialize() has already started the
     * one power-up fault-detection cycle; the thresholds only act on
     * conversions, which start after that cycle completes. */
    status = max31865_set_thresholds(&s_max31865, MAX31865_C1_LOW_THRESHOLD_WORD,
                                     MAX31865_C1_HIGH_THRESHOLD_WORD);
    if (status != HAL_OK) {
        s_bootstrap_failed = true;
        return status;
    }
    rtd_convert_default_params(&s_c1_conv);
    s_c1_conv.loading_correction = (RTD_FRONT_END_CR1 != 0);
    s_c1_phase = RTD_C1_PHASE_FAULT_CYCLE;
    s_c1_have_sample = false;
    s_c1_same_code = 0u;
    s_c1_last_flag = false;
    s_c1_clear_requested = false;
    s_c1_sample = (rtd_sample_t){0};
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

static void c1_tick(void)
{
    if (s_c1_phase == RTD_C1_PHASE_FAULT_CYCLE) {
        bool busy = true;
        if (max31865_fault_cycle_busy(&s_max31865, &busy) != HAL_OK) {
            c1_fail_open();
            return;
        }
        if (busy) {
            s_drdy_wait_ticks++;
            if (s_drdy_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
                c1_fail_open();
            }
            return;
        }
        uint8_t status = 0u;
        if (max31865_read_fault_status(&s_max31865, &status) != HAL_OK) {
            c1_fail_open();
            return;
        }
        if (status != 0u) {
            /* A power-up fault blocks the sensor: report and stay down. */
            s_ready = false;
            state_machine_report_rtd_device_fault((status & MAX31865_FAULT_LOW_THRESHOLD) != 0u,
                                                  (status & (uint8_t)~MAX31865_FAULT_LOW_THRESHOLD) != 0u,
                                                  NULL);
            return;
        }
        if (max31865_start_conversions(&s_max31865) != HAL_OK) {
            c1_fail_open();
            return;
        }
        s_c1_phase = RTD_C1_PHASE_CONVERTING;
        s_drdy_wait_ticks = 0u;
        s_drdy_complete = false;
        return;
    }

    if (s_c1_clear_requested) {
        /* D-OPEN: the reset policy asked for a clean 07h. Conversions keep
         * running; the next one reports only its own condition. */
        s_c1_clear_requested = false;
        if (max31865_clear_fault_status(&s_max31865) != HAL_OK) {
            c1_fail_open();
            return;
        }
    }

    if (!s_drdy_complete) {
        s_drdy_wait_ticks++;
        if (s_drdy_wait_ticks >= RTD_C1_STALE_CONTROL_TICKS) {
            c1_fail_open();
        }
        return;
    }
    s_drdy_complete = false;
    s_drdy_wait_ticks = 0u;

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
            state_machine_report_rtd_device_fault((status & MAX31865_FAULT_LOW_THRESHOLD) != 0u,
                                                  (status & (uint8_t)~MAX31865_FAULT_LOW_THRESHOLD) != 0u,
                                                  NULL);
        }
    }
    smp.seq++;
    s_c1_sample = smp;
    s_c1_have_sample = true;
    s_c1_last_flag = fault_flag;
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
    if (s_c1_last_flag) {
        s_c1_clear_requested = true;
        return false;
    }
    return !s_c1_clear_requested;
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
#endif

void rtd_service_control_tick(void)
{
    if (s_bootstrap_failed) {
        /* Bootstrap runs before the control task. Report the failure here so
         * only the control task changes state-machine context. */
        report_bootstrap_failure_once();
        return;
    }

#ifdef TEMPER_PAN_CONTROL_C1
    if (s_ready) {
        c1_tick();
    }
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
