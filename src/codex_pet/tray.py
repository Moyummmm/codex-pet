"""系统托盘:迷你电量图标 + 菜单。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPen,
                         QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .colors import fill_color


def make_tray_icon(remaining: int | None, status: str) -> QIcon:
    """画一个 64x64 的迷你电量胶囊图标。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    body = QRectF(10, 8, 44, 48)
    offline = status != "online"
    color = fill_color(remaining, offline)

    p.setPen(QPen(QColor(120, 130, 145), 3))
    p.setBrush(QColor(232, 238, 244))
    p.drawRoundedRect(body, 14, 14)

    if remaining is not None and not offline:
        fill_h = body.height() * remaining / 100
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(
            QRectF(body.left(), body.bottom() - fill_h, body.width(), fill_h),
            12, 12,
        )

    if remaining is not None and not offline:
        p.setPen(QColor(50, 55, 65))
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, str(remaining))
    else:
        p.setPen(QColor(90, 98, 110))
        p.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, "Z")
    p.end()
    return QIcon(pixmap)


class Tray(QObject):
    refreshRequested = pyqtSignal()
    toggleBarRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._remaining: int | None = None
        self._status = "offline"

        self.icon = QSystemTrayIcon(self)
        self.icon.setToolTip("Codex Pet")

        menu = QMenu()
        self.toggle_action = QAction("隐藏余额条", menu)
        self.toggle_action.triggered.connect(self.toggleBarRequested.emit)
        menu.addAction(self.toggle_action)

        refresh = QAction("立即刷新", menu)
        refresh.triggered.connect(self.refreshRequested.emit)
        menu.addAction(refresh)

        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quitRequested.emit)
        menu.addAction(quit_action)

        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggleBarRequested.emit()

    def update_state(self, remaining: int | None, status: str) -> None:
        self._remaining, self._status = remaining, status
        self.icon.setIcon(make_tray_icon(remaining, status))
        if status != "online":
            tip = "Codex 余额条(离线)"
        elif remaining is None:
            tip = "Codex 余额条(读取中…)"
        else:
            tip = f"Codex 剩余 {remaining}%"
        self.icon.setToolTip(tip)

    def set_bar_visible(self, visible: bool) -> None:
        self.toggle_action.setText("隐藏余额条" if visible else "显示余额条")
