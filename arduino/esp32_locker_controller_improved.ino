#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
using namespace websockets;

// —— Configuración Wi-Fi y WebSocket ——
const char* SSID       = "FAM TITO";
const char* PASS       = "Max17Conny10";
const IPAddress BACKEND_IP(192, 168, 100, 6);
const uint16_t BACKEND_PORT = 8000;
const String WS_PREFIX = "/ws/locker/";
const int   LOCKER_ID  = 1;
WebsocketsClient ws;

// —— Pines ——
constexpr int PIN_TRIG  = 5;
constexpr int PIN_ECHO  = 18;
constexpr int PIN_SERVO = 13;
Servo servoMotor;

// —— Temporizadores y estados ——
constexpr unsigned long STORE_TIMEOUT   = 5000;
constexpr unsigned long CLOSE_DELAY     = 3000;
constexpr unsigned long DEBOUNCE_PERIOD = 100;

enum State { IDLE, OPEN_WAIT_STORE, OPEN_WAIT_CLOSE };
State state     = IDLE;
bool  modeStore = true;
String currentType = "unknown";
unsigned long storeDeadline, closeDeadline, lastPrintStore, lastPrintClose;
int prevSecsStore = -1, prevSecsClose = -1;
float lastDistance = -1;

// —— Prototipos ——
void sendEvent(const char* evt, float val = NAN, const char* context = nullptr);
float measureDistance();
bool detectObjectChange();
bool hasObject();
void onOpen();
void prepareClose(unsigned long now);
void runStateMachine();
void onWsMessage(WebsocketsMessage msg);

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  WiFi.begin(SSID, PASS);
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi conectado: " + WiFi.localIP().toString());

  servoMotor.attach(PIN_SERVO, 500, 2400);
  servoMotor.write(0);

  ws.onMessage(onWsMessage);
  ws.onEvent([](WebsocketsEvent event, String data) {
    if (event == WebsocketsEvent::ConnectionOpened) Serial.println("WebSocket conectado");
    else if (event == WebsocketsEvent::ConnectionClosed) Serial.println("WebSocket cerrado");
  });

  String url = "ws://" + BACKEND_IP.toString() + ":" + String(BACKEND_PORT) + WS_PREFIX + String(LOCKER_ID);
  if (ws.connect(url)) Serial.println("Conexión WebSocket exitosa a " + url);
  else Serial.println("Error al conectar WebSocket");
}

void loop() {
  ws.poll();
  runStateMachine();
}

void onWsMessage(WebsocketsMessage msg) {
  Serial.println("Mensaje recibido:");
  Serial.println(msg.data());

  StaticJsonDocument<128> doc;
  if (deserializeJson(doc, msg.data())) return;

  if (doc["cmd"] == "actuate" && doc["open"] == true) {
    modeStore = (String((const char*)doc["mode"]) == "store");
    currentType = doc.containsKey("tipo") ? String((const char*)doc["tipo"]) : "unknown";
    Serial.println("Comando para abrir recibido");
    onOpen();
  }
}

void onOpen() {
  sendEvent("opening");
  servoMotor.write(180);
  storeDeadline = millis() + STORE_TIMEOUT;
  lastPrintStore = 0;
  prevSecsStore = -1;
  state = OPEN_WAIT_STORE;
}

void prepareClose(unsigned long now) {
  closeDeadline = now + CLOSE_DELAY;
  lastPrintClose = 0;
  prevSecsClose = -1;
  sendEvent("closing_in", CLOSE_DELAY / 1000.0, "cerrando locker");
  state = OPEN_WAIT_CLOSE;
}

void runStateMachine() {
  unsigned long now = millis();

  if (state == OPEN_WAIT_STORE) {
    int secs = max(0, int((storeDeadline - now + 999) / 1000));
    if (secs != prevSecsStore && now - lastPrintStore >= 1000) {
      prevSecsStore = secs;
      lastPrintStore = now;
      sendEvent("store_timer", secs, modeStore ? "esperando objeto" : "esperando retiro");
    }

    if (modeStore) {
      if (detectObjectChange() || hasObject()) {
        storeDeadline = now + STORE_TIMEOUT;
        sendEvent("object_detected");
      }
    } else {
      if (hasObject()) {
        storeDeadline = now + STORE_TIMEOUT;
        sendEvent("object_still_present");
      } else {
        sendEvent("object_absent");
      }
    }

    if (now >= storeDeadline) {
      prepareClose(now);
    }
  }

  else if (state == OPEN_WAIT_CLOSE) {
    int secs = max(0, int((closeDeadline - now + 999) / 1000));
    if (secs != prevSecsClose && now - lastPrintClose >= 1000) {
      prevSecsClose = secs;
      lastPrintClose = now;
      sendEvent("closing_timer", secs, "cerrando locker");
    }

    if (now >= closeDeadline) {
      servoMotor.write(0);
      sendEvent("closed");

      // ⭐ Nuevo: Enviar identificador del origen
      StaticJsonDocument<96> extra;
      extra["tipo"] = currentType;
      extra["event"] = "closed";
      String payload;
      serializeJson(extra, payload);
      ws.send(payload);
      Serial.println("Evento enviado: " + payload);

      if (!modeStore) {
        sendEvent("object_retrieved");
      }

      state = IDLE;
    }
  }
}

float measureDistance() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 25000);
  return (dur > 0) ? (dur * 0.0343f) / 2.0f : -1;
}

bool detectObjectChange() {
  static unsigned long lastChk = 0;
  if (millis() - lastChk < DEBOUNCE_PERIOD) return false;
  lastChk = millis();

  float sum = 0;
  int cnt = 0;
  for (int i = 0; i < 3; ++i) {
    float d = measureDistance();
    if (d > 0) { sum += d; cnt++; }
    delay(10); yield();
  }
  if (!cnt) return false;

  float avg = sum / cnt;
  bool changed = fabs(avg - lastDistance) > 1.0;
  lastDistance = avg;
  if (changed) sendEvent("distance_change", avg);
  return changed;
}

bool hasObject() {
  float sum = 0;
  int cnt = 0;
  for (int i = 0; i < 3; ++i) {
    float d = measureDistance();
    if (d > 0) { sum += d; cnt++; }
    delay(10); yield();
  }
  if (!cnt) return false;

  float avg = sum / cnt;
  bool present = (avg > 0 && avg <= 16);
  if (present) sendEvent("object_present", avg);
  return present;
}

void sendEvent(const char* evt, float val, const char* context) {
  StaticJsonDocument<192> doc;
  doc["event"] = evt;
  if (!isnan(val)) doc["value"] = val;
  if (context != nullptr) doc["context"] = context;

  String out;
  serializeJson(doc, out);
  ws.send(out);
  Serial.println("Evento enviado: " + out);
}
