# Python Tools

Small GUI tools for turning images or text into XY laser paths.

## Main Files

- `ld_stippling_qt.py`: image to XY preview/export app
- `ld_text_outline_qt.py`: text outline to XY export app
- `ld_pathopt_xy.py`: shared sampling and path-optimization code

## Setup

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements.txt
```

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r python\requirements.txt
```

## Run

```bash
python python/ld_stippling_qt.py
python python/ld_text_outline_qt.py
```

## Notes

- Use native Windows Python for audio output; WSL may not detect the laser audio device correctly.
- `scipy` is important for fast Voronoi rendering on large images.
- `sounddevice` is only needed for live playback from the GUI.
- Keep `ld_stippling_qt.py` and `ld_pathopt_xy.py` in the same folder.
