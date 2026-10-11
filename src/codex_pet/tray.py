"""系统托盘:迷你电量图标 + 菜单。"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QIcon, QPainter, QPen,
                         QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .colors import deepseek_color, fill_color, ui_font


def make_tray_icon(remaining: int | None, status: str,
                   provider: str = "codex", ds_total: float | None = None) -> QIcon:
    """画一个 64x64 的迷你图标:配额电量胶囊 / DeepSeek ¥ 圆标。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    offline = status != "online"

    if provider == "deepseek":
        color = deepseek_color(ds_total) if not offline else QColor(170, 177, 186)
        p.setPen(QPen(color, 5))
        p.setBrush(QColor(232, 238, 244) if not offline else QColor(225, 228, 232))
        p.drawEllipse(QRectF(8, 8, 48, 48))
        p.setPen(QColor(50, 55, 65) if not offline else QColor(120, 126, 136))
        p.setFont(ui_font(22, bold=True))
        p.drawText(QRectF(8, 8, 48, 48), Qt.AlignmentFlag.AlignCenter, "¥")
        p.end()
        return QIcon(pixmap)

    body = QRectF(10, 8, 44, 48)
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
        p.setFont(ui_font(16, bold=True))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, str(remaining))
    else:
        p.setPen(QColor(90, 98, 110))
        p.setFont(ui_font(20))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, "Z")
    p.end()
    return QIcon(pixmap)


class Tray(QObject):
    refreshRequested = pyqtSignal()
    toggleBarRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

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

    def update_payload(self, payload: dict) -> None:
        """根据统一状态快照更新图标与提示。"""
        active = payload.get("active", "codex")
        status = payload.get("status", "offline")
        if active == "deepseek":
            ds = payload.get("deepseek")
            total = ds.get("total") if ds else None
            self.icon.setIcon(make_tray_icon(None, status, "deepseek", total))
            if status == "error":
                tip = "DeepSeek(密钥无效)"
            elif status != "online" or total is None:
                tip = "DeepSeek(读取中…)"
            else:
                sym = {"CNY": "¥", "USD": "$"}.get((ds or {}).get("currency"), "¥")
                tip = f"DeepSeek 余额 {sym}{total:,.2f}"
            self.icon.setToolTip(tip)
            return

        codex = payload.get("codex") or {}
        remaining = (codex.get("primary") or {}).get("remaining")
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
