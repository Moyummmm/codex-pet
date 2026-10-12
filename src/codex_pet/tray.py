"""菜单栏/系统托盘:大号数字图标(内部线性容量填充)+ 菜单。

macOS:状态项即主显示——剩余额度以尽量大的数字直接显示,数字内部
按剩余% 线性填充(下亮上暗),左键弹出详情面板,右键手动弹菜单
(不挂原生菜单,规避 Qt 菜单追踪的 clickCount 断言崩溃)。
Windows:托盘图标为辅助,左键切换悬浮余额条,右键走原生菜单。
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QCursor, QFont, QFontMetrics,
                         QIcon, QPainter, QPen, QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .colors import deepseek_color, fill_color, ui_font

IS_MAC = sys.platform == "darwin"


def _draw_number(size: int, remaining: int | None, offline: bool,
                 provider: str, ds_total: float | None) -> QPixmap:
    """大号数字图标:数字尽量占满画布,内部按剩余% 线性填充(下亮上暗)。

    - 0% = 全暗,100% = 全亮;20% 即数字下 1/5 亮,连续线性
    - macOS 低电量(≤20%)亮色转红;Windows 托盘亮色用电量分级色
    - DeepSeek 模式显示 ¥(按余额水平取色);离线 Z;在线读取中 …
    """
    s = size / 64.0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if provider == "deepseek":
        text = "¥"
        bright = deepseek_color(ds_total) if not offline else QColor(170, 177, 186)
        dim, fill_ratio = bright, None
    elif offline:
        text = "Z"
        bright = dim = QColor(170, 177, 186)
        fill_ratio = None
    elif remaining is None:
        text = "…"
        bright = dim = QColor(200, 206, 214)
        fill_ratio = None
    else:
        text = str(remaining)
        if IS_MAC:
            bright = (QColor(255, 105, 107) if remaining <= 20
                      else QColor(236, 240, 246))
            dim = QColor(235, 239, 245, 95)
        else:
            bright = fill_color(remaining, False)
            dim = QColor(120, 130, 145, 110)
        fill_ratio = max(0, min(100, remaining)) / 100

    # 字号尽量大:先取画布高的 ~90%,超宽(如 100)按宽度等比缩
    font = ui_font(17, bold=True)
    font.setPixelSize(max(9, round(58 * s)))
    p.setFont(font)
    fm = QFontMetrics(font)
    max_w = 62 * s
    w = fm.horizontalAdvance(text)
    if w > max_w:
        font.setPixelSize(max(9, round(58 * s * max_w / w)))
        p.setFont(font)
        fm = QFontMetrics(font)

    rect = QRectF(0, 0, size, size)
    text_rect = p.boundingRect(rect, Qt.AlignmentFlag.AlignCenter, text)

    # 暗色整字
    p.setPen(QPen(dim))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # 亮色填充:从文字底边按剩余% 向上,裁剪在数字内
    if fill_ratio:
        fill_h = text_rect.height() * fill_ratio
        p.setClipRect(QRectF(0, text_rect.bottom() - fill_h, size, fill_h))
        p.setPen(QPen(bright))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        p.setClipping(False)
    p.end()
    return pixmap


def make_tray_icon(remaining: int | None, status: str,
                   provider: str = "codex", ds_total: float | None = None) -> QIcon:
    """菜单栏图标:多尺寸位图(32/48/64/128)保证 Retina 下清晰。"""
    offline = status != "online"
    icon = QIcon()
    for size in (32, 48, 64, 128):
        icon.addPixmap(_draw_number(size, remaining, offline, provider, ds_total))
    return icon


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
