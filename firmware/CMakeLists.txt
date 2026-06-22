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
if(NOT gen_config_result EQUAL 0)
    message(WARNING "config.h regeneration failed — using committed copy")
endif()

# Regenerate transition_table.h from transition_table.yaml before every build.
execute_process(
    COMMAND python3 "${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_transition_table.py"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE gen_tt_result
)
if(NOT gen_tt_result EQUAL 0)
    message(WARNING "transition_table.h regeneration failed — using committed copy")
endif()

# Include ESP-IDF CMake functions
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Project name
project(induction_cooker)

# Set C standard
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
