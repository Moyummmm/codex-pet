"""任务栏文字条:不占用桌面的极简显示(Windows)。

在任务栏系统托盘左侧显示一行文字,如 "Codex 29% · 2h15m",随配额实时更新。
位置通过 Windows API 探测任务栏与托盘区域来锚定;探测失败时回退为
工作区右下角(任务栏正上方)。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from .status_bar import StatusBarBase


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


# 独立的 user32 实例:WindowFromPoint 的 argtypes 挂在本模块私有函数指针上,
# 避免与进程中其他代码共享 windll.user32 缓存函数对象时发生类型冲突
if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _win_from_point = _user32.WindowFromPoint
    _win_from_point.argtypes = [_POINT]
    _win_from_point.restype = wintypes.HWND
else:  # 模块在非 Windows 上仅作导入兼容,不触碰 Win32
    _user32 = None
    _win_from_point = None


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


class TaskbarBar(StatusBarBase):
    """任务栏上的迷你状态条。left-click 切换详情;拖拽可微调位置。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        # 任务栏锚定稳定性:矩形连续两次采样一致且完全在屏内才重新锚定
        self._raw_key = None
        self._stable_count = 0
        self._applied_key = None
        self._stable_base: QPoint | None = None
        super().__init__(parent)

        # 被盖检测 250ms(Windows 置顶强化)
        self._fast_timer = QTimer(self)
        self._fast_timer.setInterval(250)
        self._fast_timer.timeout.connect(self._reassert_topmost)
        self._fast_timer.start()

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
