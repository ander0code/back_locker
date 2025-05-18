#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
using namespace websockets;

const char* SSID       = "FAM TITO";
const char* PASS       = "Max17Conny10";
const IPAddress BACKEND_IP(192, 168, 100, 6);
const uint16_t BACKEND_PORT = 8000;
const String WS_PREFIX = "/ws/locker/";  
const int   LOCKER_ID  = 1;

// ————— Pines HC-SR04 y Servo —————
constexpr int PIN_TRIG  = 5;
constexpr int PIN_ECHO  = 18;
constexpr int PIN_SERVO = 13;
Servo servoMotor;

// ————— WebSocket —————
WebsocketsClient ws;

// ————— Temporizadores y umbrales —————
constexpr unsigned long STORE_TIMEOUT   = 5000;
constexpr unsigned long CLOSE_DELAY     = 3000;
constexpr unsigned long DEBOUNCE_PERIOD = 100;

enum State { IDLE, OPEN_WAIT_STORE, OPEN_WAIT_CLOSE };
State state     = IDLE;
bool  modeStore = true;
unsigned long storeDeadline, closeDeadline, lastPrintStore, lastPrintClose;
int prevSecsStore = -1, prevSecsClose = -1;
float lastDistance = -1;

// ————— Prototipos —————
float measureDistance();
void onOpen();
void onClose();
void prepareClose(unsigned long now);
bool detectObjectChange();
bool hasObject();
void runStateMachine();
void sendEvent(const char* evt, float val = NAN);

// ————— Callback WS —————
void onWsMessage(WebsocketsMessage msg) {
  StaticJsonDocument<128> doc;
  auto err = deserializeJson(doc, msg.data());
  if (err) return;
  if (doc["cmd"] == "actuate" && doc["open"] == true) {
    modeStore = (String((const char*)doc["mode"]) == "store");
    onOpen();
  }
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(SSID, PASS);
  Serial.print("Conectando Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi OK, IP: " + WiFi.localIP().toString());

  servoMotor.attach(PIN_SERVO, 500, 2400);
  servoMotor.write(0);

  ws.onMessage(onWsMessage);
  String url = "ws://" + BACKEND_IP.toString() + ":" + String(BACKEND_PORT) + WS_PREFIX + String(LOCKER_ID);
  ws.connect(url);
}

void loop() {
  ws.poll();
  runStateMachine();

  static unsigned long lastDist=0;
  if (millis() - lastDist > 2000) {
    lastDist = millis();
    float d = measureDistance();
    sendEvent("distance", d);
  }
}

// ————— Máquina de estados —————
void onOpen() {
  sendEvent("opening");
  servoMotor.write(180);
  storeDeadline  = millis() + STORE_TIMEOUT;
  lastPrintStore = 0; prevSecsStore = -1;
  state = OPEN_WAIT_STORE;
}

void onClose() {
  sendEvent("forced_closed");
  servoMotor.write(0);
  state = IDLE;
}

void prepareClose(unsigned long now) {
  closeDeadline  = now + CLOSE_DELAY;
  lastPrintClose = 0; prevSecsClose = -1;
  sendEvent("closing_in", CLOSE_DELAY/1000.0);
  state = OPEN_WAIT_CLOSE;
}

void runStateMachine() {
  unsigned long now = millis();
  switch(state) {
    case OPEN_WAIT_STORE: {
      int secs = max(0, int((storeDeadline - now + 999)/1000));
      if (secs != prevSecsStore && now - lastPrintStore >= 1000) {
        prevSecsStore = secs; lastPrintStore = now;
        sendEvent("store_timer", secs);
      }
      if (detectObjectChange() || hasObject()) {
        storeDeadline = now + STORE_TIMEOUT;
        sendEvent("object_detected");
      }
      if (now >= storeDeadline) {
        prepareClose(now);
      }
      break;
    }
    case OPEN_WAIT_CLOSE: {
      int secs = max(0, int((closeDeadline - now + 999)/1000));
      if (secs != prevSecsClose && now - lastPrintClose >= 1000) {
        prevSecsClose = secs; lastPrintClose = now;
        sendEvent("closing_timer", secs);
      }
      if (now >= closeDeadline) {
        for (int a = 180; a >= 0; --a) {
          servoMotor.write(a);
          delay(10);
        }
        sendEvent("closed");
        state = IDLE;
      }
      break;
    }
    case IDLE:
    default:
      break;
  }
}

bool detectObjectChange() {
  static unsigned long lastChk=0;
  if (millis()-lastChk < DEBOUNCE_PERIOD) return false;
  lastChk = millis();
  float sum=0; int cnt=0;
  for (int i=0; i<3; ++i) {
    float d = measureDistance();
    if (d>0) { sum+=d; cnt++; }
    delay(10);
  }
  if (!cnt) return false;
  float avg = sum/cnt;
  bool changed = fabs(avg - lastDistance) > 1.0;
  lastDistance = avg;
  if (changed) sendEvent("distance_change", avg);
  return changed;
}

bool hasObject() {
  float sum=0; int cnt=0;
  for (int i=0; i<3; ++i) {
    float d = measureDistance();
    if (d>0) { sum+=d; cnt++; }
    delay(10);
  }
  if (!cnt) return false;
  float avg = sum/cnt;
  bool present = (avg>0 && avg<15);
  if (present) sendEvent("object_present", avg);
  return present;
}

float measureDistance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 25000);
  return (dur>0)?(dur*0.0343f)/2.0f:-1;
}

void sendEvent(const char* evt, float val) {
  StaticJsonDocument<128> doc;
  doc["event"] = evt;
  if (!isnan(val)) doc["value"] = val;
  String out;
  serializeJson(doc, out);
  ws.send(out);
}
