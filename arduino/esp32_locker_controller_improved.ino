#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>

// ————— Ajustes generales —————
const char* SSID       = "FAM TITO";
const char* PASSWORD   = "Max17Conny10";
const String BASE_URL  = "http://192.168.100.6:8000";  // IP de tu PC (backend)
const int   LOCKER_ID  = 1;

// Pines
constexpr int PIN_TRIG  = 5;
constexpr int PIN_ECHO  = 18;
constexpr int PIN_SERVO = 13;

// Parámetros de tiempos (ms)
constexpr unsigned long STORE_TIMEOUT   = 5'000;   // 5 s para colocar/retirar
constexpr unsigned long CLOSE_DELAY     = 3'000;   // 3 s antes de cerrar
constexpr unsigned long DEBOUNCE_PERIOD = 100;     // 0.1 s entre lecturas

WiFiServer server(80);
Servo      servoMotor;

// Máquina de estados
enum State { IDLE, OPEN_WAIT_STORE, OPEN_WAIT_CLOSE };
State state     = IDLE;
bool  modeStore = true;  // true = store / false = retrieve

// Deadlines y contadores
unsigned long storeDeadline   = 0;
unsigned long closeDeadline   = 0;
unsigned long lastPrintStore  = 0;
int          prevSecsStore    = -1;
unsigned long lastPrintClose  = 0;
int          prevSecsClose    = -1;

// Detección de objetos
float lastDistance   = -1;
bool  objectDetected = false;

void setup() {
  Serial.begin(115200);
  delay(200);
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Conectando Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
    Serial.print(".");
    yield();
  }
  Serial.println("\nWi-Fi conectada, IP: " + WiFi.localIP().toString());
  server.begin();
  Serial.println("HTTP endpoint: POST /actuate");
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  servoMotor.attach(PIN_SERVO);
  servoMotor.write(0);
  Serial.println("Listo. Estado = IDLE");
}

void loop() {
  handleHttp();
  runStateMachine();
}

void handleHttp() {
  WiFiClient client = server.available();
  if (!client) return;

  String req = client.readStringUntil('\r');
  client.readStringUntil('\n');
  int len = 0;
  while (true) {
    String h = client.readStringUntil('\r');
    client.readStringUntil('\n');
    if (h.startsWith("Content-Length:")) len = h.substring(15).toInt();
    if (h.isEmpty()) break;
    yield();
  }

  if (req.startsWith("POST /actuate") && len > 0) {
    String body; body.reserve(len);
    while ((int)body.length() < len) {
      if (client.available()) body += char(client.read());
      yield();
    }
    bool open = parseOpen(body);
    modeStore  = (parseMode(body) == "store");
    Serial.printf("✉️ /actuate open=%d mode=%s\n",
                  open, modeStore ? "store" : "retrieve");
    if (open) {
      onOpen();
      client.print("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
                   "{\"status\":\"opening\"}");
    } else {
      onClose();
      client.print("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
                   "{\"status\":\"closing\"}");
    }
  } else {
    client.print("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n"
                 "Locker Controller\n"
                 "Estado: " + stateToString(state) + "\n"
                 "Modo: " + String(modeStore?"store":"retrieve") + "\n");
  }
  delay(1);
  client.stop();
}

bool parseOpen(const String& b) {
  int i = b.indexOf("\"open\"");
  if (i<0) return false;
  int c = b.indexOf(':', i), cm = b.indexOf(',', c);
  String v = b.substring(c+1, cm); v.trim();
  return v.equalsIgnoreCase("true");
}

String parseMode(const String& b) {
  int i = b.indexOf("\"mode\"");
  if (i<0) return "store";
  int c = b.indexOf(':', i);
  int q1= b.indexOf('"', c+1), q2= b.indexOf('"', q1+1);
  return (q1<0||q2<=q1) ? "store" : b.substring(q1+1, q2);
}

String stateToString(State s) {
  switch(s) {
    case IDLE:            return "IDLE";
    case OPEN_WAIT_STORE: return "OPEN_WAIT_STORE";
    case OPEN_WAIT_CLOSE: return "OPEN_WAIT_CLOSE";
  }
  return "UNK";
}

void onOpen() {
  servoMotor.write(180);
  storeDeadline  = millis() + STORE_TIMEOUT;
  lastPrintStore = 0; prevSecsStore = -1;
  objectDetected = false;
  state = OPEN_WAIT_STORE;
  Serial.printf("⬆️ Apertura: %lus timeout\n", STORE_TIMEOUT/1000);
}

void onClose() {
  servoMotor.write(0);
  state = IDLE;
  Serial.println("✖️ Cierre forzado -> IDLE");
}

void runStateMachine() {
  yield();
  unsigned long now = millis();
  switch(state) {
    case OPEN_WAIT_STORE: {
      int secs = (storeDeadline>now)?(int)((storeDeadline-now+999)/1000):0;
      if (secs!=prevSecsStore && now-lastPrintStore>=1000) {
        prevSecsStore=secs; lastPrintStore=now;
        Serial.printf("⏳ %ds restantes\n", secs);
      }
      // Reinicia timeout si hay movimiento o presencia continua
      if (detectObjectChange() || hasObject()) {
        storeDeadline = now + STORE_TIMEOUT;
        Serial.println("↺ Reinicio timeout STORE");
      }
      // Si expira, pasar a cerrar
      if (now>=storeDeadline) {
        Serial.println("⌛ Timeout store, preparando cierre");
        prepareClose(now);
      }
      break;
    }

    case OPEN_WAIT_CLOSE: {
      int secs = (closeDeadline>now)?(int)((closeDeadline-now+999)/1000):0;
      if (secs!=prevSecsClose && now-lastPrintClose>=1000) {
        prevSecsClose=secs; lastPrintClose=now;
        Serial.printf("🔒 Cierra en %ds\n", secs);
      }
      if (now>=closeDeadline) {
        // Cierre rápido y suave
        for (int a=180; a>=0; --a) {
          servoMotor.write(a);
          delay(10);  // más rápido
          yield();
        }
        Serial.println("✅ Cierre completo");
        // Ya no notificamos al backend, esto lo hace el backend automáticamente
        state=IDLE;
      }
      break;
    }

    case IDLE:
    default:
      break;
  }
}

void prepareClose(unsigned long now) {
  closeDeadline  = now + CLOSE_DELAY;
  lastPrintClose = 0; prevSecsClose = -1;
  state = OPEN_WAIT_CLOSE;
  Serial.printf("⏲️ Preparando cierre %lus\n", CLOSE_DELAY/1000);
}

bool detectObjectChange() {
  static unsigned long lastChk=0;
  if (millis()-lastChk<DEBOUNCE_PERIOD) return false;
  lastChk=millis();
  float sum=0; int cnt=0;
  for (int i=0;i<3;++i) {
    float d=measureDistance();
    if (d>0) { sum+=d; cnt++; }
    delay(10); yield();
  }
  if (!cnt) return false;
  float avg=sum/cnt;
  float ch=fabs(avg-lastDistance);
  lastDistance=avg;
  Serial.printf("📏 Dist:%.2f Δ=%.2f\n", avg, ch);
  return ch>1.0;
}

bool hasObject() {
  float sum=0; int cnt=0;
  for (int i=0;i<3;++i) {
    float d=measureDistance();
    if (d>0) { sum+=d; cnt++; }
    delay(10); yield();
  }
  if (!cnt) return false;
  float avg=sum/cnt;
  Serial.printf("📊 Prom:%.2f -> %s\n",
                avg, (avg>0 && avg<15)?"OBJ":"S/OBJ");
  return (avg>0 && avg<15);
}

float measureDistance() {
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur=pulseIn(PIN_ECHO, HIGH, 25000);
  return (dur>0)?(dur*0.0343f)/2.0f:-1;
}
