# Top-level CMakeLists.txt for Induction Cooker Firmware
# For use with ESP-IDF build system

cmake_minimum_required(VERSION 3.16)

# Regenerate config.h from config.yaml before every build.
# Uses configure-time generation so it works under ESP-IDF's
# project.cmake wrapper (which may not propagate pre-project
# custom commands to component libraries).
execute_process(
    COMMAND python3 "${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_config.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE gen_config_result
)
# A failed regeneration is fatal: config.h carries the safety thresholds, and a
# silently stale copy would build a firmware that disagrees with config.yaml.
# The usual cause is the IDF Python env lacking the codegen deps:
#   python -m pip install -r firmware/tools/requirements.txt  (after export.sh)
if(NOT gen_config_result EQUAL 0)
    message(FATAL_ERROR "config.h regeneration failed (exit ${gen_config_result}). "
        "Install the codegen deps into the IDF Python env: "
        "python -m pip install -r tools/requirements.txt")
endif()

# Regenerate transition_table.h from transition_table.yaml before every build.
execute_process(
    COMMAND python3 "${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_transition_table.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE gen_tt_result
)
if(NOT gen_tt_result EQUAL 0)
    message(FATAL_ERROR "transition_table.h regeneration failed (exit ${gen_tt_result}). "
        "Install the codegen deps into the IDF Python env: "
        "python -m pip install -r tools/requirements.txt")
endif()

# Include ESP-IDF CMake functions
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Project name
project(induction_cooker)

# Set C standard
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
