# Teensy-4-galvos

DIY laser galvanometer projector tools for Teensy 4.1, Max/MSP, and Python-based XY path generation. The system was developed for the [Laser Dye Project](https://shihweichieh.com/Laser-Dye-Project), but it can also be used for engraving, PCB work, and audio-visual experiments.

## What is in this repo

- `src/`: Teensy firmware
- `max/`: Max/MSP patches for playback and control
- `python/`: image/text to XY waveform tools
- `kicad/`: hardware design files

## Quick Start

1. Clone the repository.
2. Flash the Teensy 4.1 firmware from `src/`.
3. Open the Max patch in `max/` and select the Teensy audio device.
4. Use the Python tools in `python/` if you want to generate XY WAV files from images or text.

## Python Tools

The main GUI app is `python/ld_stippling_qt.py`.

Setup:

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
