"""菜单栏/系统托盘:电量图标(数字显示在电池内)+ 菜单。

macOS:状态项即主显示——电池图标实时显示剩余额度,左键弹出详情面板,
右键手动弹菜单(不挂原生菜单,规避 Qt 菜单追踪的 clickCount 断言崩溃)。
Windows:托盘图标为辅助,左键切换悬浮余额条,右键走原生菜单。
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QIcon,
                         QPainter, QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .colors import deepseek_color, fill_color, ui_font

IS_MAC = sys.platform == "darwin"


def _draw_battery(size: int, remaining: int | None, offline: bool,
                  color: QColor) -> QPixmap:
    """电池图标:竖置胶囊,容量线性填充(高度 = 内高 × 剩余% / 100)。

    macOS 菜单栏参考系统电池:空 = 只有描边、内部透明;满 = 白色填充;
    低电量(≤20%)红色;数字跨填充线自动反色。Windows 托盘保持
    浅色底 + 彩色填充的原风格。
    """
    s = size / 64.0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if IS_MAC:
        body_brush = QBrush(Qt.BrushStyle.NoBrush)              # 透明内部
        outline = QColor(198, 204, 214, 235)
        fill_color = QColor(236, 240, 246)                      # 白(满)
        if remaining is not None and not offline and remaining <= 20:
            fill_color = QColor(255, 105, 107)                  # 低电量红
        text_on_fill = QColor(36, 42, 52)
        text_on_empty = QColor(240, 244, 250)
        cap_color = QColor(198, 204, 214, 235)
    else:
        body_brush = QColor(232, 238, 244)                      # Windows:浅底
        outline = QColor(120, 130, 145)
        fill_color = color                                      # 电量分级色
        text_on_fill = QColor(36, 42, 52)
        text_on_empty = QColor(36, 42, 52)
        cap_color = QColor(150, 160, 172)

    # 顶部电极帽
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(cap_color)
    p.drawRoundedRect(QRectF(24 * s, 2 * s, 16 * s, 6.5 * s), 3 * s, 3 * s)

    # 电池身:描边 + (透明/浅色)内部
    body = QRectF(10 * s, 10 * s, 44 * s, 52 * s)
    p.setPen(QPen(outline, 3 * s))
    p.setBrush(body_brush)
    p.drawRoundedRect(body, 12 * s, 12 * s)

    body_path = QPainterPath()
    body_path.addRoundedRect(body, 12 * s, 12 * s)

    has_fill = remaining is not None and not offline and remaining > 0
    fill_path = QPainterPath()
    if has_fill:
        inset = 4 * s
        inner = body.adjusted(inset, inset, -inset, -inset)
        fill_h = inner.height() * max(0, min(100, remaining)) / 100
        fill_rect = QRectF(inner.left(), inner.bottom() - fill_h,
                           inner.width(), fill_h)
        fill_path.addRoundedRect(fill_rect, 5.5 * s, 5.5 * s)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill_color)
        p.drawPath(fill_path)

    # 数字/状态字:跨填充线双色——填充区内深色,透明区浅色
    if offline:
        text, t_fill, t_empty = "Z", text_on_empty, text_on_empty
    elif remaining is None:
        text, t_fill, t_empty = "…", text_on_empty, text_on_empty
    else:
        text = str(remaining)
        t_fill, t_empty = text_on_fill, text_on_empty

    p.setFont(_battery_font(size, text))
    p.setClipPath(body_path.subtracted(fill_path))
    p.setPen(QPen(t_empty))
    p.drawText(body, Qt.AlignmentFlag.AlignCenter, text)
    if has_fill:
        p.setClipping(False)
        p.setClipPath(fill_path)
        p.setPen(QPen(t_fill))
        p.drawText(body, Qt.AlignmentFlag.AlignCenter, text)
    p.setClipping(False)
    p.end()
    return pixmap


def _battery_font(size: int, text: str) -> QFont:
    """电池内文字:像素字号随图标尺寸缩放,3 位数略缩。"""
    s = size / 64.0
    font = ui_font(17, bold=True)
    px = 19 * s
    if len(text) >= 3:
        px *= 0.82
    font.setPixelSize(max(8, round(px)))
    return font


def _draw_deepseek(size: int, offline: bool, color: QColor) -> QPixmap:
    """DeepSeek 模式:¥ 圆标。"""
    s = size / 64.0
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 4.5 * s))
    p.setBrush(QColor(232, 238, 244) if not offline else QColor(225, 228, 232))
    p.drawEllipse(QRectF(6 * s, 6 * s, 52 * s, 52 * s))
    p.setPen(QColor(50, 55, 65) if not offline else QColor(120, 126, 136))
    font = ui_font(22, bold=True)
    font.setPixelSize(max(9, round(28 * s)))
    p.setFont(font)
    p.drawText(QRectF(6 * s, 6 * s, 52 * s, 52 * s),
               Qt.AlignmentFlag.AlignCenter, "¥")
    p.end()
    return pixmap


def make_tray_icon(remaining: int | None, status: str,
                   provider: str = "codex", ds_total: float | None = None) -> QIcon:
    """菜单栏图标:多尺寸位图(32/48/64/128)保证 Retina 下清晰。"""
    offline = status != "online"
    icon = QIcon()
    for size in (32, 48, 64, 128):
        if provider == "deepseek":
            color = (deepseek_color(ds_total) if not offline
                     else QColor(170, 177, 186))
            icon.addPixmap(_draw_deepseek(size, offline, color))
        else:
            color = fill_color(remaining, offline)
            icon.addPixmap(_draw_battery(size, remaining, offline, color))
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
