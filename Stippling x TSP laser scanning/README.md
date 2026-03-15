# Minimal Vibe Model

This folder now keeps only the current Python tools that matter for the laser galvo workflow.

## Kept tools

- `ld_stippling_qt.py`: main image-to-XY stippling app with preview, export, and playback controls
- `ld_pathopt_xy.py`: shared path/stipple algorithm module used by the stippling app
- `ld_text_outline_qt.py`: text-to-outline XY export tool

## What each tool is for

### `ld_stippling_qt.py`

Use this for image-based laser drawing.

Features:

- load bitmap images
- generate stipple points with `voronoi`, `poisson`, or `random`
- optional path optimization
- preview the point cloud and draw order
- export 2-channel XY WAV
- direct playback controls for hardware testing

Run:

```bash
python3 minimal_vibe_model/ld_stippling_qt.py
```

Dependencies:

- `numpy`
- `Pillow`
- `PySide6`
- `scipy`
- optional: `sounddevice`

### `ld_pathopt_xy.py`

This is the shared algorithm layer behind the image stippling workflow.

It contains:

- weighted image sampling
- Voronoi stippling
- Poisson-disk stippling
- nearest-neighbor path ordering
- aspect fitting
- XY resampling helpers

`ld_stippling_qt.py` imports this file directly, so keep both files together.

### `ld_text_outline_qt.py`

Use this for text-based laser drawing.

Features:

- choose a font
- enter multiline text
- convert glyphs to outlines
- optimize contour ordering
- export 2-channel XY WAV

Run:

```bash
python3 minimal_vibe_model/ld_text_outline_qt.py
```

Dependencies:

- `numpy`
- `Pillow`
- `PySide6`

## Notes

- The old Tk GUI, wrapper scripts, and earlier prototype files were removed.
- If you move these files, keep `ld_stippling_qt.py` and `ld_pathopt_xy.py` in the same folder unless you also update the import path.
- Generated outputs like `.wav`, `.npz`, and cache folders should not be committed unless they are intentional examples.
