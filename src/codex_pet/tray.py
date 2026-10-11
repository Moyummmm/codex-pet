"""系统托盘:迷你电量图标 + 菜单。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPen,
                         QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .pet_widget import fill_color


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
    togglePetRequested = pyqtSignal()
    switchModeRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._remaining: int | None = None
        self._status = "offline"

        self.icon = QSystemTrayIcon(self)
        self.icon.setToolTip("Codex Pet")

        menu = QMenu()
        self.toggle_action = QAction("隐藏宠物", menu)
        self.toggle_action.triggered.connect(self.togglePetRequested.emit)
        menu.addAction(self.toggle_action)

        self.mode_action = QAction("切换为任务栏文字", menu)
        self.mode_action.triggered.connect(self.switchModeRequested.emit)
        menu.addAction(self.mode_action)

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
            self.togglePetRequested.emit()

    def update_state(self, remaining: int | None, status: str) -> None:
        self._remaining, self._status = remaining, status
        self.icon.setIcon(make_tray_icon(remaining, status))
        if status != "online":
            tip = "Codex Pet(离线)"
        elif remaining is None:
            tip = "Codex Pet(读取中…)"
        else:
            tip = f"Codex 剩余 {remaining}%"
        self.icon.setToolTip(tip)

    def set_pet_visible(self, visible: bool, mode: str = "pet") -> None:
        name = "宠物" if mode == "pet" else "状态条"
        self.toggle_action.setText(("隐藏" if visible else "显示") + name)

    def set_mode(self, mode: str) -> None:
        """根据当前模式更新"切换"菜单项文案。"""
        self.mode_action.setText(
            "切换为任务栏文字" if mode == "pet" else "切换为桌面宠物"
        )
