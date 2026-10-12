"""共享胶囊条基类:文案、测量、绘制与交互,平台子类只实现定位与维护。

当前仅 Windows 子类(taskbar_bar),锚定 Win32 任务栏托盘;
macOS 走菜单栏电池图标(见 tray.py),不使用悬浮条。
"""

from __future__ import annotations

import os
import time

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QBrush, QColor, QFontMetrics, QPainter,
                         QPainterPath, QPen)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from .colors import COL_OFFLINE, deepseek_color, fill_color, ui_font
from .config import load_config, save_config

COL_BG = QColor(32, 36, 44, 225)
COL_BORDER = QColor(255, 255, 255, 40)
COL_TEXT = QColor(238, 242, 247)
COL_TEXT_DIM = QColor(160, 170, 182)


class StatusBarBase(QWidget):
    """任务栏/菜单栏上的迷你状态条。left-click 切换详情;拖拽可微调位置。

    平台子类需实现:_compute_base(锚点)、_apply_position(落位),
    并按需覆盖 _maintain(周期维护,如全屏隐藏/锚定)。
    """

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

        self._font = ui_font(9)
        self._font_bold = ui_font(9, bold=True)
        self._dot_color = QColor(150, 158, 168)

        # 倒计时文字每秒刷新;锚定/全屏检测每秒维护(平台子类定义行为)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._refresh)
        self._tick_timer.start()

        self._maintain_timer = QTimer(self)
        self._maintain_timer.setInterval(1000)
        self._maintain_timer.timeout.connect(self._maintain)
        self._maintain_timer.start()

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
        """平台锚点:Windows 为任务栏托盘左侧,macOS 为菜单栏下右上角。"""
        raise NotImplementedError

    def _apply_position(self) -> None:
        """按当前锚点落位(平台子类实现)。"""
        raise NotImplementedError

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

    def _maintain(self) -> None:
        """周期维护(平台子类覆盖:全屏隐藏/锚定等)。"""

    def set_user_hidden(self, hidden: bool) -> None:
        """用户主动隐藏时,暂停自动显示。"""
        self._user_hidden = hidden

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
                # 保存相对锚点的偏移(Windows 用稳定锚点,macOS 用即时锚点)
                base = getattr(self, "_stable_base", None) or self._compute_base()
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
