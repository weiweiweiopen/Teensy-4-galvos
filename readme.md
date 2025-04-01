# Laser Dye Project
<img src="https://github.com/user-attachments/assets/f038ca3e-6013-47a2-a172-c22516c4ae91" width="500">
<img src="https://github.com/user-attachments/assets/0fd4f6e0-4eee-4ea7-8569-28a9c2438982" width="500">
<img src="https://github.com/user-attachments/assets/157e2703-0284-4cd6-b078-0bb24821dd5d" width="500">

## Description
This DIY laser galvonometer projector was designed for [Laser Dye Project](https://shihweichieh.com/Laser-Dye-Project) to develop New Cyanotype and Vandyke Brown images on sewn garments masklessly. It is also capable for other conventional application like engraving, PCB etching or audio visual performace. This system (hardware and software) is designed by the audio synthesis in max or puredata, not by ILDA protocal.

## Installation
1. Clone this repository or download the zip files:  
   ```bash
   git clone https://github.com/shihweichieh2023/LaserDyeProject.git
2. Upload the .ino file to teensy 4.1. that is connected to teensy audio adaptor board.
4. Open Max/MSP and load the .maxpat patches.

<img width="250" alt="Screenshot 2025-03-31 at 4 45 16 PM" src="https://github.com/user-attachments/assets/30cbdc99-58ab-4cc6-96c7-ae5199936e60"><img width="250" alt="Screenshot 2025-04-01 at 6 45 59 PM" src="https://github.com/user-attachments/assets/0b9dec41-2fbd-4026-80cc-728aa95d1c10">

4. Open "audio status" window in the top menu bar, select "Teensy audio" as output device.
## The amplifier board
The amplifier board is simply used for converting the output of teensy audio adaptor board to differential signals to adapt the +/- 5V inputs of the galvonometer system. For more details of ILDA differential signals please visit the references. 

<img src="https://github.com/user-attachments/assets/08dd317c-af9e-4438-8b58-dd9819970b0c" width="500">

## References
1. [ILDA signal hacking](https://github.com/ffd8/dac_ilda)
2. [Laser Dye Project book](https://archive.org/details/laser-dye-if-time-was-wearable-and-foldable-curatior-and-artist)
3. [Laser Dye Project video](https://shihweichieh.com/Laser-Dye-Project)

