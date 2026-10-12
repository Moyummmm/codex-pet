"""共享配色与工具函数。"""

from __future__ import annotations

import sys

from PyQt6.QtGui import QColor, QFont

COL_BODY_EMPTY = QColor(232, 238, 244)
COL_BODY_EMPTY_DARK = QColor(205, 214, 224)
COL_FULL = QColor(76, 209, 133)            # >60% 绿
COL_MID = QColor(255, 178, 66)             # 30–60% 橙
COL_LOW = QColor(255, 107, 107)            # <30% 红
COL_OFFLINE = QColor(170, 177, 186)        # 离线灰
COL_TEXT = QColor(70, 78, 90)
COL_DEEPSEEK = QColor(77, 163, 255)        # DeepSeek 蓝


def deepseek_color(total: float | None) -> QColor:
    """按余额水平选色:充足蓝,偏低橙,<5 红。"""
    if total is None:
        return COL_OFFLINE
    if total >= 20:
        return COL_DEEPSEEK
    if total >= 5:
        return COL_MID
    return COL_LOW


def fill_color(remaining: int | None, offline: bool) -> QColor:
    if offline or remaining is None:
        return COL_OFFLINE
    if remaining > 60:
        return COL_FULL
    if remaining > 30:
        return COL_MID
    return COL_LOW


def ui_font(size: int, bold: bool = False) -> QFont:
    """平台 UI 字体:Windows 用 Segoe UI,其余平台用系统默认(如 SF Pro)。"""
    if sys.platform == "win32":
        font = QFont("Segoe UI", size)
    else:
        font = QFont()
        font.setPointSize(size)
    font.setBold(bold)
    return font
