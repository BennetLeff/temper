/* USB descriptors of the Rev E/F firmware: a CDC serial function, bus powered, 500 mA.

   Pico SDK 2.2.0 pico_stdio_usb has no setting for the declared current. Its default descriptors
   (stdio_usb_descriptors.c) hard-code USBD_MAX_POWER_MA to 250 for a bus-powered device, and to 1
   with PICO_STDIO_USB_DEVICE_SELF_POWERED=1, without an #ifndef, so a -D of it would only be a
   redefinition. CMakeLists.txt therefore sets PICO_STDIO_USB_USE_DEFAULT_DESCRIPTORS=0 and this
   file supplies the three TinyUSB descriptor callbacks. Everything else is the SDK file's content
   (same VID/PID, strings, serial number and endpoints), which is BSD-3-Clause / MIT licensed:
   Copyright (c) 2020 Raspberry Pi (Trading) Ltd., Copyright (c) 2019 Damien P. George.

   The board draws about 0.46 A from VBUS (validation/power-spurs/regulator_check.json) and has
   no self power: USB 2.0 7.2.1 allows a bus-powered function 500 mA after configuration, which
   the configuration descriptor must state (audit PE-3). */
#include "pico/stdio_usb.h"
#include "pico/unique_id.h"
#include "tusb.h"

#if PICO_STDIO_USB_USE_DEFAULT_DESCRIPTORS || PICO_STDIO_USB_ENABLE_RESET_VIA_VENDOR_INTERFACE || \
    PICO_STDIO_USB_DEVICE_SELF_POWERED
#error "usb_descriptors.c replaces the SDK descriptors: CDC only, bus powered (see CMakeLists.txt)"
#endif

#ifndef USBD_VID
#define USBD_VID (0x2E8A) /* Raspberry Pi */
#endif
#ifndef USBD_PID
#define USBD_PID (0x000a) /* Raspberry Pi Pico SDK CDC for RP2040 */
#endif
#ifndef USBD_MANUFACTURER
#define USBD_MANUFACTURER "Raspberry Pi"
#endif
#ifndef USBD_PRODUCT
#define USBD_PRODUCT "Pico"
#endif

#define USBD_DESC_LEN (TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN)
#define USBD_CONFIGURATION_DESCRIPTOR_ATTRIBUTE (0) /* bus powered, no remote wake-up */
#define USBD_MAX_POWER_MA (500)                     /* bMaxPower = 250 (2 mA units) */

#define USBD_ITF_CDC (0) /* needs 2 interfaces */
#define USBD_ITF_MAX (2)
#define USBD_CDC_EP_CMD (0x81)
#define USBD_CDC_EP_OUT (0x02)
#define USBD_CDC_EP_IN (0x82)
#define USBD_CDC_CMD_MAX_SIZE (8)
#define USBD_CDC_IN_OUT_MAX_SIZE (64)

#define USBD_STR_0 (0x00)
#define USBD_STR_MANUF (0x01)
#define USBD_STR_PRODUCT (0x02)
#define USBD_STR_SERIAL (0x03)
#define USBD_STR_CDC (0x04)

/* Descriptors returned from callbacks must exist long enough for the transfer to complete. */
static const tusb_desc_device_t usbd_desc_device = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = USBD_VID,
    .idProduct = USBD_PID,
    .bcdDevice = 0x0100,
    .iManufacturer = USBD_STR_MANUF,
    .iProduct = USBD_STR_PRODUCT,
    .iSerialNumber = USBD_STR_SERIAL,
    .bNumConfigurations = 1,
};

static const uint8_t usbd_desc_cfg[USBD_DESC_LEN] = {
    TUD_CONFIG_DESCRIPTOR(1, USBD_ITF_MAX, USBD_STR_0, USBD_DESC_LEN,
        USBD_CONFIGURATION_DESCRIPTOR_ATTRIBUTE, USBD_MAX_POWER_MA),

    TUD_CDC_DESCRIPTOR(USBD_ITF_CDC, USBD_STR_CDC, USBD_CDC_EP_CMD,
        USBD_CDC_CMD_MAX_SIZE, USBD_CDC_EP_OUT, USBD_CDC_EP_IN, USBD_CDC_IN_OUT_MAX_SIZE),
};

static char usbd_serial_str[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

static const char *const usbd_desc_str[] = {
    [USBD_STR_MANUF] = USBD_MANUFACTURER,
    [USBD_STR_PRODUCT] = USBD_PRODUCT,
    [USBD_STR_SERIAL] = usbd_serial_str,
    [USBD_STR_CDC] = "Board CDC",
};

const uint8_t *tud_descriptor_device_cb(void) {
    return (const uint8_t *)&usbd_desc_device;
}

const uint8_t *tud_descriptor_configuration_cb(__unused uint8_t index) {
    return usbd_desc_cfg;
}

const uint16_t *tud_descriptor_string_cb(uint8_t index, __unused uint16_t langid) {
#define USBD_DESC_STR_MAX (20)
    static uint16_t desc_str[USBD_DESC_STR_MAX];

    /* The serial number is the unique flash id. */
    if (!usbd_serial_str[0]) {
        pico_get_unique_board_id_string(usbd_serial_str, sizeof(usbd_serial_str));
    }

    uint8_t len;
    if (index == 0) {
        desc_str[1] = 0x0409; /* supported language is English */
        len = 1;
    } else {
        if (index >= sizeof(usbd_desc_str) / sizeof(usbd_desc_str[0])) {
            return NULL;
        }
        const char *str = usbd_desc_str[index];
        for (len = 0; len < USBD_DESC_STR_MAX - 1 && str[len]; ++len) {
            desc_str[1 + len] = str[len];
        }
    }

    /* First byte is the length (including the header), second the string type. */
    desc_str[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * len + 2));

    return desc_str;
}
