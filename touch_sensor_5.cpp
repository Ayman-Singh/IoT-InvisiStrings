// Your pins
#define S1 15   // Already using
#define S2 4
#define S3 18
#define S4 19
#define S5 21

void setup() {
  Serial.begin(115200);

  pinMode(S1, INPUT);
  pinMode(S2, INPUT);
  pinMode(S3, INPUT);
  pinMode(S4, INPUT);
  pinMode(S5, INPUT);

  Serial.println("Touch sensors initialized...");
}

void loop() {

  int v1 = digitalRead(S1);
  int v2 = digitalRead(S2);
  int v3 = digitalRead(S3);
  int v4 = digitalRead(S4);
  int v5 = digitalRead(S5);

  Serial.print("S1: "); Serial.print(v1);
  Serial.print("  S2: "); Serial.print(v2);
  Serial.print("  S3: "); Serial.print(v3);
  Serial.print("  S4: "); Serial.print(v4);
  Serial.print("  S5: "); Serial.println(v5);

  delay(150);
}
