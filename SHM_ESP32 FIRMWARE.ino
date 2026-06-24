/*
=================================================
SHM ESP32 Client
=================================================
Sensors:
- DHT22 -> Temperature, Humidity
  "strain": 0.0,
  "temperature": 28.5,
  "humidity": 65.4,
  "pressure": 101.2,
  "vibration": 0.0
}
=================================================
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include "HX711.h"

// =====================================
// WIFI SETTINGS
// =====================================
const char* WIFI_SSID = "UNCLEMECHATRON 7480";
const char* WIFI_PASSWORD = "123456789";

// =====================================
// FLASK SERVER
// =====================================
const char* SERVER_URL =
  "http://192.168.137.147:2000/api/data";

// =====================================
// DHT22
// =====================================
#define DHTPIN 4
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);

// =====================================
// HX711
// =====================================
#define HX711_DOUT 18
#define HX711_SCK 19

HX711 scale;

// Calibration factor
// Adjust after calibration
float calibration_factor = 2280.0;

// =====================================
// SW420
// =====================================
#define SW420_PIN 15

// =====================================
// TIMING
// =====================================
unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 10000;

// =====================================
// WIFI CONNECTION
// =====================================
void connectWiFi()
{
  Serial.print("Connecting to WiFi");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi Connected");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

// =====================================
// SETUP
// =====================================
void setup()
{
  Serial.begin(115200);

  delay(1000);

  dht.begin();

  pinMode(SW420_PIN, INPUT);

  // HX711 Setup
  scale.begin(HX711_DOUT, HX711_SCK);

  scale.set_scale(calibration_factor);

  Serial.println("Taring scale...");
  scale.tare();
  Serial.println("Scale ready.");

  connectWiFi();
}

// =====================================
// LOOP
// =====================================
void loop()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("WiFi disconnected.");
    connectWiFi();
  }

  if (millis() - lastSendTime >= SEND_INTERVAL)
  {
    lastSendTime = millis();

    sendSensorData();
  }
}

// =====================================
// SEND DATA
// =====================================
void sendSensorData()
{
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity))
  {
    
    temperature = 0.0;
    humidity = 0.0;
  }

  // ---------------------------------
  // STRAIN PLACEHOLDER
  // ---------------------------------
  float strain = 0.0;

  // ---------------------------------
  // PRESSURE FROM HX711
  // ---------------------------------
  float pressure = 100.0;

  if (scale.is_ready())
  {
    pressure = scale.get_units(5);

    // Optional offset adjustment
    pressure += 100.0;

    if (pressure < 0)
      pressure = 0;
  }
  else
  {
    pressure = 6;
  }

  // ---------------------------------
  // VIBRATION
  // ---------------------------------
  int vibrationState = digitalRead(SW420_PIN);

  float vibration;

  if (vibrationState == HIGH)
  {
    vibration = 20.0;
  }
  else
  {
    vibration = 0.0;
  }

  // ---------------------------------
  // CREATE JSON
  // ---------------------------------
  StaticJsonDocument<256> doc;

  doc["strain"] = strain;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["pressure"] = pressure;
  doc["vibration"] = vibration;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  Serial.println("--------------------------------");
  Serial.println("Sending JSON:");
  Serial.println(jsonPayload);
  Serial.println("--------------------------------");

  HTTPClient http;

  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  int httpResponseCode = http.POST(jsonPayload);

  if (httpResponseCode > 0)
  {
    Serial.print("HTTP Response: ");
    Serial.println(httpResponseCode);

    String response = http.getString();

    Serial.println("Server Reply:");
    Serial.println(response);
  }
  else
  {
    Serial.print("POST Error: ");
    Serial.println(http.errorToString(httpResponseCode));
  }

  http.end();
}