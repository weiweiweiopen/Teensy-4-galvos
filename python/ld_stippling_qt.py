#!/usr/bin/env python3
"""PySide6/Qt version of ld_stippling.

Integrated features:
- input image
- contrast toggle/amount
- downsample toggle/step
- stippling method (voronoi/poisson/random)
- dots number, voronoi iterations/lerp, pixel step, aspect mode
- path lines preview toggle
- 2ch XY wav export
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import wave

import numpy as np
from PIL import Image

from ld_pathopt_xy import (
    sample_weighted_dots,
    weighted_voronoi_stipple_points,
    poisson_disk_stipple_points,
    nearest_neighbor_order,
    apply_aspect_fit,
    resample_to_length,
)

from PySide6 import QtCore, QtGui, QtWidgets

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None


def apply_contrast(gray01: np.ndarray, enabled: bool, amount: float) -> np.ndarray:
    if not enabled:
        return gray01
    c = max(0.0, amount)
    return np.clip((gray01 - 0.5) * c + 0.5, 0.0, 1.0)


def load_ink_with_controls(
    image_path: Path,
    use_downsample: bool,
    downsample_step: int,
    use_contrast: bool,
    contrast_amount: float,
) -> np.ndarray:
    img = Image.open(image_path).convert("L")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = apply_contrast(arr, use_contrast, contrast_amount)
    if use_downsample:
        step = max(1, int(downsample_step))
        arr = arr[::step, ::step]
    return 1.0 - arr


def write_xy_wav(path: Path, x: np.ndarray, y: np.ndarray, sr: int) -> None:
    sig = np.stack([x, y], axis=1)
    sig = np.clip(sig, -1.0, 1.0)
    pcm = (sig * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


@dataclass
class RenderResult:
    image_size: tuple[int, int]
    points_px: np.ndarray
    x: np.ndarray
    y: np.ndarray
    contour_points: int
    actual_points_per_sec: float


@dataclass
class XYBuffer:
    data: np.ndarray
    sample_rate: int


def compute_xy_for_image(image_path: Path, p: dict) -> RenderResult:
    ink = load_ink_with_controls(
        image_path,
        use_downsample=p["use_downsample"],
        downsample_step=p["downsample_step"],
        use_contrast=p["use_contrast"],
        contrast_amount=p["contrast_amount"],
    )
    h, w = ink.shape

    method = p["method"]
    if method == "voronoi":
        points = weighted_voronoi_stipple_points(
            ink,
            dots_number=p["dots_number"],
            density=p["density"],
            tone_gamma=p["tone_gamma"],
            tone_floor=p["tone_floor"],
            seed=p["seed"],
            pixel_step=p["pixel_step"],
            iterations=p["voronoi_iterations"],
            lerp=p["voronoi_lerp"],
        )
    elif method == "poisson":
        points = poisson_disk_stipple_points(
            ink,
            dots_number=p["dots_number"],
            density=p["density"],
            tone_gamma=p["tone_gamma"],
            tone_floor=p["tone_floor"],
            seed=p["seed"],
            min_dist=p["poisson_min_dist"],
            attempts=p["poisson_attempts"],
        )
    else:
        points = sample_weighted_dots(
            ink,
            dots_number=p["dots_number"],
            density=p["density"],
            tone_gamma=p["tone_gamma"],
            tone_floor=p["tone_floor"],
            seed=p["seed"],
            pixel_step=p["pixel_step"],
        )

    if p["optimize_path"]:
        start = int(np.argmin(points[:, 0] + points[:, 1]))
        points = points[nearest_neighbor_order(points, start_index=start)]

    if p["dot_dwell"] > 1:
        points = np.repeat(points, p["dot_dwell"], axis=0)

    contour_points = int(points.shape[0])

    x = (2.0 * points[:, 0] / max(w - 1, 1)) - 1.0
    y = 1.0 - (2.0 * points[:, 1] / max(h - 1, 1))
    x, y = apply_aspect_fit(x, y, w, h, mode="fit")

    # Non-integer points/sec mapping for better mathematical accuracy.
    pps = max(1e-6, float(p["points_per_second"]))
    sr = max(1, int(p["sample_rate"]))
    target_len_by_pps = max(1, int(round(contour_points * sr / pps)))
    x, y = resample_to_length(x, y, target_len_by_pps, mode=p["resample_mode"])

    if p["target_seconds"] > 0:
        x, y = resample_to_length(
            x,
            y,
            int(p["target_seconds"] * p["sample_rate"]),
            mode=p["resample_mode"],
        )

    x *= 0.75
    y *= 0.75
    actual_pps = contour_points * sr / max(1, x.shape[0])
    return RenderResult(
        image_size=(w, h),
        points_px=points,
        x=x,
        y=y,
        contour_points=contour_points,
        actual_points_per_sec=actual_pps,
    )


def result_to_xybuffer(result: RenderResult, sample_rate: int) -> XYBuffer:
    n = min(result.x.shape[0], result.y.shape[0])
    data = np.stack([result.x[:n], result.y[:n]], axis=1).astype(np.float32)
    return XYBuffer(data=np.clip(data, -1.0, 1.0), sample_rate=sample_rate)


def make_projection_range(xy: XYBuffer, cycles: int = 40) -> XYBuffer:
    data = xy.data
    xmin = float(np.min(data[:, 0]))
    xmax = float(np.max(data[:, 0]))
    ymin = float(np.min(data[:, 1]))
    ymax = float(np.max(data[:, 1]))

    corners = np.array(
        [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]],
        dtype=np.float32,
    )
    seg_pts = 300
    parts = []
    for i in range(4):
        a = corners[i]
        b = corners[i + 1]
        t = np.linspace(0.0, 1.0, seg_pts, endpoint=False, dtype=np.float32)
        parts.append(a[None, :] + (b - a)[None, :] * t[:, None])
    loop = np.concatenate(parts + [corners[:1]], axis=0)
    loop = np.tile(loop, (max(1, int(cycles)), 1))
    return XYBuffer(data=np.clip(loop, -1.0, 1.0), sample_rate=xy.sample_rate)


class RenderWorker(QtCore.QObject):
    finished = QtCore.Signal(object, object, str)

    def __init__(self, image_path: Path, params: dict, preview_size: int):
        super().__init__()
        self.image_path = image_path
        self.params = params
        self.preview_size = preview_size

    @staticmethod
    def _build_preview(result: RenderResult, size: int, show_path: bool) -> QtGui.QImage:
        w, h = result.image_size
        arr = np.full((size, size, 3), 255, dtype=np.uint8)

        pad = 30
        fx0, fy0, fx1, fy1 = (pad, pad, size - pad, size - pad)
        fw, fh = fx1 - fx0, fy1 - fy0
        if w >= h:
            iw = fw
            ih = int(fw * (h / w))
            ix0 = fx0
            iy0 = fy0 + (fh - ih) // 2
        else:
            ih = fh
            iw = int(fh * (w / h))
            ix0 = fx0 + (fw - iw) // 2
            iy0 = fy0

        p = result.points_px
        if p.size > 0:
            xp = ix0 + (p[:, 0] / max(w - 1, 1)) * max(1, iw - 1)
            yp = iy0 + (p[:, 1] / max(h - 1, 1)) * max(1, ih - 1)
            xi = np.clip(np.rint(xp).astype(np.int32), 0, size - 1)
            yi = np.clip(np.rint(yp).astype(np.int32), 0, size - 1)
            arr[yi, xi] = (0, 0, 0)

            if show_path and len(xi) > 1:
                from PIL import ImageDraw

                img = Image.fromarray(arr, mode="RGB")
                draw = ImageDraw.Draw(img)
                max_pts = 2000
                if len(xi) > max_pts:
                    idx = np.linspace(0, len(xi) - 1, max_pts).astype(np.int32)
                    path = list(zip(xi[idx].tolist(), yi[idx].tolist()))
                else:
                    path = list(zip(xi.tolist(), yi.tolist()))
                draw.line(path, fill=(220, 0, 0), width=1)
                arr = np.asarray(img, dtype=np.uint8)

        h0, w0, _ = arr.shape
        return QtGui.QImage(arr.data, w0, h0, 3 * w0, QtGui.QImage.Format.Format_RGB888).copy()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            p = self.params
            result = compute_xy_for_image(self.image_path, p)
            preview = self._build_preview(result, self.preview_size, p["show_path"])
            self.finished.emit(result, preview, "")
        except Exception as exc:
            self.finished.emit(None, None, str(exc))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ld_stippling_qt")
        self.resize(1440, 920)

        self.image_path: Path | None = None
        self.last_result: RenderResult | None = None
        self.render_thread: QtCore.QThread | None = None
        self.worker: RenderWorker | None = None
        self.play_xy: XYBuffer | None = None
        self.range_xy: XYBuffer | None = None
        self.active_xy: XYBuffer | None = None
        self.stream = None
        self.play_index = 0
        self.playing = False
        self.play_mode = "main"

        self._build_ui()
        self._refresh_audio_devices()

        self.cpu_timer = QtCore.QTimer(self)
        self.cpu_timer.timeout.connect(self._tick_audio)
        self.cpu_timer.start(200)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        self.left = QtWidgets.QWidget()
        self.left.setMinimumWidth(360)
        self.left.setMaximumWidth(520)
        form_layout = QtWidgets.QVBoxLayout(self.left)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(10)

        left_scroll = QtWidgets.QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setWidget(self.left)
        splitter.addWidget(left_scroll)

        btn_row1 = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Load Image")
        self.btn_render = QtWidgets.QPushButton("Render Preview")
        btn_row1.addWidget(self.btn_load)
        btn_row1.addWidget(self.btn_render)
        form_layout.addLayout(btn_row1)

        btn_row2 = QtWidgets.QHBoxLayout()
        self.btn_export = QtWidgets.QPushButton("Export WAV")
        self.btn_save_preview = QtWidgets.QPushButton("Save Preview PNG")
        btn_row2.addWidget(self.btn_export)
        btn_row2.addWidget(self.btn_save_preview)
        form_layout.addLayout(btn_row2)

        audio_top = QtWidgets.QHBoxLayout()
        self.power = QtWidgets.QPushButton("Power")
        self.power.setCheckable(True)
        self.power.setChecked(False)
        self.cpu_label = QtWidgets.QLabel("CPU 0.0%")
        audio_top.addWidget(self.power)
        audio_top.addStretch(1)
        audio_top.addWidget(self.cpu_label)
        form_layout.addLayout(audio_top)

        audio_form = QtWidgets.QFormLayout()
        self.driver = QtWidgets.QLabel("PortAudio" if sd is not None else "Unavailable")
        self.device_combo = QtWidgets.QComboBox()
        self.refresh_audio_btn = QtWidgets.QPushButton("Refresh Audio")
        self.audio_sample_rate = QtWidgets.QSpinBox(); self.audio_sample_rate.setRange(8000, 192000); self.audio_sample_rate.setValue(44100)
        self.block_size = QtWidgets.QSpinBox(); self.block_size.setRange(0, 4096); self.block_size.setValue(512)
        self.out_ch1 = QtWidgets.QSpinBox(); self.out_ch1.setRange(1, 64); self.out_ch1.setValue(1)
        self.out_ch2 = QtWidgets.QSpinBox(); self.out_ch2.setRange(1, 64); self.out_ch2.setValue(2)
        audio_form.addRow("Driver", self.driver)
        audio_form.addRow("Output Device", self.device_combo)
        audio_form.addRow("", self.refresh_audio_btn)
        audio_form.addRow("Audio Rate", self.audio_sample_rate)
        audio_form.addRow("I/O Vector Size", self.block_size)
        audio_form.addRow("Output Ch 1", self.out_ch1)
        audio_form.addRow("Output Ch 2", self.out_ch2)
        form_layout.addLayout(audio_form)

        audio_btns = QtWidgets.QHBoxLayout()
        self.btn_projection = QtWidgets.QPushButton("Projection Range")
        self.btn_play = QtWidgets.QPushButton("Play")
        self.btn_stop = QtWidgets.QPushButton("Stop")
        audio_btns.addWidget(self.btn_projection)
        audio_btns.addWidget(self.btn_play)
        audio_btns.addWidget(self.btn_stop)
        form_layout.addLayout(audio_btns)

        btn_row3 = QtWidgets.QHBoxLayout()
        self.btn_save_params = QtWidgets.QPushButton("Save Params")
        self.btn_load_params = QtWidgets.QPushButton("Load Params")
        btn_row3.addWidget(self.btn_save_params)
        btn_row3.addWidget(self.btn_load_params)
        form_layout.addLayout(btn_row3)

        btn_row4 = QtWidgets.QHBoxLayout()
        self.btn_batch = QtWidgets.QPushButton("Batch Export")
        self.btn_preset_fast = QtWidgets.QPushButton("Preset: Fast")
        self.btn_preset_detail = QtWidgets.QPushButton("Preset: Detail")
        self.btn_preset_safe = QtWidgets.QPushButton("Preset: Laser-safe")
        btn_row4.addWidget(self.btn_batch)
        form_layout.addLayout(btn_row4)

        btn_row5 = QtWidgets.QHBoxLayout()
        btn_row5.addWidget(self.btn_preset_fast)
        btn_row5.addWidget(self.btn_preset_detail)
        btn_row5.addWidget(self.btn_preset_safe)
        form_layout.addLayout(btn_row5)

        self.path_label = QtWidgets.QLabel("No image loaded")
        form_layout.addWidget(self.path_label)

        self.controls: dict[str, QtWidgets.QWidget] = {}

        def add_spin(label: str, key: str, minv: int, maxv: int, v: int):
            w = QtWidgets.QSpinBox(); w.setRange(minv, maxv); w.setValue(v)
            self._add_form_row(form_layout, label, w); self.controls[key] = w

        def add_dspin(label: str, key: str, minv: float, maxv: float, v: float, step: float = 0.1):
            w = QtWidgets.QDoubleSpinBox(); w.setRange(minv, maxv); w.setValue(v); w.setSingleStep(step)
            self._add_form_row(form_layout, label, w); self.controls[key] = w

        def add_check(label: str, key: str, v: bool):
            w = QtWidgets.QCheckBox(); w.setChecked(v)
            self._add_form_row(form_layout, label, w); self.controls[key] = w

        def add_combo(label: str, key: str, items: list[str], value: str):
            w = QtWidgets.QComboBox(); w.addItems(items); w.setCurrentText(value)
            self._add_form_row(form_layout, label, w); self.controls[key] = w

        add_combo("Method", "method", ["voronoi", "poisson", "random"], "voronoi")
        add_spin("Dots", "dots_number", 100, 200000, 10000)
        add_dspin("Density", "density", 0.0, 10.0, 1.0, 0.1)
        add_spin("Seed", "seed", 0, 9999999, 0)
        add_check("Use Contrast", "use_contrast", False)
        add_dspin("Contrast", "contrast_amount", 0.1, 5.0, 1.2, 0.1)
        add_check("Use Downsample", "use_downsample", False)
        add_spin("Downsample Step", "downsample_step", 1, 16, 2)
        add_spin("Pixel Step", "pixel_step", 1, 16, 2)
        add_spin("Vor Iter", "voronoi_iterations", 1, 200, 20)
        add_dspin("Vor Lerp", "voronoi_lerp", 0.01, 1.0, 0.2, 0.01)
        add_dspin("Poisson Dist", "poisson_min_dist", 1.0, 50.0, 4.0, 0.5)
        add_spin("Poisson Attempts", "poisson_attempts", 1, 200, 30)
        add_check("Optimize Path", "optimize_path", True)
        add_spin("Sample Rate", "sample_rate", 8000, 192000, 44100)
        add_spin("Points/sec", "points_per_second", 1, 200000, 150)
        add_spin("Dot Dwell", "dot_dwell", 1, 100, 1)
        add_dspin("Target Sec (0=off)", "target_seconds", 0.0, 3600.0, 0.0, 0.1)
        add_combo("Resample", "resample_mode", ["hold", "linear"], "hold")
        add_dspin("Tone Gamma", "tone_gamma", 0.05, 8.0, 1.0, 0.05)
        add_dspin("Tone Floor", "tone_floor", 0.0, 1.0, 0.0, 0.01)
        add_check("Show Path Lines", "show_path", False)

        self.status = QtWidgets.QLabel("Ready")
        self.time_info = QtWidgets.QLabel("Estimated print time: -")
        self.pps_info = QtWidgets.QLabel("Actual points/sec: -")
        self.export_info = QtWidgets.QLabel("Last export: -")
        form_layout.addWidget(self.status)
        form_layout.addWidget(self.time_info)
        form_layout.addWidget(self.pps_info)
        form_layout.addWidget(self.export_info)
        form_layout.addStretch(1)

        self.preview = QtWidgets.QLabel("Preview")
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#ffffff;")
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 1000])

        self.btn_load.clicked.connect(self.on_load)
        self.btn_render.clicked.connect(self.on_render)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_save_preview.clicked.connect(self.on_save_preview)
        self.btn_save_params.clicked.connect(self.on_save_params)
        self.btn_load_params.clicked.connect(self.on_load_params)
        self.btn_batch.clicked.connect(self.on_batch_export)
        self.btn_preset_fast.clicked.connect(lambda: self.apply_preset("fast"))
        self.btn_preset_detail.clicked.connect(lambda: self.apply_preset("detail"))
        self.btn_preset_safe.clicked.connect(lambda: self.apply_preset("safe"))
        self.refresh_audio_btn.clicked.connect(self._refresh_audio_devices)
        self.power.toggled.connect(self._on_power)
        self.btn_projection.clicked.connect(self._start_projection_range)
        self.btn_play.clicked.connect(self._start_playback)
        self.btn_stop.clicked.connect(self._stop_playback)

        self._apply_widget_sizing()

    def _apply_widget_sizing(self) -> None:
        buttons = self.findChildren(QtWidgets.QPushButton)
        for b in buttons:
            b.setMinimumHeight(32)

        combos = self.findChildren(QtWidgets.QComboBox)
        spins = self.findChildren(QtWidgets.QAbstractSpinBox)
        checks = self.findChildren(QtWidgets.QCheckBox)

        for w in combos + spins:
            w.setMinimumHeight(30)
        for w in checks:
            w.setMinimumHeight(24)

    @staticmethod
    def _add_form_row(layout: QtWidgets.QVBoxLayout, label: str, widget: QtWidgets.QWidget) -> None:
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(label))
        row.addWidget(widget, 1)
        layout.addLayout(row)

    def _params(self) -> dict:
        c = self.controls
        return {
            "method": c["method"].currentText(),
            "dots_number": c["dots_number"].value(),
            "density": c["density"].value(),
            "seed": c["seed"].value(),
            "use_contrast": c["use_contrast"].isChecked(),
            "contrast_amount": c["contrast_amount"].value(),
            "use_downsample": c["use_downsample"].isChecked(),
            "downsample_step": c["downsample_step"].value(),
            "pixel_step": c["pixel_step"].value(),
            "voronoi_iterations": c["voronoi_iterations"].value(),
            "voronoi_lerp": c["voronoi_lerp"].value(),
            "poisson_min_dist": c["poisson_min_dist"].value(),
            "poisson_attempts": c["poisson_attempts"].value(),
            "optimize_path": c["optimize_path"].isChecked(),
            "sample_rate": c["sample_rate"].value(),
            "points_per_second": c["points_per_second"].value(),
            "dot_dwell": c["dot_dwell"].value(),
            "target_seconds": c["target_seconds"].value(),
            "resample_mode": c["resample_mode"].currentText(),
            "tone_gamma": c["tone_gamma"].value(),
            "tone_floor": c["tone_floor"].value(),
            "show_path": c["show_path"].isChecked(),
        }

    def _set_busy(self, busy: bool) -> None:
        for w in [
            self.btn_load,
            self.btn_render,
            self.btn_export,
            self.btn_save_preview,
            self.btn_save_params,
            self.btn_load_params,
            self.btn_batch,
            self.btn_preset_fast,
            self.btn_preset_detail,
            self.btn_preset_safe,
        ]:
            w.setEnabled(not busy)

    def _refresh_audio_devices(self) -> None:
        self.device_combo.clear()
        if sd is None:
            self.device_combo.addItem("sounddevice not installed", None)
            return
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_output_channels", 0) > 0:
                self.device_combo.addItem(f"{i}: {d['name']} (out {d['max_output_channels']})", i)

    def _sync_audio_buffers(self) -> bool:
        if self.last_result is None:
            QtWidgets.QMessageBox.information(self, "No render", "Please render preview first")
            return False
        sr = self.controls["sample_rate"].value()
        self.play_xy = result_to_xybuffer(self.last_result, sr)
        self.range_xy = make_projection_range(self.play_xy)
        return True

    def _on_power(self, on: bool) -> None:
        if not on:
            self._stop_playback()

    def _audio_callback(self, outdata, frames, time_info, status):
        if self.active_xy is None or not self.playing:
            outdata.fill(0)
            return

        ch1 = max(1, self.out_ch1.value())
        ch2 = max(1, self.out_ch2.value())
        out_channels = max(ch1, ch2)
        block = np.zeros((frames, out_channels), dtype=np.float32)
        src = self.active_xy.data
        remain = src.shape[0] - self.play_index
        n = min(frames, max(0, remain))

        if n > 0:
            block[:n, ch1 - 1] = src[self.play_index:self.play_index + n, 0]
            block[:n, ch2 - 1] = src[self.play_index:self.play_index + n, 1]
            self.play_index += n

        if n < frames:
            if self.play_mode == "range":
                self.play_index = 0
                remain2 = src.shape[0]
                n2 = min(frames - n, remain2)
                if n2 > 0:
                    block[n:n+n2, ch1 - 1] = src[:n2, 0]
                    block[n:n+n2, ch2 - 1] = src[:n2, 1]
                    self.play_index = n2
            else:
                self.playing = False

        outdata[:] = block

    def _open_stream(self) -> None:
        dev_index = self.device_combo.currentData()
        sr = int(self.audio_sample_rate.value())
        bs = int(self.block_size.value())
        ch1 = max(1, self.out_ch1.value())
        ch2 = max(1, self.out_ch2.value())
        out_channels = max(ch1, ch2)
        self.stream = sd.OutputStream(
            device=dev_index,
            samplerate=sr,
            blocksize=bs,
            channels=out_channels,
            dtype="float32",
            callback=self._audio_callback,
        )
        self.stream.start()

    def _start_projection_range(self) -> None:
        if sd is None:
            QtWidgets.QMessageBox.information(self, "Missing dependency", "Install sounddevice first")
            return
        if not self.power.isChecked():
            QtWidgets.QMessageBox.information(self, "Power off", "Turn Power ON first")
            return
        if not self._sync_audio_buffers():
            return
        self._stop_playback()
        try:
            self.active_xy = self.range_xy
            self.play_mode = "range"
            self.play_index = 0
            self.playing = True
            self._open_stream()
            self.status.setText("Projection Range running")
        except Exception as exc:
            self.playing = False
            QtWidgets.QMessageBox.critical(self, "Audio error", str(exc))

    def _start_playback(self) -> None:
        if sd is None:
            QtWidgets.QMessageBox.information(self, "Missing dependency", "Install sounddevice first")
            return
        if not self.power.isChecked():
            QtWidgets.QMessageBox.information(self, "Power off", "Turn Power ON first")
            return
        if not self._sync_audio_buffers():
            return
        self._stop_playback()
        try:
            self.active_xy = self.play_xy
            self.play_mode = "main"
            self.play_index = 0
            self.playing = True
            self._open_stream()
            self.status.setText("Playback started")
        except Exception as exc:
            self.playing = False
            QtWidgets.QMessageBox.critical(self, "Audio error", str(exc))

    def _stop_playback(self) -> None:
        self.playing = False
        self.play_mode = "main"
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _tick_audio(self) -> None:
        cpu = 0.0
        if self.stream is not None:
            try:
                cpu = float(self.stream.cpu_load) * 100.0
            except Exception:
                cpu = 0.0
        self.cpu_label.setText(f"CPU {cpu:.1f}%")

    def apply_preset(self, name: str) -> None:
        c = self.controls
        if name == "fast":
            c["method"].setCurrentText("voronoi")
            c["dots_number"].setValue(8000)
            c["density"].setValue(1.0)
            c["pixel_step"].setValue(4)
            c["voronoi_iterations"].setValue(10)
            c["voronoi_lerp"].setValue(0.25)
            c["points_per_second"].setValue(22000)
            c["show_path"].setChecked(False)
        elif name == "detail":
            c["method"].setCurrentText("voronoi")
            c["dots_number"].setValue(30000)
            c["density"].setValue(2.0)
            c["pixel_step"].setValue(1)
            c["voronoi_iterations"].setValue(40)
            c["voronoi_lerp"].setValue(0.15)
            c["points_per_second"].setValue(12000)
            c["show_path"].setChecked(False)
        else:  # safe
            c["method"].setCurrentText("poisson")
            c["dots_number"].setValue(12000)
            c["density"].setValue(1.2)
            c["poisson_min_dist"].setValue(5.0)
            c["pixel_step"].setValue(2)
            c["points_per_second"].setValue(10000)
            c["show_path"].setChecked(False)
        self.status.setText(f"Preset applied: {name}")

    @staticmethod
    def _fmt_hms(sec: float) -> str:
        total = max(0, int(round(sec)))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def on_load(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        self.image_path = Path(path)
        full = str(self.image_path)
        self.path_label.setText(full if len(full) <= 64 else "..." + full[-61:])
        self.status.setText("Image loaded")

    def on_render(self) -> None:
        if self.image_path is None:
            QtWidgets.QMessageBox.information(self, "No image", "Please load an image first")
            return
        params = self._params()
        size = int(min(max(420, self.preview.width() - 20), max(420, self.preview.height() - 20), 1200))

        self._set_busy(True)
        self.status.setText("Rendering...")
        self.preview.setText("Rendering...")
        self.preview.setPixmap(QtGui.QPixmap())

        self.render_thread = QtCore.QThread(self)
        self.worker = RenderWorker(self.image_path, params, size)
        self.worker.moveToThread(self.render_thread)
        self.render_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_render_done)
        self.worker.finished.connect(self.render_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.render_thread.finished.connect(self.render_thread.deleteLater)
        self.render_thread.start()

    @QtCore.Slot(object, object, str)
    def _on_render_done(self, result: object, preview: object, error: str) -> None:
        self._set_busy(False)
        if error:
            QtWidgets.QMessageBox.critical(self, "Render error", error)
            self.status.setText("Render failed")
            return

        self.last_result = result
        self.play_xy = result_to_xybuffer(result, self.controls["sample_rate"].value())
        self.range_xy = make_projection_range(self.play_xy)
        qimg: QtGui.QImage = preview
        pix = QtGui.QPixmap.fromImage(qimg)
        self.preview.setPixmap(pix)
        self.preview.setText("")
        self.status.setText(f"Rendered: points={result.points_px.shape[0]} samples={result.x.shape[0]}")
        self.pps_info.setText(
            f"Actual points/sec: {result.actual_points_per_sec:.2f} (target {self.controls['points_per_second'].value()})"
        )

        if self.controls["target_seconds"].value() <= 0:
            sec = result.x.shape[0] / max(1, self.controls["sample_rate"].value())
            self.time_info.setText(f"Estimated print time: {self._fmt_hms(sec)}")
        else:
            self.time_info.setText("Estimated print time: target-sec mode (forced)")

    def on_export(self) -> None:
        if self.last_result is None:
            QtWidgets.QMessageBox.information(self, "No render", "Please render preview first")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save XY WAV", "ld_stippling.wav", "WAV (*.wav)")
        if not path:
            return
        out = Path(path)
        sr = self.controls["sample_rate"].value()
        write_xy_wav(out, self.last_result.x, self.last_result.y, sr)
        np.savez(out.with_suffix(".npz"), x=self.last_result.x, y=self.last_result.y, sample_rate=sr)
        self.status.setText(f"Saved WAV: {out}")
        total_samples = int(self.last_result.x.shape[0])
        duration_sec = total_samples / max(1, sr)
        self.export_info.setText(
            f"Last export: {total_samples} samples ({duration_sec:.3f} s @ {sr} Hz)"
        )

    def on_save_preview(self) -> None:
        pix = self.preview.pixmap()
        if pix is None or pix.isNull():
            QtWidgets.QMessageBox.information(self, "No preview", "Please render preview first")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Preview", "ld_stippling_preview.png", "PNG (*.png)")
        if not path:
            return
        pix.save(path, "PNG")
        self.status.setText(f"Saved preview: {path}")

    def closeEvent(self, event) -> None:
        self._stop_playback()
        super().closeEvent(event)

    def _set_params(self, params: dict) -> None:
        c = self.controls
        if "method" in params:
            c["method"].setCurrentText(str(params["method"]))
        numeric_keys = [
            "dots_number", "density", "seed", "contrast_amount", "downsample_step", "pixel_step",
            "voronoi_iterations", "voronoi_lerp", "poisson_min_dist", "poisson_attempts", "sample_rate",
            "points_per_second", "dot_dwell", "target_seconds", "tone_gamma", "tone_floor",
        ]
        bool_keys = ["use_contrast", "use_downsample", "optimize_path", "show_path"]
        combo_keys = ["resample_mode"]

        for k in numeric_keys:
            if k in params and k in c:
                w = c[k]
                if isinstance(w, QtWidgets.QSpinBox):
                    w.setValue(int(params[k]))
                else:
                    w.setValue(float(params[k]))
        for k in bool_keys:
            if k in params and k in c:
                c[k].setChecked(bool(params[k]))
        for k in combo_keys:
            if k in params and k in c:
                c[k].setCurrentText(str(params[k]))

    def on_save_params(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Parameters",
            "ld_stippling_params.json",
            "JSON (*.json)",
        )
        if not path:
            return
        params = self._params()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=2)
        self.status.setText(f"Saved params: {path}")

    def on_load_params(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Parameters",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            params = json.load(f)
        self._set_params(params)
        self.status.setText(f"Loaded params: {path}")

    def on_batch_export(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not files:
            return

        out_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not out_dir:
            return

        params = self._params()
        out_root = Path(out_dir)
        progress = QtWidgets.QProgressDialog("Batch exporting...", "Cancel", 0, len(files), self)
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.show()

        done = 0
        for i, fp in enumerate(files, start=1):
            if progress.wasCanceled():
                break
            path = Path(fp)
            progress.setValue(i - 1)
            progress.setLabelText(f"Processing {path.name} ({i}/{len(files)})")
            QtWidgets.QApplication.processEvents()

            try:
                result = compute_xy_for_image(path, params)
                out_wav = out_root / f"{path.stem}_stippling.wav"
                write_xy_wav(out_wav, result.x, result.y, params["sample_rate"])
                np.savez(out_wav.with_suffix(".npz"), x=result.x, y=result.y, sample_rate=params["sample_rate"])
                done += 1
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Batch warning", f"Failed: {path.name}\n{exc}")

        progress.setValue(len(files))
        self.status.setText(f"Batch done: {done}/{len(files)} files")


def main() -> None:
    app = QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
