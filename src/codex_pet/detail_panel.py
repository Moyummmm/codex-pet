"""详情面板:点击宠物后在其旁弹出的配额详情浮层。"""

from __future__ import annotations

import time

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QProgressBar, QVBoxLayout, QWidget)

from .colors import fill_color

PLAN_NAMES = {
    "plus": "ChatGPT Plus",
    "pro": "ChatGPT Pro",
    "free": "Free",
    "go": "Go",
    "team": "Team",
    "business": "Business",
    "enterprise": "Enterprise",
}


def _fmt_countdown(resets_at) -> str:
    if not resets_at:
        return "--"
    secs = max(0, int(resets_at - time.time()))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h > 24:
        return f"{h // 24}d{h % 24}h"
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


class _LimitRow(QFrame):
    """一行:标题 + 进度条 + 已用% + 重置倒计时。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #444;")
        self.pct_label = QLabel("--%")
        self.pct_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.pct_label)
        layout.addLayout(header)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, 100)
        self.bar.setStyleSheet(
            "QProgressBar { background: #e8eef4; border-radius: 5px; }"
            "QProgressBar::chunk { border-radius: 5px; background: #4cd185; }"
        )
        layout.addWidget(self.bar)

        self.reset_label = QLabel("重置于 --")
        self.reset_label.setStyleSheet("color: #8a94a3; font-size: 11px;")
        layout.addWidget(self.reset_label)

    def update_data(self, window: dict | None) -> None:
        if not window:
            self.pct_label.setText("--%")
            self.bar.setValue(0)
            self.reset_label.setText("重置于 --")
            return
        used = window.get("used")
        remaining = window.get("remaining")
        if used is None:
            self.pct_label.setText("--%")
            self.bar.setValue(0)
        else:
            self.pct_label.setText(f"已用 {used}%")
            self.bar.setValue(used)
            color = fill_color(remaining, False)
            self.bar.setStyleSheet(
                "QProgressBar { background: #e8eef4; border-radius: 5px; }"
                f"QProgressBar::chunk {{ border-radius: 5px; background: {color.name()}; }}"
            )
            self.pct_label.setStyleSheet(
                f"font-weight: bold; color: {color.name()};"
            )
        self.reset_label.setText(f"重置于 {_fmt_countdown(window.get('resets_at'))} 后")


class DetailPanel(QWidget):
    """点击宠物时在旁边弹出的详情卡片(独立置顶无边框小窗)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._data: dict | None = None
        self._filter_installed = False
        self._keep_rects: list[QRect] = []  # 点击这些区域内不关闭(面板自身 + 余额条)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_labels)

        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(255,255,255,245); border-radius: 14px; }"
        )
        root = QVBoxLayout(card)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        title = QHBoxLayout()
        self.plan_label = QLabel("Codex 配额")
        self.plan_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        title.addWidget(self.plan_label)
        title.addStretch(1)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFlat(True)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet("color: #3b82f6; font-weight: bold; border: none;")
        title.addWidget(self.refresh_btn)
        root.addLayout(title)

        self.primary_row = _LimitRow("5 小时窗口", card)
        root.addWidget(self.primary_row)
        self.secondary_row = _LimitRow("周窗口", card)
        root.addWidget(self.secondary_row)

        self.updated_label = QLabel("")
        self.updated_label.setStyleSheet("color: #8a94a3; font-size: 11px;")
        root.addWidget(self.updated_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()

    def set_data(self, data: dict | None, status: str) -> None:
        self._data = data
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        data = self._data
        if not data:
            self.plan_label.setText("Codex 配额(离线)")
            self.primary_row.update_data(None)
            self.secondary_row.update_data(None)
            self.updated_label.setText("等待数据…")
            return
        plan = data.get("plan_type")
        self.plan_label.setText(f"Codex 配额 · {PLAN_NAMES.get(plan, plan or '?')}")
        self.primary_row.update_data(data.get("primary"))
        self.secondary_row.update_data(data.get("secondary"))
        updated_at = data.get("updated_at")
        if updated_at:
            t = time.strftime("%H:%M:%S", time.localtime(updated_at))
            self.updated_label.setText(f"更新于 {t}")
        self.adjustSize()

    def popup_near(self, anchor_global_pos, screen_rect,
                   keep_rects: list[QRect] | None = None) -> None:
        """在宠物旁边弹出;超出屏幕则换边。

        keep_rects:除面板自身外,点击这些区域(如余额条)也不触发关闭。
        """
        self._refresh_labels()
        self._keep_rects = list(keep_rects or [])
        w, h = self.width(), self.height()
        x = anchor_global_pos.x() - w - 12
        if x < screen_rect.left():
            x = anchor_global_pos.x() + 12
        y = max(screen_rect.top(),
                min(anchor_global_pos.y(), screen_rect.bottom() - h))
        self.move(x, y)
        self.show()
        self.raise_()
        if not self._filter_installed:
            QApplication.instance().installEventFilter(self)
            self._filter_installed = True
        self._timer.start(1000)  # 倒计时每秒刷新

    def hide_panel(self) -> None:
        self._timer.stop()
        self.hide()
        if self._filter_installed:
            QApplication.instance().removeEventFilter(self)
            self._filter_installed = False

    def eventFilter(self, obj, event) -> bool:
        """点击面板与余额条以外的任何位置 → 自动收起;Esc → 收起。"""
        et = event.type()
        if et == event.Type.MouseButtonPress:
            gp = event.globalPosition().toPoint()
            inside = self.geometry().contains(gp) or any(
                r.contains(gp) for r in self._keep_rects)
            if not inside:
                self.hide_panel()
        elif et == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.hide_panel()
        return False
