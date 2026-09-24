AVR_GCC ?= avr-gcc
AVR_SIZE ?= avr-size
PROFILE ?= locked
ifeq ($(PROFILE),locked)
OUT ?= /tmp/temper-rev38-avr64da32.elf
else ifeq ($(PROFILE),engineering)
OUT ?= /tmp/temper-rev38-avr64da32-engineering.elf
else
$(error Unknown receiver profile $(PROFILE))
endif
CFLAGS := -std=c11 -Os -Wall -Wextra -Werror -Wpedantic -mmcu=avr64da32
CFLAGS += -ffunction-sections -fdata-sections
ifeq ($(PROFILE),engineering)
# Protocol-development profile only; see ENGINEERING-WINDOWS.md. The default
# locked profile has zero windows and still cannot authorize RUN.
CFLAGS += -DPE_TARGET_ENGINEERING_CANDIDATE
CFLAGS += -DPE_TARGET_PREPARE_WINDOW_MS=250u
CFLAGS += -DPE_TARGET_START_WINDOW_MS=100u
CFLAGS += -DPE_TARGET_WATCHDOG_WINDOW_MS=75u
CFLAGS += -DPE_TARGET_BYTE_GAP_MS=10u
CFLAGS += -DPE_TARGET_PING_PERIOD_MS=20u
CFLAGS += -DPE_TARGET_SAMPLE_TO_RUN_MS=5u
CFLAGS += -DPE_TARGET_EXPECTED_WDTCFG=0x05u
CFLAGS += -DPE_TARGET_EXPECTED_BODCFG=0x65u
CFLAGS += -DPE_TARGET_EXPECTED_SYSCFG0=0xC9u
endif
LDFLAGS := -mmcu=avr64da32 -Wl,--gc-sections
SOURCES := protocol.c journal.c receiver.c runtime.c avr64da32_boot_contract.c avr64da32_target.c

.PHONY: all
all:
	$(AVR_GCC) $(CFLAGS) $(SOURCES) $(LDFLAGS) -o $(OUT)
	$(AVR_SIZE) $(OUT)
