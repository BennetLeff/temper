# Control component: PLL/ZVS tracking, PID + cascade PID, pan detection,
# thermal-mass estimation and cooking profiles.
#
# This file did not exist. ESP-IDF's component scan reports a directory with no
# CMakeLists.txt with an *informational* message ("does not contain a
# CMakeLists.txt file. No component will be added") and then continues, so the
# entire control layer was dropped from the firmware image without the build
# ever failing. main/state_machine.c includes ../components/control/*.h and
# calls into it, so those calls were unresolved at link.
#
# NOTE: adding this component does NOT compile any simulation code into the
# image. Every pll_sim_*/zvs_sim_* entry point in these sources sits inside an
# `#ifndef ESP_PLATFORM` block, and ESP-IDF defines ESP_PLATFORM for every
# target build, so those blocks are preprocessed away here. See the same note
# in ../safety/CMakeLists.txt, which is the load-bearing case.

idf_component_register(
    SRCS
        "pll_control.c"
        "zvs_monitor.c"
        "pid_control.c"
        "cascade_pid.c"
        "pan_detect.c"
        "thermal_mass.c"
        "low_temp_control.c"
        "profiles.c"
    INCLUDE_DIRS
        "."
    REQUIRES
        driver
        esp_timer
)
