# Safety component: watchdogs, hardware interlocks, and the guard modules
# (ADC / coil / fan / NTC / PWM).
#
# This file did not exist, so the whole safety layer was silently dropped from
# the firmware image: ESP-IDF only prints an informational "does not contain a
# CMakeLists.txt file. No component will be added" and carries on.
#
# ---------------------------------------------------------------------------
# THIS COMPONENT DOES NOT LINK SIMULATION CODE INTO THE PRODUCTION IMAGE.
# ---------------------------------------------------------------------------
# safety.c defines a *static* simulated read_dc_bus_current() returning
# sim_state.dc_bus_current (and matching stubs for heatsink temperature, RTD
# resistance and fan state). Those definitions, and the whole sim_state struct
# and safety_sim_* API, live inside a single `#ifndef ESP_PLATFORM` block
# (safety.c, "Simulation/Testing Support (Non-ESP builds)"). ESP-IDF defines
# ESP_PLATFORM for every target build -- idf.py passes -DESP_PLATFORM=1 and the
# build system adds it as a compile definition -- so that block is preprocessed
# away here and the `#else` arm is used instead, which merely *declares*
#
#     extern float read_dc_bus_current(void);
#     extern float read_heatsink_temperature(void);
#     extern bool  is_fan_running(void);
#     extern float read_rtd_resistance(void);
#
# with no definition anywhere in the tree. Those are therefore genuine
# undefined symbols at link time, and that is correct and intended: they gate
# the IGBT short-circuit, over-current and thermal trips, and an honest link
# failure is the only acceptable state until a real sensor implementation
# exists. Do not satisfy them with a stub, a weak symbol, or by re-enabling the
# simulation arm -- that would silently fabricate protection.
#
# This is verified, not assumed: `xtensa-esp32s3-elf-nm` on the built
# safety.c object shows no sim_state and no safety_sim_* symbols, and shows
# read_dc_bus_current as an undefined (U) reference rather than a defined one.

idf_component_register(
    SRCS
        "safety.c"
        "adc_guard.c"
        "coil_guard.c"
        "fan_guard.c"
        "ntc_guard.c"
        "pwm_guard.c"
    INCLUDE_DIRS
        "include"
        "."
        # firmware/ itself, for the generated config.h (single-sourced from
        # config.yaml). Mirrors the INCLUDE_DIRS ".." already used by
        # main/CMakeLists.txt for the same header.
        "../.."
    REQUIRES
        temper_hal
        control
        driver
        esp_timer
)
