// sensor-r3 bench logger: MAX31865 (Pt100, auto-conversion ~60 Hz) + MAX31856 (type-K pan
// reference, auto-conversion ~10 Hz) on one ESP32-S3 SPI bus, one microsecond clock.
//
// Board: ESP32-S3-DevKitC-1 (Arduino core for ESP32 >= 2.0, "USB CDC On Boot: Enabled").
// Wiring (3V3 logic; both breakouts powered from 3V3):
//   SCK 12, MISO 13, MOSI 11 (FSPI defaults)
//   MAX31865 CS 10, DRDY 4     (Adafruit 3328, PT100 version, Rref 430 ohm, 4-wire jumpers set)
//   MAX31856 CS 9,  DRDY 5     (Adafruit 3263, type K)
//   marker button: BOOT (GPIO0), press at each set-down
//
// Output, one record per line (fit.py / logger.py read it):
//   R,<t_us>,<rtd_reg16>          raw RTD register (15-bit code << 1 | fault bit)
//   T,<t_us>,<tc_counts>,<cj>     LTC 19-bit signed (LSB 2^-7 C), cold junction 14-bit (LSB 2^-6 C)
//   F,<t_us>,<fault_status>       MAX31865 fault register when the fault bit is set (then cleared)
//   M,<t_us>,<n>                  marker
//   #,...                         info lines
// Not compiled in the session that wrote it (no Arduino toolchain there); see DECISIONS.md D9.

#include <SPI.h>
#include "esp_timer.h"

static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11;
static const int CS_RTD = 10, DRDY_RTD = 4;
static const int CS_TC = 9, DRDY_TC = 5;
static const int PIN_MARK = 0;

// MAX31865 config: VBIAS on, auto-convert, 2/4-wire, fault-status clear, 60 Hz notch.
static const uint8_t RTD_CFG = 0xC2;
// MAX31856: CR0 auto-convert, 60 Hz notch; CR1 1-sample averaging, type K.
static const uint8_t TC_CR0 = 0x80, TC_CR1 = 0x03;

SPISettings spiset(1000000, MSBFIRST, SPI_MODE1);   // both parts accept mode 1 or 3

static void wr(int cs, uint8_t reg, uint8_t v) {
  SPI.beginTransaction(spiset);
  digitalWrite(cs, LOW);
  SPI.transfer(reg | 0x80);
  SPI.transfer(v);
  digitalWrite(cs, HIGH);
  SPI.endTransaction();
}

static void rd(int cs, uint8_t reg, uint8_t *buf, int n) {
  SPI.beginTransaction(spiset);
  digitalWrite(cs, LOW);
  SPI.transfer(reg & 0x7F);
  for (int i = 0; i < n; i++) buf[i] = SPI.transfer(0x00);
  digitalWrite(cs, HIGH);
  SPI.endTransaction();
}

static uint32_t marks = 0;
static int last_btn = HIGH;
static int64_t last_btn_t = 0;

void setup() {
  Serial.begin(921600);
  pinMode(CS_RTD, OUTPUT); digitalWrite(CS_RTD, HIGH);
  pinMode(CS_TC, OUTPUT);  digitalWrite(CS_TC, HIGH);
  pinMode(DRDY_RTD, INPUT_PULLUP);
  pinMode(DRDY_TC, INPUT_PULLUP);
  pinMode(PIN_MARK, INPUT_PULLUP);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, -1);
  delay(50);
  wr(CS_RTD, 0x00, RTD_CFG);
  wr(CS_TC, 0x00, TC_CR0);
  wr(CS_TC, 0x01, TC_CR1);
  uint8_t c[2];
  rd(CS_RTD, 0x00, c, 1);
  rd(CS_TC, 0x01, c + 1, 1);
  Serial.printf("#,logger_fw,rtd_cfg=0x%02X,tc_cr1=0x%02X\n", c[0], c[1]);
}

void loop() {
  if (digitalRead(DRDY_RTD) == LOW) {
    uint8_t b[2];
    rd(CS_RTD, 0x01, b, 2);
    int64_t t = esp_timer_get_time();
    uint16_t reg = ((uint16_t)b[0] << 8) | b[1];
    Serial.printf("R,%lld,%u\n", (long long)t, reg);
    if (reg & 1) {
      uint8_t f;
      rd(CS_RTD, 0x07, &f, 1);
      Serial.printf("F,%lld,%u\n", (long long)t, f);
      wr(CS_RTD, 0x00, RTD_CFG);          // D1 clears the fault status
    }
  }
  if (digitalRead(DRDY_TC) == LOW) {
    uint8_t b[5];
    rd(CS_TC, 0x0A, b, 5);                // CJTH CJTL LTCBH LTCBM LTCBL
    int64_t t = esp_timer_get_time();
    int32_t raw = ((int32_t)b[2] << 16) | ((int32_t)b[3] << 8) | b[4];
    if (raw & 0x800000) raw |= (int32_t)0xFF000000;   // sign-extend 24 bits
    int32_t tc = raw >> 5;                            // 19-bit, LSB 2^-7 C
    int16_t cj = (int16_t)(((uint16_t)b[0] << 8) | b[1]) >> 2;   // 14-bit, LSB 2^-6 C
    Serial.printf("T,%lld,%ld,%d\n", (long long)t, (long)tc, cj);
  }
  int btn = digitalRead(PIN_MARK);
  int64_t now = esp_timer_get_time();
  if (btn == LOW && last_btn == HIGH && now - last_btn_t > 200000) {
    Serial.printf("M,%lld,%lu\n", (long long)now, (unsigned long)++marks);
    last_btn_t = now;
  }
  last_btn = btn;
}
