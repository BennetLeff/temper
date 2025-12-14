# Top-level CMakeLists.txt for Induction Cooker Firmware
# For use with ESP-IDF build system

cmake_minimum_required(VERSION 3.16)

# Include ESP-IDF CMake functions
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Project name
project(induction_cooker)

# Set C standard
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
