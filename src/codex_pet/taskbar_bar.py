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

from .colors import COL_OFFLINE, deepseek_color, fill_color
from .config import load_config, save_config

COL_BG = QColor(32, 36, 44, 225)
COL_BORDER = QColor(255, 255, 255, 40)
COL_TEXT = QColor(238, 242, 247)
COL_TEXT_DIM = QColor(160, 170, 182)


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


# 独立的 user32 实例:WindowFromPoint 的 argtypes 挂在本模块私有函数指针上,
# 避免与进程中其他代码共享 windll.user32 缓存函数对象时发生类型冲突
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_win_from_point = _user32.WindowFromPoint
_win_from_point.argtypes = [_POINT]
_win_from_point.restype = wintypes.HWND


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
    autoHidden = pyqtSignal()  # 因全屏应用而自动隐藏时发射

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

        self._payload: dict = {}
        self._remaining: int | None = None
        self._drag_offset: QPoint | None = None
        self._moved = False
        self._user_hidden = False
        # 任务栏锚定稳定性:矩形连续两次采样一致且完全在屏内才重新锚定
        self._raw_key = None
        self._stable_count = 0
        self._applied_key = None
        self._stable_base: QPoint | None = None

        self._font = QFont("Segoe UI", 9)
        self._font_bold = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self._dot_color = QColor(150, 158, 168)

        # 倒计时文字每秒刷新;全屏检测/锚定 1 秒;被盖检测 250ms
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._refresh)
        self._tick_timer.start()

        self._maintain_timer = QTimer(self)
        self._maintain_timer.setInterval(1000)
        self._maintain_timer.timeout.connect(self._maintain)
        self._maintain_timer.start()

        self._fast_timer = QTimer(self)
        self._fast_timer.setInterval(250)
        self._fast_timer.timeout.connect(self._reassert_topmost)
        self._fast_timer.start()

        self._refresh()

    # ------------------------------------------------------------------ 数据

    def set_state(self, payload: dict | None) -> None:
        """接收统一状态快照(main.compose 生成)。"""
        self._payload = payload or {}
        self._refresh()

    def anchor_global_point(self) -> QPoint:
        """详情面板锚点:状态条上沿中点。"""
        geo = self.geometry()
        return QPoint(geo.center().x(), geo.top())

    # ------------------------------------------------------------------ 文案

    def _segments(self) -> list[tuple[str, QColor, bool]]:
        """(文字, 颜色, 是否加粗)。"""
        active = self._payload.get("active", "codex")
        status = self._payload.get("status", "offline")
        if active == "deepseek":
            return self._deepseek_segments(status)
        return self._codex_segments(status)

    def _deepseek_segments(self, status: str) -> list[tuple[str, QColor, bool]]:
        ds = self._payload.get("deepseek")
        if status == "error":
            return [("DeepSeek 密钥无效", COL_TEXT_DIM, False)]
        if status != "online":
            return [("DeepSeek 离线", COL_TEXT_DIM, False)]
        if not ds or ds.get("total") is None:
            return [("DeepSeek …", COL_TEXT_DIM, False)]
        total = ds["total"]
        sym = {"CNY": "¥", "USD": "$"}.get(ds.get("currency"), "¥")
        return [("DeepSeek ", COL_TEXT_DIM, False),
                (f"{sym}{total:,.2f}", deepseek_color(total), True)]

    def _codex_segments(self, status: str) -> list[tuple[str, QColor, bool]]:
        codex = self._payload.get("codex") or {}
        primary = codex.get("primary") or {}
        self._remaining = primary.get("remaining")
        if status != "online":
            return [("Codex 离线", COL_TEXT_DIM, False)]
        if self._remaining is None:
            return [("Codex …", COL_TEXT_DIM, False)]
        segs: list[tuple[str, QColor, bool]] = [
            ("Codex ", COL_TEXT_DIM, False),
            (f"{self._remaining}%", fill_color(self._remaining, False), True),
        ]
        cd = self._fmt_countdown(primary.get("resets_at"))
        if cd:
            segs.append((f" · {cd}", COL_TEXT_DIM, False))
        return segs

    def _fmt_countdown(self, resets_at) -> str:
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
        active = self._payload.get("active", "codex")
        if active == "deepseek":
            ds = self._payload.get("deepseek")
            self._dot_color = (deepseek_color(ds.get("total"))
                               if ds else COL_OFFLINE)
        else:
            codex = self._payload.get("codex") or {}
            self._remaining = (codex.get("primary") or {}).get("remaining")
            online = self._payload.get("status") == "online"
            self._dot_color = (fill_color(self._remaining, False)
                               if online and self._remaining is not None
                               else COL_OFFLINE)

    # ------------------------------------------------------------------ 位置

    def _compute_base(self) -> QPoint:
        """按当前任务栏探测结果计算锚点(条右缘贴托盘左侧)。

        任务栏正在动画/滑出屏幕(自动隐藏)时矩形不可靠,回退到整屏右下角。
        """
        screen = self.screen() or QApplication.primaryScreen()
        geo = screen.geometry()
        info = _taskbar_rects()
        if info is not None:
            (tb_l, tb_t, tb_r, tb_b), tray_left = info
            dpr = screen.devicePixelRatio() or 1.0
            tray_left_l = int(tray_left / dpr)
            tl, tt = int(tb_l / dpr), int(tb_t / dpr)
            tr, tb = int(tb_r / dpr), int(tb_b / dpr)
            # 只接受完全在屏内的停靠矩形(动画帧/隐藏态不满足)
            if (tb > tb_t and geo.left() - 2 <= tl and geo.top() - 2 <= tt
                    and tr <= geo.right() + 2 and tb <= geo.bottom() + 2):
                return QPoint(tray_left_l - self.width() - 10,
                              (tt + tb - self.height()) // 2)
        # 回退:整屏右下角(不用 availableGeometry——它随任务栏显隐变化)
        return QPoint(geo.right() - self.width() - 12,
                      geo.bottom() - self.height() - 12)

    def _positioned(self, base: QPoint) -> QPoint:
        """锚点 + 用户偏移,并钳制在整屏内。"""
        cfg = load_config()
        offset = cfg.get("bar_offset")
        if isinstance(offset, list) and len(offset) == 2:
            pos = QPoint(base.x() + int(offset[0]), base.y() + int(offset[1]))
        else:
            pos = QPoint(base)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            pos.setX(max(geo.left(), min(pos.x(), geo.right() - self.width() + 1)))
            pos.setY(max(geo.top(), min(pos.y(), geo.bottom() - self.height() + 1)))
        return pos

    def _apply_position(self) -> None:
        pos = self._positioned(self._compute_base())
        if pos != self.pos():
            self.move(pos)

    def _update_anchor(self) -> None:
        """稳定锚定:任务栏矩形连续两次采样一致且完全在屏内才重定位。

        自动隐藏任务栏的滑入/滑出动画会让矩形每帧都变——期间保持不动,
        彻底避免余额条跟着任务栏动画上下蹦。
        """
        if self._drag_offset is not None:  # 拖拽中不抢位置
            return
        info = _taskbar_rects()
        key = None
        base = None
        if info is not None:
            (tb_l, tb_t, tb_r, tb_b), tray_left = info
            screen = self.screen() or QApplication.primaryScreen()
            geo = screen.geometry()
            dpr = screen.devicePixelRatio() or 1.0
            tl, tt = int(tb_l / dpr), int(tb_t / dpr)
            tr, tb = int(tb_r / dpr), int(tb_b / dpr)
            tray_left_l = int(tray_left / dpr)
            if (tb > tb_t and geo.left() - 2 <= tl and geo.top() - 2 <= tt
                    and tr <= geo.right() + 2 and tb <= geo.bottom() + 2):
                key = (tl, tt, tr, tb, tray_left_l)
                base = QPoint(tray_left_l - self.width() - 10,
                              (tt + tb - self.height()) // 2)
        if key is None:
            # 任务栏隐藏/动画中:保持现状,重置稳定性计数
            self._raw_key = None
            self._stable_count = 0
            return
        if key != self._raw_key:
            self._raw_key = key
            self._stable_count = 1
            return
        self._stable_count += 1
        if self._stable_count < 2:
            return
        if self._applied_key == key:
            return
        self._applied_key = key
        self._stable_base = QPoint(base)
        pos = self._positioned(base)
        if pos != self.pos():
            self.move(pos)

    # ------------------------------------------------------------ 置顶/全屏

    def _maintain(self) -> None:
        """周期维护:全屏应用时自动隐藏 + 稳定锚定(位置不在每秒循环里动)。"""
        if self._user_hidden:
            return
        if self._fullscreen_app_active():
            if self.isVisible():
                self.hide()
                self.autoHidden.emit()
            return
        if not self.isVisible():
            self.show()
        self._update_anchor()

    def set_user_hidden(self, hidden: bool) -> None:
        """用户主动隐藏时,暂停自动显示。"""
        self._user_hidden = hidden

    def _reassert_topmost(self) -> None:
        """周期性保证余额条可见:检测是否被盖住(如点击任务栏后任务栏被
        提到 topmost 层顶端,而余额条恰好住在任务栏区域内),被盖住则用
        HWND_TOP 在 topmost 层内重排到顶端;否则轻量维持置顶。

        注意:这台系统上 NOTOPMOST→TOPMOST 舞步与 hide/show 重显都只会
        把窗口插回 topmost 层底部,唯有 HWND_TOP 能在层内真正重排。
        """
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE

            # 用 WindowFromPoint 探测余额条中心点最顶层的窗口是不是自己
            screen = self.screen() or QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() or 1.0
            pt = _POINT(
                int((self.x() + self.width() / 2) * dpr),
                int((self.y() + self.height() / 2) * dpr),
            )
            covered = True
            hwnd_at = _win_from_point(pt)
            if hwnd_at:
                root = _user32.GetAncestor(hwnd_at, 2)  # GA_ROOT
                covered = root != hwnd

            if covered:
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)  # HWND_TOP
            else:
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_FLAGS)  # HWND_TOPMOST
        except Exception:
            pass

    def _fullscreen_app_active(self) -> bool:
        """前台窗口是否为真正的全屏应用(视频/游戏)→ 此时应隐藏。

        关键:最大化的窗口同样覆盖整块屏幕,但它带有 WS_CAPTION 标题栏样式;
        真正的全屏(全屏视频、游戏、幻灯片)是无标题栏的。仅当
        覆盖整屏 且 无标题栏 且 与余额条在同一块屏幕 时才算全屏。
        """
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
            # 带标题栏的窗口(普通最大化窗口)不算全屏
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            if user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION:
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
            covered = (r.left <= sx0 + tol and r.top <= sy0 + tol
                       and r.right >= sx1 - tol and r.bottom >= sy1 - tol)
            if not covered:
                return False
            # 还需与余额条同一块屏幕(MonitorFromWindow)
            MONITOR_DEFAULTTONEAREST = 2
            bar_hwnd = int(self.winId())
            bar_mon = user32.MonitorFromWindow(bar_hwnd, MONITOR_DEFAULTTONEAREST)
            fg_mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            return bar_mon == fg_mon
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
                # 保存相对稳定锚点的偏移(锚点由 _update_anchor 确认,拖拽期间不被跟随)
                base = self._stable_base or self._compute_base()
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
