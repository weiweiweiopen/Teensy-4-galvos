# Teensy-4-galvos
This DIY laser galvonometer projector was originally designed for [Laser Dye Project](https://shihweichieh.com/Laser-Dye-Project) to develop New Cyanotype and Vandyke brown images on sewn garments masklessly. It is also capable for other conventional application like engraving, PCB etching or audio visual performace. The software interface is made with max/msp and teensy code, and the protocol is based on pure audio synthesis, not by ILDA, however the hardware is compatible with ILDA connectors and software too.

# The amplifier board
The amplifier board is simply used for converting the output of teensy audio adaptor board to differential signals to adapt the +/- 5V inputs of the galvonometer system. For more details of ILDA differential signals please visit the references.
<img src="https://github.com/user-attachments/assets/9e69c03e-9d29-4196-98c8-8e4a2a3f8d71" width="500"></br>

<img src="https://github.com/user-attachments/assets/c8d95678-d485-42c2-aee1-a79e7517e275" width="500">
<img src="https://github.com/user-attachments/assets/a81763fa-8f1b-4860-bc4b-4d1afd21970e" width="500"> 
<img src="https://github.com/user-attachments/assets/c126f6e9-4923-4cae-8264-216de1f0bb26" width="500">
<img src="https://github.com/user-attachments/assets/3dfa0f24-51fe-43d1-969c-83ab22fda4b4" width="500">
</br>Figure 1. Teensy 4.1 connected to the differential amplifier board.</br></br>

# Laser Dye Project
<img src="https://github.com/user-attachments/assets/0fd4f6e0-4eee-4ea7-8569-28a9c2438982" width="500">
<img src="https://github.com/user-attachments/assets/8f97b4e0-cdf2-4f4b-bba7-526ff108df4f" width="500">
</br>Figure 2. The projection and the process of 405nm laser scanning.</br></br>

<img src="https://github.com/user-attachments/assets/e090b024-9602-4216-9291-1efe46ce2832" width="500">
<img src="https://github.com/user-attachments/assets/ed6fc365-e28f-417f-8c8d-286755ae4b2a" width="500">
</br>Figure 3. The closeup of the developed textile or garment.</br></br>

# Installation
1. Clone this repository or download the zip files:  
   ```bash
   git clone https://github.com/shihweichieh2023/LaserDyeProject.git
2. Upload the .ino file to teensy 4.0 that is connected to teensy audio adaptor board.
4. Open Max/MSP and load the .maxpat patches.
</br><img src="https://github.com/user-attachments/assets/0b9dec41-2fbd-4026-80cc-728aa95d1c10" width="200"><img src="https://github.com/user-attachments/assets/30cbdc99-58ab-4cc6-96c7-ae5199936e60" width="200"></br>
4. Open "audio status" window in the top menu bar, select "Teensy audio" as output device.


# References
1. [ILDA signal hacking](https://github.com/ffd8/dac_ilda)
2. [Laser Dye Project book](https://archive.org/details/laser-dye-if-time-was-wearable-and-foldable-curatior-and-artist)
3. [Laser Dye Project video](https://shihweichieh.com/Laser-Dye-Project)
4. [axoloti laser amp board](https://github.com/dusjagr/Axoloti_Laser_Interface)
