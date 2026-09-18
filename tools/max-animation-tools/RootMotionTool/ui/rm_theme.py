# -*- coding: utf-8 -*-
"""发布工具统一深色主题样式。"""
from __future__ import print_function

DARK_STYLESHEET = u"""
QDialog, QWidget {
    background: #141922;
    color: #e6ebf2;
}
QLabel {
    color: #dbe2ea;
    background: transparent;
}
QGroupBox {
    border: 1px solid #2b3445;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px 10px 8px 10px;
    font-weight: bold;
    background: #1b2230;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #8ea0b8;
}
QTabWidget::pane {
    border: 1px solid #2b3445;
    border-radius: 10px;
    background: #1b2230;
    top: -1px;
}
QTabBar::tab {
    background: #202a39;
    color: #c8d1dd;
    border: 1px solid #31405a;
    padding: 8px 14px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected {
    background: #3f6ed8;
    color: white;
}
QPushButton {
    background: #273244;
    color: #eef3fb;
    border: 1px solid #384861;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover {
    background: #31415b;
}
QPushButton:pressed {
    background: #223047;
}
QPushButton:disabled {
    background: #1a2230;
    color: #6a7588;
}
QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget, QTextEdit {
    background: #0f141d;
    color: #edf2f8;
    border: 1px solid #303a4c;
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: #3f6ed8;
}
QSpinBox, QDoubleSpinBox {
    background: #0f141d;
    color: #edf2f8;
    border: 1px solid #303a4c;
    border-radius: 8px;
    padding: 4px 6px;
    min-height: 24px;
    selection-background-color: #3f6ed8;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}
QCheckBox {
    spacing: 8px;
    padding: 4px 0px;
    background: transparent;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #5d6f8c;
    background: #101620;
}
QCheckBox::indicator:checked {
    background: #4c7bf0;
    border: 1px solid #4c7bf0;
}
QCheckBox::indicator:hover {
    border: 1px solid #7e94b8;
}
QHeaderView::section {
    background: #202a39;
    color: #dbe2ea;
    border: none;
    padding: 6px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #202a39;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    background: #4c7bf0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #3f6ed8;
    border-radius: 3px;
}
QListWidget::item {
    min-height: 24px;
    padding: 2px 6px;
    color: #dbe2ea;
    background: transparent;
}
QListWidget::item:hover {
    background: #283246;
}
QListWidget::item:selected {
    background: #3f6ed8;
    color: #ffffff;
}
QListWidget#opWeaponStateList {
    outline: none;
    padding: 2px;
}
QListWidget#opWeaponStateList::item {
    min-height: 28px;
    padding: 4px 10px;
    color: #edf2f8;
    background: transparent;
}
QListWidget#opWeaponStateList::item:hover {
    background: #2a3548;
}
QListWidget#opWeaponStateList::item:selected {
    background: #3f6ed8;
    color: #ffffff;
}
QWidget#rmGroupBody {
    background: #1b2230;
    border: 1px solid #2d394d;
    border-top: none;
    border-radius: 0 0 12px 12px;
}
QPushButton#rmGroupToggle {
    background: #212c3d;
    border: 1px solid #31405a;
    border-radius: 12px 12px 0 0;
    text-align: left;
    padding: 9px 12px;
    font-weight: bold;
}
QPushButton#rmGroupToggle:hover {
    background: #273449;
}
QPushButton#rmGroupToggle:checked {
    background: #25344d;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 6px 2px 6px 2px;
}
QScrollBar::handle:vertical {
    background: #5e6f8b;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #7c90b2;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    border: none;
    height: 0px;
}
"""


def apply_dark_theme(widget):
    if widget is None:
        return
    widget.setStyleSheet(DARK_STYLESHEET)
