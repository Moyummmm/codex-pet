"""生成应用图标:Qt 离屏绘制电池+⚡ → .icns(iconutil)/ .ico(PyInstaller Windows)。

用法:uv run python scripts/make_icns.py [输出路径]
  *.icns → iconutil 合成(macOS 打包用)
  *.ico  → Qt 直接写出 256px(Windows PyInstaller 用,任意平台可生成)
默认输出 assets/CodexPet.icns。
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

from codex_pet.colors import ui_font

SIZES = [16, 32, 64, 128, 256, 512, 1024]


def draw_icon(size: int) -> QPixmap:
    """圆角底 + 电池主体 + 绿色电量 + ⚡ 徽标。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size / 128.0  # 以 128 为基准的比例因子

    # 圆角渐变底
    path = QPainterPath()
    path.addRoundedRect(QRectF(4 * s, 4 * s, 120 * s, 120 * s), 28 * s, 28 * s)
    from PyQt6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 4 * s, 0, 124 * s)
    grad.setColorAt(0.0, QColor(52, 60, 78))
    grad.setColorAt(1.0, QColor(28, 32, 40))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(path)

    # 电池主体(横置)
    body = QRectF(26 * s, 44 * s, 60 * s, 40 * s)
    p.setPen(QPen(QColor(200, 208, 220), 3.5 * s))
    p.setBrush(QColor(232, 238, 244))
    p.drawRoundedRect(body, 8 * s, 8 * s)
    # 电池正极凸头
    cap = QRectF(86 * s, 55 * s, 6 * s, 18 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(200, 208, 220))
    p.drawRoundedRect(cap, 2.5 * s, 2.5 * s)
    # 电量(约 3/5)
    fill = QRectF(30 * s, 48 * s, 33 * s, 32 * s)
    p.setBrush(QColor(76, 209, 133))
    p.drawRoundedRect(fill, 5 * s, 5 * s)

    # ⚡ 徽标(右下角小圆)
    badge = QRectF(70 * s, 68 * s, 44 * s, 44 * s)
    p.setBrush(QColor(76, 209, 133))
    p.drawEllipse(badge)
    p.setPen(QPen(QColor(24, 30, 38), 2.5 * s))
    p.setBrush(QColor(255, 255, 255))
    zap = QPainterPath()
    zap.moveTo(96 * s, 77 * s)
    zap.lineTo(86 * s, 92 * s)
    zap.lineTo(92 * s, 92 * s)
    zap.lineTo(88 * s, 104 * s)
    zap.lineTo(100 * s, 88 * s)
    zap.lineTo(94 * s, 88 * s)
    zap.closeSubpath()
    p.drawPath(zap)

    p.end()
    return pixmap


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "assets", "CodexPet.icns")
    out = os.path.abspath(out)

    app = QApplication(sys.argv)

    if out.endswith(".ico"):
        # Windows:Qt 自带 ICO 写入;256px 单图,系统负责缩放
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        if not draw_icon(256).save(out):
            print("ico save failed", file=sys.stderr)
            return 1
        print("saved", out)
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "CodexPet.iconset")
        os.makedirs(iconset)
        # 常规与 @2X 两套命名,覆盖到 1024
        entries = {sz: sz for sz in SIZES}
        for logical, px in entries.items():
            pix = draw_icon(px)
            if logical <= 512:
                pix.save(os.path.join(iconset, f"icon_{logical}x{logical}.png"))
            if logical >= 32:
                half = px // 2
                if half in (16, 32, 128, 256, 512):
                    draw_icon(half).save(
                        os.path.join(iconset, f"icon_{half}x{half}@2x.png"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    print("saved", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
