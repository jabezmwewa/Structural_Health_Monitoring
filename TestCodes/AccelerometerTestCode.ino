#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>


Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

void setup() {
  Serial.begin(9600);

  Serial.println("ADXL345 Accelerometer Test");

  if (!accel.begin()) {
    Serial.println("Could not find a valid ADXL345 sensor!");
    while (1);
  }

  
  accel.setRange(ADXL345_RANGE_16_G);

  Serial.println("Sensor initialized successfully.");
}

void loop() {
  sensors_event_t event;
  accel.getEvent(&event);

  Serial.print("X: ");
  Serial.print(event.acceleration.x);
  Serial.print(" m/s^2\t");

  Serial.print("Y: ");
  Serial.print(event.acceleration.y);
  Serial.print(" m/s^2\t");

  Serial.print("Z: ");
  Serial.print(event.acceleration.z);
  Serial.println(" m/s^2");

  Serial.println("---------------------------");

  delay(5000);
}