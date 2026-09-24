AVR_GCC ?= avr-gcc
AVR_SIZE ?= avr-size
OUT ?= /tmp/temper-rev38-avr64da32.elf
CFLAGS := -std=c11 -Os -Wall -Wextra -Werror -Wpedantic -mmcu=avr64da32
CFLAGS += -ffunction-sections -fdata-sections
LDFLAGS := -mmcu=avr64da32 -Wl,--gc-sections
SOURCES := protocol.c journal.c receiver.c runtime.c avr64da32_boot_contract.c avr64da32_target.c

.PHONY: all
all:
	$(AVR_GCC) $(CFLAGS) $(SOURCES) $(LDFLAGS) -o $(OUT)
	$(AVR_SIZE) $(OUT)
