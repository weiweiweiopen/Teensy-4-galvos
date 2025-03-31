#include <Audio.h>
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <SerialFlash.h>

// GUItool: begin automatically generated code
AudioInputUSB            usb1;           //xy=238,256
AudioOutputAnalogStereo  dacs1;          //xy=520,282
AudioConnection          patchCord1(usb1, 0, dacs1, 0);
AudioConnection          patchCord2(usb1, 1, dacs1, 1);
AudioControlSGTL5000     sgtl5000_1;     //xy=367,478
// GUItool: end automatically generated code

void setup() {
  AudioMemory(50);
  sgtl5000_1.enable();
  sgtl5000_1.volume(0.5); // Set volume (range: 0.0 to 1.0)
}

void loop() {
  // Main loop remains empty since USB audio is automatically processed
}
