#!/usr/bin/env python3
"""Text outline laser app (PySide6).

- Select font
- Enter multiline text
- Convert glyphs to outlines
- Trace outlines with shortest-path ordering across contours
- Export 2ch XY WAV
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import wave

import numpy as np

try:
    from PIL import Image
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: Pillow. Install with `python3 -m pip install -r python/requirements.txt`."
    ) from exc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: PySide6. Install with `python3 -m pip install -r python/requirements.txt`."
    ) from exc

DEFAULT_FONT_SIZE = 96.0


def write_xy_wav(path: Path, x: np.ndarray, y: np.ndarray, sr: int) -> None:
    sig = np.stack([x, y], axis=1)
    sig = np.clip(sig, -1.0, 1.0)
    pcm = (sig * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def apply_aspect_fit(x: np.ndarray, y: np.ndarray, w: float, h: float, mode: str) -> tuple[np.ndarray, np.ndarray]:
    if mode == "fill":
        return x, y
    if w > h and w > 0:
        y = y * (h / w)
    elif h > w and h > 0:
        x = x * (w / h)
    return x, y


def resample_to_length(x: np.ndarray, y: np.ndarray, target_len: int, mode: str) -> tuple[np.ndarray, np.ndarray]:
    if target_len <= 1 or x.shape[0] == target_len:
        return x, y
    if mode == "hold":
        idx = np.floor(np.linspace(0, x.shape[0] - 1, target_len)).astype(np.int64)
        return x[idx], y[idx]
    src_t = np.linspace(0.0, 1.0, x.shape[0], endpoint=True)
    dst_t = np.linspace(0.0, 1.0, target_len, endpoint=True)
    return np.interp(dst_t, src_t, x), np.interp(dst_t, src_t, y)


def contour_from_polygon(poly: QtGui.QPolygonF) -> np.ndarray:
    pts = np.array([[p.x(), p.y()] for p in poly], dtype=np.float32)
    if pts.shape[0] < 3:
        return np.empty((0, 2), dtype=np.float32)
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts


def densify_closed_contour(contour: np.ndarray, spacing: float) -> np.ndarray:
    if contour.shape[0] < 2:
        return contour
    s = max(0.2, float(spacing))
    out = []
    n = contour.shape[0]
    for i in range(n):
        a = contour[i]
        b = contour[(i + 1) % n]
        seg = b - a
        dist = float(np.linalg.norm(seg))
        if dist < 1e-9:
            continue
        steps = max(1, int(np.ceil(dist / s)))
        t = np.linspace(0.0, 1.0, steps, endpoint=False, dtype=np.float32)
        pts = a[None, :] + t[:, None] * seg[None, :]
        out.append(pts)
    if not out:
        return contour
    dense = np.concatenate(out, axis=0)
    dense = np.concatenate([dense, dense[:1]], axis=0)
    return dense


def choose_start_and_direction(contour: np.ndarray, cur: np.ndarray) -> np.ndarray:
    # For closed contour: choose nearest start index; compare cw/ccw for local smoothness.
    d2 = np.sum((contour - cur) ** 2, axis=1)
    idx = int(np.argmin(d2))

    cw = np.concatenate([contour[idx:], contour[:idx], contour[idx:idx+1]], axis=0)
    ccw_base = contour[::-1]
    d2r = np.sum((ccw_base - cur) ** 2, axis=1)
    idxr = int(np.argmin(d2r))
    ccw = np.concatenate([ccw_base[idxr:], ccw_base[:idxr], ccw_base[idxr:idxr+1]], axis=0)

    if cw.shape[0] < 2:
        return cw
    score_cw = np.sum((cw[1] - cur) ** 2)
    score_ccw = np.sum((ccw[1] - cur) ** 2)
    return cw if score_cw <= score_ccw else ccw


def order_contours_shortest(contours: list[np.ndarray]) -> np.ndarray:
    if not contours:
        return np.empty((0, 2), dtype=np.float32)

    remaining = [c for c in contours if c.shape[0] > 1]
    if not remaining:
        return np.empty((0, 2), dtype=np.float32)

    # Start from top-left-ish contour anchor.
    anchors = np.array([c[np.argmin(c[:, 0] + c[:, 1])] for c in remaining], dtype=np.float32)
    start_i = int(np.argmin(np.sum(anchors, axis=1)))

    path_parts: list[np.ndarray] = []
    cur = anchors[start_i]
    chosen = choose_start_and_direction(remaining.pop(start_i), cur)
    path_parts.append(chosen)
    cur = chosen[-1]

    while remaining:
        best_i = 0
        best_cost = float("inf")
        for i, c in enumerate(remaining):
            d2 = np.min(np.sum((c - cur) ** 2, axis=1))
            if d2 < best_cost:
                best_cost = d2
                best_i = i
        chosen = choose_start_and_direction(remaining.pop(best_i), cur)
        path_parts.append(chosen)
        cur = chosen[-1]

    return np.concatenate(path_parts, axis=0)


@dataclass
class RenderResult:
    points_px: np.ndarray
    x: np.ndarray
    y: np.ndarray
    bbox_w: float
    bbox_h: float
    contour_points: int
    actual_points_per_sec: float


def compute_text_outline(params: dict) -> RenderResult:
    text = params["text"]
    if text.strip() == "":
        raise ValueError("Please enter text")

    font = QtGui.QFont(params["font_family"])
    style_name = params.get("font_style", "")
    if style_name:
        font.setStyleName(style_name)
    font.setPointSizeF(DEFAULT_FONT_SIZE)
    font.setKerning(bool(params.get("kerning", True)))
    tracking = float(params.get("tracking", 0.0))
    if abs(tracking) > 1e-9:
        font.setLetterSpacing(QtGui.QFont.SpacingType.AbsoluteSpacing, tracking)
    fm = QtGui.QFontMetricsF(font)

    path = QtGui.QPainterPath()
    y = fm.ascent()
    line_spacing = fm.lineSpacing() * float(params["line_spacing"])
    lines = text.split("\n")
    widths = [fm.horizontalAdvance(line) if line else 0.0 for line in lines]
    block_w = max(widths) if widths else 0.0
    align = params.get("paragraph_align", "left")

    any_text = any(line != "" for line in lines)
    for i, line in enumerate(lines):
        if line != "":
            w = widths[i]
            if align == "center":
                x0 = (block_w - w) * 0.5
                path.addText(x0, y, font, line)
            elif align == "right":
                x0 = block_w - w
                path.addText(x0, y, font, line)
            elif align == "justify" and i < len(lines) - 1 and " " in line:
                # Simple paragraph justify for non-last lines.
                spaces = line.count(" ")
                extra = max(0.0, block_w - w) / spaces if spaces > 0 else 0.0
                x0 = 0.0
                for ch in line:
                    path.addText(x0, y, font, ch)
                    adv = fm.horizontalAdvance(ch)
                    if ch == " ":
                        adv += extra
                    x0 += adv
            else:
                path.addText(0.0, y, font, line)
        y += line_spacing
    if not any_text:
        raise ValueError("No visible glyphs to outline")

    if params["unite_paths"]:
        # Similar to Illustrator Pathfinder > Unite.
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        path = path.simplified()

    polys = path.toSubpathPolygons()
    contours = [contour_from_polygon(p) for p in polys]
    contours = [c for c in contours if c.shape[0] > 1]
    contours = [densify_closed_contour(c, spacing=params["contour_spacing"]) for c in contours]
    if not contours:
        raise ValueError("Failed to generate glyph outlines")

    if params["optimize_path"]:
        points = order_contours_shortest(contours)
    else:
        points = np.concatenate([np.concatenate([c, c[:1]], axis=0) for c in contours], axis=0)

    if params["point_step"] > 1:
        points = points[:: int(params["point_step"])]
    if params["point_dwell"] > 1:
        points = np.repeat(points, int(params["point_dwell"]), axis=0)

    contour_points = int(points.shape[0])

    minx, miny = points[:, 0].min(), points[:, 1].min()
    maxx, maxy = points[:, 0].max(), points[:, 1].max()
    bw = max(1e-6, maxx - minx)
    bh = max(1e-6, maxy - miny)

    xn = (points[:, 0] - minx) / bw
    yn = (points[:, 1] - miny) / bh
    x = xn * 2.0 - 1.0
    y = 1.0 - yn * 2.0
    x, y = apply_aspect_fit(x, y, bw, bh, "fit")

    # Non-integer points/sec mapping for better mathematical accuracy.
    pps = max(1e-6, float(params["points_per_second"]))
    sr = max(1, int(params["sample_rate"]))
    target_len_by_pps = max(1, int(round(contour_points * sr / pps)))
    x, y = resample_to_length(x, y, target_len_by_pps, params["resample_mode"])

    if params["target_seconds"] > 0:
        target_len = int(params["target_seconds"] * params["sample_rate"])
        x, y = resample_to_length(x, y, target_len, params["resample_mode"])

    x *= 0.75
    y *= 0.75
    actual_pps = contour_points * sr / max(1, x.shape[0])
    return RenderResult(
        points_px=points,
        x=x,
        y=y,
        bbox_w=bw,
        bbox_h=bh,
        contour_points=contour_points,
        actual_points_per_sec=actual_pps,
    )


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ld_text_outline_qt")
        self.resize(1420, 900)

        self.last_result: RenderResult | None = None
        self.preview_qimage: QtGui.QImage | None = None
        self.last_params: dict | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        left = QtWidgets.QWidget()
        left.setFixedWidth(430)
        form = QtWidgets.QVBoxLayout(left)
        layout.addWidget(left)

        row1 = QtWidgets.QHBoxLayout()
        self.btn_render = QtWidgets.QPushButton("Render Preview")
        self.btn_export = QtWidgets.QPushButton("Export WAV")
        row1.addWidget(self.btn_render)
        row1.addWidget(self.btn_export)
        form.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        self.btn_save_preview = QtWidgets.QPushButton("Save Preview PNG")
        row2.addWidget(self.btn_save_preview)
        form.addLayout(row2)

        self.font_combo = QtWidgets.QFontComboBox()
        self.font_combo.setFontFilters(QtWidgets.QFontComboBox.FontFilter.ScalableFonts)
        self.font_style_combo = QtWidgets.QComboBox()
        self.line_spacing = QtWidgets.QDoubleSpinBox(); self.line_spacing.setRange(0.4, 4.0); self.line_spacing.setValue(1.1)
        self.kerning = QtWidgets.QCheckBox(); self.kerning.setChecked(True)
        self.tracking = QtWidgets.QDoubleSpinBox(); self.tracking.setRange(-20.0, 60.0); self.tracking.setValue(0.0); self.tracking.setSingleStep(0.2)

        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setPlainText("LASER\nOUTLINE")
        self.text_edit.setMinimumHeight(130)

        self.optimize_path = QtWidgets.QCheckBox(); self.optimize_path.setChecked(True)
        self.unite_paths = QtWidgets.QCheckBox(); self.unite_paths.setChecked(True)
        self.show_path = QtWidgets.QCheckBox(); self.show_path.setChecked(True)
        self.paragraph_align = QtWidgets.QComboBox(); self.paragraph_align.addItems(["left", "center", "right", "justify"])

        self.sample_rate = QtWidgets.QSpinBox(); self.sample_rate.setRange(8000, 192000); self.sample_rate.setValue(44100)
        self.points_per_sec = QtWidgets.QSpinBox(); self.points_per_sec.setRange(1, 200000); self.points_per_sec.setValue(150)
        self.point_step = QtWidgets.QSpinBox(); self.point_step.setRange(1, 20); self.point_step.setValue(1)
        self.contour_spacing = QtWidgets.QDoubleSpinBox(); self.contour_spacing.setRange(0.2, 20.0); self.contour_spacing.setValue(1.0); self.contour_spacing.setSingleStep(0.2)
        self.point_dwell = QtWidgets.QSpinBox(); self.point_dwell.setRange(1, 100); self.point_dwell.setValue(1)
        self.target_sec = QtWidgets.QDoubleSpinBox(); self.target_sec.setRange(0.0, 3600.0); self.target_sec.setValue(0.0)
        self.resample_mode = QtWidgets.QComboBox(); self.resample_mode.addItems(["hold", "linear"])

        def row(label: str, widget: QtWidgets.QWidget):
            h = QtWidgets.QHBoxLayout()
            h.addWidget(QtWidgets.QLabel(label))
            h.addWidget(widget, 1)
            form.addLayout(h)

        row("Font", self.font_combo)
        row("Style", self.font_style_combo)
        row("Line Spacing", self.line_spacing)
        row("Kerning", self.kerning)
        row("Tracking", self.tracking)
        row("Paragraph Align", self.paragraph_align)
        form.addWidget(QtWidgets.QLabel("Text (multiline)"))
        form.addWidget(self.text_edit)
        row("Optimize Path", self.optimize_path)
        row("Pathfinder Unite", self.unite_paths)
        row("Show Path Lines", self.show_path)
        row("Sample Rate", self.sample_rate)
        row("Points/sec (scan speed)", self.points_per_sec)
        row("Contour Spacing", self.contour_spacing)
        row("Point Step", self.point_step)
        row("Point Dwell", self.point_dwell)
        row("Target Sec (0=off)", self.target_sec)
        row("Resample", self.resample_mode)

        self.status = QtWidgets.QLabel("Ready")
        self.time_info = QtWidgets.QLabel("Estimated print time: -")
        self.pps_info = QtWidgets.QLabel("Actual points/sec: -")
        self.export_info = QtWidgets.QLabel("Last export: -")
        form.addWidget(self.status)
        form.addWidget(self.time_info)
        form.addWidget(self.pps_info)
        form.addWidget(self.export_info)
        form.addStretch(1)

        self.preview = QtWidgets.QLabel("Preview")
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#ffffff;")
        layout.addWidget(self.preview, 1)

        self.btn_render.clicked.connect(self.on_render)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_save_preview.clicked.connect(self.on_save_preview)
        self.font_combo.currentFontChanged.connect(self._refresh_font_styles)
        self._refresh_font_styles()

    def _refresh_font_styles(self) -> None:
        family = self.font_combo.currentFont().family()
        styles = QtGui.QFontDatabase.styles(family)
        if not styles:
            styles = ["Regular"]
        prev = self.font_style_combo.currentText()
        self.font_style_combo.blockSignals(True)
        self.font_style_combo.clear()
        self.font_style_combo.addItems(styles)
        if prev in styles:
            self.font_style_combo.setCurrentText(prev)
        else:
            self.font_style_combo.setCurrentIndex(0)
        self.font_style_combo.blockSignals(False)

    def _params(self) -> dict:
        return {
            "font_family": self.font_combo.currentFont().family(),
            "font_style": self.font_style_combo.currentText(),
            "line_spacing": self.line_spacing.value(),
            "kerning": self.kerning.isChecked(),
            "tracking": self.tracking.value(),
            "paragraph_align": self.paragraph_align.currentText(),
            "text": self.text_edit.toPlainText(),
            "optimize_path": self.optimize_path.isChecked(),
            "unite_paths": self.unite_paths.isChecked(),
            "show_path": self.show_path.isChecked(),
            "sample_rate": self.sample_rate.value(),
            "points_per_second": self.points_per_sec.value(),
            "contour_spacing": self.contour_spacing.value(),
            "point_step": self.point_step.value(),
            "point_dwell": self.point_dwell.value(),
            "target_seconds": self.target_sec.value(),
            "resample_mode": self.resample_mode.currentText(),
        }

    @staticmethod
    def _fmt_hms(sec: float) -> str:
        total = max(0, int(round(sec)))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _build_preview_qimage(self, result: RenderResult, size: int, show_path: bool) -> QtGui.QImage:
        arr = np.full((size, size, 3), 255, dtype=np.uint8)
        p = result.points_px
        if p.size > 0:
            minx, miny = p[:, 0].min(), p[:, 1].min()
            maxx, maxy = p[:, 0].max(), p[:, 1].max()
            bw = max(1e-6, maxx - minx)
            bh = max(1e-6, maxy - miny)

            pad = 30
            fw = size - 2 * pad
            fh = size - 2 * pad
            if bw >= bh:
                iw = fw
                ih = int(fw * (bh / bw))
                ix0 = pad
                iy0 = pad + (fh - ih) // 2
            else:
                ih = fh
                iw = int(fh * (bw / bh))
                ix0 = pad + (fw - iw) // 2
                iy0 = pad

            xp = ix0 + ((p[:, 0] - minx) / bw) * max(1, iw - 1)
            yp = iy0 + ((p[:, 1] - miny) / bh) * max(1, ih - 1)
            xi = np.clip(np.rint(xp).astype(np.int32), 0, size - 1)
            yi = np.clip(np.rint(yp).astype(np.int32), 0, size - 1)
            arr[yi, xi] = (0, 0, 0)

            if show_path and len(xi) > 1:
                from PIL import ImageDraw

                img = Image.fromarray(arr, mode="RGB")
                draw = ImageDraw.Draw(img)
                max_pts = 2500
                if len(xi) > max_pts:
                    idx = np.linspace(0, len(xi) - 1, max_pts).astype(np.int32)
                    path = list(zip(xi[idx].tolist(), yi[idx].tolist()))
                else:
                    path = list(zip(xi.tolist(), yi.tolist()))
                draw.line(path, fill=(220, 0, 0), width=1)
                arr = np.asarray(img, dtype=np.uint8)

        h0, w0, _ = arr.shape
        return QtGui.QImage(arr.data, w0, h0, 3 * w0, QtGui.QImage.Format.Format_RGB888).copy()

    def on_render(self) -> None:
        try:
            params = self._params()
            result = compute_text_outline(params)
            self.last_result = result
            self.last_params = dict(params)

            size = int(min(max(420, self.preview.width() - 20), max(420, self.preview.height() - 20), 1300))
            qimg = self._build_preview_qimage(result, size, params["show_path"])
            self.preview_qimage = qimg
            self.preview.setPixmap(QtGui.QPixmap.fromImage(qimg))
            self.preview.setText("")

            self.status.setText(f"Rendered: points={result.points_px.shape[0]} samples={result.x.shape[0]}")
            self.pps_info.setText(
                f"Actual points/sec: {result.actual_points_per_sec:.2f} (target {params['points_per_second']})"
            )
            if params["target_seconds"] <= 0:
                sec = result.x.shape[0] / max(1, params["sample_rate"])
                self.time_info.setText(f"Estimated print time: {self._fmt_hms(sec)}")
            else:
                self.time_info.setText("Estimated print time: target-sec mode (forced)")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Render error", str(exc))

    def on_export(self) -> None:
        params = self._params()
        if self.last_result is None or self.last_params != params:
            try:
                self.last_result = compute_text_outline(params)
                self.last_params = dict(params)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Export error", str(exc))
                return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save XY WAV", "ld_text_outline.wav", "WAV (*.wav)")
        if not path:
            return
        out = Path(path)
        sr = self.sample_rate.value()
        write_xy_wav(out, self.last_result.x, self.last_result.y, sr)
        np.savez(out.with_suffix(".npz"), x=self.last_result.x, y=self.last_result.y, sample_rate=sr)
        self.status.setText(f"Saved WAV: {out}")
        total_samples = int(self.last_result.x.shape[0])
        duration_sec = total_samples / max(1, sr)
        self.export_info.setText(
            f"Last export: {total_samples} samples ({duration_sec:.3f} s @ {sr} Hz)"
        )

    def on_save_preview(self) -> None:
        if self.preview_qimage is None:
            QtWidgets.QMessageBox.information(self, "No preview", "Please render preview first")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Preview", "ld_text_outline_preview.png", "PNG (*.png)")
        if not path:
            return
        self.preview_qimage.save(path, "PNG")
        self.status.setText(f"Saved preview: {path}")


def main() -> None:
    app = QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    main()
