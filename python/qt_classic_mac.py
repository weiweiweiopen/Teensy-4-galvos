from __future__ import annotations

try:
    from PySide6 import QtGui, QtWidgets
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: PySide6. Install with `python3 -m pip install -r python/requirements.txt`."
    ) from exc


CLASSIC_MAC_STYLESHEET = """
QMainWindow, QWidget#ClassicCentral {
    background: #d9d9d9;
    color: #111111;
    font-family: Geneva, Helvetica, Arial;
    font-size: 12px;
}
QWidget#SidebarPanel {
    background: #cfcfcf;
    border: 2px solid #111111;
}
QScrollArea {
    background: #cfcfcf;
    border: 2px solid #111111;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #d9d9d9;
    border: 1px solid #111111;
}
QPushButton {
    background: #efefef;
    border-top: 2px solid #ffffff;
    border-left: 2px solid #ffffff;
    border-right: 2px solid #555555;
    border-bottom: 2px solid #555555;
    padding: 5px 10px;
    min-height: 24px;
    color: #111111;
}
QPushButton:pressed, QPushButton:checked {
    border-top: 2px solid #555555;
    border-left: 2px solid #555555;
    border-right: 2px solid #ffffff;
    border-bottom: 2px solid #ffffff;
    background: #d7d7d7;
}
QPushButton:disabled {
    color: #707070;
    background: #dddddd;
}
QComboBox, QSpinBox, QDoubleSpinBox, QFontComboBox, QTextEdit {
    background: #ffffff;
    color: #111111;
    selection-background-color: #000000;
    selection-color: #ffffff;
    border-top: 2px solid #777777;
    border-left: 2px solid #777777;
    border-right: 2px solid #ffffff;
    border-bottom: 2px solid #ffffff;
    padding: 4px 6px;
}
QComboBox::drop-down {
    width: 22px;
    border-left: 1px solid #111111;
    background: #e5e5e5;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 2px solid #111111;
    selection-background-color: #111111;
    selection-color: #ffffff;
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    width: 18px;
    background: #e5e5e5;
    border-left: 1px solid #111111;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background: #ffffff;
    border-top: 2px solid #777777;
    border-left: 2px solid #777777;
    border-right: 2px solid #ffffff;
    border-bottom: 2px solid #ffffff;
}
QCheckBox::indicator:checked {
    background: #111111;
}
QLabel#SectionLabel {
    color: #111111;
    font-weight: 700;
    padding: 6px 8px 3px 8px;
}
QLabel#InfoLabel, QLabel#PathLabel {
    background: #efefef;
    border-top: 2px solid #777777;
    border-left: 2px solid #777777;
    border-right: 2px solid #ffffff;
    border-bottom: 2px solid #ffffff;
    padding: 5px 8px;
}
QLabel#PreviewFrame {
    background: #f7f5ee;
    color: #111111;
    border-top: 2px solid #777777;
    border-left: 2px solid #777777;
    border-right: 2px solid #ffffff;
    border-bottom: 2px solid #ffffff;
    padding: 12px;
}
QSplitter::handle {
    background: #bcbcbc;
    border-left: 1px solid #ffffff;
    border-right: 1px solid #555555;
}
QToolTip {
    background: #ffffd6;
    color: #111111;
    border: 1px solid #111111;
}
"""


def apply_classic_mac_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    font = QtGui.QFont("Geneva", 12)
    app.setFont(font)

    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#d9d9d9"))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#111111"))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#efefef"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#ffffd6"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#111111"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#111111"))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#efefef"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#111111"))
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#111111"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(CLASSIC_MAC_STYLESHEET)


def make_section_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName("SectionLabel")
    return label
