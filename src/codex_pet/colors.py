"""共享配色与工具函数。"""

from __future__ import annotations

from PyQt6.QtGui import QColor

COL_BODY_EMPTY = QColor(232, 238, 244)
COL_BODY_EMPTY_DARK = QColor(205, 214, 224)
COL_FULL = QColor(76, 209, 133)            # >60% 绿
COL_MID = QColor(255, 178, 66)             # 30–60% 橙
COL_LOW = QColor(255, 107, 107)            # <30% 红
COL_OFFLINE = QColor(170, 177, 186)        # 离线灰
COL_TEXT = QColor(70, 78, 90)


def fill_color(remaining: int | None, offline: bool) -> QColor:
    if offline or remaining is None:
        return COL_OFFLINE
    if remaining > 60:
        return COL_FULL
    if remaining > 30:
        return COL_MID
    return COL_LOW
