#define TOUCH_PIN 15

void setup() {
  Serial.begin(115200);
  pinMode(TOUCH_PIN, INPUT);
}

void loop() {
  int val = digitalRead(TOUCH_PIN);
  if (val == HIGH) {
    Serial.println("Touched!");
  } else {
    Serial.println("Not touched");
  }
  delay(100);
}
