"""详情面板:点击宠物后在其旁弹出的配额详情浮层。"""

from __future__ import annotations

import ctypes
import sys
import time

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QProgressBar, QVBoxLayout, QWidget)

from .colors import deepseek_color, fill_color

PLAN_NAMES = {
    "plus": "ChatGPT Plus",
    "pro": "ChatGPT Pro",
    "free": "Free",
    "go": "Go",
    "team": "Team",
    "business": "Business",
    "enterprise": "Enterprise",
}

BTN_IDLE = "color: #3b82f6; font-weight: bold; border: none;"
BTN_BUSY = "color: #8a94a3; font-weight: bold; border: none;"
BTN_OK = "color: #2fae74; font-weight: bold; border: none;"
BTN_MISS = "color: #d29a3a; font-weight: bold; border: none;"


def _fmt_countdown(resets_at) -> str:
    if not resets_at:
        return "--"
    secs = max(0, int(resets_at - time.time()))
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h > 24:
        return f"{h // 24}d{h % 24}h"
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


class _LimitRow(QFrame):
    """一行:标题 + 进度条 + 已用% + 重置倒计时。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; color: #444;")
        self.pct_label = QLabel("--%")
        self.pct_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.pct_label)
        layout.addLayout(header)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setRange(0, 100)
        self.bar.setStyleSheet(
            "QProgressBar { background: #e8eef4; border-radius: 5px; }"
            "QProgressBar::chunk { border-radius: 5px; background: #4cd185; }"
        )
        layout.addWidget(self.bar)

        self.reset_label = QLabel("重置于 --")
        self.reset_label.setStyleSheet("color: #8a94a3; font-size: 11px;")
        layout.addWidget(self.reset_label)

    def update_data(self, window: dict | None) -> None:
        if not window:
            self.pct_label.setText("--%")
            self.bar.setValue(0)
            self.reset_label.setText("重置于 --")
            return
        used = window.get("used")
        remaining = window.get("remaining")
        if used is None:
            self.pct_label.setText("--%")
            self.bar.setValue(0)
        else:
            self.pct_label.setText(f"已用 {used}%")
            self.bar.setValue(used)
            color = fill_color(remaining, False)
            self.bar.setStyleSheet(
                "QProgressBar { background: #e8eef4; border-radius: 5px; }"
                f"QProgressBar::chunk {{ border-radius: 5px; background: {color.name()}; }}"
            )
            self.pct_label.setStyleSheet(
                f"font-weight: bold; color: {color.name()};"
            )
        self.reset_label.setText(f"重置于 {_fmt_countdown(window.get('resets_at'))} 后")


class DetailPanel(QWidget):
    """点击宠物时在旁边弹出的详情卡片(独立置顶无边框小窗)。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._payload: dict = {}
        self._keep_rects: list[QRect] = []  # 点击这些区域内不关闭(面板自身 + 余额条)
        self._prev_held = False             # 上次轮询时鼠标按住状态(用于按下沿检测)
        # 刷新反馈:进行中禁用按钮;updated_at 变化 = 拿到新数据;超时提示
        self._refreshing = False
        self._baseline: tuple = ()
        self._btn_restore = QTimer(self)
        self._btn_restore.setSingleShot(True)
        self._btn_restore.timeout.connect(self._restore_btn)
        self._refresh_timeout = QTimer(self)
        self._refresh_timeout.setSingleShot(True)
        self._refresh_timeout.timeout.connect(self._on_refresh_timeout)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_labels)
        # 全局鼠标轮询:点击本进程以外的窗口(任务栏/其他应用)时也能收到
        self._close_poll = QTimer(self)
        self._close_poll.setInterval(80)
        self._close_poll.timeout.connect(self._check_outside_press)

        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { background: rgba(255,255,255,245); border-radius: 14px; }"
        )
        root = QVBoxLayout(card)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        title = QHBoxLayout()
        self.plan_label = QLabel("Codex 配额")
        self.plan_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        title.addWidget(self.plan_label)
        title.addStretch(1)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFlat(True)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(BTN_IDLE)
        title.addWidget(self.refresh_btn)
        root.addLayout(title)

        # ---- DeepSeek 余额分组(active 为 deepseek 时显示在最上) ----
        self.ds_group = QWidget(card)
        ds_layout = QVBoxLayout(self.ds_group)
        ds_layout.setContentsMargins(0, 0, 0, 0)
        ds_layout.setSpacing(4)
        self.ds_title = QLabel("DeepSeek API")
        self.ds_title.setStyleSheet("font-weight: bold; color: #4da3ff;")
        ds_layout.addWidget(self.ds_title)
        self.ds_rows = QLabel("")
        self.ds_rows.setTextFormat(Qt.TextFormat.RichText)
        self.ds_rows.setStyleSheet("color: #444; font-size: 13px;")
        ds_layout.addWidget(self.ds_rows)
        self.ds_note = QLabel("")
        self.ds_note.setStyleSheet("color: #8a94a3; font-size: 11px;")
        ds_layout.addWidget(self.ds_note)
        root.addWidget(self.ds_group)

        # ---- ChatGPT Plus 配额分组 ----
        self.codex_header = QLabel("ChatGPT Plus 配额")
        self.codex_header.setStyleSheet("font-weight: bold; color: #444; font-size: 12px;")
        root.addWidget(self.codex_header)

        self.primary_row = _LimitRow("5 小时窗口", card)
        root.addWidget(self.primary_row)
        self.secondary_row = _LimitRow("周窗口", card)
        root.addWidget(self.secondary_row)

        self.updated_label = QLabel("")
        self.updated_label.setStyleSheet("color: #8a94a3; font-size: 11px;")
        root.addWidget(self.updated_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()

    def set_state(self, payload: dict | None) -> None:
        """接收统一状态快照(main.compose 生成);刷新中检测新数据给出反馈。"""
        self._payload = payload or {}
        if self._refreshing:
            codex = self._payload.get("codex") or {}
            ds = self._payload.get("deepseek") or {}
            if ((codex.get("updated_at"), ds.get("updated_at"))
                    != self._baseline):
                self._finish_refresh(ok=True)
        self._refresh_labels()

    # ------------------------------------------------------------ 刷新反馈

    def begin_refresh(self) -> None:
        """外部触发刷新:按钮进入进行中状态,数据到达/超时后给出反馈。"""
        codex = self._payload.get("codex") or {}
        ds = self._payload.get("deepseek") or {}
        self._baseline = (codex.get("updated_at"), ds.get("updated_at"))
        self._refreshing = True
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("刷新中…")
        self.refresh_btn.setStyleSheet(BTN_BUSY)
        self.updated_label.setText("正在请求最新数据…")
        self._refresh_timeout.start(8000)

    def _finish_refresh(self, ok: bool) -> None:
        if not self._refreshing:
            return
        self._refreshing = False
        self._refresh_timeout.stop()
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("✓ 已刷新" if ok else "未收到新数据")
        self.refresh_btn.setStyleSheet(BTN_OK if ok else BTN_MISS)
        self._btn_restore.start(2500)

    def _restore_btn(self) -> None:
        if not self._refreshing:
            self.refresh_btn.setText("刷新")
            self.refresh_btn.setStyleSheet(BTN_IDLE)

    def _on_refresh_timeout(self) -> None:
        if self._refreshing:
            self._finish_refresh(ok=False)

    def _refresh_labels(self) -> None:
        p = self._payload
        active = p.get("active", "codex")
        codex = p.get("codex")
        ds = p.get("deepseek")

        # DeepSeek 分组
        if active == "deepseek" or ds is not None:
            self.ds_group.setVisible(True)
            self._update_deepseek(ds, p.get("ds_status", "offline"),
                                  active == "deepseek", p.get("model"))
        else:
            self.ds_group.setVisible(False)

        # Codex 分组
        if codex:
            plan = codex.get("plan_type")
            self.plan_label.setText(f"ChatGPT Plus 配额 · {PLAN_NAMES.get(plan, plan or '?')}")
            self.primary_row.update_data(codex.get("primary"))
            self.secondary_row.update_data(codex.get("secondary"))
            updated_at = codex.get("updated_at")
            if updated_at:
                t = time.strftime("%H:%M:%S", time.localtime(updated_at))
                self.updated_label.setText(f"更新于 {t}")
            else:
                self.updated_label.setText("")
        else:
            self.plan_label.setText("ChatGPT Plus 配额(离线)")
            self.primary_row.update_data(None)
            self.secondary_row.update_data(None)
            self.updated_label.setText("等待数据…")
        self.adjustSize()

    def _update_deepseek(self, ds: dict | None, status: str,
                         is_active: bool, model: str | None = None) -> None:
        if status == "error":
            self.ds_rows.setText('<span style="color:#e06c6c;">API 密钥无效或无权限</span>')
            self.ds_note.setText("")
            return
        if status != "online" or not ds:
            self.ds_rows.setText('<span style="color:#8a94a3;">读取中…</span>')
            self.ds_note.setText("")
            return
        sym = {"CNY": "¥", "USD": "$"}.get(ds.get("currency"), "¥")
        total = ds.get("total")
        color = deepseek_color(total).name()
        note = "当前 Codex 正在使用 DeepSeek" if is_active else ""
        if model:
            note += f" · {model}" if note else model
        self.ds_rows.setText(
            f"总余额 <b style='color:{color};'>{sym}{total:,.2f}</b>"
            f" &nbsp;·&nbsp; 赠送 {sym}{ds.get('granted', 0):,.2f}"
            f" &nbsp;·&nbsp; 充值 {sym}{ds.get('topped_up', 0):,.2f}"
        )
        updated_at = ds.get("updated_at")
        if updated_at:
            t = time.strftime("%H:%M:%S", time.localtime(updated_at))
            note = (note + " · " if note else "") + f"更新于 {t}"
        self.ds_note.setText(note)

    def popup_near(self, anchor_global_pos, screen_rect,
                   keep_rects: list[QRect] | None = None) -> None:
        """在宠物旁边弹出;超出屏幕则换边。

        keep_rects:除面板自身外,点击这些区域(如余额条)也不触发关闭。
        """
        self._refresh_labels()
        self._keep_rects = list(keep_rects or [])
        w, h = self.width(), self.height()
        x = anchor_global_pos.x() - w - 12
        if x < screen_rect.left():
            x = anchor_global_pos.x() + 12
        y = max(screen_rect.top(),
                min(anchor_global_pos.y(), screen_rect.bottom() - h))
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start(1000)   # 倒计时每秒刷新
        self._prev_held = self._any_button_held()
        self._close_poll.start()  # 点击外部自动收起

    def hide_panel(self) -> None:
        self._timer.stop()
        self._close_poll.stop()
        self.hide()

    # ------------------------------------------------------------ 点外关闭

    @staticmethod
    def _button_state(vk: int) -> int:
        """返回按键状态位:0x8000=当前按着,0x0001=自上次查询以来按过。"""
        if sys.platform == "win32":
            return ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8001
        if sys.platform == "darwin":
            from . import macos_native
            return macos_native.mouse_button_state(vk)
        return 0

    @classmethod
    def _any_button_held(cls) -> bool:
        return bool((cls._button_state(0x01) | cls._button_state(0x02)) & 0x8000)

    def _check_outside_press(self) -> None:
        """轮询全局鼠标:检测到新的按下且位置在面板/余额条之外 → 收起。

        不依赖 Qt 事件,因此点击任务栏或其他应用同样生效;
        0x0001 锁存位兜底捕捉两次轮询之间完成的极快点击。
        """
        if not self.isVisible():
            return
        l, r = self._button_state(0x01), self._button_state(0x02)
        press_event = bool(l or r)
        held_now = bool((l | r) & 0x8000)
        pressed_edge = press_event and not self._prev_held
        self._prev_held = held_now
        if not pressed_edge:
            return
        gp = QCursor.pos()
        inside = self.geometry().contains(gp) or any(
            rect.contains(gp) for rect in self._keep_rects)
        if not inside:
            self.hide_panel()
