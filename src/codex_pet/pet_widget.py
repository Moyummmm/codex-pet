"""电量条宠物:QPainter 自绘的史莱姆小人,身体填充量 = 配额剩余。"""

from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import QWidget

# 配色
COL_BODY_EMPTY = QColor(232, 238, 244)     # 空体
COL_BODY_EMPTY_DARK = QColor(205, 214, 224)
COL_FULL = QColor(76, 209, 133)            # >60% 绿
COL_MID = QColor(255, 178, 66)             # 30–60% 橙
COL_LOW = QColor(255, 107, 107)            # <30% 红
COL_OFFLINE = QColor(170, 177, 186)        # 离线灰
COL_TEXT = QColor(70, 78, 90)
COL_OUTLINE = QColor(120, 130, 145)


def fill_color(remaining: int | None, offline: bool) -> QColor:
    if offline or remaining is None:
        return COL_OFFLINE
    if remaining > 60:
        return COL_FULL
    if remaining > 30:
        return COL_MID
    return COL_LOW


class PetWidget(QWidget):
    """宠物本体。

    set_limits(data, status) 由外部调用;data 为 CodexClient.limitsUpdated
    的 payload,status 为 "online"/"offline"/"starting"。
    """

    clicked = pyqtSignal()

    BODY_W = 120
    BODY_H = 150
    MARGIN_TOP = 46      # 头顶气泡空间
    MARGIN_BOTTOM = 18   # 小脚
    MARGIN_X = 14

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._remaining: int | None = None
        self._used: int | None = None
        self._resets_at: float | None = None
        self._status = "offline"
        self._phase = 0.0
        self._blink_until = 0.0

        self.setFixedSize(
            self.BODY_W + 2 * self.MARGIN_X,
            self.BODY_H + self.MARGIN_TOP + self.MARGIN_BOTTOM,
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # 呼吸/眨眼动画
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(50)  # 20 fps

    # ------------------------------------------------------------------ 数据

    def set_limits(self, data: dict | None, status: str) -> None:
        self._status = status
        if data and status == "online":
            primary = data.get("primary", {})
            self._used = primary.get("used")
            self._remaining = primary.get("remaining")
            self._resets_at = primary.get("resets_at")
        self.update()

    # ------------------------------------------------------------------ 动画

    def _tick(self) -> None:
        self._phase += 0.05
        # 低电量(<20%)时身体闪烁
        if self._status == "online" and self._remaining is not None and self._remaining < 20:
            if time.time() > self._blink_until:
                self._blink_until = time.time() + 0.9
        self.update()

    # ------------------------------------------------------------------ 绘制

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        body_rect = QRectF(
            (w - self.BODY_W) / 2,
            self.MARGIN_TOP,
            self.BODY_W,
            self.BODY_H,
        )

        # 呼吸:整体上下轻微起伏 + 宽度微变
        breathe = math.sin(self._phase) * 3
        body_rect.translate(0, breathe)

        offline = self._status != "online"
        remaining = self._remaining

        # 低电量闪烁:在 60% 不透明度与全透明度间切换
        blink_off = False
        if (not offline and remaining is not None and remaining < 20
                and time.time() % 0.9 < 0.45):
            blink_off = True

        self._draw_feet(painter, body_rect, offline)
        self._draw_body(painter, body_rect, remaining, offline, blink_off)
        self._draw_face(painter, body_rect, remaining, offline)
        self._draw_bubble(painter, body_rect, remaining, offline)

    def _body_path(self, rect: QRectF) -> QPainterPath:
        """胶囊/史莱姆外形:上半更圆润,底部平。"""
        path = QPainterPath()
        r = rect.width() / 2
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + r * 0.9)
        path.quadTo(rect.left(), rect.top(), rect.center().x(), rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r * 0.9)
        path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()
        return path

    def _draw_body(self, painter: QPainter, rect: QRectF,
                   remaining: int | None, offline: bool, blink_off: bool) -> None:
        body = self._body_path(rect)

        # 空腔底色
        painter.setPen(QPen(COL_OUTLINE, 2.5))
        painter.setBrush(QBrush(COL_BODY_EMPTY))
        painter.drawPath(body)

        if offline or remaining is None:
            return

        # 电量填充:从底部向上裁剪
        fill_h = rect.height() * remaining / 100.0
        if fill_h > 0.5:
            fill_rect = QRectF(rect.left(), rect.bottom() - fill_h,
                               rect.width(), fill_h)
            clip = QPainterPath()
            clip.addRect(fill_rect)
            color = fill_color(remaining, offline)
            grad = QRadialGradient(rect.center(), rect.width())
            grad.setColorAt(0.0, color.lighter(115))
            grad.setColorAt(1.0, color)
            painter.save()
            painter.setClipPath(clip.intersected(body))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(body)
            painter.restore()
            # 液面线
            painter.setPen(QPen(color.darker(120), 2))
            y = rect.bottom() - fill_h
            painter.drawLine(QPointF(rect.left() + 2, y), QPointF(rect.right() - 2, y))
            if blink_off:
                painter.setPen(QPen(QColor(255, 255, 255, 140), 4))
                painter.drawLine(QPointF(rect.left() + 2, y), QPointF(rect.right() - 2, y))

        # 电量刻度线
        painter.setPen(QPen(COL_BODY_EMPTY_DARK, 1))
        for frac in (0.25, 0.5, 0.75):
            y = rect.bottom() - rect.height() * frac
            painter.drawLine(QPointF(rect.left() + 8, y), QPointF(rect.left() + 18, y))

    def _draw_feet(self, painter: QPainter, rect: QRectF, offline: bool) -> None:
        color = COL_OFFLINE if offline else COL_OUTLINE
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        for cx in (rect.left() + rect.width() * 0.28,
                   rect.left() + rect.width() * 0.72):
            painter.drawEllipse(QPointF(cx, rect.bottom() + 6), 9, 6)

    def _draw_face(self, painter: QPainter, rect: QRectF,
                   remaining: int | None, offline: bool) -> None:
        cx = rect.center().x()
        eye_y = rect.top() + rect.height() * 0.32
        dx = 20
        # 眨眼:周期性闭眼
        blink = (self._phase % 6.0) > 5.85

        if offline:
            # 睡觉:闭眼 + Zzz
            painter.setPen(QPen(COL_TEXT, 2.5))
            for ex in (cx - dx, cx + dx):
                painter.drawArc(QRectF(ex - 7, eye_y - 4, 14, 10), 180 * 16, 180 * 16)
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(COL_TEXT))
        happy = remaining is not None and remaining > 60
        for ex in (cx - dx, cx + dx):
            if blink:
                painter.setPen(QPen(COL_TEXT, 2.5))
                painter.drawLine(QPointF(ex - 6, eye_y), QPointF(ex + 6, eye_y))
                painter.setPen(Qt.PenStyle.NoPen)
            elif happy:
                # 眯眼笑:∩ 形闭眼
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(COL_TEXT, 2.5))
                painter.drawArc(QRectF(ex - 7, eye_y - 3, 14, 12), 0, 180 * 16)
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                painter.drawEllipse(QPointF(ex, eye_y), 5, 6.5)

        # 嘴巴:随电量变化(Qt 角度逆时针,180°起画下半圆 = ∪ 微笑)
        mouth_y = eye_y + 22
        painter.setPen(QPen(COL_TEXT, 2.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if remaining is None:
            painter.drawLine(QPointF(cx - 8, mouth_y), QPointF(cx + 8, mouth_y))
        elif remaining > 60:
            painter.drawArc(QRectF(cx - 10, mouth_y - 8, 20, 16), 180 * 16, 180 * 16)
        elif remaining > 30:
            painter.drawLine(QPointF(cx - 8, mouth_y), QPointF(cx + 8, mouth_y))
        else:
            painter.drawArc(QRectF(cx - 10, mouth_y - 8, 20, 16), 0, 180 * 16)
            # 汗滴
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(90, 160, 255)))
            painter.drawEllipse(QPointF(rect.right() - 10, rect.top() + 40), 4, 6)

        # 腮红
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 150, 150, 90)))
        painter.drawEllipse(QPointF(cx - dx - 14, eye_y + 12), 7, 4.5)
        painter.drawEllipse(QPointF(cx + dx + 14, eye_y + 12), 7, 4.5)

    def _fmt_countdown(self) -> str:
        if not self._resets_at:
            return ""
        secs = max(0, int(self._resets_at - time.time()))
        h, rem = divmod(secs, 3600)
        m = rem // 60
        if h > 0:
            return f"{h}h{m:02d}m"
        return f"{m}m"

    def _draw_bubble(self, painter: QPainter, rect: QRectF,
                     remaining: int | None, offline: bool) -> None:
        if offline:
            text = "Zzz…"
            color = COL_OFFLINE
        elif remaining is None:
            text = "…"
            color = COL_TEXT
        else:
            cd = self._fmt_countdown()
            text = f"{remaining}%{(' · ' + cd) if cd else ''}"
            color = fill_color(remaining, offline)

        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(text)
        bw, bh = tw + 18, 24
        bubble = QRectF(
            rect.center().x() - bw / 2,
            rect.top() - bh - 10,
            bw, bh,
        )
        # 气泡随呼吸一起动
        breathe = math.sin(self._phase) * 3
        bubble.translate(0, breathe)

        painter.setPen(QPen(COL_OUTLINE, 1.5))
        painter.setBrush(QBrush(QColor(255, 255, 255, 235)))
        painter.drawRoundedRect(bubble, 10, 10)
        # 气泡小尾巴
        tail = QPainterPath(QPointF(bubble.center().x() - 4, bubble.bottom()))
        tail.lineTo(QPointF(bubble.center().x() + 4, bubble.bottom()))
        tail.lineTo(QPointF(bubble.center().x(), bubble.bottom() + 6))
        tail.closeSubpath()
        painter.drawPath(tail)

        painter.setPen(QPen(color))
        painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------ 交互

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
