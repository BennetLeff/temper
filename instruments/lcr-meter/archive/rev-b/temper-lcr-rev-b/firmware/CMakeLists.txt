cmake_minimum_required(VERSION 3.13)
if(NOT DEFINED ENV{PICO_SDK_PATH})
  message(FATAL_ERROR "Set PICO_SDK_PATH to the pinned Pico SDK 2.2.0 checkout.")
endif()
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(temper_lcr_rev_b C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(temper_lcr src/main.c)
pico_generate_pio_header(temper_lcr ${CMAKE_CURRENT_LIST_DIR}/src/capture.pio)
target_include_directories(temper_lcr PRIVATE src)
target_link_libraries(temper_lcr pico_stdlib pico_unique_id hardware_pio hardware_dma hardware_clocks)
target_compile_options(temper_lcr PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(temper_lcr PRIVATE
    PICO_DEFAULT_UART_TX_PIN=28
    PICO_DEFAULT_UART_RX_PIN=29
    PICO_STDIO_USB_DEVICE_SELF_POWERED=1
    PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=0
    PICO_STDIO_USB_STDOUT_TIMEOUT_US=5000000
    USBD_MANUFACTURER="Temper"
    USBD_PRODUCT="Temper LCR Rev B")
pico_enable_stdio_usb(temper_lcr 1)
pico_enable_stdio_uart(temper_lcr 0)
pico_add_extra_outputs(temper_lcr)
