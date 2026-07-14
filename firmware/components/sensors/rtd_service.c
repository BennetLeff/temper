/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 */

#include "rtd_service.h"

#include "hal.h"
#include "max31865.h"
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

    s_ready = true;
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
