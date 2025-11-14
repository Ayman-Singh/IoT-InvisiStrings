// touch_event_esp_pressed_only.ino
#include <WiFi.h>
#include <WiFiUdp.h>

const char* ssid     = "Redmi Note 13 Pro+ 5G";
const char* password = "nahidunga";
const char* hostIP = "10.129.90.199";
const uint16_t hostPort = 5005;

// --- SENSORS ---
const int S_PINS[] = {15, 4, 18, 19, 21};
const int NUM_S = sizeof(S_PINS) / sizeof(S_PINS[0]);

// Debounce & send options
const unsigned long DEBOUNCE_MS = 50;
const bool SEND_ON_PRESS_ONLY = true; // <<-- only send when sensor becomes ACTIVE_STATE
const int ACTIVE_STATE = HIGH;        // set to HIGH if "1" = touched; set LOW if sensors are active-low

WiFiUDP udp;

int lastState[NUM_S];
unsigned long lastChangeTs[NUM_S];

void sendJsonChange(int idx, int newState) {
  String msg = "{";
  msg += "\"device\":\"touch_esp\",";
  msg += "\"sensor\":" + String(idx) + ",";
  msg += "\"state\":" + String(newState) + ",";
  msg += "\"ts\":" + String(millis());
  msg += "}";
  Serial.println("UDP-> " + msg);
  udp.beginPacket(hostIP, hostPort);
  udp.write((const uint8_t*)msg.c_str(), msg.length());
  int res = udp.endPacket(); // 1 = success normally
  Serial.printf("udp endPacket returned %d\n", res);
}

void setup() {
  Serial.begin(115200);
  delay(10);

  // choose pull mode based on active polarity
  for (int i=0;i<NUM_S;i++){
    if (ACTIVE_STATE == LOW) {
      pinMode(S_PINS[i], INPUT_PULLUP);    // active = LOW -> use internal pull-up
    } else {
      pinMode(S_PINS[i], INPUT_PULLDOWN);  // active = HIGH -> use internal pull-down
    }
    lastState[i] = digitalRead(S_PINS[i]);
    lastChangeTs[i] = 0;
    Serial.printf("Pin %d initial %d\n", S_PINS[i], lastState[i]);
  }

  // wifi
  WiFi.begin(ssid, password);
  Serial.printf("Connecting to WiFi %s ...\n", ssid);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis()-t0 < 15000) {
    delay(200);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) Serial.printf("Connected. IP: %s\n", WiFi.localIP().toString().c_str());
  else Serial.println("WiFi connect failed (continuing).");
}

void loop() {
  unsigned long now = millis();
  for (int i=0;i<NUM_S;i++){
    int r = digitalRead(S_PINS[i]);
    if (r != lastState[i]) {
      // candidate change - check debounce time
      if (now - lastChangeTs[i] >= DEBOUNCE_MS) {
        // commit change
        lastChangeTs[i] = now;
        int prev = lastState[i];
        lastState[i] = r;
        // only send when sensor becomes ACTIVE_STATE (pressed)
        if (SEND_ON_PRESS_ONLY) {
          if (r == ACTIVE_STATE) {
            sendJsonChange(i+1, r);
          } // else: do not send on release
        } else {
          // fallback: send on any change
          sendJsonChange(i+1, r);
        }
      }
    }
  }
  delay(5);
}
