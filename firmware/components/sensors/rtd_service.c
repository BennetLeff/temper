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
#include <math.h>

/* SPI2 maps to HAL bus zero. MAX31865 supports mode 1 and a 500 kHz clock is
 * comfortably below its 5 MHz maximum while board bring-up remains pending. */
#define RTD_SPI2_BUS       0
#define RTD_SPI_CLOCK_HZ   500000u
#define RTD_SAMPLE_READY   0x80000000u
#define RTD_SAMPLE_COUNT   0x7fffffffu

static max31865_device_t s_max31865;
static uint32_t s_drdy_complete;
static bool s_ready;
static bool s_bootstrap_failed;
static bool s_bootstrap_failure_reported;
static uint8_t s_drdy_wait_ticks;
static uint8_t s_fault_cycle_wait_ticks;
static bool s_fault_cycle_started;
static bool s_conversion_armed;
static bool s_has_sample;
static float s_rtd_resistance_ohm;
/* Single writer: the control task. The sequence encloses both state and
 * timestamp, preventing a monitor from pairing a generation with another
 * conversion's time. */
static uint32_t s_sample_state;
static uint32_t s_sample_time_ms;
static uint32_t s_sample_seq;

static void publish_sample_state(uint32_t state, uint32_t time_ms)
{
    (void)__atomic_add_fetch(&s_sample_seq, 1u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&s_sample_time_ms, time_ms, __ATOMIC_SEQ_CST);
    __atomic_store_n(&s_sample_state, state, __ATOMIC_SEQ_CST);
    (void)__atomic_add_fetch(&s_sample_seq, 1u, __ATOMIC_SEQ_CST);
}

static void invalidate_sample(void)
{
    uint32_t state = __atomic_load_n(&s_sample_state, __ATOMIC_RELAXED);
    s_ready = false;
    publish_sample_state(state & RTD_SAMPLE_COUNT, 0u);
}

static void rtd_drdy_isr(hal_pin_t pin, void *context)
{
    (void)pin;
    (void)context;

    /* No SPI, logging, allocation, or state-machine mutation in interrupt
     * context. The control task atomically consumes this single-bit handoff. */
    __atomic_store_n(&s_drdy_complete, 1u, __ATOMIC_RELEASE);
}

static void report_bootstrap_failure_once(void)
{
    if (!s_bootstrap_failure_reported) {
        s_bootstrap_failure_reported = true;
        state_machine_report_rtd_device_fault(false, true, NULL);
    }
}

static void report_conversion_fault(bool short_fault, bool open_fault,
                                    void *context)
{
    bool *faulted = context;
    if (short_fault || open_fault) {
        *faulted = true;
        invalidate_sample();
    }
    state_machine_report_rtd_device_fault(short_fault, open_fault, NULL);
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
    __atomic_store_n(&s_drdy_complete, 0u, __ATOMIC_RELEASE);
    s_ready = false;
    s_bootstrap_failed = false;
    s_bootstrap_failure_reported = false;
    s_drdy_wait_ticks = 0u;
    s_fault_cycle_wait_ticks = 0u;
    s_fault_cycle_started = false;
    s_conversion_armed = false;
    s_has_sample = false;
    s_rtd_resistance_ohm = RTD_OPEN_FAULT_OHM + 1.0f;
    __atomic_store_n(&s_sample_state, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&s_sample_time_ms, 0u, __ATOMIC_RELAXED);
    __atomic_store_n(&s_sample_seq, 0u, __ATOMIC_RELEASE);

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
            invalidate_sample();
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
            invalidate_sample();
            state_machine_report_rtd_device_fault(false, true, NULL);
            return;
        }
        __atomic_store_n(&s_drdy_complete, 0u, __ATOMIC_RELEASE);
        s_drdy_wait_ticks = 0u;
        s_conversion_armed = true;
        return;
    }

    if (!s_ready ||
        !__atomic_exchange_n(&s_drdy_complete, 0u, __ATOMIC_ACQ_REL)) {
        if (s_ready) {
            s_drdy_wait_ticks++;
            if (s_drdy_wait_ticks >= RTD_DRDY_TIMEOUT_CONTROL_TICKS) {
                /* A silent MAX31865 or broken DRDY path must not leave the
                 * RTD interlock unmonitored indefinitely. */
                invalidate_sample();
                state_machine_report_rtd_device_fault(false, true, NULL);
            }
        }
        return;
    }

    s_drdy_wait_ticks = 0u;
    {
        uint16_t rtd_code = 0u;
        bool faulted = false;
        if (max31865_service_fault_cycle(&s_max31865, &rtd_code,
                                         report_conversion_fault,
                                         &faulted) != HAL_OK || faulted) {
            /* The driver has already reported the device or transport fault.
             * Do not publish a generation from a failed conversion read. */
            invalidate_sample();
        } else {
            /* Publish only the fresh conversion that was read before status.
             * MAX31865's 15-bit code is code = floor(32768*R/RREF). */
            if (hal_timer == NULL || hal_timer->get_time_ms == NULL) {
                invalidate_sample();
                state_machine_report_rtd_device_fault(false, true, NULL);
                return;
            }
            uint32_t generation = __atomic_load_n(&s_sample_state,
                                                   __ATOMIC_RELAXED) &
                                  RTD_SAMPLE_COUNT;
            /* Zero is reserved for "never sampled". The monitor compares
             * changes within a bounded deadline, so wrapping to one does
             * not extend a stale sample's lifetime. */
            generation = generation == RTD_SAMPLE_COUNT ? 1u
                                                        : generation + 1u;
            s_rtd_resistance_ohm = ((float)rtd_code * 430.0f) / 32768.0f;
            s_has_sample = true;
            s_fault_cycle_wait_ticks = 0u;
            publish_sample_state(RTD_SAMPLE_READY | generation,
                                 hal_timer->get_time_ms());
        }
    }
}

bool rtd_service_is_ready(void)
{
    return rtd_service_sample_status().ready;
}

bool rtd_service_has_sample(void)
{
    return s_has_sample;
}

rtd_sample_status_t rtd_service_sample_status(void)
{
    uint32_t before;
    uint32_t after;
    uint32_t state;
    uint32_t sample_time_ms;
    for (;;) {
        before = __atomic_load_n(&s_sample_seq, __ATOMIC_SEQ_CST);
        if (before & 1u) continue;
        state = __atomic_load_n(&s_sample_state, __ATOMIC_SEQ_CST);
        sample_time_ms = __atomic_load_n(&s_sample_time_ms,
                                         __ATOMIC_SEQ_CST);
        after = __atomic_load_n(&s_sample_seq, __ATOMIC_SEQ_CST);
        if (before == after && !(after & 1u)) break;
    }
    bool ready = (state & RTD_SAMPLE_READY) != 0u &&
                 hal_timer != NULL && hal_timer->get_time_ms != NULL;
    return (rtd_sample_status_t){
        .ready = ready,
        .generation = state & RTD_SAMPLE_COUNT,
        .age_ms = ready ? hal_timer->get_time_ms() - sample_time_ms
                        : UINT32_MAX,
    };
}

#ifdef RTD_SERVICE_TESTING
void rtd_service_test_seed_generation(uint32_t generation)
{
    publish_sample_state(RTD_SAMPLE_READY | (generation & RTD_SAMPLE_COUNT),
                         hal_timer != NULL && hal_timer->get_time_ms != NULL
                             ? hal_timer->get_time_ms() : 0u);
}
#endif

float rtd_service_get_resistance(void)
{
    return s_ready && s_has_sample ? s_rtd_resistance_ohm
                                   : RTD_OPEN_FAULT_OHM + 1.0f;
}

/* MAX31865 data sheet, Temperature Conversion: IEC 751 PT100 coefficients.
 * R(T) is monotonic on -200..850 C. Use a fixed-count inverse search to avoid
 * an approximation that silently under-reports high temperatures. */
static float pt100_resistance_at(float temperature_c)
{
    const float a = 3.90830e-3f;
    const float b = -5.77500e-7f;
    const float c = -4.18301e-12f;
    const float t = temperature_c;
    return 100.0f * (1.0f + a * t + b * t * t +
                     (t < 0.0f ? c * (t - 100.0f) * t * t * t : 0.0f));
}

float rtd_pt100_temperature_c(float resistance_ohm)
{
    if (!isfinite(resistance_ohm) ||
        resistance_ohm < pt100_resistance_at(-200.0f) ||
        resistance_ohm > pt100_resistance_at(850.0f)) {
        return NAN;
    }
    float lo = -200.0f;
    float hi = 850.0f;
    for (unsigned int i = 0u; i < 24u; ++i) {
        const float mid = (lo + hi) * 0.5f;
        if (pt100_resistance_at(mid) < resistance_ohm) {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    return (lo + hi) * 0.5f;
}

float rtd_service_pan_temperature_c(void)
{
    const rtd_sample_status_t sample = rtd_service_sample_status();
    if (!sample.ready || sample.age_ms > RTD_MAX_CONTROL_SAMPLE_AGE_MS) {
        return NAN;
    }
    /* Called by the control task, the sole reader of s_rtd_resistance_ohm. */
    const float resistance_ohm = rtd_service_get_resistance();
    if (!isfinite(resistance_ohm) ||
        resistance_ohm <= RTD_SHORT_FAULT_OHM ||
        resistance_ohm >= RTD_OPEN_FAULT_OHM) {
        return NAN;
    }
    return rtd_pt100_temperature_c(resistance_ohm);
}

#if defined(ESP_PLATFORM) && !defined(TEMPER_DIAGNOSTIC_LOCKOUT)
/* The diagnostic image supplies its own fail-closed link hook. In the
 * production image this is the sole pan-temperature implementation. */
float read_pan_temperature(void)
{
    return rtd_service_pan_temperature_c();
}
#endif

/* Production state-machine callers already use this interface name. The
 * weak definition lets host SIL stubs override it while production receives
 * the newest MAX31865 sample and fails closed before the first sample. */
__attribute__((weak)) float read_rtd_resistance(void)
{
    return rtd_service_get_resistance();
}
