// Jet bench logger (temper-airflow-r1/bench): the sensor-r3 ESP32-S3 + MAX31865 kit plus
//   up to 7 x MAX31856 type-K channels (plate x3, guard x2, jet air, exit air)
//   INA226 (plate heater volts and amps), SDP810-125Pa (jet manifold pressure)
//   one PWM output for the guard heater, duty commanded by jet_logger.py over USB serial.
//
// Board: ESP32-S3-DevKitC-1 (Arduino core for ESP32 2.x or 3.x, "USB CDC On Boot: Enabled").
// Wiring (3V3 logic; all breakouts on 3V3):
//   SPI  SCK 12, MISO 13, MOSI 11 (as sensor-r3)
//   MAX31865 CS 10 (Pt100, hood stand-in air)           MAX31856 CS: 9 (the kit's), 14, 15, 16, 17, 18, 21
//   I2C  SDA 1, SCL 2 (INA226 at 0x40, SDP810 at 0x25; 4.7k pull-ups if the modules lack them)
//   Guard heater MOSFET gate: GPIO 7 (logic-level module; not 38, the v1.1 RGB LED)   Marker button: BOOT (GPIO 0)
//
// Output, one record per line (jet_logger.py reads it; raw values, the host converts):
//   K,<t_us>,<ch>,<ltc_counts>,<cj_counts>,<sr>   MAX31856 ch 0..6: LTC 19-bit signed (LSB 2^-7 C), CJ 14-bit (LSB 2^-6 C), fault reg
//   R,<t_us>,<rtd_reg16>                          MAX31865 RTD register
//   P,<t_us>,<shunt_raw>,<bus_raw>                INA226: shunt int16 (LSB 2.5 uV), bus uint16 (LSB 1.25 mV)
//   D,<t_us>,<dp_raw>,<t_raw>,<scale>             SDP810: dp = dp_raw / scale Pa, T = t_raw / 200 C
//   G,<t_us>,<duty>                               guard duty 0..1023 (after each command)
//   M,<t_us>,<n>                                  marker
//   #,...                                         info / alarms
// Input: "G <0..1023>\n" sets the guard duty. The duty falls to 0 if no command arrives for 5 s (host gone).
// Not compiled in the session that wrote it (no Arduino toolchain there): first bring-up step in PROCEDURE.md.

#include <SPI.h>
#include <Wire.h>
#include "esp_timer.h"

static const int PIN_SCK = 12, PIN_MISO = 13, PIN_MOSI = 11;
static const int CS_RTD = 10;
static const int CS_TC[] = {9, 14, 15, 16, 17, 18, 21};
static const int N_TC = sizeof(CS_TC) / sizeof(CS_TC[0]);
static const int PIN_SDA = 1, PIN_SCL = 2;
static const int PIN_GUARD = 7, PIN_MARK = 0;
static const uint8_t INA_ADDR = 0x40, SDP_ADDR = 0x25;

static const uint8_t RTD_CFG = 0xC2;                 // VBIAS, auto-convert, fault clear, 60 Hz
static const uint8_t TC_CR0 = 0x80, TC_CR1 = 0x23;   // auto-convert 60 Hz; 4-sample average, type K
static const uint16_t INA_CFG = 0x4727;              // AVG 64, 1.1 ms bus/shunt, continuous (~140 ms/result)

SPISettings spiset(1000000, MSBFIRST, SPI_MODE1);

static void wr(int cs, uint8_t reg, uint8_t v) {
  SPI.beginTransaction(spiset); digitalWrite(cs, LOW);
  SPI.transfer(reg | 0x80); SPI.transfer(v);
  digitalWrite(cs, HIGH); SPI.endTransaction();
}

static void rd(int cs, uint8_t reg, uint8_t *buf, int n) {
  SPI.beginTransaction(spiset); digitalWrite(cs, LOW);
  SPI.transfer(reg & 0x7F);
  for (int i = 0; i < n; i++) buf[i] = SPI.transfer(0x00);
  digitalWrite(cs, HIGH); SPI.endTransaction();
}

static bool i2c_w16(uint8_t addr, uint8_t reg, uint16_t v) {
  Wire.beginTransmission(addr); Wire.write(reg); Wire.write(v >> 8); Wire.write(v & 0xFF);
  return Wire.endTransmission() == 0;
}

static bool i2c_r16(uint8_t addr, uint8_t reg, uint16_t *v) {
  Wire.beginTransmission(addr); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)addr, 2) != 2) return false;
  *v = ((uint16_t)Wire.read() << 8) | Wire.read();
  return true;
}

static uint8_t crc8(const uint8_t *d, int n) {      // Sensirion CRC-8, poly 0x31, init 0xFF
  uint8_t c = 0xFF;
  for (int i = 0; i < n; i++) { c ^= d[i]; for (int b = 0; b < 8; b++) c = (c & 0x80) ? (c << 1) ^ 0x31 : (c << 1); }
  return c;
}

static bool sdp_ok = false, ina_ok = false;
static int guard_duty = 0;
static int64_t last_cmd_us = 0;
static int mark_n = 0;
static bool mark_prev = true;

static void guard_write(int duty) {
  guard_duty = constrain(duty, 0, 1023);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_GUARD, guard_duty);
#else
  ledcWrite(0, guard_duty);
#endif
  Serial.printf("G,%lld,%d\n", esp_timer_get_time(), guard_duty);
}

void setup() {
  Serial.begin(921600);
  pinMode(PIN_MARK, INPUT_PULLUP);
  pinMode(CS_RTD, OUTPUT); digitalWrite(CS_RTD, HIGH);
  for (int i = 0; i < N_TC; i++) { pinMode(CS_TC[i], OUTPUT); digitalWrite(CS_TC[i], HIGH); }
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI);
  wr(CS_RTD, 0x00, RTD_CFG);
  for (int i = 0; i < N_TC; i++) { wr(CS_TC[i], 0x00, TC_CR0); wr(CS_TC[i], 0x01, TC_CR1); }
  Wire.begin(PIN_SDA, PIN_SCL, 100000);
  ina_ok = i2c_w16(INA_ADDR, 0x00, INA_CFG);
  Wire.beginTransmission(SDP_ADDR); Wire.write(0x36); Wire.write(0x03);   // continuous, mass-flow T-comp, average till read
  sdp_ok = Wire.endTransmission() == 0;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_GUARD, 1000, 10);
#else
  ledcSetup(0, 1000, 10); ledcAttachPin(PIN_GUARD, 0);
#endif
  guard_write(0);
  delay(50);
  Serial.printf("#,jet_logger_fw,n_tc=%d,ina=%d,sdp=%d\n", N_TC, ina_ok, sdp_ok);
}

static void poll_serial() {
  static char line[32];
  static int n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line[n] = 0;
      if (n > 1 && line[0] == 'G') { guard_write(atoi(line + 1)); last_cmd_us = esp_timer_get_time(); }
      n = 0;
    } else if (n < (int)sizeof(line) - 1) {
      line[n++] = c;
    }
  }
}

void loop() {
  static int64_t t_tc = 0, t_rtd = 0, t_i2c = 0;
  int64_t now = esp_timer_get_time();
  poll_serial();
  if (guard_duty > 0 && now - last_cmd_us > 5000000LL) { guard_write(0); Serial.println("#,ALARM,host silent 5 s: guard off"); }

  if (now - t_tc >= 200000) {                         // 5 Hz per thermocouple channel
    t_tc = now;
    for (int i = 0; i < N_TC; i++) {
      uint8_t b[6];
      rd(CS_TC[i], 0x0A, b, 6);                        // CJTH CJTL LTCBH LTCBM LTCBL SR
      int32_t cj = (int16_t)((b[0] << 8) | b[1]) >> 2;
      int32_t ltc = ((int32_t)((uint32_t)b[2] << 24 | (uint32_t)b[3] << 16 | (uint32_t)b[4] << 8)) >> 13;
      Serial.printf("K,%lld,%d,%ld,%ld,%u\n", esp_timer_get_time(), i, (long)ltc, (long)cj, b[5]);
    }
  }
  if (now - t_rtd >= 100000) {                        // 10 Hz Pt100
    t_rtd = now;
    uint8_t b[2];
    rd(CS_RTD, 0x01, b, 2);
    uint16_t reg = (b[0] << 8) | b[1];
    Serial.printf("R,%lld,%u\n", esp_timer_get_time(), reg);
    if (reg & 1) { rd(CS_RTD, 0x07, b, 1); Serial.printf("#,RTD_FAULT,%u\n", b[0]); wr(CS_RTD, 0x00, RTD_CFG); }
  }
  if (now - t_i2c >= 200000) {                        // 5 Hz INA226 + SDP810
    t_i2c = now;
    uint16_t sh, bus;
    if (ina_ok && i2c_r16(INA_ADDR, 0x01, &sh) && i2c_r16(INA_ADDR, 0x02, &bus))
      Serial.printf("P,%lld,%d,%u\n", esp_timer_get_time(), (int16_t)sh, bus);
    if (sdp_ok && Wire.requestFrom((int)SDP_ADDR, 9) == 9) {
      uint8_t d[9];
      for (int i = 0; i < 9; i++) d[i] = Wire.read();
      if (crc8(d, 2) == d[2] && crc8(d + 3, 2) == d[5] && crc8(d + 6, 2) == d[8])
        Serial.printf("D,%lld,%d,%d,%u\n", esp_timer_get_time(), (int16_t)((d[0] << 8) | d[1]),
                      (int16_t)((d[3] << 8) | d[4]), (uint16_t)((d[6] << 8) | d[7]));
    }
  }
  bool m = digitalRead(PIN_MARK);
  if (!m && mark_prev) Serial.printf("M,%lld,%d\n", esp_timer_get_time(), ++mark_n);
  mark_prev = m;
}
