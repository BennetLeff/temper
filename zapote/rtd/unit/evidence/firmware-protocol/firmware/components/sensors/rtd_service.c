/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 */

#include "rtd_service.h"

#include "hal.h"
#include "max31865.h"
#include "config.h"
#include "state_machine.h"
#include "temper_pins.h"

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
static uint8_t s_fault_cycle_wait_ticks;
static bool s_fault_cycle_started;
static bool s_conversion_armed;
static bool s_has_sample;
static float s_rtd_resistance_ohm;

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
    s_fault_cycle_wait_ticks = 0u;
    s_fault_cycle_started = false;
    s_conversion_armed = false;
    s_has_sample = false;
    s_rtd_resistance_ohm = RTD_OPEN_FAULT_OHM + 1.0f;

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

    /* MAX31865 DRDY is active-low; its falling edge marks a completed ADC
     * conversion. The separate automatic fault cycle is timed by the control
     * task because it does not provide conversion DRDY. */
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

    s_ready = true;
    /* initialize() enables BIAS only. It is not a conversion trigger. */
    s_conversion_armed = false;
    return HAL_OK;
}

void rtd_service_control_tick(void)
{
    if (s_bootstrap_failed) {
        /* Bootstrap runs before the control task. Report the failure here so
         * only the control task changes state-machine context. */
        report_bootstrap_failure_once();
        return;
    }

    if (!s_fault_cycle_started) {
        /* Wait for MAX31865's 10 ms maximum BIAS startup before writing 0x84. */
        if (++s_fault_cycle_wait_ticks < RTD_BIAS_STARTUP_CONTROL_TICKS) {
            return;
        }
        if (max31865_start_fault_detection(&s_max31865) != HAL_OK) {
            s_ready = false;
            state_machine_report_rtd_device_fault(false, true, NULL);
            return;
        }
        s_fault_cycle_started = true;
        s_fault_cycle_wait_ticks = 0u;
        return;
    }

    if (!s_conversion_armed) {
        /* 0x84 has no conversion-complete DRDY. One task period exceeds the
         * 600 us automatic-cycle maximum before enabling continuous D6. */
        if (++s_fault_cycle_wait_ticks < RTD_FAULT_CYCLE_SETTLE_CONTROL_TICKS) {
            return;
        }
        if (max31865_start_continuous(&s_max31865) != HAL_OK) {
            s_ready = false;
            state_machine_report_rtd_device_fault(false, true, NULL);
            return;
        }
        s_drdy_complete = false;
        s_drdy_wait_ticks = 0u;
        s_conversion_armed = true;
        return;
    }

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
    {
        uint16_t rtd_code = 0u;
        if (max31865_service_fault_cycle(&s_max31865, &rtd_code,
                                         state_machine_report_rtd_device_fault,
                                         NULL) != HAL_OK) {
        /* The driver has already reported the terminal open fault. Do not
         * resume a monitor after a failed conversion/status transfer. */
            s_ready = false;
        } else {
            /* Publish only the fresh conversion that was read before status.
             * MAX31865's 15-bit code is code = floor(32768*R/RREF). */
            s_rtd_resistance_ohm = ((float)rtd_code * 430.0f) / 32768.0f;
            s_has_sample = true;
            s_fault_cycle_wait_ticks = 0u;
        }
    }
}

bool rtd_service_is_ready(void)
{
    return s_ready && s_has_sample;
}

bool rtd_service_has_sample(void)
{
    return s_has_sample;
}

float rtd_service_get_resistance(void)
{
    return s_has_sample ? s_rtd_resistance_ohm : RTD_OPEN_FAULT_OHM + 1.0f;
}

/* Production state-machine callers already use this interface name. The
 * weak definition lets host SIL stubs override it while production receives
 * the newest MAX31865 sample and fails closed before the first sample. */
__attribute__((weak)) float read_rtd_resistance(void)
{
    return rtd_service_get_resistance();
}
