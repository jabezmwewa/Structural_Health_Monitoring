#include <DHT.h>

#define DHTPIN 22
#define DHTTYPE DHT11


DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(9600);
  Serial.println("DHT11 Sensor Test Code");

  dht.begin();
}

void loop() {
 
  delay(5000);
  float humidity = dht.readHumidity();
  float temperature = dht.readTemperature();

  
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("Failed to read from DHT11 sensor!");
    return;
  }

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" °C");

  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");

  Serial.println("----------------------");
}