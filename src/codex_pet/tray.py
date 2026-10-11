"""菜单栏/系统托盘:电量图标(数字显示在电池内)+ 菜单。

macOS:状态项即主显示——电池图标实时显示剩余额度,左键弹出详情面板,
右键手动弹菜单(不挂原生菜单,规避 Qt 菜单追踪的 clickCount 断言崩溃)。
Windows:托盘图标为辅助,左键切换悬浮余额条,右键走原生菜单。
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QCursor, QIcon, QPainter, QPen,
                         QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .colors import deepseek_color, fill_color, ui_font

IS_MAC = sys.platform == "darwin"


def make_tray_icon(remaining: int | None, status: str,
                   provider: str = "codex", ds_total: float | None = None) -> QIcon:
    """画一个 64x64 的菜单栏图标:电池内嵌剩余数字 / DeepSeek ¥ 圆标。"""
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

    body = QRectF(5, 14, 52, 36)
    color = fill_color(remaining, offline)

    p.setPen(QPen(QColor(120, 130, 145), 3))
    p.setBrush(QColor(232, 238, 244))
    p.drawRoundedRect(body, 9, 9)
    p.setBrush(QColor(120, 130, 145))
    p.drawRoundedRect(QRectF(58, 24, 5, 16), 2, 2)

    if remaining is not None and not offline:
        fill_h = (body.height() - 4) * remaining / 100
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(
            QRectF(body.left() + 2, body.bottom() - 2 - fill_h,
                   body.width() - 4, fill_h),
            6, 6,
        )

    if remaining is not None and not offline:
        p.setPen(QColor(50, 55, 65))
        p.setFont(ui_font(20, bold=True))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, str(remaining))
    else:
        p.setPen(QColor(90, 98, 110))
        p.setFont(ui_font(22))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, "Z")
    p.end()
    return QIcon(pixmap)


class Tray(QObject):
    refreshRequested = pyqtSignal()
    toggleBarRequested = pyqtSignal()    # 仅 Windows:切换悬浮余额条
    showPanelRequested = pyqtSignal()    # 仅 macOS:弹出详情面板
    quitRequested = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.icon = QSystemTrayIcon(self)
        self.icon.setToolTip("Codex Pet")

        self._menu = QMenu()
        self.toggle_action = None
        if not IS_MAC:
            self.toggle_action = QAction("隐藏余额条", self._menu)
            self.toggle_action.triggered.connect(self.toggleBarRequested.emit)
            self._menu.addAction(self.toggle_action)

        refresh = QAction("立即刷新", self._menu)
        refresh.triggered.connect(self.refreshRequested.emit)
        self._menu.addAction(refresh)

        self._menu.addSeparator()
        quit_action = QAction("退出", self._menu)
        quit_action.triggered.connect(self.quitRequested.emit)
        self._menu.addAction(quit_action)

        self.icon.activated.connect(self._on_activated)
        if IS_MAC:
            # macOS:不给状态项挂原生菜单——点击状态项弹原生菜单会在 Qt 的
            # 菜单追踪观察者里对不支持 clickCount 的事件调用 clickCount,
            # ObjC 断言直接 abort。改为激活时手动弹出(见 _on_activated)。
            pass
        else:
            self.icon.setContextMenu(self._menu)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if IS_MAC:
                self.showPanelRequested.emit()
            else:
                self.toggleBarRequested.emit()
        elif (reason == QSystemTrayIcon.ActivationReason.Context
              and IS_MAC):
            self._menu.popup(QCursor.pos())

    def anchor_point(self) -> QPoint:
        """详情面板锚点:状态项下沿中点;取不到几何时回退鼠标位置。"""
        g = self.icon.geometry()
        if g.isValid() and not g.isNull():
            return QPoint(g.center().x(), g.bottom())
        return QCursor.pos()

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
            tip = "Codex(离线)"
        elif remaining is None:
            tip = "Codex(读取中…)"
        else:
            tip = f"Codex 剩余 {remaining}%(点击查看详情)"
        self.icon.setToolTip(tip)

    def set_bar_visible(self, visible: bool) -> None:
        if self.toggle_action is not None:
            self.toggle_action.setText("隐藏余额条" if visible else "显示余额条")
