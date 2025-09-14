#include <Audio.h>
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <SerialFlash.h>

// Audio objects
AudioInputUSB            usbIn;
AudioAnalyzePeak         peakX;
AudioAnalyzePeak         peakY;
AudioOutputI2S           audioOut;
AudioControlSGTL5000     sgtl5000_1;

// Audio connections
AudioConnection c1(usbIn, 0, peakX, 0);
AudioConnection c2(usbIn, 1, peakY, 0);
AudioConnection c3(usbIn, 0, audioOut, 0);
AudioConnection c4(usbIn, 1, audioOut, 1);

const int laserPin = 5;
const float threshold = 0.01;  // Adjust based on noise floor
bool laserActive = false;

void setup() {
  AudioMemory(50);

  pinMode(laserPin, OUTPUT);
  digitalWrite(laserPin, LOW);

  Serial.begin(9600);
  sgtl5000_1.enable();
  sgtl5000_1.volume(0.8);
}

void loop() {
  if (peakX.available() && peakY.available()) {
    float xLevel = peakX.read();
    float yLevel = peakY.read();

    bool audioDetected = (xLevel > threshold || yLevel > threshold);

    if (audioDetected && !laserActive) {
      digitalWrite(laserPin, HIGH); // Laser ON
      laserActive = true;
    }
    else if (!audioDetected && laserActive) {
      digitalWrite(laserPin, LOW);  // Laser OFF
      laserActive = false;
    }
  }
}