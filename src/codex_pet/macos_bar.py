"""macOS 菜单栏悬浮条:Windows 任务栏余额条的 macOS 对应实现。

在菜单栏右上角下方悬浮同款胶囊条;NSWindow 设为跨 Space 显示,使所有
桌面 Space 均可见;全屏应用(独占 Space)时自动隐藏,退出恢复。
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from . import macos_native
from .status_bar import StatusBarBase


class MacosBar(StatusBarBase):
    """菜单栏下的迷你状态条。接口与 Windows TaskbarBar 完全一致。"""

    EDGE_GAP_X = 12
    MENUBAR_GAP_Y = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        self._native_ready = False
        super().__init__(parent)

    # ------------------------------------------------------------------ 位置

    def _compute_base(self) -> QPoint:
        """锚点:所在屏菜单栏下方右上角(条右缘距屏右缘 12px)。

        availableGeometry 顶部即菜单栏下沿;不用整屏 top,避免被菜单栏盖住。
        """
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        return QPoint(avail.right() - self.width() - self.EDGE_GAP_X,
                      avail.top() + self.MENUBAR_GAP_Y)

    def _apply_position(self) -> None:
        pos = self._positioned(self._compute_base())
        if pos != self.pos():
            self.move(pos)

    # ------------------------------------------------------------ 全屏维护

    def _maintain(self) -> None:
        """全屏应用(独占 Space)时自动隐藏,退出恢复。

        跨 Space 由 showEvent 时的 NSWindow collectionBehavior 保证;
        这里只负责全屏 Space 内主动隐藏(与 Windows 版行为一致)。
        """
        if self._user_hidden:
            return
        screen = self.screen() or QApplication.primaryScreen()
        geo = screen.geometry()
        fullscreen = macos_native.fullscreen_app_active(
            [(geo.left(), geo.top(), geo.width(), geo.height())],
            exclude_pid=os.getpid(),
        )
        if fullscreen:
            if self.isVisible():
                self.hide()
                self.autoHidden.emit()
            return
        if not self.isVisible():
            self.show()

    # -------------------------------------------------------------- 原生窗口

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._native_ready:
            return
        if QApplication.platformName() != "cocoa":
            # offscreen(测试)等非真实窗口系统的 winId 是假指针,
            # objc_msgSend 会段错误——跳过原生设置
            self._native_ready = True
            return
        self._native_ready = macos_native.setup_floating_window(int(self.winId()))
        # show 途中设 level/跨 Space 会让窗口服务器在初次落位时把窗口约束到
        # 菜单栏下沿;等落位完成后再补一次定位,回到设计锚点
        QTimer.singleShot(0, self._apply_position)
        QTimer.singleShot(200, self._apply_position)
