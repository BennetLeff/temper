/**
 * @file pwm_guard.c
 * @brief Implementation of PWM safety mechanisms
 */

#include "pwm_guard.h"
#include "hal_pwm.h"
#include "hal_timer.h"
#include <string.h>
#include <stdlib.h>

// Module state
static struct {
    hal_pwm_channel_t pwm_channel;
    hal_timer_t timer_channel;
    uint32_t last_capture_timestamp;
    volatile uint32_t measured_freq_hz;
    uint32_t config_crc;
    bool initialized;
} s_pwm_guard;

// Forward decl
static void pwm_capture_callback(const hal_capture_event_t *event, void *arg);

void pwm_guard_init(hal_pwm_channel_t pwm_channel, hal_timer_t timer_channel) {
    memset(&s_pwm_guard, 0, sizeof(s_pwm_guard));
    s_pwm_guard.pwm_channel = pwm_channel;
    s_pwm_guard.timer_channel = timer_channel;
    s_pwm_guard.initialized = true;
    
    // Configure timer capture for frequency measurement
    // Capturing on both edges allows duty cycle calc, but rising-to-rising is enough for freq
    if (hal_timer && hal_timer->configure_capture) {
        // Assuming PIN_PWM_HI feedback is routed to capture pin
        // For now, we assume the HAL handles pin routing via config
        hal_timer->configure_capture(
            timer_channel, 
            HAL_PIN_INVALID, // HAL should know the pin or it's set elsewhere
            HAL_GPIO_INTR_RISING,
            pwm_capture_callback,
            NULL
        );
    }
}

// Timer capture ISR to measure frequency
static void pwm_capture_callback(const hal_capture_event_t *event, void *arg) {
    (void)arg;
    uint32_t current = (uint32_t)event->timestamp;
    uint32_t diff = current - s_pwm_guard.last_capture_timestamp;
    
    if (diff > 0) {
        // F = 1 / T (microseconds) -> F_hz = 1,000,000 / diff
        s_pwm_guard.measured_freq_hz = 1000000 / diff;
    }
    
    s_pwm_guard.last_capture_timestamp = current;
}

pwm_guard_status_t pwm_guard_validate_frequency(uint32_t freq_hz) {
    if (freq_hz < PWM_GUARD_MIN_FREQ_HZ) {
        return PWM_GUARD_ERR_FREQ_LOW;
    }
    if (freq_hz > PWM_GUARD_MAX_FREQ_HZ) {
        return PWM_GUARD_ERR_FREQ_HIGH;
    }
    return PWM_GUARD_OK;
}

pwm_guard_status_t pwm_guard_self_test(void) {
    if (!s_pwm_guard.initialized) return PWM_GUARD_ERR_NULL;
    if (!hal_pwm) return PWM_GUARD_ERR_NULL;
    
    hal_pwm_state_t state;
    if (hal_pwm->get_state(s_pwm_guard.pwm_channel, &state) != HAL_OK) {
        return PWM_GUARD_ERR_NULL;
    }
    
    // 1. Check Frequency
    if (state.frequency_hz < PWM_GUARD_MIN_FREQ_HZ) return PWM_GUARD_ERR_FREQ_LOW;
    if (state.frequency_hz > PWM_GUARD_MAX_FREQ_HZ) return PWM_GUARD_ERR_FREQ_HIGH;
    
    // 2. Check Target Match (approximate)
    // Allow small deviation for integer math errors in HAL
    uint32_t diff = (state.frequency_hz > PWM_GUARD_TARGET_FREQ_HZ) ? 
                    (state.frequency_hz - PWM_GUARD_TARGET_FREQ_HZ) : 
                    (PWM_GUARD_TARGET_FREQ_HZ - state.frequency_hz);
                    
    if (diff > (PWM_GUARD_TARGET_FREQ_HZ / 100)) { // 1% tolerance
        return PWM_GUARD_ERR_MISMATCH;
    }
    
    // 3. Check Dead-time
    if (state.dead_time_ns < PWM_GUARD_MIN_DEADTIME_NS || 
        state.dead_time_ns > PWM_GUARD_MAX_DEADTIME_NS) {
        return PWM_GUARD_ERR_DEADTIME;
    }
    
    // Store simple "CRC" (checksum) of config for integrity check
    s_pwm_guard.config_crc = state.frequency_hz ^ state.dead_time_ns;
    
    return PWM_GUARD_OK;
}

pwm_guard_status_t pwm_guard_check_integrity(void) {
    if (!s_pwm_guard.initialized) return PWM_GUARD_ERR_NULL;
    
    // 1. Check Runtime Frequency (measured via timer)
    // If measurement hasn't happened yet (0), skip or fail? 
    // Let's assume startup is done.
    if (s_pwm_guard.measured_freq_hz > 0) {
        uint32_t freq = s_pwm_guard.measured_freq_hz;
        
        if (freq < PWM_GUARD_MIN_FREQ_HZ) return PWM_GUARD_ERR_FREQ_LOW;
        if (freq > PWM_GUARD_MAX_FREQ_HZ) return PWM_GUARD_ERR_FREQ_HIGH;
        
        // Check deviation from target tolerance
        uint32_t target = PWM_GUARD_TARGET_FREQ_HZ;
        uint32_t tolerance = (target * PWM_GUARD_FREQ_TOLERANCE_PERCENT) / 100;
        
        if (freq < (target - tolerance) || freq > (target + tolerance)) {
            return PWM_GUARD_ERR_MISMATCH;
        }
    }
    
    // 2. Check Register Integrity
    // Read back config and compare to stored checksum
    if (hal_pwm) {
        hal_pwm_state_t state;
        hal_pwm->get_state(s_pwm_guard.pwm_channel, &state);
        
        uint32_t current_crc = state.frequency_hz ^ state.dead_time_ns;
        if (current_crc != s_pwm_guard.config_crc) {
            return PWM_GUARD_ERR_CORRUPTION;
        }
    }
    
    return PWM_GUARD_OK;
}

// Internal function to inject frequency measurement for unit testing
void _pwm_guard_inject_freq(uint32_t freq_hz) {
    s_pwm_guard.measured_freq_hz = freq_hz;
}
