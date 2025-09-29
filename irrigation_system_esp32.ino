#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>

// ===== CONFIG =====
const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
String SERVER_BASE = "http://192.168.1.58:5000";
String API_SCHEDULE  = SERVER_BASE + "/api/schedule";
String API_CONFIG    = SERVER_BASE + "/api/config";
String API_HEARTBEAT = SERVER_BASE + "/api/heartbeat";

const int RELAY_PIN = 26;
const int SWITCH_PIN = 27;  // interruttore fisico
const bool RELAY_ACTIVE_LOW = false;

const unsigned long REFRESH_MS   = 60UL * 1000UL;
const unsigned long HEARTBEAT_MS = 60UL * 1000UL;
unsigned long lastHeartbeat = 0;
unsigned long lastFetch = 0;

bool manualOverride = false;  // se true, comanda lo switch
bool manualState = false;     // stato richiesto dal server

// ===== STRUTTURE =====
struct Schedule {
  int startH, startM, startS;
  int endH, endM, endS;
  int days[7];
  int daysCount;
};

Schedule schedules[10];
int scheduleCount = 0;

// ===== FUNZIONI =====

void setRelay(bool on) {
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(RELAY_PIN, on ? LOW : HIGH);
  } else {
    digitalWrite(RELAY_PIN, on ? HIGH : LOW);
  }
  Serial.printf("Relay %s (pin=%d, active_low=%d)\n", on ? "ON" : "OFF", RELAY_PIN, RELAY_ACTIVE_LOW);
}

void fetchManualRelay() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(SERVER_BASE + "/get_manual_relay");
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(128);
    DeserializationError err = deserializeJson(doc, http.getString());
    if (!err) {
      manualState = doc["state"] | false;
      manualOverride = manualState; // override solo se switch ON
    }
  }
  http.end();
}


bool checkSchedule(Schedule s, struct tm* t){
  int wday = (t->tm_wday == 0 ? 7 : t->tm_wday); // 1=Lun ... 7=Dom
  bool dayMatch = false;
  for(int i=0; i<s.daysCount; i++){
    if(s.days[i] == wday) {
      dayMatch = true;
      break;
    }
  }
  if(!dayMatch) return false;

    int nowSec   = t->tm_hour * 3600 + t->tm_min * 60 + t->tm_sec;
    int startSec = s.startH * 3600 + s.startM * 60 + s.startS;
    int endSec   = s.endH   * 3600 + s.endM * 60 + s.endS;

    return (nowSec >= startSec && nowSec <= endSec);
}

void fetchSchedules() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(API_SCHEDULE);
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(4096);
    DeserializationError err = deserializeJson(doc, http.getStream());
    if (!err) {
      scheduleCount = doc.size() < 10 ? doc.size() : 10;
      for (int i = 0; i < scheduleCount; i++) {
        const char* st = doc[i]["start"];
        const char* en = doc[i]["end"];

        // Parsing con fallback: se non ci sono i secondi → 0
        int sh=0, sm=0, ss=0;
        int eh=0, em=0, es=0;

        if (sscanf(st, "%d:%d:%d", &sh, &sm, &ss) < 2) {
          sscanf(st, "%d:%d", &sh, &sm);
          ss = 0;
        }
        if (sscanf(en, "%d:%d:%d", &eh, &em, &es) < 2) {
          sscanf(en, "%d:%d", &eh, &em);
          es = 0;
        }

        schedules[i].startH = sh;
        schedules[i].startM = sm;
        schedules[i].startS = ss;
        schedules[i].endH   = eh;
        schedules[i].endM   = em;
        schedules[i].endS   = es;

        JsonArray daysArr = doc[i]["days"];
        schedules[i].daysCount = 0;
        for (int d : daysArr) {
          if (schedules[i].daysCount < 7) {
            schedules[i].days[schedules[i].daysCount++] = d;
          }
        }
      }
      Serial.printf("Schedulazioni caricate: %d\n", scheduleCount);
    } else {
      Serial.println("Errore JSON fetchSchedules");
    }
  } else {
    Serial.printf("Errore HTTP fetchSchedules: %d\n", code);
  }
  http.end();
}

void sendHeartbeat(bool relay){
  if(WiFi.status()!=WL_CONNECTED) return;
  HTTPClient http;
  http.begin(API_HEARTBEAT);
  http.addHeader("Content-Type","application/json");

  DynamicJsonDocument doc(256);
  doc["device"] = "ESP32_1";
  doc["ip"] = WiFi.localIP().toString();
  doc["relay_on"] = relay;
  doc["enabled"] = true;

  String payload;
  serializeJson(doc, payload);
  int code = http.POST(payload);
  if(code==200) Serial.println("Heartbeat inviato");
  http.end();
}

bool fetchEnabled() {
  if (WiFi.status() != WL_CONNECTED) return true; // default on se non connesso

  HTTPClient http;
  http.begin(API_CONFIG);
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(256);
    DeserializationError err = deserializeJson(doc, http.getStream());
    if (!err) {
      return doc["enabled"] | false;
    }
  }
  http.end();
  return true; // default on se errore
}


// ===== SETUP & LOOP =====
void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW); // relè spento all'avvio
  pinMode(SWITCH_PIN, INPUT_PULLUP); // interruttore fisico

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connesso");

  configTime(3600, 7200, "pool.ntp.org");

  fetchSchedules();
  lastFetch = millis();
}

void loop() {

  time_t now = time(nullptr);
  struct tm* t = localtime(&now);

  // === Debug giorni e schedulazioni ===
  int wday = (t->tm_wday == 0 ? 7 : t->tm_wday);
  Serial.printf("Oggi è giorno %d (1=Lun..7=Dom)\n", wday);
  for(int i=0; i<scheduleCount; i++){
    Serial.printf("Sched %d: %02d:%02d-%02d:%02d giorni:",
      i,
      schedules[i].startH, schedules[i].startM,
      schedules[i].endH, schedules[i].endM);
    for(int j=0; j<schedules[i].daysCount; j++) {
      Serial.printf(" %d", schedules[i].days[j]);
    }
    Serial.println();
  }

  bool switchOn = (digitalRead(SWITCH_PIN) == LOW); // chiuso = ON
  bool active = false;

  if (switchOn) {
    // Interruttore fisico ON → forza relè ON
    active = true;
    Serial.println("Interruttore fisico: RELAY ON (forzato)");
  } else {

    fetchManualRelay();  // <-- aggiorna lo stato dello switch

    bool enabled = fetchEnabled();

    if (manualOverride) {
      active = manualState;   // se switch attivo → forzato
    } else if (enabled) {
      for (int i = 0; i < scheduleCount; i++) {
        active |= checkSchedule(schedules[i], t);
      }
    }
  }

  Serial.printf("Attivo? %d (ora=%02d:%02d)\n", active, t->tm_hour, t->tm_min);

  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? !active : active);

  if(millis() - lastHeartbeat > HEARTBEAT_MS){
    sendHeartbeat(active);
    lastHeartbeat = millis();
  }

  if(millis() - lastFetch > REFRESH_MS){
    fetchSchedules();
    lastFetch = millis();
  }

  delay(2000);
}
