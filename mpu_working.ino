// mpu_udp_stream.ino
#include <Wire.h>
#include "I2Cdev.h"
#include "MPU6050.h"
#include <WiFi.h>
#include <WiFiUdp.h>

MPU6050 mpu;
WiFiUDP udp;

// --- NETWORK ---
const char* ssid     = "Redmi Note 13 Pro+ 5G";
const char* password = "nahidunga";
const char* hostIP   = "10.129.90.199"; // set to laptop IP
const uint16_t hostPort = 5005;

// timing
const unsigned long SAMPLE_INTERVAL = 5; // 5ms = 200 Hz
unsigned long lastSample = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(21, 22); // explicit SDA=21, SCL=22 for ESP32
  Serial.println("Initializing MPU6050...");
  mpu.initialize();
  if (mpu.testConnection()) {
    Serial.println("MPU6050 connected!");
  } else {
    Serial.println("MPU6050 NOT connected!");
  }
  
  // Connect to WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
    delay(200);
    Serial.print('.');
  }
  Serial.println();
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Sending data to: ");
    Serial.print(hostIP);
    Serial.print(":");
    Serial.println(hostPort);
  } else {
    Serial.println("WiFi not connected (continuing)");
  }
  
  lastSample = millis();
  Serial.println("Starting data stream...");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL) return;
  lastSample = now;

  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
  
  // Convert to physical units
  // Accel: +/-2g range, 16384 LSB/g
  float ax_ms2 = (float)ax / 16384.0 * 9.80665;
  float ay_ms2 = (float)ay / 16384.0 * 9.80665;
  float az_ms2 = (float)az / 16384.0 * 9.80665;
  
  // Gyro: +/-250 deg/s range, 131 LSB/(deg/s)
  float gx_dps = (float)gx / 131.0;
  float gy_dps = (float)gy / 131.0;
  float gz_dps = (float)gz / 131.0;

  // Build JSON message
  String msg = "{";
  msg += "\"ax\":" + String(ax_ms2, 3) + ",";
  msg += "\"ay\":" + String(ay_ms2, 3) + ",";
  msg += "\"az\":" + String(az_ms2, 3) + ",";
  msg += "\"gx\":" + String(gx_dps, 3) + ",";
  msg += "\"gy\":" + String(gy_dps, 3) + ",";
  msg += "\"gz\":" + String(gz_dps, 3) + ",";
  msg += "\"t\":" + String(millis());
  msg += "}";

  // Send UDP if WiFi connected
  if (WiFi.status() == WL_CONNECTED) {
    udp.beginPacket(hostIP, hostPort);
    udp.write((const uint8_t*)msg.c_str(), msg.length());
    udp.endPacket();
  }
  
  // Print to serial every 50 samples (~250ms)
  static int count = 0;
  if (++count >= 50) {
    Serial.print("A: "); Serial.print(ax); Serial.print(" ");
    Serial.print(ay); Serial.print(" ");
    Serial.print(az); Serial.print("  |  G: ");
    Serial.print(gx); Serial.print(" "); Serial.print(gy); Serial.print(" ");
    Serial.println(gz);
    count = 0;
  }
}
