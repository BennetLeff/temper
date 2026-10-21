cmake_minimum_required(VERSION 3.13)
if(NOT DEFINED ENV{PICO_SDK_PATH})
  message(FATAL_ERROR "Set PICO_SDK_PATH to the pinned Pico SDK 2.2.0 checkout.")
endif()
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(temper_lcr_rev_e C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
# 0: 187.5 kHz (default); 1: 375 kHz (README "Sample rate"). Both PIO programs are always
# assembled so tools/verify_tdm.rs checks both from either build.
set(LCR_FS_375K 0 CACHE STRING "1 builds the 375 kHz sample-rate variant")
add_executable(temper_lcr src/main.c src/syncavg.c src/wave.c src/tac5112.c src/relay.c)
pico_generate_pio_header(temper_lcr ${CMAKE_CURRENT_LIST_DIR}/src/tdm.pio)
pico_generate_pio_header(temper_lcr ${CMAKE_CURRENT_LIST_DIR}/src/tdm375.pio)
target_include_directories(temper_lcr PRIVATE src)
target_link_libraries(temper_lcr pico_stdlib pico_bootrom pico_unique_id hardware_pio hardware_dma
                      hardware_clocks hardware_adc hardware_i2c)
target_compile_options(temper_lcr PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(temper_lcr PRIVATE
    SYNCAVG_IN_RAM=1
    LCR_FS_375K=${LCR_FS_375K}
    PICO_DEFAULT_UART_TX_PIN=28
    PICO_DEFAULT_UART_RX_PIN=29
    PICO_STDIO_USB_DEVICE_SELF_POWERED=1
    PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=0
    PICO_STDIO_USB_STDOUT_TIMEOUT_US=5000000
    USBD_MANUFACTURER="Temper"
    USBD_PRODUCT="Temper LCR E-codec")
pico_enable_stdio_usb(temper_lcr 1)
pico_enable_stdio_uart(temper_lcr 0)
pico_add_extra_outputs(temper_lcr)
