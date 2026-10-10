/**
 * @file rtd_service.c
 * @brief Board-owned SPI2/MAX31865 bootstrap and DRDY handoff.
 *
 * Integrated controller, layout L2: SPI2 on RTD_SCK 11 / RTD_SDI (MOSI) 13 / RTD_SDO (MISO) 12,
 * CS 10, mode 3 so the MCP3202 can share the bus (DECISIONS C20). DRDY moved from GPIO14 to the
 * TCA9555 P07 (C23), so it is no longer an interrupt: the control task samples its level from the
 * expander snapshot every tick and this service turns a high-to-low transition into the same
 * single completion handoff the ISR used to make. A DRDY low pulse shorter than one control tick
 * is missed, which ends in the fail-silent timeout below (fail-closed), never in a stale reading.
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
static bool s_drdy_complete;
static rtd_drdy_level_fn s_drdy_level;
static void *s_drdy_ctx;
static bool s_drdy_prev_low;
static bool s_ready;
static bool s_bootstrap_failed;
static bool s_bootstrap_failure_reported;
static uint8_t s_drdy_wait_ticks;

void rtd_service_set_drdy_source(rtd_drdy_level_fn level, void *context)
{
    s_drdy_level = level;
    s_drdy_ctx = context;
}

/* One sample per control tick. Only a fresh high-to-low transition completes a cycle; an
 * unavailable (stale) sample is "no edge" and leaves the timeout running. */
static void sample_drdy(void)
{
    bool low = false;
    if (s_drdy_level == NULL || !s_drdy_level(s_drdy_ctx, &low)) {
        return;
    }
    if (low && !s_drdy_prev_low) {
        s_drdy_complete = true;
    }
    s_drdy_prev_low = low;
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
    s_drdy_complete = false;
    s_drdy_prev_low = false;
    s_ready = false;
    s_bootstrap_failed = false;
    s_bootstrap_failure_reported = false;
    s_drdy_wait_ticks = 0u;

    if (hal_spi == NULL || s_drdy_level == NULL) {
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

    /* MAX31865 DRDY is active-low; only its falling edge marks a completed
     * conversion/fault-detection cycle. It is sampled through the expander
     * (rtd_service_set_drdy_source) in rtd_service_control_tick(). */

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

    if (s_ready) {
        sample_drdy();
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
