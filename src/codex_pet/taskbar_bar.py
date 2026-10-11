"""任务栏文字条:不占用桌面的极简显示。

在任务栏系统托盘左侧显示一行文字,如 "Codex 29% · 2h15m",随配额实时更新。
位置通过 Windows API 探测任务栏与托盘区域来锚定;探测失败时回退为
工作区右下角(任务栏正上方)。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QBrush, QColor, QFont, QFontMetrics, QPainter,
                         QPainterPath, QPen)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from .config import load_config, save_config
from .pet_widget import fill_color

COL_BG = QColor(32, 36, 44, 225)
COL_BORDER = QColor(255, 255, 255, 40)
COL_TEXT = QColor(238, 242, 247)
COL_TEXT_DIM = QColor(160, 170, 182)


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def _taskbar_rects() -> tuple[tuple[int, int, int, int], int] | None:
    """返回 (任务栏矩形, 托盘左边界),均为物理像素;失败返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if not hwnd or not user32.IsWindowVisible(hwnd):
            return None
        tb = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(tb)):
            return None
        tray_left = tb.right
        tray = user32.FindWindowExW(hwnd, 0, "TrayNotifyWnd", None)
        if tray:
            tr = _RECT()
            if user32.GetWindowRect(tray, ctypes.byref(tr)) and tr.left > tb.left:
                tray_left = tr.left
        return (tb.left, tb.top, tb.right, tb.bottom), tray_left
    except Exception:
        return None


class TaskbarBar(QWidget):
    """任务栏上的迷你状态条。left-click 切换详情;拖拽可微调位置。"""

    clicked = pyqtSignal()

    HEIGHT = 24
    PAD_X = 9
    DOT_R = 4.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Codex Pet Bar")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._data: dict | None = None
        self._status = "offline"
        self._remaining: int | None = None
        self._drag_offset: QPoint | None = None
        self._moved = False
        self._user_hidden = False

        self._font = QFont("Segoe UI", 9)
        self._font_bold = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self._dot_color = QColor(150, 158, 168)

        # 每秒刷新倒计时;每 2 秒重锚位置/保持置顶/检测全屏
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._refresh)
        self._tick_timer.start()

        self._anchor_timer = QTimer(self)
        self._anchor_timer.setInterval(2000)
        self._anchor_timer.timeout.connect(self._maintain)
        self._anchor_timer.start()

        self._refresh()

    # ------------------------------------------------------------------ 数据

    def set_limits(self, data: dict | None, status: str) -> None:
        self._data = data
        self._status = status
        self._refresh()

    def anchor_global_point(self) -> QPoint:
        """详情面板锚点:状态条上沿中点。"""
        geo = self.geometry()
        return QPoint(geo.center().x(), geo.top())

    # ------------------------------------------------------------------ 文案

    def _segments(self) -> list[tuple[str, QColor, bool]]:
        """(文字, 颜色, 是否加粗)。"""
        if self._status != "online":
            return [("Codex 离线", COL_TEXT_DIM, False)]
        if self._remaining is None:
            return [("Codex …", COL_TEXT_DIM, False)]
        segs: list[tuple[str, QColor, bool]] = [
            ("Codex ", COL_TEXT_DIM, False),
            (f"{self._remaining}%", fill_color(self._remaining, False), True),
        ]
        cd = self._fmt_countdown()
        if cd:
            segs.append((f" · {cd}", COL_TEXT_DIM, False))
        return segs

    def _fmt_countdown(self) -> str:
        resets_at = (self._data or {}).get("primary", {}).get("resets_at")
        if not resets_at:
            return ""
        secs = max(0, int(resets_at - time.time()))
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h >= 24:
            return f"{h // 24}d{h % 24}h"
        return f"{h}h{m:02d}m" if h else f"{m}m"

    def _measure(self) -> tuple[int, int]:
        from PyQt6.QtGui import QFontMetrics

        width = self.PAD_X * 2 + int(self.DOT_R * 2) + 6
        for text, _color, bold in self._segments():
            fm = QFontMetrics(self._font_bold if bold else self._font)
            width += fm.horizontalAdvance(text)
        return width, self.HEIGHT

    def _refresh(self) -> None:
        self._data_remaining()
        width, height = self._measure()
        if (self.width(), self.height()) != (width, height):
            self.setFixedSize(width, height)
            self._apply_position()
        self.update()

    def _data_remaining(self) -> None:
        if self._status == "online" and self._data:
            self._remaining = self._data.get("primary", {}).get("remaining")
            self._dot_color = fill_color(self._remaining, False)
        else:
            self._remaining = None
            self._dot_color = QColor(150, 158, 168)

    # ------------------------------------------------------------------ 位置

    def _default_pos(self) -> QPoint:
        """任务栏托盘左侧;探测失败则工作区右下角(任务栏正上方)。"""
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        info = _taskbar_rects()
        if info is not None:
            (tb_l, tb_t, tb_r, tb_b), tray_left = info
            dpr = screen.devicePixelRatio() or 1.0
            tray_left_l = int(tray_left / dpr)
            tb_t_l, tb_b_l = int(tb_t / dpr), int(tb_b / dpr)
            geo = screen.geometry()
            # 合理性检查:任务栏顶部需在屏幕内(排除自动隐藏滑出屏幕的情况)
            if tb_t_l < tb_b_l and geo.top() <= tb_t_l < geo.bottom():
                x = tray_left_l - self.width() - 10
                y = (tb_t_l + tb_b_l - self.height()) // 2
                return QPoint(x, y)
        # 回退:工作区右下角
        return QPoint(avail.right() - self.width() - 12,
                      avail.bottom() - self.height() - 12)

    def _apply_position(self) -> None:
        base = self._default_pos()
        cfg = load_config()
        offset = cfg.get("bar_offset")
        if isinstance(offset, list) and len(offset) == 2:
            pos = QPoint(base.x() + int(offset[0]), base.y() + int(offset[1]))
        else:
            pos = base
        if pos != self.pos():
            self.move(pos)

    # ------------------------------------------------------------ 置顶/全屏

    def _maintain(self) -> None:
        """周期维护:位置跟随、置顶层级、全屏应用时自动隐藏。"""
        if self._user_hidden:
            return
        if self._fullscreen_app_active():
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        self._apply_position()
        self._reassert_topmost()

    def set_user_hidden(self, hidden: bool) -> None:
        """用户主动隐藏时,暂停自动显示。"""
        self._user_hidden = hidden

    def _reassert_topmost(self) -> None:
        """周期性重申 TOPMOST,避免被任务栏或后激活的置顶窗口压住。"""
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            hwnd = int(self.winId())
            HWND_TOPMOST = -1
            SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def _fullscreen_app_active(self) -> bool:
        """前台窗口是否全屏覆盖整块屏幕(视频/游戏)→ 此时应隐藏。"""
        if sys.platform != "win32":
            return False
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd or hwnd == int(self.winId()):
                return False
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in ("Shell_TrayWnd", "Progman", "WorkerW",
                             "Shell_SecondaryTrayWnd"):
                return False
            r = _RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
                return False
            screen = self.screen() or QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() or 1.0
            geo = screen.geometry()
            sx0, sy0 = int(geo.left() * dpr), int(geo.top() * dpr)
            sx1, sy1 = int((geo.left() + geo.width()) * dpr), \
                       int((geo.top() + geo.height()) * dpr)
            tol = 4
            return (r.left <= sx0 + tol and r.top <= sy0 + tol
                    and r.right >= sx1 - tol and r.bottom >= sy1 - tol)
        except Exception:
            return False

    # ------------------------------------------------------------------ 绘制

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if os.environ.get("CODEX_PET_DEBUG") == "1":
            # 调试:实心品红,用于验证定位与合成链路
            p.fillRect(self.rect(), QColor(255, 0, 255))
            return

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 7, 7)
        p.setPen(QPen(COL_BORDER, 1))
        p.setBrush(QBrush(COL_BG))
        p.drawPath(path)

        # 状态色圆点
        cy = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._dot_color))
        p.drawEllipse(QPoint(int(self.PAD_X + self.DOT_R), int(cy)),
                      int(self.DOT_R), int(self.DOT_R))

        # 文字段
        x = self.PAD_X + self.DOT_R * 2 + 6
        for text, color, bold in self._segments():
            font = self._font_bold if bold else self._font
            p.setFont(font)
            p.setPen(QPen(color))
            from PyQt6.QtGui import QFontMetrics
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(text)
            p.drawText(QRectF(x, 0, tw, self.height()),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                       text)
            x += tw

    # ------------------------------------------------------------------ 交互

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            if (new_pos - self.pos()).manhattanLength() > 3:
                self._moved = True
            if self._moved:
                self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            if self._moved:
                # 保存相对默认锚点的偏移
                base = self._default_pos()
                cfg = load_config()
                cfg["bar_offset"] = [self.x() - base.x(), self.y() - base.y()]
                save_config(cfg)
            else:
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        refresh = QAction("立即刷新", menu)
        refresh.triggered.connect(lambda: getattr(self, "on_refresh", lambda: None)())
        menu.addAction(refresh)

        reset_pos = QAction("重置位置", menu)
        reset_pos.triggered.connect(self._reset_position)
        menu.addAction(reset_pos)

        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(lambda: getattr(self, "on_quit", self.close)())
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def _reset_position(self) -> None:
        cfg = load_config()
        cfg.pop("bar_offset", None)
        save_config(cfg)
        self._apply_position()
