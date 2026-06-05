# Teensy-4-galvos

DIY laser galvanometer projector tools for Teensy 4.0, Max/MSP, and Python-based XY path generation. The system was developed for the [Laser Dye Project](https://shihweichieh.com/Laser-Dye-Project), but it can also be used for engraving, PCB work, and audio-visual experiments.

![2025-10-28T01-01-20 830Z-IMG_3341](https://github.com/user-attachments/assets/c29f5953-d863-4279-983b-8799ac718b67)
![2025-10-28T01-01-20 830Z-IMG_3347](https://github.com/user-attachments/assets/3177fca0-fad8-4d90-86a6-e4fa18566fc6)

## Quick Start

1. Clone the repository.
2. Flash the Teensy 4.0 firmware from `src/`.
3. Open the Max patch in `max/` and select the Teensy audio device. Or use the Python tools in `python/`.

## Python Tools

The main GUI app is `python/ld_stippling_qt.py`.

Setup on Mac and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements.txt
python python/ld_stippling_qt.py
```

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r python\requirements.txt
python python\ld_stippling_qt.py
```

Notes:

- Use native Windows Python for audio output; WSL may not see the laser audio device correctly.
- `scipy` is recommended for fast Voronoi rendering on large images.
- `sounddevice` is only needed for direct audio playback from the Python GUI.

you may purchase the ready made machine here: https://weiweiweishop2.myshopify.com/
